import asyncio

from dotenv import load_dotenv

load_dotenv()

from livekit.agents import AgentSession
from livekit.plugins import groq

from vobs.agent import clinic_db
from vobs.agent.clinic_agent import ClinicAgent

MESSAGES = [
    "Hi, what times do you have tomorrow?",
    "Eleven works. My name is Rahul and my number is 9 8 7 6 5 4 3 2 1 0.",
    "Yes, please book it.",
]


async def main():
    print("slots created:", clinic_db.reset())   # fresh clinic database every run

    async with AgentSession(llm=groq.LLM(model="openai/gpt-oss-20b")) as session:
        await session.start(ClinicAgent())
        for msg in MESSAGES:
            print("\n=== CALLER:", msg)
            result = await session.run(user_input=msg)
            for ev in result.events:
                print("  ", type(ev).__name__, "|", str(ev)[:300])


asyncio.run(main())