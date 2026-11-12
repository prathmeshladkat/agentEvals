import pytest

from vobs.evals.scenario import load_scenario

GOOD = """
id: t1
mode: scripted
script: ["hello"]
success_checks:
  - id: c1
    type: regex
    pattern: "hello"
"""


def write(tmp_path, text):
    p = tmp_path / "s.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_good_card_gets_defaults(tmp_path):
    sc = load_scenario(write(tmp_path, GOOD))
    assert sc["turn_cap"] == 16 and sc["disfluency"] == "off" and sc["seed"] == []


def test_placeholders_are_filled(tmp_path):
    sc = load_scenario(write(tmp_path, GOOD.replace('"hello"', '"{tomorrow}"')))
    assert "{tomorrow}" not in sc["success_checks"][0]["pattern"]


def test_card_without_checks_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_scenario(write(tmp_path, "id: t\nmode: scripted\nscript: [hi]\n"))


def test_bad_disfluency_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_scenario(write(tmp_path, GOOD + "disfluency: loud\n"))


def test_simulation_needs_persona(tmp_path):
    with pytest.raises(ValueError):
        load_scenario(write(tmp_path, GOOD.replace("scripted", "simulation")))


def test_bad_regex_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_scenario(write(tmp_path, GOOD.replace('"hello"', '"(unclosed"')))