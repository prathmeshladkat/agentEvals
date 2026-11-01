import os
import httpx
from dotenv import load_dotenv

load_dotenv()
r = httpx.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
    json={
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": "Say hello in five words."}],
    },
    timeout=30,
)
print(r.status_code)
print(r.json())