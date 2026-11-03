import re
import json
from dataclasses import dataclass, field


DIGIT_WORD = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)"

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 7 or more spoken digit words in a row ("nine eight seven six ...")
SPOKEN_NUMBER = re.compile(
    rf"\b(?:{DIGIT_WORD}[\s,-]+){{6,}}{DIGIT_WORD}\b", re.IGNORECASE
)
# 9 to 14 digits, optionally separated by spaces or dashes, optional +
PHONE = re.compile(r"(?<!\d)\+?\d(?:[\s-]?\d){8,13}(?!\d)")
# cue phrase (any case) followed by a capitalised name
NAME = re.compile(
    r"(?i:\b(?:my name is|this is|i am|i'm))\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

@dataclass
class RedactionResult:
    text: str
    counts: dict = field(default_factory=dict)

def redact(text:str) -> RedactionResult:
    counts: dict = {}

    def bump(kind: str) -> None:
        counts[kind] = counts.get(kind, 0) + 1

    def sub_simple(pattern, kind, s):
        def repl(_m):
            bump(kind)
            return f"[{kind}]"
        return pattern.sub(repl, s)

    text = sub_simple(EMAIL, "EMAIL", text)
    text = sub_simple(SPOKEN_NUMBER, "SPOKEN_NUMBER", text)
    def phone_repl(m):
        if ISO_DATE.search(m.group(0)):
            return m.group(0)   # a date/time, not a phone number
        bump("PHONE")
        return "[PHONE]"

    text = PHONE.sub(phone_repl, text)

    def name_repl(m):
        bump("NAME")
        return m.group(0).replace(m.group(1), "[NAME]")

    text = NAME.sub(name_repl, text)
    return RedactionResult(text, counts)


SENSITIVE_KEYS = {"name": "NAME", "phone": "PHONE", "email": "EMAIL"}


def redact_obj(obj, counts=None):
    """Redact every string inside nested dicts/lists. Returns (clean_obj, counts)."""
    if counts is None:
        counts = {}
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") and s.endswith("}"):      # tool inputs arrive as JSON text
            try:
                inner = json.loads(s)
            except ValueError:
                inner = None
            if isinstance(inner, dict):
                clean, _ = redact_obj(inner, counts)
                return json.dumps(clean), counts
        r = redact(obj)
        for k, n in r.counts.items():
            counts[k] = counts.get(k, 0) + n
        return r.text, counts
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kind = SENSITIVE_KEYS.get(k)
            if kind and isinstance(v, str) and v:
                counts[kind] = counts.get(kind, 0) + 1
                out[k] = f"[{kind}]"
            else:
                out[k] = redact_obj(v, counts)[0]
        return out, counts
    if isinstance(obj, list):
        return [redact_obj(v, counts)[0] for v in obj], counts
    return obj, counts