"""JEG-1058 and JEG-1059: the kind of an override, and the flag on every value.

JEG-1058: an override is an absolute value ("worth 58.0") or an adjustment
("+5" / "-3") added to the pipeline's own value and capped at the 0-100 value
scale. The Overrides tab has a type toggle next to the value input (absolute by
default); the export file and the share link carry the kind.

JEG-1059: everywhere an overridden player's DDF Value appears, the value carries
a badge whose tooltip is the spec's sentence ("You set this player's value to
58.0 (was 53.0 from DDF Value). Reset on the Overrides tab."), and the player
detail panel says "Your override: 58.0" above the source breakdown, with a note
that the individual source values are unchanged.

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

READY = "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady() && window.TradeValueV2"


def setUpModule():
    _render_env.ensure_built()


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
        self.errors = []
        # One context: a second tab is a second view of the same reader's settings.
        self.context = self.browser.new_context(viewport={"width": self.viewport[0], "height": self.viewport[1]})
        self.page = self.new_page()
        if self.init:
            self.page.add_init_script(self.init)
        return self

    def new_page(self):
        page = self.context.new_page()
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        return page

    def open(self, hash_, page=None):
        page = page or self.page
        page.goto(self.base + "/v2/" + hash_, wait_until="networkidle")
        page.wait_for_function(READY, timeout=90000)
        page.wait_for_timeout(300)
        return page

    def __exit__(self, *exc):
        try:
            self._srv.__exit__(*exc)
        finally:
            try:
                self.context.close()
                self.browser.close()
            finally:
                self._pw.stop()


def top_player(page, pos="WR", rank=5):
    return page.evaluate("""([pos, rank]) => { const rows = window.TradeValueCurveControls.getAllRows().filter(r => r.pos === pos && Number.isFinite(r.values.ddf_value))
      .sort((a, b) => b.values.ddf_value - a.values.ddf_value); return {key: rows[rank].player_key, name: rows[rank].name, value: rows[rank].values.ddf_value}; }""", [pos, rank])


def row_of(page, key):
    return page.evaluate("""(key) => { const r = window.TradeValueCurveControls.getAllRows().find(x => x.player_key === key);
      return r ? {value: r.values.ddf_value, pipeline: r.ddfPipelineValue, override: r.valueOverride, spec: r.valueOverrideSpec} : null; }""", key)


def pick_player(page, name):
    """The reader's way: search the player on the Overrides tab and pick him."""
    page.fill("#v2OvSearch", name)
    page.wait_for_selector("#v2OvResults button")
    page.click("#v2OvResults button")
    page.wait_for_selector("#v2OvNumber")
    chosen = page.inner_text("#v2OvName")
    assert chosen == name, f"picked {chosen!r} instead of {name!r}"


def set_value(page, name, value):
    page.fill("#v2OvNumber", str(value))
    page.press("#v2OvNumber", "Enter")
    page.dispatch_event("#v2OvNumber", "change")
    page.wait_for_timeout(300)


def set_absolute(page, name, value):
    pick_player(page, name)
    page.click('[data-ov-type="absolute"]')
    page.wait_for_timeout(150)
    set_value(page, name, value)


def set_adjustment(page, name, delta):
    """The reader's way: pick him, switch the kind to an adjustment, type the delta."""
    pick_player(page, name)
    page.click('[data-ov-type="adjustment"]')
    page.wait_for_timeout(150)
    set_value(page, name, delta)


class AdjustmentTest(unittest.TestCase):
    """JEG-1058: the type toggle, the adjustment's value, and what travels."""

    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists() or not (V2 / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_the_type_toggle_is_absolute_by_default_and_makes_an_adjustment(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "WR", 3)
            pick_player(page, star["name"])
            self.assertEqual(page.get_attribute('[data-ov-type="absolute"]', "aria-pressed"), "true")
            self.assertEqual(page.get_attribute('[data-ov-type="adjustment"]', "aria-pressed"), "false")
            # An absolute value is what the input says.
            set_value(page, star["name"], round(star["value"] + 3, 1))
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()"),
                             {str(star["key"]): round(star["value"] + 3, 1)})
            # Switching the kind keeps the value and stores it as an adjustment.
            page.click('[data-ov-type="adjustment"]')
            page.wait_for_timeout(300)
            got = page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")
            self.assertEqual(got[str(star["key"])]["type"], "adjustment")
            self.assertAlmostEqual(got[str(star["key"])]["delta"], 3.0, places=6)
            row = row_of(page, star["key"])
            self.assertAlmostEqual(row["value"], star["value"] + 3, places=6)
            self.assertEqual(s.errors, [])

    def test_an_adjustment_adds_to_the_ddf_value_and_is_capped(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "WR", 3)
            set_adjustment(page, star["name"], 5)
            row = row_of(page, star["key"])
            self.assertAlmostEqual(row["value"], star["value"] + 5, places=6)
            self.assertAlmostEqual(row["pipeline"], star["value"], places=6)
            self.assertEqual(row["spec"], {"type": "adjustment", "delta": 5})
            # A negative delta takes off.
            set_adjustment(page, star["name"], -3)
            self.assertAlmostEqual(row_of(page, star["key"])["value"], star["value"] - 3, places=6)
            # The value scale is 0-100: an adjustment past either end is capped.
            set_adjustment(page, star["name"], 500)
            self.assertAlmostEqual(row_of(page, star["key"])["value"], 100.0, places=6)
            set_adjustment(page, star["name"], -500)
            self.assertAlmostEqual(row_of(page, star["key"])["value"], 0.0, places=6)
            self.assertEqual(s.errors, [])

    def test_an_adjustment_is_saved_and_survives_a_reload(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "RB", 4)
            set_adjustment(page, star["name"], 2)
            saved = json.loads(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"))
            self.assertEqual(saved["v"], 2)
            self.assertEqual(saved["values"][str(star["key"])], {"type": "adjustment", "delta": 2})
            page.reload(wait_until="networkidle")
            page.wait_for_function(READY, timeout=90000)
            page.wait_for_timeout(400)
            row = row_of(page, star["key"])
            self.assertAlmostEqual(row["value"], star["value"] + 2, places=6)
            self.assertEqual(s.errors, [])

    def test_the_share_link_carries_the_adjustment(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "RB", 4)
            set_adjustment(page, star["name"], 5)
            params = page.evaluate("() => window.DDFOverrides.shareParams()")
            self.assertEqual(params["ov"], f"{star['key']}:+5")

    def test_a_link_with_an_adjustment_reaches_the_reader(self):
        """The reader's side: a link that says ov=key:+5 is an adjustment, not
        an absolute value."""
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "RB", 4)
            other = top_player(page, "QB", 2)
        with Session() as r:
            page = r.open(f"#compare-trade?give={star['key']}&get={other['key']}&ov={star['key']}:+5")
            got = page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")
            self.assertEqual(got.get(str(star["key"])), {"type": "adjustment", "delta": 5})
            self.assertIn("1 player override", page.inner_text("#v2OvLinkBanner"))
            # The link's settings are the reader's for this visit only.
            self.assertIsNone(page.evaluate("() => localStorage.getItem('ddf-v2-value-overrides')"))
            self.assertEqual(r.errors, [])

    def test_an_override_from_a_link_is_capped_at_the_scale(self):
        """A link that carries a value off the scale is put on the scale: the
        reader sees 100.0, and an adjustment travels inside the scale's span so
        a packed link can still carry it."""
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "RB", 4)
        with Session() as r:
            page = r.open(f"#compare-trade?ov={star['key']}:120")
            got = page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")
            self.assertEqual(got.get(str(star["key"])), 100)
            self.assertAlmostEqual(row_of(page, star["key"])["value"], 100.0, places=6)
            # The link the reader would pass on carries the capped value.
            self.assertEqual(page.evaluate("() => window.DDFOverrides.shareParams()")["ov"], f"{star['key']}:100")
            # An adjustment past the scale is capped to its span.
            page2 = r.open(f"#compare-trade?ov={star['key']}:+5000", page=r.new_page())
            got2 = page2.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")
            self.assertEqual(got2.get(str(star["key"])), {"type": "adjustment", "delta": 100})
            self.assertEqual(page2.evaluate("() => window.DDFOverrides.shareParams()")["ov"], f"{star['key']}:+100")
            self.assertEqual(r.errors, [])

    def test_an_override_from_an_import_is_capped_at_the_scale(self):
        """An imported file is put on the scale too."""
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "RB", 4)
            qb = top_player(page, "QB", 2)
        doc = {"v": 2, "basis": None, "overrides": [
            {"player_key": str(star["key"]), "type": "absolute", "value": 120, "name": star["name"]},
            {"player_key": str(qb["key"]), "type": "adjustment", "delta": 5000, "name": qb["name"]}]}
        path = ROOT / "dist" / "_ov-scale-import.json"
        path.write_text(json.dumps(doc))
        try:
            with Session() as r:
                page = r.open("#value-overrides")
                with page.expect_file_chooser() as chooser:
                    page.click("#v2OvImport")
                chooser.value.set_files(files=[str(path)])
                page.wait_for_selector("#v2OvImportNote")
                got = page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")
                self.assertEqual(got.get(str(star["key"])), 100)
                self.assertEqual(got.get(str(doc["overrides"][1]["player_key"])), {"type": "adjustment", "delta": 100})
                self.assertAlmostEqual(row_of(page, star["key"])["value"], 100.0, places=6)
                self.assertEqual(r.errors, [])
        finally:
            path.unlink(missing_ok=True)

    def test_export_and_import_carry_the_adjustment(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "RB", 4)
            set_adjustment(page, star["name"], 5)
            with page.expect_download() as dl:
                page.click("#v2OvExport")
            exported = json.loads(Path(dl.value.path()).read_text())
            entry = exported["overrides"][0]
            self.assertEqual(entry["player_key"], str(star["key"]))
            self.assertEqual(entry["type"], "adjustment")
            self.assertEqual(entry["delta"], 5)
            path = ROOT / "dist" / "_ov-adjustments-export.json"
            path.write_text(json.dumps(exported))
        try:
            # Import it into a fresh visit: nothing is saved there yet.
            with Session() as r:
                page = r.open("#value-overrides")
                with page.expect_file_chooser() as chooser:
                    page.click("#v2OvImport")
                chooser.value.set_files(files=[str(path)])
                page.wait_for_selector("#v2OvImportNote")
                self.assertIn("Imported 1 player override", page.inner_text("#v2OvImportNote"))
                got = page.evaluate("() => window.TradeValueCurveControls.getValueOverrides()")
                self.assertEqual(got.get(str(star["key"])), {"type": "adjustment", "delta": 5})
                row = row_of(page, star["key"])
                self.assertAlmostEqual(row["value"], star["value"] + 5, places=6)
                self.assertEqual(r.errors, [])
        finally:
            path.unlink(missing_ok=True)


class FlagTest(unittest.TestCase):
    """JEG-1059: the badge next to the value the reader set."""

    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists() or not (V2 / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_player_values_carries_the_badge_with_the_spec_tooltip(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "WR", 2)
            set_absolute(page, star["name"], round(star["value"] + 3, 1))
            # A second tab: the override is saved, so it is there on the way in.
            values = s.open("#player-values", page=s.new_page())
            values.wait_for_selector(f'#v2Table tr[data-player-key="{star["key"]}"]', timeout=20000)
            badge = values.evaluate("""(key) => { const td = document.querySelector(`#v2Table tr[data-player-key="${key}"] td[data-source="ddf_value"]`);
              const flag = td && td.querySelector('.v2-ov-flag');
              return flag ? {title: flag.getAttribute('title'), label: flag.getAttribute('aria-label'), text: flag.textContent} : null; }""",
                             star["key"])
            self.assertIsNotNone(badge, "no badge on the overridden player's DDF Value")
            self.assertIn(f"You set this player's value to {round(star['value'] + 3, 1):.1f}", badge["title"])
            self.assertIn(f"(was {star['value']:.1f} from DDF Value)", badge["title"])
            self.assertIn("Reset on the Overrides tab.", badge["title"])
            self.assertEqual(badge["label"], badge["title"])
            self.assertNotEqual(badge["text"], "", "the badge says nothing")
            self.assertEqual(s.errors, [])

    def test_an_adjustment_carries_its_own_badge(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "WR", 2)
            set_adjustment(page, star["name"], 5)
            values = s.open("#player-values", page=s.new_page())
            values.wait_for_selector(f'#v2Table tr[data-player-key="{star["key"]}"]', timeout=20000)
            badge = values.evaluate("""(key) => { const td = document.querySelector(`#v2Table tr[data-player-key="${key}"] td[data-source="ddf_value"]`);
              const flag = td && td.querySelector('.v2-ov-flag');
              return flag ? {title: flag.getAttribute('title'), text: flag.textContent} : null; }""", star["key"])
            self.assertIsNotNone(badge, "no badge on the adjusted player's DDF Value")
            self.assertIn("You set this player's value to", badge["title"])
            self.assertIn("Reset on the Overrides tab.", badge["title"])
            self.assertNotEqual(badge["text"], "", "the badge says nothing")
            self.assertEqual(s.errors, [])

    def test_the_player_detail_panel_says_your_override(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "WR", 2)
            set_absolute(page, star["name"], round(star["value"] + 3, 1))
            values = s.open("#player-values", page=s.new_page())
            values.wait_for_selector(f'#v2Table tr[data-player-key="{star["key"]}"]', timeout=20000)
            values.click(f'#v2Table tr[data-player-key="{star["key"]}"] td.player')
            values.wait_for_selector("#v2Drawer:not([hidden])", timeout=10000)
            drawer = values.inner_text("#v2Drawer")
            self.assertIn(f"Your override: {round(star['value'] + 3, 1):.1f}", drawer)
            self.assertIn("Individual source values are unchanged.", drawer)
            self.assertEqual(s.errors, [])

    def test_the_overrides_list_carries_the_badge(self):
        with Session() as s:
            page = s.open("#value-overrides")
            star = top_player(page, "WR", 2)
            set_absolute(page, star["name"], round(star["value"] + 3, 1))
            page.wait_for_selector("#v2OvList tbody tr", timeout=10000)
            badge = page.evaluate("""(name) => { const rows = [...document.querySelectorAll('#v2OvList tbody tr')];
              const row = rows.find(tr => tr.textContent.includes(name));
              const flag = row && row.querySelector('.v2-ov-flag');
              return flag ? flag.getAttribute('title') : null; }""", star["name"])
            self.assertIsNotNone(badge, "no badge on the Overrides tab list")
            self.assertIn("You set this player's value to", badge)
            self.assertIn("Reset on the Overrides tab.", badge)
            self.assertEqual(s.errors, [])


if __name__ == "__main__":
    unittest.main()
