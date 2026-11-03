from vobs.evals.outcomes import classify_call


def tool(name, output, is_error=False):
    return {"name": name, "output": output, "is_error": is_error}


def turn(caller, agent, interrupted=False):
    return {"caller": caller, "agent": agent, "interrupted": interrupted}


def test_booking_resolves():
    assert classify_call([tool("book_appointment", "Booked. The booking number is 1.")],
                         [turn("book me", "Done")])[0] == "resolved"


def test_cancel_resolves():
    assert classify_call([tool("cancel_appointment", "The booking is cancelled.")],
                         [turn("cancel it", "Done")])[0] == "resolved"


def test_failed_booking_does_not_resolve():
    out = classify_call([tool("book_appointment", "That time was just taken. Offer another time.")],
                        [turn("book me", "Sorry, that time is taken.")])
    assert out[0] == "open"


def test_tool_error_does_not_resolve():
    out = classify_call([tool("book_appointment", "Booked. The booking number is 1.", is_error=True)],
                        [turn("book me", "Done")])
    assert out[0] != "resolved"


def test_staff_callback_escalates():
    out = classify_call([], [turn("what is the fee", "A staff member will call you back.")])
    assert out[0] == "escalated"


def test_unanswered_last_turn_is_dropped():
    assert classify_call([], [turn("hi", "Hello"), turn("I want to", "")])[0] == "dropped"


def test_cut_off_reply_is_dropped():
    assert classify_call([], [turn("hi", "Hello there", interrupted=True)])[0] == "dropped"


def test_caller_never_spoke_is_dropped():
    assert classify_call([], [turn("", "Hello")])[0] == "dropped"