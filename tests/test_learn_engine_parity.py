"""JEG-1536: Learn > How we get our numbers shows the engine's own numbers.

The Learn page (dist/learn.html, built by pipelines/build_root_pages.py with the live engine
injected) renders the Value pie, Health check, Source build-up and Trace from the engine that runs
hidden on the page. This test reads the engine directly (TradeValueCurveControls.getAllRows /
getInspection / getPublishedMath, never the page's own model) and requires every number the page
shows to equal it, at 3 scorings x 10/12 teams x superflex on/off (plan step 2 parity gate):

  * every player in the picker: his DDF Value (the 4-chart mean, ddfByVersion.blended) and no
    player the engine does not price, none missing;
  * Trace for the top three players: DDF Value, and per chart published / index factor / indexed /
    adjusted;
  * Value pie: the donut total and each chart's adjusted value;
  * Source build-up (CBS Sports and FantasyCalc, first page): published, indexed, adjusted and
    DDF Value per row, in the chart's own order;
  * Health check: each source's adjusted total;
  * the settings the page says it shows are the engine's.

Discrimination (test_guard_catches_a_wrong_number): the same comparison must fail when the page's
reader is served with DDF Value nudged by 0.2.

Also here: the Manifesto renders word for word from docs/manifesto-mirror.md (the Doc mirror the
live tab is held to, MF-01), one visible h1 per view, the methodology draft and the week-9
snapshot files are not published (decisions D6 and D8, 2026-11-06).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve, chromium_executable

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MIRROR = ROOT / "docs" / "manifesto-mirror.md"
CHARTS = ("cbs", "usatoday", "fantasypros", "fantasycalc")
COMBOS = [(scoring, teams, sf) for scoring in ("standard", "half_ppr", "ppr") for teams in (10, 12) for sf in (0, 1)]
ROSTER = "QB1.RB2.WR2.TE1.FLEX1.SF{sf}.BN7"
SNAP_READY = """(want) => { const s = window.DDFNumbers && DDFNumbers.snapshot();
  return !!s && s.settings.scoring === want.scoring && s.settings.teams === want.teams && s.settings.superflex === want.sf
    && document.getElementById('nx-loading').hidden; }"""


def setUpModule():
    _render_env.ensure_built()


def f1(v):
    if v is None:
        return "—"
    text = f"{v:.1f}"
    if text in ("-0.0",):
        text = "0.0"
    return text.replace("-", "−")


def fpub(src, v):
    if v is None:
        return "—"
    return f"{round(v):,}" if src == "fantasycalc" else f1(v)


def ffactor(v):
    """The page's String(Number(v.toPrecision(6)))."""
    if v is None:
        return "—"
    text = str(float(f"{v:.6g}"))
    return text[:-2] if text.endswith(".0") else text


# The engine, read straight from TradeValueCurveControls (not from the page's model).
ENGINE = """() => {
  const C = window.TradeValueCurveControls, ins = C.getInspection(), st = C.getState(), shape = C.getRosterShape();
  const rows = {};
  C.getAllRows().forEach(r => {
    const b = r.ddfByVersion && r.ddfByVersion.blended;
    if (!b || typeof b.value !== 'number' || !isFinite(b.value)) return;
    const k = String(r.player_key), ir = ins.rows[k] || {};
    const src = {};
    ['cbs','usatoday','fantasypros','fantasycalc'].forEach(s => {
      const p = ins.players[s] && ins.players[s][k];
      src[s] = p ? {published: p.native, indexed: ir.indexed ? ir.indexed[s] : null, adjusted: ir.adjusted ? ir.adjusted[s] : null} : null;
    });
    rows[k] = {name: r.name, ddf: b.value, src};
  });
  const factor = {};
  const anyKey = Object.keys(rows)[0];
  ['cbs','usatoday','fantasypros','fantasycalc'].forEach(s => {
    const pm = C.getPublishedMath(Number(anyKey), s); factor[s] = pm ? pm.factor : null; });
  const order = {};
  ['cbs','fantasycalc'].forEach(s => {
    const ps = ins.players[s] || {};
    order[s] = Object.keys(ps).sort((a, b) => (ps[b].native - ps[a].native) || (Number(a) - Number(b)))
      .map(k => ({k, published: ps[k].native, indexed: ins.rows[k] && ins.rows[k].indexed ? ins.rows[k].indexed[s] : null,
        adjusted: ins.rows[k] && ins.rows[k].adjusted ? ins.rows[k].adjusted[s] : null}));
  });
  const totals = {};
  Object.keys(ins.players).forEach(s => {
    if (!ins.valuePipeline.sources[s]) return;
    totals[s] = Object.values(ins.players[s]).reduce((t, p) => t + (['QB','RB','WR','TE'].includes(p.pos) && (p.role === 'starter' || p.role === 'bench') ? (p.adjusted || 0) : 0), 0);
  });
  return {scoring: st.scoring, teams: st.teams, sf: shape.SUPERFLEX || 0, rows, factor, order, totals};
}"""

PAGE_PICKER = """() => [...document.querySelectorAll('#nx-players option')].map(o => ({k: o.dataset.key, name: o.value, label: o.label || o.textContent}))"""
PAGE_TRACE = """() => ({big: document.getElementById('tr-big').textContent.trim(),
  rows: Object.fromEntries([...document.querySelectorAll('#tr-pub tbody tr')].map(tr => [tr.dataset.src, [...tr.querySelectorAll('td')].map(td => td.textContent.trim())]))})"""
PAGE_PIE = """() => ({big: document.querySelector('#pie-chart .nx-donut-val').textContent.trim(),
  rows: Object.fromEntries([...document.querySelectorAll('#pie-table tbody tr')].map(tr => [tr.dataset.src, [...tr.querySelectorAll('td')].map(td => td.textContent.trim())])),
  totals: Object.fromEntries([...document.querySelectorAll('#hc-body table.nx-hc')[0].querySelectorAll('tbody tr')].map(tr => [tr.dataset.src, [...tr.querySelectorAll('td')].map(td => td.textContent.trim())]))})"""
PAGE_BUILDUP = """() => [...document.querySelectorAll('#bu-table tbody tr')].map(tr => ({k: tr.dataset.key, cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())}))"""


def go(page, hash_):
    page.evaluate("h => { location.hash = h; }", hash_)
    page.wait_for_timeout(120)


def compare(page, combo) -> list[str]:
    """Every mismatch between the Learn page and the engine at one setting."""
    scoring, teams, sf = combo
    q = f"?scoring={scoring}&teams={teams}&roster={ROSTER.format(sf=sf)}"
    errors: list[str] = []
    tag = f"{scoring}/{teams}/sf{sf}"
    go(page, "#numbers/pie" + q)
    page.wait_for_function(SNAP_READY, arg={"scoring": scoring, "teams": teams, "sf": bool(sf)}, timeout=60000)
    eng = page.evaluate(ENGINE)
    if (eng["scoring"], eng["teams"], eng["sf"]) != (scoring, teams, sf):
        return [f"{tag}: engine is at {eng['scoring']}/{eng['teams']}/sf{eng['sf']}"]
    rows = eng["rows"]

    picker = page.evaluate(PAGE_PICKER)
    seen = set()
    for opt in picker:
        row = rows.get(opt["k"])
        if row is None:
            errors.append(f"{tag}: picker lists {opt['name']} ({opt['k']}), the engine has no DDF Value for him")
            continue
        seen.add(opt["k"])
        want = f1(row["ddf"])
        if not opt["label"].endswith("· " + want):
            errors.append(f"{tag}: {row['name']} DDF Value on the page {opt['label']!r}, engine {want}")
    if set(rows) - seen:
        errors.append(f"{tag}: {len(set(rows) - seen)} priced players missing from the page")

    top = sorted(rows, key=lambda k: (-rows[k]["ddf"], int(k)))[:3]
    for k in top:
        go(page, f"#numbers/trace/{k}{q}")
        tr = page.evaluate(PAGE_TRACE)
        if tr["big"] != f1(rows[k]["ddf"]):
            errors.append(f"{tag}: trace {rows[k]['name']} shows {tr['big']}, engine {f1(rows[k]['ddf'])}")
        for s in CHARTS:
            e = rows[k]["src"][s]
            want = [fpub(s, e and e["published"]), ffactor(eng["factor"][s]), f1(e and e["indexed"]), f1(e and e["adjusted"])]
            if tr["rows"].get(s) != want:
                errors.append(f"{tag}: trace {rows[k]['name']} {s} page {tr['rows'].get(s)}, engine {want}")
    k = top[0]
    go(page, f"#numbers/pie/{k}{q}")
    pie = page.evaluate(PAGE_PIE)
    if pie["big"] != f1(rows[k]["ddf"]):
        errors.append(f"{tag}: pie total {pie['big']}, engine {f1(rows[k]['ddf'])}")
    for s in CHARTS:
        e = rows[k]["src"][s]
        got = (pie["rows"].get(s) or [None])[0]
        if got != f1(e and e["adjusted"]):
            errors.append(f"{tag}: pie {s} adjusted {got}, engine {f1(e and e['adjusted'])}")
    for s, total in eng["totals"].items():
        cells = pie["totals"].get(s)
        if not cells or cells[2] != f1(total):
            errors.append(f"{tag}: health check {s} total {cells and cells[2]}, engine {f1(total)}")

    for s in ("cbs", "fantasycalc"):
        go(page, f"#numbers/build-up/{s}{q}")
        got = page.evaluate(PAGE_BUILDUP)
        want_rows = eng["order"][s][:len(got)]
        if not got:
            errors.append(f"{tag}: build-up {s} shows no rows")
        for i, (g, w) in enumerate(zip(got, want_rows)):
            if g["k"] != w["k"]:
                errors.append(f"{tag}: build-up {s} row {i + 1} is {g['k']}, engine order {w['k']}")
                break
            # cells: rank, pos, role, published, indexed, adjusted, others, ddf
            ddf = rows.get(w["k"])
            want = [fpub(s, w["published"]), f1(w["indexed"]), f1(w["adjusted"])]
            if g["cells"][3:6] != want:
                errors.append(f"{tag}: build-up {s} {w['k']} page {g['cells'][3:6]}, engine {want}")
            if g["cells"][7] != (f1(ddf["ddf"]) if ddf else "—"):
                errors.append(f"{tag}: build-up {s} {w['k']} DDF {g['cells'][7]}, engine {ddf and f1(ddf['ddf'])}")
    return errors


def manifesto_words(mirror: str) -> list[str]:
    """Same rule as tests/test_v2_contract_render.py MF-01: the mirror body without Markdown marks."""
    body = mirror.split("-->", 1)[1] if mirror.startswith("<!--") else mirror
    body = re.sub(r"^\s*- ", " ", body, flags=re.M)
    return body.replace("*", "").replace("#", " ").split()


class LearnEngineParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            if _render_env.required():
                raise
            raise unittest.SkipTest("playwright not installed")
        if not (DIST / "learn.html").exists():
            if _render_env.required():
                raise AssertionError("dist/learn.html is not built")
            raise unittest.SkipTest("dist/learn.html is not built")
        cls.sync_playwright = staticmethod(sync_playwright)

    def _page(self, p, base, viewport=(1440, 900)):
        browser = p.chromium.launch(executable_path=chromium_executable(p), args=_render_env.HERMETIC_ARGS)
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(base + "/learn.html#numbers/pie")
        page.wait_for_function("() => window.DDFNumbers && DDFNumbers.snapshot()", timeout=90000)
        return browser, page, errors

    def test_numbers_match_engine(self):
        with serve() as base, self.sync_playwright() as p:
            browser, page, console = self._page(p, base)
            errors = []
            for combo in COMBOS:
                errors += compare(page, combo)
            browser.close()
        self.assertEqual(errors, [], "\n".join(errors[:40]))
        self.assertEqual([e for e in console if "Failed to load resource" not in e], [])

    def test_guard_catches_a_wrong_number(self):
        reader = (DIST / "learn" / "numbers" / "learn-engine.js").read_text(encoding="utf-8")
        nudged = reader.replace("var ddf = finite(blended && blended.value);",
                                "var ddf = finite(blended && blended.value); if (ddf !== null) ddf += 0.2;")
        self.assertNotEqual(reader, nudged, "the nudge did not apply; update the guard")
        with serve(overrides={"learn/numbers/learn-engine.js": nudged.encode()}) as base, self.sync_playwright() as p:
            browser, page, _ = self._page(p, base)
            errors = compare(page, ("ppr", 12, 0))
            browser.close()
        self.assertTrue(any("DDF Value" in e or "trace" in e for e in errors), errors[:5])

    def test_manifesto_verbatim_and_one_h1(self):
        want = manifesto_words(MIRROR.read_text(encoding="utf-8"))
        with serve() as base, self.sync_playwright() as p:
            for viewport in ((1440, 900), (390, 844)):
                browser, page, console = self._page(p, base, viewport)
                go(page, "#manifesto")
                page.wait_for_selector("#post-body h1", timeout=20000)
                got = page.evaluate("""() => { const b = document.getElementById('post-body').cloneNode(true);
                  b.querySelectorAll('#post-actions').forEach(n => n.remove()); document.body.appendChild(b);
                  const t = b.innerText; b.remove(); return t; }""").split()
                self.assertEqual(got, want, "Manifesto differs from docs/manifesto-mirror.md")
                for h in ("#", "#manifesto", "#numbers/pie", "#numbers/build-up", "#numbers/trace", "#numbers/glossary", "#numbers/logic"):
                    go(page, h)
                    page.wait_for_timeout(300)
                    n = page.evaluate("() => [...document.querySelectorAll('h1')].filter(h => h.getClientRects().length).length")
                    self.assertEqual(n, 1, f"{h} at {viewport[0]}: {n} visible h1")
                browser.close()

    def test_no_snapshots_or_drafts_published(self):
        self.assertFalse((DIST / "learn" / "data").exists(), "week snapshot files are published (D8)")
        posts = (DIST / "learn" / "posts.json").read_text(encoding="utf-8")
        self.assertNotIn('"draft"', posts, "a draft post is listed (D6)")
        self.assertFalse((DIST / "learn" / "posts" / "methodology.md").exists())
        page = (DIST / "learn.html").read_text(encoding="utf-8")
        start = page.index('<main id="learn-main">')
        main = page[start:page.index("</main>", start)]
        for stale in ("week 9", "week9", "Week 9", "84.3", "2,688", "Jahmyr Gibbs"):
            self.assertNotIn(stale, main, f"hard-coded snapshot text in learn.html: {stale!r}")


if __name__ == "__main__":
    unittest.main()
