import re

ESCALATION = re.compile(r"staff member|call you back|will call you|transfer", re.IGNORECASE)


def classify_call(tools: list[dict], turns: list[dict]) -> tuple[str, str]:
    """tools: [{name, output, is_error}], turns: [{caller, agent, interrupted}]
    Returns (outcome, reason)."""
    # 1. resolved: a booking or cancellation really succeeded
    for t in tools:
        if t["is_error"]:
            continue
        out = t["output"] or ""
        if t["name"] == "book_appointment" and out.startswith("Booked"):
            return "resolved", "booking made"
        if t["name"] == "cancel_appointment" and out.startswith("The booking is cancelled"):
            return "resolved", "booking cancelled"

    # only look at turns where somebody actually said something
    turns = [t for t in turns if t["caller"] or t["agent"]]

    # 2. escalated: agent handed off to a person
    for t in turns:
        if t["agent"] and ESCALATION.search(t["agent"]):
            return "escalated", "agent promised a staff callback or transfer"

    # 3. dropped: call ended abruptly
    if not any(t["caller"] for t in turns):
        return "dropped", "caller never spoke"
    last = turns[-1]
    if not last["agent"]:
        return "dropped", "last caller turn got no agent reply"
    if last["interrupted"]:
        return "dropped", "last agent reply was cut off"

    # 4. open
    return "open", "ended with no completed task"


def classify_trace(conn, trace_id: str) -> tuple[str, str]:
    tool_rows = conn.execute(
        "SELECT coalesce(attributes->>'tool.name', attributes->>'lk.function_tool.name'), "
        "coalesce(attributes->>'tool.output', attributes->>'lk.function_tool.output'), "
        "coalesce(attributes->>'tool.is_error', attributes->>'lk.function_tool.is_error') "
        "FROM spans WHERE trace_id = %s AND name IN ('tool', 'function_tool') "
        "ORDER BY start_time",
        (trace_id,),
    ).fetchall()
    tools = [{"name": n, "output": o, "is_error": e == "true"} for n, o, e in tool_rows]

    turn_rows = conn.execute(
        "SELECT caller_text, agent_text, interrupted FROM transcript_turns "
        "WHERE trace_id = %s ORDER BY turn_time",
        (trace_id,),
    ).fetchall()
    turns = [{"caller": c, "agent": a, "interrupted": bool(i)} for c, a, i in turn_rows]

    return classify_call(tools, turns)