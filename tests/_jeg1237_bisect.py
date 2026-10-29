"""JEG-1237 scratch: which finder.js turns the ESPN-mine/Yahoo-theirs eval scenario from natural groups to none (not a test)."""
import functools
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_box_render import FIXTURE
from tests.test_v2_finder_eval_render import ESPN, GROUPS
from tests.test_v2_finder_render import FINDER_JS, _built_dist
from tests.test_v2_modules_render import _serve

_render_env.ensure_built()
from playwright.sync_api import sync_playwright
variants = [("current", FINDER_JS.read_text(encoding="utf-8"))] + sorted(
    (p.stem, p.read_text(encoding="utf-8")) for p in Path("tests/_jeg1237_variants").glob("*.js"))
with _built_dist() as base, sync_playwright() as pw:
    b = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
    for name, js in variants:
        for swap in (True, False):
            page = b.new_page(viewport={"width": 1440, "height": 900})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)[:120]))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.route("**/v2/finder.js*", functools.partial(_serve, js, "text/javascript"))
            try:
                page.goto(base + "#find-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
                page.evaluate("() => { location.hash = '#find-trade'; }")
                page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
                page.fill("#v2FindMineSearch", (ESPN if swap else FIXTURE).read_text(encoding="utf-8"))
                page.fill("#v2FindTheirsSearch", (FIXTURE if swap else ESPN).read_text(encoding="utf-8"))
                page.wait_for_timeout(500)
                page.select_option("#v2FindSize", "3")
                page.click("#v2FindGo")
                page.wait_for_timeout(1500)
                groups = page.evaluate(GROUPS)
                head = page.evaluate("() => document.getElementById('v2FindFit').textContent")
                counts = page.evaluate("() => ({mine: document.querySelectorAll('#v2FindMinePlayers li.v2-find-row').length, theirs: document.querySelectorAll('#v2FindTheirsPlayers li.v2-find-row').length, out: (document.getElementById('v2FindOut').innerText || '').slice(0, 300)})")
                fits = {}
                for g in groups: fits[g["fit"]] = fits.get(g["fit"], 0) + 1
                print(f"JEG1237BISECT {name} {'ESPN-mine' if swap else 'Yahoo-mine'} groups={len(groups)} fits={fits} rows={counts['mine']}/{counts['theirs']} head={head[:90]!r} errors={errs[:2]}")
                if len(groups) <= 2:
                    print(f"JEG1237BISECT {name} out={counts['out']!r}")
            except Exception as exc:
                print(f"JEG1237BISECT {name} {'ESPN-mine' if swap else 'Yahoo-mine'} FAILED {str(exc)[:200]} errors={errs[:2]}")
            page.close()
    b.close()
