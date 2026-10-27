"""v2 source links and the indexed-value math on hover (JEG-457, contract GL-27, TT-12), rendered.

Part 1: every source name links to the publisher's page (a new tab). The addresses are the ones in
assets/comparison-sources-data.json, read here independently. Checked on Trade targets (column heads at 1100 px,
chart values in the expanded row, the "Compare against" link), the Showing legend, Player values column heads (a link
beside the sort button: clicking it does not sort), Customize rows (clicking it does not toggle the source) and the
Compare series rows. A projection source with a page per position uses the player's position in row context.

Part 2: hovering or focusing a chart value on Trade targets shows the math, leading with the number as the publisher
prints it. For three players per chart that number equals the published number in the data file, "x rescale factor"
times it equals the rescaled value shown, and "- our value" gives the gap shown. A player the chart does not price
shows the reason. The cell is keyboard-focusable with aria-describedby.

Discrimination: test_guard_fails_on_broken_builds serves v2.js without the head link, with the head link inside the
sort button, and with a wrong "original" number, and requires failures.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
V2_JS = ROOT / "app" / "v2" / "v2.js"

from tests.test_v2_targets_render import build_v2_page  # noqa: E402
from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
NAMES = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS Sports"}


def load_data():
    return json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))


def expected_urls(data):
    out = {}
    for key, s in data["sources"].items():
        url = s.get("url") or s.get("source_url")
        if isinstance(url, str) and url.startswith("http"):
            out[key] = url
    return out


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)   # JEG-834: test the source in app/v2, not a stale committed build

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(Quiet, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


NO_NAV = "() => document.addEventListener('click', e => { if (e.target.closest('a[target=_blank]')) e.preventDefault(); }, true)"

LINKS = """(sel) => [...document.querySelectorAll(sel)].map(a => ({pub: a.dataset.sourceLink, href: a.getAttribute('href'), target: a.target, rel: a.rel,
  text: a.textContent, inButton: Boolean(a.closest('button')), visible: a.offsetParent !== null}))"""


def check_links(links, expected, tag, want_pubs, allow_missing=()):
    errors = []
    seen = {l["pub"] for l in links}
    for pub in want_pubs:
        if pub in allow_missing:
            continue
        if pub not in expected:
            continue
        if pub not in seen:
            errors.append(f"{tag}: no link for {pub}")
    for l in links:
        want = expected.get(l["pub"])
        if want is None:
            errors.append(f"{tag}: a link for {l['pub']} with no address in the data")
        elif l["pub"] in ("cbsros", "razzball"):
            if not re.sub(r"/(QB|RB|WR|TE)/", "/QB/", re.sub(r"-(qb|rb|wr|te)-", "-qb-", l["href"])) == want:
                errors.append(f"{tag}: {l['pub']} link {l['href']!r} is not a position variant of {want!r}")
        elif l["href"] != want:
            errors.append(f"{tag}: {l['pub']} link {l['href']!r}, want {want!r}")
        if l["target"] != "_blank" or "noopener" not in l["rel"]:
            errors.append(f"{tag}: {l['pub']} link should open a new tab safely: target {l['target']!r}, rel {l['rel']!r}")
    return errors


def run_checks(js_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    data = load_data()
    expected = expected_urls(data)
    combo = "full_12"
    name_of = {pk: name for name, pk in data["player_keys"].items()}
    js = V2_JS.read_text(encoding="utf-8")
    if js_patch:
        old, new = js_patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        page_errors: list[str] = []

        def open_page(hash_, width=1000, height=1000):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if js_patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            page.goto(base + hash_, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
            page.wait_for_function("() => document.querySelector('a[data-source-link]')", timeout=30000)
            page.evaluate(NO_NAV)
            page.wait_for_timeout(300)
            return page

        try:
            # Trade targets.
            page = open_page("#trade-targets")
            page.wait_for_function("() => window.TradeValueV2.targets() && document.querySelector('#v2TTable tbody tr[data-player-key]')", timeout=60000)
            # A held source (fidelity or coverage hold) has no column, legend entry or cell; the charts to
            # walk are the ones the build shows now (JEG-675).
            shown = page.evaluate("() => window.TradeValueCurveControls.getActiveSources()")
            charts = [c for c in CHARTS if c in shown]
            if len(charts) < 2:
                errors.append(f"[targets heads] want at least two chart sources shown, got {shown}")
            heads = page.evaluate(LINKS, "#v2TTable thead th[data-chart] a[data-source-link]")
            errors += check_links(heads, expected, "[targets heads]", charts)
            if len({l["pub"] for l in heads}) < 2:
                errors.append(f"[targets heads] only {[l['pub'] for l in heads]} linked")
            # JEG-851 (superseding JEG-834): a single chart is now selectable, so Compare against offers
            # "All trade charts" plus the chart sources shown; nothing else.
            enabled = page.evaluate("() => [...document.querySelectorAll('#v2TChart option')].filter(o => !o.disabled).map(o => o.value)")
            if "all" not in enabled or not set(enabled) - {"all"} or not set(enabled) <= {"all"} | set(CHARTS):
                errors.append(f"[compare against] selectable options {enabled}, want 'all' plus shown charts from {charts}")
            # Math on hover: three players per chart.
            keys = page.evaluate("() => [...document.querySelectorAll('#v2TTable tbody tr[data-player-key]')].slice(0, 6).map(tr => tr.dataset.playerKey)")
            checked = {c: 0 for c in charts}
            for key in keys:
                for chart in charts:
                    cell = page.query_selector(f'#v2TTable tr[data-player-key="{key}"] td.t-chart[data-chart="{chart}"]')
                    if not cell:
                        continue
                    if cell.get_attribute("aria-describedby") != "v2MathTip" or cell.get_attribute("tabindex") not in ("0", "-1"):  # JEG-899: roving tabindex leaves one tab stop per row; cells are reached with ArrowRight
                        errors.append(f"[math] the {chart} cell is not keyboard focusable with aria-describedby")
                    cell.focus()
                    page.wait_for_timeout(150)
                    tip = page.evaluate("""() => { const t = document.getElementById('v2MathTip'); return {hidden: t.hidden, rows: [...t.querySelectorAll('.row')].map(r =>
                      [r.children[0].textContent, r.children[1]?.textContent || '']), link: t.querySelector('a')?.getAttribute('href') || '', text: t.textContent}; }""")
                    shown = page.evaluate("(el) => el.firstChild.textContent", cell)
                    if tip["hidden"]:
                        errors.append(f"[math] focusing {chart} for {key} showed no tip")
                        continue
                    rows = {label: value for label, value in tip["rows"]}
                    published = next((v for l, v in tip["rows"] if l.endswith("(original)")), None)
                    if published is None:
                        reason = tip["text"]
                        if not re.search(r"Not on|Not enough|Estimated|no published number|waiver", reason, re.I):
                            errors.append(f"[math] {chart} for {key}: neither the math nor a reason: {reason!r}")
                        continue
                    pk = int(key)
                    combos = data["sources"][chart]["combos"]
                    chart_combo = combo if combo in combos else f"{combo}_qb1"   # FantasyCalc is published for one-QB leagues
                    want_native = combos[chart_combo]["native"].get(name_of.get(pk))
                    if want_native is None or abs(float(published) - float(want_native)) > 1e-9:
                        errors.append(f"[math] {chart} for {key}: as published {published}, data file {want_native}")
                    factor = float(rows.get("× rescale factor", "nan"))
                    indexed = float(rows.get("= rescaled value", "nan"))
                    if abs(float(published) * factor - indexed) > 0.06 + 0.0005 * float(published):
                        errors.append(f"[math] {chart} for {key}: {published} x {factor} = {float(published) * factor:.2f}, tip says {indexed}")
                    if abs(indexed - float(shown.replace("−", "-"))) > 0.051:
                        errors.append(f"[math] {chart} for {key}: tip indexed {indexed}, cell {shown!r}")
                    if "− our value" in rows and "= gap" in rows:
                        ours = float(rows["− our value"])
                        gap = float(rows["= gap"].replace("−", "-"))
                        if abs((indexed - ours) - gap) > 0.11:
                            errors.append(f"[math] {chart} for {key}: {indexed} - {ours} != gap {gap}")
                    if tip["link"] != expected[chart]:
                        errors.append(f"[math] {chart} tip link {tip['link']!r}")
                    checked[chart] += 1
            for chart, n in checked.items():
                if n < 3:
                    errors.append(f"[math] only {n} players checked for {chart} (want 3)")
            page.keyboard.press("Escape")
            page.close()

            # Two-column layout (1440): the expanded row lists each chart with a link.
            wide = open_page("#trade-targets", 1440, 1000)
            wide.wait_for_function("() => document.querySelector('#v2TTable .v2-texpand')", timeout=60000)
            wide.click("#v2TTable .v2-texpand >> nth=0")
            wide.wait_for_timeout(300)
            detail = wide.evaluate(LINKS, "#v2TTable tr.t-detail a[data-source-link]")
            errors += check_links(detail, expected, "[targets detail]", charts)
            if not detail:
                errors.append("[targets detail] the expanded row has no source links")
            wide.close()

            # Player values: the Showing legend, column heads (link beside the sort button), Customize.
            page = open_page("#player-values")
            legend = page.evaluate(LINKS, "#v2ShowingLegend a[data-source-link]")
            errors += check_links(legend, expected, "[legend]", charts)
            head_links = page.evaluate(LINKS, "#v2Table thead a[data-source-link]")
            errors += check_links(head_links, expected, "[table heads]", charts)
            if any(l["inButton"] for l in head_links):
                errors.append("[table heads] a link inside the sort button")
            if head_links:
                sort_before = page.evaluate("() => JSON.stringify(window.TradeValueV2.state.sort)")
                page.click("#v2Table thead a[data-source-link] >> nth=0")
                page.wait_for_timeout(200)
                if page.evaluate("() => JSON.stringify(window.TradeValueV2.state.sort)") != sort_before:
                    errors.append("[table heads] clicking the source link sorted the column")
            page.click("#v2EditSources")
            page.wait_for_timeout(500)
            rows = page.evaluate(LINKS, "#v2Popover a[data-source-link]")
            errors += check_links(rows, expected, "[customize]", CHARTS)
            if rows:
                before = page.evaluate("() => [...document.querySelectorAll('#v2Popover input[type=checkbox]')].map(i => i.checked).join()")
                page.click("#v2Popover a[data-source-link] >> nth=0")
                page.wait_for_timeout(150)
                after = page.evaluate("() => [...document.querySelectorAll('#v2Popover input[type=checkbox]')].map(i => i.checked).join()")
                if before != after:
                    errors.append("[customize] clicking a source link toggled the source")
            page.keyboard.press("Escape")
            page.close()

            # Compare series rows.
            page = open_page("#compare-trade")
            page.wait_for_function("() => window.TradeValueV2.compare()", timeout=30000)
            page.wait_for_timeout(500)
            rows = page.evaluate(LINKS, "#v2CTable a[data-source-link]")
            errors += check_links(rows, expected, "[compare rows]", [])
            if not rows:
                errors.append("[compare rows] no source links in the Compare table")
            page.close()

            # Phone: the tip stays inside the viewport.
            phone = open_page("#trade-targets", 390, 844)
            phone.wait_for_function("() => document.querySelector('#v2TCards li [data-math-for]')", timeout=30000)
            cell = phone.query_selector("#v2TCards li [data-math-for]")
            cell.click()
            phone.wait_for_timeout(200)
            box = phone.evaluate("() => { const t = document.getElementById('v2MathTip'); const r = t.getBoundingClientRect(); return {hidden: t.hidden, left: r.left, right: r.right, w: innerWidth}; }")
            if box["hidden"] or box["left"] < -0.5 or box["right"] > box["w"] + 0.5:
                errors.append(f"[390px] the tip is hidden or outside the screen: {box}")
            if phone.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
                errors.append("[390px] sideways scroll")
            phone.close()
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


PATCHES = {
    "table head link missing": ("        if (col.source && sourceUrl(col.source)) {", "        if (false) {"),
    "table head link inside the button": ("          th.appendChild(link);\n        }\n      }\n      hr.appendChild(th);", "          button.appendChild(link);\n        }\n      }\n      hr.appendChild(th);"),
    "wrong published number": ("lines.push([`${name}${week} (original)`, String(math.native)]);", "lines.push([`${name}${week} (original)`, String(math.native + 1)]);"),
    "targets head not linked": ("      line.append(key ? sourceLink(key, text) : document.createTextNode(text));", "      line.append(document.createTextNode(text));"),
}


class SourceLinksRenderTest(unittest.TestCase):
    def test_links_and_math(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                try:
                    errors = run_checks(patch)
                except Exception as exc:
                    if "unavailable" in type(exc).__name__.lower() or type(exc).__name__ == "SkipTest":
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
