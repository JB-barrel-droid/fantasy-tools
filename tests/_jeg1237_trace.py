"""JEG-1237 scratch: step trace of the keyboard settings check (not a test)."""
from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import PICK, _built_dist, add

_render_env.ensure_built()
from playwright.sync_api import sync_playwright
with _built_dist() as base, sync_playwright() as pw:
    b = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
    page = b.new_page(viewport={"width": 1366, "height": 768})
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    page.goto(base + "#find-trade", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    for n in pick["mine"]: add(page, "Mine", n)
    for n in pick["theirs"]: add(page, "Theirs", n)
    T = "() => ({te: document.getElementById('v2FindBackupsTE').textContent, up: document.getElementById('v2FindBackupsTEUp').disabled, focus: document.activeElement && document.activeElement.id, rails: document.getElementById('v2FindGuardrails').hidden, g: JSON.stringify(window.TradeValueWorkspace.store.get ? '' : '')})"
    page.click("#v2FindGo"); page.wait_for_timeout(400)
    page.click("#v2FindEdit"); page.wait_for_timeout(200)
    print("JEG1237TRACE open", page.evaluate(T))
    page.focus("#v2FindBackupsTEUp"); print("JEG1237TRACE focused", page.evaluate(T))
    page.keyboard.press("Enter"); print("JEG1237TRACE enter1", page.evaluate(T))
    page.keyboard.press("Enter"); print("JEG1237TRACE enter2", page.evaluate(T))
    page.click("#v2FindBackupsTEUp"); print("JEG1237TRACE click3", page.evaluate(T))
    page.focus("#v2FindProtectRB"); page.keyboard.press("Space"); print("JEG1237TRACE space", page.evaluate(T))
    page.click("#v2FindGo"); page.wait_for_timeout(400)
    print("JEG1237TRACE after", page.evaluate("() => document.getElementById('v2FindGuardrailSummary').textContent"))
    b.close()
