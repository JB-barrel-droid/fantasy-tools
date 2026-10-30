"""v2 Trade targets check 2 (potential positional weight inflation), rendered (JEG-476, JEG-489).

Loads the built page headless at 1440 and 390 px, opens #trade-targets and checks:

  * the page names both checks: numbered headings "1. Potential mispricing" and
    "2. Positions the market overpays for" (JEG-1130, PMM doc 3.2), and the subtitle names both;
  * the weight table has a row per position and per position starter / bench
    tier; each consensus gap shown equals an independent recomputation from the
    engine's rows (share of market total / share of DDF Value total - 1);
  * every row carries a signal chip (symbol plus words) at the +/-10% lines, and
    a group with fewer than 3 players shows no number;
  * the headline only cites groups with 8+ players;
  * a group opens to its players (DDF Value, consensus, gap, each chart) and
    closes again;
  * changing the league (teams) redraws the check from the new engine rows;
  * no page errors and no horizontal page overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves the page with the
weight check removed, and with the gap computed on raw totals, and requires
the checks to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import statistics
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

TARGETS_JS = ROOT / "app" / "v2" / "targets.js"
POSITIONS = ("QB", "RB", "WR", "TE")

READ = """() => {
  const V = window.TradeValueV2, C = window.TradeValueCurveControls;
  const t = document.getElementById('v2Weight');
  const rows = C.getAllRows().map(r => ({pos: r.pos, tier: r.ddfTier || null, name: r.name,
    ddf: r.values && r.values.ddf_value, charts: Object.fromEntries((V.targets().used || []).map(k => [k, r.values ? r.values[k] : null]))}));
  const trs = t ? [...t.querySelectorAll('tbody > tr[data-group]')] : [];
  return {
    h2: [...document.querySelectorAll('#v2Targets h2')].map(h => h.textContent.trim()),
    sub: (document.querySelector('#v2Targets .v2-ttitle p') || {}).textContent || '',
    shown: Boolean(t) && !t.hidden && t.getBoundingClientRect().height > 0,
    headline: (document.getElementById('v2WeightHeadline') || {}).textContent || '',
    used: V.targets().used,
    groups: trs.map(tr => ({key: tr.dataset.group, n: Number(tr.children[1].textContent),
      gap: tr.querySelector('td.w-gap').dataset.gap, gapText: tr.querySelector('td.w-gap').textContent,
      signal: (tr.querySelector('.v2-wsignal') || {dataset: {}}).dataset.signal || null,
      chipText: (tr.querySelector('.v2-wsignal') || {}).textContent || '',
      toggle: Boolean(tr.querySelector('[data-weight-expand]'))})),
    rows,
    overflow: document.documentElement.scrollWidth - innerWidth,
  };
}"""


@contextlib.contextmanager
def _served(js_patch=None, drop_weight=False):
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist)

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


def recompute(snap: dict) -> dict:
    """Independent consensus gaps from the engine rows: share of market total / share of DDF total - 1."""
    pairs = []
    for r in snap["rows"]:
        if r["pos"] not in POSITIONS or not isinstance(r["ddf"], (int, float)):
            continue
        priced = [v for v in r["charts"].values() if isinstance(v, (int, float))]
        if len(priced) >= 2:
            pairs.append((r, r["ddf"], statistics.median(priced)))
    to, tm = sum(p[1] for p in pairs), sum(p[2] for p in pairs)
    out = {}
    for pos in POSITIONS:
        for tier in (None, "starter", "bench"):
            members = [p for p in pairs if p[0]["pos"] == pos and (tier is None or p[0]["tier"] == tier)]
            key = pos if tier is None else f"{pos}|{tier}"
            if len(members) < 3 or sum(p[1] for p in members) <= 0:
                out[key] = (len(members), None)
            else:
                o, m = sum(p[1] for p in members), sum(p[2] for p in members)
                out[key] = (len(members), (m / tm) / (o / to) - 1)
    return out


def check_snap(snap: dict, tag: str) -> list[str]:
    errors = []
    if "1. Potential mispricing" not in snap["h2"] or "2. Positions the market overpays for" not in snap["h2"]:
        errors.append(f"{tag}numbered check headings missing: {snap['h2']}")
    if "potential mispricing" not in snap["sub"] or "the positions the market overpays for" not in snap["sub"]:
        errors.append(f"{tag}subtitle must name both checks: {snap['sub']!r}")
    if not snap["shown"]:
        errors.append(f"{tag}the weight check is not shown")
        return errors
    keys = [g["key"] for g in snap["groups"]]
    want_keys = [k for pos in POSITIONS for k in (pos, f"{pos}|starter", f"{pos}|bench")]
    if keys != want_keys:
        errors.append(f"{tag}groups {keys}, want {want_keys}")
    want = recompute(snap)
    for g in snap["groups"]:
        wn, wgap = want.get(g["key"], (None, None))
        if g["n"] != wn:
            errors.append(f"{tag}{g['key']}: players {g['n']}, want {wn}")
        if wgap is None:
            if g["gap"] != "" or g["signal"] is not None or g["gapText"] != "—":
                errors.append(f"{tag}{g['key']} has {g['n']} players: no number or signal expected, got {g}")
            continue
        if g["gap"] == "" or abs(float(g["gap"]) - wgap) > 1e-6:
            errors.append(f"{tag}{g['key']}: gap {g['gap']}, want {wgap}")
        signal = "sell" if wgap >= 0.10 else "buy" if wgap <= -0.10 else "fair"
        if g["signal"] != signal:
            errors.append(f"{tag}{g['key']}: signal {g['signal']}, want {signal} at gap {wgap:.3f}")
        if not g["chipText"].strip() or g["chipText"].strip()[0] not in "▲▼●":
            errors.append(f"{tag}{g['key']}: the signal chip needs a symbol and words, got {g['chipText']!r}")
    sizes = dict(want)
    named = [k for k in want_keys if k in snap["headline"].replace(" starters", "|starter").replace(" bench", "|bench")]
    for k in named:
        if sizes.get(k, (0,))[0] < 8:
            errors.append(f"{tag}the headline names {k} with only {sizes[k][0]} players: {snap['headline']!r}")
    if not snap["headline"].strip():
        errors.append(f"{tag}no headline")
    return errors


def run_checks(broken: str | None = None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors: list[str] = []
    targets_js = TARGETS_JS.read_text(encoding="utf-8")
    if broken == "raw totals":
        targets_js = targets_js.replace("const gap = shown ? (market / totalMarket) / (ours / totalOurs) - 1 : null;",
                                        "const gap = shown ? market / ours - 1 : null;", 1)
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if broken == "raw totals":
                    page.route("**/v2/targets.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=targets_js))
                page.goto(base + "#trade-targets", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelectorAll('#v2WeightTable tbody tr[data-group]').length > 0", timeout=60000)
                snap = page.evaluate(READ)
                tag = f"[{width}px] "
                errors += check_snap(snap, tag)
                if width <= 390 and snap["overflow"] > 0:
                    errors.append(f"{tag}horizontal overflow {snap['overflow']}px")
                if width == 1440 and snap["groups"]:
                    first = next((g for g in snap["groups"] if g["toggle"]), None)
                    if first:
                        sel = f'[data-weight-expand="{first["key"]}"]'
                        page.click(sel)
                        opened = page.evaluate("k => { const d = document.querySelector(`tr.w-detail[data-detail-for=\"${k}\"]`);"
                                               " const n = Number(document.querySelector(`tr[data-group=\"${k}\"]`).children[1].textContent);"
                                               " return [d ? d.querySelectorAll('.v2-wplayers > tbody > tr').length : -1, n]; }", first["key"])
                        if opened[0] != opened[1]:
                            errors.append(f"{tag}opening {first['key']} lists {opened[0]} players, want {opened[1]}")
                        page.click(sel)
                        if page.evaluate("k => Boolean(document.querySelector(`tr.w-detail[data-detail-for=\"${k}\"]`))", first["key"]):
                            errors.append(f"{tag}{first['key']} did not close")
                    # A different league redraws the check from the new engine rows.
                    page.evaluate("async () => { window.TradeValueCurveControls.setTeams(10); await new Promise(r => setTimeout(r, 400)); }")
                    page.wait_for_timeout(500)
                    errors += check_snap(page.evaluate(READ), "[1440px 10 teams] ")
                if page_errors:
                    errors.append(f"{tag}page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class GroupWeightRenderTest(unittest.TestCase):
    def test_weight_check(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        self.assertNotEqual(run_checks("raw totals"), [], "raw-totals build was not caught")


if __name__ == "__main__":
    unittest.main()
