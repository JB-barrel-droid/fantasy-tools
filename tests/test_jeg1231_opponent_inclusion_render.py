"""JEG-1231: the opponent inclusion control in a real browser, at desktop and phone width.

Opens the private preview (preview/opponent-inclusion/index.html, served from the repo root) and checks keyboard use, focus
that survives a redraw, screen-reader names and counts, the won't-trade distinction, the empty and all-excluded states, and
phone layout. With JEG1231_SHOTS=<dir> it also saves the review screenshots (light and dark, 1280 and 390).
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import os
import socketserver
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
PAGE = "preview/opponent-inclusion/index.html"


@contextlib.contextmanager
def _server():
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


@contextlib.contextmanager
def _browser():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with _server() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            yield browser, base
        finally:
            browser.close()


def _open(browser, base, width, state="league", theme="light"):
    errors = []
    page = browser.new_page(viewport={"width": width, "height": 900 if width > 500 else 844})
    page.on("pageerror", lambda e: errors.append(str(e)))
    # A failed load is reported with its address (the console line alone does not name it).
    page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    page.goto(f"{base}{PAGE}?state={state}&theme={theme}")
    page.wait_for_selector("#pvOi .oi-item")
    return page, errors


FOCUSED = "() => document.activeElement && document.activeElement.dataset.teamId || null"
COUNT = "() => document.getElementById('pvOiCount').textContent"
SEARCH = "() => [...document.querySelectorAll('#pvSearch li')].map(li => li.dataset.teamId)"


class OpponentInclusionRenderTest(unittest.TestCase):
    def test_keyboard_names_counts_and_phone(self):
        with _browser() as (browser, base):
            for width in (1280, 390):
                with self.subTest(width=width):
                    page, errors = _open(browser, base, width)
                    self.assertEqual(page.locator("#pvOi legend").inner_text(), "Opponents to include")
                    self.assertEqual(page.get_attribute("#pvOi", "aria-describedby"), "pvOiCount")
                    self.assertEqual(page.get_attribute("#pvOiCount", "role"), "status")
                    boxes = page.locator("#pvOi input[type=checkbox]")
                    self.assertEqual(boxes.count(), 11, "every other team, never my own")
                    names = page.evaluate("() => [...document.querySelectorAll('#pvOi input')].map(b => b.getAttribute('aria-label'))")
                    self.assertTrue(all(names) and len(set(names)) == len(names), names)
                    labels = page.evaluate("() => [...document.querySelectorAll('#pvOi input')].every(b => document.querySelector(`label[for='${b.id}']`))")
                    self.assertTrue(labels, "each box has a visible label")
                    self.assertEqual(page.locator("#pvOiNone").inner_text(), "Clear")
                    metas = page.evaluate("() => [...document.querySelectorAll('#pvOi .oi-meta')].map(n => n.textContent)")
                    self.assertEqual(len(metas), 11)
                    self.assertTrue(all(m.endswith((" player", " players")) for m in metas), metas)
                    self.assertIn("0 players", metas, "a team with no roster says so")
                    described = page.evaluate("() => [...document.querySelectorAll('#pvOi input')].map(b => (b.getAttribute('aria-describedby') || '').split(' ').map(id => document.getElementById(id) && document.getElementById(id).textContent).join(' | '))")
                    self.assertTrue(all(d.endswith((" player", " players")) or " | " in d for d in described), described)
                    self.assertTrue(all(d.split(" | ")[0].endswith((" player", " players")) for d in described), "every box's description starts with its player count")
                    self.assertIn("Searching 8 of 11 opponents. 2 left out here.", page.evaluate(COUNT))
                    self.assertIn("1 included has no roster yet.", page.evaluate(COUNT))
                    before = page.evaluate(SEARCH)
                    # Keyboard: Tab from the last preview control reaches Select all, Clear, then the first box.
                    page.focus("#pvTheme")
                    page.keyboard.press("Tab")
                    self.assertEqual(page.evaluate("() => document.activeElement.id"), "pvOiAll")
                    page.keyboard.press("Tab")
                    page.keyboard.press("Tab")
                    first = page.evaluate(FOCUSED)
                    self.assertIsNotNone(first)
                    self.assertTrue(page.is_checked(f"#pvOi input[data-team-id='{first}']"))
                    page.keyboard.press("Space")
                    self.assertFalse(page.is_checked(f"#pvOi input[data-team-id='{first}']"))
                    self.assertEqual(page.evaluate(FOCUSED), first, "focus stays on the box after the redraw")
                    self.assertIn("Searching 7 of 11", page.evaluate(COUNT))
                    self.assertNotIn(first, page.evaluate(SEARCH), "a left-out team is not searched")
                    page.keyboard.press("Space")
                    self.assertEqual(page.evaluate(SEARCH), before)
                    # Rename keeps the choice (team 3 starts left out); remove and re-add arrives included with a new id.
                    third = page.evaluate("() => window.__pv.ws.teams[2].id")
                    page.click("#pvRename")
                    self.assertFalse(page.is_checked(f"#pvOi input[data-team-id='{third}']"))
                    self.assertIn("(renamed)", page.get_attribute(f"#pvOi input[data-team-id='{third}']", "aria-label"))
                    fourth = page.evaluate("() => window.__pv.ws.teams[3].id")
                    page.click("#pvReadd")
                    self.assertEqual(page.locator(f"#pvOi input[data-team-id='{fourth}']").count(), 0)
                    newest = page.evaluate("() => window.__pv.ws.teams.at(-1).id")
                    self.assertTrue(page.is_checked(f"#pvOi input[data-team-id='{newest}']"))
                    # Clear (Fieldnotes: Clear means none) from the keyboard: the all-excluded state, nothing searched.
                    page.focus("#pvOiNone")
                    page.keyboard.press("Enter")
                    self.assertEqual(page.get_attribute("#pvOi", "data-status"), "allExcluded")
                    self.assertTrue(page.evaluate(COUNT).startswith("No opponents are included"))
                    self.assertEqual(page.evaluate(SEARCH), [])
                    self.assertEqual(page.evaluate("() => document.activeElement.id"), "pvOiNone", "the pressed button keeps focus")
                    page.keyboard.press("Shift+Tab")
                    page.keyboard.press("Enter")
                    self.assertEqual(page.get_attribute("#pvOi", "data-status"), "ok")
                    self.assertEqual(page.locator("#pvOi input:checked").count(), 11)
                    # Layout: 44px targets and no sideways scroll on a phone.
                    heights = page.evaluate("() => [...document.querySelectorAll('#pvOi .oi-label, #pvOi .oi-btn')].map(n => n.getBoundingClientRect().height)")
                    self.assertTrue(min(heights) >= 44, heights)
                    if width == 390:
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
                        cols = page.evaluate("() => new Set([...document.querySelectorAll('#pvOi .oi-item')].map(li => Math.round(li.getBoundingClientRect().left))).size")
                        self.assertEqual(cols, 1, "one column on a phone")
                    self.assertEqual(errors, [])
                    page.close()

    def test_profile_duplicates_and_empty(self):
        with _browser() as (browser, base):
            page, errors = _open(browser, base, 390, "profile")
            locked = page.locator("#pvOi .oi-item[data-state='profile'] input")
            self.assertEqual(locked.count(), 1)
            self.assertEqual(locked.get_attribute("aria-disabled"), "true")
            described = locked.get_attribute("aria-describedby").split()
            self.assertEqual(len(described), 2, "the count, then why it is locked")
            self.assertIn("players", page.evaluate("(id) => document.getElementById(id).textContent", described[0]))
            note = page.evaluate("(id) => document.getElementById(id).textContent", described[1])
            self.assertIn("won't trade in Managers", note)
            locked.focus()
            page.keyboard.press("Space")
            self.assertFalse(locked.is_checked(), "a won't-trade manager cannot be ticked here")
            locked.click(force=True)
            self.assertFalse(locked.is_checked())
            page.click("#pvOiAll")
            self.assertFalse(locked.is_checked(), "Select all leaves a won't-trade manager out")
            self.assertIn("1 marked won't trade in Managers.", page.evaluate(COUNT))
            page.select_option("#pvState", "duplicates")
            dup = page.evaluate("() => [...document.querySelectorAll('#pvOi input')].map(b => b.getAttribute('aria-label')).filter(n => n.startsWith('Sunday Scaries'))")
            self.assertEqual(dup, ["Sunday Scaries · team 3", "Sunday Scaries · team 6"])
            page.locator("#pvOi input[aria-label='Sunday Scaries · team 6']").uncheck()
            self.assertTrue(page.is_checked("#pvOi input[aria-label='Sunday Scaries · team 3']"), "two teams with one name stay apart")
            page.select_option("#pvState", "none")
            self.assertEqual(page.get_attribute("#pvOi", "data-status"), "none")
            self.assertTrue(page.locator("#pvOiList").is_hidden())
            self.assertEqual(page.evaluate(COUNT), "Add another team to choose which opponents to search.")
            self.assertEqual(errors, [])
            page.close()

    def test_review_screenshots(self):
        out = os.environ.get("JEG1231_SHOTS")
        if not out:
            raise unittest.SkipTest("set JEG1231_SHOTS=<dir> to save the review screenshots")
        Path(out).mkdir(parents=True, exist_ok=True)
        with _browser() as (browser, base):
            for state in ("league", "profile", "allExcluded"):
                for theme in ("light", "dark"):
                    for width in (1280, 390):
                        page, _ = _open(browser, base, width, state, theme)
                        page.evaluate("document.documentElement.classList.add('is-shot')")
                        page.screenshot(path=str(Path(out) / f"opponent-inclusion-{state}-{width}-{theme}.png"), full_page=True)
                        page.close()


if __name__ == "__main__":
    unittest.main()
