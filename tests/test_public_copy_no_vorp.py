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
    """Yield (line_number, literal_text) for every JS string literal.

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
                literals.append((start_line, "".join(buf), quote))
            continue
        i += 1
    return literals


# JEG-225: one internal view-ID declaration, not a global exemption for "vorp".
# A visible label using that exact word anywhere else must still fail.
INTERNAL_VIEW_ORDER_RE = re.compile(
    r'^\s*const VIEW_MODE_ORDER = \["indexed", "vorp", "adj"\];\s*$'
)
# The same view ID passed as the lookup key of publishedViewMap() (math
# inspector, 2026-10-08). Only this exact call shape on its own line.
INTERNAL_VIEW_LOOKUP_RE = re.compile(
    r'^\s*const \w+ = publishedViewMap\(key, "vorp"\);\s*$'
)


def visible_vorp_literals(source):
    lines = source.splitlines()
    offenders = []
    for lineno, text, quote in string_literals(source):
        if text in INTERNAL_LITERALS:
            continue
        if text == "vorp" and (INTERNAL_VIEW_ORDER_RE.fullmatch(lines[lineno - 1])
                               or INTERNAL_VIEW_LOOKUP_RE.fullmatch(lines[lineno - 1])):
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
