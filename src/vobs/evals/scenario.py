import datetime as dt
import pathlib
import re

import yaml

MODES = {"simulation", "scripted"}
DISFLUENCY = {"off", "low", "medium", "high"}
REQUIRED_FIELDS = {
    "tool_called": ["tool"],
    "regex": ["pattern"],
    "field_value": ["sql", "expect"],
}
PERSONA_KEYS = ("name", "who", "mood", "wants")


def variables() -> dict:
    today = dt.date.today()
    return {
        "today": today.isoformat(),
        "tomorrow": (today + dt.timedelta(days=1)).isoformat(),
        "day_after": (today + dt.timedelta(days=2)).isoformat(),
    }


def _fill(obj, vals):
    if isinstance(obj, str):
        for k, v in vals.items():
            obj = obj.replace("{" + k + "}", v)
        return obj
    if isinstance(obj, list):
        return [_fill(x, vals) for x in obj]
    if isinstance(obj, dict):
        return {k: _fill(v, vals) for k, v in obj.items()}
    return obj


def load_scenario(path) -> dict:
    raw = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: file is empty or is not a scenario card")
    sc = _fill(raw, variables())

    sc["turn_cap"] = sc.get("turn_cap") or 16
    sc["soft_cap"] = sc.get("soft_cap") or 10
    sc["disfluency"] = sc.get("disfluency") or "off"
    sc["inputs"] = sc.get("inputs") or {}
    sc["seed"] = sc.get("seed") or []
    sc["success_checks"] = sc.get("success_checks") or []
    sc["forbidden_checks"] = sc.get("forbidden_checks") or []

    problems = []
    if not sc.get("id"):
        problems.append("missing id")
    if sc.get("mode") not in MODES:
        problems.append(f"mode must be one of {sorted(MODES)}")
    if sc["disfluency"] not in DISFLUENCY:
        problems.append(f"disfluency must be one of {sorted(DISFLUENCY)}")
    if sc["soft_cap"] > sc["turn_cap"]:
        problems.append("soft_cap is bigger than turn_cap")

    if sc.get("mode") == "simulation":
        persona = sc.get("persona") or {}
        for k in PERSONA_KEYS:
            if not persona.get(k):
                problems.append(f"persona is missing '{k}'")
    if sc.get("mode") == "scripted":
        if not isinstance(sc.get("script"), list) or not sc["script"]:
            problems.append("scripted mode needs a non-empty 'script' list")

    for b in sc["seed"]:
        for k in ("name", "phone", "slot"):
            if k not in b:
                problems.append(f"a seed booking is missing '{k}'")

    if not sc["success_checks"] and not sc["forbidden_checks"]:
        problems.append("a scenario needs at least one check")

    seen = set()
    for c in sc["success_checks"] + sc["forbidden_checks"]:
        cid, ctype = c.get("id"), c.get("type")
        if not cid:
            problems.append("a check has no id")
        elif cid in seen:
            problems.append(f"duplicate check id '{cid}'")
        seen.add(cid)
        if ctype not in REQUIRED_FIELDS:
            problems.append(f"check '{cid}' has unknown type '{ctype}'")
            continue
        for k in REQUIRED_FIELDS[ctype]:
            if k not in c:
                problems.append(f"check '{cid}' is missing '{k}'")
        if ctype == "regex" and "pattern" in c:
            try:
                re.compile(c["pattern"])
            except re.error as e:
                problems.append(f"check '{cid}' has a bad pattern: {e}")

    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return sc