from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, metrics
from livekit.plugins import deepgram, elevenlabs, groq, silero
from livekit.agents.telemetry import set_tracer_provider
from vobs.tracing.setup import setup_tracing
from vobs.tracing.adapters.livekit import normalize



load_dotenv()


class ClinicAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="You are a friendly receptionist for a small clinic. Keep replies to one or two short sentences."
        )


server = agents.AgentServer()

provider = setup_tracing(adapter=normalize)
set_tracer_provider(provider, metadata={
    "version.prompt": "v1",
    "version.model": "llama-3.3-70b-versatile",
    "version.stt": "nova-3",
    "version.tts": "eleven-default",
})

async def _flush():
    provider.force_flush()
    

@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):
    ctx.add_shutdown_callback(_flush)
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=groq.LLM(model="qwen/qwen3.8-27b"),
        tts=elevenlabs.TTS(),
        vad=silero.VAD.load(),
    )

    def on_metrics(ev):
        m = ev.metrics
        if isinstance(m, metrics.STTMetrics):
            print(f"STT  duration={m.duration:.3f} audio={m.audio_duration:.3f}")
        elif isinstance(m, metrics.LLMMetrics):
            print(
                f"LLM  ttft={m.ttft:.3f} duration={m.duration:.3f} "
                f"prompt_tokens={m.prompt_tokens} completion_tokens={m.completion_tokens}"
            )
        elif isinstance(m, metrics.TTSMetrics):
            print(f"TTS  ttfb={m.ttfb:.3f} duration={m.duration:.3f} chars={m.characters_count}")

    session.on("metrics_collected", on_metrics)

    await session.start(room=ctx.room, agent=ClinicAgent())
    await session.generate_reply(instructions="Greet the caller and ask how you can help.")



if __name__ == "__main__":
    agents.cli.run_app(server)