"""JEG-1271: the isolated Compare evidence view in a real browser at 320, 390 and 1280 px.

Serves the repository root, opens tests/fixtures/compare_evidence_view/preview.html (every synthetic case,
deep-frozen, each with a mock readout in the opaque slot) and requires, at each width:

- no page errors and no horizontal page overflow, and no element of the view wider than its card
  (long-names case included);
- every case renders its synthetic label, verdict text, nets and one row per supplied series, with the
  rendered value text equal to the supplied number in the v2.js format (re-read from the input in the page);
- disclosures work from the keyboard: Tab reaches the toggle, Enter and Space open and close it, aria-expanded
  and the panel's hidden state follow, and focus stays on the toggle;
- update() with the same or a changed input keeps open disclosures open, keeps focus on the same toggle, and
  keeps the readout slot's node and content (the slot is never rebuilt or read);
- update() keeps focus on a control inside the readout slot (JEG-1294);
- the evidence groups stack at 320 and 390 and sit side by side at 1280 (the 900 px pick);
- the frozen input is unchanged after all of the above.
Set CEV_SCREENSHOT_DIR to save a full-page screenshot per width.
Discrimination: test_guard_fails_on_broken_builds serves broken copies of the module and stylesheet and
requires the checks to fail.
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
JS = ROOT / "app" / "v2" / "compare-evidence-view.js"
CSS = ROOT / "app" / "v2" / "compare-evidence-view.css"
PREVIEW = "tests/fixtures/compare_evidence_view/preview.html"
WIDTHS = (320, 390, 1280)

READ = r"""() => {
  const P = window.__cevPreview, V = window.CompareEvidenceView;
  const out = {problems: [], before: JSON.stringify(P.cases.map(c => c.input))};
  const bad = m => out.problems.push(m);
  const doc = document.documentElement;
  if (doc.scrollWidth > doc.clientWidth + 1) bad(`page scrolls sideways: ${doc.scrollWidth} > ${doc.clientWidth}`);
  P.cases.forEach(c => {
    const root = document.querySelector(`[data-case="${c.id}"] .cev`);
    if (!root) { bad(`${c.id}: not rendered`); return; }
    const box = root.getBoundingClientRect();
    root.querySelectorAll("*").forEach(el => {
      if (!el.closest('[data-cev-slot="readout"]') && el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).display !== "inline")
        bad(`${c.id}: ${el.className || el.tagName} content is wider than its box (${el.scrollWidth} > ${el.clientWidth})`);
      const r = el.getBoundingClientRect();
      if (r.width && (r.right > box.right + 1 || r.left < box.left - 1)) bad(`${c.id}: ${el.className || el.tagName} overflows its card (${Math.round(r.left)}..${Math.round(r.right)} vs ${Math.round(box.left)}..${Math.round(box.right)})`);
    });
    const t = sel => (root.querySelector(sel) || {}).textContent;
    if (t(".cev-synthetic") !== c.input.syntheticLabel) bad(`${c.id}: synthetic label missing`);
    if (t(".cev-verdict-text") !== c.input.verdict.text) bad(`${c.id}: verdict text changed`);
    c.input.groups.forEach(g => g.rows.forEach(r => {
      const li = root.querySelector(`[data-group="${g.id}"] [data-series="${r.key}"]`);
      if (!li) { bad(`${c.id}: ${r.key} missing from ${g.id}`); return; }
      const want = r.held ? c.input.copy.held : r.net === null ? c.input.copy.missingValue : V.format.gap(r.net);
      if (li.querySelector(".cev-row-value").textContent !== want) bad(`${c.id}: ${r.key} shows ${li.querySelector(".cev-row-value").textContent}, want ${want}`);
      if (li.querySelector(".cev-row-name").textContent !== r.label) bad(`${c.id}: ${r.key} label changed`);
    }));
    const slot = root.querySelector('[data-cev-slot="readout"] [data-mock-readout]');
    if (!slot || slot.dataset.mockReadout !== c.id) bad(`${c.id}: readout slot content missing`);
    const toggles = root.querySelectorAll(".cev-disclosure-toggle");
    if (toggles.length !== c.input.disclosures.length) bad(`${c.id}: ${toggles.length} disclosures for ${c.input.disclosures.length}`);
    toggles.forEach(b => {
      const h = b.getBoundingClientRect().height;
      if (h < 44) bad(`${c.id}: disclosure toggle is ${h}px tall`);
    });
  });
  return out;
}"""

STATE = r"""id => {
  const root = document.querySelector(`[data-case="${id}"] .cev`);
  const b = root.querySelector('.cev-disclosure-toggle');
  const panel = document.getElementById(b.getAttribute('aria-controls'));
  return {expanded: b.getAttribute('aria-expanded'), hidden: panel.hidden, focused: document.activeElement === b,
    focusId: document.activeElement && document.activeElement.getAttribute('data-cev-focus')};
}"""

SLOT_FOCUS = r"""([id, changed]) => {
  const P = window.__cevPreview;
  const c = P.cases.find(x => x.id === id);
  const other = P.cases.find(x => x.id !== id);
  const control = document.querySelector(`[data-case="${id}"] [data-mock-control="${id}"]`);
  control.focus();
  const before = document.activeElement === control;
  P.handles[id].update(changed ? other.input : c.input);
  const after = document.activeElement === control;
  P.handles[id].update(c.input);
  return {before, after, active: document.activeElement && document.activeElement.tagName};
}"""

LAYOUT = r"""id => {
  const boxes = [...document.querySelectorAll(`[data-case="${id}"] .cev-group`)].map(g => g.getBoundingClientRect());
  return {sideBySide: boxes.length > 1 && boxes.every(b => Math.abs(b.top - boxes[0].top) < 1) && boxes[1].left > boxes[0].right - 1,
    stacked: boxes.length > 1 && boxes.every((b, i) => !i || b.top >= boxes[i - 1].bottom - 1)};
}"""

UPDATE = r"""([id, changed]) => {
  const P = window.__cevPreview;
  const c = P.cases.find(x => x.id === id);
  const h = P.handles[id];
  const slotBefore = h.readoutSlot;
  const mockBefore = slotBefore.firstChild;
  const other = P.cases.find(x => x.id !== id);
  h.update(changed ? other.input : c.input);
  const root = document.querySelector(`[data-case="${id}"] .cev`);
  const slotNow = root.querySelector('[data-cev-slot="readout"]');
  const b = root.querySelector('.cev-disclosure-toggle');
  const out = {sameSlot: slotNow === slotBefore && slotNow.firstChild === mockBefore && mockBefore.dataset.mockReadout === id,
    expanded: b.getAttribute('aria-expanded'), focused: document.activeElement === b,
    verdict: root.querySelector('.cev-verdict-text').textContent, want: (changed ? other : c).input.verdict.text};
  h.update(c.input);
  return out;
}"""


@contextlib.contextmanager
def _served(overrides=None):
    overrides = overrides or {}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in overrides:
                body = overrides[path].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/css" if path.endswith(".css") else "text/javascript")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    handler = functools.partial(Handler, directory=str(ROOT))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


def run_checks(js_patch=None, css_patch=None, shots=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    overrides = {}
    for url, path, patch in (("/app/v2/compare-evidence-view.js", JS, js_patch), ("/app/v2/compare-evidence-view.css", CSS, css_patch)):
        if patch:
            text = path.read_text(encoding="utf-8")
            assert patch[0] in text, f"patch anchor missing: {patch[0]!r}"
            overrides[url] = text.replace(patch[0], patch[1], 1)
    problems: list[str] = []
    with _served(overrides) as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                page.goto(base + PREVIEW, wait_until="networkidle")
                page.wait_for_function("() => window.__cevPreview && (window.__cevPreview.ready || window.__cevPreview.error)", timeout=30000)
                tag = f"[{width}px]"
                err = page.evaluate("() => window.__cevPreview.error || null")
                if err:
                    problems.append(f"{tag} preview failed: {err}")
                    page.close()
                    continue
                snap = page.evaluate(READ)
                problems += [f"{tag} {p}" for p in snap["problems"]]
                if shots:
                    Path(shots).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(shots) / f"compare-evidence-view-{width}.png"), full_page=True)
                case = page.evaluate("() => window.__cevPreview.cases[0].id")
                toggle = page.locator(f'[data-case="{case}"] .cev-disclosure-toggle').first
                # Keyboard: Tab from the element before the toggle reaches it; Enter opens, Space closes, Enter reopens.
                page.evaluate("""id => { const b = document.querySelector(`[data-case="${id}"] .cev-disclosure-toggle`);
                  const all = [...document.querySelectorAll('button, a[href], [tabindex]')]; const i = all.indexOf(b);
                  if (i > 0) all[i - 1].focus(); else document.body.focus(); }""", case)
                page.keyboard.press("Tab")
                start = page.evaluate(STATE, case)
                if not start["focused"]:
                    problems.append(f"{tag} Tab did not reach the first disclosure toggle")
                toggle.focus()
                for key, want in (("Enter", "true"), ("Space", "false"), ("Enter", "true")):
                    page.keyboard.press(key)
                    st = page.evaluate(STATE, case)
                    if st["expanded"] != want or st["hidden"] != (want == "false") or not st["focused"]:
                        problems.append(f"{tag} after {key}: {st}, want expanded={want} and focus kept")
                for changed in (False, True):
                    up = page.evaluate(UPDATE, [case, changed])
                    if not up["sameSlot"]:
                        problems.append(f"{tag} update(changed={changed}) rebuilt or lost the readout slot")
                    if up["expanded"] != "true" or not up["focused"]:
                        problems.append(f"{tag} update(changed={changed}) lost the open disclosure or focus: {up}")
                    if up["verdict"] != up["want"]:
                        problems.append(f"{tag} update(changed={changed}) did not render the new input")
                for changed in (False, True):
                    sf = page.evaluate(SLOT_FOCUS, [case, changed])
                    if not sf["before"] or not sf["after"]:
                        problems.append(f"{tag} update(changed={changed}) lost focus inside the readout slot: {sf}")
                layout = page.evaluate(LAYOUT, case)
                want = "sideBySide" if width >= 900 else "stacked"
                if not layout[want]:
                    problems.append(f"{tag} evidence groups are not {want}: {layout}")
                after = page.evaluate("() => JSON.stringify(window.__cevPreview.cases.map(c => c.input))")
                if after != snap["before"]:
                    problems.append(f"{tag} the frozen input changed")
                problems += [f"{tag} page error: {e}" for e in errors]
                page.close()
        finally:
            browser.close()
    return problems


class CompareEvidenceViewRenderTest(unittest.TestCase):
    def test_widths_values_keyboard_and_retained_state(self):
        self.assertEqual([], run_checks(shots=os.environ.get("CEV_SCREENSHOT_DIR")))

    def test_guard_fails_on_broken_builds(self):
        broken = {
            "no wrapping": (None, (".cev-row-name { font-weight: 600; min-width: 0; }", ".cev-row-name { font-weight: 600; white-space: nowrap; }")),
            "focus not restored": (("if (target) target.focus();", "if (target) target.blur();"), None),
            "slot rebuilt": (("fresh.querySelector('[data-cev-slot=\"readout\"]').replaceWith(slot);", ""), None),
            "panel not toggled": (("panel.hidden = !opening;", ""), None),
            "slot focus not restored": (("        slotFocus.focus();", "        slotFocus.blur();"), None),
            "groups never side by side": (None, ("@media (min-width: 900px) { .cev-groups", "@media (min-width: 9000px) { .cev-groups")),
        }
        for label, (js, css) in broken.items():
            with self.subTest(label):
                self.assertNotEqual([], run_checks(js_patch=js, css_patch=css), label)


if __name__ == "__main__":
    unittest.main()
