"""v2 Compare a trade, rendered: every number on the tab is the engine's.

Builds dist/v2 into a temp copy of the built dist/, loads /v2/#compare-trade
headless (desktop 1440 and mobile 390), turns on one Indexed and one VORP vs
waivers series next to the default DDA ones, builds a trade through the page's
own search boxes, and checks against window.TradeValueCurveControls.getAllRows():

  * one row per selected, available series; "You give" and "You get" are the
    sums of that series' engine values for the players on each side, and
    "Get − give" is exactly their difference with a matching ▲ / ▼ / = label;
  * a player with no value in a series turns that row into "—" plus a reason
    naming the player, never a 0 (JEG-541: the missing value is simulated by
    wrapping the engine's row accessors, since after JEG-508 every chart prices
    every player and the fixture may have no natural gap);
  * VORP vs waivers series sit only in their own panel, never in the
    trade-value table;
  * the trade survives a round trip to Player values;
  * JEG-467: "Player values shown" defaults to DDF Value and is the shared
    grouped picker (JEG-466); DDF Value is the first row of "Difference by
    source & method", marked in words as the series that decides the verdict;
  * no page errors and no horizontal overflow at 390 px;
  * JEG-886: the Deal read never says "fair market price" / "little reason to
    refuse" unless the per-chart count says the charts would accept (Likely), never
    "will likely see a loss" unless it is Unlikely, and when the per-chart count does not
    support the chart average's side it names the split (and so does the market card),
    on the search-box trade and on a second trade opened by link where the charts
    disagree with each other and DDF Value agrees;
  * JEG-1112 (Jeremy, 2026-10-26, option D): the verdict card no longer opens with the
    "Should you propose or accept?" / "Will they accept?" lines (the Deal read says the
    same), so neither is in the DOM; the JEG-875/895 answer, level and chart-count checks
    that read them went with them.

Discrimination: test_guard_fails_on_broken_builds serves trade.js with the
sign flipped, with missing values read as 0 and with the chart split ignored, and
v2.js with VORP mixed into the trade-value table, and requires the checks to fail
on each.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
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
from tests._holds import pin_holds_in_dist  # noqa: E402
from tests.test_v2_risers_render import PICKER_READ, check_picker  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


TRADE_JS = ROOT / "app" / "v2" / "trade.js"
V2_JS = ROOT / "app" / "v2" / "v2.js"
EXTRA_SERIES = ("usatoday", "espn_vorp")
# The published chart series "Will they accept?" and the deal read count (targets.js CHART_KEYS).
CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
# JEG-886: the answer to "Will they accept?" each chart-average column's copy assumes.
DEAL_SPLIT_ACCEPT = {"win": "Unlikely", "even": "Likely", "lose": "Likely"}
FAIR_COPY = ("fair market price", "little reason to refuse", "easy for them", "call it fair")
HARD_SELL_COPY = ("will likely see a loss",)

# JEG-875/886: a second trade, opened by link, where the compared charts disagree with each
# other (nets on both sides of zero) while DDF Value says win by 5%+
# of the value traded. Prefers one where the per-chart count contradicts the chart average's
# side (the JEG-886 split). Selection only: the checks recompute everything in Python.
PICK_SPLIT = """() => {
  const C = window.TradeValueCurveControls;
  const info = Object.fromEntries(C.getSourceInfo({includeComposite: true}).map(i => [i.key, i.available]));
  const active = window.TradeValueV2.pageKeys('compare').filter(k => info[k]);
  const charts = active.filter(k => window.TradeValueTargets.CHART_KEYS.includes(k));
  const keys = [...new Set(active.concat(['ddf_value', 'ddf_value_projections']))];
  const rows = C.getAllRows().filter(r => keys.every(k => Number.isFinite(r.values[k])) && !r.ddfLowConfidence)
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value).slice(0, 40);
  const sum = (list, k) => list.reduce((s, r) => s + r.values[k], 0);
  const sideOf = (net, give, receive) => { const t = Math.max(1, 0.03 * ((give + receive) / 2)); return net >= t ? 'win' : net <= -t ? 'lose' : 'even'; };
  const table = {win: 'Unlikely', even: 'Likely', lose: 'Likely'};
  let fallback = null;
  for (let a = 0; a < rows.length; a++) for (let b = a + 1; b < rows.length; b++) for (let c = 0; c < rows.length; c++) {
    if (c === a || c === b) continue;
    const give = [rows[a], rows[b]], receive = [rows[c]];
    const net = k => sum(receive, k) - sum(give, k);
    const traded = k => sum(receive, k) + sum(give, k);
    if (net('ddf_value') < 0.05 * traded('ddf_value') || net('ddf_value_projections') < 0.05 * traded('ddf_value_projections')) continue;
    const nets = charts.map(net);
    if (charts.length < 3 || !(Math.min(...nets) < 0 && Math.max(...nets) > 0)) continue;
    const pick = {give: give.map(r => [String(r.player_key), r.name]), receive: receive.map(r => [String(r.player_key), r.name])};
    const avg = list => list.reduce((s, x) => s + x, 0) / list.length;
    const side = sideOf(avg(nets), avg(charts.map(k => sum(give, k))), avg(charts.map(k => sum(receive, k))));
    const yes = nets.filter(n => n < 0.05).length, share = yes / nets.length;
    const accept = share >= 2 / 3 ? 'Likely' : share <= 1 / 3 ? 'Unlikely' : 'Toss-up';
    if (accept !== table[side]) return pick;
    fallback = fallback || pick;
  }
  return fallback;
}"""

# Two priced stars to give, one star plus one player missing a selected series to get.
PICK = """(extra) => {
  const C = window.TradeValueCurveControls;
  const info = Object.fromEntries(C.getSourceInfo({includeComposite: true}).map(i => [i.key, i.available]));
  const rows = C.getAllRows();
  const active = window.TradeValueV2.pageKeys('compare').filter(k => info[k]);
  const byEspn = rows.filter(r => Number.isFinite(r.values.espn)).sort((a, b) => b.values.espn - a.values.espn);
  const complete = r => active.every(k => Number.isFinite(r.values[k]));
  const priced = byEspn.filter(complete);
  const gap = byEspn.find(r => !complete(r) && active.some(k => Number.isFinite(r.values[k])));
  return {give: [priced[0], priced[3]].map(r => [String(r.player_key), r.name]),
          receive: [priced[1], gap].filter(Boolean).map(r => [String(r.player_key), r.name])};
}"""

# JEG-541: since JEG-508 every chart gives a value (listed, estimated, or 0 below rosterable
# depth), so the live fixture may have no star missing a selected series. The missing-value path
# is exercised hermetically: the engine's row accessors are wrapped so one priced player lacks
# `series` (value null, with a reason), exactly as the engine reports a null.
SIMULATE_MISSING = """(series) => {
  const C = window.TradeValueCurveControls;
  const ranked = C.getAllRows().filter(r => Number.isFinite(r.values.espn) && Number.isFinite(r.values[series]))
    .sort((a, b) => b.values.espn - a.values.espn);
  const target = ranked[6];
  if (!target) return null;
  const key = String(target.player_key);
  const reason = 'Simulated in test: no value in this series';
  const patch = r => {
    if (!r || String(r.player_key) !== key) return r;
    const estimated = {...(r.estimated || {})};
    delete estimated[series];
    return {...r, values: {...r.values, [series]: null}, estimated,
      missingReasons: {...(r.missingReasons || {}), [series]: reason}};
  };
  for (const name of ['getAllRows', 'getRows']) {
    const original = C[name].bind(C);
    C[name] = (...args) => original(...args).map(patch);
  }
  if (C.getPlayer) { const original = C.getPlayer.bind(C); C.getPlayer = (...args) => patch(original(...args)); }
  return {key, name: target.name, series};
}"""


def simulate_missing(page, series):
    """Make one priced player lack `series` (see SIMULATE_MISSING); returns {key, name, series}."""
    simulated = page.evaluate(SIMULATE_MISSING, series)
    if not simulated:
        raise AssertionError(f"no priced player has {series!r} to simulate a missing value")
    return simulated


READ = """() => {
  const C = window.TradeValueCurveControls;
  const engine = Object.fromEntries(C.getAllRows().map(r => [String(r.player_key), {name: r.name, values: r.values, low: Boolean(r.ddfLowConfidence)}]));
  const info = Object.fromEntries(C.getSourceInfo({includeComposite: true}).map(i => [i.key, i.available]));
  const read = table => [...table.querySelectorAll('tbody tr')].map(tr => {
    const cell = name => tr.querySelector(`td[data-col="${name}"]`);
    return {key: tr.dataset.source,
      give: cell('give').textContent, receive: cell('receive').textContent,
      net: cell('net').childNodes[0]?.textContent ?? null,
      label: cell('net').querySelector('.delta')?.textContent ?? null,
      missing: Boolean(cell('net').querySelector('.missing')),
      why: cell('net').querySelector('.missing .why')?.textContent ?? null};
  });
  const side = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)].map(li => li.dataset.playerKey);
  return {engine, active: window.TradeValueV2.pageKeys('compare').filter(k => info[k]),
    give: side('v2GivePlayers'), receive: side('v2GetPlayers'),
    points: document.getElementById('v2CTable').hidden ? [] : read(document.getElementById('v2CTable')),
    vorp: document.getElementById('v2CVorpCard').hidden ? [] : read(document.getElementById('v2CVorpTable')),
    marked: [...document.querySelectorAll('#v2CTable tbody tr.is-verdict')].map(tr => ({key: tr.dataset.source,
      tag: tr.querySelector('.v2-cverdict-tag')?.textContent ?? null})),
    headsGone: !document.getElementById('v2CHeads') && !document.querySelector('#v2CVerdict .v2-chead'),
    deal: {hidden: document.getElementById('v2CDeal').hidden, read: document.getElementById('v2CDealRead').textContent,
      text: document.getElementById('v2CDealText').textContent,
      market: document.querySelector('#v2CDealNets li[data-net="market"] .v2-deal-net')?.textContent ?? null},
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""


def fmt(value):
    return f"{value:.1f}"


def fmt_net(net):
    text = f"{abs(net):.1f}"
    if text == "0.0":
        return "0.0"
    return ("+" if net > 0 else "−") + text


def finite(value):
    return isinstance(value, (int, float)) and value == value and abs(value) != float("inf")


def check(snap) -> list[str]:
    errors = []
    engine = snap["engine"]
    want_give, want_receive = [k for k, _ in snap["pick"]["give"]], [k for k, _ in snap["pick"]["receive"]]
    if snap["give"] != want_give or snap["receive"] != want_receive:
        errors.append(f"sides {snap['give']} / {snap['receive']} != picked {want_give} / {want_receive}")
    point_keys = [k for k in snap["active"] if not k.endswith("_vorp")]
    vorp_keys = [k for k in snap["active"] if k.endswith("_vorp")]
    if [r["key"] for r in snap["points"]] != point_keys and sorted(r["key"] for r in snap["points"]) != sorted(point_keys):
        errors.append(f"trade-value rows {[r['key'] for r in snap['points']]} != selected {point_keys}")
    if sorted(r["key"] for r in snap["vorp"]) != sorted(vorp_keys):
        errors.append(f"VORP vs waivers rows {[r['key'] for r in snap['vorp']]} != selected {vorp_keys}")
    if not vorp_keys or not point_keys:
        errors.append("the test needs both a trade-value and a VORP vs waivers series selected")
    saw_missing = False
    for row in snap["points"] + snap["vorp"]:
        key = row["key"]
        vals = lambda keys: [(engine.get(k) or {}).get("values", {}).get(key) for k in keys]
        give, receive = vals(snap["give"]), vals(snap["receive"])
        absent = [engine.get(k, {}).get("name", k) for k, v in zip(snap["give"] + snap["receive"], give + receive) if not finite(v)]
        if absent:
            saw_missing = True
            if not row["missing"] or row["give"] != "—" or row["receive"] != "—" or "0.0" in (row["net"] or ""):
                errors.append(f"{key}: {absent} have no value but the row shows {row}")
            elif not all(name in (row["why"] or "") for name in absent):
                errors.append(f"{key}: reason {row['why']!r} does not name {absent}")
            continue
        g, r = sum(give), sum(receive)
        net = r - g
        if row["missing"] or row["give"] != fmt(g) or row["receive"] != fmt(r) or row["net"] != fmt_net(net):
            errors.append(f"{key}: shows give {row['give']} get {row['receive']} net {row['net']}; "
                          f"engine {fmt(g)} / {fmt(r)} / {fmt_net(net)}")
        symbol = "=" if fmt_net(net) == "0.0" else "▲" if net > 0 else "▼"
        if not (row["label"] or "").startswith(symbol):
            errors.append(f"{key}: label {row['label']!r} does not match net {net}")
    if snap["kind"] == "gap" and not saw_missing:
        errors.append("the trade has no player missing a selected series; the missing-value path went unchecked")
    if snap["kind"] == "split" and saw_missing:
        errors.append("the split trade must be priced by every selected series")
    if "ddf_value" in point_keys:
        if not snap["points"] or snap["points"][0]["key"] != "ddf_value":
            errors.append(f"DDF Value is not the first row: {[r['key'] for r in snap['points']]}")
        if snap["marked"] != [{"key": "ddf_value", "tag": "★ Decides the verdict"}]:
            errors.append(f"DDF Value row not marked as deciding the verdict: {snap['marked']}")
    else:
        errors.append("DDF Value is not shown; its row went unchecked")
    # JEG-1112: the two headline lines are gone from the verdict card (the Deal read says the same).
    if not snap["headsGone"]:
        errors.append("the verdict card still has the propose / accept headline lines (removed in JEG-1112)")
    errors += check_deal(snap, point_keys)
    errors += check_picker(snap["picker"], "Player values shown")
    if snap["firstShown"] != "ddf_value":
        errors.append(f"Player values shown opened on {snap['firstShown']!r}, not DDF Value")
    return errors


def trade_players(snap):
    """(give, receive, low) in test_v2_headlines' case shape, from the engine snapshot."""
    engine = snap["engine"]

    def side(keys):
        return [{"player_key": k, "values": engine[k]["values"]} for k in keys]
    return side(snap["give"]), side(snap["receive"]), any(engine[k]["low"] for k in snap["give"] + snap["receive"])


def deal_expectation(snap, point_keys):
    """JEG-886: the chart average's side and the per-chart count "Will they accept?" uses, from the
    engine values; None when fewer than 3 compared charts price every player."""
    give, receive, _ = trade_players(snap)
    nets = []
    for key in [k for k in CHART_KEYS if k in point_keys]:
        vals = [p["values"].get(key) for p in give + receive]
        if not all(finite(v) for v in vals):
            continue
        g, r = sum(p["values"][key] for p in give), sum(p["values"][key] for p in receive)
        nets.append((r - g, g, r))
    if len(nets) < 3:
        return None
    avg_net, avg_give, avg_rec = (sum(x[i] for x in nets) / len(nets) for i in range(3))
    threshold = max(1.0, 0.03 * (avg_give + avg_rec) / 2)
    side = "win" if avg_net >= threshold else "lose" if avg_net <= -threshold else "even"
    yes = sum(1 for n, _, _ in nets if n < 0.05)
    share = yes / len(nets)
    accept = "Likely" if share >= 2 / 3 else "Unlikely" if share <= 1 / 3 else "Toss-up"
    return {"side": side, "accept": accept, "split": accept != DEAL_SPLIT_ACCEPT[side], "nets": [n for n, _, _ in nets]}


def check_deal(snap, point_keys) -> list[str]:
    """JEG-886: the Deal read and "Will they accept?" never contradict, and a split is named."""
    errors = []
    want = deal_expectation(snap, point_keys)
    deal = snap["deal"]
    if want is None or deal["hidden"] or not deal["read"].strip():
        if snap["kind"] == "split":
            errors.append(f"the split trade has no deal read: {deal}")
        return errors
    text = f"{deal['read']} {deal['text']}"
    if want["accept"] != "Likely" and any(phrase in text for phrase in FAIR_COPY):
        errors.append(f"deal read {text!r} calls the trade fair while the charts say accept {want['accept']} ({want['nets']})")
    if want["accept"] != "Unlikely" and any(phrase in text for phrase in HARD_SELL_COPY):
        errors.append(f"deal read {text!r} says a hard sell while the charts say accept {want['accept']} ({want['nets']})")
    if want["split"]:
        if "split" not in deal["read"] or "the other manager winning or even" not in deal["text"]:
            errors.append(f"deal read {text!r} does not name the chart split ({want['nets']}, accept {want['accept']})")
        if "Charts split" not in (deal["market"] or ""):
            errors.append(f"market card {deal['market']!r} hides the chart split ({want['nets']})")
    elif "Charts split" in (deal["market"] or ""):
        errors.append(f"market card {deal['market']!r} says split but the charts support the average's side ({want['nets']})")
    if snap["kind"] == "split" and not want["split"]:
        errors.append(f"the split trade's charts {want['nets']} support the chart average's side: the split path went unchecked")
    return errors


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/javascript", body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        # Held-proof fixture (JEG-718): the fidelity pulse holds different sources on different days.
        pin_holds_in_dist(dist)
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#compare-trade"
            finally:
                server.shutdown()


def collect(overrides=None, viewports=((1440, 1000), (390, 844))):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    snapshots = []
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=30000)
                first_shown = page.evaluate("() => document.getElementById('v2CShown').value")
                # JEG-498: Compare reads its own Customize list, so the extra series are added there.
                page.evaluate("""extra => { const V = window.TradeValueV2; V.setPageKeys('compare', [...new Set(V.pageKeys('compare').concat(extra))]); }""",
                              list(EXTRA_SERIES))
                simulate_missing(page, "usatoday")
                pick = page.evaluate(PICK, None)
                for side, field in (("give", "#v2GiveSearch"), ("receive", "#v2GetSearch")):
                    results = "#v2GiveResults" if side == "give" else "#v2GetResults"
                    for key, name in pick[side]:
                        page.fill(field, name)
                        page.click(f'{results} button[data-player-key="{key}"]')
                # The trade must survive a trip to Player values and back.
                page.evaluate("() => { location.hash = '#player-values'; }")
                page.wait_for_function("() => !document.getElementById('v2Main').hidden")
                page.evaluate("() => { location.hash = '#compare-trade'; }")
                page.wait_for_function("() => !document.getElementById('v2Compare').hidden")
                snap = page.evaluate(READ)
                snap.update(width=width, kind="gap", pick=pick, pageErrors=list(errors), firstShown=first_shown,
                            picker=page.evaluate(PICKER_READ, "#v2CShown"))
                snapshots.append(snap)
                # JEG-875/886: the second trade, opened by link (a shared trade).
                split = page.evaluate(PICK_SPLIT)
                if not split:
                    raise AssertionError("the fixture has no 2-for-1 where the charts disagree and DDF Value agrees")
                link = "#compare-trade?give=" + ",".join(k for k, _ in split["give"]) + "&get=" + ",".join(k for k, _ in split["receive"])
                page.evaluate("link => { location.hash = link; }", link)
                page.wait_for_function(
                    """want => JSON.stringify([...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(li => li.dataset.playerKey)) === want""",
                    arg=json.dumps([k for k, _ in split["give"]], separators=(",", ":")))
                snap = page.evaluate(READ)
                snap.update(width=width, kind="split", pick=split, pageErrors=list(errors), firstShown=first_shown,
                            picker=page.evaluate(PICKER_READ, "#v2CShown"))
                snapshots.append(snap)
                page.close()
        finally:
            browser.close()
    return snapshots


def check_all(snapshots) -> list[str]:
    errors = []
    for snap in snapshots:
        prefix = f"[{snap['width']}px {snap['kind']}] "
        errors += [prefix + e for e in check(snap)]
        if snap["pageErrors"]:
            errors.append(prefix + f"page errors: {snap['pageErrors']}")
        if snap["width"] <= 390 and snap["overflow"] > 0:
            errors.append(prefix + f"horizontal overflow {snap['overflow']}px")
    return errors


class CompareTradeRenderTest(unittest.TestCase):
    def test_rendered_numbers_match_engine(self):
        snapshots = collect()
        self.assertEqual(check_all(snapshots), [])
        self.assertTrue(all(s["points"] and s["vorp"] for s in snapshots))

    def test_guard_fails_on_broken_builds(self):
        trade = TRADE_JS.read_text(encoding="utf-8")
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = {
            "sign flipped": {"trade.js": trade.replace("net: receiveSum - giveSum", "net: giveSum - receiveSum", 1)},
            "missing read as zero": {"trade.js": trade.replace(
                "const value = row.values ? row.values[key] : null;",
                "const value = (row.values ? row.values[key] : null) ?? 0;")},
            # JEG-886: the deal read falls back to the chart average's cell copy whatever the per-chart count says.
            "deal read ignores the chart split": {"trade.js": trade.replace(
                "market.split = market.charts.accept !== DEAL_SPLIT_ACCEPT[market.side];", "market.split = false;", 1)},
            "VORP mixed into trade values": {"v2.js": v2.replace(
                'let pointKeys = usable(mineOrdered.filter(key => sourceMeta(key).method !== "vorp"));',
                "let pointKeys = usable(mineOrdered);", 1)},
        }
        for name, overrides in broken.items():
            with self.subTest(mutation=name):
                for file, body in overrides.items():
                    original = trade if file == "trade.js" else v2
                    self.assertNotEqual(body, original, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check_all(collect(overrides, viewports=((1440, 1000),))), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
