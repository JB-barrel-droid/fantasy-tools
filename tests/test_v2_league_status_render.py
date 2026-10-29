"""Loaded-league status header and collapsed summary, rendered (JEG-1233).

Opens the private component preview (app/v2-concept/league-status.html), which runs app/v2/league-status.js and .css
against the real workspace store in memory, at 1280x900 and 390x844, and checks:

  * every state card renders with its truthful summary line, and no text claims sync, connection or accounts;
  * the disclosure is a real button with aria-expanded/aria-controls; Tab reaches it, Enter and Space fold and open it,
    the one-line summary stays visible while folded, and the edit controls inside stay reachable when open;
  * Escape from a control inside the body folds it and puts focus back on the button;
  * rename and remove update the status without a reload, and the starred team's removal is named;
  * at phone width nothing scrolls sideways, the facts stack in one column and the button is at least 44px tall;
  * a visible focus ring on the button.

Set SAVE_SHOTS=1 to write desktop and phone screenshots to docs/design/shots/league-status-*.png.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import os
import re
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
PAGE = "app/v2-concept/league-status.html"
SHOTS = ROOT / "docs" / "design" / "shots"
BANNED = re.compile(r"\b(sync(ed|s|ing)?|connected|account|every device|cloud)\b", re.I)

EXPECTED = {
    "lsEmpty": "No league loaded yet",
    "lsSaved": "12 teams · 180 players · Your team: Glenview Gridiron · Saved on this device",
    "lsFolded": "12 teams · 180 players · Your team: Waiver Wire Warriors · Saved on this device",
    "lsDup": "4 teams · 60 players · Your team: team smith · Saved on this device",
    "lsRemoved": "11 teams · 165 players · Your team was removed · Saved on this device",
    "lsLoading": "12 teams · 180 players · No team marked · Saved on this device",
    "lsNoSave": "8 teams · 120 players · No team marked · Not saved: this browser isn't keeping data between visits",
    "lsError": "Saved league could not be read",
}


@contextlib.contextmanager
def serve_repo():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    finally:
        httpd.shutdown()


@contextlib.contextmanager
def browser():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as playwright:
        try:
            b = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            yield b
        finally:
            b.close()


def open_preview(b, base, width, height, errors, scheme="light"):
    ctx = b.new_context(viewport={"width": width, "height": height}, color_scheme=scheme)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"[{width}] page error: {e}"))
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    page.goto(base + PAGE + "?shot=1" + ("&theme=dark" if scheme == "dark" else ""), wait_until="load")
    page.wait_for_selector("#lsError")
    return page


def summary(page, id_):
    return page.inner_text(f"#{id_}Summary").strip()


def check_desktop(page, errors):
    for id_, want in EXPECTED.items():
        got = summary(page, id_)
        if got != want:
            errors.append(f"[desktop] {id_} summary {got!r}, want {want!r}")
    partial = page.inner_text("#lsPartial")
    if "2 lines from your last paste could not be matched" not in partial or "1 team has no players yet: Late Adds." not in partial:
        errors.append(f"[desktop] partial paste issues missing: {partial!r}")
    if page.get_attribute("#lsPartial", "data-state") != "partial":
        errors.append("[desktop] partial card is not in the partial state")
    if "Read from your paste this visit" not in partial:
        errors.append("[desktop] partial card does not say the league came from the paste")
    if "2 teams are named" not in page.inner_text("#lsDup"):
        errors.append("[desktop] duplicate names not flagged")
    if "Your team (Glenview Gridiron) was removed" not in page.inner_text("#lsRemoved"):
        errors.append("[desktop] removed starred team not named")
    if "still loading" not in page.inner_text("#lsLoading"):
        errors.append("[desktop] loading note missing")
    body = page.inner_text("main")
    if BANNED.search(body):
        errors.append(f"[desktop] banned claim: {BANNED.search(body).group(0)!r}")

    # Disclosure semantics and keyboard.
    t = "#lsSavedToggle"
    if page.evaluate(f"() => document.querySelector('{t}').tagName") != "BUTTON":
        errors.append("[desktop] toggle is not a button")
    if page.get_attribute(t, "aria-controls") != "lsSavedBody" or page.get_attribute(t, "aria-expanded") != "true":
        errors.append("[desktop] toggle aria-controls/aria-expanded wrong at start")
    if page.get_attribute("#lsFoldedToggle", "aria-expanded") != "false" or page.is_visible("#lsFoldedBody"):
        errors.append("[desktop] folded card is not folded")
    if not page.is_visible("#lsFoldedSummary"):
        errors.append("[desktop] folded card hides its summary")
    page.focus("#lsEmptyToggle")
    for _ in range(6):
        page.keyboard.press("Tab")
        if page.evaluate("() => document.activeElement && document.activeElement.id") == "lsSavedToggle":
            break
    else:
        errors.append("[desktop] Tab never reached the second card's toggle")
    ring = page.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
    if ring in ("none", ""):
        errors.append("[desktop] no visible focus ring on the toggle")
    page.keyboard.press("Enter")
    if page.get_attribute(t, "aria-expanded") != "false" or page.is_visible("#lsSavedBody"):
        errors.append("[desktop] Enter did not fold")
    page.keyboard.press(" ")
    if page.get_attribute(t, "aria-expanded") != "true" or not page.is_visible("#lsSavedBody"):
        errors.append("[desktop] Space did not open")
    # The controls inside are reachable, and Escape there folds and returns focus.
    page.keyboard.press("Tab")
    inside = page.evaluate("() => !!document.activeElement.closest('#lsSavedBody')")
    if not inside:
        errors.append("[desktop] Tab from the open toggle did not reach the controls inside")
    page.keyboard.press("Escape")
    if page.get_attribute(t, "aria-expanded") != "false":
        errors.append("[desktop] Escape inside the body did not fold")
    if page.evaluate("() => document.activeElement.id") != "lsSavedToggle":
        errors.append("[desktop] focus did not return to the toggle after Escape")
    page.click(t)
    # Rename and remove: the status follows the store, no reload.
    page.click("#lsSaved-rename")
    if "Your team: Glenview Gridiron II" not in summary(page, "lsSaved"):
        errors.append(f"[desktop] rename not shown: {summary(page, 'lsSaved')!r}")
    if page.get_attribute(t, "aria-expanded") != "true":
        errors.append("[desktop] a change re-folded or re-opened the card")
    page.click("#lsSaved-remove")
    if "Your team (Glenview Gridiron II) was removed" not in page.inner_text("#lsSaved") or not summary(page, "lsSaved").startswith("11 teams"):
        errors.append(f"[desktop] remove not shown: {summary(page, 'lsSaved')!r}")
    live = page.inner_text("#lsSavedLive")
    if not live.startswith("11 teams"):
        errors.append(f"[desktop] live region did not announce the change: {live!r}")


def check_phone(page, errors):
    over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if over > 0:
        errors.append(f"[phone] page scrolls sideways by {over}px")
    h = page.evaluate("() => document.querySelector('#lsSavedToggle').getBoundingClientRect().height")
    if h < 44:
        errors.append(f"[phone] toggle is {h}px tall, under 44")
    cols = page.evaluate("() => getComputedStyle(document.querySelector('#lsSavedFacts')).gridTemplateColumns.split(' ').length")
    if cols != 1:
        errors.append(f"[phone] facts use {cols} columns, want 1")
    for id_ in ("lsSaved", "lsNoSave", "lsPartial"):
        box = page.evaluate(f"() => {{ const r = document.getElementById('{id_}').getBoundingClientRect(); return [r.left, r.right]; }}")
        if box[0] < 0 or box[1] > 390:
            errors.append(f"[phone] {id_} overflows the viewport: {box}")
    if summary(page, "lsSaved") != EXPECTED["lsSaved"]:
        errors.append("[phone] summary differs from desktop")


class LeagueStatusRenderTest(unittest.TestCase):
    def test_league_status_preview(self):
        errors: list[str] = []
        save = os.environ.get("SAVE_SHOTS", "").strip() not in ("", "0", "false")
        with serve_repo() as base, browser() as b:
            page = open_preview(b, base, 1280, 900, errors)
            if save:
                SHOTS.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(SHOTS / "league-status-1280-light.png"), full_page=True)
            check_desktop(page, errors)
            phone = open_preview(b, base, 390, 844, errors)
            if save:
                phone.screenshot(path=str(SHOTS / "league-status-390-light.png"), full_page=True)
                open_preview(b, base, 390, 844, errors, scheme="dark").screenshot(path=str(SHOTS / "league-status-390-dark.png"), full_page=True)
            check_phone(phone, errors)
        self.assertEqual([], errors, "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
