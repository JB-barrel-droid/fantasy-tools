"""JEG-1558 part 2: the team page's opportunity read matches the engine, and reads cleanly at 1440 and 390.

Seeded synthetic league (tests.test_team_engine_parity.seeded_league: a snake draft of the frozen player table, no real
league). At 3 settings the oracle recomputes, in the same browser and without ddf-opportunity.js:
- worth = TradeValueWaivers.netOf(lineupValue(my rows)) (starters in full, bench weighted);
- the best natural-fit trade = max tradeFit us.net over DDF.find.searchPartner (find.html defaults) against every other
  team (never waivers), counted only above its tau; the best pickup = max totalDelta of DDF.find.pickups on the league's
  available players, counted only above its tau;
- the tier from the published rule (3 / 6 / 10% of worth), recomputed here in Python.
The page must show that tier (data-tier), the percent truncated to one decimal, the waivers line exactly when no pickup
beats its floor, and no banned reader text. Phone and desktop: no horizontal overflow, the block is visible.
Discrimination: test_guard_fails_on_shifted_threshold serves ddf-opportunity.js with the big line moved to 11%.
"""
from __future__ import annotations

import math
import re
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_team_engine_parity import APPLY, READY, seed_script, seeded_league

SETTINGS = [("half_ppr", 12, False), ("ppr", 10, True), ("standard", 12, False)]

ORACLE = r"""() => {
  const W = window.TradeValueWaivers, F = window.TradeValueFinder, cur = DDF.league.current(), mine = DDF.league.myTeam();
  const ctx = DDF.find.context(), rows = DDF.find.rowsOf(mine);
  const worth = W.netOf(F.lineupValue(rows, ctx.shape, 'ddf_value'), 'ddf_value', ctx.weights);
  let trade = 0, tradeRaw = null, partnersChecked = 0;
  const skip = new Set(DDF.league.skipped()), held = new Set(DDF.league.held().map(String));
  cur.teams.forEach(t => {
    if (t.index === mine.index || skip.has(t.name)) return;
    const theirs = DDF.find.rowsOf(t);
    if (!theirs.length) return;
    partnersChecked++;
    DDF.find.searchPartner(ctx, rows, theirs, {your: 'DDF', their: 'Market', sizes: [1, 2], held}).trades.forEach(tr => {
      if (tr.give.some(r => held.has(String(r.player_key)))) throw new Error('held player offered');
      if (tr.cls !== 'natural') return;
      if (tradeRaw === null || tr.fit.us.net > tradeRaw) tradeRaw = tr.fit.us.net;
      if (tr.fit.us.net > tr.fit.us.tau && tr.fit.us.net > trade) trade = tr.fit.us.net;
    });
  });
  const cand = cur.waivers.map(r => ({key: r.key, name: r.n, pos: r.pos, team: r.team}));
  const pk = DDF.find.pickups(ctx, DDF.find.entriesOf(mine), cand, 'DDF');
  let waiver = 0, waiverRaw = null;
  pk.results.forEach(r => {
    if (r.totalDelta === null) return;
    if (waiverRaw === null || r.totalDelta > waiverRaw) waiverRaw = r.totalDelta;
    if (r.totalDelta > r.tau && r.totalDelta > waiver) waiver = r.totalDelta;
  });
  return {worth, trade, tradeRaw, waiver, waiverRaw, partnersChecked, candidates: cand.length, held: held.size};
}"""

READ = r"""async () => {
  const t0 = Date.now();
  while (!document.querySelector('#opp-tier[data-tier]') && Date.now() - t0 < 60000) await new Promise(r => setTimeout(r, 100));
  const box = document.getElementById('opportunity'), r = box.getBoundingClientRect();
  return {tier: document.getElementById('opp-tier').dataset.tier || null, headline: document.getElementById('opp-tier').textContent,
    line: document.getElementById('opp-line').textContent, look: document.getElementById('opp-look').hidden ? null : document.getElementById('opp-look').textContent,
    waivers: document.getElementById('opp-waivers').hidden ? null : document.getElementById('opp-waivers').textContent,
    visible: !box.hidden && r.width > 0 && r.height > 0, overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    text: box.innerText, caveat: (document.querySelector('[data-ddf-caveats="assessment"] .ddf-caveats__slot') || {}).textContent || ''};
}"""

RESET = "() => { const t = document.getElementById('opp-tier'); t.removeAttribute('data-tier'); }"
BANNED = [re.compile(r"(^|[\s(])-\d"), re.compile(r"(^|[\s(])[+−-]0\.0(?!\d)"), re.compile(r"\bFA\b"), re.compile(r"\bW\d{1,2}\b"),
          re.compile(r"\bguarantee|\bwill accept|\bdefinitely\b|\bdemo\b|\bsample\b", re.I), re.compile(r"\bMarket\b")]


def tier_of(pct: float) -> str:
    return "big" if pct >= 10 else "medium" if pct >= 6 else "marginal" if pct >= 3 else "none"


def shown(pct: float) -> str:
    return f"{math.floor(pct * 10 + 1e-9) / 10:.1f}%"


def run(overrides=None, settings=None, widths=(1440,), me=0, exclude=False) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    if not all((DIST / p).exists() for p in ("team.html", "ddf-opportunity.js", "find-engine.js")):
        raise _render_env.unavailable("dist workspace pages are not built")
    league, errors = seeded_league(), []
    league["me"] = me
    with serve(DIST, overrides) as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        try:
            for width in widths:
                page = browser.new_page(viewport={"width": width, "height": 900 if width > 500 else 844})
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith(base), lambda route: route.abort())
                page.add_init_script(seed_script(league))
                page.goto(f"{base}/team.html", wait_until="networkidle", timeout=60000)
                page.wait_for_function(READY, timeout=30000)
                if exclude:  # skip two teams and hold my two best players, as Trading Partners / Pick players would
                    page.evaluate("""() => { const c = DDF.league.current(), me = DDF.league.myTeam();
                      DDF.league.setSkipped(c.teams.filter(t => t.index !== me.index).slice(0, 2).map(t => t.name));
                      DDF.league.setHeld(DDF.find.rowsOf(me).slice().sort((a, b) => b.values.ddf_value - a.values.ddf_value).slice(0, 2).map(r => String(r.player_key))); }""")
                for scoring, teams, sf in settings or SETTINGS:
                    label = f"{width} {scoring}/{teams}/{'sf' if sf else 'no-sf'}"
                    page.evaluate(RESET)
                    page.evaluate(APPLY, [scoring, teams, sf])
                    got = page.evaluate(READ)
                    want = page.evaluate(ORACLE)
                    if want["partnersChecked"] < 1:
                        errors.append(f"{label}: oracle checked no partners")
                    gain = max(want["trade"], want["waiver"])
                    pct = 100 * gain / want["worth"]
                    tier = tier_of(pct) if gain > 0 else "none"
                    if got["tier"] != tier:
                        errors.append(f"{label}: tier page={got['tier']} engine={tier} (gain {gain:.2f} of {want['worth']:.2f})")
                    if tier != "none" and shown(pct) not in got["line"]:
                        errors.append(f"{label}: line {got['line']!r} lacks {shown(pct)}")
                    nothing = "nothing available beats your bench" in (got["waivers"] or "")
                    if nothing != (want["waiverRaw"] is None or want["waiverRaw"] <= 0.05):
                        errors.append(f"{label}: waivers line {got['waivers']!r} with best pickup {want['waiverRaw']}")
                    if want["waiver"] <= 0 and got["waivers"] is None:
                        errors.append(f"{label}: no waivers line although no pickup beats its floor")
                    if tier == "none" and gain > 0 and "too small" not in got["line"]:
                        errors.append(f"{label}: a counted gain under 3% must say so: {got['line']!r}")
                    if exclude and "left out" not in got["line"]:
                        errors.append(f"{label}: skipped teams / held players not disclosed")
                    if "one week of three" not in got["caveat"]:
                        errors.append(f"{label}: best-move caveat missing from the caveats note: {got['caveat']!r}")
                    if not got["visible"] or got["overflow"]:
                        errors.append(f"{label}: visible={got['visible']} overflow={got['overflow']}")
                    for rx in BANNED:
                        m = rx.search(got["text"])
                        if m:
                            errors.append(f"{label}: banned reader text {m.group(0)!r} in {got['text'][:200]!r}")
                errors.extend(f"{width}: page error {e}" for e in page_errors)
                page.close()
        finally:
            browser.close()
    return errors


class TeamOpportunityRenderTest(unittest.TestCase):
    def test_matches_engine_at_desktop_and_phone(self):
        errors = run(widths=(1440, 390)) + run(me=6) + run(me=11) + run(me=11, exclude=True, widths=(390,))
        self.assertEqual(errors, [], "\n".join(errors[:20]))

    def test_guard_fails_on_shifted_threshold(self):
        src = (DIST / "ddf-opportunity.js").read_text() if (DIST / "ddf-opportunity.js").exists() else None
        if src is None:
            raise _render_env.unavailable("dist workspace pages are not built")
        bad = src.replace('{id: "big", min: 10}', '{id: "big", min: 11}')
        self.assertNotEqual(bad, src)
        errors = run({"ddf-opportunity.js": bad.encode()})
        self.assertNotEqual(errors, [], "the check passes with the tier lines moved")


if __name__ == "__main__":
    unittest.main()
