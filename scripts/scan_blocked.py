import ctypes
import pathlib
import sys

site = pathlib.Path(sys.prefix) / "Lib" / "site-packages"
files = sorted(list(site.rglob("*.pyd")) + list(site.rglob("*.dll")))

ok, blocked, other = 0, [], []
for p in files:
    try:
        ctypes.WinDLL(str(p))
        ok += 1
    except OSError as e:
        msg = str(e)
        if "Application Control" in msg or "4551" in msg:
            blocked.append(p)
        else:
            other.append((p, msg))

print(f"loaded fine: {ok}")
print(f"BLOCKED by Application Control: {len(blocked)}")
for p in blocked:
    print("  ", p.relative_to(site))
print(f"failed for other reasons (usually harmless): {len(other)}")