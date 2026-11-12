import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from vobs.tracing import attrs as A
from vobs.redaction.redactor import redact_obj

load_dotenv()
pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=5, open=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()


app = FastAPI(title="vobs ingestion", lifespan=lifespan)


class EventIn(BaseModel):
    name: str
    ts_ns: int
    attributes: dict = Field(default_factory=dict)


class SpanIn(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    start_ns: int
    end_ns: int | None = None
    status: str = "ok"
    attributes: dict = Field(default_factory=dict)
    events: list[EventIn] = Field(default_factory=list)


def ts(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v1/spans")
def ingest(batch: list[SpanIn]):
    inserted = 0
    with pool.connection() as conn:
        for s in batch:
            start = ts(s.start_ns)
            end = ts(s.end_ns) if s.end_ns else None
            dur = (s.end_ns - s.start_ns) / 1e6 if s.end_ns else None

            # Children finish (and arrive) before their root, so make sure
            # a trace row exists first. Foreign key needs it.
            conn.execute(
                "INSERT INTO traces (trace_id, started_at) VALUES (%s, %s) "
                "ON CONFLICT (trace_id) DO UPDATE "
                "SET started_at = LEAST(traces.started_at, EXCLUDED.started_at)",
                (s.trace_id, start),
            )

            # The root span carries the call-level tags.
            if s.name == "call":
                a = s.attributes
                conn.execute(
                    "UPDATE traces SET room_name=%s, ended_at=%s, prompt_version=%s, "
                    "model=%s, stt_config=%s, tts_config=%s, injected_fault=%s, run_id=%s, "
                    "scenario_id=%s WHERE trace_id=%s",
                    (
                        a.get(A.CALL_ROOM), end, a.get(A.VERSION_PROMPT), a.get(A.VERSION_MODEL),
                        a.get(A.VERSION_STT), a.get(A.VERSION_TTS), a.get(A.FAULT_INJECTED),
                        a.get(A.RUN_ID), a.get(A.SCENARIO_ID), s.trace_id,
                    ),
                )

            # TODO(pii): redaction goes here, before anything is stored.
            s.attributes, found = redact_obj(s.attributes)
            for e in s.events:
                e.attributes, more = redact_obj(e.attributes)
                for k, n in more.items():
                    found[k] = found.get(k, 0) + n
            for pii_type, n in found.items():
                conn.execute(
                    "INSERT INTO pii_audit (trace_id, span_id, pii_type, count) "
                    "VALUES (%s,%s,%s,%s)",
                    (s.trace_id, s.span_id, pii_type, n),
                )
            cur = conn.execute(
                "INSERT INTO spans (span_id, trace_id, parent_span_id, name, start_time, "
                "end_time, duration_ms, status, attributes) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (span_id) DO NOTHING",
                (s.span_id, s.trace_id, s.parent_span_id, s.name, start, end, dur,
                 s.status, Jsonb(s.attributes)),
            )
            if cur.rowcount == 1:  # skip events if this span was a retry duplicate
                if s.name == "turn":
                    a = s.attributes
                    conn.execute(
                        "INSERT INTO transcript_turns (trace_id, span_id, turn_time, "
                        "caller_text, agent_text, interrupted, e2e_latency) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (span_id) DO NOTHING",
                        (s.trace_id, s.span_id, start, a.get("turn.user_text"),
                         a.get("turn.agent_text"), a.get("turn.interrupted"),
                         a.get("turn.e2e_latency")),
                    )
                inserted += 1
                for e in s.events:
                    conn.execute(
                        "INSERT INTO span_events (span_id, trace_id, name, ts, attributes) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (s.span_id, s.trace_id, e.name, ts(e.ts_ns), Jsonb(e.attributes)),
                    )
    return {"received": len(batch), "inserted": inserted}