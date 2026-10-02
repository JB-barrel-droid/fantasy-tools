"""JEG-103: bench-share slider must update the Weights panel readout text.

Root cause (2026-10-02): syncWeightsReadout() prints benchShare into the
"Weights" panel readout, but the bench-share slider's input/change/dblclick
handlers (app/trade-value-chart/assets/curve-widget.js ~2311-2313) called
setBenchShareFraction(...) and publishShared() only -- syncWeightsReadout()
was never invoked from the slider path. The slider's own label updated but
the Weights panel readout stayed at "Bench 15.0% (default 15%)" forever.

Fix: call syncWeightsReadout() from the central setBenchShareFraction()
(matches the single source of truth for bench share). This covers every
path that can move the share -- slider input/change, dblclick reset, the
"Reset to 15%" button, resetAllWeights(), and external setBenchShareFraction
callers -- so the readout cannot go stale again.

Discrimination: this test fires the actual slider `input` and `dblclick`
events on the real widget's DOM, then asserts #weightsReadout.textContent
reflects the new share. On broken code the readout text still says
"Bench 15.0%" after a slider move; on fixed code it updates to "Bench 20.0%".
"""
import json
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "jeg103_bench_readout_harness.cjs"
WIDGET = REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js"


def run_case():
    proc = subprocess.run(
        ["node", str(HARNESS)],
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "harness failed (rc=%d): stdout=%s stderr=%s"
            % (proc.returncode, proc.stdout.decode()[:500], proc.stderr.decode()[:500])
        )
    out = proc.stdout.decode().strip()
    return json.loads(out)


class TestBenchSliderUpdatesReadout(unittest.TestCase):
    def test_initial_readout_at_15(self):
        """After init the readout must show the 15.0% default share. Sanity
        check that the harness actually exercises the readout, not some
        dead DOM node."""
        out = run_case()
        self.assertNotIn("Errored", out, msg=f"harness errored: {out}")
        self.assertIn("Bench 15.0%", out["initialReadout"],
                      f"initial readout must show 15.0%: {out['initialReadout']!r}")

    def test_slider_input_updates_readout(self):
        """DEFECT REPRO: fire the slider input event with value 0.20. The
        Weights panel readout must now contain 'Bench 20.0%'.

        On broken code (pre-fix): the slider's own .bench-share-value label
        updates but the #weightsReadout textContent still says
        'Bench 15.0% (default 15%)' because syncWeightsReadout() was never
        called from the slider path.
        """
        out = run_case()
        self.assertNotIn("Errored", out, msg=f"harness errored: {out}")
        self.assertTrue(out["matches"]["slider"],
                        f"slider input must update #weightsReadout to "
                        f"'Bench 20.0%', got: {out['afterSliderReadout']!r}")
        # Belt-and-braces: the slider's own block readout should also show 20%.
        self.assertIn("20.0%", out["afterSliderBlockValue"],
                      f"bench-share-block readout must show 20.0%: {out['afterSliderBlockValue']!r}")

    def test_slider_dblclick_resets_readout(self):
        """After dblclick (which resets to 15.0%), the readout must
        reflect 15.0%. This catches a regression where the dblclick handler
        changes bench share without syncing the readout."""
        out = run_case()
        self.assertNotIn("Errored", out, msg=f"harness errored: {out}")
        self.assertTrue(out["matches"]["dblclick"],
                        f"slider dblclick must reset readout to "
                        f"'Bench 15.0%', got: {out['afterDblclickReadout']!r}")

    def test_reset_button_updates_readout(self):
        """The 'Reset to 15%' button click must also sync the Weights
        readout. Catches a regression where the reset button path changes
        bench share without syncing the readout."""
        out = run_case()
        self.assertNotIn("Errored", out, msg=f"harness errored: {out}")
        self.assertTrue(out["matches"]["resetBtn"],
                        f"reset button must update readout to "
                        f"'Bench 15.0%', got: {out['afterResetButtonReadout']!r}")


class TestWiring(unittest.TestCase):
    """Code-level wiring: the fix is implemented at the central
    setBenchShareFraction() so every path that can change bench share
    syncs the readout. These checks document the contract: any path that
    mutates benchShare must go through setBenchShareFraction."""

    def test_setBenchShareFraction_calls_syncWeightsReadout(self):
        """JEG-103 fix: setBenchShareFraction must invoke syncWeightsReadout
        on the success path so the slider (and every other caller) cannot
        leave the Weights readout stale. This is the wiring-level check
        that backs the behavior-level tests above."""
        src = WIDGET.read_text(encoding="utf-8")
        # Find the body of setBenchShareFraction and assert it calls
        # syncWeightsReadout() before publishShared().
        self.assertIn("syncWeightsReadout()", src,
                      "syncWeightsReadout must be called from the bench-share path")
        # The literal sequence in the success branch.
        self.assertRegex(
            src,
            r"syncBenchShareControl\(\);\s*(?://[^\n]*\n\s*)*syncWeightsReadout\(\);",
            "setBenchShareFraction must call syncWeightsReadout after "
            "syncBenchShareControl",
        )

    def test_no_stale_readout_paths_in_widget(self):
        """No user-facing handler should mutate benchShare outside of
        setBenchShareFraction. If a new code path mutates benchShare
        directly, it will skip the readout sync and reintroduce JEG-103."""
        src = WIDGET.read_text(encoding="utf-8")
        # The only `benchShare =` writes that aren't the module-level
        # declaration or the `let` initialization.
        import re
        assigns = re.findall(r"^\s*benchShare\s*=", src, flags=re.MULTILINE)
        # Inside the IIFE we have: module-level `let benchShare = ...`
        # and two writes inside setBenchShareFraction/syncBenchShareControl.
        # Anything else is a stale-readout hazard.
        self.assertLessEqual(
            len(assigns), 3,
            f"benchShare is assigned in {len(assigns)} places -- only the "
            f"declaration and setBenchShareFraction/syncBenchShareControl "
            f"should write it. Assignments found: {assigns}",
        )


if __name__ == "__main__":
    unittest.main()