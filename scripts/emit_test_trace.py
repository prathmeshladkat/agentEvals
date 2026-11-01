import time

from vobs.tracing import attrs as A
from vobs.tracing.setup import setup_tracing

provider = setup_tracing()
tracer = provider.get_tracer("vobs.test")

with tracer.start_as_current_span("call", attributes={
    A.CALL_ROOM: "test-room", A.VERSION_PROMPT: "v1", A.VERSION_MODEL: "qwen/qwen3.8-27b",
    A.VERSION_STT: "nova-3", A.VERSION_TTS: "eleven-default",
}):
    for i in (1, 2):
        with tracer.start_as_current_span("turn", attributes={"turn_index": i}):
            with tracer.start_as_current_span("stt"):
                time.sleep(0.05)
            with tracer.start_as_current_span("llm", attributes={"ttft_ms": 340}):
                time.sleep(0.10)
            if i == 2:
                with tracer.start_as_current_span("tool", attributes={"tool_name": "check_availability"}):
                    time.sleep(0.20)
                with tracer.start_as_current_span("llm"):
                    time.sleep(0.10)
            with tracer.start_as_current_span("tts") as tts:
                tts.add_event("interruption", {"caller_speech_ms": 300})
                time.sleep(0.10)

provider.shutdown()   # flushes the batch; without this the last spans never leave
print("done")