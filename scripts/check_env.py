import importlib, importlib.util

mods = [
    "livekit.agents", "livekit.plugins.silero", "livekit.plugins.deepgram",
    "livekit.plugins.elevenlabs", "livekit.plugins.groq", "livekit.plugins.openai",
    "opentelemetry.sdk.trace",
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    "fastapi", "uvicorn", "psycopg", "psycopg_pool", "apscheduler",
    "httpx", "yaml", "dotenv",
]
for m in mods:
    try:
        importlib.import_module(m)
        print("ok  ", m)
    except Exception as e:
        print("FAIL", m, "->", type(e).__name__, e)

print("av installed:", importlib.util.find_spec("av") is not None)