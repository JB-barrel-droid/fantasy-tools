"""JEG-264: every top-level dashboard section heading carries exactly one view tag.

The monitor dashboard distinguishes four chart views: [Indexed], [VORP],
[Adj], and [Legacy]. Every <section class="card"> heading must carry
EXACTLY one of those tags -- the test fails on missing tags AND on tags
the four-tag whitelist does not recognise.

Discrimination: the test must FAIL when an untagged heading is added.
The negative-case fixture below copies a representative subset of the
dashboard structure and adds an untagged heading; running against that
fixture is expected to raise.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DASHBOARD = REPO / "modules" / "dashboard.html"

ALLOWED_TAGS = ("[Indexed]", "[VORP]", "[Adj]", "[Legacy]")
TAG_RE = re.compile(r"\[(" + "|".join(t.strip("[]") for t in ALLOWED_TAGS) + r")\]")
# Any bracketed token -- catches tags the whitelist does not know, which
# TAG_RE alone is blind to (a [Rogue] tag yields zero TAG_RE matches and
# would otherwise pass silently).
ANY_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")


def _check_heading(h):
    """Return (allowed_matches, rogue_tags) for one heading's inner HTML."""
    text = re.sub(r"<[^>]+>", "", h)
    allowed = TAG_RE.findall(text)
    rogue = [t for t in ANY_BRACKET_RE.findall(text)
             if f"[{t}]" not in ALLOWED_TAGS]
    return allowed, rogue


def _read_dashboard() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def _section_headings(html: str):
    """Yield the inner text of every <h2> inside a <section class="card">."""
    for m in re.finditer(
        r'<section\s+class="card"[^>]*>\s*<h2>(.*?)</h2>', html, re.DOTALL
    ):
        yield m.group(1)


def _fixture_with_untagged():
    """Tiny fixture derived from the dashboard that adds an untagged heading."""
    return (
        '<section class="card" id="x1">'
        '<h2><span class="view-tag view-tag-indexed">[Indexed]</span> ok heading</h2>'
        '</section>'
        '<section class="card" id="x2">'
        '<h2>UN-TAGGED HEADING</h2>'  # violates JEG-264
        '</section>'
    )


def _fixture_with_bad_tag():
    """Tiny fixture that uses a tag the four-tag whitelist does not recognise."""
    return (
        '<section class="card" id="x1">'
        '<h2><span class="view-tag view-tag-rogue">[Rogue]</span> rogue tag</h2>'
        '</section>'
    )


class DashboardViewTagsTest(unittest.TestCase):
    def test_every_section_heading_has_exactly_one_allowed_tag(self):
        html = _read_dashboard()
        headings = list(_section_headings(html))
        self.assertGreater(len(headings), 0,
                           "no <section class=card><h2> headings found")
        for h in headings:
            allowed, rogue = _check_heading(h)
            self.assertEqual(
                rogue, [],
                f"heading carries tag outside the whitelist: {rogue!r}: "
                f"{h[:120]!r}"
            )
            self.assertEqual(
                len(allowed), 1,
                f"heading must carry exactly one view tag, got {allowed!r}: "
                f"{h[:120]!r}"
            )

    def test_untagged_heading_fails(self):
        """Discrimination: an untagged heading is caught (no silent pass)."""
        html = _fixture_with_untagged()
        bad = []
        for h in _section_headings(html):
            if len(TAG_RE.findall(h)) != 1:
                bad.append(h)
        self.assertEqual(len(bad), 1,
                         "fixture must produce exactly one untagged heading")
        self.assertIn("UN-TAGGED", bad[0])

    def test_disallowed_tag_fails(self):
        """Discrimination: a tag outside the four-tag whitelist is caught.

        TAG_RE alone is blind to unknown tags (a [Rogue] tag yields zero
        matches and would pass silently); the check must scan for ANY
        bracketed token.
        """
        html = _fixture_with_bad_tag()
        bad = []
        for h in _section_headings(html):
            _allowed, rogue = _check_heading(h)
            bad.extend(rogue)
        self.assertEqual(bad, ["Rogue"],
                         "fixture must produce exactly one rogue tag")

    def test_well_formed_fixture_passes(self):
        """Discrimination: a well-formed fixture passes the same check."""
        html = (
            '<section class="card"><h2><span class="view-tag">[Indexed]</span> a</h2></section>'
            '<section class="card"><h2><span class="view-tag">[VORP]</span> b</h2></section>'
            '<section class="card"><h2><span class="view-tag">[Adj]</span> c</h2></section>'
            '<section class="card"><h2><span class="view-tag">[Legacy]</span> d</h2></section>'
        )
        for h in _section_headings(html):
            ms = TAG_RE.findall(h)
            self.assertEqual(len(ms), 1, f"well-formed heading should pass: {h!r}")


if __name__ == "__main__":
    unittest.main()