import os

import psycopg
from dotenv import load_dotenv

from vobs.evals.outcomes import classify_trace

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    ids = [r[0] for r in conn.execute(
        "SELECT trace_id FROM traces WHERE ended_at IS NOT NULL "
        "AND outcome_reason IS NULL ORDER BY started_at"
    ).fetchall()]
    for tid in ids:
        outcome, reason = classify_trace(conn, tid)
        conn.execute(
            "UPDATE traces SET outcome = %s, outcome_reason = %s WHERE trace_id = %s",
            (outcome, reason, tid),
        )
        print(f"{tid[:8]}  {outcome:<10} {reason}")
    print(f"classified {len(ids)} calls")