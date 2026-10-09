"""v2 Compare a trade, rendered: every number on the tab is the engine's.

Builds dist/v2 into a temp copy of the built dist/, loads /v2/#compare-trade
headless (desktop 1440 and mobile 390), turns on one Indexed and one VORP vs
waivers series next to the default DDA ones, builds a trade through the page's
own search boxes, and checks against window.TradeValueCurveControls.getAllRows():

  * one row per selected, available series; "You give" and "You get" are the
    sums of that series' engine values for the players on each side, and
    "Get − give" is exactly their difference with a matching ▲ / ▼ / = label;
  * a player with no value in a series turns that row into "—" plus a reason
    naming the player, never a 0;
  * VORP vs waivers series sit only in their own panel, never in the
    trade-value table;
  * the trade survives a round trip to Player values;
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves trade.js with the
sign flipped and with missing values read as 0, and v2.js with VORP mixed into
the trade-value table, and requires the checks to fail on each.
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
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


TRADE_JS = ROOT / "app" / "v2" / "trade.js"
V2_JS = ROOT / "app" / "v2" / "v2.js"
EXTRA_SERIES = ("usatoday", "espn_vorp")

# Two priced stars to give, one star plus one player missing a selected series to get.
PICK = """(extra) => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows();
  const active = C.getActiveSources();
  const byEspn = rows.filter(r => Number.isFinite(r.values.espn)).sort((a, b) => b.values.espn - a.values.espn);
  const complete = r => active.every(k => Number.isFinite(r.values[k]));
  const priced = byEspn.filter(complete);
  const gap = byEspn.find(r => !complete(r) && active.some(k => Number.isFinite(r.values[k])));
  return {give: [priced[0], priced[3]].map(r => [String(r.player_key), r.name]),
          receive: [priced[1], gap].filter(Boolean).map(r => [String(r.player_key), r.name])};
}"""

READ = """() => {
  const C = window.TradeValueCurveControls;
  const engine = Object.fromEntries(C.getAllRows().map(r => [String(r.player_key), {name: r.name, values: r.values}]));
  const info = Object.fromEntries(C.getSourceInfo().map(i => [i.key, i.available]));
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
  return {engine, active: C.getActiveSources().filter(k => info[k]),
    give: side('v2GivePlayers'), receive: side('v2GetPlayers'),
    points: document.getElementById('v2CTable').hidden ? [] : read(document.getElementById('v2CTable')),
    vorp: document.getElementById('v2CVorpCard').hidden ? [] : read(document.getElementById('v2CVorpTable')),
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
    if not saw_missing:
        errors.append("the trade has no player missing a selected series; the missing-value path went unchecked")
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
                for key in EXTRA_SERIES:
                    page.evaluate("""key => { const box = document.querySelector(`#legacyEngine #sourceToggles input[data-source="${key}"]`);
                      if (box && !box.checked && !box.disabled) box.click(); }""", key)
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
                snap.update(width=width, pick=pick, pageErrors=list(errors))
                snapshots.append(snap)
                page.close()
        finally:
            browser.close()
    return snapshots


def check_all(snapshots) -> list[str]:
    errors = []
    for snap in snapshots:
        prefix = f"[{snap['width']}px] "
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
            "VORP mixed into trade values": {"v2.js": v2.replace(
                "const pointKeys = usable(view.plotKeys);",
                "const pointKeys = usable(view.plotKeys.concat(view.vorpKeys));", 1)},
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
