import os

AGENT_MODEL = os.getenv("AGENT_MODEL", "openai/gpt-oss-20b")
SIM_MODEL = os.getenv("SIM_MODEL", AGENT_MODEL)   # the model that plays the fake caller