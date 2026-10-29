#!/usr/bin/env python3
"""Browser checks and screenshots for the JEG-1209 Fieldnotes revision 3 private preview.

  python3 preview/jeg-1209-fieldnotes/checks.py [--shots DIR]

Serves the repo root on 127.0.0.1, opens preview/jeg-1209-fieldnotes/index.html in Chromium (Playwright) and checks, at
1280x900, 768x1024, 390x844 and 320x700: no sideways page scroll, no script error, no request leaving 127.0.0.1, controls
at least 44px tall; the Managers card has no free text input and every manager starts at the default profile (Jeremy,
2026-10-29); the revision2.html routes load without errors. Then, keyboard only: the table and phone cards draw the fixed column order, value first, with no order picker; details open with focus on
their heading and Escape returns focus to the row's button; Clear and Select all in Opponents to include; a preference
change marks the results out of date; each review state (loading, no league, projections missing) says so. JEG-1250: with live keys
(ddf.v2.workspaces, ddf.v2.managerProfiles) seeded, using the preview leaves them byte-for-byte unchanged; a left-out
opponent and a ticked manager box survive reload, No league and back, and reload in No league; Also show and Reset
preview write their final text into one stable live region and keep focus; a note saved before the checkboxes keeps
its exact text through box changes and reloads, even when it starts with a box label or is only one. Screenshots
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
R2_ROUTES = ["home", "paste", "compare", "targets", "settings", "more", "review", "values", "chatbot", "guides", "rosters"]
# Anything a reader could type into. Checkboxes, radios, file pickers, buttons and selects are choices. Checked inside the
# Managers card only: "I just didn't want text boxes for how my leaguemates trade" (Jeremy, 2026-10-29).
FIXED = ["us", "usProj", "ourRoster", "them", "themProj", "theirRoster"]
LIVE_KEYS = ["ddf.v2.workspaces", "ddf.v2.managerProfiles"]
PREVIEW_KEYS = ["ddf.preview.jeg1209.workspaces", "ddf.preview.jeg1209.managerProfiles", "ddf.preview.jeg1209.managerTags"]
LEGACY_NOTES = ["Likes rookies; answers on weekends", "Likes rookies", "Win-now; Rebuilding; prefers WR depth"]
FREE_TEXT = ("input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=hidden]):not([type=range])"
             ":not([type=button]):not([type=submit]):not([type=reset]), textarea, [contenteditable]:not([contenteditable=false])")


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
                wide = "" if overflow <= 0 else page.evaluate("""(() => { const vw = document.documentElement.clientWidth;
                  return [...document.querySelectorAll('body *')].filter(e => e.offsetParent && e.getBoundingClientRect().right > vw + 1)
                    .slice(0, 4).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '')).join(' ') })()""")
                check(f"{route}@{w}: no sideways scroll", overflow <= 0, f"overflow {overflow}px {wide}")
                check(f"{route}@{w}: no script errors", not errors, "; ".join(errors[:3]))
                check(f"{route}@{w}: no external requests", not external, ", ".join(external[:3]))
                if route == "finder":
                    free = page.evaluate("s => [...document.querySelectorAll('#v2LgManagers ' + s.split(', ').join(', #v2LgManagers '))].map(e => e.tagName.toLowerCase() + '#' + e.id)", FREE_TEXT)
                    check(f"finder@{w}: Managers card has no free text inputs", not free, ", ".join(free[:5]))
                    teams = page.evaluate("document.querySelectorAll('#v2LgManagers .v2-mg-team').length")
                    off = page.evaluate("""[...document.querySelectorAll('#v2LgManagers select')].filter(s => s.value !== 'unknown').map(s => s.id)
                      .concat([...document.querySelectorAll('#v2LgManagers input[type=checkbox]')].filter(b => b.checked).map(b => b.id))""")
                    check(f"finder@{w}: every manager starts at the default profile", teams > 0 and not off, f"{teams} managers; not default: {', '.join(off[:5])}")
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

        # The revision-2 routes the page links to.
        r2 = base.replace("index.html", "revision2.html")
        for w, h in [(1280, 900), (390, 844)]:
            for route in R2_ROUTES:
                ctx, page, errors, external = page_at(w, h)
                page.goto(f"{r2}?shot=1#{route}")
                page.wait_for_timeout(300)
                check(f"revision2 {route}@{w}: no script errors", not errors, "; ".join(errors[:3]))
                check(f"revision2 {route}@{w}: no external requests", not external, ", ".join(external[:3]))
                ctx.close()
        ctx, page, errors, _ = page_at(1280, 900)
        page.goto(f"{r2}?shot=1#finder")
        page.wait_for_timeout(400)
        check("revision2 Find a trade opens the revision-3 page", page.url.split("?")[0].endswith("/index.html#finder") or page.url.endswith("index.html#finder"), page.url)
        ctx.close()

        # Keyboard and disclosure, desktop then phone.
        for w, h in [(1280, 900), (390, 844)]:
            ctx, page, errors, _ = page_at(w, h)
            page.goto(f"{base}?shot=1#finder")
            page.wait_for_timeout(400)
            # Columns: one fixed order, value first (Jeremy, 2026-10-29, JEG-1232), and no order picker.
            heads = page.evaluate("[...document.querySelectorAll('.finder-table thead th')].map(t => t.dataset.col || 'trade')")
            cards = page.evaluate("[...document.querySelector('.finder-result .finder-mobile-metrics').children].map(d => d.dataset.col)")
            check(f"@{w}: table and cards draw the fixed order, value first", heads[1:] == FIXED and cards == FIXED, f"{heads} {cards}")
            check(f"@{w}: no column order picker", page.evaluate("!document.querySelector('[data-move], #colOrder')"))
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
        # JEG-1250: preview-only storage. Seed the live keys first, then use the preview: they must not change.
        ctx, page, errors, _ = page_at(1280, 900)
        page.goto(base.replace("index.html", "README.md"))
        real = page.evaluate("""() => {
          const ws = JSON.stringify({kind: "ddf.workspaces", v: 1, note: "a saved real league", teams: [{id: "real-1", name: "Real team"}]});
          const mp = JSON.stringify({v: 1, leagues: {"real-league": {"real-1": {teamId: "real-1", note: "real note"}}}});
          localStorage.setItem("ddf.v2.workspaces", ws); localStorage.setItem("ddf.v2.managerProfiles", mp);
          return {ws, mp, keys: Object.keys(localStorage).sort()}; }""")
        page.goto(f"{base}?shot=1#finder")
        page.wait_for_timeout(400)
        first_opp = page.evaluate("document.querySelector('#oiFinder input[type=checkbox]:not([disabled])').id")
        page.locator(f"#{first_opp}").focus()
        page.keyboard.press("Space")
        team = page.evaluate("document.querySelector('#v2LgManagers .v2-mg-team').dataset.teamId")
        page.evaluate("id => document.querySelector(`#v2LgManagers .v2-mg-team[data-team-id=\"${id}\"] .v2-mg-tags input`).click()", team)
        anchor = page.evaluate("id => document.querySelector(`#v2LgManagers .v2-mg-team[data-team-id=\"${id}\"] select`).id", team)
        page.evaluate("id => { const s = document.getElementById(id); s.value = 'some'; s.dispatchEvent(new Event('change', {bubbles: true})); }", anchor)
        page.wait_for_timeout(1300)   # both stores save 1 second after a change
        page.reload()
        page.wait_for_timeout(500)
        after = page.evaluate("""() => ({ws: localStorage.getItem("ddf.v2.workspaces"), mp: localStorage.getItem("ddf.v2.managerProfiles"),
          keys: Object.keys(localStorage).filter(k => !k.startsWith("ddf.preview.jeg1209.") && k !== "jeg1209-private-state").sort()})""")
        check("storage: live league key unchanged after using the preview", after["ws"] == real["ws"], str(after["ws"])[:80])
        check("storage: live manager profiles key unchanged", after["mp"] == real["mp"], str(after["mp"])[:80])
        check("storage: no other non-preview key added or removed", after["keys"] == real["keys"], f"{real['keys']} -> {after['keys']}")
        check("storage: preview keys hold the preview's own state", page.evaluate("ks => ks.every(k => localStorage.getItem(k))", PREVIEW_KEYS))
        check("persistence: an opponent left out stays left out after reload", page.evaluate("id => !document.getElementById(id).checked", first_opp))
        check("persistence: a ticked manager box stays ticked after reload",
              page.evaluate("id => document.querySelector(`#v2LgManagers .v2-mg-team[data-team-id=\"${id}\"] .v2-mg-tags input`).checked", team))
        check("persistence: a manager's anchor choice stays after reload", page.evaluate("id => document.getElementById(id).value === 'some'", anchor))
        # No league, then Loaded: the saved filter carries through; reloading in No league keeps it too.
        page.locator('#stateSwitch button[data-state="empty"]').click()
        page.wait_for_timeout(100)
        check("empty state: no league shown", "No league loaded yet" in page.inner_text("#v2LgOppsBody"))
        page.wait_for_timeout(1300)
        page.reload()
        page.wait_for_timeout(500)
        check("empty then reload: sample teams back, filter kept", page.evaluate("id => document.getElementById(id) && !document.getElementById(id).checked", first_opp))
        page.locator('#stateSwitch button[data-state="empty"]').click()
        page.locator('#stateSwitch button[data-state="normal"]').click()
        page.wait_for_timeout(100)
        check("empty then loaded: filter kept", page.evaluate("id => !document.getElementById(id).checked", first_opp))
        # Announcements: one stable region; focus stays on the control pressed.
        page.evaluate("window.__live = document.getElementById('previewLive')")
        page.locator('#columnHost input[data-optional="package"]').focus()
        page.keyboard.press("Space")
        page.wait_for_timeout(80)
        check("announce: Also show keeps the same live region and its text",
              page.evaluate("Boolean(window.__live) && document.getElementById('previewLive') === window.__live && window.__live.textContent === 'Package capture column shown.'"),
              page.evaluate("(document.getElementById('previewLive') || {}).textContent"))
        check("announce: focus stays on the Also show box", page.evaluate("document.activeElement.dataset.optional === 'package'"))
        has_reset = page.locator("#resetPreview").count() == 1
        check("reset: Reset preview exists", has_reset)
        if has_reset:
            page.locator("#resetPreview").focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(120)
        check("reset: same live region, final text says what was reset",
              page.evaluate("Boolean(window.__live) && document.getElementById('previewLive') === window.__live && window.__live.textContent.startsWith('Preview reset')"),
              page.evaluate("(document.getElementById('previewLive') || {}).textContent"))
        check("reset: focus stays on Reset preview", page.evaluate("document.activeElement.id === 'resetPreview'"))
        check("reset: every opponent included and every manager at the default",
              page.evaluate("[...document.querySelectorAll('#oiFinder input[type=checkbox]:not([disabled])')].every(b => b.checked) && ![...document.querySelectorAll('#v2LgManagers input[type=checkbox]')].some(b => b.checked) && [...document.querySelectorAll('#v2LgManagers select')].every(s => s.value === 'unknown')"))
        page.wait_for_timeout(1300)
        check("reset: live keys still unchanged",
              page.evaluate("r => localStorage.getItem('ddf.v2.workspaces') === r.ws && localStorage.getItem('ddf.v2.managerProfiles') === r.mp", real))
        check("storage checks: no script errors", not errors, "; ".join(errors[:3]))
        ctx.close()

        # JEG-1250: a note saved before the checkboxes is never changed or read as ticks, even when it starts with a
        # box label or is only a label. One legacy note per manager.
        ctx, page, errors, _ = page_at(390, 844)
        page.goto(f"{base}?shot=1#finder")
        page.wait_for_timeout(400)
        teams = page.evaluate("[...document.querySelectorAll('#v2LgManagers .v2-mg-team')].map(t => t.dataset.teamId)")
        cases = list(zip(teams, LEGACY_NOTES))
        page.evaluate("""cases => { const M = TradeValueManagerProfiles, W = TradeValueWorkspace;
          cases.forEach(([id, note]) => M.store.update(b => M.ops.setNote(b, W.store.get(), id, note), "test")); M.store.flush(); }""", cases)
        page.reload()
        page.wait_for_timeout(500)
        note = "id => TradeValueManagerProfiles.get(TradeValueManagerProfiles.store.get(), TradeValueWorkspace.store.get(), id).note"
        box = "([id, i]) => { const b = document.querySelectorAll(`#v2LgManagers .v2-mg-team[data-team-id=\"${id}\"] .v2-mg-tags input`)[i]; if (b) b.click(); }"
        ticked = "id => [...document.querySelectorAll(`#v2LgManagers .v2-mg-team[data-team-id=\"${id}\"] .v2-mg-tags input`)].map(b => b.checked)"
        for team, legacy in cases:
            label = f"legacy note {legacy!r}"
            check(f"{label}: no box starts ticked", not any(page.evaluate(ticked, team)), str(page.evaluate(ticked, team)))
            check(f"{label}: shown as written", page.evaluate("([id, n]) => (document.querySelector(`#v2LgManagers .v2-mg-team[data-team-id=\"${id}\"] [data-kept-note]`) || {}).textContent === `Earlier note, kept as written: ${n}`", [team, legacy]))
            for i in (0, 2, 0):   # tick Likes rookies and Win-now, then untick Likes rookies
                page.evaluate(box, [team, i])
            got = page.evaluate(note, team)
            check(f"{label}: unchanged after ticking and unticking", got == legacy, got)
        page.wait_for_timeout(1300)
        page.reload()
        page.wait_for_timeout(500)
        for team, legacy in cases:
            label = f"legacy note {legacy!r}"
            check(f"{label}: after reload, note unchanged and only Win-now ticked",
                  page.evaluate(note, team) == legacy and page.evaluate(ticked, team) == [False, False, True, False, False, False],
                  f"{page.evaluate(note, team)!r} {page.evaluate(ticked, team)}")
        check("legacy note checks: no script errors", not errors, "; ".join(errors[:3]))
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
