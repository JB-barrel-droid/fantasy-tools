"""JEG-135 rendered-input sweep wrapper.

The harness (tests/rendered_gate/gate_flexibility.mjs) drives the four input
classes the JEG-47 gate does NOT cover (best-practices §6 / BH-4):

  (a) Bench share  -- real mouse drag + real keyboard arrows; assert the
                     #weightsReadout "Bench X.X%" segment matches the
                     slider value at every step (same shape as JEG-103's
                     guard); round-trip returns the original table hash.
  (b) Roster shape -- real typing into the RB and FLEX roster inputs;
                     assert the table changes; round-trip returns the
                     original table hash.
  (c) Source toggle-- click a source off and on; assert the source card
                     label reflects the change; round-trip returns the
                     original table hash.
  (d) Lock order   -- change the lock order; round-trip returns the
                     original table hash.

The harness is a sibling of tests/rendered_gate/gate.mjs and
bench_share_readout_harness.mjs (same playwright-core import path, same
in-process HTTP server). The wrapper invokes it the same way
test_jeg103_bench_share_readout.py does: skip when dist/ is absent or
when playwright-core is not installed, so `make test-unit` keeps its
"safe in CI" contract -- preview.yml is the real gate.

Discrimination argument (required by PH-8 / BH-1):
  * The bench-share readout assertion (Bench X.X% in #weightsReadout
    must equal slider value) is the same shape as the JEG-103 guard.
    On a build where the slider's input/change handler forgets to call
    syncWeightsReadout(), the readout segment stays at the old value
    (15.0) while the slider is at, say, 22.0; the assertion fails.
  * The away-and-back table-hash assertion is its own discrimination:
    on a build that caches the table under a stale settings object,
    toggling away and back leaves a different SHA-256, and the assert
    fails. The hash is taken from every cell of #tableWrap
    table.all-table tbody tr.row-main in document order, so any value
    drift, ordering drift, or stuck row will surface.
"""
import json
import os
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "rendered_gate" / "gate_flexibility.mjs"
DIST = REPO / "dist"


class RenderedFlexibilitySweepTest(unittest.TestCase):
    def test_away_and_back_round_trips(self):
        if not DIST.exists():
            self.skipTest("dist/ not built; run `make build` before this test")
        # Without the rendered_gate node_modules the harness cannot start.
        # Skip (do not fail) so `make test-unit` stays "safe in CI" -- the
        # preview workflow runs this harness where Chromium is installed.
        gate_modules = REPO / "tests" / "rendered_gate" / "node_modules" / "playwright-core"
        if not gate_modules.exists():
            self.skipTest("playwright-core not installed; see preview.yml rendered gate step")
        env = os.environ.copy()
        proc = subprocess.run(
            ["node", str(HARNESS), str(DIST)],
            capture_output=True, text=True, timeout=90, env=env,
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
                "rendered input sweep failed -- "
                f"{'; '.join(report.get('mismatches') or []) or report}"
            )
        # Belt-and-braces: the harness must have actually exercised each of
        # the four input classes. A guard that short-circuits without
        # touching the controls proves nothing.
        phases = {s.get("phase") for s in report.get("steps", [])}
        for required in ("bench-mouse", "bench-keyboard", "bench-return",
                         "roster-rb-up", "roster-flex-up", "roster-return",
                         "lock-return"):
            self.assertIn(required, phases,
                          f"harness did not exercise phase {required!r}")
        # And the source toggle phase ran (its `source` field is only set
        # when an available checked source was found -- acceptable to skip
        # only if no such source exists, which we surface in mismatches).
        self.assertTrue(
            any(s.get("phase") in ("source-off", "source-on") for s in report["steps"]),
            "harness did not exercise any source-toggle phase",
        )


if __name__ == "__main__":
    unittest.main()