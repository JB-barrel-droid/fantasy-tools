"""JEG-68: CBS ROS starter-markup health check must not false-fire on a
source whose raw pool genuinely sits at the target split.

Root cause (verified 2026-10-02): the `${vorpKey}-starter-markup`
ChartHealth check in curve-widget.js required `markup > 1.05`, i.e. a raw
starter share below 80.95%. CBS ROS's raw value-above-waivers pool genuinely
sits at 84.96% starter share (349 players, default 12-team Full PPR shape):

- the CBS ROS snapshot's per_game_* = ROS totals / gp (raw projections);
- the fixture's cbsros_ppg matches the snapshot;
- the pipeline's independent two-tier raw_value prices the same pool at
  86.25% starter share.

So markup = 0.85 / 0.8496 = 1.0004 on a CORRECT build: the fixed-pie
adjustment is vacuous, not broken. The fix replaces the `> 1.05` threshold
with ValueModel.starterMarkupSane (sane band 0.98-1.6): no material
inversion, no absurd inflation.

Discrimination: test_widget_uses_sane_predicate FAILS on the pre-fix widget
(it asserts the `markup > 1.05` literal is gone and the predicate call is
present). test_old_threshold_false_fired documents that the old rule
rejects the genuine 1.0004 markup. The predicate and harness tests pin the
new behavior against the real fixture.
"""
import json
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIDGET = REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
HARNESS = REPO / "tests" / "jeg68_markup_harness.cjs"
FIXTURE = REPO / "data" / "fixtures" / "current" / "players.json"

# The genuine CBS ROS markup measured on the real fixture at the default
# shape (12 teams, Full PPR). Pinned so a future data or math regression
# that moves the raw split shows up here, not as a mystery red panel.
GENUINE_CBSROS_MARKUP = 1.000441
# Signature of the pre-valued-inputs defect the check guards against:
# ~91% raw starter share -> 0.85/0.91 markup.
PREVALUED_MARKUP = 0.85 / 0.91


def _node_eval_predicate(values):
    """Evaluate ValueModel.starterMarkupSane over a list via node.

    values: list of floats or the strings "nan"/"inf"/"str" for edge cases.
    """
    script = (
        "const VM = require(process.argv[1]);\n"
        "const vals = JSON.parse(process.argv[2], (k, v) =>\n"
        "  v === '$$nan' ? NaN : v === '$$inf' ? Infinity : v);\n"
        "console.log(JSON.stringify(vals.map(v => VM.starterMarkupSane(v))));\n"
    )
    payload = json.dumps([
        "$$nan" if v == "nan" else "$$inf" if v == "inf" else v
        for v in values
    ])
    proc = subprocess.run(
        ["node", "-e", script, str(VALUE_MODEL), payload],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"node crashed: {proc.stderr[:300]}"
    return json.loads(proc.stdout)


def _harness(*args):
    proc = subprocess.run(
        ["node", str(HARNESS), "--fixture", str(FIXTURE), *args],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"harness crashed: {proc.stderr[:300]}"
    return json.loads(proc.stdout)


class StarterMarkupPredicateTest(unittest.TestCase):
    def test_accepts_genuine_cbsros_markup(self):
        # The exact markup the real fixture produces: ~1.0 must be sane.
        self.assertTrue(_node_eval_predicate([GENUINE_CBSROS_MARKUP])[0])

    def test_accepts_healthy_sources(self):
        # ESPN (1.073) and Razzball (1.088) at the default shape stay green.
        self.assertEqual(_node_eval_predicate([1.073, 1.088]), [True, True])

    def test_accepts_knife_edge_shapes(self):
        # CBS ROS at standard-scoring shapes inverts by <0.5% (0.996-0.997):
        # noise, not a defect.
        self.assertEqual(_node_eval_predicate([0.996, 0.997, 1.028]), [True] * 3)

    def test_rejects_prevalued_inputs(self):
        # Already-valued "raw" inputs (~91% starter share) invert the pie.
        self.assertFalse(_node_eval_predicate([PREVALUED_MARKUP])[0])
        self.assertFalse(_node_eval_predicate([0.959])[0])

    def test_rejects_absurd_and_nonfinite(self):
        self.assertEqual(
            _node_eval_predicate([1.7, 0.5, 0.0, "nan", "inf", "str"]),
            [False] * 6,
        )

    def test_old_threshold_false_fired_on_genuine_markup(self):
        # Discrimination, part 1: the pre-fix rule (`markup > 1.05`) rejects
        # the genuine CBS ROS markup -- the false-fire JEG-68 fixes.
        self.assertFalse(GENUINE_CBSROS_MARKUP > 1.05)
        # ...while it (correctly) rejected genuinely inverted pools.
        self.assertFalse(PREVALUED_MARKUP > 1.05)


class StarterMarkupWiringTest(unittest.TestCase):
    def test_widget_uses_sane_predicate(self):
        # Discrimination, part 2: FAILS on the pre-fix widget. The health
        # check must call the shared predicate, not inline `> 1.05`.
        src = WIDGET.read_text(encoding="utf-8")
        self.assertIn("ValueModel.starterMarkupSane(markup)", src)
        self.assertNotIn("markup > 1.05", src)
        self.assertNotIn("expected > 1.05", src)

    def test_predicate_exported(self):
        src = VALUE_MODEL.read_text(encoding="utf-8")
        self.assertIn("starterMarkupSane: starterMarkupSane", src)
        self.assertIn("STARTER_MARKUP_SANE_LOW: STARTER_MARKUP_SANE_LOW", src)
        self.assertIn("STARTER_MARKUP_SANE_HIGH: STARTER_MARKUP_SANE_HIGH", src)


class StarterMarkupFixtureTest(unittest.TestCase):
    def test_cbsros_fixture_markup_is_sane(self):
        out = _harness("--ppg-field", "cbsros_ppg", "--scoring", "ppr",
                       "--teams", "12")
        self.assertEqual(out["n"], 349)
        self.assertAlmostEqual(out["markup"], GENUINE_CBSROS_MARKUP, places=4)
        self.assertAlmostEqual(out["rawStarterShare"], 0.849625, places=4)
        self.assertTrue(out["sane"], f"harness: {out}")

    def test_espn_and_razzball_still_sane(self):
        for field in ("espn_ppg", "rz_ppg"):
            out = _harness("--ppg-field", field, "--scoring", "ppr",
                           "--teams", "12")
            self.assertTrue(out["sane"], f"{field}: {out}")

    def test_prevalued_simulation_is_flagged(self):
        # End-to-end: a pool pre-run through the fixed pie (the defect the
        # check guards against) must still be flagged by the new band.
        out = _harness("--ppg-field", "cbsros_ppg", "--scoring", "ppr",
                       "--teams", "12", "--simulate-prevalued")
        self.assertLess(out["markup"], 0.98)
        self.assertFalse(out["sane"], f"harness: {out}")


if __name__ == "__main__":
    unittest.main()
