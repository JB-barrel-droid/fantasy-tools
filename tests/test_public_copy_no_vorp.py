"""Regression: public copy says "value above waivers", never "VORP".

Standing copy rule: user-visible strings in the trade-value-chart widgets must
not contain the word VORP in any casing. Internal identifiers (rawVorp,
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
INTERNAL_LITERALS = {"espn_vorp"}

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


class PublicCopyNoVorpTest(unittest.TestCase):
    def test_no_vorp_in_user_visible_strings(self):
        offenders = []
        for path in WIDGETS:
            self.assertTrue(path.is_file(), "widget file missing: %s" % path)
            for lineno, text, quote in string_literals(path.read_text(encoding="utf-8")):
                if text in INTERNAL_LITERALS:
                    continue
                if VORP_RE.search(static_text(text, quote)):
                    offenders.append("%s:%d: %r" % (path.name, lineno, text))
        self.assertEqual(
            offenders,
            [],
            "user-visible strings must say 'value above waivers', never 'VORP':\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
