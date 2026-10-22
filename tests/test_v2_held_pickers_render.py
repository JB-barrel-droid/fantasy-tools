"""JEG-906 / JEG-914: a held (red, hidden) source is never offered as a series whose numbers read as current.

One predicate decides held everywhere (v2.js `heldReason` / `unavailableReason`, JEG-807): the engine marks a red
hold `available: false` with an excludedReason starting "held". An amber (lagging) hold stays available and is
only labelled, so it is not covered here.

  H1  Risers & fallers: the held source's Movement option is disabled with the held reason; a change event that
      picks it (the way a script or stale saved pick would) leaves the page on an offered series with no deltas
      built on held values; the note names the held source as not offered.
  H2  Compare "Player values shown": the held option is disabled; a change event that picks it leaves the picker
      on the series whose numbers the side totals carry (the totals label names the picked series).

Discrimination: each guard is run against v2.js with the held rule removed and must fail.
The fixture is pinned (tests/_holds.py): CBS is the held source.
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
from tests import _render_env  # noqa: E402
from tests._holds import PINNED_HELD, pin_holds_in_dist  # noqa: E402

V2_JS = ROOT / "app" / "v2" / "v2.js"
HELD = PINNED_HELD[0]
OPTIONS = "(id) => [...document.querySelectorAll(`#${id} option`)].map(o => ({value: o.value, disabled: o.disabled, text: o.textContent}))"
PICK = "([id, key]) => { const s = document.getElementById(id); s.value = key; s.dispatchEvent(new Event('change', {bubbles: true})); }"
SETTLED = "() => !/Recomputing|Reading/.test(document.getElementById('v2RMeta').textContent)"


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        build_v2_page.build(dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        class Server(socketserver.ThreadingTCPServer):
            request_queue_size = 128

        with Server(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def _open(browser, base, route, js=None):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    if js is not None:
        page.route("**/v2/v2.js*", lambda route_: route_.fulfill(status=200, content_type="text/javascript", body=js))
    page.goto(base + route, wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=40000)
    page.wait_for_timeout(600)
    return page


def _held_item(page):
    return page.evaluate("(key) => window.TradeValueV2.view().infoByKey[key]", HELD)


def check_h1_risers(page):
    errors = []
    page.wait_for_function(SETTLED, timeout=30000)
    item = _held_item(page)
    if not item or item.get("available") or not str(item.get("excludedReason") or "").lower().startswith("held"):
        return [f"H1 premise: {HELD} is not a held source in the pinned fixture: {item}"]
    options = {o["value"]: o for o in page.evaluate(OPTIONS, "v2RSeries")}
    held = options.get(HELD)
    if not held:
        errors.append(f"H1: the held source {HELD} is missing from the Movement picker (it should be listed, disabled)")
    elif not held["disabled"] or "held" not in held["text"]:
        errors.append(f"H1: the held source is offered as a Movement series: {held}")
    page.evaluate(PICK, ["v2RSeries", HELD])
    page.wait_for_function(SETTLED, timeout=30000)
    picked = page.evaluate("() => document.getElementById('v2RSeries').value")
    movers = page.evaluate("() => window.TradeValueV2.risers()")
    if picked == HELD or (movers and movers.get("series") == HELD):
        errors.append(f"H1: a change event picked the held source (select {picked!r}, movers series {movers and movers.get('series')!r})")
    if movers and movers.get("series") == HELD and (movers.get("risers") or movers.get("fallers")):
        errors.append("H1: deltas were built on the held source's values")
    note = page.text_content("#v2RNote") or ""
    if "Not offered" not in note or "held" not in note:
        errors.append(f"H1: the note does not say the held source is not offered: {note!r}")
    if page.errors:
        errors.append(f"H1 page errors: {page.errors[:2]}")
    return errors


def check_h2_compare(page):
    errors = []
    page.wait_for_selector("#v2CShown option", state="attached")
    item = _held_item(page)
    if not item or item.get("available"):
        return [f"H2 premise: {HELD} is not held: {item}"]
    options = {o["value"]: o for o in page.evaluate(OPTIONS, "v2CShown")}
    held = options.get(HELD)
    if held is None:
        errors.append(f"H2: the held source {HELD} is not listed in Player values shown (it should be listed, disabled)")
    elif not held["disabled"] or "held" not in held["text"]:
        errors.append(f"H2: the held source is selectable in Player values shown: {held}")
    before = page.evaluate("() => document.getElementById('v2CShown').value")
    page.evaluate(PICK, ["v2CShown", HELD])
    page.wait_for_timeout(400)
    after = page.evaluate("() => document.getElementById('v2CShown').value")
    shown = page.evaluate("() => window.TradeValueV2.tradeState.shown")
    total = page.text_content("#v2GiveTotal") or ""
    if after == HELD or shown == HELD:
        errors.append(f"H2: the picker accepted the held source (select {after!r}, state {shown!r})")
    if after != before:
        errors.append(f"H2: the picker moved from {before!r} to {after!r} on a held pick")
    label = page.evaluate("(key) => document.querySelector(`#v2CShown option[value='${key}']`).textContent", after)
    name = label.split(" ", 1)[1].split(" —")[0].split(" ·")[0].strip()
    if name.split(" ")[0] not in total:
        errors.append(f"H2: the side total {total!r} does not name the picked series {name!r}")
    if page.errors:
        errors.append(f"H2 page errors: {page.errors[:2]}")
    return errors


class HeldPickersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise _render_env.unavailable("playwright is not installed")
        exe = _render_env.chromium_executable()
        if exe is None and not _render_env.required():
            raise _render_env.unavailable("no browser")
        cls._stack = contextlib.ExitStack()
        cls.base = cls._stack.enter_context(_served())
        cls.pw = cls._stack.enter_context(sync_playwright())
        cls.browser = cls.pw.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        cls.js = V2_JS.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._stack.close()

    def run_check(self, check, route, js=None):
        page = _open(self.browser, self.base, route, js)
        try:
            return check(page)
        except Exception as error:   # a control the check needs is missing: a failure, not a pass
            return [f"{check.__name__} raised {type(error).__name__}: {str(error).splitlines()[0][:160]}"]
        finally:
            page.close()

    def assertCaught(self, check, route, js, label):
        # A guard catches the bug only through a finding; a check that raised (a timeout, a missing control) is not a catch.
        errors = self.run_check(check, route, js)
        self.assertTrue(errors and not any(e.startswith(check.__name__) for e in errors), f"the guard did not catch: {label} ({errors})")

    def mutate(self, old, new):
        self.assertEqual(self.js.count(old), 1, f"stale mutation anchor: {old[:60]!r}")
        return self.js.replace(old, new)

    def test_h1_risers_never_offers_a_held_source(self):
        self.assertEqual(self.run_check(check_h1_risers, "#risers-fallers"), [])

    def test_h1_guard_catches_a_held_series_offered(self):
        # The old build: Risers read the engine's prior week for every series, held or not.
        js = self.mutate("const prior = item && !item.available ? {available: false, reason: unavailableReason(item)} : priorCache.get(key);",
                         "const prior = priorCache.get(key);")
        self.assertCaught(check_h1_risers, "#risers-fallers", js, "Risers offers a held source")

    def test_h2_compare_never_accepts_a_held_source(self):
        self.assertEqual(self.run_check(check_h2_compare, "#compare-trade"), [])

    def test_h2_guard_catches_a_held_pick_accepted(self):
        # The held option enabled, and the change handler applying whatever arrives.
        js = self.mutate(".concat(compareView.unavailable.map(key => ({key, reason: unavailableReason(view.infoByKey[key])})));",
                         ".concat(compareView.unavailable.map(key => ({key, reason: null})));")
        js = js.replace("if (compareView && !compareView.shownChoices.includes(picked)) { renderShownPicker(); return; }", "")
        self.assertCaught(check_h2_compare, "#compare-trade", js, "Compare accepts a held source")


if __name__ == "__main__":
    unittest.main()
