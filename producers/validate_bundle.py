"""Validate the staged_bundle against the loader's checks (without loading).

Mirrors pipelines/load_weekly_dashboard.py::load_bundle + dedupe. Exit 0 if
all checks pass, exit 2 if any fail.
"""
import hashlib
import json
import sys

p = "/tmp/wt-jeg421/data/weekly/staged_bundle_wk4_2026-10-05.json"
raw = open(p, "rb").read()
sha = hashlib.sha256(raw).hexdigest()
b = json.loads(raw)
m = b["meta"]

errs = []
if not isinstance(m, dict):
    errs.append("meta not a dict")
w, s = m.get("week"), m.get("season")
if not isinstance(w, int) or not (1 <= w <= 25):
    errs.append(f"meta.week bad: {w!r}")
if not isinstance(s, int) or not (2020 <= s <= 2100):
    errs.append(f"meta.season bad: {s!r}")
if not m.get("built_at") or not isinstance(m["built_at"], str):
    errs.append("meta.built_at bad")
if not isinstance(b.get("players"), list) or not b["players"]:
    errs.append("players not non-empty list")

# dedupe mirroring loader
def classify(r):
    if r.get("vegas_leg") is not None:
        return "FULL"
    if r.get("category") == "no_market_read":
        return "STUB"
    return None

best = {}
shape_count = {"FULL": 0, "STUB": 0}
for i, r in enumerate(b["players"]):
    if not isinstance(r, dict):
        errs.append(f"row {i}: not dict")
        continue
    k = (r.get("player_key") or "").strip().lower()
    if not k:
        errs.append(f"row {i}: missing player_key")
        continue
    sh = classify(r)
    if sh is None:
        errs.append(
            f"player {k}: unrecognized shape "
            f"(no vegas_leg, category={r.get('category')!r})")
        continue
    shape_count[sh] += 1
    prior = best.get(k)
    if prior is None:
        best[k] = sh
    elif prior == sh:
        if sh == "FULL":
            errs.append(f"player {k}: two FULL rows")
        else:
            errs.append(f"player {k}: two STUB rows")
    elif sh == "FULL":
        best[k] = "FULL"

from_espn = sum(1 for r in b["players"]
                if r.get("expert_source") == "espn_ros")

print(f"path: {p}")
print(f"sha256: {sha}")
print(f"bytes: {len(raw)}")
print(f"meta.week={w} season={s}")
print(f"meta.built_at={m['built_at']}")
print(f"meta.expert_source={m.get('expert_source')}")
print(f"meta.expert_leg_replaces={m.get('expert_leg_replaces')}")
print(f"labels: {m.get('labels')}")
print(f"rows: {len(b['players'])} | FULL={shape_count['FULL']} "
      f"STUB={shape_count['STUB']}")
print(f"unique keys after dedupe: {len(best)}")
print(f"players with expert_source=espn_ros: {from_espn}")
print(f"validation errors: {len(errs)}")
for e in errs[:10]:
    print(f"  - {e}")

if errs:
    sys.exit(2)
print("\nVALIDATION OK: bundle passes loader's fail-closed checks.")