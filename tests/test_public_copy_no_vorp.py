"""Regression: user-facing copy never says VORP; the term is "Value above waivers".

JEG-861 (Jeremy, 2026-10-22, multiple choice, recommendation taken): "VORP vs
waivers" is renamed "Value above waivers" everywhere on the site and no
"VORP" appears in user-facing text (docs/manifesto.md). This retires decision
copy-vorp-001 (2026-10-06), which had locked "VORP vs waivers" as the one
allowed phrase; the static scanner below now flags that phrase too.

Two guards:
  1. Static: every JS *string literal* in the chart widgets that contains
     "vorp" in any casing fails. Internal identifiers (rawVorp,
     buildEspnVorpMap, the "espn_vorp" data key, the "vorp" view ID in a key
     position) are exempt -- comments and identifiers never count.
  2. Rendered (the source of truth): the built v2 page at 1440 and 390 px,
     every tab, the Customize dialog and the player detail drawer: no "vorp"
     in the visible text, the document title, or any aria-label / title /
     alt / placeholder attribute on any element.
     Negative-tested in test_dom_guard_fails_on_vorp_labels: a shell with the
     old "VORP vs waivers" pill and a v2.js that writes VORP into an
     aria-label each make the sweep fail.

2026-10-08 (copy-guard lane): lowercase snake_case literals in key positions
(call argument, array element, index, object key, comparison operand) with no
rendering sink in their statement are internal keys -- see is_internal_key.
"""

import re
import unittest
from pathlib import Path

from tests import _render_env

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDGETS = [
    REPO_ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js",
    REPO_ROOT / "app" / "trade-value-chart" / "assets" / "comparison-dashboard.js",
]

# String literals that are internal data keys, never rendered for users.
INTERNAL_LITERALS = {"espn_vorp", "cbsros_vorp", "razzball_vorp"}

VORP_RE = re.compile(r"vorp", re.IGNORECASE)
INTERP_RE = re.compile(r"\$\{[^{}]*\}")


def static_text(literal, quote):
    """User-visible text of a literal: for template literals, strip ${...}
    interpolations, which are code rather than copy."""
    if quote == "`":
        previous = None
        while previous != literal:
            previous = literal
            literal = INTERP_RE.sub("", literal)
    return literal


def string_literals(source):
    """Return (line_number, literal_text, quote, start, end) for every JS
    string literal; start/end are source offsets including the quotes.

    Hand-rolled scanner: skips // and /* */ comments, understands single,
    double, and template quotes with backslash escapes. Regex literals that
    contain quote characters would confuse it; neither widget file has any.
    """
    literals = []
    i, n = 0, len(source)
    line = 1
    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                if source[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue
        if ch in "\"'`":
            quote = ch
            start_line = line
            start = i
            i += 1
            buf = []
            closed = False
            while i < n:
                c = source[i]
                if c == "\\" and i + 1 < n:
                    buf.append(source[i + 1])
                    i += 2
                    continue
                if c == "\n":
                    line += 1
                    if quote != "`":
                        break  # unterminated literal; bail out of it
                    buf.append(c)
                    i += 1
                    continue
                if c == quote:
                    i += 1
                    closed = True
                    break
                buf.append(c)
                i += 1
            if closed:
                literals.append((start_line, "".join(buf), quote, start, i))
            continue
        i += 1
    return literals


# Internal keys (the "vorp" view ID, "_vorp" series suffixes, "espn_vorp")
# are recognised by shape AND position, not by an allowlist of strings:
#  * shape: a lowercase snake_case token ("vorp", "_vorp", "cbsros_vorp") --
#    never capitalised words or text with spaces, which is what copy looks like;
#  * position: the literal sits where code consumes a key -- a call argument,
#    an array element, an index, an object key or a comparison operand. Copy
#    lands as an assignment, return, object value or ternary branch, which
#    stay flagged (fail closed);
#  * no rendering sink anywhere in the same statement, so a key-shaped literal
#    fed to textContent/innerHTML/setAttribute/etc. is still treated as copy.
KEY_SHAPE_RE = re.compile(r"_?[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
# Call argument / array element / index / key after a comma, or a comparison.
KEY_BEFORE_RE = re.compile(r"(?:[(,\[]|[=!]==?)\s*$")
# First object key ({"vorp": ...}) or the left side of a comparison. A bare
# ":" after the literal is not enough: that is also a ternary branch.
OBJECT_OPEN_RE = re.compile(r"\{\s*$")
COLON_AFTER_RE = re.compile(r"^\s*:")
COMPARISON_AFTER_RE = re.compile(r"^\s*[=!]==?")
RENDER_SINK_RE = re.compile(
    r"\b(?:textContent|innerText|innerHTML|outerHTML|insertAdjacent(?:HTML|Text)|createTextNode"
    r"|setAttribute|title|placeholder|ariaLabel|alt|label|caption|append|prepend|alert|confirm|prompt)\b"
)
STATEMENT_BOUNDARY = ";{}"


def statement_around(source, start, end):
    """The source of the statement holding [start, end): from the last ; { }
    before it to the first one after it."""
    left = max(source.rfind(ch, 0, start) for ch in STATEMENT_BOUNDARY) + 1
    rights = [pos for pos in (source.find(ch, end) for ch in STATEMENT_BOUNDARY) if pos != -1]
    return source[left:min(rights) if rights else len(source)]


def is_internal_key(source, text, start, end):
    if not KEY_SHAPE_RE.fullmatch(text):
        return False
    line_start = source.rfind("\n", 0, start) + 1
    line_end = source.find("\n", end)
    before = source[line_start:start]
    after = source[end:line_end if line_end != -1 else len(source)]
    key_position = (KEY_BEFORE_RE.search(before) or COMPARISON_AFTER_RE.search(after)
                    or (OBJECT_OPEN_RE.search(before) and COLON_AFTER_RE.search(after)))
    if not key_position:
        return False
    return not RENDER_SINK_RE.search(statement_around(source, start, end))


def visible_vorp_literals(source):
    offenders = []
    for lineno, text, quote, start, end in string_literals(source):
        if text in INTERNAL_LITERALS or is_internal_key(source, text, start, end):
            continue
        if VORP_RE.search(static_text(text, quote)):
            offenders.append((lineno, text))
    return offenders


class PublicCopyNoVorpTest(unittest.TestCase):
    def test_no_vorp_in_user_visible_strings(self):
        offenders = []
        for path in WIDGETS:
            self.assertTrue(path.is_file(), "widget file missing: %s" % path)
            for lineno, text in visible_vorp_literals(path.read_text(encoding="utf-8")):
                offenders.append("%s:%d: %r" % (path.name, lineno, text))
        self.assertEqual(
            offenders,
            [],
            "user-visible strings never say VORP (the term is 'Value above waivers'):\n"
            + "\n".join(offenders),
        )

    def test_internal_view_id_does_not_exempt_visible_labels(self):
        internal = 'const VIEW_MODE_ORDER = ["indexed", "vorp", "adj"];'
        self.assertEqual(visible_vorp_literals(internal), [])
        for visible in ('caption.textContent = "VORP";', 'caption.textContent = "vorp";',
                        'const title = "Raw VORP";'):
            with self.subTest(visible=visible):
                self.assertEqual(len(visible_vorp_literals(internal + "\n" + visible)), 1)

    def test_internal_view_lookup_is_exempt_only_as_that_call(self):
        self.assertEqual(visible_vorp_literals('        const vorp = publishedViewMap(key, "vorp");'), [])
        self.assertTrue(visible_vorp_literals('        const vorp = publishedViewMap(key, "vorp"); label.textContent = "vorp";'))
        self.assertTrue(visible_vorp_literals('        caption.textContent = "vorp";'))

    def test_extra_rendered_literal_on_enum_line_is_not_exempt(self):
        source = 'const VIEW_MODE_ORDER = ["indexed", "vorp", "adj"]; caption.textContent = "vorp";'
        self.assertTrue(visible_vorp_literals(source))

    def test_template_copy_and_data_keys_keep_their_existing_rules(self):
        self.assertTrue(visible_vorp_literals('const title = `Publisher VORP`;'))
        self.assertEqual(visible_vorp_literals('const key = "espn_vorp";'), [])


class InternalKeyPositionTest(unittest.TestCase):
    """Key-shaped literals are exempt only where code consumes them as keys."""

    def test_key_positions_are_internal(self):
        for ok in ('const base = series.endsWith("_vorp") ? series.slice(0, -5) : series;',
                   'if (source.endsWith("_vorp") && !PURE_VORP_KEYS.includes(source)) {',
                   'const vorp = measuredPublishedView(key, "vorp");',
                   '["indexed", "vorp", "adjusted"].forEach(view => {',
                   'const VIEW_MODE_ORDER = ["indexed", "vorp", "adj"];',
                   'const row = out["vorp"];',
                   'if (viewMode === "vorp") draw();',
                   'const m = {"vorp": 1};', 'if ("vorp" === viewMode) draw();'):
            with self.subTest(ok=ok):
                self.assertEqual(visible_vorp_literals(ok), [])

    def test_key_shaped_copy_positions_still_fail(self):
        for bad in ('const title = "vorp";', 'return "vorp";', 'const row = {label: "vorp"};',
                    'const mode = saved ? "saved vorp_views" : "derived";',
                    'const t = ok ? "vorp" : "adj";',
                    'el.textContent = pick("vorp");', 'el.setAttribute("title", ["vorp"][0]);',
                    'node.append(", vorp");',
                    'const m = {method: "buildVorpRows on the saved projections + scaleToSharedTotal"};'):
            with self.subTest(bad=bad):
                self.assertEqual(len(visible_vorp_literals(bad)), 1)

    def test_sink_in_a_later_statement_does_not_taint_a_key(self):
        source = 'if (series.endsWith("_vorp")) {\n  caption.textContent = "Value above waivers";\n}'
        self.assertEqual(visible_vorp_literals(source), [])


class RetiredPhraseTest(unittest.TestCase):
    """JEG-861: the former locked phrase "VORP vs waivers" is copy like any other."""

    def test_retired_phrase_fails(self):
        for bad in ('const t = "VORP vs waivers";', 'const t = "Raw VORP vs waivers";',
                    'const t = "ESPN raw VORP vs waivers";', 'const t = `Every source in VORP vs waivers units`;',
                    'const t = "VORP";', 'const t = "Raw VORP";', 'const t = "vorp vs waivers";',
                    'const t = "VORP vs replacement";', 'const t = `Publisher VORP`;'):
            with self.subTest(bad=bad):
                self.assertEqual(len(visible_vorp_literals(bad)), 1)

    def test_new_term_passes(self):
        for ok in ('const t = "Value above waivers";', 'const t = "ESPN value above waivers, raw";'):
            with self.subTest(ok=ok):
                self.assertEqual(visible_vorp_literals(ok), [])


# ---------------------------------------------------------------- rendered DOM sweep (JEG-861)

TABS = ("#trade-targets", "#player-values", "#risers-fallers", "#compare-trade", "#find-trade",
        "#writing/how-values", "#writing/research", "#writing/manifesto", "#values-auditing")
SHELL = REPO_ROOT / "app" / "v2" / "shell.html"
V2_JS = REPO_ROOT / "app" / "v2" / "v2.js"
# Visible text plus every accessible-name attribute on every element (hidden ones too: attributes are
# static copy, and a hidden dialog's label becomes visible when it opens).
SWEEP = """() => {
  const out = [];
  const grab = (node, where) => { if (/vorp/i.test(node)) out.push(where + ': ' + String(node).slice(0, 120)); };
  grab(document.title, 'title');
  grab(document.body.innerText, 'text');
  for (const el of document.querySelectorAll('[aria-label],[title],[alt],[placeholder]')) {
    for (const a of ['aria-label', 'title', 'alt', 'placeholder']) {
      const v = el.getAttribute(a);
      if (v) grab(v, a + ' on ' + (el.id ? '#' + el.id : el.tagName.toLowerCase()));
    }
  }
  return out;
}"""


def dom_vorp_hits(shell_patch=None, v2_patch=None):
    """Every "vorp" hit in the rendered site, as "[width tab] where: text" lines."""
    from tests.test_published_league_settings_render import _chromium_executable
    from tests.test_v2_deal_read_render import _served
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if v2_patch:
        assert v2_patch[0] in js, f"v2 patch anchor missing: {v2_patch[0]!r}"
        js = js.replace(v2_patch[0], v2_patch[1])
    hits = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 1000), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_patch:
                    page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
                if shell_patch:
                    def serve_shell(route, *_):
                        response = route.fetch()
                        body = response.text()
                        assert shell_patch[0] in body, f"shell patch anchor missing: {shell_patch[0]!r}"
                        route.fulfill(response=response, body=body.replace(shell_patch[0], shell_patch[1]))
                    page.route("**/v2/", serve_shell)
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
                # Every method in the shown set so each series label and detail column renders.
                page.evaluate("() => window.TradeValueV2.setShown(window.TradeValueV2.shown().concat(['espn', 'espn_vorp']))")
                page.wait_for_timeout(300)
                for tab in TABS:
                    page.evaluate("h => { location.hash = h; }", tab)
                    page.wait_for_timeout(500)
                    if tab == "#trade-targets":
                        for _ in range(3):
                            toggle = page.locator("[data-expand][aria-expanded=false]").first
                            if toggle.count() and toggle.is_visible():
                                toggle.click()
                    if tab == "#player-values":
                        page.click("#v2Table tbody tr td.player")
                        page.wait_for_timeout(200)
                        hits += [f"[{width}px {tab} drawer] {h}" for h in page.evaluate(SWEEP)]
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(100)
                    _render_env.open_phone_context(page)  # JEG-1134: on a phone the context row opens first
                    if page.locator("#v2EditSources").count() and page.locator("#v2EditSources").first.is_visible():
                        page.click("#v2EditSources")
                        page.wait_for_timeout(200)
                        hits += [f"[{width}px {tab} customize] {h}" for h in page.evaluate(SWEEP)]
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(100)
                    hits += [f"[{width}px {tab}] {h}" for h in page.evaluate(SWEEP)]
                if page_errors:
                    hits.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return sorted(set(hits))


DOM_PATCHES = {
    "old pill back": {"shell_patch": ('<span class="v2-pill is-vorp">Value above waivers</span>', '<span class="v2-pill is-vorp">VORP vs waivers</span>')},
    "old series label back": {"v2_patch": ('vorp: "Value above waivers"}', 'vorp: "VORP vs waivers"}')},
    "VORP in an aria-label": {"v2_patch": ("`${text}: open the publisher's page in a new tab`", "`${text}: open the publisher's VORP page in a new tab`")},
}


class RenderedNoVorpTest(unittest.TestCase):
    def test_no_vorp_in_rendered_text_or_accessible_names(self):
        _render_env.ensure_built()
        self.assertEqual(dom_vorp_hits(), [])

    def test_dom_guard_fails_on_vorp_labels(self):
        _render_env.ensure_built()
        for name, kwargs in DOM_PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(dom_vorp_hits(**kwargs), [], f"sweep did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
