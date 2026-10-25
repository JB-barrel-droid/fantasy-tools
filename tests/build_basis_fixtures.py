"""Build tests/fixtures/basis_*.json (JEG-1044), once, from real engine output.

These are FROZEN reference fixtures (iteration contract): do not regenerate to
make a test pass. Re-running this script is only for adding a case, and the
change is logged in docs/claude-log.md.

JEG-1073 (Jeremy, 2026-10-25: "Keep adj trade chart avg as the main ddf and
projections as an alt."): the default DDF Value is now the equal-weight mean of
the trade charts' Adjusted values, so the default-path fixtures (basis_default,
basis_with_override) were regenerated ONCE from the new engine. This is the
rule change, not a test bent to go green. The hand check
(test_default_fixture_is_the_chart_mean) and the two independent Python
references (changed separately) must reproduce the regenerated numbers.

How each is made:
* basis_default.json is the JEG-1073 engine's output with no basis. Before
  JEG-1073 it was the pre-change engine at origin/main 61ecb39e (the
  projection mean, JEG-804); BASELINE_SHA records that history only.
* the others are the JS engine's output with the named basis/overrides; the
  test (tests/test_basis_overrides.py) then requires BOTH Python references to
  reproduce each one independently, and checks the hand formulas of spec 7.1.

Run: python3 tests/build_basis_fixtures.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXDIR = ROOT / "tests" / "fixtures"
SOURCE = FIXDIR / "value_pipeline_worked_example.json"
VALUE_MODEL = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = ROOT / "tests" / "value_pipeline_driver.js"
BASELINE_SHA = "61ecb39e"   # origin/main before JEG-1044

# "c1" stands in for a trade chart (FantasyCalc), "p1" for a projection (ESPN).
CASES = [
    {"case": "default", "split": "training", "basis": None, "overrides": {},
     "note": "Default path (JEG-1073): equal-weight mean of the trade charts' Adjusted values."},
    {"case": "fantasycalc_only", "split": "held-out", "basis": {"mode": "single", "source": "c1"}, "overrides": {},
     "note": "Single trade-chart source (c1 stands in for FantasyCalc)."},
    {"case": "projections_only", "split": "held-out", "basis": {"mode": "single", "source": "p1"}, "overrides": {},
     "note": "Explicit projection basis (p1 stands in for ESPN); it was the default before JEG-1073."},
    {"case": "blend_50_50", "split": "training",
     "basis": {"mode": "blend", "sources": ["p1", "c1"], "weights": {"p1": 50, "c1": 50}}, "overrides": {},
     "note": "Cross-family 50/50 blend."},
    {"case": "with_override", "split": "held-out", "basis": None, "overrides": {"201": 99.0},
     "note": "Default basis + a large override on one player: written into Adjusted it would break the pie."},
    {"case": "override_missing_source", "split": "held-out",
     "basis": {"mode": "blend", "sources": ["p1", "p2"], "weights": {"p1": 60, "p2": 40}}, "overrides": {"207": 12.5},
     "note": "60/40 blend; player 207 is missing from p2 (renormalises to p1) and carries an override."},
]


def run_driver(model: Path, basis, overrides) -> dict:
    cmd = ["node", str(DRIVER), str(model), str(SOURCE), "--no-promotion-model", "--no-flex-bench-seats"]
    if basis:
        cmd += ["--basis", json.dumps(basis)]
    if overrides:
        cmd += ["--overrides", json.dumps(overrides)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr[-2000:])
    return json.loads(proc.stdout)


def compact(out: dict) -> dict:
    rows = {}
    for k, r in out["rows"].items():
        rows[k] = {
            "pos": r["pos"],
            "adjusted": r["adjusted"],
            "ddf_blended": {f: r["ddf_blended"][f] for f in ("value", "count", "sources", "low_confidence")},
            "ddf_projections": {"value": r["ddf_projections"]["value"], "count": r["ddf_projections"]["count"]},
            "ddf_charts": {"value": r["ddf_charts"]["value"], "count": r["ddf_charts"]["count"]},
            "ddf_tier": r["ddf_tier"],
        }
        if "pipeline_value" in r["ddf_blended"]:
            rows[k]["ddf_blended"]["pipeline_value"] = r["ddf_blended"]["pipeline_value"]
            rows[k]["ddf_blended"]["overridden"] = r["ddf_blended"]["overridden"]
    return {"pie": out["pie"], "basis": out.get("basis"), "rows": rows,
            "indexed_factor": {s: v["factor"] for s, v in out["indexed"].items()},
            "indexed_ddf_total": {s: v["ddf_total"] for s, v in out["indexed"].items()}}


def main() -> int:
    baseline = subprocess.run(
        ["git", "show", f"{BASELINE_SHA}:app/trade-value-chart/assets/value-model.js"],
        capture_output=True, text=True, cwd=ROOT, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        base_model = Path(tmp) / "value-model.js"
        base_model.write_text(baseline, encoding="utf-8")
        for case in CASES:
            # JEG-1073: every case, the default included, now comes from the current engine.
            model = VALUE_MODEL
            out = run_driver(model, case["basis"], case["overrides"])
            doc = {"schema": "basis-fixture/1", "case": case["case"], "split": case["split"],
                   "note": case["note"], "source_fixture": SOURCE.name, "basis": case["basis"],
                   "overrides": case["overrides"],
                   "generated_by": "value-model.js (JEG-1073: default = Adjusted trade chart average)"
                   if case["case"] in ("default", "with_override")
                   else "value-model.js with basisConfig (JEG-1044)",
                   "expected": compact(out)}
            path = FIXDIR / f"basis_{case['case']}.json"
            path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            print("wrote", path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
