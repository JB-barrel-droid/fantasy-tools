"""v2 source divergence "Under review" chip (was "Check") (JEG-609, data from JEG-460), rendered.

Serves the built page with assets/reference-freshness.json's source_divergence set to known statuses and checks:

  * warn and investigate show a "Check" chip next to the source name, with the published message as its tooltip
    and in its accessible name; ok and n/a show nothing;
  * reviewed shows "Reviewed" and links to the resolution issue (a JEG-NNN id becomes its Linear issue link);
    in a table column header, which is itself a button, it is not a link;
  * the chip sits on Trade targets column heads, the Showing legend, Player values column heads and the Customize
    rows, and never hides or disables the source: every flagged source's column, legend entry and row is still there;
  * our own DDF Value and VORP columns carry no chip;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js that flags ok sources, drops the tooltip, and links
inside the header button, and requires failures.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
V2_JS = ROOT / "app" / "v2" / "v2.js"

from tests import _render_env  # noqa: E402
from tests._holds import pin_holds_in_dist  # noqa: E402
from tests.test_v2_targets_render import build_v2_page  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

MESSAGES = {
    "razzball": "Razzball projections: in line with its usual range (47% vs 46%).",
    "usatoday": "USA Today disagrees with the other charts on 38% of players this week (usually 20%).",
    "fantasycalc": "FantasyCalc disagrees with the other charts on 47% of players this week (usually 46%). Under review.",
    "fantasypros": "FantasyPros was reviewed on 2026-10-14: its ordering is unusual but correct.",
}
DIVERGENCE = {
    "usatoday": {"status": "warn", "message": MESSAGES["usatoday"], "resolution_issue": None},
    "fantasycalc": {"status": "investigate", "message": MESSAGES["fantasycalc"], "resolution_issue": None},
    "fantasypros": {"status": "reviewed", "message": MESSAGES["fantasypros"], "resolution_issue": "JEG-123"},
    "cbs": {"status": "ok", "message": "CBS disagrees with the other charts on 14% of players this week.", "resolution_issue": None},
    # JEG-870: CBS is held in the pinned fixture (its chip is the hold marker), so an open ok source proves ok shows nothing.
    "cbsros": {"status": "ok", "message": "CBS rest of season disagrees with the other projections on 12% of players this week.", "resolution_issue": None},
    "espn": {"status": "n/a", "message": "", "resolution_issue": None},
    # JEG-834: warned only by the fixed ceiling while within 5 points of its own usual rate: the chip stays (GL-25)
    # but says "In range" with a plain message, not the flagged "disagrees ... Under review" wording.
    "razzball": {"status": "warn", "message": "Razzball disagrees with the other projections on 47% of players this week (usually 46%). Under review.",
                 "resolution_issue": None, "outlier_rate": 0.474, "usual_outlier_rate": 0.46},
}
# JEG-850 (Jeremy, 2026-10-22): "Check" reads "Under review", "In range" reads "Normal range".
EXPECT = {"usatoday": "Under review", "fantasycalc": "Under review", "fantasypros": "Reviewed", "razzball": "Normal range"}

CHIPS = """() => [...document.querySelectorAll('.v2-div-chip')].filter(c => c.offsetParent !== null).map(c => ({
  src: c.dataset.divergence, status: c.dataset.status, text: c.textContent.trim(), mark: Boolean(c.querySelector('svg.v2-ok-mark')), border: getComputedStyle(c).borderTopWidth, title: c.title, aria: c.getAttribute('aria-label') || '',
  tag: c.tagName, href: c.getAttribute('href') || '', inButton: Boolean(c.closest('button')), in: c.closest('#v2TDivergence') ? 'note' : c.closest('thead') ? 'head' : c.closest('#v2ShowingLegend') ? 'legend'
  : c.closest('#v2Popover, #v2Sources, .v2-popover') ? 'customize' : 'other'}))"""


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        # JEG-870: the fixture's holds are pinned (tests/_holds.py), so the flagged sources are open and CBS is held.
        # Before this the test passed on a held Razzball only because a held source still showed the check (the bug).
        pin_holds_in_dist(dist)
        build_v2_page.build(dist)   # JEG-834: test the source in app/v2, not a stale committed build
        path = dist / "assets" / "reference-freshness.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["source_divergence"] = DIVERGENCE
        path.write_text(json.dumps(doc), encoding="utf-8")

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


def check_chips(chips: list[dict], where: str, place: str, allow_link: bool, expect: dict | None = None) -> list[str]:
    errors = []
    mine = [c for c in chips if c["in"] == place]
    seen = {c["src"]: c for c in mine}
    expect = EXPECT if expect is None else expect
    if set(seen) != set(expect):
        errors.append(f"[{where}] chips on {sorted(seen)}, want exactly {sorted(expect)} (ok and n/a show none)")
    for src, word in expect.items():
        c = seen.get(src)
        if not c:
            continue
        # JEG-856: in range is a green checkmark glyph with no word and no box; its name is the aria-label.
        if word == "Normal range":
            if not c["mark"] or c["text"] or c["border"] != "0px":
                errors.append(f"[{where}] {src}: in range must be the checkmark glyph only (mark {c['mark']}, text {c['text']!r}, border {c['border']})")
            if not c["aria"].startswith("Normal range: ") or c["status"] == "reviewed":
                errors.append(f"[{where}] {src}: checkmark name {c['aria']!r} should start with 'Normal range: '")
        else:
            if c["mark"]:
                errors.append(f"[{where}] {src}: only an in-range source gets the checkmark")
            if c["text"].lstrip("⚑✓ ").strip() != word or not c["aria"].startswith(word + ": "):
                errors.append(f"[{where}] {src}: chip says {c['text']!r} / {c['aria']!r}, want {word!r}")
            if word == "Under review" and (not c["text"].startswith("⚑") or c["border"] != "0px"):
                errors.append(f"[{where}] {src}: out of range must be the plain amber flag, no box: {c['text']!r} border {c['border']}")
        if c["title"] != MESSAGES[src] or MESSAGES[src] not in c["aria"]:
            errors.append(f"[{where}] {src}: tooltip {c['title']!r} / name {c['aria']!r}, want the published message")
        linked = c["tag"] == "A"
        # Jeremy, 2026-10-25: the live dashboard has no links to Linear, and the fixture's resolution issue is a
        # Linear ticket, so no chip links anywhere (it used to link the reviewed chip to the ticket).
        if linked:
            errors.append(f"[{where}] {src}: a chip must not link (Linear ticket ids are not linked): {c['href']!r}")
        if c["inButton"] and linked:
            errors.append(f"[{where}] {src}: interactive chip inside a button")
    return errors


def run_checks(patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if patch:
        old, new = patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            # Trade targets column heads.
            page.goto(base + "#trade-targets", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets() && document.querySelector('#v2TTable thead th[data-chart]')", timeout=60000)
            page.wait_for_function("() => document.querySelector('.v2-div-chip')", timeout=20000)
            # A source the pipeline holds (fidelity or coverage hold) has no column, so it can carry no chip:
            # the flagged set is the fixture's flagged sources that the build actually shows (JEG-675).
            shown_heads = page.evaluate("() => [...document.querySelectorAll('#v2TTable thead th[data-chart]')].map(th => th.dataset.chart)")
            expect = {k: v for k, v in EXPECT.items() if k in shown_heads}
            if len(expect) < 2 or not {"usatoday", "fantasypros"} <= set(expect):
                errors.append(f"[trade targets] want at least USA Today and FantasyPros shown to carry chips: {shown_heads}")
            chips = page.evaluate(CHIPS)
            errors += check_chips(chips, "trade targets note", "note", True, expect)
            # JEG-1042 (Jeremy, 2026-10-24): the note shows chips side by side; each chip's explanation is its hover
            # text (title) and accessible name, not inline text.
            note_titles = page.evaluate("() => [...document.querySelectorAll('#v2TDivergence .v2-div-chip')].map(c => (c.title || '') + ' ' + (c.getAttribute('aria-label') || '')).join(' ')")
            for message in (MESSAGES[k] for k in expect):
                if message not in note_titles:
                    errors.append(f"[trade targets] no note chip explains: {message!r}")
            # Per-chart columns are folded from 1024 px (v2.css, #639), so the head chips are on screen below it.
            page.set_viewport_size({"width": 900, "height": 1000})
            page.wait_for_timeout(400)
            errors += check_chips(page.evaluate(CHIPS), "trade targets heads at 900", "head", True, expect)
            page.set_viewport_size({"width": 1440, "height": 1000})
            heads = page.evaluate("() => [...document.querySelectorAll('#v2TTable thead th[data-chart]')].map(th => th.dataset.chart)")
            for src in expect:
                if src not in heads:
                    errors.append(f"[trade targets] flagged source {src} lost its column: {heads}")
            # Player values: the Showing legend and the column heads.
            page.evaluate("() => { location.hash = '#player-values'; }")
            page.wait_for_function("() => document.querySelector('#v2Table thead th') && document.querySelector('#v2ShowingLegend li')", timeout=40000)
            page.wait_for_timeout(500)
            chips = page.evaluate(CHIPS)
            errors += check_chips(chips, "player values legend", "legend", True, expect)
            errors += check_chips(chips, "player values heads", "head", False, expect)
            heads = page.evaluate("() => [...document.querySelectorAll('#v2Table thead th')].map(th => th.textContent)")
            for name in (n for k, n in (("usatoday", "USA Today"), ("fantasycalc", "FantasyCalc"), ("fantasypros", "FantasyPros")) if k in expect):
                if not any(name in h for h in heads):
                    errors.append(f"[player values] flagged source {name} lost its column")
            vorp = page.evaluate("() => [...document.querySelectorAll('.v2-div-chip')].filter(c => c.closest('th') && /VORP/.test(c.closest('th').textContent)).length")
            if vorp:
                errors.append("[player values] a VORP column carries a divergence chip")
            ddf = page.evaluate("() => [...document.querySelectorAll('#v2ShowingLegend li')].filter(li => /DDF Value/.test(li.textContent) && li.querySelector('.v2-div-chip')).length")
            if ddf:
                errors.append("[player values] DDF Value carries a divergence chip")
            # Customize rows.
            page.click("#v2EditSources")
            page.wait_for_timeout(600)
            chips = page.evaluate("""() => [...document.querySelectorAll('.v2-div-chip')].filter(c => c.offsetParent !== null && c.closest('label'))
              .map(c => ({src: c.dataset.divergence, status: c.dataset.status, text: c.textContent.trim(), mark: Boolean(c.querySelector('svg.v2-ok-mark')), border: getComputedStyle(c).borderTopWidth, title: c.title, aria: c.getAttribute('aria-label') || '',
                tag: c.tagName, href: c.getAttribute('href') || '', inButton: Boolean(c.closest('button')), in: 'customize'}))""")
            # JEG-870: the Customize list still names a held source (greyed, CBS in the pinned fixture); its chip is
            # the hold marker, never the in-range check. The flagged open sources keep their chips.
            held = [c for c in chips if c["status"] == "held"]
            if {c["src"] for c in held} != {"cbs"} or any(c["mark"] or not c["aria"].startswith("Paused: ") for c in held):
                errors.append(f"[customize] held CBS should carry the Paused marker and nothing else: {held}")
            chips = [c for c in chips if c["status"] != "held"]
            seen = {c["src"] for c in chips}
            if seen != set(EXPECT):
                errors.append(f"[customize] chips on {sorted(seen)}, want {sorted(EXPECT)}")
            # JEG-834: a source within its usual range keeps its chip but says so plainly.
            razz = next((c for c in chips if c["src"] == "razzball"), None)
            if razz and (not razz["mark"] or razz["text"] or not razz["aria"].startswith("Normal range: ") or razz["title"] != MESSAGES["razzball"]):
                errors.append(f"[customize] Razzball within its usual range reads {razz['text']!r} / {razz['aria']!r} / {razz['title']!r}")
            other = [c["src"] for c in chips if c["src"] != "razzball" and c["mark"]]
            if other:
                errors.append(f"[customize] checkmark on out-of-range sources {other}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "ok sources flagged": ('if (status !== "warn" && status !== "investigate" && status !== "reviewed" && status !== "excluded") return null;',
                           'if (status === "n/a") return null;'),
    "tooltip dropped": ("    chip.title = message;\n", "    chip.title = '';\n"),
    "link inside the header button": ('const href = (status === "reviewed" || status === "excluded") && !(opts && opts.noLink) ? resolutionHref(entry.resolution_issue) : "";',
                                      'const href = (status === "reviewed" || status === "excluded") ? resolutionHref(entry.resolution_issue) : "";'),
    "within-usual-range source flagged": ("usualGap <= 5;", "usualGap <= -999;"),
    "reviewed shown as check": ('const word = status === "excluded" ? "Excluded" : (status === "reviewed" ? "Reviewed" : (inRange ? "Normal range" : "Under review"));', 'const word = "Under review";'),
    "in range checkmark dropped": ('chip.insertAdjacentHTML("beforeend", \'<svg class="v2-ok-mark"', 'chip.insertAdjacentHTML("beforeend", \'<svg class="v2-x"'),
    "in range back to a worded box": ('chipClass = status === "excluded" ? "excluded" : (status === "reviewed" ? "reviewed" : (inRange ? "ok" : "check"))', 'chipClass = status === "excluded" ? "excluded" : (status === "reviewed" ? "reviewed" : "other")'),
    "out of range gets the checkmark": ('    if (inRange) {\n      chip.insertAdjacentHTML', '    if (inRange || status === "warn") {\n      chip.insertAdjacentHTML'),
}


class DivergenceChipRenderTest(unittest.TestCase):
    def test_chip(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
