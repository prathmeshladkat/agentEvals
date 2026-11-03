from dotenv import load_dotenv

load_dotenv()

from vobs.agent.clinic_db import reset

print(f"clinic database reset, {reset()} open slots created")