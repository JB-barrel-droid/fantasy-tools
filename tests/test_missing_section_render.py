"""GAP-MISSING-SECTION-REFUSES-RENDER: a missing source section drops that
source; only a missing ESPN anchor refuses the render / fails the build.

Before (origin/main dac0ff2): any source section absent from
comparison-sources-data.json made product-data.js throw "sourceMapCoverage
failed ... Render refused" (blank chart, blank data-health panel), and
build_reference_data.py (the first step of `make validate`) failed on
REQUIRED_LIVE_SOURCES, so the deploy held and the site stayed on its last
build for a problem in one comparison source.

Now:
  * page: the source is listed, greyed out and labelled unavailable, carries
    no values (never zeros), and every other curve renders with the guards
    green; ESPN missing still refuses the render (every curve is indexed to it);
  * build: build_reference_data passes with the source reported as dropped,
    and still fails when the espn section is missing.

Discrimination: the pre-fix product-data.js / build_reference_data.py (read
from git dac0ff2; skipped when absent) fail the "drops, renders" checks.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._dist_server import DIST, ROOT, chromium_executable, serve

PRE_FIX_COMMIT = "dac0ff2"
DROP = ("usatoday", "usatoday_adjusted")
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
READ = """() => {
  const c = window.TradeValueCurveControls;
  const d = window.TradeValueCurveDiagnostics;
  const attempt = fn => { try { return fn(); } catch (e) { return []; } };
  const info = c ? attempt(() => c.getSourceInfo()) : [];
  const rows = c ? attempt(() => c.getAllRows()) : [];
  const valued = key => rows.filter(r => typeof r.values[key] === "number").length;
  const toggle = document.querySelector('#sourceToggles input[data-source="usatoday"]')
    || document.querySelector('input[data-source="usatoday"]');
  return {
    status: document.querySelector('#curve-status')?.innerText || "",
    guards: d ? {fixedPieIndexed: d.fixedPieIndexed, sourceMapCoverage: d.sourceMapCoverage} : null,
    info: Object.fromEntries(info.map(s => [s.key, {available: s.available, unavailable: s.unavailable}])),
    valued: {usatoday: valued("usatoday"), usatoday_adjusted: valued("usatoday_adjusted"),
             espn: valued("espn"), fantasycalc: valued("fantasycalc"), cbsros: valued("cbsros")},
    toggleDisabled: toggle ? toggle.disabled : null,
    toggleText: toggle ? toggle.closest("label").innerText : null,
  };
}"""


def fixture_without(*keys):
    data = json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
    for key in keys:
        data["sources"].pop(key, None)
    return json.dumps(data).encode("utf-8")


def load(overrides, path="/classic/"):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as p:
        exe = chromium_executable(p)
        if exe is None:
            raise unittest.SkipTest("no Chromium available")
        browser = p.chromium.launch(executable_path=exe)
        try:
            with serve(DIST, overrides) as base:
                page = browser.new_page()
                page.goto(base + path, wait_until="networkidle")
                try:
                    page.wait_for_function("() => window.TradeValueCurveDiagnostics", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(500)
                return page.evaluate(READ)
        finally:
            browser.close()


def renders_with_source_dropped(state):
    return (state["guards"] == {"fixedPieIndexed": True, "sourceMapCoverage": True}
            and state["valued"]["espn"] > 100 and state["valued"]["fantasycalc"] > 100
            and state["valued"]["cbsros"] > 100
            and state["valued"]["usatoday"] == 0 and state["valued"]["usatoday_adjusted"] == 0
            and state["info"].get("usatoday", {}).get("available") is False
            and state["info"].get("usatoday", {}).get("unavailable") is True)


def git_show(path):
    proc = subprocess.run(["git", "show", f"{PRE_FIX_COMMIT}:{path}"], cwd=ROOT, capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


class MissingSectionRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "classic" / "index.html").exists():
            raise unittest.SkipTest("dist/ not built (run make sync)")

    def test_missing_source_is_dropped_and_the_rest_renders(self):
        overrides = {"assets/comparison-sources-data.json": fixture_without(*DROP)}
        state = load(overrides)
        self.assertTrue(renders_with_source_dropped(state), json.dumps(state, indent=1))
        self.assertTrue(state["toggleDisabled"], state)
        self.assertIn("unavailable", state["toggleText"] or "", state)
        # The v2 front door renders on the same engine.
        v2 = load(overrides, "/")
        self.assertEqual(v2["guards"], {"fixedPieIndexed": True, "sourceMapCoverage": True}, v2)

    def test_missing_anchor_still_refuses(self):
        state = load({"assets/comparison-sources-data.json": fixture_without("espn")})
        self.assertIsNone(state["guards"], state)
        self.assertEqual(state["valued"]["fantasycalc"], 0, state)

    def test_guard_fails_on_pre_fix_product_data(self):
        old = git_show("app/trade-value-chart/assets/product-data.js")
        if old is None:
            self.skipTest(f"{PRE_FIX_COMMIT} not in this clone")
        state = load({"assets/comparison-sources-data.json": fixture_without(*DROP),
                      "assets/product-data.js": old})
        self.assertFalse(renders_with_source_dropped(state), state)


def load_reference_module(source: bytes | None = None):
    path = ROOT / "pipelines" / "build_reference_data.py"
    if source is not None:
        tmp = Path(tempfile.mkdtemp()) / "build_reference_data_prefix.py"
        tmp.write_bytes(source)
        path = tmp
    sys.path.insert(0, str(ROOT / "pipelines"))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MissingSectionBuildTest(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.keys = set(self.payload["player_keys"].values())

    def without(self, *keys):
        payload = json.loads(json.dumps(self.payload))
        for key in keys:
            payload["sources"].pop(key, None)
        return payload

    def test_missing_source_is_dropped_not_fatal(self):
        mod = load_reference_module()
        report = mod.validate_comparison(self.without(*DROP), self.keys)
        self.assertEqual(sorted(report["dropped_sources"]), sorted(DROP))

    def test_missing_anchor_fails(self):
        mod = load_reference_module()
        with self.assertRaises(SystemExit) as ctx:
            mod.validate_comparison(self.without("espn"), self.keys)
        self.assertIn("anchor", str(ctx.exception))

    def test_complete_fixture_drops_nothing(self):
        mod = load_reference_module()
        self.assertEqual(mod.validate_comparison(self.payload, self.keys)["dropped_sources"], [])

    def test_guard_fails_on_pre_fix_builder(self):
        old = git_show("pipelines/build_reference_data.py")
        if old is None:
            self.skipTest(f"{PRE_FIX_COMMIT} not in this clone")
        mod = load_reference_module(old)
        with self.assertRaises(SystemExit):
            mod.validate_comparison(self.without(*DROP), self.keys)


if __name__ == "__main__":
    unittest.main()
