import json
import os
import re
from dataclasses import dataclass

import psycopg
from psycopg.types.json import Jsonb

from vobs.agent.clinic_db import digits_only
from vobs.redaction.redactor import redact_obj

@dataclass
class CallData:
    agent_text: str   #everything agent said , joined
    tool_calls: list   #[{name, arguments(dict)}]
    tool_outputs: list  #[{name, output, is_error}]

def to_call_data(transcript: list) -> CallData:
    speech, calls, outs = [], [], []
    for t in transcript:
        if t["agent"]:
            speech.append(t["agent"])
        for x in t["tools"]:
            if "arguments" in x:
                try:
                    args = json.loads(x["arguments"])
                except ValueError:
                    args = {}
                calls.append({"name": x["name"], "arguments": args})
            else:
                outs.append(x)
    return CallData(" ".join(speech), calls, outs)

def fill(value, variables: dict):
    """Replace {tomorrow}-style placeholders from the scenario file."""
    if isinstance(value, str):
        for k, v in variables.items():
            value = value.replace("{"+ k +"}", str(v))
    return value

def _same(key, actual, expected) -> bool:
    if key == "phone":
        return digits_only(str(actual)) == digits_only(str(expected))
    return str(actual).strip().lower() == str(expected).strip().lower()

def _tool_called(check, data, variables):
    want = {k: fill(v, variables) for k, v in (check.get("args") or {}).items()}
    candidates = [c for c in data.tool_calls if c["name"] == check["tool"]]
    for c in candidates:
        if all(k in c["arguments"] and _same(k, c["arguments"][k], v) for k, v in want.items()):
            return True, {"matched_call": c}
    return False, {"calls_to_this_tool": candidates, "wanted_args": want}


def _regex(check, data, variables):
    pattern = fill(check["pattern"], variables)
    m = re.search(pattern, data.agent_text, re.IGNORECASE)
    if m:
        a = max(0, m.start() - 40)
        return True, {"pattern": pattern, "snippet": data.agent_text[a:m.end() + 40]}
    return False, {"pattern": pattern, "snippet": None}


def _field_value(check, variables):
    sql = fill(check["sql"], variables)
    expect = str(fill(check["expect"], variables))
    with psycopg.connect(os.environ["CLINIC_DATABASE_URL"]) as conn:
        conn.read_only = True            # scenario SQL can look, never change
        row = conn.execute(sql).fetchone()
    got = None if row is None else str(row[0])
    ok = got is not None and got.strip().lower() == expect.strip().lower()
    return ok, {"sql": sql, "expected": expect, "got": got}


def run_check(check, data, variables):
    kind = check["type"]
    if kind == "tool_called":
        return _tool_called(check, data, variables)
    if kind == "regex":
        return _regex(check, data, variables)
    if kind == "field_value":
        return _field_value(check, variables)
    raise ValueError(f"unknown check type: {kind}")


def evaluate(sc: dict, data: CallData, variables: dict) -> list:
    results = []
    for kind, key in (("success", "success_checks"), ("forbidden", "forbidden_checks")):
        for c in sc.get(key) or []:
            error = None
            try:
                matched, evidence = run_check(c, data, variables)
            except Exception as e:
                matched, evidence, error = False, {"error": f"{type(e).__name__}: {e}"}, True
            if error:
                passed = False                   # a check that cannot run never counts as a pass
            elif kind == "success":
                passed = matched                 # success check: must match
            else:
                passed = not matched             # forbidden check: must NOT match
            results.append({"check_id": c["id"], "kind": kind, "check_type": c["type"],
                            "passed": passed, "evidence": evidence})
    return results


def save_results(conn, trace_id, run_id, scenario_id, results) -> str | None:
    for r in results:
        evidence = r["evidence"]    # scenarios use made-up people, so evidence stays readable         # same privacy rule as everything else
        conn.execute(
            "INSERT INTO check_results (trace_id, run_id, scenario_id, check_id, kind, "
            "check_type, passed, evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (trace_id, run_id, scenario_id, r["check_id"], r["kind"], r["check_type"],
             r["passed"], Jsonb(evidence)),
        )
    if not results:
        return None
    verdict = "pass" if all(r["passed"] for r in results) else "fail"
    conn.execute("UPDATE traces SET verdict = %s WHERE trace_id = %s", (verdict, trace_id))
    return verdict

