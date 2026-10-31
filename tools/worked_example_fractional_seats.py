#!/usr/bin/env python3
"""Write the fractional-seat variant of the value pipeline's worked example
(JEG-1335; Jeremy, 2026-10-30, option A of JEG-1333).

tests/fixtures/value_pipeline_worked_example.json keeps the hard VP-2.2 rule
(setting.seat_sigma = 0), so its hand-checked numbers stand. This block,
variant_fractional_seats, runs the same league at the default seat sigma
(setting_change seat_sigma = null, i.e. 0.75 PPG): flex seats and, with no
league loaded, bench seats shared near the cutoff, the pipeline run once per
whole allocation and blended by weight. It pins the mix (each allocation's
weight, flex and bench), the expected counts, every row's blended DDF Value
and tier, and the default ranking.

Values come from pipelines/value_reference.py, rounded to 6 decimals; the
engine (value-model.js) and the spec reference (pipelines/spec_reference)
must reproduce them to 1e-6 (tests/test_fractional_seats_worked_example.py).

Usage: python3 tools/worked_example_fractional_seats.py [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
import value_reference as ref  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "value_pipeline_worked_example.json"
KEY = "variant_fractional_seats"
SETTING_CHANGE = {"seat_sigma": None}
COUNTS = ("flex", "bench", "starters", "rostered")


def run(fx: dict) -> dict:
    s = {**fx["setting"], **SETTING_CHANGE}
    league = ref.League(teams=s["teams"], slots=dict(s["slots"]), flex=s["flex"], superflex=s["superflex"],
                        bench=s["bench_per_team"], bench_share=s["bench_share"],
                        flex_eligible=tuple(s["flex_eligible"]), seat_sigma=s.get("seat_sigma"))
    sources = {k: ref.SourceInput(k, v["family"], {int(i): float(x) for i, x in v["values"].items()})
               for k, v in fx["inputs"].items()}
    pos_of = {int(i): p["pos"] for i, p in fx["players"].items()}
    included = [k for k, v in fx["inputs"].items() if v["status"] == "included"]
    return ref.run_pipeline(league, sources, pos_of, included)


def expected(res: dict) -> dict:
    return {
        "allocation_mix": [{"weight": round(e["weight"], 6),
                            "allocation": {p: {c: e["allocation"][p][c] for c in ("flex", "bench")}
                                           for p in ref.POSITIONS}}
                           for e in res["allocation_mix"]],
        "allocation_expected": {p: {c: round(res["allocation_expected"][p][c], 6) for c in COUNTS}
                                for p in ref.POSITIONS},
        "rows_ddf_blended": {str(k): (None if r["ddf"]["blended"]["value"] is None
                                      else round(r["ddf"]["blended"]["value"], 6))
                             for k, r in sorted(res["rows"].items())},
        "rows_ddf_tier": {str(k): r["ddf_tier"] for k, r in sorted(res["rows"].items())},
        "default_ranking": [int(k) for k in res["default_ranking"]],
    }


def block(fx: dict) -> dict:
    return {
        "note": ("JEG-1335: the fixture's league at the default seat sigma (0.75 PPG): flex seats, and "
                 "with no league loaded the bench seats, are shared near the cutoff; the pipeline runs once "
                 "per whole allocation and every value is weight-averaged. Written by "
                 "tools/worked_example_fractional_seats.py from pipelines/value_reference.py."),
        "setting_change": SETTING_CHANGE,
        "expected": expected(run(fx)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if the fixture's block is out of date")
    args = ap.parse_args()
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    new = block(fx)
    if args.check:
        if fx.get(KEY) != json.loads(json.dumps(new)):
            print(f"{KEY} is out of date: run python3 tools/worked_example_fractional_seats.py", file=sys.stderr)
            return 1
        return 0
    fx[KEY] = new
    FIXTURE.write_text(json.dumps(fx, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
