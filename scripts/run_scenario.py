import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
import time
import uuid

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()

from livekit.agents import AgentSession
from livekit.agents.telemetry import set_tracer_provider
from livekit.plugins import groq

from vobs.agent import clinic_db
from vobs.agent.clinic_agent import ClinicAgent
from vobs.agent.prompts import PROMPT_VERSION
from vobs.config import AGENT_MODEL, SIM_MODEL
from vobs.evals.checks import evaluate, save_results, to_call_data
from vobs.evals.outcomes import classify_trace
from vobs.evals.scenario import load_scenario
from vobs.tracing import attrs as A
from vobs.tracing.adapters.livekit import normalize
from vobs.tracing.setup import setup_tracing

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GREETING = "Hello! Thanks for calling the clinic. How can I help you today?"

DISFLUENCY_TEXT = {
    "off": "",
    "low": " Occasionally start with a filler like 'um' or 'uh'.",
    "medium": " Often use fillers ('um', 'uh', 'like'), sometimes restart a sentence, and now and then trail off with '...'.",
    "high": " Use fillers in most messages, restart sentences, correct yourself mid-sentence, and sometimes send a sentence that trails off unfinished.",
}


def set_status(run_id, scenario_id, status, batch_id=None, trace_id=None, error=None):
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, batch_id, scenario_id, status, trace_id, error, started_at) "
            "VALUES (%s,%s,%s,%s,%s,%s, now()) "
            "ON CONFLICT (run_id) DO UPDATE SET status = EXCLUDED.status, "
            "trace_id = coalesce(EXCLUDED.trace_id, runs.trace_id), "
            "error = coalesce(EXCLUDED.error, runs.error), "
            "started_at = coalesce(runs.started_at, now()), "
            "finished_at = CASE WHEN EXCLUDED.status IN ('completed','failed') "
            "THEN now() ELSE runs.finished_at END",
            (run_id, batch_id, scenario_id, status, trace_id, error),
        )


def clean(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def caller_system_prompt(sc: dict, turn: int) -> str:
    p = sc["persona"]
    wrap = " You have talked long enough. Start wrapping up politely now." if turn >= sc["soft_cap"] else ""
    return (
        "You are a person phoning a clinic. Stay in character.\n"
        f"Name: {p['name']}. Who you are: {p['who']}. Mood: {p['mood']}.\n"
        f"What you want: {p['wants']}. Your phone number: {p.get('phone', '')}. Notes: {p.get('notes', '')}\n"
        "Rules: talk like on a phone call, one or two short sentences. "
        "Only give personal details when asked. Never say you are an AI. "
        "Only when the agent has told you your request is finished (for example, a booking is "
        "confirmed), or you have clearly given up after being refused, say a short goodbye and "
        "end that message with [END]. Never use [END] in your first three messages."
        + DISFLUENCY_TEXT[sc["disfluency"]]
        + wrap
    )


async def caller_says(client, sc, history, turn) -> str:
    body = {
        "model": SIM_MODEL,
        "messages": [{"role": "system", "content": caller_system_prompt(sc, turn)}] + history,
        "temperature": 0.7,
        "max_tokens": 800,
    }
    if "gpt-oss" in SIM_MODEL:
        body["reasoning_effort"] = "low"
    for _ in range(5):
        r = await client.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json=body,
        )
        if r.status_code == 429:
            await asyncio.sleep(6)
            continue
        if r.status_code == 400 and "tool_use_failed" in r.text:
            print("(simulator glitch, asking again)")
            await asyncio.sleep(1)
            continue
        if r.status_code >= 400:
            print("SIMULATOR HTTP", r.status_code, r.text[:500])
        r.raise_for_status()
        text = clean(r.json()["choices"][0]["message"]["content"] or "")
        if text:
            return text
    raise RuntimeError("fake caller produced no text")


def read_events(result):
    agent_parts, tools = [], []
    for ev in result.events:
        kind = type(ev).__name__
        if kind == "ChatMessageEvent" and ev.item.role == "assistant":
            agent_parts.append(" ".join(ev.item.content).strip())
        elif kind == "FunctionCallEvent":
            tools.append({"name": ev.item.name, "arguments": ev.item.arguments})
        elif kind == "FunctionCallOutputEvent":
            tools.append({"name": ev.item.name, "output": ev.item.output, "is_error": ev.item.is_error})
    return " ".join(p for p in agent_parts if p), tools


async def execute(sc, run_id, batch_id) -> bool:
    clinic_db.reset()
    clinic_db.seed(sc["seed"])

    provider = setup_tracing(adapter=normalize)
    set_tracer_provider(provider, metadata={
        "version.prompt": PROMPT_VERSION,
        "version.model": AGENT_MODEL,
        "version.stt": "text-mode",
        "version.tts": "text-mode",
    })
    tracer = provider.get_tracer("vobs.runner")

    scripted = sc["mode"] == "scripted"
    history = [{"role": "user", "content": GREETING}]
    transcript = []
    invalid = None
    trace_id = None

    with tracer.start_as_current_span("call", attributes={
        A.CALL_ROOM: f"text-{sc['id']}",
        A.RUN_ID: run_id,
        A.SCENARIO_ID: sc["id"],
    }) as call_span:
        trace_id = format(call_span.get_span_context().trace_id, "032x")

        async with httpx.AsyncClient(timeout=30) as client:
            async with AgentSession(llm=groq.LLM(model=AGENT_MODEL)) as session:
                await session.start(ClinicAgent(sc["inputs"]))

                for turn in range(1, sc["turn_cap"] + 1):
                    if scripted:
                        if turn > len(sc["script"]):
                            break
                        said = sc["script"][turn - 1]
                        ended = turn == len(sc["script"])
                    else:
                        try:
                            said = await caller_says(client, sc, history, turn)
                        except Exception as e:
                            print(f"SIMULATOR ERROR (not the agent's fault): {e}")
                            invalid = "simulator error"
                            break
                        ended = "[END]" in said and turn >= 4
                        said = said.replace("[END]", "").strip()
                        if not said:
                            print("SIMULATOR ERROR (not the agent's fault): empty caller message")
                            invalid = "empty caller message"
                            break
                    print(f"\nCALLER: {said}")

                    try:
                        result = await session.run(user_input=said)
                        agent_text, tools = read_events(result)
                        agent_error = None
                    except Exception as e:
                        agent_text, tools, agent_error = "", [], f"{type(e).__name__}: {e}"
                        print(f"AGENT ERROR: {agent_error[:200]}")

                    print(f"AGENT:  {agent_text or '(silence)'}")
                    for t in tools:
                        print(f"   tool: {t}")

                    transcript.append({"turn": turn, "caller": said, "agent": agent_text,
                                       "tools": tools, "agent_error": agent_error})
                    history.append({"role": "assistant", "content": said})
                    history.append({"role": "user", "content": agent_text or "(silence)"})

                    if agent_error:
                        break           # an agent failure is a real result: stop and score it
                    if ended:
                        print("(caller ended the call)")
                        break
                    await asyncio.sleep(2)

    provider.force_flush()      # call record must be in the database before scoring

    out = pathlib.Path("runs")
    out.mkdir(exist_ok=True)
    f = out / f"{sc['id']}_{run_id}.json"
    f.write_text(json.dumps({"scenario": sc, "transcript": transcript}, indent=2), encoding="utf-8")
    print(f"\nsaved {f}  ({len(transcript)} caller messages)")

    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            if not conn.execute("SELECT 1 FROM traces WHERE trace_id = %s", (trace_id,)).fetchone():
                msg = "call record never reached the database (is the API running?)"
                print(f"\nRUN FAILED: {msg}")
                set_status(run_id, sc["id"], "failed", batch_id, trace_id, msg)
                return False
            if invalid:
                conn.execute("UPDATE traces SET verdict = 'invalid' WHERE trace_id = %s", (trace_id,))
                print(f"\nRUN INVALID ({invalid}): checks skipped")
                set_status(run_id, sc["id"], "failed", batch_id, trace_id, f"invalid run: {invalid}")
                return False

            set_status(run_id, sc["id"], "scoring", batch_id, trace_id)
            results = evaluate(sc, to_call_data(transcript), {})
            verdict = save_results(conn, trace_id, run_id, sc["id"], results)
            outcome, reason = classify_trace(conn, trace_id)
            conn.execute(
                "UPDATE traces SET outcome = %s, outcome_reason = %s WHERE trace_id = %s",
                (outcome, reason, trace_id),
            )
            print("\nCHECKS")
            for r in results:
                print(f"  {'PASS' if r['passed'] else 'FAIL'}  [{r['kind']}] {r['check_id']}")
            print(f"VERDICT: {verdict}   OUTCOME: {outcome} ({reason})")
        set_status(run_id, sc["id"], "completed", batch_id, trace_id)
        return True
    finally:
        provider.shutdown()


async def main(path, run_id, batch_id) -> bool:
    sc = load_scenario(path)
    set_status(run_id, sc["id"], "simulating", batch_id)
    try:
        return await execute(sc, run_id, batch_id)
    except Exception as e:
        set_status(run_id, sc["id"], "failed", batch_id, error=f"{type(e).__name__}: {e}"[:500])
        raise


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--batch-id", default=None)
    args = ap.parse_args()
    ok = asyncio.run(main(args.scenario, args.run_id or uuid.uuid4().hex[:12], args.batch_id))
    sys.exit(0 if ok else 1)