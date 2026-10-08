"""JEG-103 regression guard: bench-share slider must keep #weightsReadout in sync.

The bug: when the user drags the bench-share slider, the slider's own label
updates and the table values recompute, but the Weights panel readout (the
caption that names the share) stays at "Bench 15.0% (default 15%)" until a
league/scoring change kicks ``syncWeightsReadout()``. The fix wires the
slider's input/change handlers to call ``syncWeightsReadout()`` directly.

Discrimination argument: on the pre-fix code, after ``moveSliderTo(...)``
sets the slider to e.g. 0.18 and dispatches input+change, the readout still
says "Bench 15.0%" (the slider's stored value moved but the caption did
not). The harness's third assertion
  ``|readoutBench - sliderValue*100| < 0.05``
fails with readout=15.0 vs slider=18.0. The guard therefore catches the
defect it names -- it is not a tautology that passes against any state.

The harness is the gate's sibling (tests/rendered_gate/gate.mjs): the same
playwright-core import path, the same in-process HTTP server. It is wired
into ``make test-unit`` alongside the other rendered checks. CI installs
the package the same way the gate's package.json directs (see Makefile /
.github/workflows).
"""
import json
import os
import subprocess
import unittest
from pathlib import Path
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "rendered_gate" / "bench_share_readout_harness.mjs"
DIST = REPO / "dist"


class BenchShareReadoutSyncTest(unittest.TestCase):
    def test_readout_follows_slider_after_drag(self):
        if not DIST.exists():
            raise _render_env.unavailable("dist/ not built; run `make build` before this test")
        # playwright-core resolves relative to the harness file; without the
        # rendered_gate node_modules the harness cannot start. Skip (do not
        # fail) so `make test-unit` keeps its "safe in CI" contract -- the
        # preview workflow runs this harness where Chromium is installed.
        gate_modules = REPO / "tests" / "rendered_gate" / "node_modules" / "playwright-core"
        if not gate_modules.exists():
            raise _render_env.unavailable("playwright-core not installed; see preview.yml rendered gate step")
        env = os.environ.copy()
        # The harness is invoked with the dist dir and prints a report on stdout.
        proc = subprocess.run(
            ["node", str(HARNESS), str(DIST)],
            capture_output=True, text=True, timeout=60, env=env,
        )
        if proc.returncode != 0 and not proc.stdout.strip().startswith("{"):
            raise AssertionError(
                f"harness failed to start: rc={proc.returncode} stderr={proc.stderr[:1000]}"
            )
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"harness produced non-JSON output: {proc.stdout[:500]} stderr={proc.stderr[:500]}"
            ) from e
        if not report.get("ok"):
            self.fail(
                "bench-share readout failed to follow slider — "
                f"{report.get('mismatch') or report}"
            )
        # Belt-and-braces: at least one step must have moved the slider and
        # seen the readout update. If the harness somehow short-circuited
        # without exercising moves, the guard proves nothing.
        self.assertGreaterEqual(len(report.get("steps", [])), 3,
                                "harness did not exercise enough slider moves")
        for step in report["steps"]:
            self.assertIsNotNone(step["readoutBench"],
                                 f"step {step['target']}: no Bench % in readout")


if __name__ == "__main__":
    unittest.main()