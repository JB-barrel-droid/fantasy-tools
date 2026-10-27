"""Shared pieces for the league workspace render tests (JEG-1021): a browser on the built page, the frozen fixture leagues, seeding."""
from __future__ import annotations

import contextlib
import functools
import json
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import _built_dist
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "league"
APP = ROOT / "app" / "v2"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"fixture-{name}.json").read_text(encoding="utf-8"))


def source(name: str) -> str:
    return (APP / name).read_text(encoding="utf-8")


SEED = """([fx, mine]) => {
  const W = window.TradeValueWorkspace;
  let ws = W.newWorkspace({name: 'Test league'});
  fx.teams.forEach(t => { ws = W.ops.addTeam(ws, t.name, {entries: t.players}); });
  if (mine !== null) ws = W.ops.setMyTeam(ws, ws.teams[mine].id);
  W.store.replace(ws, 'replace');
  return ws.teams.map(t => t.entries.length);
}"""

# Every fixture key is an engine row (K and DEF excepted).
RESOLVE = """(fx) => { const have = new Set(window.TradeValueCurveControls.getAllRows().map(r => String(r.player_key)));
  return fx.teams.flatMap(t => t.players).filter(p => !p.key.startsWith('x:') && !have.has(p.key)).map(p => p.name); }"""


def seed(page, name: str, mine="fixture"):
    fx = fixture(name)
    index = fx.get("myTeamIndex", 0) if mine == "fixture" else mine
    return page.evaluate(SEED, [fx, index])


@contextlib.contextmanager
def browser_on_build():
    """(browser, base): the built page served locally and a hermetic Chromium."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            yield browser, base
        finally:
            browser.close()


def open_page(browser, base, width=1366, height=768, overrides=None, errors=None, tag="", scheme="light", init_script=None, context=None):
    ctx = context or browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme, accept_downloads=True)
    if init_script:
        ctx.add_init_script(init_script)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"{tag}page error: {e}") if errors is not None else None)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    for name, body in (overrides or {}).items():
        page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/css" if name.endswith(".css") else "text/javascript"))
    page.goto(base + "#find-league", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && window.TradeValueCurveControls && document.getElementById('v2LgCard')", timeout=60000)
    page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=20000)
    return page


def wait_opps(page, timeout=60000):
    page.wait_for_function("() => document.querySelector('#v2LgOppsTable, #v2LgOppsMsg') && !document.querySelector('#v2LgOppsBody[aria-busy]') && !(document.getElementById('v2LgOppsMsg') || {}).textContent?.startsWith('Finding')", timeout=timeout)
    page.wait_for_timeout(100)
