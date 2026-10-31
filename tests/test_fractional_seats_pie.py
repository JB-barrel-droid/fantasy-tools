"""JEG-1335: the seat mix keeps every source's pie balanced.

With the mix, a result is the weight-average of one run per whole allocation.
The page's fixed-pie check (curve-widget.js fixedPieDiagnostics, in the
failed-diagnostics gate) sums each source's per-player values against the
blended budgets, so each source's per-player records have to be blended the
same way as the rows: a player off a source's work list in one allocation
counts 0 there, each slice is restated at the blended rate (rate x slice is
the player's value), and a budget moved to the other role, or unpaid, in some
allocations is the weight-average with 0 where it was not.

On the worked example's fractional-seat variant (5 allocations, a player on
one chart's work list in only some of them, a TE bench budget moved in some),
at the default sigma and at sigma 0:

- engine (value-model.js): each source sums to the pie less what is unpaid,
  its display VORP sums to the pie, each role group sums to its funded budget,
  rate x slice is the player's value, value above waivers x the source's
  factor is the display VORP (the math inspector's rebuild), the source's record equals the row's
  value, and no row is both estimated and below rosterable depth for one
  source;
- all three: each chart's Indexed value is native x its factor for every
  player it prices, so Indexed keeps the chart's own order (VP-6.4, the
  page's indexedOrderDiagnostics and tests/test_rank_guard.py). Averaging
  the rows gave a player priced in only some allocations a part value there,
  below players the chart ranks lower (CI rank guard on ef6d859);
- Python reference and spec reference: each source sums to the pie and
  rate x slice is the player's value.

Before the fix the engine held the per-player records whole from the
heaviest allocation and the check failed on every source (group gaps of 3 to
5 on USO).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "tools"))

from spec_reference import worked_example as we  # noqa: E402
import worked_example_fractional_seats as gen  # noqa: E402

HARNESS = REPO / "tests" / "fractional_seats_pie_harness.cjs"
VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
TOL = 1e-6


def _engine(sigma):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node not installed")
    proc = subprocess.run([node, str(HARNESS), str(VALUE_MODEL), str(gen.FIXTURE), json.dumps(sigma)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-2000:])
    return json.loads(proc.stdout)


def _python_gaps(res: dict, bench_key: str, starter_key: str) -> list:
    """[(source, |sum - pie|, worst of |rate x slice - value| and
    |vorp x factor - display VORP|)] for a Python result."""
    out = []
    pie = res.get("pie")
    for key, src in res["sources"].items():
        players = src.get("players") or {}
        if not players or not any(v for v in (src.get("rates") or {}).values()):
            continue
        rates = src["rates"]
        total = sum(p["adjusted"] for p in players.values())
        gap = max(abs(rates[f"{p['pos']}|bench"] * p[bench_key] + rates[f"{p['pos']}|starter"] * p[starter_key]
                      - p["adjusted"]) for p in players.values())
        f = src.get("vorp_display_factor")
        if f is not None:
            gap = max(gap, max(abs(p["vorp"] * f - p["vorp_display"]) for p in players.values()))
        unpaid = src.get("unfunded_groups") or []
        out.append((key, abs(total - pie) if not unpaid else 0.0, gap))
    return out


def _python_indexed(res: dict) -> list:
    """[(chart, inversions, worst |indexed - native x factor|)] over the players
    each chart prices, for a Python result."""
    out = []
    for key, ix in (res.get("indexed") or {}).items():
        f = ix.get("factor")
        players = (res["sources"].get(key) or {}).get("players") or {}
        if f is None or not players:
            continue
        val = {i: res["rows"][i]["indexed"][key] for i in players}
        gap = max(abs(val[i] - p["native"] * f) for i, p in players.items())
        ks = sorted(players, key=lambda i: -players[i]["native"])
        inv = sum(1 for a in range(len(ks)) for b in range(a + 1, len(ks))
                  if players[ks[a]]["native"] != players[ks[b]]["native"] and not val[ks[a]] > val[ks[b]])
        out.append((key, inv, gap))
    return out


class FractionalSeatPie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = json.loads(gen.FIXTURE.read_text(encoding="utf-8"))
        cls.change = cls.fx[gen.KEY]["setting_change"]

    def _check_engine(self, sigma):
        got = _engine(sigma)
        if sigma != 0:
            self.assertGreater(got["mix"], 1)
        self.assertTrue(got["checks"])
        for c in got["checks"]:
            with self.subTest(sigma=sigma, source=c["source"]):
                self.assertAlmostEqual(c["total"], c["target"], delta=TOL)
                self.assertAlmostEqual(c["vorpTotal"], c["pie"], delta=TOL)
                self.assertLessEqual(c["groupGap"], TOL)
                self.assertLessEqual(c["sliceGap"], TOL)
                self.assertLessEqual(c["rowGap"], TOL)
                self.assertLessEqual(c["vorpGap"], TOL)
        for ix in got["indexed"]:
            self.assertLessEqual(ix["gap"], TOL, ix)
        self.assertTrue(got["order"])
        for o in got["order"]:
            with self.subTest(sigma=sigma, indexed=o["source"]):
                self.assertEqual(o["inversions"], 0)
                self.assertLessEqual(o["gap"], TOL)
        self.assertEqual(got["bothLabels"], 0)

    def test_engine_default_sigma(self):
        self._check_engine(None)

    def test_engine_hard_rule(self):
        self._check_engine(0)

    def test_python_reference(self):
        for sigma in (None, 0):
            saved = gen.SETTING_CHANGE
            gen.SETTING_CHANGE = {"seat_sigma": sigma}
            try:
                res = gen.run(self.fx)
            finally:
                gen.SETTING_CHANGE = saved
            if sigma is None:
                self.assertGreater(len(res["allocation_mix"]), 1)
            gaps = _python_gaps(res, "bench_slice", "starter_slice")
            self.assertTrue(gaps)
            for key, sum_gap, slice_gap in gaps:
                with self.subTest(sigma=sigma, source=key):
                    self.assertLessEqual(sum_gap, TOL)
                    self.assertLessEqual(slice_gap, TOL)
            order = _python_indexed(res)
            self.assertTrue(order)
            for key, inv, gap in order:
                with self.subTest(sigma=sigma, indexed=key):
                    self.assertEqual(inv, 0)
                    self.assertLessEqual(gap, TOL)

    def test_spec_reference(self):
        for change in (self.change, {**self.change, "seat_sigma": 0}):
            res = we.run_fixture(self.fx, setting_change=change)
            gaps = _python_gaps(res, "bench_slice", "starter_slice")
            self.assertTrue(gaps)
            for key, sum_gap, slice_gap in gaps:
                with self.subTest(change=change, source=key):
                    self.assertLessEqual(sum_gap, TOL)
                    self.assertLessEqual(slice_gap, TOL)
            order = _python_indexed(res)
            self.assertTrue(order)
            for key, inv, gap in order:
                with self.subTest(change=change, indexed=key):
                    self.assertEqual(inv, 0)
                    self.assertLessEqual(gap, TOL)


if __name__ == "__main__":
    unittest.main()
