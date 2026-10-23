"""v2 accessibility batch 2, rendered (JEG-897, 899, 900, 901, 904).

Builds dist/v2 into a temp copy of the built dist/ and checks, headless:

  * JEG-897: every row / card / mover item that opens the player drawer says so
    (aria-haspopup=dialog + a description) and opens on Space as well as Enter;
    #v2Chart is a named group and arrow keys announce the player in a polite
    status line;
  * JEG-899: one tab stop per table / card list (roving tabindex, ArrowDown /
    ArrowUp / Home / End move, ArrowRight enters the value cells), value cells
    and waterfall steps are not tab stops but still focus by pointer;
  * JEG-900: the Compare and Find a trade name boxes are comboboxes with a
    listbox, a polite "N players match" line, ArrowDown to a result and Enter;
  * JEG-901: the target-card dots and the Start/Bench tag have a real accessible
    name, and the hover-only notes are also aria-description;
  * JEG-904: Value-pie tables have a name and th scope=col, the Values auditing
    headings run h1 > h2 > h3, and the Player values / Compare tables are named.

Discrimination: test_guard_fails_on_broken_builds serves a build with each fix
reverted in turn and requires the checks to fail.
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


@contextlib.contextmanager
def _built_dist(patches=()):
    """Build dist/v2; `patches` are (file, old, new) text edits applied to the built copy."""
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)
        for name, old, new in patches:
            target = dist / "v2" / name if name != "index.html" else dist / "v2" / "index.html"
            text = target.read_text(encoding="utf-8")
            if old not in text:
                raise AssertionError(f"mutation anchor is stale: {name}: {old[:60]!r}")
            target.write_text(text.replace(old, new, 1), encoding="utf-8")

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


def _goto(page, base, route, ready):
    page.goto(base + "#" + route, wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2", timeout=40000)
    page.evaluate(f"() => {{ location.hash = '#{route}'; }}")
    page.wait_for_function(ready, timeout=40000)
    page.wait_for_timeout(300)


def _open_checks(page, tag, list_sel, item_sel, errors):
    """Rows of one list: one tab stop, haspopup, description, Space opens, arrows move."""
    info = page.evaluate("""([listSel, itemSel]) => {
      const box = document.querySelector(listSel);
      const items = box ? [...box.querySelectorAll(itemSel)].filter(e => e.offsetParent !== null) : [];
      const stops = box ? [...box.querySelectorAll('[tabindex="0"]')].filter(e => e.offsetParent !== null).length : -1;
      return {n: items.length, stops,
        popup: items.every(e => e.getAttribute('aria-haspopup') === 'dialog'),
        described: items.every(e => e.getAttribute('aria-describedby') === 'v2OpenHint'),
        hint: (document.getElementById('v2OpenHint') || {}).textContent || ''};
    }""", [list_sel, item_sel])
    if info["n"] < 2:
        errors.append(f"{tag}: expected 2+ visible items in {list_sel}, found {info['n']}")
        return
    if info["stops"] != 1:
        errors.append(f"{tag}: {list_sel} has {info['stops']} tab stops, expected 1 (JEG-899)")
    if not info["popup"]:
        errors.append(f"{tag}: {list_sel} items lack aria-haspopup=dialog (JEG-897)")
    if not info["described"] or "Enter or Space" not in info["hint"]:
        errors.append(f"{tag}: {list_sel} items lack the open-details description (JEG-897)")
    page.locator(f"{list_sel} {item_sel}").first.focus()
    page.keyboard.press("ArrowDown")
    second = page.evaluate("([l, i]) => { const e = [...document.querySelectorAll(l + ' ' + i)]; return e.indexOf(document.activeElement); }", [list_sel, item_sel])
    if second != 1:
        errors.append(f"{tag}: ArrowDown in {list_sel} moved to item {second}, expected 1")
    page.keyboard.press("ArrowUp")
    page.keyboard.press("Space")
    page.wait_for_timeout(250)
    opened = page.evaluate("() => { const d = document.getElementById('v2Drawer'); return !!d && !d.hidden && d.contains(document.activeElement); }")
    if not opened:
        errors.append(f"{tag}: Space on a {list_sel} item did not open the player drawer (JEG-897)")
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)


def run_checks(patches=(), only=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors: list[str] = []
    want = lambda name: only is None or name in only  # noqa: E731
    with _built_dist(patches) as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            def fresh(width):
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.errors = []
                page.on("pageerror", lambda e: page.errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                return page

            # Player values (desktop): rows, value cells, chart, table name.
            if want("values"):
                page = fresh(1440)
                _goto(page, base, "player-values", "() => document.querySelector('#v2Table tbody tr')")
                _open_checks(page, "player-values", "#v2Table", "tbody > tr", errors)
                cells = page.evaluate("""() => {
                  const c = [...document.querySelectorAll('#v2Table td.has-math')];
                  return {n: c.length, tab0: c.filter(e => e.tabIndex === 0).length};
                }""")
                if cells["n"] and cells["tab0"]:
                    errors.append(f"player-values: {cells['tab0']} value cells are tab stops (JEG-899)")
                if cells["n"]:
                    page.locator("#v2Table tbody tr").first.focus()
                    page.keyboard.press("ArrowRight")
                    inside = page.evaluate("() => document.activeElement.classList.contains('has-math')")
                    if not inside:
                        errors.append("player-values: ArrowRight on a row did not reach its value cells (JEG-899)")
                    page.locator("#v2Table td.has-math").first.click()
                    if not page.evaluate("() => document.activeElement.classList.contains('has-math')"):
                        errors.append("player-values: a pointer click no longer focuses a value cell (JEG-899)")
                grid = page.evaluate("() => { const t = document.getElementById('v2Table'); return [t.getAttribute('role'), t.getAttribute('aria-labelledby'), t.querySelectorAll('th[scope=col]').length > 0]; }")
                if grid[0] != "grid" or grid[1] != "v2TableTitle" or not grid[2]:
                    errors.append(f"player-values: #v2Table role/name/scope {grid} (JEG-904)")
                chart = page.evaluate("() => { const c = document.getElementById('v2Chart'); return [c.getAttribute('role'), c.getAttribute('aria-label')]; }")
                if chart[0] != "group" or not chart[1]:
                    errors.append(f"player-values: #v2Chart role/name {chart} (JEG-897)")
                page.locator("#v2Chart").focus()
                page.keyboard.press("ArrowRight")
                page.keyboard.press("ArrowRight")
                said = page.evaluate("() => { const s = document.getElementById('v2ChartSay'); return s ? [s.getAttribute('role'), s.textContent] : null; }")
                if not said or said[0] != "status" or "rank" not in said[1]:
                    errors.append(f"player-values: arrow keys on the chart announce {said} (JEG-897)")
                tags = page.evaluate("() => [...document.querySelectorAll('.v2-tag')].filter(e => !e.getAttribute('aria-label')).length")
                if tags:
                    errors.append(f"player-values: {tags} .v2-tag chips without an accessible name (JEG-901)")
                if page.errors:
                    errors.append(f"player-values: page errors {page.errors}")
                page.close()

            # Trade targets: desktop table and phone cards, dots, tags.
            if want("targets"):
                page = fresh(1440)
                _goto(page, base, "trade-targets", "() => document.querySelector('#v2TTable tbody tr[data-player-key]')")
                _open_checks(page, "targets desktop", "#v2TTable", "tbody > tr[data-player-key]", errors)
                dots = page.evaluate("""() => { const d = [...document.querySelectorAll('.t-dot')];
                  return {n: d.length, bad: d.filter(e => e.getAttribute('role') !== 'img' || !/our value/.test(e.getAttribute('aria-label') || '')).length}; }""")
                if not dots["n"] or dots["bad"]:
                    errors.append(f"targets desktop: {dots['bad']} of {dots['n']} chart dots lack a role=img label (JEG-901)")
                notes = page.evaluate("""() => { const n = [...document.querySelectorAll('.t-score, .t-count[title], .t-diff')];
                  return {n: n.length, bad: n.filter(e => e.title && !e.getAttribute('aria-description')).length}; }""")
                if not notes["n"] or notes["bad"]:
                    errors.append(f"targets desktop: {notes['bad']} of {notes['n']} hover notes lack aria-description (JEG-901)")
                page.close()
                page = fresh(390)
                _goto(page, base, "trade-targets", "() => document.querySelector('#v2TCards > li')")
                _open_checks(page, "targets phone", "#v2TCards", "li", errors)
                stops = page.evaluate("() => [...document.querySelectorAll('#v2TCards .has-math')].filter(e => e.tabIndex === 0).length")
                if stops:
                    errors.append(f"targets phone: {stops} card values are tab stops (JEG-899)")
                page.close()

            if want("risers"):
                page = fresh(1440)
                _goto(page, base, "risers-fallers", "() => document.querySelector('#v2RRise > li[data-player-key]')")
                _open_checks(page, "risers", "#v2RRise", "li[data-player-key]", errors)
                page.close()

            # Compare: combobox, waterfall, table names.
            if want("compare"):
                page = fresh(1440)
                _goto(page, base, "compare-trade", "() => document.getElementById('v2GiveSearch')")
                box = page.locator("#v2GiveSearch")
                box.fill("a")
                page.wait_for_timeout(300)
                combo = page.evaluate("""() => { const i = document.getElementById('v2GiveSearch'), l = document.getElementById('v2GiveResults'), s = document.getElementById('v2GiveResultsCount');
                  return {role: i.getAttribute('role'), expanded: i.getAttribute('aria-expanded'), list: l.getAttribute('role'),
                    options: l.querySelectorAll('[role=option]').length, status: s ? s.textContent : null, live: s ? s.getAttribute('aria-live') : null}; }""")
                if combo["role"] != "combobox" or combo["expanded"] != "true" or combo["list"] != "listbox" or not combo["options"]:
                    errors.append(f"compare: search is not a combobox {combo} (JEG-900)")
                if not combo["status"] or str(combo["options"]) not in combo["status"] or combo["live"] != "polite":
                    errors.append(f"compare: result count not announced {combo} (JEG-900)")
                box.press("ArrowDown")
                active = page.evaluate("() => { const i = document.getElementById('v2GiveSearch'); const id = i.getAttribute('aria-activedescendant'); const e = id && document.getElementById(id); return e ? e.getAttribute('aria-selected') : null; }")
                if active != "true":
                    errors.append(f"compare: ArrowDown did not set aria-activedescendant ({active}) (JEG-900)")
                box.press("Enter")
                page.wait_for_timeout(300)
                added = page.evaluate("() => document.querySelectorAll('#v2GivePlayers li').length")
                if added != 1:
                    errors.append(f"compare: Enter on the active result added {added} players (JEG-900)")
                box.fill("zzzzqq")
                page.wait_for_timeout(300)
                none = page.evaluate("() => (document.getElementById('v2GiveResultsCount') || {}).textContent")
                if none != "No players match":
                    errors.append(f"compare: empty search announces {none!r} (JEG-900)")
                page.locator("#v2GetSearch").fill("b")
                page.wait_for_timeout(300)
                page.locator("#v2GetSearch").press("ArrowDown")
                page.locator("#v2GetSearch").press("Enter")
                page.wait_for_timeout(600)
                names = page.evaluate("() => ['v2CTable', 'v2CDealGrid'].map(id => (document.getElementById(id) || {getAttribute: () => 'missing'}).getAttribute('aria-labelledby'))")
                if names != ["v2CResultTitle", "v2CDealTitle"]:
                    errors.append(f"compare: table names {names} (JEG-904)")
                wf = page.evaluate("() => { const s = [...document.querySelectorAll('.v2-wf-step, .v2-wf-land')]; return {n: s.length, tab0: s.filter(e => e.tabIndex === 0).length}; }")
                if not wf["n"]:
                    errors.append("compare: no waterfall steps rendered for the test trade (guard cannot run)")
                elif wf["tab0"]:
                    errors.append(f"compare: {wf['tab0']} waterfall steps are tab stops (JEG-899)")
                page.close()

            if want("find"):
                page = fresh(1440)
                _goto(page, base, "find-trade", "() => document.getElementById('v2FindMineSearch')")
                page.locator("#v2FindMineSearch").fill("a")
                page.wait_for_timeout(300)
                combo = page.evaluate("""() => { const i = document.getElementById('v2FindMineSearch'), l = document.getElementById('v2FindMineResults'), s = document.getElementById('v2FindMineResultsCount');
                  return {role: i.getAttribute('role'), list: l.getAttribute('role'), status: s ? s.textContent : null}; }""")
                if combo["role"] != "combobox" or combo["list"] != "listbox" or not combo["status"] or "match" not in combo["status"]:
                    errors.append(f"find: search is not an announced combobox {combo} (JEG-900)")
                page.close()

            # Values auditing: Value pie tables and heading levels.
            if want("pie"):
                page = fresh(1440)
                _goto(page, base, "values-auditing/value-pie", "() => document.querySelector('table.audit-pie-table')")
                pie = page.evaluate("""() => {
                  const t = [...document.querySelectorAll('table.audit-pie-table')];
                  const levels = [...document.querySelectorAll('main h1, main h2, main h3, main h4')].filter(h => h.offsetParent !== null).map(h => Number(h.tagName[1]));
                  let jump = 0; levels.forEach((l, i) => { if (i && l - levels[i - 1] > 1) jump++; });
                  return {n: t.length, unnamed: t.filter(x => !x.getAttribute('aria-label')).length,
                    noScope: t.filter(x => [...x.querySelectorAll('th')].some(h => h.getAttribute('scope') !== 'col')).length, jump, levels}; }""")
                if not pie["n"] or pie["unnamed"] or pie["noScope"]:
                    errors.append(f"value-pie: {pie['n']} tables, {pie['unnamed']} unnamed, {pie['noScope']} without th scope (JEG-904)")
                if pie["jump"]:
                    errors.append(f"value-pie: heading levels skip a level {pie['levels']} (JEG-904)")
                page.close()
        finally:
            browser.close()
    return errors


class A11yBatch2RenderTest(unittest.TestCase):
    def test_batch2_checks(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        broken = {
            "no haspopup on rows": ([("v2.js", 'node.setAttribute("aria-haspopup", "dialog");', "")], {"values"}),
            "every row a tab stop": ([("v2.js", "item.tabIndex = item === keep ? 0 : -1;", "item.tabIndex = 0;")], {"values"}),
            "no Space to open": ([("v2.js", 'event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }',
                                  'event.key === "Enter") { event.preventDefault(); open(); }')], {"values"}),
            "chart not announced": ([("v2.js", "say.textContent = `${at.name}", "void `${at.name}")], {"values"}),
            "table unnamed": ([("index.html", ' role="grid" aria-labelledby="v2TableTitle"', "")], {"values"}),
            "no combobox": ([("namesearch.js", 'status.id = `${list.id}Count`;', 'status.id = "unused";')], {"compare"}),
            "dots unlabeled": ([("v2.js", 'd.setAttribute("aria-label", d.title);', "")], {"targets"}),
            "pie tables unscoped": ([("audit-pie.js", 'node.setAttribute("scope", "col");', "")], {"pie"}),
            "pie heading jump": ([("audit-pie.js", 'el("h2", "audit-pie-heading", "Total pie by source")',
                                   'el("h3", "audit-pie-heading", "Total pie by source")')], {"pie"}),
        }
        for name, (patches, only) in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(run_checks(patches, only), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
