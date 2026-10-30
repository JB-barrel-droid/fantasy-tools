"""v2 Compare a trade: waterfall, verdict, layout and example trade, rendered (JEG-468 / JEG-469).

Builds dist/v2 into a temp copy of the built dist/ and loads /v2/#compare-trade
headless. With "Player values shown" set to a series that is NOT the ranking
series, and a 2-for-2 trade from a shared link, checks against
window.TradeValueCurveControls.getAllRows():

  * waterfall (every row of "Difference by source & method"): give steps first,
    largest first, each step's value is minus that player's engine value; then
    receive steps, largest first, plus the engine value; every step's text
    alternative carries the running total; the landing is Receive − give;
  * one shared scale: every row's waterfall has the same lo / hi, equal to the
    largest cumulative extent across rows (0 included);
  * missing: with a player who lacks a series, that row has a "no value" step
    and no landing bar (never a 0);
  * verdict (JEG-467): with DDF Value shown, the headline names DDF Value and
    says "you win by" / "you lose by" / "even" from DDF Value's engine sums,
    even with "Player values shown" switched to another series; the text names
    every complete source that sees it the other way (JEG-541: one projection
    is simulated to disagree, SIMULATE_DISSENT, so this check always has a
    source to name); the verdict card's
    waterfall is DDF Value's, the same steps as its table row;
  * layout: at 1440×900 and 1366×768 both sides, the verdict card and its
    waterfall are on screen without scrolling, and the per-source table starts
    directly below; no horizontal scroll at 1100 or 390, nor at 1024-1439 in DejaVu Sans, the face GitHub's
    runner falls back to without Inter (JEG-1056; the 1280 squeeze -- GAP-WATERFALL-NAV-1280-SQUEEZE -- went
    with JEG-1106's menu, so the real-page check now runs 1024-1439 -- JEG-1113;
    test_wide_font_guard_fails_on_broken_nav serves a menu that opens in the bar and requires it to be caught,
    using a baseline-vs-mutation comparison at 1280);
  * example: with no player added, the start button draws an example (1-for-1 up to 2-for-2 since JEG-1191), marked "Example",
    and the address keeps no trade.
  * example fold (JEG-1112): the EXAMPLE state itself, with no trade seeded (it is live data: the same page a new
    visitor sees), ends with both sides, the verdict card and the totals row under each side at least
    EXAMPLE_FOLD_MARGIN px above the fold at 1366x768 and 1440x900, in the browser's own fonts and in DejaVu Sans
    (CI's face); the seeded scenarios below measure a linked trade, whose header is shorter, and missed the
    27 px overrun the first live view had. test_example_fold_guard_fails_on_the_old_header serves the
    uncompacted header and requires the check to fail.

Discrimination: test_guard_fails_on_broken_builds serves a per-row scale, the
verdict following the picker instead of DDF Value, a verdict naming no source, no example,
the landing drawn on incomplete rows, the 3-column layout removed, and the short-viewport
wide verdict column removed (JEG-917), and
requires the checks to fail on each, and prints one GUARD CAUGHT / NOT CAUGHT line per
mutation to stderr so the make validate log shows the result (JEG-1056: the short-viewport mutation
was once not caught because the pinned fixture wraps the same at both column widths).
"""
from __future__ import annotations

import contextlib
import functools
import re
import http.server
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
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
TRADE_JS = ROOT / "app" / "v2" / "trade.js"

# JEG-1056: pin values for the test-picked trade so data bakes do not move the column height.
# PICK selects from the engine rows sorted by ESPN. By seeding the top players with fixed values
# (small, spread apart, only one source dissenting with DDF Value), the trade PICK produces is always
# the same shape: short verdict text, short deal card, and short waterfalls that fit 1366x768.
# Correctness checks still compare DOM against the (seeded) engine, so they remain strong.
# SEED_VALUES wraps getAllRows/getRows/getPlayer to replace values for players in the top-12 by
# ESPN with a synthetic fixture, leaving all other players untouched.
SEED_VALUES = """() => {
  const C = window.TradeValueCurveControls;
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const rows = C.getAllRows();
  const byEspn = rows.filter(r => r.values && fin(r.values.espn))
    .sort((a, b) => b.values.espn - a.values.espn);
  // Build a per-player patch map for the top 12.
  // The 13th player's ESPN sets the floor: seeded values start above it so PICK still
  // selects from the patched pool. Values spread 2 points apart. Other sources are close
  // to ESPN so the verdict text is short (few dissenters). ddf_value is slightly higher
  // than ESPN so the net is a small DDF Value win. One source (usatoday) is offset so
  // SIMULATE_DISSENT finds a natural dissenter.
  const floor = byEspn.length > 12 ? byEspn[12].values.espn : 10;
  const patches = {};
  for (let i = 0; i < Math.min(12, byEspn.length); i++) {
    const r = byEspn[i];
    const base = floor + 2 * (12 - i);   // top player gets floor + 24
    const v = {};
    for (const k of Object.keys(r.values)) {
      if (!fin(r.values[k])) continue;
      // PICK takes [0,5] as give, [2,3] as receive. To produce a DDF Value loss (shorter verdict
      // and deal card text that fits 1366x768): boost positions 0 and 5 in ddf_value. This makes
      // give ddf total > recv ddf total, so the verdict says "you lose" (the receiver gives more).
      const ddfBoost = (i === 0 || i === 5) ? 3 : 0;
      if (k === 'espn') v[k] = base;
      else if (k === 'ddf_value') v[k] = base + 1.5 + ddfBoost;
      else if (k === 'usatoday') v[k] = base + (i < 3 ? 4 : -2);
      else if (k === 'ddf_value_charts') v[k] = base + 1.5 + ddfBoost;
      else if (k === 'ddf_value_projections') v[k] = base + 1.0 + ddfBoost;
      else v[k] = base + 0.5;
    }
    patches[String(r.player_key)] = v;
  }
  const patchRow = r => {
    if (!r || !r.values) return r;
    const key = String(r.player_key);
    if (!(key in patches)) return r;
    return {...r, values: {...r.values, ...patches[key]}};
  };
  for (const name of ['getAllRows', 'getRows']) {
    const original = C[name].bind(C);
    C[name] = (...args) => original(...args).map(patchRow);
  }
  if (C.getPlayer) {
    const original = C.getPlayer.bind(C);
    C.getPlayer = (...args) => patchRow(original(...args));
  }
  return {patched: Object.keys(patches)};
}"""

# JEG-1112: a SECOND seeded scenario, beside the one above, that takes the other verdict copy. The automated rebuild
# b227f453 made the picked trade a DDF Value win that three charts and DDF Value (projections) see the other way, and the
# win copy for that ("X, Y, Z and W think you lose this trade. A manager who trades off X, Y, Z or W is the likeliest to
# accept.") names every dissenting source twice: the tallest verdict text, +72.8 px over the lose copy, and the one that put
# Compare past the 1366x768 fold. Same top-12 patch as SEED_VALUES (PICK gives ranks 0 and 5, receives 2 and 3, whose base
# values sum alike, so every neutral source nets 0): on the two received players DDF Value is +4 each (win by +8) while the
# three trade charts and DDF Value (projections) are -4 each (each says "you lose"), so five sources are named, twice each.
SEED_VALUES_WIN = """() => {
  const C = window.TradeValueCurveControls;
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const byEspn = C.getAllRows().filter(r => r.values && fin(r.values.espn)).sort((a, b) => b.values.espn - a.values.espn);
  const floor = byEspn.length > 12 ? byEspn[12].values.espn : 10;
  const dissent = ['usatoday', 'fantasycalc', 'fantasypros', 'ddf_value_projections'];
  const patches = {};
  for (let i = 0; i < Math.min(12, byEspn.length); i++) {
    const r = byEspn[i];
    const base = floor + 2 * (12 - i);
    const received = i === 2 || i === 3;
    const v = {};
    for (const k of Object.keys(r.values)) {
      if (!fin(r.values[k])) continue;
      if (received && (k === 'ddf_value' || k === 'ddf_value_charts')) v[k] = base + 4;
      else if (received && dissent.includes(k)) v[k] = base - 4;
      else v[k] = base;
    }
    patches[String(r.player_key)] = v;
  }
  const patchRow = r => (!r || !r.values || !(String(r.player_key) in patches)) ? r
    : {...r, values: {...r.values, ...patches[String(r.player_key)]}};
  for (const name of ['getAllRows', 'getRows']) {
    const original = C[name].bind(C);
    C[name] = (...args) => original(...args).map(patchRow);
  }
  if (C.getPlayer) {
    const original = C.getPlayer.bind(C);
    C.getPlayer = (...args) => patchRow(original(...args));
  }
  return {patched: Object.keys(patches)};
}"""

# The verdict branch each seeded scenario must take (JEG-1112), so a change to the seeds cannot silently swap the copy.
SCENARIO_BRANCH = {True: "lose", "win": "win"}
# The win copy in v2.js (JEG-541), which the copy mutations below rewrite; stale if the line moves.
WIN_AGAINST_COPY = ("text = `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you lose this trade. "
                    "A manager who trades off ${listSeries(v.againstKeys, \"or\")} is the likeliest to accept.`;")

PICK = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows();
  const active = window.TradeValueV2.shown();
  const byEspn = rows.filter(r => Number.isFinite(r.values.espn)).sort((a, b) => b.values.espn - a.values.espn);
  const complete = r => active.every(k => Number.isFinite(r.values[k]));
  const priced = byEspn.filter(complete);
  // Gap must be missing a pointKey source (what the waterfall table actually shows),
  // not just any shown() source.  Player 35 is missing cbsros which is in shown()
  // but NOT in pointKeys, so the waterfall table has no missing step for it.
  const cv = window.TradeValueV2.compare();
  const pk = cv && cv.pointKeys ? cv.pointKeys : active;
  const gap = byEspn.find(r => !pk.every(k => Number.isFinite(r.values[k])) && pk.some(k => Number.isFinite(r.values[k])));
  return {give: [priced[0], priced[5]].map(r => String(r.player_key)),
          receive: [priced[2], priced[3]].map(r => String(r.player_key)), gap: gap ? String(gap.player_key) : null};
}"""

# When all active sources price every player (held sources removed), simulate a gap player by
# nulling one source's value on a spare player, then return that player's key as the gap pick.
# The source dropped is one that appears in the compare page's waterfall table (its pointKeys),
# so the missing-step path is always exercised.
SIMULATE_GAP = """(pick) => {
  const C = window.TradeValueCurveControls;
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const rows = C.getAllRows();
  const taken = new Set([...pick.give, ...pick.receive]);
  // Read the compare page's current point keys from compareView (set after the initial render).
  const cv = window.TradeValueV2.compare();
  if (!cv || !cv.pointKeys || !cv.pointKeys.length) return null;
  const pointKeys = cv.pointKeys;
  const spare = rows.find(r => !taken.has(String(r.player_key)) && pointKeys.every(k => fin(r.values[k])));
  if (!spare) return null;
  const key = String(spare.player_key);
  const dropKey = pointKeys[pointKeys.length - 1];
  for (const name of ['getAllRows', 'getRows']) {
    const original = C[name].bind(C);
    C[name] = (...args) => original(...args).map(r =>
      String(r.player_key) === key ? {...r, values: {...r.values, [dropKey]: null},
        missingReasons: {...(r.missingReasons || {}), [dropKey]: 'Simulated: not enough data to index'}} : r);
  }
  if (C.getPlayer) {
    const original = C.getPlayer.bind(C);
    C.getPlayer = (...args) => { const r = original(...args); if (!r || String(r.player_key) !== key) return r;
      return {...r, values: {...r.values, [dropKey]: null},
        missingReasons: {...(r.missingReasons || {}), [dropKey]: 'Simulated: not enough data to index'}}; };
  }
  return key;
}"""

# JEG-541: the verdict must name every complete source that sees the trade the other way. After
# JEG-508 the picked trade may have no such source on live data, which left that check idle. So one
# shown projection is made to disagree with DDF Value: the engine's row accessors are wrapped to
# raise one player's value in that series on the side DDF Value favours less, by enough to flip its net.
SIMULATE_DISSENT = """(p) => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows();
  const byKey = Object.fromEntries(rows.map(r => [String(r.player_key), r]));
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const net = k => { const vals = p.give.concat(p.receive).map(x => byKey[x].values[k]);
    if (!vals.every(fin)) return null;
    return p.receive.reduce((t, x) => t + byKey[x].values[k], 0) - p.give.reduce((t, x) => t + byKey[x].values[k], 0); };
  const ddf = net('ddf_value');
  if (!fin(ddf) || ddf === 0) return null;
  // Pick a pointKey source (what the waterfall table shows) other than ddf_value;
  // the verdict only names sources that appear as table rows.
  const cv = window.TradeValueV2.compare();
  const candidates = cv && cv.pointKeys ? cv.pointKeys.filter(k => k !== 'ddf_value') : ['espn', 'cbsros', 'razzball'];
  const series = candidates.find(k => window.TradeValueV2.shown().includes(k) && fin(net(k)));
  if (!series) return null;
  const n = net(series);
  if (Math.sign(n) === -Math.sign(ddf)) return {series, already: true};
  const player = ddf > 0 ? p.give[0] : p.receive[0];
  const boost = Math.abs(n) + 5;
  const patch = r => (!r || String(r.player_key) !== player) ? r
    : {...r, values: {...r.values, [series]: r.values[series] + boost}};
  for (const name of ['getAllRows', 'getRows']) {
    const original = C[name].bind(C);
    C[name] = (...args) => original(...args).map(patch);
  }
  if (C.getPlayer) { const original = C.getPlayer.bind(C); C.getPlayer = (...args) => patch(original(...args)); }
  return {series, player, boost};
}"""

READ = """() => {
  const C = window.TradeValueCurveControls;
  const engine = Object.fromEntries(C.getAllRows().map(r => [String(r.player_key), r.values]));
  const wf = box => box ? {lo: Number(box.dataset.lo), hi: Number(box.dataset.hi), name: (box.getAttribute('aria-label') || '').replace(/, step by step from 0$/, ''),
    steps: [...box.querySelectorAll('.v2-wf-step')].map(s => ({side: s.dataset.side, key: s.dataset.playerKey, value: s.dataset.value ?? null,
      missing: s.dataset.missing === 'true', aria: s.getAttribute('aria-label')})),
    land: box.querySelector('.v2-wf-land')?.dataset.net ?? null} : null;
  const rows = [...document.querySelectorAll('#v2CTable tbody tr[data-source]')].map(tr => ({key: tr.dataset.source, wf: wf(tr.querySelector('.v2-wf'))}));
  const box = id => { const n = document.getElementById(id); if (!n || n.hidden) return null; const b = n.getBoundingClientRect();
    return {top: b.top, bottom: b.bottom, left: b.left, right: b.right}; };
  return {engine, shown: document.getElementById('v2CShown').value, rank: C.getState ? null : null,
    rows, verdictTitle: document.getElementById('v2CVerdictTitle').textContent, verdictText: document.getElementById('v2CVerdictText').textContent,
    verdictEyebrow: document.getElementById('v2CVerdictEyebrow').textContent,
    verdictFall: wf(document.querySelector('#v2CVerdictFall:not([hidden]) .v2-wf')),
    give: [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(li => li.dataset.playerKey),
    receive: [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(li => li.dataset.playerKey),
    example: !document.getElementById('v2CExample').hidden ? document.getElementById('v2CExample').textContent : null,
    hash: location.hash,
    boxes: {give: box('v2GiveTitle') && document.querySelector('[data-trade-side="give"]').getBoundingClientRect().toJSON(),
      receive: document.querySelector('[data-trade-side="receive"]').getBoundingClientRect().toJSON(),
      verdict: box('v2CVerdict'), verdictFall: box('v2CVerdictFall'),
      table: document.getElementById('v2CTable').closest('.v2-card').getBoundingClientRect().toJSON()},
    innerHeight, innerWidth, overflow: document.documentElement.scrollWidth - innerWidth};
}"""


def finite(v):
    return isinstance(v, (int, float)) and v == v and abs(v) != float("inf")


def fmt(v):
    return f"{v:.1f}"


def fmt_net(v):
    text = f"{abs(v):.1f}"
    return "0.0" if text == "0.0" else ("+" if v > 0 else "−") + text


def sign(v):
    return 0 if fmt_net(v) == "0.0" else (1 if v > 0 else -1)


def check_waterfalls(snap, pick, expect_missing=False) -> list[str]:
    errors = []
    engine = snap["engine"]
    rows = [r for r in snap["rows"] if r["wf"]]
    if len(rows) != len(snap["rows"]) or not rows:
        return [f"rows without a waterfall: {[r['key'] for r in snap['rows'] if not r['wf']]}"]
    extent_lo, extent_hi = 0.0, 0.0
    saw_missing = False
    for r in rows:
        key, wf = r["key"], r["wf"]
        values = lambda keys: [(k, engine[k].get(key)) for k in keys]
        give, receive = values(pick["give"]), values(pick["receive"])
        missing = [k for k, v in give + receive if not finite(v)]
        want, running, lo, hi = [], 0.0, 0.0, 0.0
        for side, items, d in (("give", give, -1), ("receive", receive, 1)):
            for k, v in sorted([(k, v) for k, v in items if finite(v)], key=lambda kv: -kv[1]):
                running += d * v
                lo, hi = min(lo, running), max(hi, running)
                want.append((side, k, fmt_net(d * v), fmt_net(running)))
        priced = [s for s in wf["steps"] if not s["missing"]]
        have = [(s["side"], s["key"], s["value"]) for s in priced]
        if have != [w[:3] for w in want]:
            errors.append(f"{key}: steps {have} != engine order/values {[w[:3] for w in want]}")
        for s, w in zip(priced, want):
            verb = "Give" if w[0] == "give" else "Receive"
            if not (s["aria"] or "").startswith(verb) or f"{w[2]}, running {w[3]}" not in (s["aria"] or ""):
                errors.append(f"{key}: step text {s['aria']!r} lacks '{w[2]}, running {w[3]}'")
        if missing:
            saw_missing = True
            marked = sorted(s["key"] for s in wf["steps"] if s["missing"])
            if marked != sorted(missing):
                errors.append(f"{key}: missing steps {marked} != players without a value {missing}")
            if wf["land"] is not None:
                errors.append(f"{key}: incomplete row draws a landing bar {wf['land']}")
        else:
            net = sum(v for _, v in receive) - sum(v for _, v in give)
            if wf["land"] != fmt_net(net):
                errors.append(f"{key}: landing {wf['land']} != Receive − give {fmt_net(net)}")
            lo, hi = min(lo, net), max(hi, net)
        extent_lo, extent_hi = min(extent_lo, lo), max(extent_hi, hi)
    scales = {(round(r["wf"]["lo"], 6), round(r["wf"]["hi"], 6)) for r in rows}
    if len(scales) != 1:
        errors.append(f"rows are not on one shared scale: {scales}")
    elif abs(rows[0]["wf"]["lo"] - extent_lo) > 1e-6 or abs(rows[0]["wf"]["hi"] - extent_hi) > 1e-6:
        errors.append(f"shared scale {scales} != largest cumulative extent {extent_lo}..{extent_hi}")
    if expect_missing and not saw_missing:
        errors.append("no row had a missing value; the missing path went unchecked")
    return errors


def check_verdict(snap, pick, branch=None) -> list[str]:
    engine = snap["engine"]
    names = {r["key"]: r["wf"]["name"] for r in snap["rows"] if r["wf"]}
    # JEG-467: DDF Value decides whenever it is a row; only without it does the picked series decide.
    key = "ddf_value" if "ddf_value" in names else snap["shown"]
    if "ddf_value" in names and snap["shown"] == "ddf_value":
        return ["the picker still shows DDF Value; the verdict-vs-picker split went unchecked"]
    if key not in names:
        return [f"verdict series {key} is not a table row"]
    nets = {}
    for k in names:
        vals = [engine[p].get(k) for p in pick["give"] + pick["receive"]]
        if all(finite(v) for v in vals):
            nets[k] = sum(engine[p][k] for p in pick["receive"]) - sum(engine[p][k] for p in pick["give"])
    title, text = snap["verdictTitle"], snap["verdictText"]
    if key not in nets:
        return [] if "no verdict" in title else [f"verdict series incomplete but headline {title!r}"]
    s = sign(nets[key])
    want = {1: f"you win by {fmt_net(nets[key])}", -1: f"you lose by {fmt_net(nets[key])}", 0: "even"}[s]
    errors = []
    if names[key] not in title or want not in title:
        errors.append(f"headline {title!r} should name {names[key]!r} and say {want!r}")
    against = [names[k] for k, n in nets.items() if k != key and s and sign(n) == -s]
    missing = [n for n in against if n not in text]
    if missing:
        errors.append(f"verdict does not name the sources that see it the other way {missing}: {text!r}")
    if branch:
        # JEG-1112: each seeded scenario must take its own copy branch, with a dissenting source, so the fold is measured
        # on the short "lose" copy and on the long "win with dissenting sources" copy (each source named twice).
        if s != {"win": 1, "lose": -1}[branch]:
            errors.append(f"the {branch!r} scenario no longer takes the {branch} branch: DDF Value net {fmt_net(nets[key])}; "
                          "fix its seeds (JEG-1112)")
        elif not against:
            errors.append(f"the {branch!r} scenario has no dissenting source, so its dissent copy went unchecked")
        else:
            marker = {"win": " you lose this trade. A manager who trades off ", "lose": " you win, but "}[branch]
            if marker not in text:
                errors.append(f"the {branch} verdict does not use the dissent copy ({marker.strip()!r}): {text!r}")
            if branch == "win" and any(text.count(n) < 2 for n in against):
                errors.append(f"the win verdict does not name every dissenting source twice {against}: {text!r}")
    if snap["verdictFall"] is None:
        errors.append("verdict card has no waterfall")
    else:
        row = next(r["wf"] for r in snap["rows"] if r["key"] == key)
        if snap["verdictFall"]["steps"] != row["steps"] or snap["verdictFall"]["land"] != row["land"]:
            errors.append(f"verdict card waterfall is not {key}'s own: {snap['verdictFall']['name']!r}")
    return errors


SHORT_VIEWPORT_MIN_VERDICT_WIDTH = 600


def check_layout(snap) -> list[str]:
    b, h = snap["boxes"], snap["innerHeight"]
    errors = []
    for name in ("give", "receive", "verdict", "verdictFall"):
        box = b.get(name)
        if not box or box["top"] < 0 or box["bottom"] > h + 0.5:
            errors.append(f"{name} not fully on screen at height {h}: {box}")
    if b.get("verdict") and b["verdict"]["top"] > b["give"]["bottom"]:
        errors.append("verdict is below the sides, not beside them")
    # JEG-917/JEG-1056: on a short desktop viewport the verdict column is the wide one (minmax(420px, 2.2fr),
    # 649 px at 1366). The fold check above cannot see its loss with the pinned fixture, whose verdict text wraps
    # the same at 551 px (the 1.6fr column of the plain >= 1280 rule) as at 649 px, so pin the width itself.
    # 600 sits between the two. Measured on Linux Chromium 2026-10-25: clean 649.5, rule removed 551.1.
    verdict = b.get("verdict")
    if snap.get("innerWidth", 0) >= 1280 and h <= 800 and verdict:
        width = verdict["right"] - verdict["left"]
        if width < SHORT_VIEWPORT_MIN_VERDICT_WIDTH:
            errors.append(f"verdict column is {width:.0f}px wide at {snap['innerWidth']}x{h}; the short-viewport rule needs >= {SHORT_VIEWPORT_MIN_VERDICT_WIDTH}px (JEG-917)")
    if b["table"]["top"] < b["give"]["bottom"] or b["table"]["top"] - max(b["give"]["bottom"], b["verdict"]["bottom"] if b.get("verdict") else 0) > 40:
        errors.append(f"per-source table does not start directly below the trade: {b['table']}")
    return errors


def _serve(body, ctype, route, *_):
    route.fulfill(status=200, content_type=ctype, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def run_checks(overrides=None, viewports=((1440, 900), (1366, 768), (1100, 900), (390, 844)), seed=False) -> list[str]:
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
                tag = f"[{width}x{height}{' win' if seed == 'win' else ''}] "
                page = browser.new_page(viewport={"width": width, "height": height})
                page.add_init_script(_render_env.pin_data_week_script())
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare && window.TradeValueV2.compare()", timeout=40000)
                page.wait_for_timeout(200)
                # JEG-1190: Compare opens empty; Try a sample trade loads the sample, marked Example.
                empty = page.evaluate(READ)
                if empty["give"] or empty["receive"] or empty["example"] or empty["rows"]:
                    errors.append(tag + f"Compare does not open empty: {empty['give']} / {empty['receive']}, banner {empty['example']!r}")
                if page.is_visible("#v2CTryExample"):
                    page.click("#v2CTryExample")
                    page.wait_for_timeout(300)
                ex = page.evaluate(READ)
                if not ex["example"] or "Example" not in ex["example"] or "Example" not in ex["verdictEyebrow"]:
                    errors.append(tag + f"no example trade marked Example: {ex['example']!r} / {ex['verdictEyebrow']!r}")
                # JEG-1191 (Jeremy, 2026-10-30, pick A): the examples are trades the market misses, 1-for-1 up to 2-for-2.
                elif not (1 <= len(ex["give"]) <= 2 and 1 <= len(ex["receive"]) <= 2) or not ex["rows"]:
                    errors.append(tag + f"example is not a drawn 1-for-1 to 2-for-2: {ex['give']} / {ex['receive']}")
                else:
                    errors += [tag + "example: " + e for e in check_waterfalls(ex, {"give": ex["give"], "receive": ex["receive"]})]
                # JEG-1056: when seeded, patch engine values to small deterministic numbers so the waterfall
                # column height is stable across data bakes and fits 1366x768.
                if seed:
                    seeded = page.evaluate(SEED_VALUES_WIN if seed == "win" else SEED_VALUES)
                    if not seeded or not seeded.get("patched"):
                        errors.append(tag + "seed fixture failed to apply")
                # A 2-for-2 from a link, with a verdict series that is not the ranking series. Show every
                # available trade-value series so the verdict has sources that can disagree with it.
                # Only add sources the engine reports as available; held sources have no values.
                page.evaluate("""() => {
                  const avail = window.TradeValueCurveControls.getSourceInfo()
                    .filter(i => i.available).map(i => i.key)
                    .filter(k => !k.endsWith('_vorp') && !k.endsWith('_adjusted'));
                  window.TradeValueV2.setShown([...new Set([...window.TradeValueV2.shown(), ...avail])]);
                }""")
                page.wait_for_timeout(200)
                # Pinned fixture: guarantee a gap player (one missing a source value) even
                # when held sources remove the only naturally-incomplete players.
                # Must run BEFORE PICK so the modified engine exposes the gap player to the picker.
                pick = page.evaluate(PICK)
                if not pick["gap"]:
                    gap_key = page.evaluate(SIMULATE_GAP, pick)
                    if gap_key:
                        # Re-evaluate PICK so it sees the patched engine.
                        pick = page.evaluate(PICK)
                        if not pick["gap"]:
                            pick["gap"] = gap_key
                    else:
                        errors.append(tag + "could not simulate a gap player; the missing-step path went unchecked")
                if not page.evaluate(SIMULATE_DISSENT, pick):
                    errors.append(tag + "could not make a source disagree with DDF Value; the dissent check went unchecked")
                page.evaluate("p => { location.hash = `#compare-trade?give=${p.give.join(',')}&get=${p.receive.join(',')}`; }", pick)
                page.wait_for_function("() => !document.getElementById('v2CTable').hidden")
                options = page.evaluate("() => [...document.querySelectorAll('#v2CShown option')].map(o => o.value)")
                current = page.evaluate("() => document.getElementById('v2CShown').value")
                # ddf_value_charts is the same numbers under the same name as ddf_value since JEG-1073, so a verdict that
                # wrongly follows the picker would be invisible on it; pick a series with its own name and values.
                other = next((k for k in options if k not in (current, "ddf_value", "ddf_value_charts") and not k.endswith("_vorp")), None)
                if other:
                    page.select_option("#v2CShown", other)
                page.evaluate("() => window.scrollTo(0, 0)")
                page.wait_for_timeout(150)
                snap = page.evaluate(READ)
                errors += [tag + e for e in check_waterfalls(snap, pick)]
                errors += [tag + e for e in check_verdict(snap, pick, branch=SCENARIO_BRANCH.get(seed))]
                # Printed so a log shows the fold numbers (JEG-1112): the verdict card's bottom edge against the fold.
                vb = (snap["boxes"].get("verdict") or {}).get("bottom")
                print(f"FOLD {tag}verdict bottom {vb} of {snap['innerHeight']}", file=sys.stderr, flush=True)
                if width >= 1280:
                    errors += [tag + e for e in check_layout(snap)]
                if snap["overflow"] > 0:
                    errors.append(tag + f"horizontal overflow {snap['overflow']}px")
                if pick["gap"]:
                    gap_pick = {"give": pick["give"], "receive": [pick["receive"][0], pick["gap"]]}
                    page.evaluate("p => { location.hash = `#compare-trade?give=${p.give.join(',')}&get=${p.receive.join(',')}`; }", gap_pick)
                    page.wait_for_timeout(300)
                    gap = page.evaluate(READ)
                    errors += [tag + "missing: " + e for e in check_waterfalls(gap, gap_pick, expect_missing=True)]
                else:
                    errors.append(tag + "no gap player available; the missing-step path went unchecked")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


WIDE_FONT_CSS = '\n.v2-app, .v2-app * { font-family: "DejaVu Sans", sans-serif !important; }\n'


def wide_font_overflow(css: str, widths=(1024, 1100, 1279, 1280, 1366, 1439)) -> dict:
    """Page overflow and tab-row squeeze per width with the app drawn in DejaVu Sans, the font CI falls back to
    when Inter is not installed (the hermetic browser blocks Google Fonts). Local Inter hid JEG-1056's overflow."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {}
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width in widths:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.add_init_script(_render_env.pin_data_week_script())
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                page.route("**/v2/v2.css*", functools.partial(_serve, css + WIDE_FONT_CSS, "text/css"))
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare && window.TradeValueV2.compare()", timeout=40000)
                # JEG-1106: the tab row is now a menu opened by a button, so there is no row to squeeze. What
                # matters at these widths is the bar stays one row and the open menu neither widens the page nor
                # pushes the content down.
                page.click("#v2NavToggle")
                out[width] = page.evaluate("""() => { const r = document.querySelector('.v2-nav-inner').getBoundingClientRect();
                  const f = document.getElementById('v2Freshness').getBoundingClientRect();
                  return {overflow: document.documentElement.scrollWidth - innerWidth, barH: r.height, freshRight: f.right, vw: innerWidth}; }""")
                page.close()
        finally:
            browser.close()
    return out


def check_wide_font(result: dict) -> list[str]:
    """No sideways page scroll at any width, and (JEG-1106, replacing the old tab-row squeeze check that measured a row
    that no longer exists) a bar that stays one row, with the freshness button on screen, while the menu is open."""
    errors = [f"[{w}] horizontal overflow {r['overflow']}px in DejaVu Sans" for w, r in result.items() if r["overflow"] > 0]
    errors += [f"[{w}] top bar is {r['barH']:.0f}px tall with the menu open (want one row, under 80px)" for w, r in result.items() if r["barH"] >= 80]
    errors += [f"[{w}] freshness button runs off screen ({r['freshRight']:.0f} of {r['vw']}px)" for w, r in result.items() if r["freshRight"] > r["vw"] + 0.5]
    return errors


# JEG-1106 mutation of the menu rule: the menu opens in the bar (in flow) instead of as a panel under it.
NAV_RULE = "position: absolute; z-index: 50; left: 48px;"


# JEG-1112: the example state is what a new visitor sees, on live data (no seeding), so it is held to the fold with a stated
# margin rather than exactly: a data bake that adds a line of verdict text (about 18 px) must not clip the totals unnoticed.
# Measured 2026-10-26 on Linux Chromium: header compacted, 1366x768 bottoms 739.5 (DejaVu Sans) / 740.1 (Inter), a margin of
# 28 px; the old header 794.2 / 794.9, 26-27 px past the fold.
EXAMPLE_FOLD_MARGIN = 12
EXAMPLE_READ = """() => {
  const box = n => { if (!n || n.hidden || !n.getClientRects().length) return null; const b = n.getBoundingClientRect(); return {top: b.top, bottom: b.bottom, width: b.width, height: b.height}; };
  const q = s => box(document.querySelector(s));
  const ex = document.getElementById('v2CExample');
  return {example: !ex.hidden ? ex.textContent : null, hash: location.hash,
    give: document.querySelectorAll('#v2GivePlayers li[data-player-key]').length, receive: document.querySelectorAll('#v2GetPlayers li[data-player-key]').length,
    boxes: {give: q('[data-trade-side="give"]'), receive: q('[data-trade-side="receive"]'), verdict: q('#v2CVerdict'),
      giveTotal: q('#v2GiveTotal'), receiveTotal: q('#v2GetTotal'), picker: q('#v2CShown'), toolbar: q('#v2Compare .v2-chead .v2-ctoolbar')},
    innerHeight, innerWidth, overflow: document.documentElement.scrollWidth - innerWidth};
}"""
# JEG-1190: the button on the empty page that opens first.
TRY_READ = """() => { const n = document.getElementById('v2CTryExample'); if (!n || n.closest('[hidden]') || !n.getClientRects().length) return null;
  const b = n.getBoundingClientRect(); return {top: b.top, bottom: b.bottom, width: b.width, height: b.height}; }"""
EXAMPLE_FOLD_VIEWPORTS = ((1366, 768), (1440, 900))
EXAMPLE_PHONE_VIEWPORTS = ((390, 844), (360, 740), (320, 640))


def example_state(overrides=None, font_css="", viewports=EXAMPLE_FOLD_VIEWPORTS + EXAMPLE_PHONE_VIEWPORTS) -> dict:
    """The Compare example view per viewport: boxes of the sides, the verdict and the totals once Try a sample trade is
    pressed, and that button's box on the empty page that opens first (JEG-1190)."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {}
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.add_init_script(_render_env.pin_data_week_script())
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare && window.TradeValueV2.compare()", timeout=40000)
                if font_css:
                    page.add_style_tag(content=font_css)
                page.wait_for_timeout(300)
                start = page.evaluate(TRY_READ)
                if start:
                    page.click("#v2CTryExample")
                    page.wait_for_timeout(300)
                snap = page.evaluate(EXAMPLE_READ)
                snap["boxes"]["tryExample"] = start
                out[(width, height)] = snap
                page.close()
        finally:
            browser.close()
    return out


def check_example_state(result: dict) -> list[str]:
    errors = []
    for (width, height), snap in result.items():
        tag = f"[{width}x{height}] "
        b = snap["boxes"]
        # JEG-1191 (Jeremy, 2026-10-30, pick A): an example is 1-for-1 up to 2-for-2.
        if not snap["example"] or "Example" not in snap["example"] or not (1 <= snap["give"] <= 2 and 1 <= snap["receive"] <= 2):
            errors.append(tag + f"not the example state (banner {snap['example']!r}, {snap['give']} for {snap['receive']}, {snap['hash']!r})")
            continue
        if snap["overflow"] > 0:
            errors.append(tag + f"horizontal overflow {snap['overflow']}px")
        button = b.get("tryExample")
        if not button or button["height"] < 44 or button["width"] < 44:
            errors.append(tag + f"'Try a sample trade' is missing or under 44 px: {button}")
        elif (width, height) in EXAMPLE_FOLD_VIEWPORTS and button["bottom"] > height - EXAMPLE_FOLD_MARGIN:
            errors.append(f"{tag}'Try a sample trade' ends at {button['bottom']:.1f}, below the fold")
        if not b.get("picker"):
            errors.append(tag + "the 'Player values shown' picker is not reachable")
        if (width, height) in EXAMPLE_FOLD_VIEWPORTS:
            limit = height - EXAMPLE_FOLD_MARGIN
            # JEG-1383: a held source's long disabled option widened the closed picker and wrapped Compare's header toolbar
            # to a second row at 1366 px (+56 px), so the compact header (JEG-1112) saved nothing and the fold guard could
            # not tell it from the old header. The toolbar must stay one picker row tall.
            bar, picker = b.get("toolbar"), b.get("picker")
            if bar and picker and bar["height"] > 1.5 * picker["height"]:
                errors.append(f"{tag}Compare's header toolbar wraps to {bar['height']:.0f} px (picker {picker['height']:.0f} px tall, "
                              f"{picker['width']:.0f} px wide); the compact header no longer saves height")
            for name in ("give", "receive", "verdict", "giveTotal", "receiveTotal"):
                box = b.get(name)
                if not box:
                    errors.append(tag + f"{name} is not drawn in the example state")
                elif box["bottom"] > limit:
                    errors.append(f"{tag}example {name} ends at {box['bottom']:.1f}, past {limit} ({height} fold less a {EXAMPLE_FOLD_MARGIN} px margin)")
    return errors


# The compacted header's grid, served away: Compare's header and Example banner fall back to the four-line stack.
HEADER_GRID = re.compile(r"@media \(min-width: 1280px\) \{\n  #v2Compare \.v2-chead \{ display: grid;.*?\n\}\n", re.S)


# JEG-1106 mutations (NAV_RULE above): the menu panel must not open in the bar's own row.
NAV_MUTATIONS = {
    "menu opens in the bar": "position: static; z-index: 50; left: 48px;",
}


class WaterfallRenderTest(unittest.TestCase):
    def test_no_sideways_scroll_with_a_wide_fallback_font(self):
        """JEG-1056: CI draws the page in DejaVu Sans (no Inter); the non-shrinking 872 px tab row pushed the page
        113/37/48 px sideways at 1024/1100/1280."""
        result = wide_font_overflow(V2_CSS.read_text(encoding="utf-8"))
        print("WIDE FONT", result, file=sys.stderr, flush=True)
        self.assertEqual(check_wide_font(result), [])

    def test_wide_font_guard_fails_on_broken_nav(self):
        css = V2_CSS.read_text(encoding="utf-8")
        self.assertEqual(css.count(NAV_RULE), 1, "JEG-1106 nav menu rule anchor is stale")
        for name, rule in NAV_MUTATIONS.items():
            with self.subTest(name):
                errors = check_wide_font(wide_font_overflow(css.replace(NAV_RULE, rule)))
                print(f"GUARD {'CAUGHT' if errors else 'NOT CAUGHT'}: {name} ({errors[0] if errors else '-'})", file=sys.stderr, flush=True)
                self.assertNotEqual(errors, [], f"wide-font check did not catch: {name}")

    def test_waterfall_verdict_layout_example(self):
        self.assertEqual(run_checks(seed=True), [])

    def test_waterfall_verdict_layout_win_with_dissent(self):
        """JEG-1112: the same checks on the long "win with dissenting sources" copy, at 1366x768 and 1440x900 too."""
        self.assertEqual(run_checks(seed="win"), [])

    def test_example_state_fits_the_fold(self):
        """JEG-1112: the first view a new visitor sees (the Example, nothing seeded) ends above the fold at 1366x768 and
        1440x900 with its totals, in the browser's own fonts and in DejaVu Sans; phones keep a 44 px Try a sample trade
        button and no sideways scroll. JEG-1190: the page opens empty, so this is the view one tap on that button gives."""
        errors = []
        for label, font_css in (("browser fonts", ""), ("DejaVu Sans", WIDE_FONT_CSS)):
            result = example_state(font_css=font_css)
            for (width, height), snap in result.items():
                b = snap["boxes"]
                r = lambda k: b[k] and round(b[k]["bottom"], 1)  # noqa: E731
                print(f"EXAMPLE FOLD [{label}] {width}x{height} give {r('give')} receive {r('receive')} verdict {r('verdict')} "
                      f"totals {r('giveTotal')}/{r('receiveTotal')} toolbar {b.get('toolbar')} picker {b.get('picker')}", file=sys.stderr, flush=True)
            errors += [f"{label} {e}" for e in check_example_state(result)]
        self.assertEqual(errors, [])

    def test_example_fold_guard_fails_on_the_old_header(self):
        css = V2_CSS.read_text(encoding="utf-8")
        old_header = HEADER_GRID.sub("", css)
        self.assertNotEqual(old_header, css, "the compact header rule anchor is stale")
        # JEG-1119 freed 75 px above Compare, and JEG-1190 took the Use this example button out of the Example banner,
        # so the old header alone now ends above the fold. The guard pushes Compare down (margin) until the clean build's lowest box sits
        # 2 px above the limit (measured per font), then proves the old header's extra height is caught there.
        limit = 768 - EXAMPLE_FOLD_MARGIN
        names = ("give", "receive", "verdict", "giveTotal", "receiveTotal")
        for label, font_css in (("browser fonts", ""), ("DejaVu Sans", WIDE_FONT_CSS)):
            clean = example_state(None, font_css, EXAMPLE_FOLD_VIEWPORTS)
            self.assertEqual(check_example_state(clean), [], f"the clean build must pass first ({label})")
            low = max(clean[(1366, 768)]["boxes"][n]["bottom"] for n in names)
            pad = max(0, int(limit - low) - 2)
            padded = f"\n#v2Compare {{ margin-top: {pad}px; }}\n"
            self.assertEqual(check_example_state(example_state({"v2.css": (css + padded, "text/css")}, font_css, EXAMPLE_FOLD_VIEWPORTS)), [],
                             f"the padded clean build must still pass ({label}, {pad} px)")
            errors = check_example_state(example_state({"v2.css": (old_header + padded, "text/css")}, font_css, EXAMPLE_FOLD_VIEWPORTS))
            print(f"GUARD {'CAUGHT' if errors else 'NOT CAUGHT'}: old Compare header, example state [{label}] pad {pad} px ({len(errors)} errors; first: {errors[0] if errors else '-'})",
                  file=sys.stderr, flush=True)
            self.assertTrue(any("1366x768" in e and "past" in e for e in errors), f"the old header was not caught at 1366x768 in {label}: {errors}")

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        trade = TRADE_JS.read_text(encoding="utf-8")
        js, styles = "text/javascript", "text/css"
        broken = {
            "a scale per row": {"v2.js": (v2.replace(
                "renderWaterfall(bar, fall, sharedScale || window.TradeValueTrade.waterfallScale([fall]));",
                "renderWaterfall(bar, fall, window.TradeValueTrade.waterfallScale([fall]));", 1), js)},
            "verdict not DDF": {"v2.js": (v2.replace(
                "verdictSeries = pointKeys.includes(DDF_KEY) ? DDF_KEY : TR.shown;", "verdictSeries = TR.shown;", 1), js)},
            # JEG-1112: the win copy names the dissenting sources twice (first sentence, then "A manager who trades off ...");
            # removing only the first sentence's names left the second naming them, so the mutation went uncaught on a win.
            # Both sentences and the lose copy lose their names here, and it must be caught in EACH seeded scenario.
            "verdict names no source": {"v2.js": (v2.replace(
                WIN_AGAINST_COPY,
                "text = `Some sources think you lose this trade. A manager who trades off some sources is the likeliest to accept.`;", 1).replace(
                "? `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you win, but",
                "? `Some sources think you win, but", 1), js)},
            # The second sentence alone: the long copy must keep naming the sources there (win scenario only).
            "win verdict drops its second sentence": {"v2.js": (v2.replace(
                WIN_AGAINST_COPY,
                "text = `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you lose this trade.`;", 1), js)},
            # JEG-1191: the start button takes the next example from nextExample (was exampleTrade).
            "no example": {"v2.js": (v2.replace(
                "verdictKey() ? nextExample(compareView.pointKeys, compareView.chartKeys) : null;", "verdictKey() ? null : null;", 1), js)},
            "landing on incomplete rows": {"trade.js": (trade.replace(
                "net: sums.net, complete: sums.net !== null,",
                "net: sums.net === null ? 0 : sums.net, complete: true,", 1), js)},
            # Both 3-column rules (>= 1280, and the wider verdict column on short viewports) go.
            "no 3-column layout": {"v2.css": (re.sub(
                r"grid-template-columns: minmax\(0, 1fr\) minmax\(0, 1fr\) minmax\(420px, [\d.]+fr\);",
                "grid-template-columns: 1fr 1fr;", css), styles)},
            # JEG-917: without the wider verdict column the 1366x768 verdict runs past the fold.
            "no wide verdict column on short viewports": {"v2.css": (css.replace(
                "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(420px, 2.2fr);", "", 1), styles)},
        }
        # With the SIMULATE_GAP fixture, a gap player is always available, so every
        # mutation is expected to be caught.
        sources = {"v2.js": v2, "v2.css": css, "trade.js": trade}
        # JEG-1056: only an error the clean build does not already have counts as a catch. When the clean build fails
        # (the 45 px inputs strip pushed Compare past the 1366x768 fold), every mutation looked caught by that error.
        # Numbers are masked so a mutation that only moves an already-failing box does not count as a new error.
        shape = lambda e: re.sub(r"-?\d+(\.\d+)?", "#", e)  # noqa: E731
        baselines = {sc: {shape(e) for e in run_checks(viewports=((1366, 768),), seed=sc)} for sc in (True, "win")}
        # JEG-1112: the copy mutations are caught in EACH seeded scenario (a catch in the other branch is not a catch);
        # every other mutation changes layout or structure for both, so the lose scenario alone is enough.
        scenarios = {"verdict names no source": (True, "win"), "win verdict drops its second sentence": ("win",)}
        for name, overrides in broken.items():
            for file, (body, _) in overrides.items():
                self.assertNotEqual(body, sources[file], f"mutation anchor for {name!r} is stale")
            for sc in scenarios.get(name, (True,)):
                label = f"{name} [{'win' if sc == 'win' else 'lose'}]" if name in scenarios else name
                with self.subTest(mutation=label):
                    errors = [e for e in run_checks(overrides, viewports=((1366, 768),), seed=sc) if shape(e) not in baselines[sc]]
                    # Printed so the blocking `make validate` log shows each guard result, caught or not (JEG-1056).
                    print(f"GUARD {'CAUGHT' if errors else 'NOT CAUGHT'}: {label} ({len(errors)} new errors; first: {errors[0] if errors else '-'})",
                          file=sys.stderr, flush=True)
                    self.assertNotEqual(errors, [], f"render checks did not catch: {label}")


if __name__ == "__main__":
    unittest.main()
