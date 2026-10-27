"""v2 Waivers tab (JEG-1022), rendered (T9-T12 of the spec, plus the shared roster, share link and sorting).

Loads dist/v2 headless at 1366x768, 390, 360 and 320 wide. A roster of 16 real players and ten candidates (three RBs,
three WRs, a QB, a TE, a defense, and a player who is already on the roster) are pasted in as names, then:

  * the headline sits inside the first screen (1366x768 and the phones) and reads "Pick up X, drop Y: ..." or one of the
    no-pickup sentences; the polite live region holds it;
  * the results table has all ten columns, role=grid labelled by the headline; every verdict cell carries its text;
    pick-up rows come before skip rows; the defense says Not evaluated and has dashes, not numbers; the player already on the
    roster is not in the results and the page says so; a player with no market value shows a dash, never 0.0;
  * the table sorts by a button in the header (aria-sort moves), numeric columns put dashes last both ways;
  * the roster folds into a summary (player count, positions) once results show; Edit roster opens it and moves focus;
  * the assessment table is the one Find a trade builds (same headings, same numbers for the same roster) and the roster is
    the same list on both tabs;
  * the share link in the address bar opens the same roster and candidates in a fresh page;
  * a scoring change (the league event) updates the numbers without a reload;
  * phones: cards instead of the table, no sideways scroll, a verdict banner on every card;
  * the page title names the tab, the tab sits seventh and Values auditing last, no page errors.

Discrimination: test_guard_fails_on_broken_builds serves waivers.js / waivers.css with: no headline text, no card layout, no
aria-sort, dashes sorted first, the settings listener removed, the grid role dropped, the verdict text dropped, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import _built_dist
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
WAIVERS_JS = ROOT / "app" / "v2" / "waivers.js"
WAIVERS_CSS = ROOT / "app" / "v2" / "waivers.css"
COLUMNS = ["Candidate", "Pos", "DDF Value", "Value above waivers", "Market value", "Starter change", "Bench change", "Best drop", "Verdict", "Reason"]


def setUpModule():
    _render_env.ensure_built()


PICK = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name).sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const count = new Map(); rows.forEach(r => count.set(r.name, (count.get(r.name) || 0) + 1));
  const by = pos => rows.filter(r => r.pos === pos && count.get(r.name) === 1);
  const take = (pos, from, n) => by(pos).slice(from, from + n).map(r => r.name);
  const roster = [].concat(take('QB', 3, 2), take('RB', 4, 6), take('WR', 5, 6), take('TE', 2, 2));
  const cands = [].concat(take('RB', 14, 3), take('WR', 20, 3), take('QB', 0, 1), take('TE', 0, 1), take('RB', 90, 1));
  const unpriced = C.getAllRows().filter(r => r.name && Number.isFinite(r.values.ddf_value) && !(r.values.usatoday > 0.05) && !(r.values.cbs > 0.05) && r.values.ddf_value >= 0).slice(0, 1).map(r => r.name);
  const defense = (window.TradeValueKDef.defenses[0] || {}).name;
  const theirs = [].concat(take('QB', 8, 2), take('RB', 24, 6), take('WR', 34, 6), take('TE', 8, 2));
  return {roster, cands: cands.concat([roster[0], defense]), defense, unpriced, theirs};
}"""

STATE = """() => {
  const vis = n => Boolean(n) && !n.hidden && n.getBoundingClientRect().height > 0;
  const head = document.getElementById('v2WaiversHeadline');
  const table = document.getElementById('v2WaiversTable');
  const rows = table ? [...table.querySelectorAll('tbody tr.v2-wv-main')] : [];
  const cards = [...document.querySelectorAll('#v2WaiversOut .v2-wv-cards > li')];
  const cell = (tr, i) => (tr.children[i].innerText || '').replace(/\\s+/g, ' ').trim();
  return {head: head.innerText.trim(), headBottom: head.getBoundingClientRect().bottom, vh: innerHeight, headVisible: vis(head),
    live: head.getAttribute('aria-live'), role: head.getAttribute('role'),
    heads: table ? [...table.querySelectorAll(':scope > thead > tr > th')].map(th => th.innerText.replace(/[↕↑↓]/g, '').trim()) : [],
    grid: table && table.getAttribute('role'), labelled: table && table.getAttribute('aria-labelledby'),
    tableVisible: vis(table), cardsVisible: cards.length > 0 && vis(cards[0]), cardCount: cards.length,
    cards: cards.map(c => ({banner: (c.querySelector('.v2-wv-card-banner').innerText || '').trim(), bannerH: c.querySelector('.v2-wv-card-banner').getBoundingClientRect().height})),
    rows: rows.map(tr => ({name: tr.children[0].querySelector('b').innerText, pos: cell(tr, 1), ddf: cell(tr, 2), vaw: cell(tr, 3), market: cell(tr, 4), starter: cell(tr, 5), bench: cell(tr, 6),
      drop: cell(tr, 7), verdict: cell(tr, 8), reason: cell(tr, 9)})),
    sorts: table ? [...table.querySelectorAll(':scope > thead > tr > th[aria-sort]')].map(th => [th.dataset.col, th.getAttribute('aria-sort')]) : [],
    summaryVisible: vis(document.getElementById('v2WaiversSummary')), summary: document.getElementById('v2WaiversSummary').innerText.replace(/\\s+/g, ' '),
    inputVisible: vis(document.getElementById('v2WaiversMineInput')), edit: document.getElementById('v2WaiversEdit').getAttribute('aria-expanded'),
    count: document.getElementById('v2WaiversCount').innerText, assess: document.getElementById('v2WaiversAssess').innerText.replace(/\\s+/g, ' '),
    scrollX: document.documentElement.scrollWidth - innerWidth, title: document.title, hash: location.hash,
    details: document.querySelectorAll('#v2WaiversOut details.v2-wv-detail').length, focus: document.activeElement && document.activeElement.id};
}"""


# The 44 px rule (JEG-861), for this tab only: every control inside #v2Waivers that a thumb can reach on a phone.
SMALL = """() => {
  const sel = 'a[href], button, input, select, textarea, summary, [role=button], [tabindex]:not([tabindex="-1"])';
  const out = []; let total = 0;
  for (const el of document.querySelectorAll('#v2Waivers ' + sel.split(', ').join(', #v2Waivers '))) {
    if (el.closest('[hidden], [aria-hidden="true"]')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (cs.display === 'inline' && el.tagName === 'A' && el.closest('p, li, .v2-meta')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    total++;
    if (r.width >= 43.5 && r.height >= 43.5) continue;
    out.push(`${el.tagName.toLowerCase()}#${el.id}.${String(el.className).slice(0, 30)} '${(el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 20)}' ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return {small: out, total};
}"""


def fill_lists(page, pick):
    page.fill("#v2WaiversMineSearch", "\n".join(pick["roster"]))
    page.wait_for_timeout(300)
    page.fill("#v2WaiversCandsSearch", "\n".join(pick["cands"]))
    page.wait_for_timeout(500)


def num(text):
    try:
        return float(text.replace("+", ""))
    except ValueError:
        return None


def check(page, tag, width, base) -> list[str]:
    errors = []
    phone = width < 600
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2WaiversHeadline') && !document.getElementById('v2Waivers').hidden", timeout=60000)
    s = page.evaluate(STATE)
    if "Add your roster first" not in s["head"]:
        errors.append(tag + f"empty tab headline {s['head']!r}")
    pick = page.evaluate(PICK)
    fill_lists(page, pick)
    s = page.evaluate(STATE)
    # headline
    if not s["headVisible"] or s["headBottom"] > s["vh"]:
        errors.append(tag + f"headline not inside the first screen: bottom {s['headBottom']:.0f} of {s['vh']}")
    if not (s["head"].startswith("Pick up ") or s["head"].startswith("No pickup") or s["head"].startswith("No clear pickup") or s["head"].startswith("No single pickup")):
        errors.append(tag + f"headline reads {s['head']!r}")
    if s["live"] != "polite" or s["role"] != "status":
        errors.append(tag + f"headline live region {s['role']}/{s['live']}")
    # table
    if len(s["rows"]) != 10:
        errors.append(tag + f"{len(s['rows'])} result rows, want 10 (nine players and a defense; the player already on the roster left out)")
    if phone:
        if s["tableVisible"] or not s["cardsVisible"] or s["cardCount"] != len(s["rows"]):
            errors.append(tag + f"phone layout: table {s['tableVisible']} cards {s['cardsVisible']} count {s['cardCount']}")
        if any(not c["banner"] or c["bannerH"] < 16 for c in s["cards"]):
            errors.append(tag + "a card has no verdict banner")
    else:
        if not s["tableVisible"] or s["cardsVisible"]:
            errors.append(tag + f"desktop layout: table {s['tableVisible']} cards {s['cardsVisible']}")
        if s["heads"] != COLUMNS:
            errors.append(tag + f"columns {s['heads']}")
        if s["grid"] != "grid" or s["labelled"] != "v2WaiversHeadline":
            errors.append(tag + f"table role {s['grid']} labelled by {s['labelled']}")
    if s["scrollX"] > 0:
        errors.append(tag + f"sideways scroll {s['scrollX']}px")
    names = [r["name"] for r in s["rows"]]
    if pick["roster"][0] in names:
        errors.append(tag + "a player already on the roster is in the results")
    if "already on your roster" not in s["count"]:
        errors.append(tag + f"no note about the player already on the roster: {s['count']!r}")
    verdicts = [r["verdict"] for r in s["rows"]]
    if any(not v for v in verdicts) or not all(v in ("Pick up", "Pick up (force)", "Consider", "Hold", "Skip", "Not evaluated") for v in verdicts):
        errors.append(tag + f"verdict cells {verdicts}")
    order = ["Pick up", "Pick up (force)", "Consider", "Hold", "Skip", "Not evaluated"]
    ranks = [order.index(v) for v in verdicts]
    if ranks != sorted(ranks):
        errors.append(tag + f"verdicts not in tier order: {verdicts}")
    defense = next((r for r in s["rows"] if r["name"] == pick["defense"]), None)
    if not defense or defense["verdict"] != "Not evaluated" or any(defense[k] != "—no value" and defense[k] != "— no value" and not defense[k].startswith("—") for k in ("ddf", "market", "starter", "bench")):
        errors.append(tag + f"the defense row: {defense}")
    if any(r["market"] in ("0.0", "+0.0") for r in s["rows"]):
        errors.append(tag + "a market value of 0.0 shown where a dash is wanted")
    if not any(r["market"].startswith("—") for r in s["rows"]):
        errors.append(tag + "no candidate shows a dash for market value (expected the deep RB)")
    if s["details"] < len(s["rows"]):
        errors.append(tag + f"{s['details']} detail toggles for {len(s['rows'])} rows")
    # collapsed roster
    if s["inputVisible"] or not s["summaryVisible"] or s["edit"] != "false":
        errors.append(tag + f"roster should fold once results show: input {s['inputVisible']} summary {s['summaryVisible']} expanded {s['edit']}")
    if "16 players" not in s["summary"] or "QB 2" not in s["summary"] or "RB 6" not in s["summary"]:
        errors.append(tag + f"summary {s['summary']!r}")
    page.focus("#v2WaiversEdit")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    s2 = page.evaluate(STATE)
    if not s2["inputVisible"] or s2["focus"] != "v2WaiversMineSearch":
        errors.append(tag + f"Edit roster: input {s2['inputVisible']} focus {s2['focus']!r}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    s2 = page.evaluate(STATE)
    if s2["inputVisible"] or s2["focus"] != "v2WaiversEdit":
        errors.append(tag + f"Escape did not fold the roster: input {s2['inputVisible']} focus {s2['focus']!r}")
    # sorting (desktop table)
    if not phone:
        page.click('#v2WaiversTable th[data-col="ddf"] button')
        page.wait_for_timeout(150)
        s3 = page.evaluate(STATE)
        if s3["sorts"] != [["ddf", "descending"]]:
            errors.append(tag + f"aria-sort after one click: {s3['sorts']}")
        vals = [num(r["ddf"]) for r in s3["rows"]]
        real = [v for v in vals if v is not None]
        if real != sorted(real, reverse=True) or vals[-1] is not None:
            errors.append(tag + f"DDF Value descending, dashes last: {vals}")
        page.click('#v2WaiversTable th[data-col="ddf"] button')
        page.wait_for_timeout(150)
        s3 = page.evaluate(STATE)
        vals = [num(r["ddf"]) for r in s3["rows"]]
        real = [v for v in vals if v is not None]
        if s3["sorts"] != [["ddf", "ascending"]] or real != sorted(real) or vals[-1] is not None:
            errors.append(tag + f"DDF Value ascending, dashes last: {s3['sorts']} {vals}")
        page.click('#v2WaiversTable th[data-col="verdict"] button')
        page.wait_for_timeout(150)
        if page.evaluate(STATE)["rows"][0]["verdict"] not in ("Pick up", "Pick up (force)", "Consider"):
            errors.append(tag + "the Verdict header does not return to the ranked order")
        # arrow keys walk the grid controls
        page.focus('#v2WaiversTable th[data-col="name"] button')
        page.keyboard.press("ArrowRight")
        if page.evaluate("() => document.activeElement.closest('th') && document.activeElement.closest('th').dataset.col") != "ddf":
            errors.append(tag + "arrow keys do not move along the header buttons")
    if phone:
        page.click("#v2WaiversOut .v2-wv-cards li >> nth=0 >> summary")
        page.click("#v2WaiversEdit")
        page.fill("#v2WaiversCandsSearch", pick["cands"][0][:4])
        page.wait_for_timeout(300)
        tap = page.evaluate(SMALL)
        if tap["total"] < 12 or tap["small"]:
            errors.append(tag + f"controls under 44 px on the Waivers tab ({tap['total']} checked): {tap['small'][:6]}")
        page.fill("#v2WaiversCandsSearch", "")
        page.click("#v2WaiversEdit")   # fold the roster again
        page.click("#v2WaiversOut .v2-wv-cards li >> nth=0 >> summary")
    # a detail opens and shows before / after
    page.click("#v2WaiversOut details.v2-wv-detail >> nth=0 >> summary") if not phone else page.click("#v2WaiversOut .v2-wv-cards li >> nth=0 >> summary")
    page.wait_for_timeout(150)
    if page.evaluate("() => document.querySelectorAll('#v2WaiversOut details[open] caption').length") < 2:
        errors.append(tag + "an opened detail does not show the lineup before and after")
    # assessment: the one Find a trade builds, for the same roster
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    page.fill("#v2FindTheirsSearch", "\n".join(pick["theirs"]))   # Find's assessment table shows once both rosters are in
    page.wait_for_timeout(600)
    find = page.evaluate("""() => ({mine: [...document.querySelectorAll('#v2FindMinePlayers .v2-find-row b')].map(b => b.textContent),
      cells: [...document.querySelectorAll('#v2FindAssess tbody tr')].map(tr => [...tr.children].map(c => c.innerText.trim()))})""")
    if sorted(find["mine"]) != sorted(pick["roster"]):
        errors.append(tag + "Find a trade does not hold the same roster")
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_function("() => !document.getElementById('v2Waivers').hidden", timeout=20000)
    mine = page.evaluate("""() => [...document.querySelectorAll('#v2WaiversAssess tbody tr')].map(tr => [...tr.children].map(c => c.innerText.trim()))""")
    # Find shows two teams side by side: the first cells of each row, as many as this tab's one-team row has, are the same.
    cut = [row[:len(m)] for row, m in zip(find["cells"], mine)]
    if cut != mine or not mine:
        errors.append(tag + f"assessment differs from Find a trade's: {[(a, b) for a, b in zip(mine, cut) if a != b][:2]}")
    page.wait_for_timeout(200)
    # share link round trip
    link = page.evaluate("() => location.href")
    if "mine=" not in link or "cands=" not in link or "scoring=" not in link:
        errors.append(tag + f"share link {link}")
    page2 = page.context.new_page()
    page2.goto(link, wait_until="networkidle")
    page2.wait_for_function("() => window.TradeValueV2 && document.getElementById('v2WaiversHeadline') && document.querySelectorAll('#v2WaiversTable tbody tr.v2-wv-main, #v2WaiversOut .v2-wv-cards li').length > 0", timeout=60000)
    again = page2.evaluate(STATE)
    if [r["name"] for r in again["rows"]] != names or again["head"] != s["head"]:
        errors.append(tag + f"the link opened a different result: {again['head']!r} vs {s['head']!r}")
    page2.close()
    # settings change without a reload
    page.evaluate("() => { window.__sentinel = 1; }")
    before = page.evaluate(STATE)["rows"]
    page.evaluate("""() => { const C = window.TradeValueCurveControls; C.setScoring(C.getState().scoring === 'standard' ? 'ppr' : 'standard');
      document.dispatchEvent(new CustomEvent('ddf:league-settings-changed', {detail: {reason: 'league', notes: []}})); }""")
    page.wait_for_timeout(500)
    after = page.evaluate(STATE)["rows"]
    if page.evaluate("() => window.__sentinel") != 1:
        errors.append(tag + "the page reloaded on a scoring change")
    if [r["ddf"] for r in before] == [r["ddf"] for r in after] and [r["name"] for r in before] == [r["name"] for r in after]:
        errors.append(tag + "a scoring change left every result as it was")
    # The event itself redraws the tab (the engine's own change may not announce): wipe the results, send the event.
    page.evaluate("""() => { document.getElementById('v2WaiversOut').replaceChildren(); document.getElementById('v2WaiversHeadline').querySelector('b').textContent = 'stale';
      document.dispatchEvent(new CustomEvent('ddf:league-settings-changed', {detail: {reason: 'league', notes: []}})); }""")
    page.wait_for_timeout(400)
    again = page.evaluate(STATE)
    if again["head"] == "stale" or not again["rows"] and not again["cardCount"]:
        errors.append(tag + "the league-settings event did not redraw the tab")
    return errors


def chrome_checks(page, tag) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_function("() => !document.getElementById('v2Waivers').hidden", timeout=20000)
    t = page.evaluate("""() => ({title: document.title, tabs: [...document.querySelectorAll('.v2-tab')].map(a => a.querySelector('.v2-tab-full').textContent.trim()),
      active: document.querySelector('.v2-tab[aria-current=page]') && document.querySelector('.v2-tab[aria-current=page]').dataset.view})""")
    if not t["title"].startswith("Waivers"):
        errors.append(tag + f"title {t['title']!r}")
    if t["tabs"].index("Waivers") != 5 or t["tabs"][4:7] != ["Risers and fallers", "Waivers", "Trade targets"] or t["active"] != "waivers":   # JEG-1106: Waivers sits in the Players group
        errors.append(tag + f"nav {t}")
    return errors


def run_checks(overrides=None, viewports=((1366, 768), (390, 844), (360, 740), (320, 640))) -> list[str]:
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
        try:
            for width, height in viewports:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, kind) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, kind))
                    context.route(f"**/v2/{name}*", functools.partial(_serve, body, kind))
                page.goto(base + "#waivers", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
                tag = f"[{width}px] "
                errors += chrome_checks(page, tag)
                errors += check(page, tag, width, base)
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class WaiversRenderTests(unittest.TestCase):
    maxDiff = None

    def test_tab(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = WAIVERS_JS.read_text(encoding="utf-8")
        css = WAIVERS_CSS.read_text(encoding="utf-8")
        broken = {
            "no headline text": ("waivers.js", js.replace("setText(headline.querySelector(\"b\"), text);", "", 1), "text/javascript"),
            "no card layout": ("waivers.css", css.replace("#v2Waivers .v2-wv-tablewrap { display: none; }", "", 1), "text/css"),
            "no aria-sort": ("waivers.js", js.replace('th.setAttribute("aria-sort", S.sort.dir === "asc" ? "ascending" : "descending");', "", 1), "text/javascript"),
            "dashes sorted first": ("waivers.js", js.replace("return nx ? 1 : -1;   // dashes last, whichever way", "return nx ? -1 : 1;", 1), "text/javascript"),
            "settings listener removed": ("waivers.js", js.replace('document.addEventListener("ddf:league-settings-changed", onLeagueSettingsChanged);', "", 1), "text/javascript"),
            "no grid role": ("waivers.js", js.replace('role: "grid", ', "", 1), "text/javascript"),
            "remove buttons 20 px tall": ("waivers.css", css.replace("#v2Waivers .v2-wv-remove { min-height: 44px; min-width: 44px; padding: 0 8px; }", "#v2Waivers .v2-wv-remove { min-height: 20px; min-width: 20px; padding: 0 2px; }", 1), "text/css"),
            "no verdict text": ("waivers.js", js.replace('"data-verdict": VERDICT_CLASS[r.verdict], text: r.verdict});', '"data-verdict": VERDICT_CLASS[r.verdict]});', 1), "text/javascript"),
        }
        for name, (file, body, kind) in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js if file.endswith(".js") else css, f"mutation anchor for {name!r} is stale")
                try:
                    errors = run_checks({file: (body, kind)}, viewports=((1366, 768), (390, 844)))
                except Exception as exc:   # so broken that a step cannot run
                    errors = [str(exc)[:80]]
                self.assertNotEqual(errors, [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
