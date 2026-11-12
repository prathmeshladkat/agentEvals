import argparse
import os
import pathlib
import subprocess
import sys
import time
import uuid

import psycopg
from dotenv import load_dotenv

from vobs.evals.scenario import load_scenario

load_dotenv()
RUNNER = pathlib.Path(__file__).parent / "run_scenario.py"
DB = os.environ["DATABASE_URL"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+", help="scenario files, or a folder of them")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--label", default="")
    ap.add_argument("--pause", type=int, default=5, help="seconds to wait between runs")
    a = ap.parse_args()

    files = []
    for t in a.targets:
        p = pathlib.Path(t)
        files += sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    if not files:
        sys.exit("no scenario files found")

    # check every card BEFORE spending anything
    cards, bad = [], []
    for f in files:
        try:
            cards.append((f, load_scenario(f)))
        except Exception as e:
            bad.append(str(e))
    if bad:
        print("Fix these scenario cards first (nothing was run):")
        for b in bad:
            print("  -", b)
        sys.exit(1)

    batch_id = uuid.uuid4().hex[:10]
    plan = [(f, sc, uuid.uuid4().hex[:12]) for _ in range(a.repeats) for f, sc in cards]

    with psycopg.connect(DB) as conn:
        conn.execute("INSERT INTO batches (batch_id, label, repeats, total_runs) VALUES (%s,%s,%s,%s)",
                     (batch_id, a.label, a.repeats, len(plan)))
        for f, sc, rid in plan:
            conn.execute("INSERT INTO runs (run_id, batch_id, scenario_id, status) VALUES (%s,%s,%s,'queued')",
                         (rid, batch_id, sc["id"]))

    print(f"batch {batch_id}: {len(plan)} runs")
    logdir = pathlib.Path("runs") / batch_id
    logdir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}     # the agent writes characters Windows files can't hold by default

    for i, (f, sc, rid) in enumerate(plan, 1):
        print(f"[{i}/{len(plan)}] {sc['id']} ... ", end="", flush=True)
        with open(logdir / f"{rid}.log", "w", encoding="utf-8") as log:
            code = subprocess.run(
                [sys.executable, str(RUNNER), str(f), "--run-id", rid, "--batch-id", batch_id],
                stdout=log, stderr=subprocess.STDOUT, env=env,
            ).returncode
        with psycopg.connect(DB) as conn:
            status = conn.execute("SELECT status FROM runs WHERE run_id = %s", (rid,)).fetchone()[0]
            if status not in ("completed", "failed"):       # the process died without reporting
                conn.execute("UPDATE runs SET status='failed', error=%s, finished_at=now() WHERE run_id=%s",
                             (f"process exited with code {code}", rid))
                status = "failed"
            verdict = conn.execute(
                "SELECT coalesce(t.verdict,'-') FROM runs r LEFT JOIN traces t ON t.trace_id = r.trace_id "
                "WHERE r.run_id = %s", (rid,)).fetchone()[0]
        print(f"{status} / {verdict}")
        time.sleep(a.pause)

    with psycopg.connect(DB) as conn:
        rows = conn.execute(
            "SELECT r.scenario_id, coalesce(t.verdict,'-') FROM runs r "
            "LEFT JOIN traces t ON t.trace_id = r.trace_id WHERE r.batch_id = %s", (batch_id,)).fetchall()

    per = {}
    for sid, v in rows:
        per.setdefault(sid, {"pass": 0, "fail": 0, "other": 0})["pass" if v == "pass" else "fail" if v == "fail" else "other"] += 1
    print("\nSUMMARY (other = invalid or no result, left out of pass rates)")
    total_pass = total_valid = 0
    for sid, c in per.items():
        valid = c["pass"] + c["fail"]
        total_pass += c["pass"]
        total_valid += valid
        print(f"  {sid:<20} pass {c['pass']}/{valid}   other {c['other']}")
    if total_valid:
        print(f"  {'ALL':<20} pass {total_pass}/{total_valid} ({total_pass / total_valid:.0%})")
    print(f"\nbatch id: {batch_id}   logs: {logdir}")


if __name__ == "__main__":
    main()