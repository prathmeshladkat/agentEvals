import os
import pathlib

import psycopg
from dotenv import load_dotenv

load_dotenv()
sql = pathlib.Path("src/vobs/db/schema.sql").read_text()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute(sql)
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY 1"
    ).fetchall()

print([r[0] for r in rows])