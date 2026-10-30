"""v2 How values work, rendered: explanation only, no new numbers.

Builds dist/v2 into a temp copy of the built dist/, loads /v2/#writing/how-values
headless (desktop 1440 and mobile 390) after switching the engine to a 10-team
league, and checks:

  * the "Your league shapes the comparison" card is the engine's own state
    (getState scoring and teams, getRosterShape counts, getPositionWeights,
    getBenchShareReadout), so it follows Edit league and Position weights; the Methods
    row is shown (frame 15);
  * each of the three views (Value above waivers, Data Driven Adjustments,
    Rescaled, JEG-510) lists exactly the engine's series of that method from
    getSourceInfo(), unavailable ones marked with a reason, older weeks labeled per the
    data's freshness record;
  * copy rules (CLAUDE.md): no "Vegas"; no "VORP" at all (JEG-861, 2026-10-22);
    no numbers anywhere on the tab except the engine-filled league card;
  * JEG-941: the "How position weights work" explainer is a collapsible in the league card, a
    button with aria-expanded, collapsed by default, opened from the keyboard, with the agreed
    wording and no stray numbers;
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds builds the tab with a bare
"VORP", with a hard-coded number in the copy, with the league line or the
position weights hard-coded, and with the source lists not split by method,
and requires each to fail.
"""
from __future__ import annotations

import datetime

import contextlib
import functools
import http.server
import re
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


SHELL = ROOT / "app" / "v2" / "shell.html"
V2_JS = ROOT / "app" / "v2" / "v2.js"
SCORING = {"standard": "Standard", "half_ppr": "Half PPR", "ppr": "Full PPR"}

READ = """() => {
  const C = window.TradeValueCurveControls;
  const how = document.getElementById('v2How');
  const clone = how.cloneNode(true);
  // JEG-861 (#821): the "NFL Week N · as of Mon D" stamp under the title carries the data week
  // and the fixture's built_at; checked against the engine below, not as copy.
  const stampNode = how.querySelector('[data-page-asof]');
  const stamp = stampNode ? stampNode.textContent.trim() : null;
  clone.querySelectorAll('[data-engine], [data-step], [data-page-asof]').forEach(n => n.remove());
  // Older-week labels come from the data's freshness record, as on every v2 tab.
  const fresh = window.TradeValueProductData?.getSourceFreshness?.()?.series || {};
  const info = C.getSourceInfo().filter(item => !item.key.endsWith('_adjusted')).map(item => {
    const row = fresh[item.key];
    return row && typeof row.is_older_week === 'boolean' ? {...item, stale: row.is_older_week} : item;
  });
  return {state: C.getState(), roster: C.getRosterShape(), info, weights: C.getPositionWeights(), bench: C.getBenchShareReadout(),
    weightsLine: document.getElementById('v2HowWeights').textContent, benchLine: document.getElementById('v2HowBench').textContent,
    methodsShown: !(document.getElementById('v2Context')?.hidden ?? true),
    league: document.getElementById('v2HowLeague').textContent,
    rosterLine: document.getElementById('v2HowRoster').textContent,
    lists: Object.fromEntries([...how.querySelectorAll('[data-sources]')].map(ul => [ul.dataset.sources,
      [...ul.querySelectorAll('li')].map(li => ({key: li.dataset.source, available: li.dataset.available,
        text: li.textContent}))])),
    text: how.textContent, copy: clone.textContent, hidden: how.hidden,
    stamp, refWeek: window.TradeValueV2.view().refWeek, builtAt: window.TradeValueProductData?.getSnapshot?.()?.built_at,
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""


EXPLAINER = """() => {
  const b = document.getElementById('v2HowWeightsExplainerBtn');
  const body = document.getElementById('v2HowWeightsExplainerBody');
  if (!b || !body) return {present: false};
  const r = body.getBoundingClientRect();
  return {present: true, tag: b.tagName, expanded: b.getAttribute('aria-expanded'), controls: b.getAttribute('aria-controls') === body.id,
    label: b.textContent.trim(), bodyHidden: body.hidden, visible: r.width > 0 && r.height > 0,
    text: body.textContent.replace(/\\s+/g, ' ').trim(), inLeagueCard: !!b.closest('.v2-how-league'),
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""

EXPLAINER_PHRASES = (
    "no single source sets the shares",
    "In superflex leagues",
    "no position has a fixed share",
)


def check_explainer(snap) -> list[str]:
    before, opened, closed = snap["explainerBefore"], snap["explainerOpen"], snap["explainerClosed"]
    if not before["present"]:
        return ["JEG-941: the position weights explainer is missing from the How values work tab"]
    errors = []
    if before["tag"] != "BUTTON" or not before["controls"]:
        errors.append(f"explainer toggle is not a button wired with aria-controls: {before}")
    if before["label"] != "How position weights work":
        errors.append(f"explainer label {before['label']!r}")
    if before["expanded"] != "false" or not before["bodyHidden"] or before["visible"]:
        errors.append(f"explainer is not collapsed by default: {before}")
    if not before["inLeagueCard"]:
        errors.append("explainer is not inside the league card (a separate card was not asked for)")
    if opened["expanded"] != "true" or opened["bodyHidden"] or not opened["visible"]:
        errors.append(f"Enter on the toggle does not expand the explainer: {opened}")
    if closed["expanded"] != "false" or not closed["bodyHidden"]:
        errors.append(f"a second Enter does not collapse the explainer: {closed}")
    for phrase in EXPLAINER_PHRASES:
        if phrase not in before["text"]:
            errors.append(f"explainer text is missing {phrase!r}")
    words = len(before["text"].split())
    if not 90 <= words <= 140:
        errors.append(f"explainer is {words} words, expected about 120")
    if re.search(r"\bJEG-\d+|\.py\b|\bDDF\b|\bVORP\b", before["text"]):
        errors.append("explainer carries a ticket id, script path or abbreviation")
    if opened["overflow"] > 0 and snap["width"] <= 390:
        errors.append(f"explainer overflows horizontally by {opened['overflow']}px when open")
    return errors


def method(key):
    if key.endswith("_vorp"):
        return "vorp"
    if key in ("espn", "cbsros", "razzball"):
        return "dda"
    return "indexed"


def as_of_label(built_at) -> str:
    """v2.js dataAsOfLabel: the built_at day as en-US "Mon D" in UTC."""
    d = datetime.date.fromisoformat(str(built_at or "")[:10])
    return f"{d.strftime('%b')} {d.day}"


def check(snap) -> list[str]:
    errors = []
    if snap["hidden"]:
        return ["the How values work tab is hidden at #writing/how-values"]
    state, roster = snap["state"], snap["roster"]
    league = f"{SCORING.get(state['scoring'], state['scoring'])} · {state['teams']} teams"
    if snap["league"] != league:
        errors.append(f"league line {snap['league']!r} != engine {league!r}")
    superflex = f"{roster['SUPERFLEX']} SUPERFLEX · " if roster.get("SUPERFLEX") else ""
    k = f"{roster['K']} K · " if roster.get("K") else ""
    dst = f"{roster['DST']} DEF · " if roster.get("DST") else ""
    line = f"{roster['QB']} QB · {roster['RB']} RB · {roster['WR']} WR · {roster['TE']} TE · {roster['FLEX']} FLEX · {superflex}{k}{dst}{roster['BENCH']} BN"
    if snap["rosterLine"] != line:
        errors.append(f"roster line {snap['rosterLine']!r} != engine {line!r}")
    want_weights = " · ".join(f"{p} {float(snap['weights'][p]) * 100:.1f}%" for p in ("QB", "RB", "WR", "TE"))
    if snap["weightsLine"] != want_weights:
        errors.append(f"weights line {snap['weightsLine']!r} != engine {want_weights!r}")
    # JEG-537: the bench share is the engine's readout by position (or the reader's override).
    r = snap["bench"]
    want = (f"{r['overrideValue'] * 100:.1f}% (your override)" if r["override"]
            else " · ".join(f"{p} {r[p] * 100:.1f}%" for p in ("QB", "RB", "WR", "TE")))
    if snap["benchLine"] != want:
        errors.append(f"bench line {snap['benchLine']!r} != engine readout {want!r}")
    if not snap["methodsShown"]:
        errors.append("frame 15: the context row is shown on How values work")
    for view in ("vorp", "dda", "indexed"):
        want = [item for item in snap["info"] if method(item["key"]) == view]
        got = snap["lists"].get(view, [])
        if [g["key"] for g in got] != [w["key"] for w in want]:
            errors.append(f"{view}: lists {[g['key'] for g in got]}, engine has {[w['key'] for w in want]}")
            continue
        for g, w in zip(got, want):
            if g["available"] != str(bool(w["available"])).lower():
                errors.append(f"{view}/{w['key']}: available {g['available']} != engine {w['available']}")
            if not w["available"] and "not available" not in g["text"] and "waiting" not in g["text"]:
                errors.append(f"{view}/{w['key']}: unavailable with no reason: {g['text']!r}")
            if w["available"] and w.get("waiverNote") and w["waiverNote"] not in g["text"]:
                errors.append(f"{view}/{w['key']}: missing the engine's waiver note {w['waiverNote']!r}")
            if w["available"] and bool(w.get("stale")) != ("older week" in g["text"]):
                errors.append(f"{view}/{w['key']}: older-week label {g['text']!r} vs engine stale={w.get('stale')}")
    if re.search(r"vegas", snap["text"], re.I):
        errors.append("copy mentions Vegas")
    # JEG-861 (2026-10-22): the term is "Value above waivers"; "VORP" never appears in user-facing copy.
    if re.search(r"vorp", snap["text"], re.I):
        errors.append("copy says VORP")
    # JEG-822: plain language, no overclaim; "estimated" is explained where the engine's count appears.
    for phrase in ("really worth", "All nine reads"):
        if phrase in snap["text"]:
            errors.append(f"copy still says {phrase!r}")
    if any(w["available"] and "estimated players" in (w.get("waiverNote") or "") for w in snap["info"]) \
            and "a chart does not list; we fill in a value" not in snap["text"]:
        errors.append("the engine's 'estimated players' note has no plain-language explanation")
    digits = re.findall(r"\d+", snap["copy"])
    if digits:
        errors.append(f"copy carries numbers not from the engine: {digits}")
    # JEG-861 (#821): the page stamp is the data week and the fixture's built_at day, from the data.
    want_stamp = f"NFL Week {snap['refWeek']} · as of {as_of_label(snap['builtAt'])}"
    if snap["stamp"] != want_stamp:
        errors.append(f"page stamp {snap['stamp']!r} != {want_stamp!r} from the data")
    errors += check_explainer(snap)
    return errors


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/javascript", body=body)


@contextlib.contextmanager
def _built_dist(shell_html=None):
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        out = build_v2_page.build(dist)
        if shell_html is not None:
            out.write_text(build_v2_page.build_v2_html(build_v2_page.ENGINE_PAGE.read_text(encoding="utf-8"), shell_html),
                           encoding="utf-8")

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#writing/how-values"
            finally:
                server.shutdown()


def collect(shell_html=None, v2_js=None, viewports=((1440, 1000), (390, 844))):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    snapshots = []
    with _built_dist(shell_html) as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=30000)
                # A non-default league: the tab must follow Edit league.
                page.evaluate("() => window.TradeValueCurveControls.setTeams(10)")
                page.evaluate("() => { location.hash = '#player-values'; }")
                page.wait_for_function("() => !document.getElementById('v2Main').hidden")
                page.evaluate("() => { location.hash = '#writing/how-values'; }")
                page.wait_for_timeout(200)
                snap = page.evaluate(READ)
                snap["explainerBefore"] = page.evaluate(EXPLAINER)
                page.focus("#v2HowWeightsExplainerBtn")
                page.keyboard.press("Enter")
                snap["explainerOpen"] = page.evaluate(EXPLAINER)
                page.keyboard.press("Enter")
                snap["explainerClosed"] = page.evaluate(EXPLAINER)
                snap.update(width=width, pageErrors=list(errors))
                snapshots.append(snap)
                page.close()
        finally:
            browser.close()
    return snapshots


def check_all(snapshots) -> list[str]:
    errors = []
    for snap in snapshots:
        prefix = f"[{snap['width']}px] "
        errors += [prefix + e for e in check(snap)]
        if snap["pageErrors"]:
            errors.append(prefix + f"page errors: {snap['pageErrors']}")
        if snap["width"] <= 390 and snap["overflow"] > 0:
            errors.append(prefix + f"horizontal overflow {snap['overflow']}px")
    return errors


class HowValuesRenderTest(unittest.TestCase):
    def test_tab_matches_engine_and_copy_rules(self):
        snapshots = collect()
        self.assertEqual(check_all(snapshots), [])
        self.assertTrue(all(s["state"]["teams"] == 10 for s in snapshots))

    def test_guard_fails_on_broken_builds(self):
        shell = SHELL.read_text(encoding="utf-8")
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = {
            "bare VORP": {"shell_html": shell.replace("<h2>The Market, by chart</h2>", "<h2>The Market, by VORP chart</h2>", 1)},
            "hard-coded number": {"shell_html": shell.replace(
                "<b>Zero is real.</b>", "<b>Zero is real.</b> About 30 players per position clear the line.", 1)},
            "league line hard-coded": {"v2_js": v2.replace(
                '$("v2HowLeague").textContent = $("v2LeagueName").textContent;',
                '$("v2HowLeague").textContent = "Full PPR · 12 teams";', 1)},
            "weights hard-coded": {"v2_js": v2.replace(
                '$("v2HowWeights").textContent = ["QB", "RB", "WR", "TE"]',
                '$("v2HowWeights").textContent = "QB 6.1% · RB 44.2% · WR 43.6% · TE 6.1%"; void ["QB", "RB", "WR", "TE"]', 1)},
            "overclaim copy back": {"shell_html": shell.replace(
                "What a player is worth in your league:", "Fair value: the price a player is really worth:", 1)},
            "no estimated gloss": {"v2_js": v2.replace("estimatedExplained = true;", "estimatedExplained = true; return;", 1)},
            # JEG-861 (#821): the stamp carries the data week; a calendar/hard-coded week is a wrong number.
            "stamp week hard-coded": {"v2_js": v2.replace(
                "return [view.refWeek ? `NFL Week ${view.refWeek}` : \"\", asOf ? `as of ${asOf}` : \"\"]",
                "return [`NFL Week ${(view.refWeek || 0) + 1}`, asOf ? `as of ${asOf}` : \"\"]", 1)},
            "explainer open by default": {"shell_html": shell.replace(
                'aria-expanded="false" aria-controls="v2HowWeightsExplainerBody"', 'aria-expanded="true" aria-controls="v2HowWeightsExplainerBody"', 1)},
            "explainer toggle dead": {"v2_js": v2.replace(
                'button.setAttribute("aria-expanded", String(open));', 'void open;', 1)},
            "explainer text changed": {"shell_html": shell.replace("no position has a fixed share", "positions have fixed shares", 1)},
            "sources not split by method": {"v2_js": v2.replace(
                "list.replaceChildren();\n      view.info.filter(item => sourceMeta(item.key).method === method)",
                "list.replaceChildren();\n      view.info", 1)},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                original = shell if "shell_html" in kwargs else v2
                self.assertNotEqual(next(iter(kwargs.values())), original, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check_all(collect(viewports=((1440, 1000),), **kwargs)), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
