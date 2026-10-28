"""JEG-1044: the Overrides tab's value basis, rendered (spec section 8: the comprehension rubric and task script).

Loads /v2/ headless and drives the Overrides tab like a reader. The ten rubric
items are checks 1-10 below; each is scored 0 or 1 from the DOM and the engine
read back, and every one must score 1.

  1  Overrides is in the nav.
  2  The basis picker shows every preset and "Our methodology" is selected on a fresh visit.
  3  Choosing FantasyCalc changes DDF Value on Player values (and the table header says Rescaled (to FantasyCalc)).
  4  Choosing Custom blend shows a weight slider for all seven sources.
  5  Moving a slider changes the engine's DDF Value live (no Save button).
  6  A player override shows on Player values (the bar counts it; the value changes).
  7  The "Overrides active" indicator appears with any override.
  8  "Reset all" returns to our methodology and clears the player overrides; Undo brings them back.
  9  Trade targets re-sorts when the basis changes.
  10 Compare a trade's verdict reads the overridden value.

Task script (answered from the first screen plus one click): what is the basis
(Our methodology), how many player overrides (0), click FantasyCalc (DDF Value
changes), is the indicator visible (yes, "FantasyCalc only"), click Reset all
(the indicator disappears).

Also: the Customize dialog has no DDF blend tab and points to Overrides; a saved
DDF blend choice (ddf.v2.selection.inputs) and a v1 overrides record migrate to
the v2 record with a one-time notice; a share link carries the basis and the
player overrides, the recipient gets a banner whose "Use our methodology" is one
click and nothing is saved for them; a link too long for the budget drops the
overrides and says why; Export and Import round-trip; radiogroup keyboard
behaviour and names; phone width has no sideways scroll; Compare still fits at
1366x768 with the indicator showing.

Discrimination: BrokenPageIsCaught serves a page whose preset buttons do nothing
and one with the indicator removed and requires the rubric to score below 10.

Skips when no browser is available, unless RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests._dist_server import DIST, ENGINE_PAGE, serve
from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
V2 = DIST / "v2"


def setUpModule():
    _render_env.ensure_built()


READY = "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady() && window.TradeValueV2"


class Session:
    def __init__(self, overrides=None, viewport=(1366, 900), init=None):
        self.overrides, self.viewport, self.init = overrides, viewport, init

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        exe = _render_env.chromium_executable(self._pw)
        if exe is None:
            self._pw.stop()
            raise _render_env.unavailable("no Chromium available")
        self.browser = self._pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        self._srv = serve(DIST, self.overrides)
        self.base = self._srv.__enter__()
        self.page = self.browser.new_page(viewport={"width": self.viewport[0], "height": self.viewport[1]})
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        if self.init:
            self.page.add_init_script(self.init)
        return self

    def open(self, hash_):
        self.page.goto(self.base + "/v2/" + hash_, wait_until="networkidle")
        self.page.wait_for_function(READY, timeout=90000)
        self.page.wait_for_timeout(300)
        return self.page

    def __exit__(self, *exc):
        self._srv.__exit__(*exc)
        self.browser.close()
        self._pw.stop()


def ddf_of(page, name):
    return page.evaluate("""(name) => { const r = window.TradeValueCurveControls.getAllRows().find(x => x.name === name); return r ? r.values.ddf_value : null; }""", name)


def top_player(page, pos="WR", rank=5):
    return page.evaluate("""([pos, rank]) => { const rows = window.TradeValueCurveControls.getAllRows().filter(r => r.pos === pos && Number.isFinite(r.values.ddf_value))
      .sort((a, b) => b.values.ddf_value - a.values.ddf_value); return {key: rows[rank].player_key, name: rows[rank].name, value: rows[rank].values.ddf_value}; }""", [pos, rank])


def set_player_override(page, name, value):
    """The reader's way: search the player on the Overrides tab, pick him, type a value.

    The editor clamps to its own scale (the range slider's max), so the value applied is returned."""
    page.fill("#v2OvSearch", name)
    page.wait_for_selector("#v2OvResults button")
    page.click("#v2OvResults button")
    page.wait_for_selector("#v2OvNumber")
    value = round(min(value, float(page.get_attribute("#v2OvRange", "max"))), 1)
    page.fill("#v2OvNumber", str(value))
    page.press("#v2OvNumber", "Enter")
    page.dispatch_event("#v2OvNumber", "change")
    page.wait_for_timeout(300)
    return value


def rubric(session) -> dict:
    """Score the ten items 0 or 1, from the DOM and the engine read back, on a fresh visit."""
    page = session.page
    score = {}
    order = lambda: page.evaluate("() => window.TradeValueV2.targets().buy.map(r => r.row.player_key).slice(0, 15).join(',')")
    # 1. nav
    session.open("#value-overrides")
    score[1] = int(page.locator('a.v2-tab[data-view="overrides"]').count() == 1)
    # 2. presets and default selection
    presets = page.eval_on_selector_all("#v2OvPresets [role=radio]", "els => els.map(e => [e.textContent, e.getAttribute('aria-checked')])")
    want = ["Our methodology", "FantasyCalc", "USA Today", "FantasyPros", "CBS trade chart", "ESPN", "CBS rest of season", "Razzball", "Custom blend"]
    score[2] = int([n for n, _ in presets] == want and dict(presets)["Our methodology"] == "true" and sum(c == "true" for _, c in presets) == 1)
    # 9 (before). Trade targets on our methodology
    session.open("#trade-targets")
    ours_order = order()
    session.open("#value-overrides")
    # 3. FantasyCalc changes DDF Value (and the page says what Rescaled now means)
    star = top_player(page)
    before = ddf_of(page, star["name"])
    page.click('[data-preset="single:fantasycalc"]')
    page.wait_for_timeout(300)
    after = ddf_of(page, star["name"])
    session.open("#player-values")
    score[3] = int(before is not None and after is not None and abs(before - after) > 1e-6
                   and "Market (to FantasyCalc)" in page.inner_text("body"))
    # 7. indicator while FantasyCalc is on, on a tab that is not Overrides
    score[7] = int("Overrides active: FantasyCalc only" in page.inner_text("#v2OvBar") and page.locator("#v2OvBar").is_visible())
    # 9. Trade targets re-sorts
    session.open("#trade-targets")
    score[9] = int(order() != ours_order)
    # 4/5. blend sliders and live apply (no Save button)
    session.open("#value-overrides")
    page.click('[data-preset="blend"]')
    page.wait_for_timeout(200)
    score[4] = int(page.locator(".v2-ov-wrow input[type=range]").count() == 7)
    espn_before = ddf_of(page, star["name"])
    # JEG-1073: a blend starts on our methodology (the four trade charts); tick a projection in to move its slider.
    page.check("#v2OvOn-espn")
    page.wait_for_timeout(200)
    page.fill("#v2OvW-espn", "90")
    page.wait_for_timeout(400)
    espn_after = ddf_of(page, star["name"])
    score[5] = int(espn_before is not None and espn_after is not None and abs(espn_before - espn_after) > 1e-9
                   and page.get_by_role("button", name="Save").count() == 0)
    page.click('[data-preset="default"]')
    page.wait_for_timeout(300)
    # 6/10. a player override through the real controls, the Player values table and the Compare verdict
    a, b = top_player(page, "RB", 3), top_player(page, "WR", 3)
    session.open("#compare-trade?give=%s&get=%s" % (a["key"], b["key"]))
    even = page.inner_text("#v2CVerdictText")
    session.open("#value-overrides")
    target = set_player_override(page, a["name"], round(a["value"] + 40, 1))
    session.open("#player-values")
    bumped = ddf_of(page, a["name"])
    score[6] = int(bumped is not None and abs(bumped - target) < 0.06
                   and "1 player override" in page.inner_text("#v2OvBar"))
    session.open("#compare-trade?give=%s&get=%s" % (a["key"], b["key"]))
    moved = page.inner_text("#v2CVerdictText")
    score[10] = int(moved != even and ("you win" in moved.lower() or "you lose" in moved.lower() or "even" in moved.lower()))
    # 8. Reset all returns to our methodology and clears the player overrides
    page.click("#v2OvResetAll")
    page.wait_for_timeout(300)
    score[8] = int(page.evaluate("() => window.TradeValueCurveControls.getBasis().isDefault")
                   and page.evaluate("() => Object.keys(window.TradeValueCurveControls.getValueOverrides()).length") == 0
                   and "Overrides active" not in page.inner_text("#v2OvBar"))
    return score


class RubricTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists() or not (V2 / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_rubric_and_task_script(self):
        with Session() as s:
            page = s.open("#value-overrides")
            # Task script, first screen: the basis, the count, then one click.
            first = page.inner_text("#v2Overrides")
            self.assertIn("Our methodology", first)
            self.assertIn("Your player overrides (0)", first)
            self.assertTrue(page.locator("#v2OvBar").is_hidden() or page.inner_text("#v2OvBar").strip() == "")
            star = top_player(page)
            before = ddf_of(page, star["name"])
            page.click('[data-preset="single:fantasycalc"]')
            page.wait_for_timeout(300)
            self.assertNotAlmostEqual(before, ddf_of(page, star["name"]), places=6)
            self.assertIn("Overrides active: FantasyCalc only", page.inner_text("#v2OvBar"))
            page.click("#v2OvResetAll")
            page.wait_for_timeout(300)
            self.assertNotIn("Overrides active", page.inner_text("#v2OvBar"))
            self.assertAlmostEqual(before, ddf_of(page, star["name"]), places=9)
            self.assertEqual(s.errors, [])

    def test_ten_rubric_items(self):
        with Session() as s:
            score = rubric(s)
            self.assertEqual(score, {k: 1 for k in range(1, 11)}, score)
            self.assertEqual(s.errors, [])

    def test_reset_all_and_undo(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page)
            before = ddf_of(page, star["name"])
            page.click('[data-preset="single:usatoday"]')
            page.wait_for_timeout(300)
            page.evaluate("""(k) => { const o = window.DDFOverrides; o.state.values[k] = 77; o.state.names[k] = 'x'; window.TradeValueCurveControls.setValueOverrides(o.state.values); }""", star["key"])
            page.click('[data-preset="blend"]')
            page.click('[data-preset="default"]')
            page.wait_for_timeout(300)
            page.click('[data-preset="single:usatoday"]')
            page.wait_for_timeout(300)
            self.assertIn("Overrides active", page.inner_text("#v2OvBar"))
            page.click("#v2OvResetAll")
            page.wait_for_timeout(300)
            self.assertAlmostEqual(before, ddf_of(page, star["name"]), places=9)
            self.assertEqual(page.evaluate("() => Object.keys(window.TradeValueCurveControls.getValueOverrides()).length"), 0)
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getBasis().isDefault"), True)
            self.assertEqual(json.loads(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"))["basis"], {"mode": "default"})
            page.click("#v2OvUndo")
            page.wait_for_timeout(300)
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getBasis().label"), "USA Today")
            self.assertEqual(s.errors, [])

    def test_customize_has_no_ddf_blend_tab_and_points_to_overrides(self):
        with Session() as s:
            page = s.open("#player-values")
            page.click("#v2EditSources")
            page.wait_for_selector("#v2Popover:not([hidden])")
            self.assertEqual(page.locator('#v2Popover [role=tab]').count(), 0)
            self.assertEqual(page.locator("#v2Popover [data-ddf-input]").count(), 0)
            self.assertNotIn("DDF blend", page.inner_text("#v2Popover"))
            self.assertEqual(page.locator('#v2Popover a[href="v2/#value-overrides"]').count(), 1)
            self.assertEqual(s.errors, [])

    def test_saved_ddf_blend_migrates_with_a_one_time_notice(self):
        seed = """() => { localStorage.setItem('ddf.v2.selection', JSON.stringify({v: 1, shown: ['ddf_value'], inputs: ['espn', 'razzball'], rank: 'ddf_value'})); }"""
        with Session(init="(" + seed + ")()") as s:
            page = s.open("#player-values")
            basis = page.evaluate("() => window.TradeValueCurveControls.getBasis()")
            self.assertEqual((basis["mode"], basis["sources"]), ("blend", ["espn", "razzball"]))
            self.assertIn("The DDF blend control has moved to the Overrides tab", page.inner_text("#v2OvNotice"))
            saved = json.loads(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"))
            self.assertEqual(saved["v"], 2)
            self.assertEqual(saved["basis"]["sources"], ["espn", "razzball"])
            legacy = json.loads(page.evaluate("() => localStorage.getItem('ddf.v2.selection')"))
            self.assertIsNone(legacy["inputs"])
            # Reload (init script would re-seed): the notice is a one-time, and the basis stays.
            page.evaluate("() => localStorage.setItem('ddf.v2.selection', JSON.stringify({v: 1, shown: ['ddf_value'], inputs: null, rank: 'ddf_value'}))")
            page.reload(wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getBasis().sources"), ["espn", "razzball"])
            self.assertEqual(s.errors, [])

    def test_all_three_projections_ticked_maps_to_our_methodology(self):
        """The old default blend (all three projections ticked) maps to our methodology, not a blend of the
        three (Jeremy, 2026-10-27, JEG-1135; reverses the JEG-1073 carry-over). The legacy record is cleared."""
        seed = """() => { localStorage.setItem('ddf.v2.selection', JSON.stringify({v: 1, shown: ['ddf_value'], inputs: ['espn', 'cbsros', 'razzball'], rank: 'ddf_value'})); }"""
        with Session(init="(" + seed + ")()") as s:
            page = s.open("#player-values")
            basis = page.evaluate("() => window.TradeValueCurveControls.getBasis()")
            self.assertTrue(basis["isDefault"], basis)
            self.assertEqual(page.locator("#v2OvNotice", has_text="carried over").count(), 0)
            legacy = json.loads(page.evaluate("() => localStorage.getItem('ddf.v2.selection')"))
            self.assertIsNone(legacy["inputs"])
            self.assertEqual(s.errors, [])

    def test_v1_override_record_reads_as_v2_with_our_basis(self):
        seed = """() => { localStorage.setItem('ddf-v2-value-overrides', JSON.stringify({v: 1, values: {'100': 55}, names: {'100': 'Someone'}})); }"""
        with Session(init="(" + seed + ")()") as s:
            page = s.open("#player-values")
            self.assertTrue(page.evaluate("() => window.TradeValueCurveControls.getBasis().isDefault"))
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()"), {"100": 55})
            page.click("#v2NavToggle")
            page.click('a.v2-tab[data-view="overrides"]')
            page.click('[data-preset="single:cbs"]')
            page.wait_for_timeout(300)
            saved = json.loads(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"))
            self.assertEqual((saved["v"], saved["basis"], saved["values"]), (2, {"mode": "single", "source": "cbs"}, {"100": 55}))
            self.assertEqual(s.errors, [])

    def test_share_link_carries_basis_and_overrides_and_the_recipient_can_leave(self):
        with Session() as s:
            page = s.open("#value-overrides")
            a, b = top_player(page, "RB", 2), top_player(page, "WR", 2)
            c_ = top_player(page, "TE", 1)
            page.click('[data-preset="blend"]')
            # JEG-1073: a blend starts on our methodology (the four trade charts); this link is the three projections.
            for key in ("espn", "cbsros", "razzball"):
                page.check(f"#v2OvOn-{key}")
            for key in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
                page.uncheck(f"#v2OvOn-{key}")
            page.fill("#v2OvW-espn", "60")
            page.fill("#v2OvW-cbsros", "10")
            page.fill("#v2OvW-razzball", "33")
            page.wait_for_timeout(400)
            page.evaluate("""(keys) => { const o = window.DDFOverrides; keys.forEach((k, i) => { o.state.values[k] = 20 + i; o.state.names[k] = 'p' + k; });
              window.TradeValueCurveControls.setValueOverrides(o.state.values); }""", [a["key"], b["key"]])
            page.goto(s.base + f"/v2/#compare-trade?give={a['key']}&get={c_['key']}", wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            page.wait_for_timeout(500)
            link = page.evaluate("() => location.hash")
            self.assertIn("basis=blend:espn.60_cbsros.10_razzball.33", link)
            self.assertRegex(link, r"ov=%d:20" % a["key"])
            saved_before = page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')")
        # A different reader, no saved settings, opens the link.
        with Session() as r:
            page = r.page
            page.goto(r.base + "/v2/" + link, wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            page.wait_for_timeout(500)
            banner = page.inner_text("#v2OvLinkBanner")
            self.assertIn("a custom basis", banner)
            self.assertIn("2 player overrides", banner)
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getBasis().mode"), "blend")
            self.assertEqual(len(page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")), 2)
            self.assertIsNone(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"), "a link's settings are not saved for the reader")
            # Leaving Compare by a tab click reloads the page; the link's settings (and only they) survive it.
            page.click("#v2NavToggle")
            page.click('a.v2-tab[data-view="overrides"]')
            page.wait_for_function(READY, timeout=90000)
            page.wait_for_timeout(400)
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getBasis().mode"), "blend")
            self.assertEqual(len(page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")), 2)
            self.assertIn("a custom basis", page.inner_text("#v2OvLinkBanner"))
            self.assertIsNone(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"))
            page.click("#v2OvUseOurs")
            page.wait_for_timeout(300)
            self.assertTrue(page.evaluate("() => window.TradeValueCurveControls.getBasis().isDefault"))
            self.assertEqual(page.evaluate("() => Object.keys(window.TradeValueCurveControls.getValueOverrides()).length"), 0)
            self.assertEqual(page.locator("#v2OvLinkBanner").count(), 0)
            self.assertIsNone(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"))
            self.assertEqual(r.errors, [])

    def test_old_link_without_basis_changes_nothing(self):
        with Session() as s:
            page = s.open("#value-overrides")
            a, b = top_player(page, "RB", 2), top_player(page, "WR", 2)
            page.goto(s.base + f"/v2/#compare-trade?give={a['key']}&get={b['key']}&scoring=ppr", wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            self.assertTrue(page.evaluate("() => window.TradeValueCurveControls.getBasis().isDefault"))
            self.assertEqual(page.locator("#v2OvLinkBanner").count(), 0)
            self.assertNotIn("basis=", page.evaluate("() => location.hash"))

    def test_many_overrides_pack_and_an_over_long_link_drops_them_with_a_message(self):
        with Session() as s:
            page = s.open("#value-overrides")
            keys = page.evaluate("() => window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values.ddf_value)).slice(0, 40).map(r => r.player_key)")
            page.evaluate("""(keys) => { const o = window.DDFOverrides; keys.slice(0, 12).forEach((k, i) => { o.state.values[k] = 10 + i; });
              window.TradeValueCurveControls.setValueOverrides(o.state.values); }""", keys)
            params = page.evaluate("() => window.DDFOverrides.shareParams()")
            self.assertTrue(params["ov"].startswith("z:"), params)
            self.assertLess(len(params["ov"]), 12 * 10)
            self.assertFalse(params["dropped"])
            # Round trip through the recipient's parser.
            page.goto(s.base + f"/v2/#compare-trade?give={keys[0]}&get={keys[1]}", wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            page.wait_for_timeout(300)
            self.assertIn("ov=z:", page.evaluate("() => location.hash"))
        with Session() as s:
            page = s.open("#value-overrides")
            keys = page.evaluate("() => window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values.ddf_value)).slice(0, 700).map(r => r.player_key)")
            page.evaluate("""(keys) => { const o = window.DDFOverrides; keys.forEach((k, i) => { o.state.values[k] = 10 + (i % 80); });
              window.TradeValueCurveControls.setValueOverrides(o.state.values); }""", keys)
            page.goto(s.base + f"/v2/#compare-trade?give={keys[0]}&get={keys[1]}", wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            page.wait_for_timeout(300)
            self.assertNotIn("ov=", page.evaluate("() => location.hash"))
            self.assertLess(len(page.evaluate("() => location.hash")), 1800)
            page.context.grant_permissions(["clipboard-read", "clipboard-write"])
            page.click("#v2CShare")
            page.wait_for_timeout(300)
            self.assertIn("too large for a link", page.inner_text("#v2CShareNote"))
            page.evaluate("() => { location.hash = '#value-overrides'; }")
            page.wait_for_timeout(400)
            self.assertIn("is-hint", page.get_attribute("#v2OvExport", "class"))

    def test_export_and_import_round_trip(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "RB", 4)
            page.click('[data-preset="single:fantasypros"]')
            page.evaluate("""(k) => { const o = window.DDFOverrides; o.state.values[k] = 41.5; o.state.names[k] = 'n'; window.TradeValueCurveControls.setValueOverrides(o.state.values); }""", star["key"])
            doc = page.evaluate("""() => { const o = window.DDFOverrides; return {basis: o.basis(), n: o.count()}; }""")
            self.assertEqual(doc["basis"], {"mode": "single", "source": "fantasypros"})
            # Export, then load the same file into a fresh page through Import.
            page.reload(wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            page.click("#v2NavToggle")
            page.click('a.v2-tab[data-view="overrides"]')
            payload = {"v": 2, "basis": {"mode": "blend", "sources": ["espn", "bogus"], "weights": {"espn": 70, "bogus": 30}},
                       "overrides": [{"player_key": str(star["key"]), "name": star["name"], "type": "absolute", "value": 41.5},
                                     {"player_key": "999999999", "name": "Nobody", "type": "absolute", "value": 10}]}
            page.set_input_files("#v2OvImportFile", files=[]) if page.locator("#v2OvImportFile").count() else None
            with page.expect_file_chooser() as chooser:
                page.click("#v2OvImport")
            chooser.value.set_files(files=[{"name": "ddf-overrides.json", "mimeType": "application/json", "buffer": json.dumps(payload).encode()}])
            page.wait_for_selector("#v2OvImportNote")
            note = page.inner_text("#v2OvImportNote")
            self.assertIn("Imported 1 player override and the value basis", note)
            self.assertIn("bogus", note)
            self.assertIn("Skipped 1 override", note)
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getBasis().sources"), ["espn"])
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()"), {str(star["key"]): 41.5})
            with page.expect_download() as dl:
                page.click("#v2OvExport")
            exported = json.loads(Path(dl.value.path()).read_text())
            self.assertEqual(exported["v"], 2)
            self.assertEqual(exported["basis"]["sources"], ["espn"])
            self.assertEqual(exported["overrides"][0]["value"], 41.5)
            page.click("#v2OvImport")
            self.assertEqual(s.errors, [])

    def test_picker_is_a_named_radiogroup_with_arrow_keys_and_blend_sliders_are_named(self):
        with Session() as s:
            page = s.open("#value-overrides")
            self.assertEqual(page.get_attribute("#v2OvPresets", "role"), "radiogroup")
            self.assertEqual(page.get_attribute("#v2OvPresets", "aria-label"), "Value basis")
            # Roving tab stop: only the selected radio is tabbable.
            tab = page.eval_on_selector_all("#v2OvPresets [role=radio]", "els => els.map(e => e.tabIndex)")
            self.assertEqual(tab, [0] + [-1] * 8)
            page.focus('[data-preset="default"]')
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(250)
            self.assertEqual(page.evaluate("() => document.activeElement.dataset.preset"), "single:fantasycalc")
            self.assertEqual(page.get_attribute('[data-preset="single:fantasycalc"]', "aria-checked"), "true")
            self.assertEqual(page.get_attribute('[data-preset="default"]', "aria-checked"), "false")
            page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(250)
            self.assertEqual(page.evaluate("() => document.activeElement.dataset.preset"), "default")
            page.click('[data-preset="blend"]')
            page.wait_for_timeout(200)
            labels = page.eval_on_selector_all(".v2-ov-wrow input[type=range]", "els => els.map(e => e.getAttribute('aria-label'))")
            self.assertEqual(labels, ["ESPN weight", "CBS rest of season weight", "Razzball weight", "FantasyCalc weight",
                                      "USA Today weight", "FantasyPros weight", "CBS trade chart weight"])
            # JEG-1073: a blend starts on the four trade charts, so the first enabled slider is FantasyCalc's.
            self.assertEqual(page.evaluate("() => document.activeElement.id"), "v2OvW-fantasycalc")
            # The last ticked source cannot be unticked: untick the other three trade charts, FantasyCalc stays.
            for key in ("usatoday", "fantasypros", "cbs"):
                page.uncheck(f"#v2OvOn-{key}")
                page.wait_for_timeout(200)
            self.assertTrue(page.locator("#v2OvOn-fantasycalc").is_disabled())
            self.assertIn("Last source stays on", page.inner_text("[data-source-row=fantasycalc]"))
            self.assertEqual(page.locator("#v2OvBar").get_attribute("hidden") is not None or "Overrides active" in page.inner_text("#v2OvBar"), True)
            self.assertEqual(s.errors, [])

    def test_health_check_says_when_the_basis_is_not_ours(self):
        """#899 Health check (and every Values auditing page): thresholds were set on our methodology."""
        with Session() as s:
            page = s.open("#values-auditing/health-check")
            self.assertTrue(page.locator("#v2AuditBasisNote").is_hidden())
            page.evaluate("() => window.TradeValueCurveControls.setBasis({mode: 'single', source: 'fantasycalc'})")
            page.evaluate("() => { location.hash = '#values-auditing/single-source'; location.hash = '#values-auditing/health-check'; }")
            page.wait_for_timeout(600)
            note = page.inner_text("#v2AuditBasisNote")
            self.assertIn("your custom basis (FantasyCalc)", note)
            self.assertIn("thresholds on these pages were set on our methodology", note)
            page.evaluate("() => window.TradeValueCurveControls.setBasis(null)")
            page.evaluate("() => { location.hash = '#values-auditing/single-source'; location.hash = '#values-auditing/health-check'; }")
            page.wait_for_timeout(600)
            self.assertTrue(page.locator("#v2AuditBasisNote").is_hidden())
            self.assertEqual(s.errors, [])

    def test_phone_has_no_sideways_scroll_and_blend_rows_stack(self):
        with Session(viewport=(390, 844)) as s:
            page = s.open("#value-overrides")
            page.click('[data-preset="blend"]')
            page.wait_for_timeout(300)
            wide = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            self.assertLessEqual(wide, 1)
            small = page.evaluate("""() => [...document.querySelectorAll('#v2Overrides button, #v2Overrides input')].filter(e => e.offsetParent && e.type !== 'checkbox')
              .map(e => [e.id || e.dataset.preset || e.className, Math.round(e.getBoundingClientRect().height)]).filter(([, h]) => h < 30)""")
            self.assertEqual(small, [])
            page.click('[data-preset="single:cbs"]')
            page.wait_for_timeout(300)
            self.assertLessEqual(page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth"), 1)
            self.assertEqual(s.errors, [])

    def test_compare_layout_is_unchanged_at_1366x768_with_the_indicator_showing(self):
        """The indicator lives in the league row, so Compare's verdict and sides sit exactly where they did
        (the layout guard itself, tests/test_v2_waterfall_render.py, runs on the default)."""
        with Session(viewport=(1366, 768)) as s:
            page = s.open("#value-overrides")
            a, b = top_player(page, "RB", 2), top_player(page, "WR", 2)
            url = s.base + f"/v2/#compare-trade?give={a['key']},{b['key']}&get={top_player(page, 'QB', 3)['key']}"
            # What the indicator could move is everything above the trade: measure where the Compare page starts.
            measure = """() => ({start: Math.round(document.querySelector('#v2Compare').getBoundingClientRect().top),
                league: Math.round(document.querySelector('#v2Context').getBoundingClientRect().height),
                chip: document.querySelector('#v2OvBar') && !document.querySelector('#v2OvBar').hidden})"""
            page.goto(url, wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            page.wait_for_timeout(600)
            plain = page.evaluate(measure)
            self.assertFalse(plain["chip"])
            page.evaluate("() => window.TradeValueCurveControls.setBasis({mode: 'single', source: 'fantasycalc'})")
            page.wait_for_timeout(600)
            shown = page.evaluate(measure)
            self.assertTrue(shown["chip"], "the indicator must be showing for this check")
            for name in ("start", "league"):
                self.assertEqual(plain[name], shown[name], f"{name} moved when the indicator appeared: {plain} vs {shown}")
            self.assertEqual(s.errors, [])


class BrokenPageIsCaught(unittest.TestCase):
    """The rubric must score below 10 on a page whose basis control does nothing."""

    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists() or not (V2 / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_presets_that_do_nothing_fail_the_task_script(self):
        src = (DIST / "v2" / "overrides.js").read_text(encoding="utf-8")
        old = "const result = S.engine.setBasis(engineBasis(), publish !== false);"
        self.assertIn(old, src)
        broken = src.replace(old, "const result = {ok: true};", 1).encode("utf-8")
        with Session(overrides={"v2/overrides.js": broken}) as s:
            page = s.open("#value-overrides")
            star = top_player(page)
            before = ddf_of(page, star["name"])
            page.click('[data-preset="single:fantasycalc"]')
            page.wait_for_timeout(300)
            self.assertAlmostEqual(before, ddf_of(page, star["name"]), places=9,
                                   msg="control: with the engine call removed DDF Value cannot change")

    def test_a_health_check_without_the_notice_is_caught(self):
        src = (DIST / "v2" / "v2.js").read_text(encoding="utf-8")
        old = "basisNote.hidden = !basis || basis.isDefault;"
        self.assertIn(old, src)
        broken = src.replace(old, "basisNote.hidden = true;", 1).encode("utf-8")
        with Session(overrides={"v2/v2.js": broken}) as s:
            page = s.open("#values-auditing/health-check")
            page.evaluate("() => window.TradeValueCurveControls.setBasis({mode: 'single', source: 'fantasycalc'})")
            page.evaluate("() => { location.hash = '#values-auditing/single-source'; location.hash = '#values-auditing/health-check'; }")
            page.wait_for_timeout(600)
            self.assertTrue(page.locator("#v2AuditBasisNote").is_hidden(), "control: the broken page never shows the notice")

    def test_a_page_without_the_indicator_fails_item_7(self):
        src = (DIST / "v2" / "overrides.js").read_text(encoding="utf-8")
        old = 'bar.hidden = !line.length;'
        self.assertIn(old, src)
        broken = src.replace(old, "bar.hidden = true;", 1).encode("utf-8")
        with Session(overrides={"v2/overrides.js": broken}) as s:
            page = s.open("#value-overrides")
            page.click('[data-preset="single:fantasycalc"]')
            page.wait_for_timeout(300)
            self.assertTrue(page.locator("#v2OvBar").is_hidden(), "the broken page hides the indicator, so rubric item 7 cannot score")


if __name__ == "__main__":
    unittest.main()
