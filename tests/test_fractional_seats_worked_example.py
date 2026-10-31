"""JEG-1335: the worked example under fractional seats, in all three
implementations.

tests/fixtures/value_pipeline_worked_example.json keeps the hard VP-2.2 rule
(setting.seat_sigma = 0) for its hand-checked numbers. Its
variant_fractional_seats block (tools/worked_example_fractional_seats.py)
pins the same league at the default seat sigma. These tests hold that:

- the block is up to date with pipelines/value_reference.py;
- the spec reference (pipelines/spec_reference) reproduces the mix, the
  expected counts, every row's blended DDF Value and tier and the default
  ranking to 1e-6;
- the engine (value-model.js, through tests/value_pipeline_driver.js) does
  the same;
- the variant is not the hard rule: the mix has more than one allocation and
  some row's value differs from the sigma-0 run.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "tools"))

from spec_reference import worked_example as we  # noqa: E402
import worked_example_fractional_seats as gen  # noqa: E402

FIXTURE = gen.FIXTURE
DRIVER = REPO / "tests" / "value_pipeline_driver.js"
VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
TOL = 1e-6


def _fx():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _shape(res: dict, rows_value, rows_tier) -> dict:
    """An implementation's result in the variant's vocabulary."""
    return {
        "allocation_mix": [{"weight": e["weight"],
                            "allocation": {p: {c: e["allocation"][p][c] for c in ("flex", "bench")}
                                           for p in ("QB", "RB", "WR", "TE")}}
                           for e in res["allocation_mix"]],
        "allocation_expected": {p: {c: res["allocation_expected"][p][c] for c in gen.COUNTS}
                                for p in ("QB", "RB", "WR", "TE")},
        "rows_ddf_blended": {str(k): rows_value(r) for k, r in res["rows"].items()},
        "rows_ddf_tier": {str(k): rows_tier(r) for k, r in res["rows"].items()},
        "default_ranking": [int(k) for k in res["default_ranking"]],
    }


def _diff(want, got, path="", out=None):
    out = [] if out is None else out
    if isinstance(want, dict):
        if not isinstance(got, dict) or set(want) != set(got):
            out.append(f"{path}: keys {sorted(want) if isinstance(want, dict) else want} vs "
                       f"{sorted(got) if isinstance(got, dict) else got}")
            return out
        for k in want:
            _diff(want[k], got[k], f"{path}.{k}", out)
    elif isinstance(want, list):
        if not isinstance(got, list) or len(want) != len(got):
            out.append(f"{path}: length {len(want)} vs {len(got) if isinstance(got, list) else got}")
            return out
        for i, (a, b) in enumerate(zip(want, got)):
            _diff(a, b, f"{path}[{i}]", out)
    elif isinstance(want, float) and not isinstance(want, bool):
        if not isinstance(got, (int, float)) or abs(want - got) > TOL:
            out.append(f"{path}: {want} vs {got}")
    elif want != got:
        out.append(f"{path}: {want!r} vs {got!r}")
    return out


def run_spec(fx: dict, change: dict) -> dict:
    res = we.run_fixture(fx, setting_change=change)
    return _shape(res, lambda r: r["ddf_blended"]["value"], lambda r: r["ddf_tier"])


def run_engine(fx: dict, change: dict) -> dict:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node not installed")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(fx, f)
        path = f.name
    try:
        proc = subprocess.run([node, str(DRIVER), str(VALUE_MODEL), path, "--setting", json.dumps(change)],
                              capture_output=True, text=True, timeout=120)
    finally:
        Path(path).unlink()
    if proc.returncode != 0:
        raise AssertionError(f"driver failed: {proc.stderr[-2000:]}")
    res = json.loads(proc.stdout)
    return _shape(res, lambda r: r["ddf_blended"]["value"], lambda r: r["ddf_tier"])


class FractionalSeatsWorkedExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = _fx()
        cls.var = cls.fx[gen.KEY]
        cls.change = cls.var["setting_change"]

    def test_generator_is_up_to_date(self):
        self.assertEqual(self.var, json.loads(json.dumps(gen.block(self.fx))))

    def test_spec_reference_reproduces(self):
        d = _diff(self.var["expected"], run_spec(self.fx, self.change))
        self.assertEqual(d, [], d[:10])

    def test_engine_reproduces(self):
        d = _diff(self.var["expected"], run_engine(self.fx, self.change))
        self.assertEqual(d, [], d[:10])

    def test_variant_is_not_the_hard_rule(self):
        exp = self.var["expected"]
        self.assertGreater(len(exp["allocation_mix"]), 1)
        hard = {str(k): r["ddf_blended"]["value"]
                for k, r in we.run_fixture(self.fx, setting_change={"seat_sigma": 0})["rows"].items()}
        moved = [k for k, v in exp["rows_ddf_blended"].items()
                 if v is not None and abs(v - (hard[k] or 0.0)) > 1e-3]
        self.assertTrue(moved, "the fractional-seat variant equals the hard rule")

    def test_walk_catches_a_perturbed_value(self):
        got = run_spec(self.fx, self.change)
        k = next(k for k, v in got["rows_ddf_blended"].items() if v is not None)
        got["rows_ddf_blended"][k] += 1e-5
        self.assertEqual(len(_diff(self.var["expected"], got)), 1)


if __name__ == "__main__":
    unittest.main()
