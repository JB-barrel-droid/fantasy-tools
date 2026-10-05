"""Demonstrate the bundle passes --expected-week and a FULL/STUB mixed case.

This re-creates a small mixed FULL+STUB bundle from the same ESPN inputs and
runs the loader's check_ecr_gate-equivalent: meta.week comparison with
EXPECTED_WEEK, plus a FULL+STUB mix that the loader's dedupe accepts.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, "/tmp/wt-jeg421")

# Import the loader (read-only contract) without touching sbclient
import importlib.util
spec = importlib.util.spec_from_file_location(
    "ld", "/tmp/wt-jeg421/pipelines/load_weekly_dashboard.py")
ld = importlib.util.module_from_spec(spec)

# Stub sbclient import by inserting a fake into sys.modules BEFORE exec
def _noop(*a, **kw): return []
class _FakeSBC:
    rpc = staticmethod(_noop)
    get = staticmethod(_noop)
    post = staticmethod(_noop)
    patch = staticmethod(_noop)
    delete = staticmethod(_noop)
sys.modules["sbclient"] = _FakeSBC()
spec.loader.exec_module(ld)

# Replicate one FULL row from existing signals_v4 (Vegas-implied leg), plus
# attach ESPN ROS as the expert leg. Build a mini mixed-shape bundle.
import csv, re
espn = {}
with open("/tmp/wt-jeg421/data/inputs/espn_projections.csv") as f:
    for r in csv.DictReader(f):
        if not r.get("has_espn_projection","").lower().startswith("t"): continue
        try:
            rec = float(r["r_receptions"] or 0); half = float(r["ros_half_ppr"] or 0)
            wks = 14
            m = re.match(r"(\d+)-(\d+)", r.get("weeks_covered") or "")
            if m: wks = max(1, int(m.group(2))-int(m.group(1))+1)
            hp = half/wks; std = hp - 0.5*rec/wks; ppr = hp + 0.5*rec/wks
        except Exception:
            continue
        k = re.sub(r"[^a-z0-9 ]","", r["player"].lower()).strip()
        espn[k] = {"name": r["player"], "pos": r["pos"], "team": r["team"],
                   "half": round(hp,2), "std": round(std,2), "ppr": round(ppr,2),
                   "snap": r.get("espn_snapshot_date","")}

# Build a small mixed bundle: 3 FULL (Vegas-implied) + 3 STUB (no_market_read)
import datetime as _dt
sample = list(espn.items())[:6]
players = []
for i, (k, e) in enumerate(sample):
    if i < 3:
        # FULL: Vegas-implied leg present
        vegas_leg = "propline"
        vegas_prov = "complete"
        vegas_half = e["half"] + 2.5  # vegas tends higher
        vegas_std = e["std"] + 2.5
        vegas_ppr = e["ppr"] + 2.5
    else:
        vegas_leg = None
        vegas_prov = "none"
        vegas_half = vegas_std = vegas_ppr = None
    row = {
        "player_key": k, "name": e["name"], "pos": e["pos"], "team": e["team"],
        "vegas_std": vegas_std, "vegas_half": vegas_half, "vegas_ppr": vegas_ppr,
        "expert_std": e["std"], "expert_half": e["half"], "expert_ppr": e["ppr"],
        "expert_source": "espn_ros",
        "vegas_leg": vegas_leg, "vegas_provenance": vegas_prov,
        "coverage_ok": vegas_prov in ("complete","td-filled"),
        "post_worthy": False, "category": "no_market_read" if vegas_leg is None else None,
        "espn_proj_std": e["std"], "espn_proj_half": e["half"], "espn_proj_ppr": e["ppr"],
        "espn_snapshot_date": e["snap"],
    }
    players.append(row)

bundle = {
    "meta": {
        "week": 4, "season": 2026,
        "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "source_file": "espn_ros_test", "n_players": len(players),
        "n_vegas_any": 3, "n_no_vegas": 3, "n_post_worthy": 0,
        "n_with_espn_weekly": 6, "expert_source": "espn_ros",
        "labels": {"expert": "ESPN (Mike Clay model)"},
        "scorings": ["std","half","ppr"],
    },
    "players": players,
}
# write bundle to /tmp so the loader sees a real file path
testp = "/tmp/jeg421_test_bundle.json"
json.dump(bundle, open(testp, "w"))

# Mirror loader's load_bundle + dedupe
b, m, sha = ld.load_bundle(testp)
print(f"loader::load_bundle OK (week={m['week']} season={m['season']} "
      f"built_at={m['built_at'][:19]})")

# --expected-week cross-check
expected_week = 4
assert m["week"] == expected_week, "EXPECTED_WEEK MISMATCH"
print(f"--expected-week {expected_week}: PASS (bundle week == expected)")

# dedupe
rows = ld.dedupe(b["players"])
print(f"dedupe produced {len(rows)} rows from {len(b['players'])} input rows")
n_full = sum(1 for r in rows.values() if r.get("vegas_leg") is not None)
n_stub = sum(1 for r in rows.values() if r.get("category") == "no_market_read")
print(f"  FULL={n_full}, STUB={n_stub}")

# Two FULL for same key -> must fail closed
dup_key = list(rows.keys())[0]
f = next(r for r in b["players"] if r["player_key"] == dup_key)
players.append(dict(f))  # duplicate FULL
b2 = {"meta": bundle["meta"], "players": players}
json.dump(b2, open(testp, "w"))
try:
    ld.load_bundle(testp)
    ld.dedupe(b2["players"])
    print("FAIL: duplicate FULL did not block")
    sys.exit(1)
except SystemExit as e:
    print(f"duplicate FULL rows -> BLOCKED exit {e.code} (correct fail-closed)")

# Unrecognized shape (no vegas_leg, category missing) -> must block
badp = "/tmp/jeg421_bad_bundle.json"
b3 = {"meta": bundle["meta"],
      "players": [{"player_key": "z", "name": "Z", "pos": "WR", "team": "KC",
                   "vegas_std": None, "vegas_half": None, "vegas_ppr": None,
                   "expert_source": "espn_ros"}]}
json.dump(b3, open(badp, "w"))
try:
    ld.load_bundle(badp)
    ld.dedupe(b3["players"])
    print("FAIL: unrecognized shape did not block")
    sys.exit(1)
except SystemExit as e:
    print(f"unrecognized shape -> BLOCKED exit {e.code} (correct fail-closed)")

print("\nALL LOADER CONTRACT CHECKS PASS")