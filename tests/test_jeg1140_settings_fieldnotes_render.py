"""Settings in the Fieldnotes design (JEG-1140) in a real browser.

Two pages:

1. HARNESS. The component on a private page (v2.css with the JEG-1137 Fieldnotes layer, settings-fieldnotes.css and
   .js) with a fixture context and recording actions. That adapter is test scaffolding, not the live hookup. Every state
   at 1280, 390 and 320 (and dark at 390): no sideways scroll, one h1, 44px targets, named controls, Unavailable for
   missing values. Keyboard: Tab reaches every action, Enter and Space run them, focus stays on the control used, the
   one status region is never replaced, a disclosure stays open and focused across a redraw, the section links move
   focus. The component writes no storage.
2. BUILT PAGE. The built dashboard (dist/v2, ?design=fieldnotes) with the component mounted on liveAdapter, which only
   presses the existing controls. Export, Import and Copy link go through the league card's own handlers, and the
   overrides Export and Import through the Overrides tab's, so the files and links are the unchanged formats. The
   fixture league and overrides round-trip by file, and the copied link reopens the same rosters and overrides in a
   fresh browser.

Set SETTINGS_FIELDNOTES_SHOTS=<dir> to save the screenshots used as PR evidence. Skips when no browser is available,
unless RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import contextlib
import copy
import functools
import http.server
import json
import os
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
FIX = ROOT / "tests" / "fixtures" / "settings-fieldnotes"
CONTEXTS = json.loads((FIX / "contexts.json").read_text(encoding="utf-8"))
LEAGUE = json.loads((FIX / "league.json").read_text(encoding="utf-8"))
OVERRIDES = json.loads((FIX / "overrides.json").read_text(encoding="utf-8"))
WIDTHS = (1280, 390, 320)
READY = "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady() && window.TradeValueV2 && window.TradeValueLeague"

PAGE = """<!doctype html>
<html lang="en" data-design="fieldnotes"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Settings Fieldnotes view (test harness, synthetic data)</title>
<link rel="stylesheet" href="v2.css"><link rel="stylesheet" href="settings-fieldnotes.css">
<script src="settings-fieldnotes.js"></script>
</head><body class="v2"><div class="v2-app"><main id="sfRoot"></main></div>
<script>
// Fixture adapter (test scaffolding only): a fixed context and actions that record their calls.
(() => {
  window.__sfCalls = [];
  const reply = {exportLeague: "Downloaded synthetic-test-league.json.", importLeague: "Synthetic test league: 2 teams loaded.",
    copyLink: "Copied a link to the whole league and its settings.", exportOverrides: "Downloaded ddf-overrides.json.",
    importOverrides: "Imported 2 player overrides.", openLeague: "", openOverrides: ""};
  const actions = Object.fromEntries(Object.entries(reply).map(([id, message]) => [id, () => {
    window.__sfCalls.push(id);
    return id === "copyLink" ? new Promise(r => setTimeout(() => r({ok: true, message}), 30)) : {ok: true, message};
  }]));
  window.__sfHandle = TradeValueSettingsFieldnotes.mount(document.getElementById("sfRoot"), {getContext: () => window.__SF_CTX, actions});
})();
</script>
</body></html>
"""

# Counts every storage write the page makes after load.
STORAGE_SPY = """(() => { window.__sfWrites = [];
  for (const name of ["setItem", "removeItem", "clear"]) { const real = Storage.prototype[name];
    Storage.prototype[name] = function (...args) { window.__sfWrites.push([name, args[0]]); return real.apply(this, args); }; } })();"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@contextlib.contextmanager
def serve(directory: Path):
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory))) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()


@contextlib.contextmanager
def harness():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("v2.css", "settings-fieldnotes.css", "settings-fieldnotes.js"):
            shutil.copy2(APP / name, Path(tmp) / name)
        shutil.copytree(APP / "fonts", Path(tmp) / "fonts")
        (Path(tmp) / "index.html").write_text(PAGE, encoding="utf-8")
        with serve(Path(tmp)) as base:
            yield base + "/index.html"


@contextlib.contextmanager
def browser():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            yield chromium
        finally:
            chromium.close()


class Shots:
    def __init__(self):
        shots = os.environ.get("SETTINGS_FIELDNOTES_SHOTS", "").strip()
        self.dir = Path(shots) if shots else None
        if self.dir:
            self.dir.mkdir(parents=True, exist_ok=True)

    def take(self, page, name):
        if self.dir:
            page.screenshot(path=str(self.dir / f"{name}.png"), full_page=True)


class SettingsHarnessRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())
        cls.base = cls._stack.enter_context(harness())
        cls.shots = Shots()

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def open(self, ctx, width, dark=False):
        context = self.chromium.new_context(viewport={"width": width, "height": 900}, color_scheme="dark" if dark else "light")
        context.add_init_script(STORAGE_SPY)
        context.add_init_script(f"window.__SF_CTX = {json.dumps(ctx)};")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base, wait_until="load")
        page.wait_for_selector(".ddf-fn-settings-body[data-state]")
        self.addCleanup(context.close)
        self.addCleanup(lambda: self.assertEqual(errors, [], "page errors"))
        return page

    def assert_layout(self, page, label):
        fit = page.evaluate("""() => ({scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,
          wide: [...document.querySelectorAll('#sfRoot *')].filter(n => n.offsetParent !== null
            && n.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5).map(n => n.className || n.tagName)})""")
        self.assertLessEqual(fit["scroll"], fit["width"], f"{label}: sideways page scroll {fit}")
        self.assertEqual(fit["wide"], [], f"{label}: elements past the right edge")
        h1 = page.evaluate("() => [...document.querySelectorAll('#sfRoot h1')].map(h => h.textContent.trim())")
        self.assertEqual(h1, ["Your league. Your context."], f"{label}: one h1")
        small = page.evaluate("""() => [...document.querySelectorAll('#sfRoot button, #sfRoot summary')].filter(n => n.offsetParent !== null)
          .map(n => [n.textContent.trim(), n.getBoundingClientRect().height, n.getBoundingClientRect().width])
          .filter(([, h, w]) => h < 44 || w < 44)""")
        self.assertEqual(small, [], f"{label}: targets under 44px")
        unnamed = page.evaluate("""() => [...document.querySelectorAll('#sfRoot button, #sfRoot summary')].filter(n => n.offsetParent !== null)
          .filter(n => !(n.getAttribute('aria-label') || n.textContent.trim())).map(n => n.outerHTML.slice(0, 80))""")
        self.assertEqual(unnamed, [], f"{label}: controls without a name")
        mismatch = page.evaluate("""() => [...document.querySelectorAll('#sfRoot button[aria-label]')]
          .filter(n => !n.getAttribute('aria-label').includes(n.textContent.trim())).map(n => n.outerHTML.slice(0, 80))""")
        self.assertEqual(mismatch, [], f"{label}: accessible name does not contain the visible label")

    def test_every_state_at_every_width(self):
        for name, ctx in CONTEXTS.items():
            for width in WIDTHS:
                with self.subTest(state=name, width=width):
                    page = self.open(ctx, width)
                    self.assert_layout(page, f"{name}@{width}")
                    text = page.inner_text("#sfRoot")
                    self.assertNotIn("0 teams", text)
                    self.assertNotIn("NaN", text)
                    self.assertNotIn("undefined", text)
                    if name in ("missing", "unavailable"):
                        self.assertIn("Unavailable", text)
                    nav = page.is_visible(".ddf-fn-settings-nav") if ctx["status"] == "ready" else None
                    if nav is not None:
                        self.assertEqual(nav, width >= 900, f"{name}@{width}: section links show on desktop only")
                    self.assertEqual(page.evaluate("window.__sfWrites"), [], "the component wrote storage")
                    self.shots.take(page, f"settings-{name}-{width}")
        for name in ("ready", "empty", "unavailable"):
            page = self.open(CONTEXTS[name], 390, dark=True)
            self.assert_layout(page, f"{name}@390 dark")
            self.shots.take(page, f"settings-{name}-390-dark")

    def test_empty_league_disables_export_and_link_with_a_reason(self):
        page = self.open(CONTEXTS["empty"], 390)
        state = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('[data-action]')]
          .map(b => [b.dataset.action, b.disabled]))""")
        self.assertEqual(state, {"exportLeague": True, "importLeague": False, "copyLink": True, "openLeague": False,
                                 "openOverrides": False, "exportOverrides": True, "importOverrides": False})
        self.assertIn("nothing to export or link", page.inner_text("[data-reason=no-league]"))

    def test_keyboard_runs_actions_and_keeps_focus_and_the_status_region(self):
        page = self.open(CONTEXTS["ready"], 390)
        page.evaluate("window.__sfStatus = document.getElementById('ddfSetStatus')")
        order = []
        page.keyboard.press("Tab")
        for _ in range(30):
            order.append(page.evaluate("() => { const a = document.activeElement; return a.dataset.action || a.dataset.scroll"
                                       " || (a.tagName === 'SUMMARY' ? 'summary:' + a.parentElement.dataset.disclosure : a.tagName); }"))
            page.keyboard.press("Tab")
        for action in ("exportLeague", "importLeague", "copyLink", "openLeague", "openOverrides", "exportOverrides", "importOverrides"):
            self.assertIn(action, order, f"Tab never reaches {action}")
        for d in ("ddf-value", "ddf-projections", "combined", "sources"):
            self.assertIn(f"summary:{d}", order)
        self.assertLess(order.index("exportLeague"), order.index("importLeague"))
        self.assertLess(order.index("importLeague"), order.index("copyLink"))

        page.focus("[data-action=exportLeague]")
        page.keyboard.press("Enter")
        page.wait_for_function("document.getElementById('ddfSetStatus').textContent.includes('Downloaded')")
        self.assertEqual(page.evaluate("document.activeElement.dataset.action"), "exportLeague")
        page.focus("[data-action=copyLink]")
        page.keyboard.press(" ")
        page.wait_for_function("document.getElementById('ddfSetStatus').textContent.includes('Copied')")
        self.assertEqual(page.evaluate("document.activeElement.dataset.action"), "copyLink")
        self.assertTrue(page.evaluate("window.__sfStatus === document.getElementById('ddfSetStatus') && window.__sfStatus.isConnected"),
                        "the status region was replaced")
        self.assertEqual(page.evaluate("window.__sfCalls"), ["exportLeague", "copyLink"])
        self.assertEqual(page.get_attribute("#ddfSetStatus", "role"), "status")

        # A disclosure opened by keyboard stays open and focused across a redraw.
        page.focus("[data-disclosure=sources] > summary")
        page.keyboard.press("Enter")
        page.evaluate("window.__sfHandle.update()")
        self.assertTrue(page.evaluate("document.querySelector('[data-disclosure=sources]').open"))
        self.assertEqual(page.evaluate("document.activeElement.parentElement.dataset.disclosure"), "sources")
        self.assertIn("Observed-trade estimates", page.inner_text("[data-disclosure=sources]"))
        self.shots.take(page, "settings-ready-390-after-keyboard")

    def test_section_links_move_focus_on_desktop(self):
        page = self.open(CONTEXTS["ready"], 1280)
        page.focus("[data-scroll=overrides]")
        page.keyboard.press("Enter")
        self.assertEqual(page.evaluate("document.activeElement.id"), "ddfSet-overrides-title")
        self.assertEqual(page.evaluate("location.hash"), "", "a section link must not change the route")


class SettingsLivePageRenderTest(unittest.TestCase):
    """The component on liveAdapter in the built dashboard."""

    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())   # first, so no browser skips before the build
        try:
            _render_env.ensure_built()
        except Exception:
            cls._stack.close()
            raise
        dist = ROOT / "dist"
        if not (dist / "v2" / "index.html").exists():
            cls._stack.close()
            raise _render_env.unavailable("dist/v2 is not built")
        cls.base = cls._stack.enter_context(serve(dist))
        cls.tmp = Path(cls._stack.enter_context(tempfile.TemporaryDirectory()))
        cls.shots = Shots()
        (cls.tmp / "league.json").write_text(json.dumps(LEAGUE), encoding="utf-8")
        (cls.tmp / "overrides.json").write_text(json.dumps(OVERRIDES), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def page(self, hash_="#find-league"):
        context = self.chromium.new_context(viewport={"width": 390, "height": 900}, accept_downloads=True)
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.base)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{self.base}/v2/?design=fieldnotes{hash_}", wait_until="networkidle")
        page.wait_for_function(READY, timeout=90000)
        page.wait_for_selector("#v2LgDownload", state="attached", timeout=30000)
        page.add_style_tag(content=(APP / "settings-fieldnotes.css").read_text(encoding="utf-8"))
        page.add_script_tag(content=(APP / "settings-fieldnotes.js").read_text(encoding="utf-8"))
        page.evaluate("""() => { const host = document.createElement('div'); host.id = 'sfLive';
          host.style.cssText = 'position:fixed;inset:0;overflow:auto;z-index:99999;background:var(--ddf-canvas)';
          document.body.append(host); const a = TradeValueSettingsFieldnotes.liveAdapter(window);
          window.__sfLive = TradeValueSettingsFieldnotes.mount(host, a); window.__sfAdapter = a; }""")
        self.addCleanup(context.close)
        self.addCleanup(lambda: self.assertEqual([e for e in errors if "ResizeObserver" not in e], [], "page errors"))
        return page

    def press(self, page, action, chooser_file=None, download=False):
        if chooser_file:
            with page.expect_file_chooser() as fc:
                page.click(f"#sfLive [data-action={action}]")
            fc.value.set_files(str(chooser_file))
        elif download:
            with page.expect_download() as dl:
                page.click(f"#sfLive [data-action={action}]")
            path = self.tmp / f"{action}-{id(page)}.json"
            dl.value.save_as(str(path))
            return json.loads(path.read_text(encoding="utf-8"))
        else:
            page.click(f"#sfLive [data-action={action}]")
        return None

    def status(self, page, contains):
        page.wait_for_function("(t) => document.getElementById('ddfSetStatus').textContent.includes(t)", arg=contains, timeout=30000)
        return page.inner_text("#ddfSetStatus")

    def league_state(self, page):
        return page.evaluate("""() => { const ws = TradeValueWorkspace.store.get(); const mine = ws.teams.find(t => t.id === ws.myTeamId);
          return {mine: mine ? mine.name : null, teams: Object.fromEntries(ws.teams.map(t => [t.name, t.entries.map(e => e.key)]))}; }""")

    def overrides_state(self, page):
        return page.evaluate("() => ({count: DDFOverrides.count(), all: DDFOverrides.all(), basis: DDFOverrides.basis().mode})")

    def test_round_trips_by_file_and_link(self):
        page = self.page()
        self.assertEqual(page.inner_text("#sfLive [data-row=saved-league] .ddf-fn-settings-value"), "No league saved yet")
        # Import through Settings goes through the league card's own Load: an empty league loads at once.
        self.press(page, "importLeague", chooser_file=self.tmp / "league.json")
        self.status(page, "loaded")
        page.evaluate("window.__sfLive.update()")
        want = {t["name"]: [e["key"] for e in t["entries"]] for t in LEAGUE["teams"]}
        self.assertEqual(self.league_state(page), {"mine": "Paper Lions", "teams": want})
        self.assertIn("Synthetic test league · 2 teams", page.inner_text("#sfLive [data-row=saved-league]"))
        self.assertNotEqual(page.inner_text("#sfLive [data-row=rules] .ddf-fn-settings-value"), "Unavailable")

        self.press(page, "importOverrides", chooser_file=self.tmp / "overrides.json")
        self.assertIn("Imported 2 player overrides", self.status(page, "Imported"))
        page.evaluate("window.__sfLive.update()")
        self.assertEqual(page.inner_text("#sfLive [data-count=overrides]"), "2 player overrides saved on this device.")
        ov = self.overrides_state(page)
        self.assertEqual(ov["count"], 2)
        self.shots.take(page, "settings-live-390")

        # Export through Settings is the league card's own Download and the Overrides tab's own Export.
        league_file = self.press(page, "exportLeague", download=True)
        self.status(page, "Downloaded")
        self.assertEqual({t["name"]: [e["key"] for e in t["entries"]] for t in league_file["teams"]}, want)
        self.assertEqual(league_file["myTeamId"], next(t["id"] for t in league_file["teams"] if t["name"] == "Paper Lions"))
        self.assertIn("scoring=", league_file["settings"]["query"])
        ov_file = self.press(page, "exportOverrides", download=True)
        pairs = lambda doc: sorted((o["player_key"], o["type"], o.get("value", o.get("delta"))) for o in doc["overrides"])
        self.assertEqual(pairs(ov_file), pairs(OVERRIDES))
        self.assertEqual(ov_file["basis"], {"mode": "default"})

        # Copy link is the league card's own link (rosters, settings, value context).
        self.press(page, "copyLink")
        self.status(page, "Copied")
        link = page.evaluate("navigator.clipboard.readText()")
        self.assertIn("#find-league?workspace=", link)

        # A fresh browser: the exported files load back to the same state, and so does the link.
        fresh = self.page()
        self.press(fresh, "importLeague", chooser_file=self.tmp / f"exportLeague-{id(page)}.json")
        self.status(fresh, "loaded")
        self.assertEqual(self.league_state(fresh), {"mine": "Paper Lions", "teams": want})
        self.press(fresh, "importOverrides", chooser_file=self.tmp / f"exportOverrides-{id(page)}.json")
        self.status(fresh, "Imported")
        self.assertEqual(self.overrides_state(fresh), ov)

        opened = self.page(link[link.index("#"):])
        opened.wait_for_function("TradeValueWorkspace.store.get().teams.length === 2", timeout=30000)
        got = self.league_state(opened)
        self.assertEqual(got["mine"], "Paper Lions")
        for name, keys in want.items():
            # The page keeps the players it prices; the kicker travels by its exact identity.
            self.assertEqual([k for k in got["teams"][name]], [k for k in keys if k in got["teams"][name]])
            self.assertGreaterEqual(len(got["teams"][name]), len(keys) - 1)
        self.assertEqual(self.overrides_state(opened)["all"], ov["all"])

    def test_open_actions_use_the_existing_routes(self):
        page = self.page("#player-values")
        self.press(page, "openLeague")
        self.assertEqual(page.evaluate("location.hash"), "#find-league")
        self.press(page, "openOverrides")
        self.assertEqual(page.evaluate("location.hash"), "#value-overrides")


if __name__ == "__main__":
    unittest.main()
