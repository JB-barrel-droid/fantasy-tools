"""The engine's source-neutral value pipeline reproduces the worked example
(JEG-508, docs/methodology.md "Value Pipeline (source-neutral, 2026-10-09)",
VP-12).

Runs ValueModel.runValuePipeline (app/trade-value-chart/assets/value-model.js,
the code the page runs) headless under node on
tests/fixtures/value_pipeline_worked_example.json and checks EVERY expected
leaf -- inputs to the allocation, fill-in estimates, groups, weights, rates,
Adjusted / VORP vs waivers / Indexed values, the three DDF versions, tiers and
the default ranking -- to 1e-6, plus the bench-share 0.10 variant.

Discrimination: test_guard_catches_* mutate the engine (ESPN-style anchor
weights, bench share left at the old 35%, estimates not capped) and require
the comparison to fail. The pre-JEG-508 engine has no runValuePipeline at all,
so this test fails there outright.

Skips when node is missing, unless RENDER_TESTS_REQUIRED=1 (CI), where a
missing node is an error.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
VALUE_MODEL = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = ROOT / "tests" / "value_pipeline_driver.js"
FIXTURE = ROOT / "tests" / "fixtures" / "value_pipeline_worked_example.json"
TOL = 1e-6


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def run_engine(model: Path = VALUE_MODEL, bench_share: float | None = None) -> dict:
    cmd = [_node(), str(DRIVER), str(model), str(FIXTURE)]
    if bench_share is not None:
        cmd += ["--bench-share", repr(bench_share)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"driver failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def diff(expected, actual, path="", out=None):
    """Every leaf of `expected` must be present in `actual` and equal (numbers
    to TOL). Extra keys in `actual` are allowed."""
    out = [] if out is None else out
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            out.append(f"{path}: expected object, got {actual!r}"[:300])
            return out
        for key, value in expected.items():
            if key not in actual:
                out.append(f"{path}.{key}: missing")
                continue
            diff(value, actual[key], f"{path}.{key}", out)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            out.append(f"{path}: expected {expected!r}, got {actual!r}"[:300])
            return out
        for i, (e, a) in enumerate(zip(expected, actual)):
            diff(e, a, f"{path}[{i}]", out)
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if expected != actual:
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
    elif isinstance(expected, (int, float)):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or abs(expected - actual) > TOL:
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
    else:
        out.append(f"{path}: unhandled {expected!r}")
    return out


SKIP_EXPECTED = {
    # Narrative-only keys (not engine outputs).
    "flex_contrast", "starting_slots_per_team",
}


def expected_main(doc: dict) -> dict:
    return {k: v for k, v in doc["expected"].items() if k not in SKIP_EXPECTED}


def variant_diff(doc: dict, actual: dict) -> list[str]:
    var = doc["variant_bench_share_0_10"]
    out = diff(var["ddf_weights"], actual["ddf_weights"], "variant.ddf_weights")
    for src, weights in var["source_weights"].items():
        diff(weights, actual["sources"][src]["weights"], f"variant.sources.{src}.weights", out)
    for key, value in var["rows_ddf_blended"].items():
        diff(value, actual["rows"][key]["ddf_blended"]["value"], f"variant.rows.{key}", out)
    return out


class WorkedExampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(FIXTURE.read_text())
        cls.actual = run_engine()

    def test_every_expected_value(self):
        problems = diff(expected_main(self.doc), self.actual, "expected")
        self.assertEqual(problems, [], "\n".join(problems[:40]))

    def test_bench_share_variant(self):
        bs = self.doc["variant_bench_share_0_10"]["setting_change"]["bench_share"]
        problems = variant_diff(self.doc, run_engine(bench_share=bs))
        self.assertEqual(problems, [], "\n".join(problems[:40]))

    def test_check_covers_the_fixture(self):
        # The diff must actually walk the rows and the per-source detail; a
        # check that compared nothing would pass on any engine.
        exp = expected_main(self.doc)
        self.assertEqual(len(exp["rows"]), 30)
        self.assertIn("imputation_ratios", exp["sources"]["c5"]["positions"]["RB"])
        self.assertEqual(self.actual["version"], "value-pipeline/2")

    def test_estimated_reasons(self):
        rows = self.actual["rows"]
        self.assertEqual(rows["207"]["estimated_reason"]["c5"],
                         "Estimated: no chart lists him; from c5's values against projected points")
        self.assertEqual(rows["306"]["estimated_reason"]["c5"],
                         "Estimated: c5 doesn't list him; scaled from c1 and c4")
        self.assertEqual(rows["205"]["reasons"]["c2"], "Below rosterable depth; c2 doesn't list him")
        self.assertEqual(rows["207"]["reasons"]["p2"], "p2 doesn't project this player")


def _mutated(replacements: list[tuple[str, str]]) -> Path:
    src = VALUE_MODEL.read_text()
    for old, new in replacements:
        if old not in src:
            raise AssertionError(f"mutation anchor not found: {old!r}")
        src = src.replace(old, new, 1)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    tmp.write(src)
    tmp.close()
    return Path(tmp.name)


class GuardDiscriminationTest(unittest.TestCase):
    """The comparison must fail on a broken engine."""

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(FIXTURE.read_text())

    def assert_fails(self, replacements):
        model = _mutated(replacements)
        try:
            actual = run_engine(model)
        except AssertionError:
            return  # the broken engine crashed: also a failure
        finally:
            model.unlink()
        self.assertNotEqual(diff(expected_main(self.doc), actual, "expected"), [])

    def test_guard_catches_old_bench_share(self):
        self.assert_fails([(
            "var bsInput = vpFinite(setting.bench_share) ? setting.bench_share : VP_DEFAULT_BENCH_SHARE;",
            "var bsInput = 0.35;")])

    def test_guard_catches_uncapped_estimates(self):
        self.assert_fails([("info.value = Math.min(Math.max(raw, 0), cap);", "info.value = Math.max(raw, 0);")])

    def test_guard_catches_flex_by_own_values(self):
        # Superseded OC-4 rule: each source fills flex by its own natives.
        self.assert_fails([("var degenerate = projI.length === 0;", "var degenerate = true;")])

    def test_guard_catches_first_source_weights(self):
        # An anchor-style rule: DDF weights from one source instead of the mean.
        self.assert_fails([("Sraw[pos] = sn ? ss / sn : 0;",
                            "Sraw[pos] = out[included[0]].starterMix[pos];")])


if __name__ == "__main__":
    unittest.main()
