#!/usr/bin/env python3
"""JEG-381: refuse to load CBS ROS legs that differ from the published chart.

The consolidated_values rows for cbsros must carry the same numbers the
published comparison fixture shows (never display unvalidated values). This
compares every rebuilt DDF leg (data/ddf-two-tier/*/ddf_leg_cbsros.json for
one snapshot date) against data/fixtures/current/comparison-sources-data.json
sources.cbsros.combos.<scoring>_<teams>.values (published at 0.1 precision).

Fail-closed (exit 1) unless, for every expected combo:
  * a leg exists for it,
  * the leg's snapshot date equals the fixture's cbsros vintage,
  * the player sets are identical, and
  * every leg value rounds to the published value (|round(v,1) - pub| <= 0.051).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
LEG_SCORING = {"standard": "standard", "half_ppr": "half", "ppr": "full"}
TEAMS = (8, 10, 12, 14)
TOL = 0.051


def compare(leg: dict, published: dict) -> list[str]:
    problems = []
    leg_vals = {v["player_norm"]: float(v["value"]) for v in leg.get("values", [])}
    missing = sorted(set(published) - set(leg_vals))
    extra = sorted(set(leg_vals) - set(published))
    if missing:
        problems.append(f"{len(missing)} published players absent from leg: {missing[:5]}")
    if extra:
        problems.append(f"{len(extra)} leg players not published: {extra[:5]}")
    off = [(p, round(leg_vals[p], 3), published[p]) for p in sorted(set(leg_vals) & set(published))
           if abs(round(leg_vals[p], 1) - float(published[p])) > TOL]
    if off:
        problems.append(f"{len(off)} values differ from published: {off[:5]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="snapshot date, YYYY-MM-DD")
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--legs-dir", type=Path, default=ROOT / "data" / "ddf-two-tier")
    ap.add_argument("--list-out", type=Path, help="write verified leg paths here")
    args = ap.parse_args()

    fx = json.loads(args.fixture.read_text(encoding="utf-8"))
    src = fx["sources"]["cbsros"]
    vintage = src.get("vintage")
    if vintage != args.date:
        print(f"FAIL: fixture cbsros vintage {vintage} != requested {args.date}")
        return 1
    stamp = args.date.replace("-", "")
    verified, failures = [], []
    for scoring, fx_scoring in LEG_SCORING.items():
        for teams in TEAMS:
            combo = f"{fx_scoring}_{teams}"
            published = (src["combos"].get(combo) or {}).get("values")
            leg_path = args.legs_dir / f"ddf-{stamp}-cbsros-{scoring}-{teams}t-0p15" / "ddf_leg_cbsros.json"
            if not published:
                failures.append(f"{combo}: no published values in fixture")
                continue
            if not leg_path.exists():
                failures.append(f"{combo}: leg missing ({leg_path.name} under {leg_path.parent.name})")
                continue
            leg = json.loads(leg_path.read_text(encoding="utf-8"))
            leg_date = (leg.get("inputs") or {}).get("cbsros_snapshot_date")
            problems = ([f"leg snapshot date {leg_date} != {args.date}"] if leg_date != args.date else [])
            problems += compare(leg, published)
            if problems:
                failures.append(f"{combo}: " + "; ".join(problems))
            else:
                verified.append(str(leg_path.relative_to(ROOT)))
                print(f"OK {combo}: {len(published)} players match published values")
    if failures:
        print("FAIL:\n  " + "\n  ".join(failures))
        return 1
    if args.list_out:
        args.list_out.write_text("\n".join(verified) + "\n", encoding="utf-8")
    print(f"all {len(verified)} CBS ROS legs equal the published fixture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
