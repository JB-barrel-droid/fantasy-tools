"""Regression: Razzball must render in the comparison dashboard (JEG-6).

On 2026-10-01 the Razzball leg was live in the data layer
(comparison-sources-data.json: source_validation.razzball == "live", 12 combos,
469 players in half_12) and wired into the curve widget, but the comparison
dashboard's SOURCE_KEYS/LABELS/TIPS/WEEKED_SOURCE_KEYS registries never listed
it -- so no source card, no column chip, no lock option ever rendered for
Razzball while the data sat unused.

This test runs the REAL comparison-dashboard.js (+ the REAL value-model.js)
against the REAL fixture JSONs with a stub DOM, then asserts:
  1. the dashboard's own regression diagnostics publish 12/12 live sources
     (allSources / configurableColumns / rolloverAware guards all true), and
  2. the rendered source cards and column toggles contain "Razzball Wk 4".

Proven to discriminate: against the pre-fix dashboard the harness reports
5 failures (no Razzball card, tooltip, or column chip); with the fix all
checks pass. It exercises the real init/render code path, not a re-parse of
the registry, so a registry entry that fails to render still fails.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DASH_JS = REPO / "app" / "trade-value-chart" / "assets" / "comparison-dashboard.js"
VALUE_MODEL_JS = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
ASSETS = REPO / "app" / "trade-value-chart" / "assets"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"

HARNESS_JS = r"""
const fs = require("fs");
const path = require("path");
const REPO = process.argv[2];
const ASSETS = path.join(REPO, "app", "trade-value-chart", "assets");

// 1. Real ValueModel.
const ValueModel = require(path.join(ASSETS, "value-model.js"));
globalThis.ValueModel = ValueModel;

// 2. Stub DOM.
const recorded = {};
const consoleErrors = [];
const origConsoleError = console.error;
console.error = (...a) => { consoleErrors.push(a.map(String).join(" ")); };

function makeEl(id) {
  const t = { __id: id, _html: "", _text: "", _value: "", dataset: {}, style: {} };
  t.classList = { add() {}, remove() {}, toggle() {}, contains: () => false };
  return new Proxy(t, {
    get(tg, p) {
      if (p === "__id" || p === "dataset" || p === "style" || p === "classList") return tg[p];
      if (p === "innerHTML") return tg._html;
      if (p === "textContent") return tg._text;
      if (p === "value") return tg._value;
      if (p === "querySelector") return (sel) => makeEl(String(sel));
      if (p === "querySelectorAll") return () => [];
      if (p === "getAttribute") return () => null;
      if (p === "closest") return () => null;
      if (["appendChild", "addEventListener", "removeEventListener",
           "setAttribute", "removeAttribute", "click", "focus"].includes(p)) return () => {};
      return (...a) => makeEl(`${id}.${String(p)}`);
    },
    set(tg, p, v) {
      if (p === "innerHTML") { tg._html = String(v); recorded[`${id}:innerHTML`] = String(v); return true; }
      if (p === "textContent") { tg._text = String(v); return true; }
      if (p === "value") { tg._value = v; return true; }
      tg[p] = v; return true;
    },
  });
}

const playersPayload = JSON.parse(fs.readFileSync(
  path.join(REPO, "data", "fixtures", "current", "players.json"), "utf8"));
const playersDataEl = makeEl("players-data");
playersDataEl.textContent = JSON.stringify({ players: playersPayload.players });

globalThis.document = {
  getElementById: (id) => (id === "players-data" ? playersDataEl : makeEl(id)),
  createElement: (tag) => makeEl(tag),
  querySelector: () => makeEl("doc>q"),
  querySelectorAll: () => [],
  body: makeEl("body"),
};
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.setInterval = () => 0;
globalThis.fetch = async (url) => {
  const u = String(url);
  const file = u.endsWith("comparison-sources-data.json") ? path.join(ASSETS, "comparison-sources-data.json")
    : u.endsWith("adjustment-inputs.json") ? path.join(ASSETS, "adjustment-inputs.json")
    : null;
  if (!file || !fs.existsSync(file)) return { ok: false, status: 404, json: async () => ({}) };
  return { ok: true, status: 200, json: async () => JSON.parse(fs.readFileSync(file, "utf8")) };
};

// 3. Load the REAL dashboard script.
(0, eval)(fs.readFileSync(path.join(ASSETS, "comparison-dashboard.js"), "utf8"));

(async () => {
  await new Promise((r) => setTimeout(r, 2500));
  await new Promise((r) => setTimeout(r, 2500));
  const out = { diagnostics: globalThis.TradeValueComparisonDiagnostics || null,
                cards: recorded["#sourceCards:innerHTML"] || "",
                toggles: recorded["#columnToggles:innerHTML"] || "",
                consoleErrors };
  process.stdout.write(JSON.stringify(out));
})();
"""


def _run_harness():
    if shutil.which("node") is None:
        raise unittest.SkipTest("node is required for the dashboard render harness")
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as handle:
        handle.write(HARNESS_JS)
        harness_path = handle.name
    try:
        proc = subprocess.run(
            ["node", harness_path, str(REPO)],
            capture_output=True, text=True, timeout=60, cwd=str(REPO),
        )
    finally:
        os.unlink(harness_path)
    if proc.returncode != 0:
        raise AssertionError(f"dashboard harness crashed: {proc.stderr[:500]}")
    return json.loads(proc.stdout)


class RazzballDashboardRenderTest(unittest.TestCase):
    def test_razzball_live_in_fixture(self):
        payload = json.loads(FIXTURE.read_text())
        self.assertEqual(payload["source_validation"].get("razzball"), "live",
                         "fixture must carry a validated-live razzball section")
        combos = payload["sources"]["razzball"]["combos"]
        for combo in ("standard_12", "half_12", "full_12"):
            values = combos.get(combo, {}).get("values", {})
            self.assertTrue(len(values) > 100,
                            f"razzball {combo} has too few values to render")

    def test_razzball_renders_in_dashboard(self):
        result = _run_harness()
        diag = result["diagnostics"]
        self.assertIsNotNone(diag, "runRegressionGuards never completed -- dashboard init threw")
        self.assertTrue(diag.get("allSources"),
                        f"allSources guard false with razzball registered: {diag}")
        self.assertEqual(diag.get("sourceCount"), 12,
                         f"expected 12 dashboard sources, got {diag}")
        self.assertTrue(diag.get("configurableColumns"), f"configurableColumns guard: {diag}")
        self.assertTrue(diag.get("rolloverAware"), f"rolloverAware guard: {diag}")
        self.assertIn("Razzball Wk 4", result["cards"],
                      "source cards do not render a Razzball card")
        self.assertIn("Razzball rest-of-season projections", result["cards"],
                      "Razzball card tooltip (TIPS) not rendered")
        self.assertIn("Razzball Wk 4", result["toggles"],
                      "column toggles do not offer a Razzball column")
        self.assertEqual(result["consoleErrors"], [],
                         f"dashboard init logged errors: {result['consoleErrors'][:2]}")


if __name__ == "__main__":
    unittest.main()
