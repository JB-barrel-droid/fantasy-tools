"""Waivers Clear and Undo keep each list to itself (JEG-1278, pinning the JEG-1190 promise), rendered.

Loads the built dist/v2 headless at 320x640, 390x844 and 1366x768. A saved league is seeded through the page's own store
(tests/fixtures/waivers-clear-isolation.json): my team (QB, RB, WR, TE, a kicker and a defense), two league teammates and a
waiver candidate list, all real player keys from the build and all distinct. Then, with the keyboard only:

  * Clear on Waiver candidates empties the candidates and leaves my roster, both teammates and the league settings exactly as
    they were; Undo is reached with Tab from where Clear leaves focus, and Enter on it puts back the same candidates in order;
  * Clear on Your roster empties the shared roster (the store Find a trade reads, and Find a trade's own list), says on the
    page that it was cleared on both Find a trade screens, and leaves the candidates, teammates and settings alone; Enter on
    Undo puts back the exact keys in order, the kicker and the defense included, and Find a trade shows the roster again;
  * focus (JEG-1316, option A): after roster Clear it lands on the unfolded roster input, with Undo
    reached by Tab; after roster Undo it lands on the roster control that is on screen (Edit roster once results fold the
    input), and "Your roster is back." shows outside the folded input;
  * no page errors, no request leaves the local server, no sideways scroll.

Discrimination: test_guard_fails_on_source_mutants serves app/v2/waivers.js with (1) candidate Clear calling the roster's
clear, (2) Undo writing back into the other list, (3) the roster's Undo writing into the candidates, (4) roster Clear
focusing before the input unfolds, (5) roster Undo leaving focus to the fold, (6) the "is back" message left inside the
folded input. Each mutant carries a
marker the page must report (so the mutant was the file actually served), and each must fail the named state assertion,
not just any assertion. The baseline run must report no marker.
"""
from __future__ import annotations

import functools
import json
import sys
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import _built_dist
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
WAIVERS_JS = ROOT / "app" / "v2" / "waivers.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "waivers-clear-isolation.json").read_text(encoding="utf-8"))


def setUpModule():
    _render_env.ensure_built()


# Builds the seed from the fixture with the page's own helpers, saves it through the page's store, and writes the
# candidate list where the Waivers tab reads it on first show. Returns what was seeded.
SEED = """(fx) => {
  const C = window.TradeValueCurveControls, W = window.TradeValueWorkspace, F = window.TradeValueFinder;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name && r.player_key != null)
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const count = new Map(); rows.forEach(r => count.set(r.name, (count.get(r.name) || 0) + 1));
  const by = pos => rows.filter(r => r.pos === pos && count.get(r.name) === 1);
  const entry = r => ({key: String(r.player_key), name: r.name, pos: r.pos, team: r.team || ''});
  const picks = list => [].concat(...list.map(([pos, from, n]) => by(pos).slice(from, from + n).map(entry)));
  const kd = window.TradeValueKDef || {};
  const paste = window.DDFRosterPaste;
  const teamCode = t => (paste && paste.normTeam ? paste.normTeam(t) : null) || String(t || '').toUpperCase();
  const def = i => { const d = (kd.defenses || [])[i]; return d && d.name ? {key: `x:DEF:${teamCode(d.team)}`, name: d.name, pos: 'DEF', team: teamCode(d.team)} : null; };
  const kick = i => { const k = (kd.kickers || [])[i]; return k && k.name ? {key: `x:K:${F.normName(k.name)}`, name: k.name, pos: 'K', team: teamCode(k.team)} : null; };
  const side = s => picks(s.picks).concat((s.kickers || []).map(kick), (s.defenses || []).map(def)).filter(Boolean);
  const roster = side(fx.roster), cands = side(fx.candidates);
  const now = Date.now();
  const mine = W.newTeam(fx.workspace.my_team.name, {id: fx.workspace.my_team.id, entries: roster, now});
  const mates = fx.workspace.teammates.map(t => W.newTeam(t.name, {id: t.id, entries: picks(t.picks), now}));
  const ws = {...W.newWorkspace({id: fx.workspace.id, name: fx.workspace.name, now}), teams: [mine].concat(mates), myTeamId: mine.id,
    settings: {query: window.TradeValueV2.leagueQuery()}};
  W.store.replace(ws, 'seed');
  W.store.flush();
  localStorage.setItem('ddf.v2.waiverCandidates', JSON.stringify(cands));
  return {roster: roster.map(e => e.key), rosterPos: roster.map(e => e.pos), cands: cands.map(e => e.key),
    mates: mates.map(t => t.entries.map(e => e.key))};
}"""

# Everything a Clear or an Undo could touch: the shared roster, the teammates, the candidates, the league settings.
SNAP = """() => {
  const W = window.TradeValueWorkspace, ws = W.store.get();
  const vis = n => Boolean(n) && !n.closest('[hidden]') && n.getBoundingClientRect().height > 0;
  const read = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  let cands; try { cands = JSON.parse(read('ddf.v2.waiverCandidates') || '[]').map(p => p.key); } catch (e) { cands = ['<corrupt>']; }
  const msg = id => { const n = document.getElementById(id + 'PasteResult'); return {text: n ? n.innerText.replace(/\\s+/g, ' ').trim() : '', visible: vis(n && n.firstElementChild)}; };
  const teams = ws.teams.map(t => ({id: t.id, name: t.name, keys: t.entries.map(e => e.key)}));
  return {
    mine: W.store.getMyRoster().map(e => e.key), minePos: W.store.getMyRoster().map(e => e.pos), myTeam: ws.myTeamId,
    mates: teams.filter(t => t.id !== ws.myTeamId),
    settings: {saved: JSON.stringify(ws.settings), ui: JSON.stringify(ws.ui), stored: read('ddf.v2.league-settings'), query: window.TradeValueV2.leagueQuery(), view: read('ddf.v2.waivers.view')},
    cands, candsShown: [...document.querySelectorAll('#v2WaiversCandsList > li b')].map(b => b.textContent),
    mineShown: [...document.querySelectorAll('#v2WaiversMineList > li b')].map(b => b.textContent),
    mineClear: vis(document.getElementById('v2WaiversMineClear')), candsClear: vis(document.getElementById('v2WaiversCandsClear')),
    mineMsg: msg('v2WaiversMine'), candsMsg: msg('v2WaiversCands'),
    mineBack: (() => { const n = document.getElementById('v2WaiversMineBack'); return {text: n ? n.innerText.replace(/\\s+/g, ' ').trim() : '', visible: vis(n && n.firstElementChild)}; })(),
    focusVisible: vis(document.activeElement),
    mineFolded: Boolean(document.getElementById('v2WaiversMineInput') && document.getElementById('v2WaiversMineInput').hidden),
    focus: document.activeElement ? (document.activeElement.id || document.activeElement.tagName.toLowerCase()) : null,
    mutant: window.__waiversMutant || null, scrollX: document.documentElement.scrollWidth - innerWidth};
}"""

# The Undo button: on screen, a real button in the tab order.
UNDO = """(id) => { const n = document.getElementById(id); if (!n) return {ok: false, why: 'missing'};
  const r = n.getBoundingClientRect();
  return {ok: n.tagName === 'BUTTON' && !n.disabled && n.tabIndex >= 0 && !n.closest('[hidden]') && r.height > 0 && r.width > 0, why: `${n.tagName} tabIndex ${n.tabIndex} ${Math.round(r.width)}x${Math.round(r.height)}`}; }"""

FIND_MINE = "() => [...document.querySelectorAll('#v2FindMinePlayers .v2-find-row b')].map(b => b.textContent)"


def focus_id(page):
    return page.evaluate("() => document.activeElement && document.activeElement.id")


def tab_to(page, target, limit=3):
    for _ in range(limit):
        page.keyboard.press("Tab")
        if focus_id(page) == target:
            return True
    return False


def press_enter_on(page, selector):
    page.focus(selector)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)


def unchanged(errors, tag, step, before, after, *, roster=True, cands=True):
    if roster and after["mine"] != before["mine"]:
        errors.append(f"{tag}{step}: roster changed {before['mine']} -> {after['mine']}")
    if cands and after["cands"] != before["cands"]:
        errors.append(f"{tag}{step}: candidates changed {before['cands']} -> {after['cands']}")
    if after["mates"] != before["mates"] or after["myTeam"] != before["myTeam"]:
        errors.append(f"{tag}{step}: league teammates changed")
    if after["settings"] != before["settings"]:
        errors.append(f"{tag}{step}: settings changed {before['settings']} -> {after['settings']}")


def go(page, view, host):
    page.evaluate(f"() => {{ location.hash = '#{view}'; }}")
    page.wait_for_function(f"() => !document.getElementById('{host}').hidden", timeout=20000)
    page.wait_for_timeout(400)


def check(page, tag, seed, external, notes) -> list[str]:
    errors = []
    s0 = page.evaluate(SNAP)
    keys = seed["roster"] + seed["cands"] + [k for m in seed["mates"] for k in m]
    if len(set(keys)) != len(keys):
        errors.append(tag + "seed: roster, candidate and teammate keys are not distinct")
    if "K" not in seed["rosterPos"] or "DEF" not in seed["rosterPos"]:
        errors.append(tag + f"seed: roster has no kicker or defense {seed['rosterPos']}")
    if s0["mine"] != seed["roster"] or s0["cands"] != seed["cands"] or [m["keys"] for m in s0["mates"]] != seed["mates"]:
        errors.append(tag + "seed: the page did not load the seeded league and candidates")
    if not s0["mineClear"] or not s0["candsClear"]:
        errors.append(tag + f"seed: a Clear button is not shown (roster {s0['mineClear']}, candidates {s0['candsClear']})")
    if errors:
        return errors
    external.clear()   # from here on, Clear and Undo must not reach the network

    # Clear the candidates: the candidates go, nothing else moves.
    a0 = s0
    press_enter_on(page, "#v2WaiversCandsClear")
    a1 = page.evaluate(SNAP)
    if a1["cands"] or a1["candsShown"]:
        errors.append(tag + f"cands-clear: candidates not cleared {a1['cands']} / {a1['candsShown']}")
    unchanged(errors, tag, "cands-clear", a0, a1, cands=False)
    if a1["mineShown"] != a0["mineShown"]:
        errors.append(tag + "cands-clear: the roster list on the page changed")
    if not a1["candsMsg"]["visible"] or not a1["candsMsg"]["text"].startswith("Cleared waiver candidates."):
        errors.append(tag + f"cands-clear: no visible cleared message {a1['candsMsg']}")
    if not tab_to(page, "v2WaiversCandsUndo"):
        errors.append(tag + f"cands-clear: Undo not reached with Tab from {a1['focus']!r}")
    u = page.evaluate(UNDO, "v2WaiversCandsUndo")
    if not u["ok"]:
        errors.append(tag + f"cands-clear: Undo not a visible keyboard button ({u['why']})")
    else:
        press_enter_on(page, "#v2WaiversCandsUndo")
    a2 = page.evaluate(SNAP)
    if a2["cands"] != a0["cands"] or a2["candsShown"] != a0["candsShown"]:
        errors.append(tag + f"cands-undo: candidates not restored {a0['cands']} -> {a2['cands']}")
    unchanged(errors, tag, "cands-undo", a0, a2, cands=False)

    # Clear Your roster: the shared roster goes (and the page says where), the candidates stay.
    b0 = page.evaluate(SNAP)
    if not b0["mineClear"]:
        errors.append(tag + "mine-clear: the roster Clear button is not shown")
        return errors
    press_enter_on(page, "#v2WaiversMineClear")
    b1 = page.evaluate(SNAP)
    if b1["mine"]:
        errors.append(tag + f"mine-clear: shared roster not cleared {b1['mine']}")
    unchanged(errors, tag, "mine-clear", b0, b1, roster=False)
    if b1["candsShown"] != b0["candsShown"]:
        errors.append(tag + "mine-clear: the candidate list on the page changed")
    if not b1["mineMsg"]["visible"] or "both Find a trade screens" not in b1["mineMsg"]["text"]:
        errors.append(tag + f"mine-clear: sharing not disclosed {b1['mineMsg']}")
    if b1["focus"] != "v2WaiversMineSearch" or not b1["focusVisible"]:
        errors.append(tag + f"mine-clear: focus was {b1['focus']!r} (visible {b1['focusVisible']}), not the roster input")
    if not tab_to(page, "v2WaiversMineUndo"):
        errors.append(tag + f"mine-clear: Undo not reached with Tab from {b1['focus']!r}")
    u = page.evaluate(UNDO, "v2WaiversMineUndo")
    if not u["ok"]:
        errors.append(tag + f"mine-clear: Undo not a visible keyboard button ({u['why']})")
    go(page, "find-trade", "v2FindTrade")
    if page.evaluate(FIND_MINE):
        errors.append(tag + f"mine-clear: Find a trade still shows a roster {page.evaluate(FIND_MINE)}")
    go(page, "waivers", "v2Waivers")
    if u["ok"]:
        press_enter_on(page, "#v2WaiversMineUndo")
    b2 = page.evaluate(SNAP)
    if b2["mine"] != b0["mine"]:
        errors.append(tag + f"mine-undo: roster not restored exactly {b0['mine']} -> {b2['mine']}")
    if [p for p in b2["minePos"] if p in ("K", "DEF")] != [p for p in b0["minePos"] if p in ("K", "DEF")]:
        errors.append(tag + f"mine-undo: kicker or defense not restored {b2['minePos']}")
    unchanged(errors, tag, "mine-undo", b0, b2, roster=False)
    want = "v2WaiversEdit" if b2["mineFolded"] else "v2WaiversMineSearch"
    if b2["focus"] != want or not b2["focusVisible"]:
        errors.append(tag + f"mine-undo: focus was {b2['focus']!r} (visible {b2['focusVisible']}), not {want} (input folded: {b2['mineFolded']})")
    if not b2["mineBack"]["visible"] or b2["mineBack"]["text"] != "Your roster is back.":
        errors.append(tag + f"mine-undo: 'is back' message not visible {b2['mineBack']}")
    notes.append(f"{tag}after roster Undo focus was {b2['focus']!r}")
    names = [n for n, p in zip(b0["mineShown"], b0["minePos"]) if p not in ("K", "DEF")] if len(b0["mineShown"]) == len(b0["minePos"]) else []
    go(page, "find-trade", "v2FindTrade")
    shown = page.evaluate(FIND_MINE)
    if not shown or any(n not in shown for n in names):
        errors.append(tag + f"mine-undo: Find a trade does not show the roster again {shown}")
    go(page, "waivers", "v2Waivers")

    end = page.evaluate(SNAP)
    if end["scrollX"] > 0:
        errors.append(tag + f"sideways scroll {end['scrollX']}px")
    if external:
        errors.append(tag + f"requests left the local server during Clear/Undo: {external[:3]}")
    return errors


def run_checks(mutant=None, viewports=None):
    """Returns (errors, notes, markers): the failed checks, observations, and the mutant marker each page reported."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors, notes, markers = [], [], []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports or [tuple(v) for v in FIXTURE["viewports"]]:
                tag = f"[{width}px] "
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors, external = [], []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.on("request", lambda r: external.append(r.url) if not r.url.startswith(("http://127.0.0.1", "data:", "blob:", "about:")) else None)
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if mutant:
                    context.route("**/v2/waivers.js*", functools.partial(_serve, mutant, "text/javascript"))
                page.goto(base, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueCurveControls && window.TradeValueCurveControls.getAllRows().length && window.TradeValueWorkspace && window.TradeValueWorkspace.store", timeout=60000)
                seed = page.evaluate(SEED, FIXTURE)
                page.goto("about:blank")
                page.goto(base + "#waivers", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.getElementById('v2WaiversHeadline') && !document.getElementById('v2Waivers').hidden"
                                       " && document.querySelectorAll('#v2WaiversTable tbody tr.v2-wv-main, #v2WaiversOut .v2-wv-cards li').length > 0", timeout=60000)
                page.wait_for_timeout(300)
                markers.append(page.evaluate("() => window.__waiversMutant || null"))
                try:
                    errors += check(page, tag, seed, external, notes)
                except Exception as exc:   # a step could not run: keep the checks that already failed
                    errors.append(tag + f"a step could not run: {str(exc)[:160]}")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors, notes, markers


def mutate(js, old, new, name):
    if js.count(old) != 1:
        raise AssertionError(f"mutation anchor for {name!r} is stale or not unique ({js.count(old)} matches)")
    return js.replace(old, new, 1) + f"\n;window.__waiversMutant = {json.dumps(name)};\n"


# name -> (anchor in waivers.js, replacement, the assertion it must fail)
MUTANTS = {
    "candidate clear calls roster clear": ("      stores[target].set([]);\n", "      stores.mine.set([]);\n", "cands-clear: roster changed"),
    "undo restores the other list": ("        stores[target].set(before);\n", '        stores[target === "mine" ? "cands" : "mine"].set(before);\n', "cands-undo: candidates not restored"),
    "roster undo writes into candidates": ("        stores[target].set(before);\n", "        (target === \"mine\" ? stores.cands : stores[target]).set(before);\n", "mine-undo: roster not restored exactly"),
    "roster clear focuses before the input unfolds": ("      if (target === \"mine\") renderSummary();\n", "", "mine-clear: focus was"),
    "roster undo leaves focus to the fold": ("          S.focusAfterUndo = true;\n", "", "mine-undo: focus was"),
    "roster undo message inside the folded input": ("          S.backSig = rosterSig(before);\n", "", "mine-undo: 'is back' message not visible"),
}


class WaiversClearIsolationRenderTests(unittest.TestCase):
    maxDiff = None

    def test_clear_and_undo_keep_each_list_to_itself(self):
        errors, notes, markers = run_checks()
        for line in notes:
            print("note:", line, file=sys.stderr)
        self.assertEqual(markers, [None] * len(FIXTURE["viewports"]), "the baseline run served a mutant")
        self.assertEqual(errors, [])

    def test_guard_fails_on_source_mutants(self):
        js = WAIVERS_JS.read_text(encoding="utf-8")
        for name, (old, new, expected) in MUTANTS.items():
            with self.subTest(mutation=name):
                body = mutate(js, old, new, name)
                errors, _, markers = run_checks(body, viewports=[tuple(FIXTURE["mutant_viewport"])])
                self.assertEqual(markers, [name], f"mutant {name!r} was not the file the page ran")
                self.assertTrue(any(expected in e for e in errors), f"{name!r} did not fail {expected!r}: {errors}")
                print(f"killed: {name!r} by {[e for e in errors if expected in e]}", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
