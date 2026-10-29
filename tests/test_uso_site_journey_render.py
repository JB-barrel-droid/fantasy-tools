"""JEG-1240 / JEG-1264: the USO-shape league journey on the built site, in Chromium.

The league: tests/fixtures/uso_site_journey/league.json, 12 teams, half PPR, QB 1, RB 2, WR 3, TE 1, W/R/T 1, BN 5, K, DEF.
Only the shape is USO's (recorded in #1105 from the league settings, 2026-10-29). The rosters are a synthetic snake draft
of real player keys with Jaxon Smith-Njigba (3247) on the user's team; no USO roster, name or note is in it. Values are
whatever the built page publishes for the week it is pinned to, never frozen here. The Node contract on the same journey
is tests/test_uso_site_journey_contract.py.

journey() drives the page in stages and records, for each stage, whether the destination was read or what blocked it.
Every comparison reads both ends off the page: the league settings, the value basis (DDFOverrides.shareParams), the
source availability (TradeValueCurveControls.getSourceInfo, in the JEG-1259 {status, reason, version} shape), the bench
level (#v2LgLevelCounts on the league page, else a data-bench-level marker inside the view the stage reads: #v2FindLeague,
#v2Compare or #v2FindTrade; no marker inside that view reads modeled), both rosters, the package,
each player's DDF Value, both sides' starter gains, and the starters and bench by position from the lineup tables the
page draws. Stages, for an equal and a throw-in candidate the league page itself found sending JSN:

  league panel         ?trade= opened and reloaded on the league page
  league -> Compare    the panel's own "Open in Compare a trade" link
  Compare reload       the same trade after a reload, not Compare's default
  pair finder          Find a trade with the two saved teams chosen in its pickers; the package must be listed in a group,
                       ticked exactly, with the same values, gains and starters by position (the pair finder draws no
                       bench rows, so its readout is compared on starters)
  pair link elsewhere  the pair finder's own share link (encodeFinderHash plus DDFOverrides.shareLink, as its Copy link
                       button builds it) opened on another device
  Compare elsewhere    Compare's own address opened on another device

Another device is a fresh browser context with its own state: PPR, 10 teams, WR 2, BN 7, a FantasyCalc-only value basis,
and a saved league whose "my team" is Team 05. A link that carries the trade's context shows the origin's settings, basis,
rosters and numbers there; one that does not shows this device's.

A HarnessError means the test could not drive the page (a script, wait or selector failed outside a destination read). It
is never counted as a finding. A bench-level scope that matches no element is HarnessError code level-scope-missing, never
a silent modeled (JEG-1304: the scopes were route hashes that matched nothing, so every destination read modeled). test_guard_fails_on_a_link_without_get runs the journey on the build and on a copy whose
league link drops get=, requires both to read every stage, and requires the mutant's new codes to include
package-changed on league -> Compare and to be only package loss and its consequences.

What this does not assert: that JSN's trades are Natural fits, or that any trade passes a viability gate.

Expected on main (2026-10-29), from reading the source, not observed (no Chromium here): the league link carries only
give= and get=, so Compare picks its default opponent (team-substituted unless that is the trade's team) and cannot draw
both lineups (gains-missing, readout-missing); Compare's address carries no rosters, so another device shows its own saved
teams (team-substituted). Those are JEG-1259's (#1086). After #1105 the league page prices from league levels and Compare
from the modeled bench (level-changed).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
LEAGUE = ROOT / "tests" / "fixtures" / "uso_site_journey" / "league.json"
CONTRACT = ROOT / "tests" / "node" / "uso_site_journey_contract.cjs"
TOL = "0.051"   # the page shows one decimal

# Another device's own state (the Node contract's other device, less the source the browser cannot switch off).
FOREIGN = {"settings": {"scoring": "ppr", "teams": 10, "roster": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 7}},
           "basis": {"mode": "single", "source": "fantasycalc"}, "mine": 4}
FOREIGN_INIT = ("try { localStorage.setItem('ddf-v2-value-overrides', "
                + json.dumps(json.dumps({"v": 2, "basis": FOREIGN["basis"], "values": {}, "names": {}})) + "); } catch (e) {}")
# Codes that losing the package can cause downstream; the guard allows these beside package-changed and nothing else.
PACKAGE_LOSS = {"package-changed", "value-missing", "gains-missing", "gains-changed", "readout-changed", "readout-missing"}


# The view each stage reads its bench level in (app/v2/shell.html). JEG-1304: these were the route hashes
# (#find-league, #compare-trade, #find-trade), which match no element. LevelScopeTest pins them to shell.html.
LEVEL_SCOPES = {"league": "#v2FindLeague", "compare": "#v2Compare", "pair": "#v2FindTrade"}
SHELL = ROOT / "app" / "v2" / "shell.html"


class HarnessError(Exception):
    """The test could not drive the page: not a finding about the trade."""

    def __init__(self, message, code="harness"):
        super().__init__(message)
        self.code = code


def checked_level(stage: str, read):
    """Raise level-scope-missing when the page's level() found no element for its scope."""
    level = read.get("level") if isinstance(read, dict) else None
    if isinstance(level, dict):
        raise HarnessError(f"{stage}: bench-level scope {level.get('missing')} matches no element", code="level-scope-missing")
    return read


def level_scopes(*scripts: str) -> list[str]:
    """Every scope the in-page scripts pass to level()."""
    import re
    return [m for s in scripts for m in re.findall(r"level\('([^']+)'\)", s)]


def league() -> dict:
    return json.loads(LEAGUE.read_text(encoding="utf-8"))


def differences(origin: dict, dest: dict) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "origin.json", Path(tmp) / "dest.json"
        a.write_text(json.dumps(origin), encoding="utf-8")
        b.write_text(json.dumps(dest), encoding="utf-8")
        out = subprocess.run(["node", str(CONTRACT), "diff", str(a), str(b), TOL], capture_output=True, text=True, timeout=120, cwd=ROOT)
        if out.returncode or not out.stdout.strip():
            raise HarnessError(f"contract diff failed: {out.stderr[-2000:]}")
        return json.loads(out.stdout.strip().splitlines()[-1])["differences"]


@dataclass
class Run:
    stages: list = field(default_factory=list)     # [(stage, "read" | "blocked")]
    problems: list = field(default_factory=list)   # [{stage, code, message}]

    def read(self, stage):
        self.stages.append((stage, "read"))

    def problem(self, stage, code, message):
        self.problems.append({"stage": stage, "code": code, "message": message})

    def blocked(self, stage, code, message):
        self.stages.append((stage, "blocked"))
        self.problem(stage, code, message)

    def compare(self, stage, origin, dest):
        self.read(stage)
        for d in differences(origin, dest):
            self.problem(stage, d["code"], d["message"])

    def lines(self) -> list[str]:
        return [f"[{p['stage']}] [{p['code']}] {p['message']}" for p in self.problems]

    def codes(self) -> set:
        return {(p["stage"], p["code"]) for p in self.problems}


# ---------- in-page scripts ----------

SETTINGS = """(s) => { const C = window.TradeValueCurveControls; C.setScoring(s.scoring, false); C.setTeams(s.teams, false);
  Object.entries(s.roster).forEach(([k, v]) => { if (C.getRosterShape()[k] !== v) C.setRosterSpot(k, v); });
  return C.getRosterShape(); }"""

# Read from the page: the settings, value basis, sources and bench level in force; one team as the screen counts it
# (priced players by key; K, DEF and players without a row counted, not valued); the starters and bench by position
# from a drawn lineup table (lineup-comparison.js renderTable rows, or the pair finder's own lineup table).
COMMON = """
  const C = window.TradeValueCurveControls, F = window.TradeValueFinder;
  const have = new Set(C.getAllRows().map(r => String(r.player_key)));
  const settings = () => { const s = C.getState(); return {scoring: s.scoring, teams: s.teams, roster: C.getRosterShape()}; };
  const basis = () => ((window.DDFOverrides && window.DDFOverrides.shareParams && window.DDFOverrides.shareParams()) || {}).basis || null;
  const sources = () => Object.fromEntries(C.getSourceInfo().filter(i => !i.composite).map(i => [i.key, {
    status: i.excludedReason && /^held/i.test(i.excludedReason) ? 'held' : i.available ? 'available' : 'unavailable',
    reason: i.excludedReason || null, version: i.week === undefined || i.week === null ? null : String(i.week)}]));
  const level = scope => { const v = document.querySelector(scope); if (!v) return {missing: scope};
    const m = v.matches('[data-bench-level]') ? v : v.querySelector('[data-bench-level]'); return m ? m.dataset.benchLevel : 'modeled'; };
  const side = team => team ? {id: team.id || null, keys: team.entries.filter(e => !F.isNotEvaluated(e) && have.has(String(e.key))).map(e => String(e.key)).sort(),
    notEvaluated: team.entries.filter(e => F.isNotEvaluated(e) || !have.has(String(e.key))).length} : null;
  const num = t => { const n = parseFloat(String(t || '').replace('\\u2212', '-').replace(/,/g, '')); return Number.isFinite(n) ? n : null; };
  const starters = table => { const tr = table && [...table.querySelectorAll('tbody tr')].find(x => x.dataset.total === 'starters' || x.firstChild.textContent === 'Starters');
    return tr ? [...tr.children].map(c => c.textContent) : null; };
  const who = text => { const s = String(text || '').trim(); return !s || s === 'empty' ? null : s.replace(/ (no value|[\\u2212-]?[\\d,]+\\.\\d)$/, ''); };
  const lineup = (table, col) => { if (!table) return null; const slots = {}, bench = [];
    table.querySelectorAll('tbody tr').forEach(tr => {
      const slot = tr.dataset.slot || (tr.dataset.total ? null : tr.firstChild.textContent.replace(/\\d+$/, ''));
      if (!slot || (!tr.dataset.slot && (slot === 'Starters' || slot === 'Bench'))) return;
      const n = who(tr.children[col].textContent); if (!n) return;
      if (slot === 'Bench') bench.push(n); else (slots[slot] = slots[slot] || []).push(n); });
    Object.values(slots).forEach(l => l.sort()); bench.sort(); return {slots, bench}; };
  const readout = (us, them) => us && them ? {ready: true, us: {before: lineup(us, 1), after: lineup(us, 2)}, them: {before: lineup(them, 1), after: lineup(them, 2)}} : null;
  const gainsOf = (us, them) => { const a = starters(us), b = starters(them);
    return {us: a ? {ddf: num(a[3]), ddfBefore: num(a[1])} : null, them: b ? {ddf: num(b[3])} : null}; };
"""

CANDIDATES = """(focus) => { const res = window.TradeValueLeague.ui.result; if (!res) return null;
  const rows = res.rows;
  const jsn = rows.filter(r => r.give.some(p => String(p.player_key) === focus));
  const pack = r => r && {id: r.id, opponent: r.opponent, opponentId: r.opponentId,
    give: r.give.map(p => String(p.player_key)), get: r.receive.map(p => String(p.player_key)),
    throwIns: r.addedThrowIns || [], unbalanced: Boolean(r.unbalanced)};
  const equal = jsn.find(r => !(r.addedThrowIns || []).length && !r.unbalanced);
  const thrown = jsn.find(r => (r.addedThrowIns || []).length && !(r.addedThrowIns || []).includes('give:' + focus));
  return {count: rows.length, jsn: jsn.length, opponents: new Set(jsn.map(r => r.opponentId)).size, equal: pack(equal), thrown: pack(thrown),
    myTeamId: window.TradeValueWorkspace.store.get().myTeamId}; }"""

ORIGIN = "([id]) => {" + COMMON + """
  const ws = window.TradeValueWorkspace.store.get();
  const r = window.TradeValueLeague.ui.result.rows.find(x => x.id === id);
  const p = document.getElementById('v2LgOppPanel');
  if (!r || !p || p.dataset.oppId !== id) return {error: `panel for ${id} is not open (open: ${p && p.dataset.oppId})`};
  const values = {};
  r.give.concat(r.receive).forEach(x => { const v = x.values && x.values.ddf_value; values[String(x.player_key)] = {ddf: Number.isFinite(v) ? v : null}; });
  const table = s => p.querySelector(`[data-side="${s}"] table[data-view="DDF Value"]`);
  return {settings: settings(), basis: basis(), sources: sources(), level: document.getElementById('v2LgLevelCounts') ? 'league' : level('""" + LEVEL_SCOPES["league"] + """'),
    mine: side(ws.teams.find(t => t.id === ws.myTeamId)), theirs: side(ws.teams.find(t => t.id === r.opponentId)),
    give: r.give.map(x => String(x.player_key)), get: r.receive.map(x => String(x.player_key)), values,
    gains: gainsOf(table('Your team'), table('Their team')), readout: readout(table('Your team'), table('Their team'))}; }"""

# Compare draws one series per player (the one shown) and DDF-only lineups.
DEST = "() => {" + COMMON + """
  const ws = window.TradeValueWorkspace.store.get();
  const team = id => ws.teams.find(t => t.id === id) || null;
  const mineSel = document.getElementById('v2CMyTeam'), theirSel = document.getElementById('v2CTheirTeam');
  const listed = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)].map(li => li.dataset.playerKey);
  const give = listed('v2GivePlayers'), get = listed('v2GetPlayers');
  const values = {};
  give.concat(get).forEach(k => { const li = document.querySelector(`#v2GivePlayers li[data-player-key="${CSS.escape(k)}"], #v2GetPlayers li[data-player-key="${CSS.escape(k)}"]`);
    const v = li && li.querySelector('.v2-trade-value');
    values[k] = v && v.dataset.source === 'ddf_value' ? {ddf: num(v.textContent)} : {ddf: null, shown: v ? v.dataset.source : null}; });
  const card = document.getElementById('v2CConstruction');
  const panels = [...document.querySelectorAll('#v2CConstructionBody .v2-cconstruction-panels > section')];
  const ready = card && card.dataset.ready === 'true';
  const us = ready && panels[0] ? panels[0].querySelector('table') : null, them = ready && panels[1] ? panels[1].querySelector('table') : null;
  return {settings: settings(), basis: basis(), sources: sources(), level: level('""" + LEVEL_SCOPES["compare"] + """'),
    mine: side(team(mineSel && mineSel.value)), theirs: side(team(theirSel && theirSel.value)), give, get, values,
    gains: gainsOf(us, them), readout: readout(us, them),
    note: (document.getElementById('v2CRosterStatus') || {}).textContent || '', hash: location.hash}; }"""

# The pair finder: find the group that lists every player of the package, tick exactly the package (check first, then
# uncheck, so the last given player is never the one left), and read what it shows. A team shown from a saved pick keeps
# its saved ID; rosters opened from a link have none.
PAIR = "([give, get]) => {" + COMMON + """
  const ui = F.ui;
  const pickerTeam = (entries, id) => ({id: (document.getElementById(id) || {}).value || null, entries});
  const base = {settings: settings(), basis: basis(), sources: sources(), level: level('""" + LEVEL_SCOPES["pair"] + """'),
    mine: side(pickerTeam(ui.getMine(), 'v2FindSavedTeam')), theirs: side(pickerTeam(ui.getTheirs(), 'v2FindTheirSavedTeam'))};
  const groups = [...document.querySelectorAll('#v2FindList li.v2-find-group')];
  const want = new Set(give.concat(get));
  const heavy = li => (li.dataset.group || '').split(',').filter(Boolean);
  const keysIn = li => new Set([...li.querySelectorAll('input[data-key]')].map(i => i.dataset.key).concat(heavy(li)));
  const li = groups.find(g => { const k = keysIn(g); return [...want].every(x => k.has(x)) && heavy(g).every(x => want.has(x)); });
  if (!li) return {...base, listed: false, groups: groups.length, give: [], get: [], values: {}, gains: {}, readout: null};
  const boxes = [...li.querySelectorAll('input[data-key]')];
  boxes.filter(i => want.has(i.dataset.key) && !i.checked && !i.disabled).forEach(i => i.click());
  boxes.filter(i => !want.has(i.dataset.key) && i.checked && !i.disabled).forEach(i => i.click());
  const inSet = (title, i) => ((i.closest('fieldset') && i.closest('fieldset').querySelector('legend') || {}).textContent || '') === title;
  const g = boxes.filter(i => i.checked && inSet('You give', i)).map(i => i.dataset.key);
  const r = heavy(li).concat(boxes.filter(i => i.checked && !inSet('You give', i)).map(i => i.dataset.key));
  const values = {};
  boxes.forEach(i => { const m = /\\(value ([^)]*)\\)$/.exec(i.getAttribute('aria-label') || ''); values[i.dataset.key] = {ddf: m ? num(m[1]) : null}; });
  const h = heavy(li);
  if (h.length === 1) { const t = li.querySelector('.v2-find-target'); const m = /([\\u2212-]?[\\d,]+\\.\\d)\\s*DDF Value/.exec(t ? t.textContent : ''); values[h[0]] = {ddf: m ? num(m[1]) : null}; }
  const table = title => [...li.querySelectorAll('table.v2-find-lineup')].find(t => (t.querySelector('caption') || {}).textContent === title);
  const us = table('Your best lineup, DDF Value'), them = table('Their best lineup, DDF Value');
  return {...base, listed: true, groups: groups.length, give: g, get: r, values, gains: gainsOf(us, them), readout: readout(us, them)}; }"""

# The link the pair finder's Copy link button makes (copyLink in finder.js), built from the page's own functions.
PAIR_LINK = """() => { const F = window.TradeValueFinder, ui = F.ui, ws = window.TradeValueWorkspace.store.get();
  const s = ws.ui && ws.ui.finderSettings ? ws.ui.finderSettings : {};
  const league = window.TradeValueV2 && window.TradeValueV2.leagueQuery ? window.TradeValueV2.leagueQuery() : '';
  const hash = F.encodeFinderHash({mine: ui.getMine(), theirs: ui.getTheirs(), maxSize: s.maxSize || 2, keepMine: s.keepMine !== false,
    keepTheirs: s.keepTheirs !== false, guardrails: s}, league);
  const ov = window.DDFOverrides; const shared = ov && ov.shareLink ? ov.shareLink(hash) : {hash};
  return location.href.split('#')[0] + shared.hash; }"""

# The lineup math Compare should show for the deal on its screen, on the rosters the league page traded between.
EXPECTED = "([mineId, theirId]) => {" + COMMON + """
  const ws = window.TradeValueWorkspace.store.get();
  const byKey = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const rows = t => t.entries.map(e => byKey.get(String(e.key))).filter(Boolean);
  const listed = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)].map(li => byKey.get(li.dataset.playerKey)).filter(Boolean);
  const give = listed('v2GivePlayers'), get = listed('v2GetPlayers');
  const mine = ws.teams.find(t => t.id === mineId), theirs = ws.teams.find(t => t.id === theirId);
  const us = F.rosterImpact(rows(mine), give, get, C.getRosterShape(), 'ddf_value');
  const them = F.rosterImpact(rows(theirs), get, give, C.getRosterShape(), 'ddf_value');
  return {us: {ddf: us.starterDelta, ddfBefore: us.before.starterValue}, them: {ddf: them.starterDelta}}; }"""


def _anon(env: dict) -> dict:
    """Another browser has other team ids: compare its rosters by their players."""
    out = json.loads(json.dumps(env))
    for s in ("mine", "theirs"):
        if out.get(s):
            out[s].pop("id", None)
    return out


def _pair_view(origin: dict, shown: dict) -> dict:
    """The origin as the pair finder can show it: the values it prints, starters only (it draws no bench rows), and the
    skill-player rosters it searches (K and DEF are never in it)."""
    out = json.loads(json.dumps(origin))
    out["values"] = {k: v for k, v in out["values"].items() if k in (shown.get("values") or {})}
    for s in ("mine", "theirs"):
        if out.get(s):
            out[s]["notEvaluated"] = (shown.get(s) or {}).get("notEvaluated")
    for s in ("us", "them"):
        for when in ("before", "after"):
            if out.get("readout") and out["readout"].get(s) and out["readout"][s].get(when):
                out["readout"][s][when]["bench"] = (((shown.get("readout") or {}).get(s) or {}).get(when) or {}).get("bench")
    return out


class _Journey:
    def __init__(self, browser, base, overrides=None):
        from tests._league_render import SEED, open_page, wait_opps
        self.browser, self.base, self.overrides = browser, base, overrides
        self.SEED, self.open_page, self.wait_opps = SEED, open_page, wait_opps
        self.fx = league()
        self.errors: list[str] = []

    @staticmethod
    def timeout():
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        return PlaywrightTimeout

    def eval(self, page, stage, script, arg=None):
        try:
            return page.evaluate(script, arg)
        except Exception as exc:
            raise HarnessError(f"{stage}: in-page script failed: {exc}") from exc

    def view(self, page, stage, script, arg=None):
        """A destination or origin read; a bench-level scope that matches nothing is a harness failure, not modeled."""
        return checked_level(stage, self.eval(page, stage, script, arg))

    def page(self, foreign=False):
        stage = "another device" if foreign else "league page"
        try:
            context = self.browser.new_context(viewport={"width": 1366, "height": 768}) if foreign else None
            page = self.open_page(self.browser, self.base, overrides=self.overrides, errors=self.errors, context=context,
                                  init_script=FOREIGN_INIT if foreign else None, tag=f"{stage}: ")
            page.evaluate(SETTINGS, FOREIGN["settings"] if foreign else self.fx["settings"])
            page.evaluate(self.SEED, [self.fx, FOREIGN["mine"] if foreign else self.fx["myTeamIndex"]])
            self.wait_opps(page, timeout=120000)
        except Exception as exc:
            raise HarnessError(f"{stage}: could not open and seed the page: {exc}") from exc
        return page

    def open_league_pick(self, page, pick) -> None:
        trade = "~".join(quote(x, safe="") for x in [pick["opponent"], ",".join(pick["give"]), ",".join(pick["get"])])
        try:
            page.evaluate("(h) => { location.hash = h; }", f"#find-league?trade={trade}")
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=30000)
            self.wait_opps(page, timeout=120000)
            page.wait_for_timeout(300)
        except Exception as exc:
            raise HarnessError(f"league panel: could not reopen the league page on ?trade=: {exc}") from exc

    def follow_compare_link(self, page, pick):
        """Show the trade's details on the league page and click its own Open in Compare a trade link; returns its href."""
        self.eval(page, "league -> Compare", "() => { const more = document.getElementById('v2LgOppsAll'); if (more) more.click(); }")
        page.wait_for_timeout(200)
        clicked = self.eval(page, "league -> Compare", """(id) => { const b = document.querySelector(`[data-details-for="${CSS.escape(id)}"]`);
          if (!b) return false; if (b.getAttribute('aria-expanded') !== 'true') b.click(); return true; }""", pick["id"])
        if not clicked:
            return None
        page.wait_for_timeout(200)
        return self.eval(page, "league -> Compare", """(id) => { const a = [...document.querySelectorAll(`tr[data-detail-for="${CSS.escape(id)}"] a`)].find(x => x.textContent === 'Open in Compare a trade');
          if (!a) return null; const href = a.getAttribute('href'); a.click(); return href; }""", pick["id"])

    def wait_compare(self, page, give=None, get=None) -> bool:
        """Compare has drawn a trade: its address, the lists (exact counts when given) and the lineup card's verdict."""
        try:
            page.wait_for_function("""([g, r]) => { const n = id => document.querySelectorAll(`#${id} li[data-player-key]`).length;
              const card = document.getElementById('v2CConstruction');
              return location.hash.startsWith('#compare-trade') && (g === null ? n('v2GivePlayers') > 0 : n('v2GivePlayers') === g) &&
                (r === null || n('v2GetPlayers') === r) && card && card.dataset.ready !== undefined; }""", arg=[give, get], timeout=30000)
        except self.timeout():
            return False
        page.wait_for_timeout(300)
        return True

    def wait_pair(self, page) -> bool:
        """The pair finder has run: its list (or its no-trades note) is out, and every group is shown."""
        try:
            page.wait_for_function("() => { const out = document.getElementById('v2FindOut'); return out && !out.hidden && out.textContent.trim().length > 0; }", timeout=60000)
        except self.timeout():
            return False
        for _ in range(20):
            if not self.eval(page, "pair finder", "() => { const b = document.getElementById('v2FindMoreGroups'); if (!b) return false; b.click(); return true; }"):
                break
            page.wait_for_timeout(100)
        page.wait_for_timeout(300)
        return True

    def open_pair(self, page, mine_id, their_id) -> bool:
        try:
            page.evaluate("() => { location.hash = '#find-trade'; }")
            page.wait_for_function("() => document.getElementById('v2FindGo') && document.getElementById('v2FindSavedTeam') && document.getElementById('v2FindTheirSavedTeam')", timeout=30000)
            page.select_option("#v2FindSavedTeam", mine_id)
            page.select_option("#v2FindTheirSavedTeam", their_id)
            page.click("#v2FindGo")
        except Exception as exc:
            raise HarnessError(f"pair finder: could not choose the saved teams and run the search: {exc}") from exc
        return self.wait_pair(page)


def journey(browser, base, overrides=None) -> Run:
    """Every stage of the journey, read or blocked, and every difference found; HarnessError if the page cannot be driven."""
    J = _Journey(browser, base, overrides)
    run = Run()
    page = J.page()
    focus = J.fx["focus"]["key"]
    found = J.eval(page, "league page", CANDIDATES, focus)
    if not found or not found["count"]:
        run.blocked("league page", "no-candidates", "the league page found no trade opportunities on the USO-shape league")
        return run
    if not found["jsn"]:
        run.blocked("league page", "not-discoverable", f"no opportunity sends {J.fx['focus']['name']} ({found['count']} found)")
        return run
    run.read("league page")
    for label in ("equal", "thrown"):
        pick = found[label]
        if not pick:
            run.blocked(f"{label}: pick", "candidate-missing", f"no {label} candidate sends JSN among {found['jsn']}")
            continue
        tag = f"{label} {pick['id']}"
        if sorted(pick["give"]) != sorted(pick["id"].split("|")[1].split(",")) or sorted(pick["get"]) != sorted(pick["id"].split("|")[2].split(",")):
            run.problem(f"{tag}: pick", "package-changed", "the row id and its package disagree")
        stage = f"{tag}: league panel"
        J.open_league_pick(page, pick)
        origin = J.view(page, stage, ORIGIN, [pick["id"]])
        if origin.get("error"):
            run.blocked(stage, "panel-missing", f"{origin['error']} after opening ?trade= and reloading")
            continue
        run.read(stage)
        if not origin["readout"]:
            run.problem(stage, "readout-missing", "the league panel draws no starters and bench for a side")
        stage = f"{tag}: league -> Compare"
        href = J.follow_compare_link(page, pick)
        if not href:
            run.blocked(stage, "link-missing", "the league page's Open in Compare a trade link was not there to follow")
            continue
        if not J.wait_compare(page):
            run.blocked(stage, "trade-not-opened", f"Compare did not draw the trade from {href}")
            continue
        run.compare(stage, origin, J.view(page, stage, DEST))
        share = J.eval(page, stage, "() => location.href")
        stage = f"{tag}: Compare reload"
        try:
            page.reload(wait_until="networkidle")
        except Exception as exc:
            raise HarnessError(f"{stage}: reload failed: {exc}") from exc
        if J.wait_compare(page):
            run.compare(stage, origin, J.view(page, stage, DEST))
        else:
            run.blocked(stage, "trade-not-opened", "Compare did not draw the trade after a reload")
        stage = f"{tag}: pair finder"
        if not J.open_pair(page, found["myTeamId"], pick["opponentId"]):
            run.blocked(stage, "pair-not-run", "the pair finder showed no result for the two saved teams")
        else:
            shown = J.view(page, stage, PAIR, [pick["give"], pick["get"]])
            if not shown["listed"]:
                run.blocked(stage, "package-not-listed", f"none of the pair finder's {shown['groups']} groups lists {pick['id']}")
            else:
                run.compare(stage, _pair_view(origin, shown), shown)
            pair_link = J.eval(page, stage, PAIR_LINK)
            arrival(J, run, f"{tag}: pair link elsewhere", pair_link, origin, pair=True, pick=pick)
        arrival(J, run, f"{tag}: Compare elsewhere", share, origin)
    page.close()
    for error in J.errors:
        run.problem("page", "page-error", error)
    return run


def arrival(J, run, stage, url, origin, pair=False, pick=None):
    """Open a link on another device (its own settings, basis and saved league) and compare what it shows."""
    other = J.page(foreign=True)
    try:
        other.goto(url, wait_until="networkidle")
        other.reload(wait_until="networkidle")
    except Exception as exc:
        other.context.close()
        raise HarnessError(f"{stage}: could not open the link: {exc}") from exc
    if pair:
        if not J.wait_pair(other):
            run.blocked(stage, "pair-not-run", "the pair finder link ran no search on another device")
        else:
            shown = J.view(other, stage, PAIR, [pick["give"], pick["get"]])
            if shown["listed"]:
                run.compare(stage, _anon(_pair_view(origin, shown)), _anon(shown))
            else:
                run.blocked(stage, "package-not-listed", f"none of the pair finder's {shown['groups']} groups lists {pick['id']} on another device")
    elif J.wait_compare(other):
        run.compare(stage, _anon(origin), _anon(J.view(other, stage, DEST)))
    else:
        run.blocked(stage, "trade-not-opened", "Compare's address did not draw the trade on another device")
    other.context.close()


def unequal_deal(browser, base) -> list[str]:
    """Compare: take the throw-in out of a page-found JSN trade; the 2-for-1 keeps its package and lineup math."""
    J = _Journey(browser, base)
    problems: list[str] = []
    page = J.page()
    found = J.eval(page, "league page", CANDIDATES, J.fx["focus"]["key"])
    pick = found and found["thrown"]
    if not pick:
        page.close()
        return ["no throw-in candidate sends JSN, so no explicit unequal deal can be derived"]
    side, key = pick["throwIns"][0].split(":", 1)
    give = [k for k in pick["give"] if not (side == "give" and k == key)]
    get = [k for k in pick["get"] if not (side == "receive" and k == key)]
    if len(give) == len(get):
        page.close()
        return [f"removing {pick['throwIns'][0]} left an equal deal {give} for {get}"]
    J.open_league_pick(page, pick)
    if not J.follow_compare_link(page, pick) or not J.wait_compare(page):
        page.close()
        return ["the league page's Open in Compare a trade link did not open the trade"]
    J.eval(page, "unequal", """(k) => { const li = document.querySelector(`#v2GivePlayers li[data-player-key="${CSS.escape(k)}"], #v2GetPlayers li[data-player-key="${CSS.escape(k)}"]`);
      li.querySelector('button.v2-remove').click(); }""", key)
    for when in ("after removing the throw-in", "after a reload"):
        if not J.wait_compare(page, len(give), len(get)):
            problems.append(f"[unequal {when}] [package-changed] Compare does not show {len(give)} for {len(get)}")
            break
        dest = J.view(page, "unequal", DEST)
        if sorted(dest["give"]) != sorted(give) or sorted(dest["get"]) != sorted(get):
            problems.append(f"[unequal {when}] [package-changed] package {dest['give']} for {dest['get']}, wanted {give} for {get}")
        if (dest["theirs"] or {}).get("id") != pick["opponentId"]:
            problems.append(f"[unequal {when}] [team-substituted] Compare shows {(dest['theirs'] or {}).get('id')} as their team, the trade was with {pick['opponent']}")
        want = J.eval(page, "unequal", EXPECTED, [found["myTeamId"], pick["opponentId"]])
        for s in ("us", "them"):
            got = dest["gains"][s]
            if not got:
                problems.append(f"[unequal {when}] [gains-missing] Compare draws no {s} lineup: {dest['note']}")
                continue
            for v, x in want[s].items():
                if got.get(v) is None or abs(got[v] - x) > float(TOL):
                    problems.append(f"[unequal {when}] [gains-changed] {s} {v} shows {got.get(v)}, lineup math says {round(x, 2)}")
        if not dest["readout"]:
            problems.append(f"[unequal {when}] [readout-missing] Compare draws no starters and bench for a side")
        if when == "after removing the throw-in":
            page.reload(wait_until="networkidle")
    page.close()
    return problems + J.errors


class LevelScopeTest(unittest.TestCase):
    """JEG-1304: every bench-level read is scoped to a view that exists. Runs without a browser."""

    def test_every_level_scope_is_an_element_in_the_shell(self):
        shell = SHELL.read_text(encoding="utf-8")
        scopes = level_scopes(ORIGIN, DEST, PAIR)
        self.assertEqual(len(scopes), 3, f"each of ORIGIN, DEST and PAIR reads one bench level: {scopes}")
        missing = [s for s in scopes if not (s.startswith("#") and f'id="{s[1:]}"' in shell)]
        self.assertEqual(missing, [], "bench-level scopes that match no element in app/v2/shell.html")

    def test_a_missing_scope_is_its_own_harness_code(self):
        with self.assertRaises(HarnessError) as caught:
            checked_level("Compare", {"level": {"missing": "#compare-trade"}})
        self.assertEqual(caught.exception.code, "level-scope-missing")
        self.assertIn("#compare-trade", str(caught.exception))
        self.assertEqual(checked_level("Compare", {"level": "modeled"}), {"level": "modeled"})


class UsoSiteJourneyRenderTest(unittest.TestCase):
    def test_level_reads_the_rendered_view(self):
        """In the browser: each real view reads a level string; a scope matching nothing raises level-scope-missing."""
        from tests._league_render import browser_on_build
        probe = "(scopes) => {" + COMMON + " return scopes.map(s => ({level: level(s)})); }"
        with browser_on_build() as (browser, base):
            J = _Journey(browser, base)
            page = J.page()
            reads = J.eval(page, "probe", probe, list(LEVEL_SCOPES.values()) + ["#compare-trade"])
            page.close()
        for scope, read in zip(LEVEL_SCOPES.values(), reads):
            self.assertIsInstance(checked_level(scope, read)["level"], str, scope)
        with self.assertRaises(HarnessError) as caught:
            checked_level("#compare-trade", reads[-1])
        self.assertEqual(caught.exception.code, "level-scope-missing")

    def test_journey_keeps_the_trade_context(self):
        from tests._league_render import browser_on_build
        with browser_on_build() as (browser, base):
            run = journey(browser, base)
        self.assertEqual(run.lines(), [])
        self.assertTrue(run.stages and all(state == "read" for _, state in run.stages), run.stages)

    def test_unequal_deal_keeps_its_package(self):
        from tests._league_render import browser_on_build
        with browser_on_build() as (browser, base):
            self.assertEqual(unequal_deal(browser, base), [])

    def test_guard_fails_on_a_link_without_get(self):
        """Dropping get= from the league page's Compare link must be caught as package-changed, and only that loss."""
        from tests._league_render import browser_on_build, source
        body = source("league.js")
        anchor = '&get=${r.receive.map(p => encodeURIComponent(p.player_key)).join(",")}`, text: "Open in Compare a trade"'
        self.assertEqual(body.count(anchor), 2, "mutation anchor is stale")
        broken = body.replace(anchor, '`, text: "Open in Compare a trade"')
        with browser_on_build() as (browser, base):
            baseline = journey(browser, base)
            mutant = journey(browser, base, {"league.js": broken})
        compare = [x for x in baseline.stages if x[0].endswith("league -> Compare")]
        self.assertEqual(len(compare), 2, f"the baseline did not reach Compare for both picks: {baseline.lines()}")
        self.assertEqual([x for x in compare if x[1] != "read"], [], f"the baseline did not read Compare: {baseline.lines()}")
        # The same stages, each read or blocked the same way: the mutant was driven as far as the build was.
        self.assertEqual(mutant.stages, baseline.stages, f"the mutant did not reach the same stages: {mutant.lines()}")
        self.assertFalse({c for s, c in baseline.codes() if s.endswith("league -> Compare")} & {"package-changed"},
                         f"package-changed already on the build, so the guard would prove nothing: {baseline.lines()}")
        new = mutant.codes() - baseline.codes()
        self.assertIn("package-changed", {c for s, c in new if s.endswith("league -> Compare")}, mutant.lines())
        self.assertEqual({c for _, c in new} - PACKAGE_LOSS, set(), f"the mutant also lost something else: {sorted(new)}")


if __name__ == "__main__":
    unittest.main()
