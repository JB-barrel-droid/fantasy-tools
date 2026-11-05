"""Simplified site section (JEG-1263) in a real browser: every state at 1280, 390 and 320 with no sideways scroll, one
"Simplified site" h1, the route contract (deep link, open a trade, Back), keyboard focus, the fixture label, the gain
text as the dashboard shows it, and no storage writes.

The section is mounted on a small harness page (v2.css, simplified-site.css, opportunities.js, simplified-site.js) with the
synthetic fixture injected, because the menu entry and route hunk in v2.js / shell.html wait on the shell owner's
agreement (JEG-1263). Set SIMPLIFIED_SITE_SHOTS=<dir> to save the screenshots used as PR evidence.
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
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "simplified-site" / "synthetic-answer.json").read_text(encoding="utf-8"))
WIDTHS = (1280, 390, 320)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simplified site (test harness, synthetic data)</title>
<link rel="stylesheet" href="v2.css"><link rel="stylesheet" href="simplified-site.css">
<script src="opportunities.js"></script><script src="simplified-site.js"></script>
</head><body class="v2"><div class="v2-app">
<main id="v2Simplified" aria-labelledby="ssTitle"></main></div>
<script>window.__ssHandle = TradeValueSimplifiedSite.mount(document.getElementById("v2Simplified"), {getContext: () => window.__SS_CTX});</script>
</body></html>
"""

# Counts every storage write the page makes after load.
STORAGE_SPY = """(() => { window.__ssWrites = [];
  for (const name of ["setItem", "removeItem", "clear"]) { const real = Storage.prototype[name];
    Storage.prototype[name] = function (...args) { window.__ssWrites.push([name, args[0]]); return real.apply(this, args); }; } })();"""


def state(name: str) -> dict:
    ctx = copy.deepcopy(FIXTURE)
    if name == "loading":
        return {"status": "loading", "fixture": ctx["fixture"]}
    if name == "error":
        return {"status": "error", "error": "synthetic failure for the test", "fixture": ctx["fixture"]}
    if name == "empty":
        ctx["league"] = None
    elif name == "incomplete":
        ctx["missing"] = [{"key": "context", "text": "Your saved league is not yet carried into this section reliably."}]
    elif name == "weekly":
        ctx["basis"]["horizon"] = "weekly"
    elif name == "none":
        ctx["ideas"]["recommendations"] = []
    return ctx


STATES = {"answer": "answer", "loading": "loading", "error": "error", "empty": "empty", "incomplete": "incomplete",
          "weekly": "incomplete", "none": "none"}


@contextlib.contextmanager
def harness():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("v2.css", "simplified-site.css", "opportunities.js", "simplified-site.js"):
            shutil.copy2(APP / name, Path(tmp) / name)
        (Path(tmp) / "index.html").write_text(PAGE, encoding="utf-8")

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp)) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
            finally:
                server.shutdown()


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


class SimplifiedSiteRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())
        cls.base = cls._stack.enter_context(harness())
        shots = os.environ.get("SIMPLIFIED_SITE_SHOTS", "").strip()
        cls.shots = Path(shots) if shots else None
        if cls.shots:
            cls.shots.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def open(self, ctx, width, hash_="#simplified-site", errors=None, wait=True):
        context = self.chromium.new_context(viewport={"width": width, "height": 900})
        context.add_init_script(STORAGE_SPY)
        context.add_init_script(f"window.__SS_CTX = {json.dumps(ctx)};")
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base + hash_, wait_until="load")
        if wait:
            page.wait_for_selector("#v2Simplified[data-state]")
        return page

    def shot(self, page, name):
        if self.shots:
            page.screenshot(path=str(self.shots / f"{name}.png"), full_page=True)

    def assert_layout(self, page, label):
        fit = page.evaluate("() => ({scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,"
                            " wide: [...document.querySelectorAll('#v2Simplified *')].filter(n => n.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5).map(n => n.className || n.tagName)})")
        self.assertLessEqual(fit["scroll"], fit["width"], f"{label}: sideways scroll {fit}")
        self.assertEqual(fit["wide"], [], f"{label}: elements past the right edge")
        heads = page.evaluate("() => [...document.querySelectorAll('#v2Simplified h1, #v2Simplified h2, #v2Simplified h3')].map(h => [Number(h.tagName[1]), h.textContent.trim()])")
        self.assertEqual([h for h in heads if h[0] == 1], [[1, "Simplified site"]], f"{label}: one h1, the exact name")
        for (prev, _), (level, text) in zip(heads, heads[1:]):
            self.assertLessEqual(level - prev, 1, f"{label}: heading level skipped before {text!r}")
        self.assertTrue(all(text for _, text in heads), f"{label}: empty heading")

    def test_every_state_at_every_width(self):
        for width in WIDTHS:
            for name, want in STATES.items():
                with self.subTest(width=width, state=name):
                    errors = []
                    page = self.open(state(name), width, errors=errors)
                    self.assertEqual(page.get_attribute("#v2Simplified", "data-state"), want)
                    self.assert_layout(page, f"{name}@{width}")
                    self.assertIn("Synthetic example.", page.inner_text(".ss-fixture"))
                    if name != "answer":
                        self.assertEqual(page.locator(".ss-offer, .ss-more").count(), 0, f"{name}: no answer shown")
                    if name in ("answer", "incomplete", "none", "empty"):
                        self.shot(page, f"{name}-{width}")
                    self.assertEqual(errors, [])
                    self.assertEqual(page.evaluate("window.__ssWrites"), [])
                    page.context.close()

    def test_answer_text_matches_dashboard_format(self):
        page = self.open(state("answer"), 1280)
        gains = page.locator(".ss-gain").all_inner_texts()
        # Answer, the two next tries, the stretch offer: opportunities.js fmt / the Trade opportunities capture cell.
        self.assertEqual(gains, ["You gain +4.2 in DDF Value.", "You gain +3.0 in DDF Value.", "You gain +0.1 in DDF Value.", "You gain +6.5 in DDF Value."])
        self.assertEqual(page.inner_text(".ss-offer"), "Offer RB Alpha to Synthetic Team B for WR India.")
        # JEG-1209's November 3 decision: show existing package evidence, never an acceptance prediction.
        self.assertEqual(page.locator(".ss-evidence").all_inner_texts(), ["Their trade-chart package +2.1.",
                         "Their trade-chart package −0.4.", "Their trade-chart package value is unavailable.",
                         "Their trade-chart package −2.2."])
        self.assertEqual(page.locator(".ss-more .ss-rank").all_inner_texts(), ["2.", "3."])
        page.context.close()

    def test_canonical_questions_navigation_and_unknown_at_every_width(self):
        ctx = json.loads(subprocess.check_output(["node", str(ROOT / "tests/simplified_site_harness.cjs"), str(APP),
                                                  "--canonical-fixture"], text=True))
        for width in WIDTHS:
            with self.subTest(width=width):
                errors = []
                page = self.open(ctx, width, errors=errors)
                self.assert_layout(page, f"canonical@{width}")
                self.assertEqual(page.inner_text(".ss-gain"), "Our starter value: +2.0 (DDF Projections).")
                self.assertNotIn("999", page.inner_text("#v2Simplified"), "legacy edge is not canonical starter gain")
                self.assertEqual(page.locator(".ss-questions li").evaluate_all("ns => ns.map(n => n.dataset.questionId)"),
                                 ["our-starters", "our-roster", "their-starters", "their-roster"])
                self.assertIn("not an exhaustive", page.inner_text(".ss-counts"))
                for _ in range(3):
                    page.locator("[data-detail-for]").first.click()
                    page.wait_for_selector("#ssDetailTitle")
                    self.assertEqual(page.evaluate("document.activeElement.id"), "ssDetailTitle")
                    self.assertEqual(page.locator(".ss-questions li").count(), 4)
                    self.assertIn("Canonical decision", page.inner_text(".ss-facts"))
                    self.assert_layout(page, f"canonical detail@{width}")
                    page.go_back()
                    page.wait_for_selector("#v2Simplified[data-view=section]")
                page.evaluate("""() => {const r=window.__SS_CTX.ideas.recommendations[0];
                  r.record.questions[2]={...r.record.questions[2],status:'unknown',value:null,pass:null};
                  r.record.label='Not judged';window.__ssHandle.update(false);}""")
                self.assertIn("Unavailable", page.inner_text('[data-question-id="their-starters"]'))
                self.assertIn("Unknown", page.inner_text('[data-question-id="their-starters"]'))
                self.assertIn("0.0", page.inner_text(".ss-evidence"), "known package zero survives unknown starter result")
                self.assertEqual(page.evaluate("window.__ssWrites"), [])
                self.assertEqual(errors, [])
                page.context.close()

    def test_deep_link_open_and_back_with_focus(self):
        first = FIXTURE["ideas"]["recommendations"][0]
        second = FIXTURE["ideas"]["recommendations"][1]
        for width in WIDTHS:
            with self.subTest(width=width):
                page = self.open(state("answer"), width)
                self.assertEqual(page.evaluate("document.activeElement.id"), "ssTitle", "entering the section focuses its title")
                # Keyboard: Tab to the answer's detail link, Enter opens the trade.
                for _ in range(10):
                    page.keyboard.press("Tab")
                    if page.evaluate("document.activeElement.dataset.detailFor || ''") == first["id"]:
                        break
                self.assertEqual(page.evaluate("document.activeElement.dataset.detailFor"), first["id"])
                page.keyboard.press("Enter")
                page.wait_for_selector("#ssDetailTitle")
                self.assertEqual(page.evaluate("location.hash"), "#simplified-site/trade/" + quote(first["id"], safe=""))
                self.assertEqual(page.evaluate("document.activeElement.id"), "ssDetailTitle")
                self.assertEqual(page.get_attribute("#v2Simplified", "data-view"), "detail")
                detail = page.inner_text(".ss-detail")
                self.assertIn("Trade chart average (published)", detail)
                self.assertIn("not a prediction", detail)
                self.assert_layout(page, f"detail@{width}")
                self.shot(page, f"detail-{width}")
                page.go_back()
                page.wait_for_selector("#v2Simplified[data-view=section]")
                self.assertEqual(page.evaluate("location.hash"), "#simplified-site")
                self.assertEqual(page.evaluate("document.activeElement.dataset.detailFor"), first["id"], "Back returns focus to the trade's link")
                page.context.close()
                # A fresh visit to a trade's address opens it directly; its Back link returns to the answer.
                page = self.open(state("answer"), width, hash_="#simplified-site/trade/" + quote(second["id"], safe=""))
                self.assertEqual(page.get_attribute("#v2Simplified", "data-view"), "detail")
                self.assertEqual(page.inner_text("#ssDetailTitle"), "Offer WR Bravo + TE Delta to Synthetic Team C for RB Golf.")
                self.assertEqual(page.evaluate("document.activeElement.id"), "ssDetailTitle")
                self.assertIn("fell back to the trade charts (nothing marked)", page.inner_text(".ss-detail"))
                page.click(".ss-back")
                page.wait_for_selector("#v2Simplified[data-view=section]")
                self.assertEqual(page.evaluate("document.activeElement.dataset.detailFor"), second["id"])
                self.assertEqual(page.evaluate("window.__ssWrites"), [])
                page.context.close()

    def test_unknown_or_withheld_deep_link(self):
        page = self.open(state("answer"), 390, hash_="#simplified-site/trade/" + quote("t9|nobody|nothing", safe=""))
        self.assertEqual(page.get_attribute("#v2Simplified", "data-view"), "section")
        self.assertIn("no longer in the list", page.inner_text(".ss-gone"))
        self.assertEqual(page.inner_text(".ss-offer"), "Offer RB Alpha to Synthetic Team B for WR India.")
        page.context.close()
        first = FIXTURE["ideas"]["recommendations"][0]
        page = self.open(state("incomplete"), 390, hash_="#simplified-site/trade/" + quote(first["id"], safe=""))
        self.assertEqual(page.get_attribute("#v2Simplified", "data-state"), "incomplete")
        self.assertEqual(page.locator(".ss-detail, .ss-offer").count(), 0, "a deep link cannot open a withheld answer")
        page.context.close()

    def test_refresh_keeps_focus_and_never_leaves_a_stale_answer(self):
        """JEG-1301: a refresh that re-renders keeps focus on the same link (or the title when that trade is gone), and a
        context that throws or comes back malformed replaces the old answer instead of leaving it on screen."""
        second = FIXTURE["ideas"]["recommendations"][1]
        page = self.open(state("answer"), 390)
        page.focus(f'.ss-more [data-detail-for="{second["id"]}"]')
        page.evaluate("window.__ssHandle.update(false)")
        self.assertEqual(page.evaluate("document.activeElement.dataset.detailFor || document.activeElement.tagName"), second["id"],
                         "a refresh keeps focus on the same trade's link")
        page.evaluate("([id]) => { window.__SS_CTX.ideas.recommendations = window.__SS_CTX.ideas.recommendations.filter(r => r.id !== id);"
                      " window.__ssHandle.update(false); }", [second["id"]])
        self.assertEqual(page.evaluate("document.activeElement.id"), "ssTitle", "focus goes to the title when the focused trade is gone")
        page.evaluate("window.__SS_CTX = {...window.__SS_CTX, ideas: {recommendations: 'oops'}}; window.__ssHandle.update(false)")
        self.assertEqual(page.get_attribute("#v2Simplified", "data-state"), "incomplete", "a malformed ideas object withholds")
        self.assertEqual(page.locator(".ss-offer, .ss-more").count(), 0, "the old answer is not left on screen")
        page.evaluate("Object.defineProperty(window, '__SS_CTX', {get() { throw new Error('synthetic adapter failure'); }, configurable: true});"
                      " window.__ssHandle.update(false)")
        self.assertEqual(page.get_attribute("#v2Simplified", "data-state"), "error", "a throwing context shows the error state")
        self.assertEqual(page.locator(".ss-offer, .ss-more").count(), 0)
        page.context.close()

    def test_activate_reads_live_context_once_mounted(self):
        """activate() mounts once, cannot bypass missing contracts with rollout flags, and re-reads the saved team."""
        page = self.open(state("answer"), 390, hash_="#find-league", wait=False)
        result = page.evaluate("""([ideas]) => {
          const box = document.createElement('main'); document.body.append(box);
          const writes = [];
          const ws = {name: 'Synthetic League', myTeamId: 'a', teams: [{id: 'a', name: 'Synthetic Team A', entries: []}]};
          window.TradeValueWorkspace = {store: {get: () => ws, replace: () => writes.push('replace')}};
          window.TradeValueTradeIdeas = {compute: () => ideas};
          const S = window.TradeValueSimplifiedSite;
          location.hash = '#simplified-site';
          return new Promise(resolve => setTimeout(() => {
            const a = S.activate(box);
            const closed = box.dataset.state;
            window.TradeValueSimplifiedGates = {context: true, readout: true, lineup: true};
            const b = S.activate(box);
            const flagged = box.dataset.state;
            ws.myTeamId = null;
            S.activate(box);
            resolve({same: a === b, closed, flagged, open: box.dataset.state, h1: box.querySelectorAll('h1').length, writes,
              fixture: box.querySelectorAll('.ss-fixture').length});
          }, 0));
        }""", [FIXTURE["ideas"]])
        self.assertTrue(result["same"], "mounted once")
        self.assertEqual(result["closed"], "incomplete", "gates closed: withheld")
        self.assertEqual(result["flagged"], "incomplete", "flags cannot replace shared contracts")
        self.assertEqual(result["open"], "empty", "later call re-reads the starred saved team")
        self.assertEqual(result["h1"], 1)
        self.assertEqual(result["fixture"], 0, "a live context is not labelled as a fixture")
        self.assertEqual(result["writes"], [])
        page.context.close()

    def test_completed_contracts_on_loaded_dashboard_without_ideas_provider(self):
        """Real built dashboard + historical USO rosters: prerequisites work before #1084, without a fake answer."""
        from tests._league_render import open_page
        from tests.test_v2_finder_render import _built_dist
        from tests.test_jeg1249_league_site_render import PASTED, SAVED, SEED, settle, uso
        from tests.test_jeg1389_link_settings_reload_render import USO_QUERY

        fx = uso()
        with _built_dist() as base:
            problems = []
            page = open_page(self.chromium, base, errors=problems)
            page.evaluate("q => TradeValueV2.applyLinkLeague(new URLSearchParams(q), {save: true})", USO_QUERY)
            settle(page)
            page.evaluate(SEED, [fx["league"]["teams"], fx["mine"], PASTED, {}, {}])
            settle(page)
            # Source on this PR has no #1084 provider. Do not stub recommendations to turn this into a success claim.
            self.assertFalse(page.evaluate("!!window.TradeValueTradeIdeas"))
            before = page.evaluate(SAVED)
            for league_pricing in (True, False):
                if not league_pricing:
                    page.set_viewport_size({"width": 1280, "height": 900})
                    page.click("#v2LgUseLeague")
                    settle(page)
                    before = page.evaluate(SAVED)
                page.evaluate("location.hash = '#simplified-site'")
                page.wait_for_selector("#v2Simplified[data-state=incomplete]")
                state = page.evaluate("""() => {const c = TradeValueSimplifiedSite.liveContext(window); return {
                  contracts:c.contracts, missing:c.missing.map(m=>m.key), scoring:c.context.common.league.scoring,
                  mine:c.context.teams.mine.id, savedMine:TradeValueWorkspace.store.get().myTeamId};}""")
                self.assertEqual(state["contracts"], {"context": True, "readout": True, "lineup": True})
                self.assertEqual(state["missing"], ["ideas"])
                self.assertEqual(state["scoring"], "half_ppr")
                self.assertEqual(state["mine"], state["savedMine"])
                for width in WIDTHS:
                    page.set_viewport_size({"width": width, "height": 900})
                    self.assert_layout(page, f"loaded USO, league pricing {league_pricing}@{width}")
                self.assertEqual(page.evaluate(SAVED), before, "Simplified must not write the saved league")
                self.assertEqual(page.locator(".ss-offer").count(), 0, "missing provider must not fabricate an answer")
                page.evaluate("location.hash = '#find-league'")
            # On the standard bench, the completed page's engine rows are its pricing rows. Check the shared readout
            # adapter on an actual trade, without simulating the missing recommendation provider.
            settle(page)
            readout = page.evaluate("""() => {
              const S=TradeValueSimplifiedSite, ws=TradeValueWorkspace.store.get(), state=S.liveContracts(window,ws);
              const result=TradeValueLeague.ui.result, rec=result.rows[0];
              if(!rec) return {missingTrade:true};
              const snapshot={...result,pricingRows:TradeValueCurveControls.getAllRows()};
              const got=S.readoutFor(window,state.context,rec,snapshot,state.shape);
              const missing=S.readoutFor(window,state.context,rec,{...snapshot,
                pricingRows:snapshot.pricingRows.filter(r=>String(r.player_key)!==String(rec.receive[0].player_key))},state.shape);
              return {ready:got.ready,mine:got.roster.mine,theirs:got.roster.theirs,
                missingReady:missing.ready,missingKeys:missing.outside.receive,receive:String(rec.receive[0].player_key)};
            }""")
            self.assertNotIn("missingTrade", readout)
            self.assertTrue(readout["ready"])
            self.assertFalse(readout["missingReady"])
            self.assertIn(readout["receive"], readout["missingKeys"])
            for side in ("mine", "theirs"):
                self.assertEqual(readout[side]["after"]["size"] - readout[side]["before"]["size"], readout[side]["rosterSizeDelta"])
            self.assertEqual(page.evaluate(SAVED), before)
            page.evaluate("location.hash = '#simplified-site'")
            page.wait_for_selector("#v2Simplified[data-state=incomplete]")
            # Change the source workspace, not the Simplified view: its subscription must redraw without a route change
            # or a manual activate() call, and must leave the new source snapshot untouched.
            page.evaluate("TradeValueWorkspace.store.update(w => ({...w, myTeamId: null}), 'test:star-cleared')")
            changed = page.evaluate(SAVED)
            page.wait_for_selector("#v2Simplified[data-state=empty]")
            self.assertEqual(page.evaluate(SAVED), changed)
            self.assertEqual(problems, [])
            page.context.close()


if __name__ == "__main__":
    unittest.main()
