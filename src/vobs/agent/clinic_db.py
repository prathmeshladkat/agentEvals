import datetime as dt
import os
import re

import psycopg

SCHEMA = """
CREATE TABLE slots (
    slot_time TIMESTAMP PRIMARY KEY
);
CREATE TABLE bookings (
    booking_id SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    phone      TEXT NOT NULL,
    slot_time  TIMESTAMP NOT NULL REFERENCES slots(slot_time),
    status     TEXT NOT NULL DEFAULT 'confirmed'
               CHECK (status IN ('confirmed', 'cancelled'))
);
-- one confirmed booking per slot: the database itself prevents double booking
CREATE UNIQUE INDEX one_booking_per_slot ON bookings(slot_time) WHERE status = 'confirmed';
"""

OPEN_HOURS = [9, 10, 11, 12, 14, 15, 16]   # 13:00 is lunch


def _connect():
    return psycopg.connect(os.environ["CLINIC_DATABASE_URL"])


def digits_only(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def reset(days: int = 7) -> int:
    """Wipe everything and create open slots for the next `days` days."""
    today = dt.date.today()
    slots = [
        dt.datetime.combine(today + dt.timedelta(days=d), dt.time(h))
        for d in range(days)
        for h in OPEN_HOURS
    ]
    with _connect() as conn:
        conn.execute("DROP TABLE IF EXISTS bookings, slots CASCADE")
        conn.execute(SCHEMA)
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO slots (slot_time) VALUES (%s)", [(s,) for s in slots])
    return len(slots)


def free_slots(day: dt.date) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT s.slot_time FROM slots s "
            "LEFT JOIN bookings b ON b.slot_time = s.slot_time AND b.status = 'confirmed' "
            "WHERE s.slot_time::date = %s AND b.booking_id IS NULL "
            "ORDER BY s.slot_time",
            (day,),
        ).fetchall()
    return [r[0].strftime("%H:%M") for r in rows]


def book(name: str, phone: str, slot: dt.datetime) -> tuple[int | None, str]:
    """Returns (booking_id, 'ok') or (None, reason)."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "INSERT INTO bookings (name, phone, slot_time) VALUES (%s, %s, %s) "
                "RETURNING booking_id",
                (name, digits_only(phone), slot),
            ).fetchone()
        return row[0], "ok"
    except psycopg.errors.UniqueViolation:
        return None, "taken"
    except psycopg.errors.ForeignKeyViolation:
        return None, "no_such_slot"


def cancel(booking_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE bookings SET status = 'cancelled' "
            "WHERE booking_id = %s AND status = 'confirmed'",
            (booking_id,),
        )
        return cur.rowcount == 1


def lookup(phone: str) -> list[tuple[int, str, dt.datetime]]:
    with _connect() as conn:
        return conn.execute(
            "SELECT booking_id, name, slot_time FROM bookings "
            "WHERE phone = %s AND status = 'confirmed' ORDER BY slot_time",
            (digits_only(phone),),
        ).fetchall()