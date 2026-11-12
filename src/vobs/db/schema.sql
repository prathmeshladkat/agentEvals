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
ALTER TABLE traces ADD COLUMN IF NOT EXISTS scenario_id TEXT;

CREATE OR REPLACE VIEW transcript AS
WITH base AS (
  SELECT tt.*,
    (SELECT count(*) FROM spans s
      WHERE s.parent_span_id = tt.span_id AND s.name IN ('tool','function_tool')) AS tools
  FROM transcript_turns tt
), w AS (
  SELECT *,
    lead(caller_text) OVER o AS next_caller,
    lead(agent_text)  OVER o AS next_agent,
    lag(tools)        OVER o AS prev_tools,
    lag(agent_text)   OVER o AS prev_agent
  FROM base
  WINDOW o AS (PARTITION BY trace_id ORDER BY turn_time)
)
SELECT trace_id, span_id, turn_time, caller_text,
  CASE WHEN coalesce(agent_text,'') = '' AND tools > 0
            AND coalesce(next_caller,'') = '' AND coalesce(next_agent,'') <> ''
       THEN next_agent ELSE agent_text END AS agent_text,
  interrupted, e2e_latency
FROM w
WHERE NOT (coalesce(caller_text,'') = '' AND coalesce(agent_text,'') <> ''
           AND coalesce(prev_tools,0) > 0 AND coalesce(prev_agent,'') = '');

ALTER TABLE traces ADD COLUMN IF NOT EXISTS verdict TEXT;

CREATE TABLE IF NOT EXISTS check_results (
    id          BIGSERIAL PRIMARY KEY,
    trace_id    TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    run_id      TEXT,
    scenario_id TEXT,
    check_id    TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('success','forbidden')),
    check_type  TEXT NOT NULL,
    passed      BOOLEAN NOT NULL,
    evidence    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_checks_trace ON check_results(trace_id);

CREATE TABLE IF NOT EXISTS batches (
    batch_id    TEXT PRIMARY KEY,
    label       TEXT,
    repeats     INTEGER NOT NULL,
    total_runs  INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    batch_id     TEXT,
    scenario_id  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued','simulating','scoring','completed','failed')),
    error        TEXT,
    trace_id     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_runs_batch ON runs(batch_id);