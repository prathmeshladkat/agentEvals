CREATE TABLE IF NOT EXISTS traces (
    trace_id        TEXT PRIMARY KEY,
    room_name       TEXT,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    outcome         TEXT NOT NULL DEFAULT 'open'
                    CHECK (outcome IN ('resolved','escalated','dropped','open')),
    prompt_version  TEXT,
    model           TEXT,
    stt_config      TEXT,
    tts_config      TEXT,
    injected_fault  TEXT,
    run_id          TEXT
);

CREATE TABLE IF NOT EXISTS spans (
    span_id         TEXT PRIMARY KEY,
    trace_id        TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    parent_span_id  TEXT,
    name            TEXT NOT NULL,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ,
    duration_ms     DOUBLE PRECISION,
    status          TEXT NOT NULL DEFAULT 'ok',
    attributes      JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS span_events (
    id          BIGSERIAL PRIMARY KEY,
    span_id     TEXT NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
    trace_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    attributes  JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS transcript_turns (
    id           BIGSERIAL PRIMARY KEY,
    trace_id     TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    span_id      TEXT NOT NULL UNIQUE,
    turn_time    TIMESTAMPTZ NOT NULL,
    caller_text  TEXT,
    agent_text   TEXT,
    interrupted  BOOLEAN,
    e2e_latency  DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS pii_audit (
    id          BIGSERIAL PRIMARY KEY,
    trace_id    TEXT NOT NULL,
    span_id     TEXT NOT NULL,
    pii_type    TEXT NOT NULL,
    count       INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_spans_trace  ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_name   ON spans(name, start_time);
CREATE INDEX IF NOT EXISTS idx_events_trace ON span_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_start ON traces(started_at);
CREATE INDEX IF NOT EXISTS idx_transcript_trace ON transcript_turns(trace_id, turn_time);
CREATE INDEX IF NOT EXISTS idx_pii_audit_trace ON pii_audit(trace_id);
ALTER TABLE traces ADD COLUMN IF NOT EXISTS outcome_reason TEXT;