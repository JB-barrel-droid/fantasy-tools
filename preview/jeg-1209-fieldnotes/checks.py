#!/usr/bin/env python3
"""Browser checks and screenshots for the JEG-1209 Fieldnotes revision 3 private preview.

  python3 preview/jeg-1209-fieldnotes/checks.py [--shots DIR]

Serves the repo root on 127.0.0.1, opens preview/jeg-1209-fieldnotes/index.html in Chromium (Playwright) and checks, at
1280x900, 768x1024, 390x844 and 320x700: no sideways page scroll, no script error, no request leaving 127.0.0.1, controls
at least 44px tall. Then, keyboard only: a column moves and focus stays on the pressed button; details open with focus on
their heading and Escape returns focus to the row's button; Clear and Select all in Opponents to include; a preference
change marks the results out of date; each review state (loading, no league, projections missing) says so. Screenshots
are named with the commit, route and width and listed in shots.json. Exit 1 on any failure.
"""
import functools
import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGE = "/preview/jeg-1209-fieldnotes/index.html"
WIDTHS = [(1280, 900), (768, 1024), (390, 844), (320, 700)]
ROUTES = ["finder", "flow", "handoffs"]


def commit():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short=8", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(argv):
    shots = Path(argv[argv.index("--shots") + 1]) if "--shots" in argv else ROOT / "preview/jeg-1209-fieldnotes/shots"
    shots.mkdir(parents=True, exist_ok=True)
    rev = commit()
    server = serve()
    base = f"http://127.0.0.1:{server.server_address[1]}{PAGE}"
    failures, listed, results = [], [], {}

    def check(name, ok, detail=""):
        results[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            failures.append(f"{name}: {detail}")

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"] if os.geteuid() == 0 else [])

        def page_at(w, h, query="?shot=1"):
            ctx = browser.new_context(viewport={"width": w, "height": h}, reduced_motion="reduce")
            page = ctx.new_page()
            errors, external = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("request", lambda r: external.append(r.url) if not r.url.startswith(("http://127.0.0.1", "data:", "blob:")) else None)
            return ctx, page, errors, external

        for w, h in WIDTHS:
            for route in ROUTES:
                ctx, page, errors, external = page_at(w, h)
                page.goto(f"{base}?shot=1#{route}")
                page.wait_for_timeout(400)
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                check(f"{route}@{w}: no sideways scroll", overflow <= 0, f"overflow {overflow}px")
                check(f"{route}@{w}: no script errors", not errors, "; ".join(errors[:3]))
                check(f"{route}@{w}: no external requests", not external, ", ".join(external[:3]))
                if route == "finder":
                    small = page.evaluate("""[...document.querySelectorAll('main button, main a.buttonlike, main a.journeystep, main summary')]
                      .filter(e => e.offsetParent && e.getBoundingClientRect().height < 44)
                      .map(e => (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 30))""")
                    check(f"finder@{w}: buttons at least 44px tall", not small, ", ".join(small[:5]))
                name = f"{rev}-{route}-{w}.png"
                page.screenshot(path=str(shots / name), full_page=True)
                listed.append({"file": name, "route": route, "width": w, "height": h, "theme": "light", "commit": rev})
                ctx.close()
        for w, h in [(1280, 900), (390, 844)]:
            ctx, page, errors, external = page_at(w, h)
            page.goto(f"{base}?shot=1&theme=dark#finder")
            page.wait_for_timeout(400)
            name = f"{rev}-finder-{w}-dark.png"
            page.screenshot(path=str(shots / name), full_page=True)
            listed.append({"file": name, "route": "finder", "width": w, "height": h, "theme": "dark", "commit": rev})
            check(f"finder@{w} dark: no script errors", not errors, "; ".join(errors[:3]))
            ctx.close()

        # Keyboard and disclosure, desktop then phone.
        for w, h in [(1280, 900), (390, 844)]:
            ctx, page, errors, _ = page_at(w, h)
            page.goto(f"{base}?shot=1#finder")
            page.wait_for_timeout(400)
            page.locator('#colOrder button[data-column="them"][data-move="up"]').focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(80)
            focused = page.evaluate("document.activeElement && document.activeElement.getAttribute('aria-label')")
            check(f"@{w}: column move keeps focus", focused == "Move Their starter Δ up", str(focused))
            heads = page.evaluate("[...document.querySelectorAll('.finder-table thead th')].map(t => t.dataset.col || 'trade')")
            cards = page.evaluate("[...document.querySelector('.finder-result .finder-mobile-metrics').children].map(d => d.dataset.col)")
            check(f"@{w}: table and cards follow the order", heads[1:4] == ["us", "usProj", "them"] and cards[:3] == ["us", "usProj", "them"], f"{heads} {cards}")
            opener = page.locator(".finder-table [data-open]" if w > 700 else ".finder-cards [data-open]").first
            opener.focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(80)
            check(f"@{w}: details focus their heading", page.evaluate("document.activeElement.classList.contains('detailtitle')"))
            page.keyboard.press("Escape")
            page.wait_for_timeout(80)
            check(f"@{w}: Escape returns focus to the row", page.evaluate("Boolean(document.activeElement.dataset.open)"))
            page.locator("#oiFinderNone").focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(80)
            check(f"@{w}: Clear shows no trades and says why", "No opponents are included" in page.inner_text("#v2LgOppsBody"))
            if w == 1280:
                page.screenshot(path=str(shots / f"{rev}-finder-{w}-cleared.png"), full_page=True)
                listed.append({"file": f"{rev}-finder-{w}-cleared.png", "route": "finder", "width": w, "height": h, "theme": "light", "state": "opponents cleared", "commit": rev})
            page.locator("#oiFinderAll").focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(80)
            check(f"@{w}: Select all brings the results back", "Showing" in page.inner_text("#oppsCount"))
            page.locator('#packageSize button[data-size="3"]').focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(50)
            check(f"@{w}: a preference change marks results out of date", page.is_visible("#staleNote") and page.get_attribute("#v2LgOpps", "data-stale") == "true")
            for state, words in [("loading", "still loading"), ("empty", "No league loaded yet"), ("missing", "Unavailable")]:
                page.locator(f'#stateSwitch button[data-state="{state}"]').click()
                page.wait_for_timeout(120)
                text = page.inner_text("#stageLeague") + page.inner_text("#v2LgOppsBody")
                check(f"@{w}: {state} state says so", words in text, text[:120])
                if w == 1280:
                    name = f"{rev}-finder-{w}-{state}.png"
                    page.screenshot(path=str(shots / name), full_page=True)
                    listed.append({"file": name, "route": "finder", "width": w, "height": h, "theme": "light", "state": state, "commit": rev})
            check(f"@{w}: no script errors during interaction", not errors, "; ".join(errors[:3]))
            ctx.close()
        browser.close()
    server.shutdown()
    (shots / "shots.json").write_text(json.dumps({"commit": rev, "shots": listed, "checks": results}, indent=1))
    print(f"{len(results) - len(failures)} of {len(results)} checks pass; {len(listed)} screenshots in {shots}")
    for f in failures:
        print("FAIL", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
