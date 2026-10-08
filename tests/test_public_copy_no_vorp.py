"""Regression: public copy says "VORP vs waivers" and never any other VORP.

Standing copy rule (decision copy-vorp-001, 2026-10-06; replaced the earlier
"value above waivers, never VORP" rule): the only user-visible use of the word
VORP is the exact locked phrase "VORP vs waivers" (capital VORP, lowercase
"vs waivers"). Any other casing or wording ("Raw VORP", "VORP vs replacement",
"vorp vs waivers", bare "VORP") still fails. Internal identifiers (rawVorp,
buildEspnVorpMap, the "espn_vorp" data key) are exempt, so this test scans JS
*string literals* only -- comments and identifiers never count.

Negative-tested 2026-09-21: reintroducing `espn_vorp: "ESPN raw VORP"` fails
this test; restoring the fixed copy passes.

2026-10-08 (copy-guard lane): lowercase snake_case literals in key positions
(call argument, array element, index, object key, comparison operand) with no
rendering sink in their statement are internal keys -- see is_internal_key.
This replaced two single-line regex exemptions for the "vorp" view ID.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDGETS = [
    REPO_ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js",
    REPO_ROOT / "app" / "trade-value-chart" / "assets" / "comparison-dashboard.js",
]

# String literals that are internal data keys, never rendered for users.
INTERNAL_LITERALS = {"espn_vorp", "cbsros_vorp", "razzball_vorp"}

VORP_RE = re.compile(r"vorp", re.IGNORECASE)
# The single locked user-facing phrase. Case-sensitive on purpose.
LOCKED_PHRASE_RE = re.compile(r"\bVORP vs waivers\b")
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
        if VORP_RE.search(LOCKED_PHRASE_RE.sub("", static_text(text, quote))):
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
            "user-visible strings may use VORP only as the exact phrase 'VORP vs waivers':\n"
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
        source = 'if (series.endsWith("_vorp")) {\n  caption.textContent = "VORP vs waivers";\n}'
        self.assertEqual(visible_vorp_literals(source), [])


class LockedPhraseTest(unittest.TestCase):
    """copy-vorp-001: the exemption is one exact phrase, not the word VORP."""

    def test_locked_phrase_is_allowed(self):
        for ok in ('const t = "VORP vs waivers";', 'const t = "Raw VORP vs waivers";',
                   'const t = "ESPN raw VORP vs waivers";', 'const t = `Every source in VORP vs waivers units`;'):
            with self.subTest(ok=ok):
                self.assertEqual(visible_vorp_literals(ok), [])

    def test_other_vorp_wording_still_fails(self):
        for bad in ('const t = "VORP";', 'const t = "Raw VORP";', 'const t = "vorp vs waivers";',
                    'const t = "VORP vs replacement";', 'const t = "VORP vs waivers and VORP";',
                    'const t = "VORP vs waiversX";', 'const t = `Publisher VORP`;'):
            with self.subTest(bad=bad):
                self.assertEqual(len(visible_vorp_literals(bad)), 1)


if __name__ == "__main__":
    unittest.main()
