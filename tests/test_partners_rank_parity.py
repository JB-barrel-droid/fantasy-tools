"""JEG-1560: partners.html answers "who are the best trading partners to explore?" with one ranking.

What we guard, at 3 scorings x 10/12 teams x superflex off/on (12 settings), with the seeded league of
tests.test_team_engine_parity, against an independent read in the same browser (TradeValueCurveControls rows and
TradeValueFinder.lineupValue / withChartAverage / matchNames, the published tier rules recomputed here, not through
DDF.league):
- the page's partner order equals the metric in docs/claude-log/2026-11-07-jeg1560-partners-ranking.md
  (sum over QB/RB/WR/TE, only where one side is Strong >= 1.10 and the other Weak < 0.90, of min(surplus, need) on the
  position ratios, both ways; ties by
  DDF Value / Analyst charts on starters, not judged last, then league order);
- each partner's reason names exactly the get / give positions of that metric, biggest first;
- the top 3 (with a positive score) carry "Best match"; my team and waivers are never listed or ranked.
Drift: the same check fails when ddf-league.js is served with the give side of the metric halved.
Render: with a league the top partner and its reason show; without one the empty state (path to connect.html) shows.
Copy: no "Player pool", no bare "Market", no demo/sample/mock/illustrative labels, no "choose"/"set up", and the old
"DDF edge" / "premium" labels are gone.
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_team_engine_parity import APPLY, READY, SETTINGS, _browser, _open, seeded_league

ORACLE = r"""(league) => {
  const F = window.TradeValueFinder, C = window.TradeValueCurveControls;
  const POS = ['QB', 'RB', 'WR', 'TE'], SLOTS = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX'];
  const rows = C.getAllRows().filter(r => POS.includes(r.pos));
  const byKey = new Map(rows.map(r => [String(r.player_key), r]));
  const shape = C.getRosterShape();
  const teams = league.teams.map((t, i) => {
    const got = [];
    t.players.forEach(e => {
      let r = e.key ? byKey.get(String(e.key)) : null;
      if (!r && e.name) r = F.matchNames([{name: e.name, pos: e.pos || ''}], rows).matched[0] || null;
      if (r && !got.includes(r)) got.push(r);
    });
    const L = F.lineupValue(got, shape, 'ddf_value');
    const A = F.lineupValue(F.withChartAverage(got, ['cbs', 'usatoday', 'fantasypros']), shape, F.MARKET_KEY);
    return {i, name: t.name, rows: got, L, A};
  }).filter(t => t.rows.length);
  const med = vals => { const s = vals.slice().sort((a, b) => a - b), m = s.length >> 1; return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : null; };
  const medians = {};
  SLOTS.forEach(p => { medians[p] = []; for (let k = 0; k < (shape[p] || 0); k++) { const v = teams.map(t => t.L.slots[p][k]).filter(Boolean).map(r => r.values.ddf_value); medians[p].push(v.length ? med(v) : null); } });
  const ratio = (t, p) => {
    let score = 0, ms = 0;
    medians[p].forEach((m, k) => { if (m === null) return; const r = t.L.slots[p][k]; const v = r ? r.values.ddf_value : 0; score += Math.min(v, 1.25 * m); ms += m; });
    return ms > 0 ? score / ms : null;
  };
  const mine = teams.find(t => t.i === league.me);
  const out = teams.filter(t => t !== mine).map(t => {
    let score = 0; const get = [], give = [];
    POS.forEach(p => {
      const m = ratio(mine, p), r = ratio(t, p);
      if (m === null || r === null) return;
      const g = r >= 1.10 && m < 0.90 ? Math.min(r - 1, 1 - m) : 0, v = m >= 1.10 && r < 0.90 ? Math.min(m - 1, 1 - r) : 0;
      if (g > 0) get.push([p, g]);
      if (v > 0) give.push([p, v]);
      score += g + v;
    });
    const big = (a, b) => b[1] - a[1] || POS.indexOf(a[0]) - POS.indexOf(b[0]);
    const an = t.A.starterValue, d = t.L.starterValue;
    const ra = t.A.unvalued.length === 0 && an > 0 ? d / an : null;
    return {i: t.i, name: t.name, score, ra, get: get.sort(big).map(x => x[0]), give: give.sort(big).map(x => x[0])};
  });
  out.sort((a, b) => (a.score !== b.score ? b.score - a.score : 0)
    || (a.ra === b.ra ? 0 : a.ra === null ? 1 : b.ra === null ? -1 : b.ra - a.ra) || a.i - b.i);
  const nTop = Math.min(3, out.filter(t => t.score > 0).length);
  return out.map((t, k) => ({name: t.name, get: t.get.join(' '), give: t.give.join(' '), best: k < nTop}));
}"""

READ = r"""() => [...document.querySelectorAll('#team-list .pt-row')].map(r => ({
  name: r.querySelector('.tn').textContent.trim(), rank: Number(r.dataset.rank), get: r.dataset.get, give: r.dataset.give,
  best: !!r.querySelector('.badge') && r.querySelector('.badge').textContent.trim() === 'Best match',
  why: r.querySelector('.why').textContent.trim(), waivers: r.hasAttribute('data-waivers')}))"""


def reason_positions(why: str) -> tuple[str, str]:
    """The get / give positions a reason line names ("You could get RB and WR and give QB." ...)."""
    def names(phrase: str | None) -> str:
        return " ".join(re.findall(r"\b(QB|RB|WR|TE)\b", phrase or ""))
    first = why.split(".")[0]
    get = re.search(r"get ((?:QB|RB|WR|TE)(?:(?:, | and )(?:QB|RB|WR|TE))*)", first)
    give = re.search(r"give ((?:QB|RB|WR|TE)(?:(?:, | and )(?:QB|RB|WR|TE))*)", first)
    return names(get and get.group(1)), names(give and give.group(1))


def run_rank(overrides=None, settings=None) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    if not all((DIST / p).exists() for p in ("partners.html", "ddf-league.js")):
        raise _render_env.unavailable("dist partners page is not built")
    league = seeded_league()
    errors: list[str] = []
    with serve(DIST, overrides) as base, sync_playwright() as pw:
        browser = _browser(pw)
        try:
            page, page_errors = _open(browser, base, "partners.html", league)
            page.wait_for_function(READY, timeout=30000)
            for scoring, teams, sf in settings or SETTINGS:
                label = f"{scoring}/{teams}/{'sf' if sf else 'no-sf'}"
                page.evaluate(APPLY, [scoring, teams, sf])
                want = page.evaluate(ORACLE, league)
                got = page.evaluate(READ)
                if [g["name"] for g in got] != [w["name"] for w in want]:
                    errors.append(f"{label}: order page={[g['name'] for g in got]} engine={[w['name'] for w in want]}")
                if [g["rank"] for g in got] != list(range(1, len(got) + 1)):
                    errors.append(f"{label}: ranks {[g['rank'] for g in got]}")
                for g, w in zip(got, want):
                    if (g["get"], g["give"], g["best"]) != (w["get"], w["give"], w["best"]):
                        errors.append(f"{label}: {g['name']} page get/give/best={g['get'], g['give'], g['best']} engine={w['get'], w['give'], w['best']}")
                    if reason_positions(g["why"]) != (g["get"], g["give"]):
                        errors.append(f"{label}: {g['name']} reason {g['why']!r} does not name get={g['get']!r} give={g['give']!r}")
                if any(g["name"] == "My Squad" or g["waivers"] for g in got):
                    errors.append(f"{label}: my team or waivers ranked as a partner")
                if not any(w["best"] for w in want):
                    errors.append(f"{label}: seeded league has no positive fit (test league too flat)")
            errors.extend(f"page error {e}" for e in page_errors)
            page.close()
        finally:
            browser.close()
    return errors


VISIBLE_TEXT = r"""() => {
  document.querySelectorAll('details').forEach(d => { d.open = true; });
  const body = document.body.cloneNode(true);
  body.querySelectorAll('script, style').forEach(n => n.remove());
  const attrs = [...document.querySelectorAll('[aria-label], [title], [data-next-label], [data-disabled-reason]')]
    .flatMap(n => ['aria-label', 'title', 'data-next-label', 'data-disabled-reason'].map(a => n.getAttribute(a) || ''));
  return [document.title, body.textContent, ...attrs].join('\n');
}"""
BANNED = [r"player pool", r"(?<!Live )\bMarket\b", r"\bdemo\b", r"\bsample\b", r"\bmock", r"illustrative", r"wireframe",
          r"\bchoose\b", r"\bset up\b", r"DDF edge", r"premium"]


class PartnersRankParityTest(unittest.TestCase):
    def test_rank_and_reasons_match_engine_at_12_settings(self):
        errors = run_rank()
        self.assertEqual(errors, [], "\n".join(errors[:20]))

    def test_guard_fails_when_metric_drifts(self):
        path = DIST / "ddf-league.js"
        if not path.exists():
            raise _render_env.unavailable("dist/ddf-league.js not built")
        src = path.read_text()
        needle = "score += g + v;"
        self.assertIn(needle, src)
        errors = run_rank({"ddf-league.js": src.replace(needle, "score += g + 0.5 * v;").encode()})
        self.assertTrue(any("order" in e for e in errors), f"metric drift not caught: {errors[:5]}")

    def _pages(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "partners.html").exists():
            raise _render_env.unavailable("dist partners page is not built")
        return sync_playwright

    def test_render_with_and_without_league(self):
        sync_playwright = self._pages()
        with serve(DIST) as base, sync_playwright() as pw:
            browser = _browser(pw)
            try:
                page, errors = _open(browser, base, "partners.html", seeded_league())
                page.wait_for_function(READY, timeout=30000)
                page.wait_for_selector("#team-list .pt-row", timeout=10000)
                first = page.locator("#team-list .pt-row").first
                self.assertTrue(first.locator(".tn").is_visible())
                self.assertEqual(first.locator(".badge").inner_text().strip(), "Best match")
                why = first.locator(".why")
                self.assertTrue(why.is_visible())
                self.assertRegex(why.inner_text(), r"You could (get|give) (QB|RB|WR|TE)")
                self.assertTrue(page.locator("main h1").inner_text().startswith("Who are the best trading partners"))
                self.assertFalse(page.locator("#no-league").is_visible())
                self.assertEqual(errors, [])
                page.close()

                page, errors = _open(browser, base, "partners.html", None)
                page.wait_for_function("() => window.DDF && DDF.league && DDF.league.ready", timeout=30000)
                page.evaluate("() => DDF.league.ready")
                page.wait_for_selector("#no-league", state="visible", timeout=10000)
                self.assertEqual(page.locator("#team-list .pt-row").count(), 0)
                self.assertEqual(page.locator("#no-league a[href='connect.html']").count(), 1)
                self.assertEqual(errors, [])
                page.close()
            finally:
                browser.close()

    def test_banned_words(self):
        sync_playwright = self._pages()
        with serve(DIST) as base, sync_playwright() as pw:
            browser = _browser(pw)
            try:
                for league in (seeded_league(), None):
                    page, _ = _open(browser, base, "partners.html", league)
                    page.wait_for_function("() => window.DDF && DDF.league && DDF.league.ready", timeout=30000)
                    page.evaluate("() => DDF.league.ready")
                    text = page.evaluate(VISIBLE_TEXT)
                    hits = [b for b in BANNED if re.search(b, text, re.I if b[0] != "(" else 0)]
                    self.assertEqual(hits, [], f"banned words on partners.html ({'league' if league else 'no league'}): {hits}")
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
