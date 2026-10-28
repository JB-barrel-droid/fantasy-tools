"""JEG-1044: the reader's value basis (and player overrides) in the engine.

Spec: fantasy-tools-selfhost-notes/jeg-overrides-tab/spec.md (sections 2, 3, 6,
7). The basis decides which sources' Adjusted values the blended DDF Value
averages, and with what weights; the Indexed basis, tiers and ranking follow
it. VP-1 to VP-5 (allocation, weights, pie, Adjusted values), the charts-only
version and the projections reference never see it.

Three-way parity: the JS engine (value-model.js, run under node), the Python
reference (pipelines/value_reference.py) and the clean-room spec reference
(pipelines/spec_reference/value_pipeline.py) each run every frozen fixture
tests/fixtures/basis_*.json; all three must reproduce the pinned values (the
JS to 1e-10, the two references to 1e-6, VP-12). The default fixture (and the
with_override one) was regenerated once for JEG-1073 (Jeremy, 2026-10-25: "Keep
adj trade chart avg as the main ddf and projections as an alt."): the default
DDF Value is the equal-weight mean of the trade charts' Adjusted values. That
is the rule change, not a test bent to go green; the explicit projections basis
(basis_projections_only) is what the default was before and still matches.

Discrimination: the Broken* classes re-run with one thing broken at a time
(a wrong source read as the basis, an override written into Adjusted, the
Indexed basis left on the default, a mutated default output) and require the
checks to go red.

Skips when node is missing, unless RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import copy
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipelines"))

from tests import _render_env  # noqa: E402
import value_reference as ref  # noqa: E402
from spec_reference import value_pipeline as vp  # noqa: E402
from spec_reference import worked_example as we  # noqa: E402

VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = REPO / "tests" / "value_pipeline_driver.js"
FIXDIR = REPO / "tests" / "fixtures"
SOURCE = FIXDIR / "value_pipeline_worked_example.json"
CASES = ["default", "fantasycalc_only", "projections_only", "blend_50_50", "with_override",
         "override_missing_source"]
TOL_JS = 1e-10
TOL_REF = 1e-6


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def fixture(case: str) -> dict:
    return json.loads((FIXDIR / f"basis_{case}.json").read_text(encoding="utf-8"))


def source_doc() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


# --------------------------------------------------------------- the three runs

def run_js(basis, overrides, model: Path = VALUE_MODEL) -> dict:
    cmd = [_node(), str(DRIVER), str(model), str(SOURCE), "--no-promotion-model", "--no-flex-bench-seats"]
    if basis:
        cmd += ["--basis", json.dumps(basis)]
    if overrides:
        cmd += ["--overrides", json.dumps(overrides)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"driver failed: {proc.stderr[-2000:]}")
    return normalize_js(json.loads(proc.stdout))


def normalize_js(out: dict) -> dict:
    rows = {}
    for k, r in out["rows"].items():
        rows[k] = {"adjusted": r["adjusted"],
                   "ddf_blended": r["ddf_blended"], "ddf_projections": r["ddf_projections"],
                   "ddf_charts": r["ddf_charts"], "ddf_tier": r["ddf_tier"]}
    return {"pie": out["pie"], "rows": rows, "indexed_factor": {s: v["factor"] for s, v in out["indexed"].items()},
            "indexed_ddf_total": {s: v["ddf_total"] for s, v in out["indexed"].items()},
            "basis": out.get("basis")}


def run_spec(basis, overrides) -> dict:
    fx = source_doc()
    inp = we.fixture_inputs(fx)
    setting = vp.Setting.from_fixture(copy.deepcopy(fx["setting"]))
    res = vp.run_week(setting, inp["pos_of"], inp["sources"], inp["included"], names=inp["names"],
                      promotion_model=False, flex_bench_seats=False, basis=basis)
    if overrides:
        vp.apply_value_overrides(res["rows"], {int(k): v for k, v in overrides.items()})
    rows = {}
    for k, r in res["rows"].items():
        rows[str(k)] = {"adjusted": r["adjusted"], "ddf_blended": r["ddf_blended"],
                        "ddf_projections": r["ddf_projections"], "ddf_charts": r["ddf_charts"],
                        "ddf_tier": r["ddf_tier"]}
    return {"pie": res["pie"], "rows": rows,
            "indexed_factor": {s: v["factor"] for s, v in res["indexed"].items()},
            "indexed_ddf_total": {s: v["ddf_total"] for s, v in res["indexed"].items()},
            "basis": res["basis"]}


def run_ref(basis, overrides) -> dict:
    fx = source_doc()
    s = fx["setting"]
    league = ref.League(teams=s["teams"], slots=dict(s["slots"]), flex=s["flex"], superflex=s["superflex"],
                        bench=s["bench_per_team"], bench_share=s["bench_share"],
                        flex_eligible=tuple(s["flex_eligible"]))
    sources = {k: ref.SourceInput(k, v["family"], {int(i): float(x) for i, x in v["values"].items()},
                                  fill_peer=v.get("fill_peer", False))
               for k, v in fx["inputs"].items()}
    pos_of = {int(i): p["pos"] for i, p in fx["players"].items()}
    included = [k for k, v in fx["inputs"].items() if v["status"] == "included"]
    res = ref.run_pipeline(league, sources, pos_of, included, promotion_model=False,
                           flex_bench_seats=False, basis=basis)
    if overrides:
        ref.apply_value_overrides(res["rows"], {int(k): v for k, v in overrides.items()})
    rows = {}
    for k, r in res["rows"].items():
        rows[str(k)] = {"adjusted": r["adjusted"], "ddf_blended": r["ddf"]["blended"],
                        "ddf_projections": r["ddf"]["projections"], "ddf_charts": r["ddf"]["charts"],
                        "ddf_tier": r["ddf_tier"]}
    return {"pie": res["pie"], "rows": rows,
            "indexed_factor": {s_: v["factor"] for s_, v in res["indexed"].items()},
            "indexed_ddf_total": {s_: v["ddf_total"] for s_, v in res["indexed"].items()},
            "basis": None}


def close(a, b, tol) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


def compare(expected: dict, actual: dict, tol: float) -> list[str]:
    """Every pinned leaf of a fixture's `expected` against one run."""
    bad: list[str] = []

    def num(path, a, b):
        if not close(a, b, tol):
            bad.append(f"{path}: expected {a!r}, got {b!r}")

    num("pie", expected["pie"], actual["pie"])
    for s, f in expected["indexed_factor"].items():
        num(f"indexed_factor.{s}", f, actual["indexed_factor"].get(s))
    for k, row in expected["rows"].items():
        got = actual["rows"].get(k)
        if got is None:
            bad.append(f"rows.{k}: missing")
            continue
        for s, v in row["adjusted"].items():
            num(f"rows.{k}.adjusted.{s}", v, got["adjusted"].get(s))
        for ver in ("ddf_blended", "ddf_projections", "ddf_charts"):
            num(f"rows.{k}.{ver}.value", row[ver]["value"], got[ver]["value"])
            if row[ver]["count"] != got[ver]["count"]:
                bad.append(f"rows.{k}.{ver}.count: expected {row[ver]['count']}, got {got[ver]['count']}")
        if row["ddf_blended"]["sources"] != list(got["ddf_blended"]["sources"]):
            bad.append(f"rows.{k}.ddf_blended.sources: expected {row['ddf_blended']['sources']}, "
                       f"got {got['ddf_blended']['sources']}")
        if bool(row["ddf_blended"]["low_confidence"]) != bool(got["ddf_blended"]["low_confidence"]):
            bad.append(f"rows.{k}.ddf_blended.low_confidence differs")
        if row["ddf_tier"] != got["ddf_tier"]:
            bad.append(f"rows.{k}.ddf_tier: expected {row['ddf_tier']}, got {got['ddf_tier']}")
    return bad


# ------------------------------------------------------------------- parity

class ThreeWayParity(unittest.TestCase):
    """Spec 7.1 test 12: JS, Python reference and spec reference agree on
    every frozen fixture."""

    def _case(self, case):
        fx = fixture(case)
        basis, overrides = fx["basis"], fx["overrides"]
        exp = fx["expected"]
        self.assertEqual(compare(exp, run_js(basis, overrides), TOL_JS), [], f"{case}: JS")
        self.assertEqual(compare(exp, run_spec(basis, overrides), TOL_REF), [], f"{case}: spec reference")
        self.assertEqual(compare(exp, run_ref(basis, overrides), TOL_REF), [], f"{case}: python reference")

    def test_default(self):
        self._case("default")

    def test_fantasycalc_only(self):
        self._case("fantasycalc_only")

    def test_projections_only(self):
        self._case("projections_only")

    def test_blend_50_50(self):
        self._case("blend_50_50")

    def test_with_override(self):
        self._case("with_override")

    def test_override_missing_source(self):
        self._case("override_missing_source")

    def test_fixtures_are_frozen_set(self):
        found = sorted(p.name for p in FIXDIR.glob("basis_*.json"))
        self.assertEqual(found, sorted(f"basis_{c}.json" for c in CASES))
        for case in CASES:
            fx = fixture(case)
            self.assertEqual(fx["schema"], "basis-fixture/1")
            self.assertIn(fx["split"], ("training", "held-out"))


class DefaultIdentity(unittest.TestCase):
    """Spec 7.1 test 1: no basis, a null basis and {mode: default} are the same
    as the pinned default (JEG-1073: the Adjusted trade chart average), and an
    unusable basis changes nothing."""

    @classmethod
    def setUpClass(cls):
        cls.pinned = fixture("default")["expected"]

    def test_absent_null_and_default_mode_match_the_pinned_default(self):
        for basis in (None, {"mode": "default"}, {"mode": "default", "sources": ["c1"], "weights": {"c1": 5}}):
            self.assertEqual(compare(self.pinned, run_js(basis, {}), TOL_JS), [], basis)

    def test_default_fixture_is_the_chart_mean(self):
        """JEG-1073: the default is the mean of the Adjusted trade charts in I
        (c3 is held), never the projections."""
        exp = fixture("default")["expected"]
        for k, r in exp["rows"].items():
            vals = [r["adjusted"][s] for s in ("c1", "c2", "c4", "c5") if r["adjusted"][s] is not None]
            self.assertAlmostEqual(r["ddf_blended"]["value"], sum(vals) / len(vals), places=9, msg=k)
            self.assertEqual(r["ddf_blended"]["sources"], [s for s in ("c1", "c2", "c4", "c5")
                                                           if r["adjusted"][s] is not None])

    def test_default_is_not_the_projection_mean_and_projections_stay_the_alternate(self):
        """Fails on the pre-JEG-1073 rule: the blended default differs from the
        projection mean, which lives on in ddf_projections."""
        exp = fixture("default")["expected"]
        moved = 0
        for k, r in exp["rows"].items():
            vals = [r["adjusted"][s] for s in ("p1", "p2") if r["adjusted"][s] is not None]
            if not vals:
                continue
            self.assertAlmostEqual(r["ddf_projections"]["value"], sum(vals) / len(vals), places=9, msg=k)
            if abs(r["ddf_blended"]["value"] - r["ddf_projections"]["value"]) > 1e-6:
                moved += 1
        self.assertGreater(moved, 10)

    def test_unusable_basis_falls_back_to_default_and_says_so(self):
        out = run_js({"mode": "single", "source": "c3"}, {})   # c3 is not in I (held)
        self.assertEqual(compare(self.pinned, out, TOL_JS), [])
        self.assertTrue(out["basis"]["fellBackToDefault"])
        self.assertFalse(out["basis"]["applied"])
        self.assertIsNone(run_js(None, {})["basis"])


# ---------------------------------------------------------------- the math

class BasisMath(unittest.TestCase):
    """Spec 7.1 tests 2-4, 9, 11: the basis formulas, written out by hand
    against the pinned default Adjusted values (which no basis changes)."""

    @classmethod
    def setUpClass(cls):
        cls.default = fixture("default")["expected"]
        cls.adj = {k: r["adjusted"] for k, r in cls.default["rows"].items()}

    def test_single_chart_basis_is_that_charts_adjusted_value(self):
        out = run_js({"mode": "single", "source": "c1"}, {})
        for k, r in out["rows"].items():
            self.assertAlmostEqual(r["ddf_blended"]["value"], self.adj[k]["c1"], places=10, msg=k)
            self.assertEqual(r["ddf_blended"]["sources"], ["c1"])
            self.assertFalse(r["ddf_blended"]["low_confidence"], "a one-source basis is not 'only one source'")

    def test_single_projection_basis_is_an_explicit_basis_that_differs_from_the_default(self):
        out = run_js({"mode": "single", "source": "p1"}, {})
        moved = 0
        for k, r in out["rows"].items():
            self.assertAlmostEqual(r["ddf_blended"]["value"], self.adj[k]["p1"], places=10, msg=k)
            if self.adj[k]["p2"] is not None and abs(self.adj[k]["p1"] - self.adj[k]["p2"]) > 1e-6:
                moved += 1
        self.assertGreater(moved, 10)

    def test_weighted_blend_is_the_normalised_weighted_mean(self):
        for weights in ({"p1": 60, "p2": 40}, {"p1": 3, "p2": 2}):
            out = run_js({"mode": "blend", "sources": ["p1", "p2"], "weights": weights}, {})
            for k, r in out["rows"].items():
                a1, a2 = self.adj[k]["p1"], self.adj[k]["p2"]
                if a2 is None:
                    expect = a1
                else:
                    expect = (weights["p1"] * a1 + weights["p2"] * a2) / (weights["p1"] + weights["p2"])
                self.assertAlmostEqual(r["ddf_blended"]["value"], expect, places=10, msg=f"{weights} {k}")

    def test_sixty_forty_equals_three_two(self):
        a = run_js({"mode": "blend", "sources": ["p1", "p2"], "weights": {"p1": 60, "p2": 40}}, {})
        b = run_js({"mode": "blend", "sources": ["p1", "p2"], "weights": {"p1": 3, "p2": 2}}, {})
        self.assertEqual(compare(normalize_expected(a), b, 1e-12), [])

    def test_player_missing_from_a_source_renormalises_over_the_rest(self):
        out = run_js({"mode": "blend", "sources": ["p1", "p2"], "weights": {"p1": 60, "p2": 40}}, {})
        row = out["rows"]["207"]            # 207 is not in p2
        self.assertIsNone(self.adj["207"]["p2"])
        self.assertAlmostEqual(row["ddf_blended"]["value"], self.adj["207"]["p1"], places=10)
        self.assertEqual(row["ddf_blended"]["sources"], ["p1"])
        self.assertTrue(row["ddf_blended"]["low_confidence"], "one of two chosen sources prices him")

    def test_zero_weight_and_unnamed_sources_are_excluded(self):
        out = run_js({"mode": "blend", "sources": ["p1", "p2", "c1"], "weights": {"p1": 1, "p2": 0, "c1": 0}}, {})
        for k, r in out["rows"].items():
            self.assertAlmostEqual(r["ddf_blended"]["value"], self.adj[k]["p1"], places=10, msg=k)

    def test_charts_only_and_projections_versions_never_move(self):
        for basis in ({"mode": "single", "source": "c1"}, {"mode": "single", "source": "p1"},
                      {"mode": "blend", "sources": ["p1", "c1"], "weights": {"p1": 50, "c1": 50}}):
            out = run_js(basis, {})
            for k, r in out["rows"].items():
                d = self.default["rows"][k]
                self.assertAlmostEqual(r["ddf_charts"]["value"] or 0.0, d["ddf_charts"]["value"] or 0.0, places=10)
                self.assertAlmostEqual(r["ddf_projections"]["value"] or 0.0,
                                       d["ddf_projections"]["value"] or 0.0, places=10)

    def test_a_basis_never_changes_the_pipeline_below_ddf(self):
        """VP-1 to VP-5 are source-level: Adjusted values and the pie are the
        same for every basis, and every source still sums to the pie."""
        for basis in ({"mode": "single", "source": "c1"}, {"mode": "blend", "sources": ["p1", "c1"],
                                                            "weights": {"p1": 50, "c1": 50}}):
            out = run_js(basis, {})
            self.assertEqual(out["pie"], self.default["pie"])
            for k, r in out["rows"].items():
                for s, v in r["adjusted"].items():
                    self.assertTrue(close(v, self.adj[k][s], TOL_JS), (k, s))
            for s in ("p1", "p2", "c1", "c2", "c4", "c5"):
                total = sum(r["adjusted"][s] or 0.0 for r in out["rows"].values()
                            if r["adjusted"][s] not in (None,))
                self.assertAlmostEqual(total, out["pie"], places=6, msg=s)


def normalize_expected(run: dict) -> dict:
    """A run in the shape compare() reads as `expected`."""
    rows = {}
    for k, r in run["rows"].items():
        rows[k] = {"adjusted": r["adjusted"],
                   "ddf_blended": {"value": r["ddf_blended"]["value"], "count": r["ddf_blended"]["count"],
                                   "sources": list(r["ddf_blended"]["sources"]),
                                   "low_confidence": r["ddf_blended"]["low_confidence"]},
                   "ddf_projections": {"value": r["ddf_projections"]["value"], "count": r["ddf_projections"]["count"]},
                   "ddf_charts": {"value": r["ddf_charts"]["value"], "count": r["ddf_charts"]["count"]},
                   "ddf_tier": r["ddf_tier"]}
    return {"pie": run["pie"], "rows": rows, "indexed_factor": run["indexed_factor"]}


class IndexedFollowsBasis(unittest.TestCase):
    """Spec 2.3 / 7.1 test 9 (Jeremy Q2 = B): the Indexed basis is the user's
    basis. A chart used as the whole basis is rescaled onto itself."""

    @classmethod
    def setUpClass(cls):
        cls.default = fixture("default")["expected"]
        cls.adj = {k: r["adjusted"] for k, r in cls.default["rows"].items()}
        cls.nat = {s: {k: float(x) for k, x in v["values"].items()} for s, v in source_doc()["inputs"].items()}

    def _factor(self, basis_values, source):
        ddf = native = 0.0
        for k, nat in self.nat[source].items():
            if basis_values.get(k) is None:
                continue
            ddf += basis_values[k]
            native += nat
        return ddf / native

    def test_a_chart_basis_gives_that_chart_a_factor_that_maps_it_to_its_adjusted_values(self):
        out = run_js({"mode": "single", "source": "c1"}, {})
        # Its Indexed total over the players it lists equals its Adjusted total.
        listed = [k for k, v in self.nat["c1"].items()]
        indexed_total = sum(self.nat["c1"][k] * out["indexed_factor"]["c1"] for k in listed)
        adjusted_total = sum(self.adj[k]["c1"] for k in listed)
        self.assertAlmostEqual(indexed_total, adjusted_total, places=9)
        # A short chart (c5 lists 13 players) is now rescaled onto c1's scale,
        # not the DDF scale. (The long charts c1, c2, c4 list nearly everyone, so
        # every basis totals about the pie over them and their factors barely
        # move in this small fixture; in live data every chart's list is partial.)
        self.assertNotAlmostEqual(out["indexed_factor"]["c5"], self.default["indexed_factor"]["c5"], places=4)
        # The factor is exactly: sum(basis over its shared players) / sum(native).
        basis = {k: r["ddf_blended"]["value"] for k, r in out["rows"].items()}
        self.assertAlmostEqual(out["indexed_factor"]["c1"], self._factor(basis, "c1"), places=12)

    def test_blend_factors_differ_from_default_and_from_single(self):
        blend = run_js({"mode": "blend", "sources": ["p1", "c1"], "weights": {"p1": 50, "c1": 50}}, {})
        single = run_js({"mode": "single", "source": "c1"}, {})
        self.assertNotAlmostEqual(blend["indexed_factor"]["c5"], self.default["indexed_factor"]["c5"], places=5)
        self.assertNotAlmostEqual(blend["indexed_factor"]["c5"], single["indexed_factor"]["c5"], places=5)

    def test_fixed_pie_identity_holds_against_the_users_basis(self):
        """The Indexed total over a chart's shared players equals the BASIS
        total over them (the fixedPieIndexed identity), for every basis."""
        for basis in (None, {"mode": "single", "source": "c1"}, {"mode": "single", "source": "p1"},
                      {"mode": "blend", "sources": ["p1", "c1"], "weights": {"p1": 50, "c1": 50}}):
            out = run_js(basis, {})
            basis_vals = {k: r["ddf_blended"]["value"] for k, r in out["rows"].items()}
            for s in ("c1", "c2", "c4", "c5"):
                shared = [k for k in self.nat[s] if basis_vals.get(k) is not None]
                indexed_total = sum(self.nat[s][k] * out["indexed_factor"][s] for k in shared)
                self.assertAlmostEqual(indexed_total, sum(basis_vals[k] for k in shared), places=8, msg=(basis, s))

    def test_default_factors_equal_the_pinned_default(self):
        self.assertEqual(compare(self.default, run_js(None, {}), TOL_JS), [])


# ---------------------------------------------------------------- overrides

class Overrides(unittest.TestCase):
    """Spec 7.1 tests 5, 7, 8, 11: an override is a row-level overlay."""

    @classmethod
    def setUpClass(cls):
        cls.default = fixture("default")["expected"]

    def test_override_replaces_ddf_but_nothing_below_it(self):
        out = run_js(None, {"201": 99.0})
        r, d = out["rows"]["201"], self.default["rows"]["201"]
        self.assertEqual(r["ddf_blended"]["value"], 99.0)
        # JEG-1073: the override replaces ddf_value (blended) only; the
        # projections alternate keeps its own value.
        self.assertTrue(close(d["ddf_projections"]["value"], r["ddf_projections"]["value"], TOL_JS))
        self.assertNotEqual(r["ddf_projections"]["value"], 99.0)
        self.assertTrue(r["ddf_blended"]["overridden"])
        self.assertAlmostEqual(r["ddf_blended"]["pipeline_value"], d["ddf_blended"]["value"], places=10)
        for s, v in d["adjusted"].items():
            self.assertTrue(close(v, r["adjusted"][s], TOL_JS), s)
        self.assertTrue(close(d["ddf_charts"]["value"], r["ddf_charts"]["value"], TOL_JS))
        self.assertEqual(out["indexed_factor"], self.default["indexed_factor"])
        self.assertEqual(out["pie"], self.default["pie"])
        for s in ("p1", "p2", "c1", "c2", "c4", "c5"):
            total = sum(x["adjusted"][s] or 0.0 for x in out["rows"].values())
            self.assertAlmostEqual(total, out["pie"], places=6, msg=s)

    def test_other_players_are_untouched(self):
        out = run_js(None, {"201": 99.0})
        for k, r in out["rows"].items():
            if k == "201":
                continue
            self.assertFalse(r["ddf_blended"]["overridden"])
            self.assertTrue(close(r["ddf_blended"]["value"], self.default["rows"][k]["ddf_blended"]["value"], TOL_JS))

    def test_override_on_a_player_missing_from_a_source_is_the_override_value(self):
        out = run_js({"mode": "blend", "sources": ["p1", "p2"], "weights": {"p1": 60, "p2": 40}}, {"207": 12.5})
        r = out["rows"]["207"]
        self.assertEqual(r["ddf_blended"]["value"], 12.5)
        self.assertAlmostEqual(r["ddf_blended"]["pipeline_value"], self.default["rows"]["207"]["adjusted"]["p1"],
                               places=10)

    def test_override_on_a_player_nobody_prices_is_the_override_value_not_null(self):
        out = run_js({"mode": "single", "source": "p2"}, {"207": 7.0})   # p2 does not project 207
        self.assertIsNone(out["rows"]["207"]["ddf_blended"]["pipeline_value"])
        self.assertEqual(out["rows"]["207"]["ddf_blended"]["value"], 7.0)

    def test_override_survives_a_basis_switch(self):
        """Global overrides (Q3 = A): the same overlay applies on any basis."""
        for basis in (None, {"mode": "single", "source": "c1"}):
            self.assertEqual(run_js(basis, {"205": 33.0})["rows"]["205"]["ddf_blended"]["value"], 33.0)


class AdjustmentOverrides(unittest.TestCase):
    """JEG-1058: an override may be an adjustment (+5 / -3) added to the
    pipeline's own value and capped at the 0-100 value scale. All three
    implementations (JS engine, Python reference, clean-room spec reference)
    must read the same adjustment the same way, and an adjustment must leave
    everything below the blended value alone."""

    @classmethod
    def setUpClass(cls):
        cls.default = fixture("default")["expected"]

    def _three(self, basis, overrides):
        return (run_js(basis, overrides), run_spec(basis, overrides), run_ref(basis, overrides))

    def test_adjustment_adds_to_the_pipeline_value_in_all_three(self):
        ov = {"201": {"type": "adjustment", "delta": 5.0}}
        base = self.default["rows"]["201"]["ddf_blended"]["value"]
        for out, tol in zip(self._three(None, ov), (TOL_JS, TOL_REF, TOL_REF)):
            row = out["rows"]["201"]["ddf_blended"]
            self.assertAlmostEqual(row["value"], base + 5.0, places=9, msg=str(out.get("rows", {}).get("201")))
            self.assertTrue(row["overridden"])
            self.assertAlmostEqual(row["pipeline_value"], base, places=9)

    def test_a_negative_adjustment_takes_off(self):
        ov = {"201": {"type": "adjustment", "delta": -5.0}}
        base = self.default["rows"]["201"]["ddf_blended"]["value"]
        for out, tol in zip(self._three(None, ov), (TOL_JS, TOL_REF, TOL_REF)):
            self.assertAlmostEqual(out["rows"]["201"]["ddf_blended"]["value"], base - 5.0, places=9)

    def test_an_adjustment_is_capped_at_the_value_scale(self):
        """The value scale is 0-100: an adjustment that runs past either end is
        capped, not refused."""
        for key, delta, expect in (("201", 60.0, 100.0), ("101", -40.0, 0.0)):
            ov = {key: {"type": "adjustment", "delta": delta}}
            for out, tol in zip(self._three(None, ov), (TOL_JS, TOL_REF, TOL_REF)):
                row = out["rows"][key]["ddf_blended"]
                self.assertAlmostEqual(row["value"], expect, places=9, msg=f"{key} {delta}")
                self.assertTrue(row["overridden"])

    def test_an_override_from_outside_the_editor_is_capped_at_the_scale(self):
        """An absolute value past the top of the scale is capped to 100 in all
        three implementations, so a link, an import or a saved record cannot
        put a value off the scale."""
        for key in ("201", "101"):
            ov = {key: 120.0}
            for out, tol in zip(self._three(None, ov), (TOL_JS, TOL_REF, TOL_REF)):
                row = out["rows"][key]["ddf_blended"]
                self.assertAlmostEqual(row["value"], 100.0, places=9, msg=f"{key} 120")
                self.assertTrue(row["overridden"])

    def test_an_adjustment_from_outside_the_editor_is_capped_to_the_scale(self):
        """An adjustment past the scale is capped to its span. The value it
        produces is the same (the result is capped anyway), so the check is
        that all three agree."""
        ov = {"201": {"type": "adjustment", "delta": 5000.0}}
        for out, tol in zip(self._three(None, ov), (TOL_JS, TOL_REF, TOL_REF)):
            row = out["rows"]["201"]["ddf_blended"]
            self.assertAlmostEqual(row["value"], 100.0, places=9, msg=str(out.get("rows", {}).get("201")))

    def test_an_adjustment_leaves_the_projections_alternate_and_the_sources_alone(self):
        ov = {"201": {"type": "adjustment", "delta": 5.0}}
        for out, tol in zip(self._three(None, ov), (TOL_JS, TOL_REF, TOL_REF)):
            row = out["rows"]["201"]
            self.assertAlmostEqual(row["ddf_projections"]["value"],
                                   self.default["rows"]["201"]["ddf_projections"]["value"], places=9)
            self.assertAlmostEqual(row["ddf_charts"]["value"],
                                   self.default["rows"]["201"]["ddf_charts"]["value"], places=9)
            for s, v in self.default["rows"]["201"]["adjusted"].items():
                self.assertAlmostEqual(row["adjusted"][s], v, places=9, msg=s)

    def test_an_adjustment_on_a_player_nobody_prices_is_the_delta(self):
        """No source prices him, so the pipeline value is nothing: the
        adjustment says what he is worth (0 + delta), not null + delta."""
        basis = {"mode": "single", "source": "p2"}      # p2 does not project 207
        ov = {"207": {"type": "adjustment", "delta": 7.0}}
        for out, tol in zip(self._three(basis, ov), (TOL_JS, TOL_REF, TOL_REF)):
            row = out["rows"]["207"]["ddf_blended"]
            self.assertIsNone(row["pipeline_value"])
            self.assertAlmostEqual(row["value"], 7.0, places=9)

    def test_an_adjustment_survives_a_basis_switch(self):
        """The adjustment follows the basis: it adds to whatever the pipeline
        says under the basis in force."""
        for basis in (None, {"mode": "single", "source": "c1"}):
            base = run_js(basis, {})["rows"]["201"]["ddf_blended"]["value"]
            out = run_js(basis, {"201": {"type": "adjustment", "delta": 2.0}})
            self.assertAlmostEqual(out["rows"]["201"]["ddf_blended"]["value"], base + 2.0, places=9)


# ----------------------------------------------------------- broken builds

def _broken_model(replacements: list[tuple[str, str]]) -> Path:
    text = VALUE_MODEL.read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in text, f"mutation target not found: {old[:60]}"
        text = text.replace(old, new, 1)
    tmp = Path(tempfile.mkdtemp()) / "value-model.js"
    tmp.write_text(text, encoding="utf-8")
    return tmp


class BrokenBuildsAreCaught(unittest.TestCase):
    """Spec 7.2: each guard goes red against the bug it names."""

    def test_perturbed_default_output_fails_the_identity_check(self):
        out = run_js(None, {})
        out["rows"]["201"]["ddf_blended"]["value"] += 1.0
        self.assertNotEqual(compare(fixture("default")["expected"], out, TOL_JS), [])

    def test_wrong_source_as_basis_fails_the_single_source_fixture(self):
        model = _broken_model([('asked = [String(one)];', 'asked = [String(one) === "c1" ? "c2" : String(one)];')])
        out = run_js({"mode": "single", "source": "c1"}, {}, model=model)
        self.assertNotEqual(compare(fixture("fantasycalc_only")["expected"], out, TOL_JS), [])

    def test_unnormalised_weights_fail_the_blend_fixture(self):
        model = _broken_model([('used.push(k); sum += weights[k] * v; wsum += weights[k];',
                                'used.push(k); sum += weights[k] * v; wsum += 1;')])
        out = run_js({"mode": "blend", "sources": ["p1", "c1"], "weights": {"p1": 50, "c1": 50}}, {}, model=model)
        self.assertNotEqual(compare(fixture("blend_50_50")["expected"], out, TOL_JS), [])

    def test_indexed_basis_left_on_the_default_fails(self):
        model = _broken_model([('if (basisPlan) { indexBasis[key] = rows[key].ddfByVersion.blended.value; return; }',
                                '')])
        out = run_js({"mode": "single", "source": "c1"}, {}, model=model)
        self.assertNotEqual(compare(fixture("fantasycalc_only")["expected"], out, TOL_JS), [])

    def test_override_written_into_adjusted_breaks_the_pie_check(self):
        """Misapplied, an override of 99 on one player lands in Adjusted and
        the source no longer sums to the pie; the invariant check sees it."""
        out = run_js(None, {"201": 99.0})
        out["rows"]["201"]["adjusted"]["p1"] = 99.0          # the misapplication
        total = sum(r["adjusted"]["p1"] for r in out["rows"].values())
        self.assertGreater(abs(total - out["pie"]), 1.0)
        self.assertNotEqual(compare(fixture("with_override")["expected"], out, TOL_JS), [])

    def test_override_that_leaks_into_the_projections_version_is_caught(self):
        out = run_js(None, {"201": 99.0})
        out["rows"]["201"]["ddf_projections"]["value"] = 99.0
        self.assertNotEqual(compare(fixture("with_override")["expected"], out, TOL_JS), [])

    def test_override_that_leaks_into_the_charts_version_is_caught(self):
        out = run_js(None, {"201": 99.0})
        out["rows"]["201"]["ddf_charts"]["value"] = 99.0
        self.assertNotEqual(compare(fixture("with_override")["expected"], out, TOL_JS), [])

    def test_python_references_catch_a_basis_that_is_ignored(self):
        exp = fixture("fantasycalc_only")["expected"]
        self.assertNotEqual(compare(exp, run_spec(None, {}), TOL_REF), [])
        self.assertNotEqual(compare(exp, run_ref(None, {}), TOL_REF), [])


if __name__ == "__main__":
    unittest.main()
