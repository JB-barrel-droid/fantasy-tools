"""v2 Compare a trade: the deal read, rendered (JEG-487, contract CT-08).

Loads the built page headless, opens trades by link (#compare-trade?give=..&get=..) and checks that:

  * the outlined cell of the 3x3 grid, the three nets and their sides equal an independent recomputation from the
    engine rows (DDF Value, Trade chart average: win at or above max(1, 3% of the average side
    total), lose at or below the negative of that);
  * the grid has nine cells, exactly one outlined (aria-current), and none for an incomplete trade;
  * each net has an info button that opens its one-line definition;
  * "The sources split." is gone, at 1440, 390 and 320 px; no horizontal overflow at 390 and 320, and the
    deal-read headline and sub-line do not overflow their own boxes (JEG-950);
  * the win|lose read (JEG-950, Jeremy 2026-10-26) reads exactly "DDF Value likes it. The market doesn't."
    with no call to action, and its sub-line is "The trade charts have you N points behind, so the other
    manager will likely see it as their win."
    with N the real market net to one decimal, recomputed here;
  * the example trade (no players added) also carries a deal read.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with the outline on the wrong cell, the old split
copy back, and the nets read from the wrong series, and requires failures.
"""
from __future__ import annotations

import contextlib
import functools
import re
import http.server
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
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

KEYS = {"value": "ddf_value", "projections": "ddf_value_projections"}
# JEG-832: the "market" net is now the mean of the per-chart rescaled nets, not ddf_value_charts.
CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]

# JEG-950 (Jeremy, 2026-10-26): the win|lose verdict. The title is fixed; the rendered headline is the title
# alone (no call to action), and the sub-line is the real market gap, one decimal, direction word from the sign.
TITLE = "DDF Value likes it. The market doesn't."


def gap_text(net):
    """The win|lose sub-line, recomputed independently of trade.js."""
    if net == 0:
        return "The trade charts call it even."
    if net > 0:
        return f"The trade charts have you {abs(net):.1f} points ahead."
    return f"The trade charts have you {abs(net):.1f} points behind, so the other manager will likely see it as their win."

# The built data may have no published trade charts for the week, so the test feeds the page deterministic
# chart and projection series on top of the engine's DDF Value. JEG-832: four chart series are injected
# so dealRead can compute the chart average from per-chart rows (the same rows Compare shows).
FEED = """() => { const C = window.TradeValueCurveControls; const orig = C.getAllRows.bind(C);
  const f = (k, salt) => 0.5 + (((Number(k) * 37 + salt) % 100) / 100);
  C.getAllRows = () => orig().map(r => Number.isFinite(r.values.ddf_value) ? {...r, values: {...r.values,
    ddf_value_charts: r.values.ddf_value * f(r.player_key, 11), ddf_value_projections: r.values.ddf_value * f(r.player_key, 53),
    usatoday: r.values.ddf_value * f(r.player_key, 7), fantasycalc: r.values.ddf_value * f(r.player_key, 19),
    fantasypros: r.values.ddf_value * f(r.player_key, 31), cbs: r.values.ddf_value * f(r.player_key, 43)}} : r); }"""

PICK = """() => {
  const C = window.TradeValueCurveControls;
  const TT = window.TradeValueTargets;
  const chartKeys = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'];
  const info = C.getSourceInfo();
  const available = new Set(info.filter(s => s.available && chartKeys.includes(s.key)).map(s => s.key));
  const allKeys = ['ddf_value', 'ddf_value_projections'].concat([...available]);
  const rows = C.getAllRows().filter(r => allKeys.every(k => Number.isFinite(r.values[k])))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const pick = list => list.map(r => {
    const o = {key: String(r.player_key), v: r.values.ddf_value, p: r.values.ddf_value_projections, charts: {}};
    available.forEach(k => { o.charts[k] = r.values[k]; });
    return o;
  });
  return {pool: pick(rows.slice(0, 40)), chartKeys: [...available]}; }"""

READ = """() => {
  const deal = document.getElementById('v2CDeal');
  const cells = [...document.querySelectorAll('#v2CDealGrid td')].map(td => ({cell: td.dataset.cell, current: td.getAttribute('aria-current') === 'true', text: td.textContent}));
  const nets = Object.fromEntries([...document.querySelectorAll('#v2CDealNets li')].map(li => [li.dataset.net, {text: li.querySelector('.v2-deal-net').textContent,
    side: li.querySelector('.v2-deal-net').dataset.side, info: Boolean(li.querySelector('button.v2-info')), def: li.querySelector('.v2-deal-def').textContent}]));
  const readEl = document.getElementById('v2CDealRead'), textEl = document.getElementById('v2CDealText');
  return {shown: Boolean(deal) && !deal.hidden, read: readEl.textContent, text: textEl.textContent,
    readOverflow: [readEl.scrollWidth - readEl.clientWidth, textEl.scrollWidth - textEl.clientWidth],
    production: document.getElementById('v2CDealProduction').textContent, cells, nets, body: document.getElementById('v2Compare').innerText,
    overflow: document.documentElement.scrollWidth - innerWidth, example: document.getElementById('v2Compare').classList.contains('is-example')};
}"""


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist)

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


def side(net, give, receive):
    threshold = max(1.0, 0.03 * (give + receive) / 2)
    return "win" if net >= threshold else "lose" if net <= -threshold else "even"


def expected(give, receive, chart_keys):
    out = {}
    for name, letter in (("value", "v"), ("projections", "p")):
        g = sum(p[letter] for p in give)
        r = sum(p[letter] for p in receive)
        out[name] = (r - g, side(r - g, g, r))
    # JEG-832: market is the mean of the per-chart rescaled nets.
    chart_nets = []
    for k in chart_keys:
        g = sum(p["charts"][k] for p in give)
        r = sum(p["charts"][k] for p in receive)
        chart_nets.append((r - g, g, r))
    if len(chart_nets) < 3:
        out["market"] = (None, None)
    else:
        avg_net = sum(n for n, _, _ in chart_nets) / len(chart_nets)
        avg_give = sum(g for _, g, _ in chart_nets) / len(chart_nets)
        avg_rec = sum(r for _, _, r in chart_nets) / len(chart_nets)
        out["market"] = (avg_net, side(avg_net, avg_give, avg_rec))
    return out


# JEG-886 / JEG-950: the read names a split (not the cell copy) when the per-chart count the accept headline
# uses does not match the average column's assumption.
DEAL_SPLIT_ACCEPT = {"win": "Unlikely", "even": "Likely", "lose": "Likely"}


def chart_nets(give, receive, chart_keys):
    return [sum(p["charts"][k] for p in receive) - sum(p["charts"][k] for p in give) for k in chart_keys]


def split_read(market_side, nets):
    of = len(nets)
    yes = sum(1 for n in nets if n <= 0)
    accept = "Likely" if yes / of >= 2 / 3 else "Unlikely" if yes / of <= 1 / 3 else "Toss-up"
    return accept != DEAL_SPLIT_ACCEPT[market_side]


def pick_trades(pool, chart_keys):
    """Trades chosen from the engine rows so the nets differ: every (V side, M side) pair that occurs among
    1-for-1 and 2-for-1 swaps of the top players, up to six of them. JEG-950: a win|lose trade whose read is
    the verdict copy (not the JEG-886 split) comes first, so the card with the longest copy (the market-gap
    sub-line) is always rendered, and its wording and overflow are actually checked."""
    seen, trades = {}, []
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            for give, receive in (([a], [b]), ([b], [a]), ([a, pool[0]] if a is not pool[0] else [a], [b])):
                if {p["key"] for p in give} & {p["key"] for p in receive}:
                    continue
                e = expected(give, receive, chart_keys)
                cell = (e["value"][1], e["market"][1])
                if cell not in seen:
                    seen[cell] = (give, receive, cell)
                    trades.append(cell)
                elif cell == ("win", "lose"):
                    # Prefer the win|lose trade whose read is the verdict copy: the first one met could be the
                    # JEG-886 split read, and the two share the cell so only one is kept.
                    old, new = seen[cell], (give, receive, cell)
                    if split_read("lose", chart_nets(old[0], old[1], chart_keys)) and not split_read("lose", chart_nets(give, receive, chart_keys)):
                        seen[cell] = new

    def rank(cell):
        return 0 if cell == ("win", "lose") and not split_read("lose", chart_nets(seen[cell][0], seen[cell][1], chart_keys)) else 1
    trades.sort(key=rank)
    return [seen[c] for c in trades[:6]]


def check_snapshot(snap, give, receive, chart_keys, tag) -> list[str]:
    errors = []
    want = expected(give, receive, chart_keys)
    if not snap["shown"]:
        return [f"{tag}the deal read is not shown"]
    if len(snap["cells"]) != 9:
        errors.append(f"{tag}grid has {len(snap['cells'])} cells, want 9")
    current = [c["cell"] for c in snap["cells"] if c["current"]]
    if want["market"][1] is None:
        cell = None  # incomplete: no outlined cell
    else:
        cell = f"{want['value'][1]}|{want['market'][1]}"
    if cell and current != [cell]:
        errors.append(f"{tag}outlined {current}, want [{cell!r}] (V {want['value']}, M {want['market']})")
    for name in ("value", "market", "projections"):
        net, s = want[name]
        got = snap["nets"].get(name)
        if net is None:
            # JEG-832: market with too few charts shows "Not enough charts" or "—".
            if got and got["side"] not in ("", None):
                errors.append(f"{tag}{name} should have no side when there are too few charts, got {got['side']!r}")
        elif not got or got["side"] != s:
            errors.append(f"{tag}{name} side {got and got['side']}, want {s}")
        elif abs(float(got["text"].split(" ")[0].replace("−", "-").replace("+", "")) - net) > 0.06:
            errors.append(f"{tag}{name} net {got['text']!r}, want {net:+.1f}")
        if got and (not got["info"] or not got["def"]):
            errors.append(f"{tag}{name} needs an info button and a definition")
    if "The sources split" in snap["body"]:
        errors.append(f"{tag}the old 'The sources split.' copy is back")
    if cell:
        if not snap["read"].strip() or TITLE in snap["read"] and cell != "win|lose":
            errors.append(f"{tag}read {snap['read']!r} for cell {cell}")
        # JEG-886: when the per-chart count disagrees with the average's cell, the read names the split instead of the
        # cell copy ("..., and the trade charts split"); the cell itself stays. DDF Value is the chart average again
        # (JEG-1073), so V and M move together and a trade can land in a split read; that is the rule, not a miss.
        split = "the trade charts split" in snap["read"]
        if cell == "win|lose" and snap["read"].strip() != TITLE and not split:
            errors.append(f"{tag}win|lose must read exactly {TITLE!r} (no call to action), got {snap['read']!r}")
        # JEG-950: the live win|lose read shows the real market gap, not the static grid explanation.
        if cell == "win|lose" and not split and want["market"][0] is not None:
            net = want["market"][0]
            got = snap["text"].strip()
            m = re.fullmatch(r"The trade charts have you (\d+\.\d) points (ahead|behind)(.*)", got)
            want_tail = gap_text(net).split(" points ", 1)[1] if net != 0 else ""
            if net == 0 or not m or m.group(2) + m.group(3) != want_tail:
                errors.append(f"{tag}win|lose sub-line {got!r}, want {gap_text(net)!r}")
            elif abs(float(m.group(1)) - abs(net)) > 0.06:
                errors.append(f"{tag}win|lose sub-line number {m.group(1)!r}, want {abs(net):.1f}")
        if cell == "lose|win" and not snap["read"].startswith("Trap") and not split:
            errors.append(f"{tag}lose|win must read 'Trap', got {snap['read']!r}")
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
            for width, height in ((1440, 1000), (390, 844), (320, 640)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if patch:
                    page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
                page.evaluate(FEED)
                page.evaluate("() => { location.hash = '#player-values'; }")
                page.wait_for_timeout(300)
                page.evaluate("() => { location.hash = '#compare-trade'; }")
                page.wait_for_timeout(600)
                # The example trade (nothing added) has a read too.
                snap = page.evaluate(READ)
                if not snap["shown"] or not snap["example"]:
                    errors.append(f"[{width}px] the example trade has no deal read (shown {snap['shown']}, example {snap['example']})")
                if "The sources split" in snap["body"]:
                    errors.append(f"[{width}px example] the old 'The sources split.' copy is back")
                pick_result = page.evaluate(PICK)
                pool = pick_result["pool"]
                chart_keys = pick_result["chartKeys"]
                trades = pick_trades(pool, chart_keys)
                if len(trades) < 4:
                    errors.append(f"[{width}px] could only build {len(trades)} distinct trades from the engine rows")
                # JEG-950: the win|lose verdict card carries the longest copy (the market-gap sub-line), so a
                # fixture refresh that no longer produces one must fail with a named message, not pass silently.
                # It must be the verdict read, not the JEG-886 split, or the new wording is never exercised.
                if width == 1440:
                    win_lose = [t for t in trades if t[2] == ("win", "lose")]
                    if not win_lose:
                        errors.append(f"[{width}px] no win|lose trade among {len(trades)} picked: the verdict card went unchecked")
                    elif split_read("lose", chart_nets(win_lose[0][0], win_lose[0][1], chart_keys)):
                        errors.append(f"[{width}px] the picked win|lose trade takes the split path: the JEG-950 verdict copy went unchecked")
                for n, (give, receive, _cell) in enumerate(trades):
                    link = f"#compare-trade?give={','.join(p['key'] for p in give)}&get={','.join(p['key'] for p in receive)}"
                    page.evaluate("h => { location.hash = h; }", link)
                    page.wait_for_timeout(600)
                    snap = page.evaluate(READ)
                    errors += check_snapshot(snap, give, receive, chart_keys, f"[{width}px trade {n}] ")
                    if width <= 390:
                        if snap["overflow"] > 0:
                            errors.append(f"[{width}px trade {n}] horizontal overflow {snap['overflow']}px")
                        for label, over in zip(("headline", "sub-line"), snap["readOverflow"]):
                            if over > 0:
                                errors.append(f"[{width}px trade {n}] the deal-read {label} overflows by {over}px")
                if width == 1440:
                    # An info button opens its definition.
                    if not page.query_selector('#v2CDealNets li[data-net="market"] button.v2-info'):
                        errors.append("[1440px] no Trade chart average net with an info button")
                    else:
                        page.click('#v2CDealNets li[data-net="market"] button.v2-info')
                    if page.query_selector('#v2CDealNets li[data-net="market"]') and page.evaluate("() => document.querySelector('#v2CDealNets li[data-net=\"market\"] .v2-deal-def').hidden"):
                        errors.append("[1440px] the info button did not open its definition")
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "outline on the wrong cell": ("if (deal.kind === \"read\" && deal.cell === `${v}|${m}`) {", "if (deal.kind === \"read\" && deal.cell === `${m}|${v}`) {"),
    "split copy back": ('box.hidden = !s.kind || s.kind === "single" || s.kind === "split";', 'box.hidden = !s.kind || s.kind === "single";'),
    "market net from the wrong series": ('["market", "Trade chart average", "Does the market think you are winning?"],',
                                         '["projections", "Trade chart average", "Does the market think you are winning?"],'),
}


class DealReadRenderTest(unittest.TestCase):
    def test_deal_read(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
