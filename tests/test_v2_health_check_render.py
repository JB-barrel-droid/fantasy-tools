"""Values auditing > Health check tab, rendered (JEG-1011).

Two layers, both proven against broken builds:

1. Logic and copy on the frozen fixtures in tests/fixtures/audit/ (a bare page with audit-pie.js and
   a stub engine, so it needs no built data): the verdict strip is one row per check, every row derives
   from the same computeChecks() result as the tables, flags fire on a perturbed source and only name that
   source, the QB starter spread and the bench spread are information and never a flag, a wording change
   never changes a flag, each section opens with a question, no code reference reaches the page, every
   term is in the legend, the raw section is collapsed, tables have a caption, an aria-label and th scope.
2. The live page (the real shell and engine, built dist): the old #values-auditing/value-pie hash
   redirects to #values-auditing/health-check, the verdict strip is visible without scrolling at
   1366x768 and 390x844, no horizontal overflow at 390 / 360 / 320, a row link scrolls to its section, the
   tab follows a league setting change, and the numbers on screen equal the engine's.

Thresholds are protected (see docs/health-check-thresholds.md): the expectations below come from the frozen
fixtures and the derived limits, never from tuning to make a test pass.

Discrimination: test_guard_fails_on_broken_builds serves audit-pie.js (or the shell) with one named bug
at a time and requires the checks to fail.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_research_render import POSTS, _built_dist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PIE_JS = ROOT / "app" / "v2" / "audit-pie.js"
FIXTURES = ROOT / "tests" / "fixtures" / "audit"

# Flags that fire on the unperturbed week 7 fixture today (PPR, 12 teams). Stable across iterations: a change
# here is a change of what "healthy" means and needs a logged justification (docs/health-check-thresholds.md).
HEALTHY_FLAGS: list[str] = []
CHECK_IDS = ["starters", "positions", "qb", "bench", "totals", "coverage", "reconcile"]
INFO_IDS = ["qb", "bench"]
QUESTION = re.compile(r"^(Do|Are|Does|How|Did)\b")
CODE_REFS = re.compile(r"groups\[|value-model|rate\s*(!=|≠)|starterSlice|benchSlice|\.js\b|getInspection|\bpipeline\.", re.I)
BANNED_WORDS = re.compile(r"\b(USAT|FP|FC|Wk|median)\b|CBS ROS|\bvegas\b|vorp", re.I)   # JEG-812 plain copy rules

CHECKS_JS = """(insp) => { const d = AuditPie.extract(insp); AuditPie.computeFlags(d);
  return AuditPie.computeChecks(d).map(c => ({id: c.id, status: c.status, sources: c.sources, positions: c.positions,
    reason: c.reason, section: c.section})); }"""

# Render into a mount and report what a reader (and a screen reader) gets.
RENDER_JS = """(insp) => {
  document.querySelectorAll('#audit-pie-root').forEach(n => n.remove());
  const host = document.createElement('div'); host.id = 'audit-pie-root'; document.body.appendChild(host);
  AuditPie.render(host, {engine: {getInspection: () => insp}});
  const q = s => [...host.querySelectorAll(s)];
  const visibleTables = q('table').filter(t => !t.closest('details:not([open])'));
  return {
    text: host.textContent,
    rows: q('.audit-pie-check').map(li => ({check: li.dataset.check, status: li.dataset.status,
      badge: (li.querySelector('.audit-pie-badge') || {}).textContent, name: (li.querySelector('.audit-pie-check-name') || {}).textContent,
      reason: (li.querySelector('.audit-pie-check-reason') || {}).textContent,
      section: (li.querySelector('[data-flag-section]') || {getAttribute: () => null}).getAttribute('data-flag-section'),
      live: li.getAttribute('aria-live'), cls: li.className})),
    sectionIds: q('[data-flag-section]').map(a => [a.getAttribute('data-flag-section'), Boolean(document.getElementById(a.getAttribute('data-flag-section')))]),
    headline: (host.querySelector('.audit-pie-headline') || {}).textContent, headlineLive: (host.querySelector('.audit-pie-headline') || {getAttribute: () => null}).getAttribute('aria-live'),
    headings: q('h2').map(h => h.textContent),
    questionSections: q('section.audit-pie-section, details.audit-pie-section').filter(s => !s.classList.contains('audit-pie-terms')).map(s => ({
      id: s.id, q: (s.querySelector('h2') || {}).textContent, how: Boolean(s.querySelector('.audit-pie-how'))})),
    flagCells: q('[data-flag]').map(c => ({table: (c.closest('table') || {getAttribute: () => ''}).getAttribute('aria-label'), row: c.parentElement.cells[0].textContent, col: c.closest('table').rows[0].cells[c.cellIndex].textContent, text: c.textContent})),
    tables: q('table').map(t => ({label: t.getAttribute('aria-label'), caption: Boolean(t.querySelector('caption')),
      cols: t.rows[0].cells.length, unscoped: [...t.querySelectorAll('th')].filter(h => !h.getAttribute('scope')).length, collapsed: Boolean(t.closest('details:not([open])'))})),
    visibleCols: Math.max(0, ...visibleTables.map(t => t.rows[0].cells.length)),
    rawOpen: host.querySelector('.audit-pie-raw').open, termsOpen: host.querySelector('.audit-pie-terms').open,
    legend: q('.audit-pie-terms dt').map(d => d.textContent),
    benchNote: Boolean(host.querySelector('[data-bench-note]')),
    benchBg: getComputedStyle(host.querySelector('.audit-pie-check-info .audit-pie-badge')).backgroundColor,
  };
}"""

LOW_LEVEL = """(insp) => { const d = AuditPie.extract(insp); AuditPie.computeFlags(d); return AuditPie.computeMetrics(d); }"""


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["inspection"]


def scaled(insp: dict, src: str, factor: float, role: str = "starter", pos: str | None = None) -> dict:
    out = json.loads(json.dumps(insp))
    for p in out["players"][src].values():
        if p["role"] == role and (pos is None or p["pos"] == pos):
            p["adjusted"] *= factor
    return out


def harness(playwright, pie_js: str | None = None):
    try:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("about:blank")
    page.add_script_tag(content=pie_js if pie_js is not None else PIE_JS.read_text(encoding="utf-8"))
    return browser, page, errors


def logic_checks(pie_js: str | None = None) -> list[str]:
    """Everything that needs no built site. Returns the list of failures."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors: list[str] = []
    healthy, perturbed = fixture("healthy_week7.json"), fixture("perturbed_espn_starter.json")
    with sync_playwright() as pw:
        browser, page, page_errors = harness(pw, pie_js)
        try:
            checks = page.evaluate(CHECKS_JS, healthy)
            ids = [c["id"] for c in checks]
            if ids != CHECK_IDS:
                errors.append(f"healthy: checks {ids}, want {CHECK_IDS} (one row per check)")
            flags = [c["id"] for c in checks if c["status"] == "flag"]
            if flags != HEALTHY_FLAGS:
                errors.append(f"healthy: flags {flags}, want {HEALTHY_FLAGS} (flag count on healthy data must be stable)")
            for c in checks:
                if c["id"] in INFO_IDS and c["status"] != "info":
                    errors.append(f"healthy: {c['id']} is {c['status']}, must be information and never a flag (Jeremy, 2026-10-24)")
                if c["id"] not in INFO_IDS and c["status"] == "info":
                    errors.append(f"healthy: {c['id']} is information, only QB and bench are")

            # Perturbed ESPN starters x1.2 and x0.8: flags fire, and name ESPN and nobody else.
            for label, insp in (("espn x1.2", perturbed), ("espn x0.8", scaled(healthy, "espn", 0.8))):
                got = page.evaluate(CHECKS_JS, insp)
                flagged = [c for c in got if c["status"] == "flag"]
                named = sorted({s for c in flagged for s in c["sources"]})
                if "starters" not in [c["id"] for c in flagged]:
                    errors.append(f"{label}: the starters row did not flag")
                if named != ["espn"]:
                    errors.append(f"{label}: flags name {named}, want exactly ['espn']")
                if any(c["id"] in INFO_IDS and c["status"] != "info" for c in got):
                    errors.append(f"{label}: an information row changed status")
                if not any("ESPN" in c["reason"] for c in flagged):
                    errors.append(f"{label}: no flag reason names ESPN in words")
            # One position of one source: the positions row flags and names that position and that source.
            got = page.evaluate(CHECKS_JS, scaled(healthy, "razzball", 1.6, pos="WR"))
            pos_row = next(c for c in got if c["id"] == "positions")
            if pos_row["status"] != "flag" or pos_row["positions"] != ["WR"] or pos_row["sources"] != ["razzball"] or "WR" not in pos_row["reason"] or "Razzball" not in pos_row["reason"]:
                errors.append(f"razzball WR starters x1.6: positions row {pos_row}")
            qb_row = next(c for c in page.evaluate(CHECKS_JS, scaled(healthy, "razzball", 3.0, pos="QB")) if c["id"] == "qb")
            if qb_row["status"] != "info":
                errors.append(f"razzball QB starters x3: the QB row became {qb_row['status']}, it must stay information")
            # A different source: the flag follows the perturbed source, it does not stick to ESPN.
            got = page.evaluate(CHECKS_JS, scaled(healthy, "fantasycalc", 1.2))
            named = sorted({s for c in got if c["status"] == "flag" for s in c["sources"]})
            if named != ["fantasycalc"]:
                errors.append(f"fantasycalc x1.2: flags name {named}, want exactly ['fantasycalc']")
            # Every source moved by the same factor: the spread does not change, so the starters row does not flag.
            every = healthy
            for src in healthy["players"]:
                every = scaled(every, src, 1.2)
            if next(c for c in page.evaluate(CHECKS_JS, every) if c["id"] == "starters")["status"] != "pass":
                errors.append("all sources x1.2: the starters row flagged although the spread is unchanged")
            # A source removed: no crash, six rows in each table.
            missing = fixture("missing_cbs.json")
            got = page.evaluate(CHECKS_JS, missing)
            if [c["id"] for c in got] != CHECK_IDS:
                errors.append(f"missing CBS: checks {[c['id'] for c in got]}")
            r = page.evaluate(RENDER_JS, missing)
            if r["text"].count("CBS Sports") and "▼ CBS Sports" in r["text"]:
                errors.append("missing CBS: the removed source is still in the tables")
            for name in ("extreme_8team_halfppr.json", "history_week5.json"):
                got = page.evaluate(CHECKS_JS, fixture(name))
                if [c["id"] for c in got] != CHECK_IDS:
                    errors.append(f"{name}: checks {[c['id'] for c in got]}")
                if [c["id"] for c in got if c["status"] == "flag"] != HEALTHY_FLAGS:
                    errors.append(f"{name}: flags {[c['id'] for c in got if c['status'] == 'flag']}, want {HEALTHY_FLAGS}")

            # Wording never changes a flag: relabel every source, statuses stay the same.
            page.evaluate("() => { window.TradeValueV2 = {publishers: () => Object.fromEntries(['espn','cbsros','razzball','fantasycalc','usatoday','fantasypros','cbs'].map(k => [k, {label: 'Source ' + k, symbol: ''}]))}; }")
            before = [(c["id"], c["status"]) for c in page.evaluate(CHECKS_JS, perturbed)]
            reasons = [c["reason"] for c in page.evaluate(CHECKS_JS, perturbed)]
            page.evaluate("() => { delete window.TradeValueV2; }")
            if before != [(c["id"], c["status"]) for c in page.evaluate(CHECKS_JS, perturbed)]:
                errors.append("a wording change (source names) changed a flag")
            if not any("Source espn" in r for r in reasons):
                errors.append("relabelled sources did not reach the row wording (test setup)")

            # The page: strip first, tables from the same checks.
            r = page.evaluate(RENDER_JS, healthy)
            if [row["check"] for row in r["rows"]] != CHECK_IDS:
                errors.append(f"strip rows {[row['check'] for row in r['rows']]}, want {CHECK_IDS}")
            for row in r["rows"]:
                if row["badge"] not in ("Pass", "Flag", "Info") or not row["reason"] or not row["name"]:
                    errors.append(f"strip row incomplete: {row}")
                if row["live"] != "polite":
                    errors.append(f"strip row {row['check']} is not an aria-live region")
                if not row["section"]:
                    errors.append(f"strip row {row['check']} has no link to its section (data-flag-section)")
            for sid, exists in r["sectionIds"]:
                if not exists:
                    errors.append(f"a row links to #{sid}, which is not on the page")
            if not r["headline"] or r["headlineLive"] != "polite":
                errors.append(f"headline {r['headline']!r} is missing or not announced")
            if "Is anything wrong?" not in r["headings"]:
                errors.append(f"no 'Is anything wrong?' heading {r['headings']}")
            for sec in r["questionSections"]:
                if not QUESTION.match(sec["q"] or ""):
                    errors.append(f"section {sec['id']} heading {sec['q']!r} is not a question")
                if not sec["how"]:
                    errors.append(f"section {sec['id']} has no how-to-read line")
            if len(r["questionSections"]) != 5:
                errors.append(f"{len(r['questionSections'])} drill-down sections, want 5")
            if r["rawOpen"]:
                errors.append("the raw-versus-adjusted section is open by default (Jeremy: collapsed)")
            if r["visibleCols"] > 8:
                errors.append(f"a main-view table has {r['visibleCols']} columns (max 8)")
            for t in r["tables"]:
                if not t["label"] or not t["caption"] or t["unscoped"]:
                    errors.append(f"table {t} lacks a label, caption or th scope")
            if CODE_REFS.search(r["text"]):
                errors.append(f"code reference in the page text: {CODE_REFS.search(r['text']).group(0)!r}")
            if BANNED_WORDS.search(r["text"]):
                errors.append(f"banned plain-copy word: {BANNED_WORDS.search(r['text']).group(0)!r}")
            terms = page.evaluate("() => AuditPie._TERMS.map(t => t[0])")
            missing_terms = [t for t in terms if t not in r["legend"]]
            if missing_terms or len(terms) < 8:
                errors.append(f"terms legend is missing {missing_terms} ({len(terms)} terms)")
            for must in ("Adjusted", "Rescaled", "DDF Value", "Value pie", "Spread", "Value above waivers", "Fill-in value", "Starter, bench, waiver"):
                if must not in r["legend"]:
                    errors.append(f"term {must!r} is not in the legend")
            # Jargon on the page must be defined: every capitalised term the copy leans on is in the legend.
            for word in ("Rescaled", "Adjusted", "DDF Value"):
                if word in r["text"] and word not in r["legend"]:
                    errors.append(f"{word!r} is used but not defined")
            bg = re.findall(r"\d+", r["benchBg"])
            if len(bg) >= 3:
                red, green, blue = (int(x) / 255 for x in bg[:3])
                hi, lo = max(red, green, blue), min(red, green, blue)
                hue = 0.0 if hi == lo else (60 * ((green - blue) / (hi - lo)) % 360 if hi == red else 60 * (2 + (blue - red) / (hi - lo)) if hi == green else 60 * (4 + (red - green) / (hi - lo)))
                if (hue < 20 or hue > 340) and (hi - lo) > 0.2:
                    errors.append(f"the bench row badge is red (rgb {r['benchBg']})")
            bench = next(row for row in r["rows"] if row["check"] == "bench")
            if "xpected" not in bench["reason"] or bench["status"] != "info":
                errors.append(f"bench row must say it is expected and be information: {bench}")
            qb = next(row for row in r["rows"] if row["check"] == "qb")
            if qb["status"] != "info" or not re.search(r"\d+\.\d%", qb["reason"]):
                errors.append(f"QB row must show its number and stay information: {qb}")
            if r["benchNote"] is not True:
                errors.append("bench spread is over 25% but the bench explanation is not shown")

            # Perturbed render: the flag row names source and position, the table cell is marked, and the strip agrees.
            rp = page.evaluate(RENDER_JS, perturbed)
            flag_rows = [row for row in rp["rows"] if row["status"] == "flag"]
            if not flag_rows:
                errors.append("perturbed ESPN: no flag row rendered")
            if not any("ESPN" in row["reason"] for row in flag_rows):
                errors.append("perturbed ESPN: no flag row names the source")
            if rp["headline"] and "need a look" not in rp["headline"]:
                errors.append(f"perturbed ESPN: headline {rp['headline']!r} does not say something needs a look")
            marked = [c for c in rp["flagCells"] if "ESPN" in c["row"] and c["col"] == "Starters"]
            if not marked:
                errors.append("perturbed ESPN: the Starters cell of the ESPN row is not marked (strip and tables must agree)")
            if any("ESPN" not in c["row"] for c in rp["flagCells"] if c["table"] and "Starter, bench and total value by source" == c["table"]):
                errors.append("perturbed ESPN: a table cell is marked for a source that is not the problem")
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


READ_LIVE = """() => {
  const q = s => document.querySelector(s);
  const strip = q('.audit-pie-verdict'), rect = strip ? strip.getBoundingClientRect() : null;
  const rows = [...document.querySelectorAll('.audit-pie-check')].map(r => r.getBoundingClientRect().bottom);
  return {hash: location.hash, title: document.title,
    sub: [...document.querySelectorAll('#v2AuditTabs .v2-subtab')].map(a => [a.dataset.audit, a.getAttribute('aria-current') === 'page', a.textContent]),
    audit: !q('#v2Audit').hidden, stripBottom: rect ? Math.round(Math.max(rect.bottom, ...rows)) : null, vh: innerHeight,
    overflow: Math.max(document.documentElement.scrollWidth, innerWidth) - innerWidth, meta: (q('.audit-pie-meta') || {}).textContent,
    rows: document.querySelectorAll('.audit-pie-check').length, flagCount: (q('.audit-pie-headline') || {dataset: {}}).dataset.flagCount,
    text: document.getElementById('audit-pie-root').innerText};
}"""


def live_checks(pie_js: str | None = None, shell_edit=None) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors: list[str] = []
    with _built_dist(POSTS) as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1366, 768), (390, 844), (360, 740), (320, 568)):
                tag = f"[{width}x{height}] "
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if pie_js is not None:
                    page.route("**/v2/audit-pie.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=pie_js))
                page.goto(base + "#values-auditing/value-pie", wait_until="networkidle")   # the OLD hash
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueCurveControls.isReady()", timeout=40000)
                try:
                    page.wait_for_selector(".audit-pie-checks", timeout=15000)
                except Exception:  # noqa: BLE001
                    errors.append(tag + "no verdict strip rendered")
                    page.close()
                    continue
                s = page.evaluate(READ_LIVE)
                if s["hash"] != "#values-auditing/health-check":
                    errors.append(f"{tag}old hash #values-auditing/value-pie did not redirect (hash {s['hash']})")
                if not s["audit"] or ["health-check", True, "Health check"] not in s["sub"] or any(a[1] for a in s["sub"] if a[0] != "health-check"):
                    errors.append(f"{tag}sub-tabs {s['sub']}")
                if not s["title"].startswith("Health check · Values auditing"):
                    errors.append(f"{tag}page title {s['title']!r}")
                if s["rows"] != len(CHECK_IDS):
                    errors.append(f"{tag}{s['rows']} verdict rows, want {len(CHECK_IDS)}")
                if s["overflow"] > 0:
                    errors.append(f"{tag}horizontal overflow {s['overflow']}px")
                if width in (1366, 390) and s["stripBottom"] is not None and s["stripBottom"] > s["vh"]:
                    errors.append(f"{tag}verdict strip ends at {s['stripBottom']}px, below the {s['vh']}px fold")
                if CODE_REFS.search(s["text"]) or BANNED_WORDS.search(s["text"]):
                    errors.append(f"{tag}code reference or banned word on the page")
                if width == 1366:
                    # A row link scrolls to its section and keeps the route.
                    page.evaluate("""() => document.querySelector('.audit-pie-check [data-flag-section="audit-pie-sec-coverage"]').click()""")
                    page.wait_for_timeout(900)   # the page scrolls smoothly
                    moved = page.evaluate("""() => ({top: document.getElementById('audit-pie-sec-coverage').getBoundingClientRect().top,
                      hash: location.hash, y: scrollY, focus: document.activeElement.className})""")
                    if not (0 <= moved["top"] < 400) or moved["hash"] != "#values-auditing/health-check":
                        errors.append(f"{tag}row link did not scroll to its section: {moved}")
                    # The tab follows league settings.
                    before = page.evaluate("() => document.querySelector('.audit-pie-meta').textContent")
                    page.evaluate("() => { const C = window.TradeValueCurveControls; C.setTeams(C.getState().teams === 10 ? 14 : 10); window.dispatchEvent(new CustomEvent('trade-value-shared-change')); }")
                    page.wait_for_timeout(500)
                    after = page.evaluate("() => document.querySelector('.audit-pie-meta').textContent")
                    if before == after:
                        errors.append(f"{tag}the tab did not follow a league settings change ({before!r})")
                    # Numbers on screen equal the engine's.
                    tie = page.evaluate("""() => { const C = window.TradeValueCurveControls, i = C.getInspection();
                      const rows = [...document.querySelectorAll('table[aria-label="Starter, bench and total value by source"] tbody tr')];
                      const want = Object.keys(i.valuePipeline.sources).length;
                      const totals = rows.map(r => Number(r.cells[3].textContent));
                      return {rows: rows.length, want, pie: i.valuePipeline.pie, totals}; }""")
                    if tie["rows"] != tie["want"] or any(abs(t - tie["pie"]) > 0.06 for t in tie["totals"]):
                        errors.append(f"{tag}table rows/totals do not tie to the engine: {tie}")
                if page_errors:
                    errors.append(f"{tag}page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


SWEEP_JS = """async ([scoring, teams]) => {
  const C = window.TradeValueCurveControls;
  C.setScoring(scoring); C.setTeams(teams);
  window.dispatchEvent(new CustomEvent('trade-value-shared-change'));
  await new Promise(r => setTimeout(r, 250));
  const rows = [...document.querySelectorAll('.audit-pie-check')].map(r => [r.dataset.check, r.dataset.status, r.innerText]);
  const insp = C.getInspection();
  return {rows, pie: insp.valuePipeline.pie, meta: document.querySelector('.audit-pie-meta').textContent,
    bad: /NaN|undefined|Infinity|null/.test(document.getElementById('audit-pie-root').innerText),
    tables: document.querySelectorAll('#audit-pie-root table').length, teams: insp.setting.teams, scoring: insp.setting.scoring};
}"""


def sweep_checks() -> list[str]:
    """3 scorings x 4 league sizes on the live page: the tab follows each setting, renders cleanly, and healthy data stays healthy."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors: list[str] = []
    with _built_dist(POSTS) as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(base + "#values-auditing/health-check", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueCurveControls.isReady()", timeout=40000)
            page.wait_for_selector(".audit-pie-checks", timeout=15000)
            seen = set()
            for scoring in ("standard", "half_ppr", "ppr"):
                for teams in (8, 10, 12, 14):
                    got = page.evaluate(SWEEP_JS, [scoring, teams])
                    tag = f"[{scoring} {teams}] "
                    seen.add(got["pie"])
                    if [r[0] for r in got["rows"]] != CHECK_IDS:
                        errors.append(f"{tag}rows {[r[0] for r in got['rows']]}")
                    if got["bad"] or got["tables"] < 9:
                        errors.append(f"{tag}page text has NaN/undefined or {got['tables']} tables")
                    if f"{teams} teams" not in got["meta"]:
                        errors.append(f"{tag}header does not follow the league size: {got['meta']!r}")
                    flags = [r[0] for r in got["rows"] if r[1] == "flag"]
                    if flags != HEALTHY_FLAGS:
                        errors.append(f"{tag}flags {flags} on healthy data")
                    if any(r[0] in INFO_IDS and r[1] != "info" for r in got["rows"]):
                        errors.append(f"{tag}an information row changed status")
            if len(seen) != 4:
                errors.append(f"the value pie took {len(seen)} values across 12 settings, want 4 (one per league size)")
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


class HealthCheckRenderTest(unittest.TestCase):
    def test_twelve_combo_sweep(self):
        self.assertEqual(sweep_checks(), [])

    def test_logic_and_copy_on_frozen_fixtures(self):
        self.assertEqual(logic_checks(), [])

    def test_live_page(self):
        self.assertEqual(live_checks(), [])


# One named bug at a time; every logic check below must be caught by logic_checks().
BROKEN_LOGIC = {
    "verdict strip removed": ("rootEl.appendChild(buildVerdictStrip(checks, data));", ""),
    "starter limit loosened so a perturbed source never flags": ("starterSpread: 0.17,", "starterSpread: 9,"),
    "flag names every source": ("sources: stFlag ? [st.outlier.src] : [], positions: [],", "sources: stFlag ? data.rows.map(function (r) { return r.src; }) : [], positions: [],"),
    "QB can flag": ('id: "qb", section: "positions", name: "QB starters",\n      status: "info"', 'id: "qb", section: "positions", name: "QB starters",\n      status: qb.spread > 0.15 ? "flag" : "info"'),
    "bench can flag": ('id: "bench", section: "starters", name: "Bench totals",\n      status: "info"', 'id: "bench", section: "starters", name: "Bench totals",\n      status: bench.spread > 0.5 ? "flag" : "info"'),
    "code reference in a note": ("A large shift means the source's value shape disagrees", "Raw is groups[pos|role] in value-model.js. A large shift means the source's value shape disagrees"),
    "a term dropped from the legend": ('    ["Value above waivers", "A player\'s value above the best replacement available on waivers."],\n', ""),
    "row link removed": ('a.setAttribute("data-flag-section", id);', ""),
    "section heading not a question": ('"Do sources agree by position?"', '"Position agreement"'),
    "how-to-read line dropped": ('if (lede) sec.appendChild(el("p", "audit-pie-note audit-pie-how", lede));', ""),
    "raw section open by default": ('var details = el("details", "audit-pie-section audit-pie-raw");', 'var details = el("details", "audit-pie-section audit-pie-raw"); details.open = true;'),
    "table without aria-label": ('table.setAttribute("aria-label", label);   // JEG-904', ""),
    "table without caption": ('table.appendChild(caption);', ""),
    "th scope dropped": ('node.setAttribute("scope", "col");   // JEG-904', ""),
    "row not announced": ('li.setAttribute("aria-live", "polite");', ""),
    "status decided by wording": ('status: stFlag ? "flag" : "pass",', 'status: stFlag && plainLabel("espn").length <= 4 ? "flag" : "pass",'),
    "table cell mark dropped": ('if (stCheck.status === "flag" && stCheck.sources.indexOf(r.src) >= 0) {', 'if (false) {'),
    "bench explanation dropped": ('note.setAttribute("data-bench-note", "");', 'note.remove();'),
}


class HealthCheckGuardTest(unittest.TestCase):
    def test_guard_fails_on_broken_builds(self):
        js = PIE_JS.read_text(encoding="utf-8")
        for name, (old, new) in BROKEN_LOGIC.items():
            with self.subTest(mutation=name):
                self.assertIn(old, js, f"mutation anchor for {name!r} is stale")
                broken = js.replace(old, new, 1)
                try:
                    caught = logic_checks(broken)
                except Exception as exc:  # noqa: BLE001  (a build that breaks the page counts as caught)
                    if isinstance(exc, unittest.SkipTest):
                        raise
                    caught = [f"page threw: {exc}"]
                self.assertNotEqual(caught, [], f"checks did not catch: {name}")


def setUpModule():
    _render_env.ensure_built()


if __name__ == "__main__":
    unittest.main()
