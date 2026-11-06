#!/usr/bin/env python3
"""FantasyCalc top-25 material-movement diagnostic, independent of freshness.

Exit 0: no material drift; 1: material drift; 2: failed check.
Neither 0 nor 1 certifies freshness. Daily acquisition belongs to
pull_fantasycalc_full_feed.py; this command never mutates published data.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO / "data/raw/sources/fantasycalc/week-4/snapshot.json"
API_URL = ("https://api.fantasycalc.com/values/current"
           "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")

# Drift threshold: fraction of sampled values that must move by more than
# 5% to report material drift. This diagnostic says nothing about content
# age or complete-feed equality; even tiny moves must be ingested daily.
DEFAULT_THRESHOLD = 0.20
MOVE_PCT = 0.05
SAMPLE_N = 25


def fetch_live() -> dict[str, float]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    out = {}
    for p in data:
        pl = p.get("player", {})
        name = pl.get("name")
        val = p.get("value")
        if name and val is not None:
            out[name] = float(val)
    return out


def load_snapshot_natives(path: Path | None = None) -> dict[str, float]:
    path = Path(path) if path else SNAPSHOT_PATH
    if not path.exists():
        raise FileNotFoundError(f"snapshot missing: {path}")
    snap = json.load(open(path))
    out = {}
    for row in snap.get("rows", []):
        if row.get("scoring") == "half_ppr" and row.get("teams") == 12:
            nv = row.get("native_value", row.get("value"))
            if row.get("player_name") and nv is not None:
                out[row["player_name"]] = float(nv)
    return out


def check_drift(threshold: float = DEFAULT_THRESHOLD, snapshot: Path | None = None) -> dict:
    live = fetch_live()
    natives = load_snapshot_natives(snapshot)
    if not live:
        raise RuntimeError("live API returned no players")
    if not natives:
        raise RuntimeError("snapshot has no half_ppr/12 natives")

    # Sample the top-N by live value (these matter most for the chart)
    top_live = sorted(live.items(), key=lambda kv: kv[1], reverse=True)[:SAMPLE_N]
    moved = 0
    details = []
    for name, live_val in top_live:
        native_val = natives.get(name)
        if native_val is None:
            moved += 1
            details.append((name, live_val, None, "missing from snapshot"))
            continue
        if native_val == 0:
            continue
        pct_move = abs(live_val - native_val) / native_val
        if pct_move > MOVE_PCT:
            moved += 1
            details.append((name, live_val, native_val, f"{pct_move:.1%}"))
    drift_frac = moved / len(top_live) if top_live else 0.0
    return {
        "drift_frac": drift_frac,
        "moved": moved,
        "sampled": len(top_live),
        "threshold": threshold,
        "needs_refresh": drift_frac > threshold,
        "details": details[:10],
        "live_top3": [n for n, _ in top_live[:3]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="FantasyCalc material-drift diagnostic only; not a freshness check")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--snapshot", type=Path, default=None)
    args = ap.parse_args()
    try:
        result = check_drift(args.threshold, args.snapshot)
    except Exception as exc:
        print(f"DRIFT CHECK FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"drift: {result['moved']}/{result['sampled']} "
          f"({result['drift_frac']:.1%}) vs threshold {result['threshold']:.1%}")
    for name, live_v, nat_v, note in result["details"]:
        print(f"  {name}: live={live_v:.0f} native={nat_v} ({note})")
    print("Material drift detected" if result["needs_refresh"] else "No material drift detected")
    print("Diagnostic only: freshness requires complete per-combo acquisition observations")
    return 1 if result["needs_refresh"] else 0


if __name__ == "__main__":
    sys.exit(main())
