"""v2 Compare a trade, frames 07 / 08 / 24, and the frame 18 series notice, rendered.

Builds dist/v2 into a temp copy of the built dist/ and loads it headless at
1440 and 390, with FantasyCalc Indexed and ESPN VORP vs waivers selected
next to the first-use sources, and a trade read from a shared link. Checks,
against the engine's own rows (TradeValueCurveControls.getAllRows()):

  * "Player values shown": every player's value on both sides is that exact
    series' engine value, or — when the engine has none (never 0);
  * each side's "<series> total" is the sum of those values, or incomplete
    (no number) when any player on that side has no value;
  * the story card's kind matches the complete rows' signs: a same-publisher,
    same-week Data Driven Adjustments vs Indexed sign flip is "contrast"; all
    one way is "agree"; otherwise "split";
  * "Show players" opens the per-player arithmetic for that series, with the
    engine's values and the same net as the row;
  * search keeps a player already on the trade, marked "✓ Added" and disabled;
  * "Swap sides" swaps the two lists;
  * bars only on complete rows;
  * Player values with one series selected shows the frame 18 notice naming it;
  * no page errors; no horizontal overflow at 390.

Discrimination: test_guard_fails_on_broken_builds serves v2.js showing the
ranking series' value whatever is picked, a total that skips missing players,
search hiding chosen players, a swap that does nothing, and the notice never
drawn, and requires each to fail.
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


V2_JS = ROOT / "app" / "v2" / "v2.js"
TRADE_JS = ROOT / "app" / "v2" / "trade.js"
EXTRA_SERIES = ("fantasycalc", "espn_vorp")

# Two priced stars each way, plus one player who lacks a selected series on the receive side.
PICK = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows();
  const active = window.TradeValueV2.shown();
  const byEspn = rows.filter(r => Number.isFinite(r.values.espn)).sort((a, b) => b.values.espn - a.values.espn);
  const complete = r => active.every(k => Number.isFinite(r.values[k]));
  const priced = byEspn.filter(complete);
  const gap = byEspn.find(r => !complete(r) && active.some(k => Number.isFinite(r.values[k])));
  return {give: [priced[0], priced[5]].map(r => String(r.player_key)),
          receive: [priced[2], gap].filter(Boolean).map(r => String(r.player_key))};
}"""

READ = """() => {
  const C = window.TradeValueCurveControls;
  const engine = Object.fromEntries(C.getAllRows().map(r => [String(r.player_key), r.values]));
  const info = Object.fromEntries(C.getSourceInfo().map(i => [i.key, i]));
  const side = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)].map(li => ({key: li.dataset.playerKey,
    source: li.querySelector('.v2-trade-value')?.dataset.source, text: li.querySelector('.v2-trade-value')?.textContent}));
  const total = id => ({hidden: document.getElementById(id).hidden, text: document.querySelector(`#${id} [data-total]`)?.textContent ?? null,
    missing: Boolean(document.querySelector(`#${id} [data-total] .missing`))});
  const rows = [...document.querySelectorAll('#v2CTable tbody tr[data-source]')].map(tr => ({key: tr.dataset.source,
    net: tr.querySelector('td[data-col="net"]').childNodes[0]?.textContent ?? null,
    missing: Boolean(tr.querySelector('td[data-col="net"] .missing')),
    bar: Boolean(tr.querySelector('.v2-wf-land'))}));
  return {engine, info, shown: document.getElementById('v2CShown').value,
    give: side('v2GivePlayers'), receive: side('v2GetPlayers'),
    giveTotal: total('v2GiveTotal'), getTotal: total('v2GetTotal'), rows,
    story: document.getElementById('v2CStory').hidden ? null : document.getElementById('v2CStory').dataset.story,
    storyText: document.getElementById('v2CStoryText').textContent,
    names: Object.fromEntries([...document.querySelectorAll('#v2CTable tbody tr[data-source]')].map(tr =>
      [tr.dataset.source, tr.querySelector('td.player').childNodes[1].textContent])),
    overflow: document.documentElement.scrollWidth - innerWidth};
}"""


def fmt(v):
    return f"{v:.1f}"


def fmt_net(v):
    t = f"{abs(v):.1f}"
    return "0.0" if t == "0.0" else ("+" if v > 0 else "−") + t


def finite(v):
    return isinstance(v, (int, float)) and v == v and abs(v) != float("inf")


def method(key):
    if key.endswith("_vorp"):
        return "vorp"
    if key.endswith("_adjusted") or key in ("espn", "cbsros", "razzball"):
        return "dda"
    return "indexed"


def publisher(key):
    for suffix in ("_vorp", "_adjusted"):
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def check_sides(snap, pick) -> list[str]:
    errors = []
    s = snap["shown"]
    engine = snap["engine"]
    for side, total in (("give", "giveTotal"), ("receive", "getTotal")):
        players = snap[side]
        if [p["key"] for p in players] != pick[side]:
            errors.append(f"{side}: players {[p['key'] for p in players]} != {pick[side]}")
            continue
        values = []
        for p in players:
            v = engine.get(p["key"], {}).get(s)
            values.append(v)
            if p["source"] != s:
                errors.append(f"{side}/{p['key']}: value from {p['source']!r}, picked {s!r}")
            if finite(v) and p["text"] != fmt(v):
                errors.append(f"{side}/{p['key']}: shows {p['text']!r}, engine {s} {fmt(v)}")
            if not finite(v) and ("—" not in (p["text"] or "") or any(ch.isdigit() for ch in p["text"] or "")):
                errors.append(f"{side}/{p['key']}: engine has no {s} value but shows {p['text']!r}")
        t = snap[total]
        if all(finite(v) for v in values):
            if t["missing"] or t["text"] != fmt(sum(values)):
                errors.append(f"{side} total {t} != engine sum {fmt(sum(values))}")
        elif not t["missing"] or any(ch.isdigit() for ch in t["text"] or ""):
            errors.append(f"{side} total must be incomplete (a player has no {s} value): {t}")
    return errors


def check_story(snap) -> list[str]:
    complete = []
    for r in snap["rows"]:
        if r["missing"]:
            if r["bar"]:
                return [f"{r['key']}: incomplete row draws a bar"]
            continue
        if not r["bar"]:
            return [f"{r['key']}: complete row has no bar"]
        net = r["net"] or ""
        sign = 0 if net == "0.0" else (1 if net.startswith("+") else -1)
        complete.append((r["key"], sign))
    signs = dict(complete)
    want = None
    for key, sign in complete:
        if method(key) == "dda" and key.endswith("_adjusted"):
            other = publisher(key)
            if other in signs and sign and signs[other] and sign != signs[other] \
                    and snap["info"][key].get("week") == snap["info"][other].get("week"):
                want = "contrast"
    if want is None and len(complete) >= 2:
        nonzero = {s for _, s in complete}
        want = "agree" if len(nonzero) == 1 else "split"
    if not complete:
        want = "incomplete"
    if snap["story"] != want:
        return [f"story {snap['story']!r}, complete rows {complete} want {want!r}"]
    # Jeremy, 2026-10-08: the story names the sources (agree and split).
    if want in ("agree", "split"):
        missing = [snap["names"][k] for k, _ in complete if snap["names"][k] not in snap["storyText"]]
        if missing:
            return [f"story does not name {missing}: {snap['storyText']!r}"]
    return []


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
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def run_checks(v2_js=None, trade_js=None, viewports=((1440, 1000), (390, 844))) -> list[str]:
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
                tag = f"[{width}px] "
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
                if trade_js is not None:
                    page.route("**/v2/trade.js*", functools.partial(_serve, trade_js))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
                # Frame 18 "only one comparable series": leave one source selected.
                page.evaluate("() => window.TradeValueV2.setShown([window.TradeValueCurveControls.getActiveSources()[0]])")
                page.evaluate("() => { location.hash = '#how-values'; location.hash = '#player-values'; }")
                page.wait_for_timeout(300)
                notice = page.evaluate("""() => ({shown: !document.getElementById('v2Notice').hidden,
                  text: document.getElementById('v2NoticeText').textContent, active: window.TradeValueV2.shown()})""")
                if len(notice["active"]) == 1 and (not notice["shown"] or "Only one series" not in notice["text"]):
                    errors.append(tag + f"one series selected but no notice: {notice}")
                page.evaluate("""keys => { for (const key of keys) {
                  const box = document.querySelector(`#legacyEngine #sourceToggles input[data-source="${key}"]`);
                  if (box && !box.checked && !box.disabled) box.click(); } }""",
                              ["espn", "fantasycalc_adjusted", "fantasypros_adjusted", "usatoday_adjusted", *EXTRA_SERIES])
                pick = page.evaluate(PICK)
                page.evaluate("p => { location.hash = `#compare-trade?give=${p.give.join(',')}&get=${p.receive.join(',')}`; }", pick)
                page.wait_for_function("() => !document.getElementById('v2Compare').hidden && !document.getElementById('v2CTable').hidden")
                options = page.evaluate("() => [...document.querySelectorAll('#v2CShown option')].map(o => o.value)")
                engine = page.evaluate(READ)["engine"]
                lacking = [k for k in options if any(not finite(engine[p].get(k)) for p in pick["give"] + pick["receive"])]
                if not lacking:
                    errors.append(tag + "no shown series lacks a value for a picked player; the incomplete total went unchecked")
                for shown in ["espn", "fantasycalc"] + lacking[:1]:
                    page.select_option("#v2CShown", shown)
                    snap = page.evaluate(READ)
                    errors += [tag + e for e in check_sides(snap, pick)]
                errors += [tag + e for e in check_story(snap)]
                # Without the FantasyCalc chart there is no same-publisher contrast, so the story
                # must agree or split, naming every complete source.
                page.evaluate("""() => { const box = document.querySelector('#legacyEngine #sourceToggles input[data-source="fantasycalc"]');
                  if (box && box.checked) box.click(); location.hash = '#player-values'; }""")
                page.wait_for_function("() => !document.getElementById('v2Main').hidden")
                page.evaluate("p => { location.hash = `#compare-trade?give=${p.give.join(',')}&get=${p.receive.join(',')}`; }", pick)
                page.wait_for_function("() => !document.getElementById('v2Compare').hidden && !document.getElementById('v2CTable').hidden")
                plain = page.evaluate(READ)
                if plain["story"] not in ("agree", "split"):
                    errors.append(tag + f"without the FantasyCalc chart the story should agree or split, got {plain['story']!r}")
                errors += [tag + e for e in check_story(plain)]
                page.evaluate("""() => { const box = document.querySelector('#legacyEngine #sourceToggles input[data-source="fantasycalc"]');
                  if (box && !box.checked) box.click(); }""")
                # Per-player arithmetic for the first complete row.
                first = next((r for r in snap["rows"] if not r["missing"]), None)
                if first:
                    page.click(f'#v2CTable tr[data-source="{first["key"]}"] .v2-cexpand')
                    lines = page.evaluate(f"""() => [...document.querySelectorAll('#v2CTable tr[data-breakdown="{first["key"]}"] p[data-player-key]')]
                      .map(p => ({{key: p.dataset.playerKey, text: p.textContent}}))""")
                    if {line["key"] for line in lines} != set(pick["give"] + pick["receive"]):
                        errors.append(tag + f"breakdown lists {lines}")
                    for line in lines:
                        v = snap["engine"][line["key"]].get(first["key"])
                        if finite(v) and not line["text"].endswith(fmt(v)):
                            errors.append(tag + f"breakdown {line} != engine {fmt(v)}")
                    net_text = page.evaluate(f"() => document.querySelector('#v2CTable tr[data-breakdown=\"{first['key']}\"] .v2-cbreak-net').textContent")
                    if first["net"] not in net_text:
                        errors.append(tag + f"breakdown net {net_text!r} != row net {first['net']!r}")
                # A chosen player stays in search, marked and disabled.
                name = page.evaluate(f"() => window.TradeValueCurveControls.getAllRows().find(r => String(r.player_key) === '{pick['give'][0]}').name")
                page.fill("#v2GetSearch", name)
                added = page.evaluate(f"""() => {{ const b = document.querySelector('#v2GetResults button[data-player-key="{pick['give'][0]}"]');
                  return b ? {{disabled: b.disabled, text: b.textContent}} : null; }}""")
                if not added or not added["disabled"] or "✓" not in added["text"]:
                    errors.append(tag + f"player on the trade is not shown as added in search: {added}")
                page.fill("#v2GetSearch", "")
                page.click("#v2CSwap")
                swapped = page.evaluate(READ)
                if [p["key"] for p in swapped["give"]] != pick["receive"] or [p["key"] for p in swapped["receive"]] != pick["give"]:
                    errors.append(tag + "Swap sides did not swap the lists")
                if width <= 390 and swapped["overflow"] > 0:
                    errors.append(tag + f"horizontal overflow {swapped['overflow']}px")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class OfferRenderTest(unittest.TestCase):
    def test_offer_matches_engine(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        trade = TRADE_JS.read_text(encoding="utf-8")
        broken = {
            "story names no source": {"v2_js": v2.replace(
                "    const names = keys.map(seriesName);", "    const names = keys.map(() => \"a source\");", 1)},
            "values from the ranking series": {"v2_js": v2.replace(
                "const v = shown && row.values ? row.values[shown] : null;",
                "const v = shown && row.values ? row.values[view.rankKey] : null;", 1)},
            "total skips missing players": {"trade_js": trade.replace(
                "if (!rows.length || missing.length) return {key, total: null, missing};",
                "if (!rows.length) return {key, total: null, missing};", 1).replace(
                "rows.reduce((sum, row) => sum + row.values[key], 0)",
                "rows.reduce((sum, row) => sum + (Number.isFinite(row.values[key]) ? row.values[key] : 0), 0)", 1)},
            "search hides chosen players": {"v2_js": v2.replace(
                "      .filter(row => String(row.name || \"\").toLowerCase().includes(needle))",
                "      .filter(row => !TR.give.concat(TR.receive).some(p => p.key === String(row.player_key)) && String(row.name || \"\").toLowerCase().includes(needle))", 1)},
            "swap does nothing": {"v2_js": v2.replace(
                "[TR.give, TR.receive] = [TR.receive, TR.give];", "void 0;", 1)},
            "notice never drawn": {"v2_js": v2.replace("    renderNotice();\n", "", 1)},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                body = next(iter(kwargs.values()))
                self.assertNotIn(body, (v2, trade), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(viewports=((1440, 1000),), **kwargs), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
