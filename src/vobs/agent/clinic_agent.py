import asyncio
import datetime as dt

from livekit.agents import Agent, function_tool

from vobs.agent import clinic_db
from vobs.agent.prompts import build_prompt


class ClinicAgent(Agent):
    def __init__(self):
        super().__init__(instructions=build_prompt(dt.date.today()))

    @function_tool()
    async def check_availability(self, date: str) -> str:
        """Check which appointment times are free on a given day.

        Args:
            date: the day to check, written as YYYY-MM-DD
        """
        try:
            day = dt.date.fromisoformat(date)
        except ValueError:
            return "That date was not understood. Ask the caller for the day again."
        times = await asyncio.to_thread(clinic_db.free_slots, day)
        if not times:
            return f"No free times on {date}."
        return f"Free times on {date}: " + ", ".join(times)

    @function_tool()
    async def book_appointment(self, name: str, phone: str, slot: str) -> str:
        """Book an appointment once the caller has confirmed the time.

        Args:
            name: the caller's name
            phone: the caller's phone number, as digits
            slot: the appointment time, written as YYYY-MM-DD HH:MM
        """
        try:
            when = dt.datetime.strptime(slot, "%Y-%m-%d %H:%M")
        except ValueError:
            return "That time was not understood. Ask the caller to confirm the time."
        booking_id, reason = await asyncio.to_thread(clinic_db.book, name, phone, when)
        if booking_id:
            return f"Booked. The booking number is {booking_id}."
        if reason == "taken":
            return "That time was just taken. Offer another time."
        return "That is not an available time. Check availability again."

    @function_tool()
    async def cancel_appointment(self, booking_id: int) -> str:
        """Cancel an existing appointment.

        Args:
            booking_id: the booking number
        """
        done = await asyncio.to_thread(clinic_db.cancel, booking_id)
        return "The booking is cancelled." if done else "No active booking with that number."

    @function_tool()
    async def lookup_booking(self, phone: str) -> str:
        """Find a caller's upcoming appointments by phone number.

        Args:
            phone: the caller's phone number, as digits
        """
        rows = await asyncio.to_thread(clinic_db.lookup, phone)
        if not rows:
            return "No bookings found for that number."
        return "; ".join(f"booking {i} for {n} at {t:%A %d %B, %H:%M}" for i, n, t in rows)