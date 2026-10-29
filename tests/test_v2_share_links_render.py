"""JEG-894: share links, rendered. Copy link to this trade beside the verdict; a finder search link.

Builds dist/v2 into a temp copy of the built dist/ and loads it headless:

  * the "Copy link to this trade" button sits inside the verdict card (desktop) and inside the phone sticky bar;
    copying writes location.href, and a fresh browser context (cleared storage) opens the same give / receive and
    the same verdict title and text;
  * "Copy link to this search" writes a #find-trade link carrying both rosters, the package size and the two lineup
    ticks; a fresh context restores both rosters (names and positions) and shows the same "N trades found";
  * the 1366x768 verdict-fit check still passes with the new button in the verdict header.

Discrimination: test_guard_fails_on_broken_builds serves finder.js / v2.js with a part removed (the encoder drops
`theirs`, the decoder ignores `size`, the link no longer runs the search) and requires the checks to fail.
"""
from __future__ import annotations

import functools
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_finder_render import PICK, _built_dist, add  # noqa: E402
from tests.test_v2_modules_render import _serve  # noqa: E402

FINDER_JS = ROOT / "app" / "v2" / "finder.js"
V2_JS = ROOT / "app" / "v2" / "v2.js"


def setUpModule():
    _render_env.ensure_built()


COUNT = r"""(text) => { const m = /(\d+) trades? found/.exec(text); return m ? Number(m[1]) : null; }"""
FIND_ROSTERS = """() => ({
  mine: [...document.querySelectorAll('#v2FindMinePlayers li')].map(li => (li.querySelector('b') || {}).textContent + ' ' + (li.querySelector('.v2-meta') || {}).textContent.trim()),
  theirs: [...document.querySelectorAll('#v2FindTheirsPlayers li')].map(li => (li.querySelector('b') || {}).textContent + ' ' + (li.querySelector('.v2-meta') || {}).textContent.trim())})"""
VERDICT = """() => ({give: [...document.querySelectorAll('#v2GivePlayers li .v2-trade-name')].map(e => e.textContent),
  get: [...document.querySelectorAll('#v2GetPlayers li .v2-trade-name')].map(e => e.textContent),
  title: document.getElementById('v2CVerdictTitle').textContent, text: document.getElementById('v2CVerdictText').textContent})"""


def run_checks(overrides=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        contexts = []

        def open_page(url, width=1440, height=900):
            # A fresh context per page: cleared storage, so a link is proved to carry everything it needs.
            context = browser.new_context(viewport={"width": width, "height": height})
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base.split("/v2/")[0])
            contexts.append(context)
            page = context.new_page()
            page.errors = []
            page.on("pageerror", lambda e: page.errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            for name, body in (overrides or {}).items():
                page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.getElementById('v2State').hidden", timeout=60000)
            page.wait_for_timeout(200)
            return page

        try:
            # --- the finder search link ---
            sender = open_page(base + "#find-trade")
            sender.wait_for_function("() => Boolean(document.getElementById('v2Find'))", timeout=30000)
            pick = sender.evaluate(PICK)
            for name in pick["mine"]:
                add(sender, "Mine", name)
            for name in pick["theirs"]:
                add(sender, "Theirs", name)
            sender.select_option("#v2FindSize", "3")
            sender.click("#v2FindGo")
            sender.wait_for_function("() => !document.getElementById('v2FindOut').hidden", timeout=60000)
            sender.wait_for_timeout(300)
            sent_count = sender.evaluate(COUNT, sender.inner_text("#v2FindOut"))
            sent_rosters = sender.evaluate(FIND_ROSTERS)
            if not sent_count or not sent_rosters["mine"] or not sent_rosters["theirs"]:
                errors.append(f"the sender page found nothing to share: count {sent_count}")
                return errors
            sender.click("#v2FindShare")
            sender.wait_for_timeout(300)
            if "Link copied" not in sender.inner_text("#v2FindShareNote"):
                errors.append(f"no copy confirmation on the finder: {sender.inner_text('#v2FindShareNote')!r}")
            url = sender.evaluate("() => navigator.clipboard.readText()")
            if not url.startswith(base + "#find-trade?"):
                errors.append(f"the copied finder link is not a #find-trade link: {url[:80]!r}")
            for part in ("mine=", "theirs=", "size=3", "km=1", "kt=1"):
                if part not in url:
                    errors.append(f"{part!r} missing from the copied finder link")
            if len(url) >= 2000:
                errors.append(f"the copied finder link is {len(url)} chars (budget 2000)")

            reader = open_page(url)
            reader.wait_for_function("() => !document.getElementById('v2FindOut').hidden", timeout=60000)
            reader.wait_for_timeout(300)
            got_rosters = reader.evaluate(FIND_ROSTERS)
            got_count = reader.evaluate(COUNT, reader.inner_text("#v2FindOut"))
            if got_rosters != sent_rosters:
                errors.append(f"the finder link restored different rosters:\n sent {sent_rosters}\n got  {got_rosters}")
            if got_count != sent_count:
                errors.append(f"the finder link showed {got_count} trades, the sender found {sent_count}")
            if reader.evaluate("() => document.getElementById('v2FindSize').value") != "3":
                errors.append("the finder link did not restore the package size")

            # --- the Compare link, copied from the verdict card ---
            compare = open_page(base + "#compare-trade")
            compare.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
            for field, results, query in (("#v2GiveSearch", "#v2GiveResults", "Gibbs"), ("#v2GetSearch", "#v2GetResults", "Chase")):
                compare.fill(field, query)
                compare.click(f"{results} button >> nth=0")
            compare.wait_for_timeout(400)
            sent_verdict = compare.evaluate(VERDICT)
            compare.click("#v2CShare")
            compare.wait_for_timeout(300)
            if "Link copied" not in compare.inner_text("#v2CShareNote"):
                errors.append(f"no copy confirmation on Compare: {compare.inner_text('#v2CShareNote')!r}")
            curl = compare.evaluate("() => navigator.clipboard.readText()")
            if curl != compare.evaluate("() => location.href"):
                errors.append(f"the Compare button copied {curl!r}, not location.href")
            fresh = open_page(curl)
            fresh.wait_for_function("() => document.querySelectorAll('#v2GivePlayers li').length && document.querySelectorAll('#v2GetPlayers li').length", timeout=60000)
            fresh.wait_for_timeout(300)
            got_verdict = fresh.evaluate(VERDICT)
            if (got_verdict["give"], got_verdict["get"]) != (sent_verdict["give"], sent_verdict["get"]):
                errors.append(f"the Compare link opened {got_verdict['give']} / {got_verdict['get']}")
            if (got_verdict["title"], got_verdict["text"]) != (sent_verdict["title"], sent_verdict["text"]):
                errors.append("the Compare link showed a different verdict")

            # --- placement ---
            box = compare.evaluate("""() => { const b = document.getElementById('v2CShare'); const card = document.getElementById('v2CVerdict');
              return {shown: !b.hidden, inCard: Boolean(b.closest('#v2CVerdict')), inHead: Boolean(b.closest('.v2-cverdict-head')),
                h: b.getBoundingClientRect().height}; }""")
            if not (box["shown"] and box["inCard"] and box["inHead"]):
                errors.append(f"the desktop Copy link is not in the verdict header: {box}")
            phone = open_page(base + "#compare-trade", width=390, height=844)
            phone.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
            for field, results, query in (("#v2GiveSearch", "#v2GiveResults", "Gibbs"), ("#v2GetSearch", "#v2GetResults", "Chase")):
                phone.fill(field, query)
                phone.click(f"{results} button >> nth=0")
            phone.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
            phone.wait_for_timeout(500)
            bar = phone.evaluate("""() => { const b = document.getElementById('v2CShare2'); const wrap = document.getElementById('v2CVerdictBarWrap');
              const r = b.getBoundingClientRect();
              return {shown: !b.hidden && !wrap.hidden, inBar: Boolean(b.closest('#v2CVerdictBarWrap')), h: r.height, bottom: r.bottom, vh: innerHeight}; }""")
            if not (bar["shown"] and bar["inBar"]):
                errors.append(f"the phone Copy link is not in the sticky bar: {bar}")
            if bar["h"] < 44:
                errors.append(f"the phone Copy link is {bar['h']}px tall (44px tap target wanted)")

            # --- the 1366x768 verdict fit ---
            fit = open_page(base + "#compare-trade", width=1366, height=768)
            fit.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
            for field, results, query in (("#v2GiveSearch", "#v2GiveResults", "Gibbs"), ("#v2GetSearch", "#v2GetResults", "Chase")):
                fit.fill(field, query)
                fit.click(f"{results} button >> nth=0")
            fit.wait_for_timeout(400)
            fold = fit.evaluate("""() => { const r = document.getElementById('v2CVerdict').getBoundingClientRect();
              return {bottom: r.bottom, vh: innerHeight, over: document.documentElement.scrollWidth - innerWidth}; }""")
            if fold["bottom"] > fold["vh"] + 0.5:
                errors.append(f"the verdict card ends at {fold['bottom']} of {fold['vh']} at 1366x768")
            if fold["over"] > 0:
                errors.append(f"horizontal overflow {fold['over']}px at 1366x768")
            for p in [sender, reader, compare, fresh, phone, fit]:
                if p.errors:
                    errors.append(f"page errors {p.errors}")
        finally:
            for c in contexts:
                c.close()
            browser.close()
    return errors


class ShareLinksRenderTest(unittest.TestCase):
    def test_finder_and_compare_share_links(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        finder = FINDER_JS.read_text(encoding="utf-8")
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = [
            ("encoder drops theirs", "finder", finder.replace("if (theirs) parts.push(`theirs=${theirs}`);", "", 1)),
            ("decoder ignores size", "finder", finder.replace("const size = Number(params.get(\"size\"));", "const size = 2;", 1)),
            ("link does not run the search", "finder",
             finder.replace("if (linkPending) { linkPending = false; if (S.mine.length && S.theirs.length) { if ($(\"v2FindSummary\")) updateSummary(); run(); } }", "", 1)),
            ("finder link not read", "v2",
             v2.replace("if (base === \"#find-trade\" && window.TradeValueFinder && window.TradeValueFinder.applyHash) window.TradeValueFinder.applyHash(params);", "", 1)),
        ]
        for name, which, body in broken:
            with self.subTest(mutation=name):
                source = finder if which == "finder" else v2
                self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                try:
                    found = run_checks({"finder.js" if which == "finder" else "v2.js": body})
                except Exception as exc:
                    found = [f"{type(exc).__name__}: {str(exc)[:80]}"]
                self.assertNotEqual(found, [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
