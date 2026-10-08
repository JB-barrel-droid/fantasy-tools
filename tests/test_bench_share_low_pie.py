"""GAP-BENCH-SHARE-LOW-PIE: the anchor keeps its pie across the whole bench
share slider, the slider re-prices the chart, and a failed guard recovers.

Found by the views-audit lane (origin/main a1ff559): Full PPR, 12 teams,
bench share 1-3%, then any rebuild -> fixedPieIndexed failed on the ESPN
anchor by 2.05 (tolerance 2) and the chart stayed blank.

Root cause (not the tolerance): the ESPN anchor is the published ESPN values
mapped through the live OLS cells, max(0, alpha + beta * x). An OLS cell's
fitted values sum to its target (the live two-tier tier total, so starter +
bench = the position's pie), but at low bench shares the bench cells fit
negative values for the deepest bench players and the clip at 0 adds mass:
the anchor ran 0.65-1.78 above its pie in 10 of 12 combos on aefb8f7 data
(peak at 4%, just inside the RB/WR/TE windows where the bench rate is ~0;
1-3% step up to the same windows, so they price identically).

Two further defects made it sticky:
  * setBenchShareFraction moved only the control and readout; the chart kept
    the previous share's values and diagnostics until an unrelated rebuild
    (view tab, scoring, ...), so moving the slider back never re-ran the
    guards;
  * a guard failure left guardsPassed true, so the resize listener repainted
    the rejected curves.

Checks (each proved against a broken state):
1. Across the slider's whole range (0.01 steps plus both bounds) at four
   league settings, the anchor's total equals the sum of its positional pies
   within 0.01 (and each position within 0.011), fixedPieIndexed holds, and a
   slider move alone gives the same values as a full rebuild. Broken states:
   the pre-fix widget (aefb8f7) and two single-defect mutations.
2. A guard failure blanks the chart for that setting only: status says
   "Curves unavailable", the canvas is empty and stays empty on resize; the
   next valid slider setting repaints and the status returns to Validated.
   Broken states: the pre-fix widget and a mutation that leaves guardsPassed
   true.
"""
from __future__ import annotations

import json
import subprocess
import unittest

from tests._dist_server import DIST, ENGINE_PAGE, ROOT, chromium_executable, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


PRE_FIX_COMMIT = "aefb8f7"
WIDGET = "assets/curve-widget.js"
SETTINGS = [("ppr", 12), ("standard", 8), ("half_ppr", 10), ("ppr", 14)]
PIE_TOLERANCE = 0.01

# Test hook on the served copy only: lets the recovery check force a guard
# failure at one setting without touching the shipped tolerance.
TOLERANCE_HOOK = ("const tolerance = 2;", "const tolerance = window.__benchLowTolerance ?? 2;")

SWEEP = """async ([settings, step]) => {
  const c = window.TradeValueCurveControls;
  const espnValues = () => Object.fromEntries(c.getAllRows()
    .filter(r => typeof r.values.espn === "number").map(r => [r.player_key, r.values.espn]));
  const anchor = () => {
    const d = window.TradeValueCurveDiagnostics;
    const e = d.fixedPie.checks.find(x => x.source === "espn");
    return {ok: d.fixedPieIndexed, delta: e.delta, perPos: e.perPos};
  };
  const problems = [];
  let checked = 0;
  for (const [scoring, teams] of settings) {
    c.setScoring(scoring); c.setTeams(teams);
    const [lo, hi] = c.getBenchBounds();
    const shares = [lo];
    for (let s = Math.ceil(lo / step) * step; s < hi - 1e-9; s += step) if (s > lo + 1e-9) shares.push(s);
    shares.push(hi);
    for (const share of shares) {
      const tag = `${scoring}/${teams} @${(share * 100).toFixed(1)}%`;
      let afterSlider = null, err = null;
      try { c.setBenchShareFraction(share); } catch (e) { err = String(e.message || e); }
      afterSlider = {values: espnValues(), anchor: anchor()};
      try { document.querySelector('#viewModeTabs [data-view-mode=indexed]').click(); } catch (e) { err = err || String(e.message || e); }
      const rebuilt = {values: espnValues(), anchor: anchor()};
      checked += 1;
      if (err) problems.push(`${tag}: threw ${err.slice(0, 120)}`);
      if (!rebuilt.anchor.ok) problems.push(`${tag}: fixedPieIndexed false`);
      if (!(Math.abs(rebuilt.anchor.delta) <= %TOL%)) problems.push(`${tag}: anchor total - pie = ${rebuilt.anchor.delta.toFixed(3)}`);
      Object.entries(rebuilt.anchor.perPos).forEach(([pos, p]) => {
        if (!(Math.abs(p.total - p.pie) <= %TOL% + 0.001)) problems.push(`${tag}: ${pos} total ${p.total} vs pie ${p.pie}`);
      });
      const keys = Object.keys(rebuilt.values);
      const stale = keys.filter(k => !(Math.abs((afterSlider.values[k] ?? NaN) - rebuilt.values[k]) <= 1e-9)).length;
      if (stale) problems.push(`${tag}: slider move left ${stale} of ${keys.length} anchor values stale until a rebuild`);
    }
    c.setBenchShareFraction(0.15);
  }
  return {checked, problems};
}""".replace("%TOL%", str(PIE_TOLERANCE))

RECOVERY = """async () => {
  const c = window.TradeValueCurveControls;
  const canvas = document.querySelector('#chart');
  const painted = () => {
    const ctx = canvas.getContext('2d');
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    for (let i = 3; i < img.length; i += 4) if (img[i] !== 0) return true;
    return false;
  };
  const status = () => document.querySelector('#curve-status')?.innerText || "";
  const out = {paintedAtLoad: painted()};
  window.__benchLowTolerance = -1;          // every source fails the pie guard
  try { c.setBenchShareFraction(0.05); } catch (e) { out.threw = String(e.message || e).slice(0, 80); }
  out.failedGuard = window.TradeValueCurveDiagnostics.fixedPieIndexed === false;
  out.failedStatus = status().slice(0, 120);
  out.paintedAfterFail = painted();
  window.dispatchEvent(new Event('resize'));
  out.paintedAfterResize = painted();
  window.__benchLowTolerance = undefined;   // the next setting is valid
  try { c.setBenchShareFraction(0.15); } catch (e) { out.threwOnRecovery = String(e.message || e).slice(0, 80); }
  out.recoveredGuard = window.TradeValueCurveDiagnostics.fixedPieIndexed === true;
  out.recoveredStatus = status().slice(0, 120);
  out.paintedAfterRecovery = painted();
  return out;
}"""


def git_show(path, commit=PRE_FIX_COMMIT):
    proc = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


def built_widget() -> bytes:
    return (DIST / WIDGET).read_bytes()


def mutate(widget: bytes, old: str, new: str) -> bytes:
    text = widget.decode("utf-8")
    if text.count(old) != 1:
        raise AssertionError(f"mutation anchor not found exactly once: {old[:60]!r}")
    return text.replace(old, new).encode("utf-8")


def with_hook(widget: bytes) -> bytes:
    return mutate(widget, *TOLERANCE_HOOK)


def run(widget: bytes, script: str, arg=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as p:
        exe = chromium_executable(p)
        if exe is None:
            raise _render_env.unavailable("no Chromium available")
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(DIST, {WIDGET: widget}) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(base + "/classic/", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveDiagnostics", timeout=30000)
                page.wait_for_timeout(300)
                return page.evaluate(script, arg)
        finally:
            browser.close()


def sweep(widget: bytes, settings=SETTINGS, step=0.01):
    return run(widget, SWEEP, [list(map(list, settings)), step])


def recovered(state) -> bool:
    return (state["paintedAtLoad"] and state["failedGuard"]
            and "Curves unavailable" in state["failedStatus"]
            and not state["paintedAfterFail"] and not state["paintedAfterResize"]
            and state["recoveredGuard"] and state["recoveredStatus"].startswith("Validated")
            and state["paintedAfterRecovery"] and "threwOnRecovery" not in state)


class BenchShareLowPieTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_anchor_pie_holds_across_the_slider(self):
        result = sweep(built_widget())
        self.assertGreater(result["checked"], 100, result)
        self.assertEqual(result["problems"], [], "\n".join(result["problems"][:40]))

    def test_sweep_catches_the_pre_fix_widget(self):
        old = git_show("app/trade-value-chart/assets/curve-widget.js")
        if old is None:
            self.skipTest(f"{PRE_FIX_COMMIT} not in this clone")
        problems = sweep(old, [("ppr", 12)])["problems"]
        self.assertTrue(any("anchor total - pie" in p for p in problems), problems[:10])
        self.assertTrue(any("stale" in p for p in problems), problems[:10])

    def test_sweep_catches_the_clip_mass(self):
        # Drop only the cell-total restoration: the pie check must fail.
        broken = mutate(built_widget(), "if (!(sums.kept > sums.fitted) || !(sums.fitted > 0)) return;", "return;")
        problems = sweep(broken, [("ppr", 12)])["problems"]
        self.assertTrue(any("anchor total - pie" in p for p in problems), problems[:10])
        self.assertFalse(any("stale" in p for p in problems), problems[:10])

    def test_sweep_catches_a_slider_that_does_not_reprice(self):
        broken = mutate(built_widget(), "if (engineReady) {\n      refreshAfterWeightChange(publish);",
                        "if (false) {\n      refreshAfterWeightChange(publish);")
        problems = sweep(broken, [("ppr", 12)])["problems"]
        self.assertTrue(any("stale" in p for p in problems), problems[:10])

    def test_guard_failure_blanks_then_recovers(self):
        state = run(with_hook(built_widget()), RECOVERY)
        self.assertTrue(recovered(state), json.dumps(state, indent=1))

    def test_recovery_check_catches_the_pre_fix_widget(self):
        old = git_show("app/trade-value-chart/assets/curve-widget.js")
        if old is None:
            self.skipTest(f"{PRE_FIX_COMMIT} not in this clone")
        state = run(with_hook(old), RECOVERY)
        self.assertFalse(recovered(state), json.dumps(state, indent=1))

    def test_recovery_check_catches_a_sticky_guards_passed(self):
        broken = mutate(with_hook(built_widget()), "      guardsPassed = false;\n      clearCanvasForFailedGuard();\n", "")
        state = run(broken, RECOVERY)
        self.assertFalse(recovered(state), json.dumps(state, indent=1))


if __name__ == "__main__":
    unittest.main()
