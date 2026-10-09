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
    every complete source that sees it the other way; the verdict card's
    waterfall is DDF Value's, the same steps as its table row;
  * layout: at 1440×900 and 1366×768 both sides, the verdict card and its
    waterfall are on screen without scrolling, and the per-source table starts
    directly below; no horizontal scroll at 1100 or 390;
  * example: with no player added, a sample 2-for-2 is drawn, marked "Example",
    and the address keeps no trade.

Discrimination: test_guard_fails_on_broken_builds serves a per-row scale, the
verdict following the picker instead of DDF Value, a verdict naming no source, no example,
the landing drawn on incomplete rows, and the 3-column layout removed, and
requires the checks to fail on each.
"""
from __future__ import annotations

import contextlib
import functools
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

PICK = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows();
  const active = window.TradeValueV2.shown();
  const byEspn = rows.filter(r => Number.isFinite(r.values.espn)).sort((a, b) => b.values.espn - a.values.espn);
  const complete = r => active.every(k => Number.isFinite(r.values[k]));
  const priced = byEspn.filter(complete);
  const gap = byEspn.find(r => !complete(r) && active.some(k => Number.isFinite(r.values[k])));
  return {give: [priced[0], priced[5]].map(r => String(r.player_key)),
          receive: [priced[2], priced[3]].map(r => String(r.player_key)), gap: gap ? String(gap.player_key) : null};
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
    innerHeight, overflow: document.documentElement.scrollWidth - innerWidth};
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


def check_verdict(snap, pick) -> list[str]:
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
    if snap["verdictFall"] is None:
        errors.append("verdict card has no waterfall")
    else:
        row = next(r["wf"] for r in snap["rows"] if r["key"] == key)
        if snap["verdictFall"]["steps"] != row["steps"] or snap["verdictFall"]["land"] != row["land"]:
            errors.append(f"verdict card waterfall is not {key}'s own: {snap['verdictFall']['name']!r}")
    return errors


def check_layout(snap) -> list[str]:
    b, h = snap["boxes"], snap["innerHeight"]
    errors = []
    for name in ("give", "receive", "verdict", "verdictFall"):
        box = b.get(name)
        if not box or box["top"] < 0 or box["bottom"] > h + 0.5:
            errors.append(f"{name} not fully on screen at height {h}: {box}")
    if b.get("verdict") and b["verdict"]["top"] > b["give"]["bottom"]:
        errors.append("verdict is below the sides, not beside them")
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


def run_checks(overrides=None, viewports=((1440, 900), (1366, 768), (1100, 900), (390, 844))) -> list[str]:
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
                tag = f"[{width}x{height}] "
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare && window.TradeValueV2.compare()", timeout=40000)
                page.wait_for_timeout(200)
                # Example empty state.
                ex = page.evaluate(READ)
                if not ex["example"] or "Example" not in ex["example"] or "Example" not in ex["verdictEyebrow"]:
                    errors.append(tag + f"no example trade marked Example: {ex['example']!r} / {ex['verdictEyebrow']!r}")
                elif len(ex["give"]) != 2 or len(ex["receive"]) != 2 or not ex["rows"]:
                    errors.append(tag + f"example is not a drawn 2-for-2: {ex['give']} / {ex['receive']}")
                elif "give=" in ex["hash"]:
                    errors.append(tag + f"example leaked into the address: {ex['hash']}")
                else:
                    errors += [tag + "example: " + e for e in check_waterfalls(ex, {"give": ex["give"], "receive": ex["receive"]})]
                # A 2-for-2 from a link, with a verdict series that is not the ranking series. Show every
                # trade-value series so the verdict has sources that can disagree with it.
                page.evaluate("""() => window.TradeValueV2.setShown(window.TradeValueV2.shown().concat(
                  ['espn', 'cbsros', 'razzball', 'fantasycalc_adjusted', 'usatoday_adjusted', 'fantasypros_adjusted', 'cbs_adjusted']))""")
                page.wait_for_timeout(200)
                pick = page.evaluate(PICK)
                page.evaluate("p => { location.hash = `#compare-trade?give=${p.give.join(',')}&get=${p.receive.join(',')}`; }", pick)
                page.wait_for_function("() => !document.getElementById('v2CTable').hidden")
                options = page.evaluate("() => [...document.querySelectorAll('#v2CShown option')].map(o => o.value)")
                current = page.evaluate("() => document.getElementById('v2CShown').value")
                other = next((k for k in options if k != current and not k.endswith("_vorp")), None)
                if other:
                    page.select_option("#v2CShown", other)
                page.evaluate("() => window.scrollTo(0, 0)")
                page.wait_for_timeout(150)
                snap = page.evaluate(READ)
                errors += [tag + e for e in check_waterfalls(snap, pick)]
                errors += [tag + e for e in check_verdict(snap, pick)]
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
                    errors.append(tag + "no player lacks a selected series; the missing path went unchecked")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class WaterfallRenderTest(unittest.TestCase):
    def test_waterfall_verdict_layout_example(self):
        self.assertEqual(run_checks(), [])

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
            "verdict names no source": {"v2.js": (v2.replace(
                "text = `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you lose this trade.",
                "text = `Some sources think you lose this trade.", 1).replace(
                "? `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you win, but",
                "? `Some sources think you win, but", 1), js)},
            "no example": {"v2.js": (v2.replace(
                "verdictKey() ? exampleTrade(pointKeys) : null;", "verdictKey() ? null : null;", 1), js)},
            "landing on incomplete rows": {"trade.js": (trade.replace(
                "net: sums.net, complete: sums.net !== null,",
                "net: sums.net === null ? 0 : sums.net, complete: true,", 1), js)},
            "no 3-column layout": {"v2.css": (css.replace(
                "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(300px, 1.05fr);",
                "grid-template-columns: 1fr 1fr;", 1), styles)},
        }
        sources = {"v2.js": v2, "v2.css": css, "trade.js": trade}
        for name, overrides in broken.items():
            with self.subTest(mutation=name):
                for file, (body, _) in overrides.items():
                    self.assertNotEqual(body, sources[file], f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(overrides, viewports=((1366, 768),)), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
