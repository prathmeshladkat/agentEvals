import os

import httpx
from dotenv import load_dotenv

load_dotenv()
from vobs.config import AGENT_MODEL

tools = [{
    "type": "function",
    "function": {
        "name": "check_availability",
        "description": "Check free appointment times on a day.",
        "parameters": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date"],
        },
    },
}]

r = httpx.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
    json={
        "model": AGENT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a clinic receptionist. Today is 2026-11-03."},
            {"role": "user", "content": "What times are free tomorrow?"},
        ],
        "tools": tools,
    },
    timeout=30,
)
print(AGENT_MODEL, r.status_code)
print(r.text[:1200])