#!/usr/bin/env python3
"""Write the expected-starts variants of the value pipeline's worked example
(JEG-536; docs/methodology.md ES-11, ES-15).

tests/fixtures/value_pipeline_worked_example.json gains two blocks:

  variant_expected_starts            the fixture's league (bench 3 per team) with lineup parameters:
                                     the ES-5 parts replace the slices, the bench
                                     share is computed (no override)
  variant_expected_starts_override   the same with the bench-share override at 0.10

Each pins the chart sigma, every source's lines, bands, availability, parts,
groups, own weights, rates and per-player values, the DDF weights and budgets,
every row's blended DDF Value, lineup share and start-worthy probability, and
the bench-share readout. Values come from pipelines/value_reference.py and are
rounded to 6 decimals; the engine (value-model.js) and the clean-room spec
reference (pipelines/spec_reference) must reproduce them to 1e-6 (they share no
code with it). The lineup parameters are round numbers chosen for a hand-sized
league, not the measured ones.

Usage: python3 tools/worked_example_expected_starts.py [--check]
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

LINEUP = {
    "bye": 0.08,
    "projection_confidence": 1.5,
    "positions": {
        "QB": {"m": 0.11, "sigma_rel": 0.18, "sigma_floor": 0.7},
        "RB": {"m": 0.15, "sigma_rel": 0.28, "sigma_floor": 0.85},
        "WR": {"m": 0.12, "sigma_rel": 0.30, "sigma_floor": 1.0},
        "TE": {"m": 0.15, "sigma_rel": 0.35, "sigma_floor": 0.65},
    },
}
OVERRIDE = 0.10
# Bench 3 per team gives WR three bench seats over two teams, so a second
# depth band (ES-3.2) and n_per_team = 2 (round half to even of 3 / 2) are
# exercised; projection confidence 1.5 scales the chart sigma (ES-14).
SETTING_CHANGE = {"bench_per_team": 3}


def r6(x):
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {str(k): r6(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [r6(v) for v in x]
    return x


def run(fx: dict, override: float | None):
    s = {**fx["setting"], **SETTING_CHANGE}
    league = ref.League(teams=s["teams"], slots=dict(s["slots"]), flex=s["flex"], superflex=s["superflex"],
                        bench=s["bench_per_team"], bench_share=s["bench_share"],
                        flex_eligible=tuple(s["flex_eligible"]), bench_share_override=override)
    sources = {k: ref.SourceInput(k, v["family"], {int(i): float(x) for i, x in v["values"].items()})
               for k, v in fx["inputs"].items()}
    pos_of = {int(i): p["pos"] for i, p in fx["players"].items()}
    included = [k for k, v in fx["inputs"].items() if v["status"] == "included"]
    return ref.run_pipeline(league, sources, pos_of, included, lineup=LINEUP)


def readout(res: dict) -> dict:
    b = res["bench_share_readout"]
    return {k: b[k] for k in ("QB", "RB", "WR", "TE", "overall", "override", "fill_in_share")}


def full(res: dict) -> dict:
    sources = {}
    for k, d in res["sources"].items():
        positions = {}
        for p, pi in d["positions"].items():
            if pi["method"] == "no_players":
                positions[p] = {"method": "no_players"}
                continue
            positions[p] = {"waiver_value": pi["waiver_value"], "starter_line": pi["starter_line"],
                            "avail": pi["avail"], "bands": pi["bands"],
                            "lineup": {"n_per_team": pi["lineup"]["n_per_team"],
                                       "sigma_rel": pi["lineup"]["sigma_rel"],
                                       "sigma_floor": pi["lineup"]["sigma_floor"]}}
        players = {i: {"bench_slice": pl["bench_slice"], "starter_slice": pl["starter_slice"],
                       "lineup_share": pl["lineup_share"], "start_worthy": pl["start_worthy"],
                       "adjusted": pl["adjusted"], "vorp_display": pl["vorp_display"]}
                   for i, pl in d["players"].items()}
        sources[k] = {"groups": d["groups"], "total_vorp": d["total_vorp"], "surplus_total": d["surplus_total"],
                      "weights": d["weights"], "rates": d["rates"], "vorp_display_factor": d["vorp_display_factor"],
                      "positions": positions, "players": players}
    rows = {i: {"ddf_blended": r["ddf"]["blended"]["value"], "lineup_share": r["lineup_share"],
                "start_worthy": r["start_worthy"]} for i, r in res["rows"].items()}
    return {"chart_sigma": {p: v["sigma_rel"] for p, v in res["chart_sigma"].items()},
            "bench_share_applied": res["bench_share_applied"], "ddf_weights": res["ddf_weights"],
            "group_budgets": res["group_budgets"], "bench_share_readout": readout(res),
            "sources": sources, "rows": rows}


def build(fx: dict) -> dict:
    main = run(fx, None)
    over = run(fx, OVERRIDE)
    return {
        "variant_expected_starts": r6({
            "note": ("ES-5 parts replace the VP-2.6 slices (docs/methodology.md ES-0..ES-15, JEG-536); "
                     "bench share computed (no override). Lineup parameters are round illustrative numbers. "
                     "Written by tools/worked_example_expected_starts.py from pipelines/value_reference.py; "
                     "value-model.js and pipelines/spec_reference reproduce it to 1e-6."),
            "lineup": LINEUP, "setting_change": {**SETTING_CHANGE, "bench_share_override": None}, "expected": full(main)}),
        "variant_expected_starts_override": r6({
            "note": "As variant_expected_starts with the reader's bench-share override at 0.10 (ES-14, VP-3.4).",
            "lineup": LINEUP, "setting_change": {**SETTING_CHANGE, "bench_share_override": OVERRIDE},
            "expected": {"bench_share_applied": over["bench_share_applied"], "ddf_weights": over["ddf_weights"],
                         "bench_share_readout": readout(over),
                         "source_weights": {k: d["weights"] for k, d in over["sources"].items()},
                         "rows_ddf_blended": {i: r["ddf"]["blended"]["value"] for i, r in over["rows"].items()}}}),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the fixture's variants differ")
    args = ap.parse_args(argv)
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    blocks = build(fx)
    if args.check:
        same = all(fx.get(k) == v for k, v in blocks.items())
        print("worked example expected-starts variants:", "up to date" if same else "DIFFER")
        return 0 if same else 1
    fx.update(blocks)
    FIXTURE.write_text(json.dumps(fx, indent=1), encoding="utf-8")
    print(f"wrote {', '.join(blocks)} to {FIXTURE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
