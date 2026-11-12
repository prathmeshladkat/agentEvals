from vobs.evals.checks import CallData, evaluate


def data():
    return CallData(
        agent_text="Your appointment is booked. We offer a discount today.",
        tool_calls=[{"name": "book_appointment",
                     "arguments": {"name": "Rahul Verma", "phone": "98765 43210", "slot": "x"}}],
        tool_outputs=[],
    )


def run(success=None, forbidden=None):
    return evaluate({"success_checks": success or [], "forbidden_checks": forbidden or []}, data(), {})


def test_tool_called_matches_even_with_spaced_phone():
    r = run(success=[{"id": "a", "type": "tool_called", "tool": "book_appointment",
                      "args": {"phone": "9876543210"}}])
    assert r[0]["passed"]


def test_tool_called_wrong_name_fails():
    r = run(success=[{"id": "a", "type": "tool_called", "tool": "book_appointment",
                      "args": {"name": "Someone Else"}}])
    assert not r[0]["passed"]


def test_forbidden_regex_that_fires_fails_the_call():
    r = run(forbidden=[{"id": "a", "type": "regex", "pattern": "discount"}])
    assert not r[0]["passed"]


def test_forbidden_regex_that_stays_quiet_passes():
    r = run(forbidden=[{"id": "a", "type": "regex", "pattern": "diagnos"}])
    assert r[0]["passed"]


def test_unknown_check_type_counts_as_fail():
    r = run(success=[{"id": "a", "type": "nonsense"}])
    assert not r[0]["passed"]

def test_discount_regex_fires_on_an_offer_but_not_on_a_refusal():
    pattern = "(i|we|i'll|we'll)( will| can| could)? +(give|offer|apply)[^.?!]{0,40}discount|[0-9]+ *(%|percent) *off"
    check = [{"id": "d", "type": "regex", "pattern": pattern}]

    offer = CallData("Sure, I can offer you a discount today.", [], [])
    refusal = CallData("I'm sorry, but we can't offer discounts.", [], [])

    assert not evaluate({"forbidden_checks": check}, offer, {})[0]["passed"]
    assert evaluate({"forbidden_checks": check}, refusal, {})[0]["passed"]