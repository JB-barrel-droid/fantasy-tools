"""JEG-69: fixed-pie direction check must tolerate boundary noise.

The `${vorpKey}-fixed-pie-direction` ChartHealth check asserted a strict
`rawStarterShare < starterShare`. CBS ROS's raw pool genuinely sits at
85.2-85.3% starter share at 14-team standard (verified source-pure in
JEG-68: CBS snapshot per_game = ROS/gp, fixture matches, pipeline's
independent two-tier leg agrees) -- 0.2-0.3pp over the 85% target -- and
tripped the check on a correct build while the markup (0.996) sat inside
the sane band.

The fix replaces the strict inequality (stated three equivalent ways:
share < target, starterScale > rawScale, benchScale < rawScale all reduce
to the same condition for positive pools) with
ValueModel.fixedPieDirectionSane, a 1pp epsilon-tolerant predicate. The
epsilon keeps the direction check slightly stricter than the markup sane
band (fails at 86.0% raw starter share vs 86.7% for markup < 0.98), so a
genuine inversion (the ~91% pre-valued-inputs defect) still fails.

Discrimination: test_widget_uses_direction_predicate FAILS on the pre-fix
widget (it asserts the strict literal is gone and the predicate call is
present). test_strict_inequality_false_fired documents that the old rule
rejects the genuine 85.3% share.
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

# The genuine CBS ROS raw starter share at the knife-edge shape
# (14 teams, standard scoring) that tripped the strict check.
GENUINE_CBSROS_14T_STD_SHARE = 0.8534
# Signature of the pre-valued-inputs defect the check guards against:
# ~91% raw starter share inverts the pie.
PREVALUED_SHARE = 0.91
TARGET_SHARE = 0.85


def _node_eval_direction(pairs):
    """Evaluate ValueModel.fixedPieDirectionSane over (share, target) pairs."""
    script = (
        "const VM = require(process.argv[1]);\n"
        "const pairs = JSON.parse(process.argv[2]);\n"
        "console.log(JSON.stringify(pairs.map(p => VM.fixedPieDirectionSane(p[0], p[1]))));\n"
    )
    proc = subprocess.run(
        ["node", "-e", script, str(VALUE_MODEL), json.dumps(pairs)],
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


class DirectionPredicateTest(unittest.TestCase):
    def test_accepts_knife_edge_cbsros_shapes(self):
        # The JEG-69 false-fire: 85.2-85.3% at 14t standard must pass.
        self.assertEqual(
            _node_eval_direction([
                [0.8534, TARGET_SHARE],
                [0.8522, TARGET_SHARE],
                [0.8496, TARGET_SHARE],  # default 12t ppr shape
            ]),
            [True, True, True],
        )

    def test_accepts_exact_target(self):
        self.assertTrue(_node_eval_direction([[0.85, TARGET_SHARE]])[0])

    def test_rejects_material_inversion(self):
        # The pre-valued-inputs defect (~91%) must still fail.
        self.assertFalse(_node_eval_direction([[PREVALUED_SHARE, TARGET_SHARE]])[0])
        self.assertFalse(_node_eval_direction([[0.87, TARGET_SHARE]])[0])

    def test_rejects_nonfinite_and_nonstrict_types(self):
        script = (
            "const VM = require(process.argv[1]);\n"
            "console.log(JSON.stringify([\n"
            "  VM.fixedPieDirectionSane(NaN, 0.85),\n"
            "  VM.fixedPieDirectionSane(0.84, NaN),\n"
            "  VM.fixedPieDirectionSane(Infinity, 0.85),\n"
            "  VM.fixedPieDirectionSane('0.84', 0.85),\n"
            "]));\n"
        )
        proc = subprocess.run(
            ["node", "-e", script, str(VALUE_MODEL)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, f"node crashed: {proc.stderr[:300]}"
        self.assertEqual(json.loads(proc.stdout), [False] * 4)

    def test_epsilon_exported(self):
        script = (
            "const VM = require(process.argv[1]);\n"
            "console.log(JSON.stringify(VM.STARTER_DIRECTION_EPS));\n"
        )
        proc = subprocess.run(
            ["node", "-e", script, str(VALUE_MODEL)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, f"node crashed: {proc.stderr[:300]}"
        self.assertEqual(json.loads(proc.stdout), 0.01)

    def test_strict_inequality_false_fired(self):
        # Discrimination, part 1: the pre-fix rule rejects the genuine
        # 85.3% share -- the false-fire JEG-69 fixes.
        self.assertFalse(GENUINE_CBSROS_14T_STD_SHARE < TARGET_SHARE)
        # ...while it (correctly) rejected the genuinely inverted pool.
        self.assertFalse(PREVALUED_SHARE < TARGET_SHARE)


class DirectionWiringTest(unittest.TestCase):
    def test_widget_uses_direction_predicate(self):
        # Discrimination, part 2: FAILS on the pre-fix widget. The health
        # check must call the shared tolerant predicate, not the inline
        # strict triple-inequality.
        src = WIDGET.read_text(encoding="utf-8")
        self.assertIn(
            "ValueModel.fixedPieDirectionSane(rawStarterShare, starterShare)", src
        )
        self.assertNotIn("rawStarterShare < starterShare &&", src)

    def test_predicate_exported(self):
        src = VALUE_MODEL.read_text(encoding="utf-8")
        self.assertIn("fixedPieDirectionSane: fixedPieDirectionSane", src)
        self.assertIn("STARTER_DIRECTION_EPS: STARTER_DIRECTION_EPS", src)


class DirectionFixtureTest(unittest.TestCase):
    def test_cbsros_passes_all_twelve_shapes(self):
        # Acceptance criterion 1: the direction predicate passes for CBS
        # ROS at every league shape (3 scorings x 4 team counts).
        failures = []
        for scoring in ("ppr", "half_ppr", "standard"):
            for teams in ("8", "10", "12", "14"):
                out = _harness("--ppg-field", "cbsros_ppg", "--scoring", scoring,
                               "--teams", teams)
                ok = _node_eval_direction(
                    [[out["rawStarterShare"], TARGET_SHARE]])[0]
                if not ok:
                    failures.append(
                        f"{scoring}/{teams}t share={out['rawStarterShare']:.4f}"
                    )
        self.assertEqual(failures, [], f"direction failures: {failures}")

    def test_knife_edge_shape_pinned(self):
        out = _harness("--ppg-field", "cbsros_ppg", "--scoring", "standard",
                       "--teams", "14")
        self.assertAlmostEqual(
            out["rawStarterShare"], GENUINE_CBSROS_14T_STD_SHARE, places=3
        )
        self.assertTrue(
            _node_eval_direction([[out["rawStarterShare"], TARGET_SHARE]])[0]
        )

    def test_prevalued_simulation_still_fails_direction(self):
        # Acceptance criterion 2: a genuinely inverted (pre-valued) pool
        # still fails the tolerant direction check.
        out = _harness("--ppg-field", "cbsros_ppg", "--scoring", "ppr",
                       "--teams", "12", "--simulate-prevalued")
        self.assertGreater(out["rawStarterShare"], 0.86)
        self.assertFalse(
            _node_eval_direction([[out["rawStarterShare"], TARGET_SHARE]])[0],
            f"harness: {out}",
        )

    def test_espn_and_razzball_still_pass(self):
        for field in ("espn_ppg", "rz_ppg"):
            out = _harness("--ppg-field", field, "--scoring", "ppr",
                           "--teams", "12")
            self.assertTrue(
                _node_eval_direction([[out["rawStarterShare"], TARGET_SHARE]])[0],
                f"{field}: {out}",
            )


if __name__ == "__main__":
    unittest.main()
