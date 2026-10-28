"""v2 mobile phase 1 (JEG-947, under JEG-927): scrolling tables, tap targets, hover rules, text size.

Jeremy, 2026-10-23: tables are a sticky name column with horizontal scroll (B1). The chart pop-out and the hamburger
nav are later phases and are not covered here (the chart's own labels, legend and brush are excluded on purpose).

Checks the built page headless with touch emulation (has_touch + is_mobile, deviceScaleFactor 2):
  * overflow:   no horizontal page overflow at 320, 360 and 390 px on every tab;
  * tables:     every table wider than its box at 360 px sits in an overflow-x scroll container, its name column is
                sticky (still pinned after scrolling sideways), and the right edge shows a fade cue that is gone at
                the end of the scroll;
  * tap:        every control the audit listed has at least a 44 x 44 px hit area (its box, or the 44 px square
                around its centre lands on it) at 390 and 844 x 390 (landscape) and 320 px;
  * hover:      no :hover rule outside @media (hover: hover) in the v2 style sheets, and an unsorted Values header
                still shows its sort arrow where there is no hover;
  * text:       no visible text below 12 px at 320, 360 and 390 px (the chart's SVG and brush labels are phase 2);
  * names:      the pinned name column reads "Last, First" (suffixes and "St. Brown" kept together), clips with an
                ellipsis, titles carry the full name, a tap on a clipped name shows it in a popover without opening the row,
                and desktop names are untouched (JEG-947, Jeremy 2026-10-23);
  * desktop:    at 1366 x 768, 1280 x 800 and 1024 x 768 (fine pointer) none of the touch rules apply.

Discrimination: test_guard_fails_on_broken_builds serves a broken v2.css / audit-pie.css for each check and requires
that check to report an error.
"""
from __future__ import annotations

import functools
import json
import unittest

from playwright.sync_api import Error as PlaywrightError  # noqa: F401

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_expand_render import DIST, V2_CSS, _built_dist, _serve  # noqa: E402

AUDIT_PIE_CSS = V2_CSS.parent / "audit-pie.css"
NAMEFMT_JS = (V2_CSS.parent / "name-format.js").read_text(encoding="utf-8")

ALL_TABS = ("writing/manifesto", "player-values", "trade-targets", "risers-fallers", "compare-trade", "find-trade", "writing/how-values", "values-auditing")
TAP_TABS = ("player-values", "trade-targets", "compare-trade", "find-trade", "values-auditing")
TABLE_TABS = ("player-values", "trade-targets", "values-auditing")
PHONES = ((390, 844), (360, 740), (320, 568))
LANDSCAPE = (844, 390)
DESKTOPS = ((1366, 768), (1280, 800), (1024, 768))


def setUpModule():
    _render_env.ensure_built()


# Chart internals (SVG, legend row, brush) are phase 2.
CHART = ".v2-chart-head, .v2-plot, .v2-brush, .v2-ybrush, svg"

# Under mobile emulation the layout viewport grows to fit overflowing content (innerWidth == scrollWidth), exactly like a
# phone zooming the page out; so overflow is measured against the device width, not innerWidth.
OVERFLOW = "(w) => ({doc: Math.max(document.documentElement.scrollWidth, innerWidth) - w, body: document.body.scrollWidth - w})"

TAP = r"""() => {
  const CHART = '%s';
  const sel = 'a[href], button, input, select, textarea, summary, [role=button], [role=tab], [onclick], .has-math';
  const hitOk = (box, x, y) => { const h = document.elementFromPoint(x, y); return !!h && box.contains(h); };
  const bad = [];
  for (const el of document.querySelectorAll(sel.split(', ').map(s => '.v2-app ' + s).join(', '))) {
    if (!el.checkVisibility() || el.closest(CHART) || el.matches('input[type=hidden]')) continue;
    // JEG-1193: the one-line context strip (JEG-1119) clips its legend, Reviewed chip included; tracked there, not here.
    if (el.matches('#v2ShowingLegend a.v2-div-chip')) continue;
    // A checkbox or radio is tapped through its label.
    const box = el.matches('input[type=checkbox], input[type=radio]') && el.labels && el.labels[0] ? el.labels[0] : el;
    box.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
    const r = box.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (r.width >= 43.5 && r.height >= 43.5) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const pts = [[cx, cy - 21], [cx, cy + 21], [cx - 21, cy], [cx + 21, cy]];
    if (pts.every(([x, y]) => x < 0 || y < 0 || x >= innerWidth || y >= innerHeight || hitOk(box, x, y))) continue;
    bad.push(el.tagName + '.' + String(el.className).slice(0, 30) + (el.id ? '#' + el.id : '') + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' "' + (el.textContent || '').trim().slice(0, 14) + '"');
  }
  window.scrollTo(0, 0);
  return [...new Set(bad)];
}""" % CHART

TABLES = r"""async () => {
  const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const out = [];
  const wraps = new Set();
  for (const t of document.querySelectorAll('.v2-app table')) {
    if (!t.checkVisibility()) continue;
    const wrap = t.closest('.v2-table-wrap, .audit-pie-scroll, .v2-ptable-wrap, .v2-dmatrix-wrap');
    const name = t.className + '#' + t.id;
    if (!wrap) { if (t.getBoundingClientRect().right > innerWidth + 1) out.push(name + ': wider than the screen and not in a scroll container'); continue; }
    if (wrap.scrollWidth <= wrap.clientWidth + 1) continue;       // fits: nothing to scroll
    if (wraps.has(wrap)) continue;
    wraps.add(wrap);
    const ox = getComputedStyle(wrap).overflowX;
    if (ox !== 'auto' && ox !== 'scroll') { out.push(name + ': scroll container has overflow-x ' + ox); continue; }
    // First visible body cell (the name column) must be sticky and stay pinned after a sideways scroll.
    const row = [...t.tBodies[0].rows].find(r => r.checkVisibility() && !r.classList.contains('audit-pie-verdict-row') && r.cells.length > 2);
    const cell = row && [...row.cells].find(c => c.checkVisibility());
    if (!cell) continue;
    if (getComputedStyle(cell).position !== 'sticky') { out.push(name + ': first column (' + cell.className + ') is ' + getComputedStyle(cell).position + ', not sticky'); continue; }
    wrap.scrollLeft = 0;
    await frame();
    const fade0 = parseFloat(getComputedStyle(wrap).getPropertyValue('--v2-edge-fade')) || 0;
    const mask0 = getComputedStyle(wrap).maskImage || getComputedStyle(wrap).webkitMaskImage;
    if (!(fade0 > 0) || !/linear-gradient/.test(mask0)) out.push(name + ': no edge fade cue at scroll start (fade ' + fade0 + ', mask ' + mask0 + ')');
    const left0 = cell.getBoundingClientRect().left, wl = wrap.getBoundingClientRect().left;
    wrap.scrollLeft = Math.min(120, (wrap.scrollWidth - wrap.clientWidth) / 2);
    await frame();
    if (wrap.scrollLeft < 20) { out.push(name + ': did not scroll sideways'); continue; }
    const moved = cell.getBoundingClientRect().left;
    if (Math.abs(moved - left0) > 1.5) out.push(name + ': first column moved ' + Math.round(moved - left0) + 'px when the table scrolled (not pinned)');
    wrap.scrollLeft = wrap.scrollWidth;
    await frame();
    const fadeEnd = parseFloat(getComputedStyle(wrap).getPropertyValue('--v2-edge-fade')) || 0;
    if (fadeEnd > 0.5) out.push(name + ': edge fade still ' + fadeEnd + 'px at the end of the scroll');
    wrap.scrollLeft = 0;
  }
  return out;
}"""

HOVER_RULES = r"""() => {
  const bad = [];
  const walk = (rules, guarded, sheet) => { for (const r of rules) {
    if (r.selectorText !== undefined) { if (/:hover/.test(r.selectorText) && !guarded) bad.push(sheet + ': ' + r.selectorText.slice(0, 80)); }   // style rules also have cssRules (nesting): test them first
    else if (r.cssRules) walk(r.cssRules, guarded || (r.media && /hover:\s*hover/.test(r.media.mediaText)), sheet); } };
  for (const s of document.styleSheets) { const href = s.href || ''; if (!/\/v2\//.test(href)) continue; try { walk(s.cssRules, false, href.split('/').pop()); } catch (e) {} }
  return bad;
}"""

SORT_ARROW = r"""() => {
  const th = [...document.querySelectorAll('#v2Table thead th')].find(t => t.querySelector('button') && !t.hasAttribute('aria-sort') || (t.getAttribute('aria-sort') === 'none'));
  if (!th) return 'no unsorted sortable header found';
  const c = getComputedStyle(th.querySelector('.th-1'), '::after').content;
  return /↕/.test(c) ? '' : 'unsorted header shows no sort arrow without hover (content ' + c + ')';
}"""

TEXT = r"""() => {
  const CHART = '%s';
  const bad = {};
  const w = document.createTreeWalker(document.querySelector('.v2-app'), NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const t = w.currentNode; if (!t.textContent.trim()) continue;
    const el = t.parentElement; if (!el.checkVisibility() || el.closest(CHART)) continue;
    const s = parseFloat(getComputedStyle(el).fontSize);
    if (s < 12) { const k = el.tagName + '.' + String(el.className).slice(0, 30) + ' ' + s + 'px'; bad[k] = 1; }
  }
  return Object.keys(bad);
}""" % CHART

NAMES = r"""(phone) => {
  const out = [];
  const spans = [...document.querySelectorAll('#v2Table .v2-nm, .v2-ttable .v2-nm')].filter(e => e.checkVisibility());
  if (!spans.length) return ['no visible player-name cells found'];
  for (const e of spans.slice(0, 60)) {
    const full = e.dataset.full, t = e.textContent;
    if (e.title !== full) out.push('title is not the full name for ' + full);
    if (!phone) { if (t !== full) out.push('desktop name changed: ' + t); continue; }
    if (!/, /.test(t) || t === full) out.push('phone name is not Last, First: ' + t + ' (' + full + ')');
    if (/ (Jr\.|Sr\.|II|III|IV|V)$/.test(full) && !/^[^,]+ (Jr\.|Sr\.|II|III|IV|V), /.test(t)) out.push('suffix not kept with the last name: ' + t);
    const cs = getComputedStyle(e);
    if (cs.textOverflow !== 'ellipsis' || cs.overflow !== 'hidden' || cs.whiteSpace !== 'nowrap') out.push('long names do not clip with an ellipsis (' + cs.textOverflow + ', ' + cs.overflow + ')');
  }
  const names = new Map(spans.map(e => [e.dataset.full, e.textContent]));
  if (phone && names.has('Kenneth Walker III') && names.get('Kenneth Walker III') !== 'Walker III, Kenneth') out.push('Kenneth Walker III shows as ' + names.get('Kenneth Walker III'));
  if (phone && names.has('Jaxon Smith-Njigba') && names.get('Jaxon Smith-Njigba') !== 'Smith-Njigba, Jaxon') out.push('Jaxon Smith-Njigba shows as ' + names.get('Jaxon Smith-Njigba'));
  if (phone && names.has('Amon-Ra St. Brown') && names.get('Amon-Ra St. Brown') !== 'St. Brown, Amon-Ra') out.push('Amon-Ra St. Brown shows as ' + names.get('Amon-Ra St. Brown'));
  return out;
}"""

NAME_TAP = r"""() => {
  const out = [];
  const spans = [...document.querySelectorAll('#v2Table .v2-nm')].filter(e => e.checkVisibility());
  let span = spans.find(e => e.scrollWidth > e.clientWidth + 1);
  if (!span && spans.length) {
    // JEG-1048: the first 50 rows can all fit the 148 px column (week 7 data: longest "Walker III, Kenneth", 133 px), so
    // a tap on a clipped name had nothing to tap. Lengthen the first name the way a long one reads, then tap it: the
    // popover handler is the code under test, and a column that no longer clips still fails here (the popover never shows).
    span = spans[0];
    span.dataset.full = 'Valdes-Scantling Marquez Jr.';
    span.title = span.dataset.full;
    span.textContent = 'Valdes-Scantling Jr., Marquez';
  }
  if (!span) return ['no clipped name found to tap'];
  span.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = span.getBoundingClientRect();
  return {x: r.left + 6, y: r.top + r.height / 2, full: span.dataset.full};
}"""

DESKTOP = r"""() => {
  const out = [];
  const rowH = getComputedStyle(document.documentElement).getPropertyValue('--v2-row-h').trim();
  if (rowH === '44px') out.push('row height is ' + rowH + ' on a fine pointer');
  for (const w of document.querySelectorAll('.v2-table-wrap, .audit-pie-scroll')) {
    const m = getComputedStyle(w).maskImage; if (m && m !== 'none') { out.push('edge fade mask on desktop: ' + w.className); break; }
  }
  const sticky = document.querySelector('.v2-ttable td.player'); if (sticky && getComputedStyle(sticky).position === 'sticky') out.push('Targets table name column is sticky on desktop');
  const b = document.querySelector('#v2Table th button'); if (b && parseFloat(getComputedStyle(b).minHeight) >= 44) out.push('table header button min-height ' + getComputedStyle(b).minHeight + ' on desktop');
  if (document.documentElement.scrollWidth > innerWidth) out.push('page overflows sideways on desktop');
  return out;
}"""


def run_checks(overrides=None, checks=("overflow", "tables", "tap", "hover", "text", "desktop", "names")) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc

        def open_page(width, height, touch):
            ctx = browser.new_context(viewport={"width": width, "height": height}, has_touch=touch, is_mobile=touch, device_scale_factor=2 if touch else 1)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(f"[{width}x{height}] page error {e}"))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            for name, (body, ctype) in (overrides or {}).items():
                # "assets/..." is published data the page fetches from the site root (its <base> is ../).
                page.route(f"**/{name}*" if name.startswith("assets/") else f"**/v2/{name}*", functools.partial(_serve, body, ctype))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
            return ctx, page

        def go(page, tab):
            page.evaluate(f"() => {{ location.hash = '#{tab}'; }}")
            page.wait_for_timeout(1500 if tab == "risers-fallers" else 450)

        try:
            for width, height in PHONES:
                if not ({"overflow", "tables", "text", "hover", "names"} & set(checks)):
                    break
                ctx, page = open_page(width, height, True)
                tag = f"[{width}x{height}] "
                if "hover" in checks and width == 390:
                    errors += [f"{tag}unguarded hover rule {e}" for e in page.evaluate(HOVER_RULES)]
                    msg = page.evaluate(SORT_ARROW)
                    if msg:
                        errors.append(tag + msg)
                for tab in ALL_TABS:
                    go(page, tab)
                    if "overflow" in checks:
                        o = page.evaluate(OVERFLOW, width)
                        if o["doc"] > 0 or o["body"] > 0:
                            errors.append(f"{tag}{tab}: page overflows sideways by {max(o['doc'], o['body'])}px")
                    if "text" in checks:
                        errors += [f"{tag}{tab}: text under 12px {e}" for e in page.evaluate(TEXT)]
                    if "names" in checks and width == 390 and tab == "player-values":
                        errors += [f"{tag}{tab}: {e}" for e in page.evaluate(NAMES, True)]
                        hit = page.evaluate(NAME_TAP)
                        page.wait_for_timeout(300)
                        if isinstance(hit, list):
                            errors += [f"{tag}{tab}: {e}" for e in hit]
                        else:
                            page.touchscreen.tap(hit["x"], hit["y"])
                            page.wait_for_timeout(200)
                            pop = page.evaluate("document.querySelector('.v2-nm-pop')?.textContent || ''")
                            if pop != hit["full"]:
                                errors.append(f"{tag}{tab}: tapping a clipped name shows {pop!r}, not {hit['full']!r}")
                            if page.evaluate("document.querySelector('.v2-drawer') && !document.querySelector('.v2-drawer').hidden"):
                                errors.append(f"{tag}{tab}: tapping the name popover opened the row drawer instead")
                    if "tables" in checks and width == 360 and tab in TABLE_TABS:
                        errors += [f"{tag}{tab}: {e}" for e in page.evaluate(TABLES)]
                ctx.close()
            if "tap" in checks:
                for width, height in PHONES[:1] + PHONES[2:] + (LANDSCAPE,):
                    ctx, page = open_page(width, height, True)
                    for tab in TAP_TABS:
                        go(page, tab)
                        errors += [f"[{width}x{height}] {tab}: tap target under 44x44 {e}" for e in page.evaluate(TAP)]
                    ctx.close()
            if "reviewedlink" in checks:   # the pinned Reviewed chip is a visible link the tap check measures (outside the JEG-1193 strip)
                ctx, page = open_page(*PHONES[0], True)
                seen = 0
                for tab in TAP_TABS:
                    go(page, tab)
                    seen += page.evaluate("() => [...document.querySelectorAll('.v2-app a.v2-div-chip[data-status=reviewed][href]')].filter(a => a.checkVisibility() && !a.closest('#v2ShowingLegend')).length")
                if not seen:
                    errors.append("no visible linked Reviewed chip on " + ", ".join(TAP_TABS))
                ctx.close()
            if "tables" in checks:
                ctx, page = open_page(*LANDSCAPE, True)       # a landscape phone is 844 px wide: touch rules, not width rules
                for tab in ("player-values", "trade-targets"):
                    go(page, tab)
                    errors += [f"[844x390] {tab}: {e}" for e in page.evaluate(TABLES)]
                    if "names" in checks and tab == "trade-targets":
                        errors += [f"[844x390] {tab}: {e}" for e in page.evaluate(NAMES, True)]
                ctx.close()
            if "desktop" in checks:
                for width, height in DESKTOPS:
                    ctx, page = open_page(width, height, False)
                    for tab in ("player-values", "trade-targets", "values-auditing"):
                        go(page, tab)
                        errors += [f"[{width}x{height}] {tab}: {e}" for e in page.evaluate(DESKTOP)]
                        if "names" in checks and tab != "values-auditing":
                            errors += [f"[{width}x{height}] {tab}: {e}" for e in page.evaluate(NAMES, False)]
                    ctx.close()
        finally:
            browser.close()
    return errors


def flagged_chart_freshness() -> str:
    """The built reference-freshness.json with a default Values column (USA Today) flagged out of range.

    The header chip word only exists when a column the Values table shows by default (the four trade charts) carries a
    worded chip. Week 7 had FantasyPros "Reviewed" (JEG-1048 wrote the mutation against it); from week 8 every default
    chart is ok or in range (a checkmark, no word), so the mutation changed nothing on the page. Pin one flagged chart."""
    doc = json.loads((DIST / "assets" / "reference-freshness.json").read_text(encoding="utf-8"))
    doc.setdefault("source_divergence", {})["usatoday"] = {
        "status": "warn", "message": "USA Today disagrees with the other charts on 38% of players this week (usually 20%).",
        "resolution_issue": None, "outlier_rate": 0.38, "usual_outlier_rate": 0.20}
    return json.dumps(doc)


def reviewed_chart_freshness() -> str:
    """The built reference-freshness.json with a default Values column (FantasyPros) reviewed, linked to a public page.

    The Reviewed chip is a link only when its resolution issue is a public http(s) page (no Linear links since #916), and
    the week's data may have none, so "Reviewed chip loses its hit area" changed nothing on the page and was caught only
    while another tap target failed. Pin one linked Reviewed chip (the page never fetches it: outside requests abort)."""
    doc = json.loads((DIST / "assets" / "reference-freshness.json").read_text(encoding="utf-8"))
    doc.setdefault("source_divergence", {})["fantasypros"] = {
        "status": "reviewed", "message": "FantasyPros was reviewed: its ordering is unusual but correct.",
        "resolution_issue": "https://example.com/ddf-review/fantasypros"}
    return json.dumps(doc)


class MobilePhase1RenderTest(unittest.TestCase):
    def test_phase1_guards_hold(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        css = V2_CSS.read_text(encoding="utf-8")
        pie = AUDIT_PIE_CSS.read_text(encoding="utf-8")
        text_css = "text/css"
        flagged = flagged_chart_freshness()
        reviewed = reviewed_chart_freshness()
        # The pinned data alone must pass the text check, so the mutation below is caught for the 0 px word, not the data.
        with self.subTest(mutation="baseline: a flagged default chart, unbroken CSS"):
            self.assertEqual(run_checks({"assets/reference-freshness.json": (flagged, "application/json")}, checks=("text",)), [])
        with self.subTest(mutation="baseline: a linked Reviewed chip, unbroken CSS"):
            self.assertEqual(run_checks({"assets/reference-freshness.json": (reviewed, "application/json")}, checks=("tap",)), [])
            links = run_checks({"assets/reference-freshness.json": (reviewed, "application/json")}, checks=("reviewedlink",))
            self.assertEqual(links, [], "the pinned Reviewed chip must be a link on the page")
        broken = {
            # name: (check, {file: (body, type)}, anchor text that must exist in the source)
            "table scroll container removed": ("tables", {"v2.css": (css.replace(".v2-table-wrap { overflow-x: auto; margin-top: 12px; }", ".v2-table-wrap { overflow-x: visible; margin-top: 12px; }", 1).replace("#v2Main .v2-table-wrap { position: relative; margin-top: 8px; overflow: auto; }", "#v2Main .v2-table-wrap { position: relative; margin-top: 8px; overflow: visible; }", 1), text_css)},
                                               ".v2-table-wrap { overflow-x: auto; margin-top: 12px; }"),
            "page overflows sideways": ("overflow", {"v2.css": (css + "\n@media (max-width: 767px) { #v2Main { min-width: 520px; } }\n", text_css)}, None),
            "Values name column not sticky": ("tables", {"v2.css": (css.replace(".v2-table td:nth-child(2), .v2-table th:nth-child(2) { position: sticky;", ".v2-table td:nth-child(2), .v2-table th:nth-child(2) { position: static;", 1), text_css)},
                                              ".v2-table td:nth-child(2), .v2-table th:nth-child(2) { position: sticky;"),
            "auditing name column not sticky": ("tables", {"audit-pie.css": (pie, text_css), "v2.css": (css.replace(".audit-pie-table tr:not(.audit-pie-verdict-row) > :first-child { position: sticky;", ".audit-pie-table tr:not(.audit-pie-verdict-row) > :first-child { position: static;", 1), text_css)},
                                                ".audit-pie-table tr:not(.audit-pie-verdict-row) > :first-child { position: sticky;"),
            "edge fade cue removed": ("tables", {"v2.css": (css.replace("mask-image: linear-gradient(to right, #000 calc(100% - var(--v2-edge-fade)), transparent);", "", 1), text_css)},
                                      "mask-image: linear-gradient(to right, #000 calc(100% - var(--v2-edge-fade)), transparent);"),
            "table header buttons back to 32px": ("tap", {"v2.css": (css.replace(".v2-vtable th button, .v2-select, .v2-cexpand, #v2Compare .v2-ctable td.player .v2-cexpand { min-height: 44px; }", ".v2-vtable th button, .v2-select, .v2-cexpand, #v2Compare .v2-ctable td.player .v2-cexpand { min-height: 32px; }", 1), text_css)},
                                                  ".v2-vtable th button, .v2-select, .v2-cexpand, #v2Compare .v2-ctable td.player .v2-cexpand { min-height: 44px; }"),
            "source link arrows lose their hit area": ("tap", {"v2.css": (css.replace(".v2-vtable th .v2-srclink-head { padding: 16px 18px; margin: -16px -13px -16px -18px; }", ".v2-vtable th .v2-srclink-head { padding: 0 3px; }", 1), text_css)},
                                                         ".v2-vtable th .v2-srclink-head { padding: 16px 18px; margin: -16px -13px -16px -18px; }"),
            "unguarded hover rule": ("hover", {"v2.css": (css + "\n.v2-chip:hover { border-color: red; }\n", text_css)}, None),
            "no touch sort arrow": ("hover", {"v2.css": (css.replace("@media (hover: none) { .v2-vtable th button .th-1::after { content: \" ↕\"; opacity: .45; } }", "", 1), text_css)},
                                    "@media (hover: none) { .v2-vtable th button .th-1::after { content: \" ↕\"; opacity: .45; } }"),
            "small text back to 11px": ("text", {"v2.css": (css.replace(".v2-find-slot, .v2-tab.is-soon::after { font-size: 12px; }", ".v2-find-slot, .v2-tab.is-soon::after { font-size: 12px; }\n@media (max-width: 767px) { .v2-table .player-sub, .v2-vtable .player-sub, .v2-vtable .th-2 { font-size: 11px; } }", 1), text_css)},
                                         ".v2-find-slot, .v2-tab.is-soon::after { font-size: 12px; }"),
            "names stay First Last on phones": ("names", {"name-format.js": (NAMEFMT_JS.replace("function lastFirst(name, pos) {", "function lastFirst(name, pos) { return String(name);", 1), "application/javascript")}, None),
            "suffix dropped from the last name": ("names", {"name-format.js": (NAMEFMT_JS.replace("var SUFFIX_RE = /^(jr|sr|ii|iii|iv|v)\\.?$/i;", "var SUFFIX_RE = /^$/;", 1), "application/javascript")}, None),
            "names no longer clip": ("names", {"v2.css": (css + "\n@media (max-width: 767px), (pointer: coarse) { .v2-table td.player .v2-nm, .v2-ttable td.player .v2-nm { text-overflow: clip; white-space: normal; } }\n", text_css)}, None),
            # JEG-1048: the Reviewed chip is a link (JEG-609) and needs its 44 px hit area; a header chip word must not be a 0 px text node.
            # The chip that stays on screen on a phone is Targets' (the context strip's is clipped, JEG-1193).
            "Reviewed chip loses its hit area": ("tap", {"v2.css": (css.replace(".v2-tdiv-item a.v2-div-chip::after, .v2-ttable a.v2-div-chip::after { content: \"\"; position: absolute; left: 50%; top: 50%; width: max(100%, 44px); height: 44px; transform: translate(-50%, -50%); }", "", 1), text_css),
                                                         "assets/reference-freshness.json": (reviewed, "application/json")},
                                                  ".v2-tdiv-item a.v2-div-chip::after, .v2-ttable a.v2-div-chip::after { content: \"\"; position: absolute; left: 50%; top: 50%; width: max(100%, 44px); height: 44px; transform: translate(-50%, -50%); }"),
            "header chip word back to 0px text": ("text", {"v2.css": (css.replace(".v2-vtable .th-2 .v2-div-chip > .v2-div-word { display: none; }", ".v2-vtable .th-2 .v2-div-chip > .v2-div-word { font-size: 0; }", 1), text_css),
                                                           "assets/reference-freshness.json": (flagged, "application/json")},
                                                  ".v2-vtable .th-2 .v2-div-chip > .v2-div-word { display: none; }"),
            "touch rules leak to desktop": ("desktop", {"v2.css": (css + "\n.v2-table-wrap { -webkit-mask-image: linear-gradient(to right, #000 90%, transparent); mask-image: linear-gradient(to right, #000 90%, transparent); }\n", text_css)}, None),
        }
        for name, (check, files, anchor) in broken.items():
            with self.subTest(mutation=name):
                for fname, (body, _) in files.items():
                    if fname == "name-format.js":
                        self.assertNotEqual(body, NAMEFMT_JS, f"mutation {name!r} changed nothing")
                if anchor is not None:
                    self.assertIn(anchor, css + pie, f"mutation anchor for {name!r} is stale")
                    self.assertTrue(any(body != (css if fname == "v2.css" else pie) for fname, (body, _) in files.items() if not fname.startswith("assets/")), f"mutation {name!r} changed nothing")
                self.assertNotEqual(run_checks(files, checks=(check,)), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
