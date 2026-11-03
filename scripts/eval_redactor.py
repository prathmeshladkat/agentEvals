import json
import pathlib

from vobs.redaction.redactor import redact, redact_obj

cases = [json.loads(l) for l in pathlib.Path("data/pii_testset/cases.jsonl").read_text().splitlines() if l.strip()]

expected = removed = 0
clean_total = clean_changed = 0
leaks, false_alarms = [], []

for c in cases:
    out = redact_obj(c["text"])[0]
    for p in c["pii"]:
        expected += 1
        if p["value"] not in out:
            removed += 1
        else:
            leaks.append((p["type"], c["text"]))
    if not c["pii"]:
        clean_total += 1
        if out != c["text"]:
            clean_changed += 1
            false_alarms.append((c["text"], out))

print(f"cases: {len(cases)}")
print(f"private values removed: {removed}/{expected}  (recall {removed/expected:.0%})")
print(f"clean sentences wrongly changed: {clean_changed}/{clean_total}")
print("\nLEAKS:")
for t, s in leaks:
    print(f"  [{t}] {s}")
print("\nFALSE ALARMS:")
for before, after in false_alarms:
    print(f"  {before}  ->  {after}")