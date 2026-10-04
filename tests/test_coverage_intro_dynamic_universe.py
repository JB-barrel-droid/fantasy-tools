"""Regression: the data-health intro copy must use the live player universe, never a hardcoded count.

QA-007: the intro read "Coverage is measured against the 596-player canonical
snapshot" while the fixture held 610 players and the per-source cards below it
already rendered coverage/<universe> with universe = embedded.players.length.
Different baselines in different places made coverage numbers incomparable.

Fix: the intro interpolates the same `universe` variable the cards use, so
there is one canonical denominator everywhere. This test fails against the
pre-fix hardcoded copy and passes against the live file.

Negative-tested 2026-10-04: the pre-fix literal ("596-player", no
interpolation) fails; the fixed template literal (${universe}) passes.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "app" / "trade-value-chart" / "index.html"

# The full textContent assignment for the data-health intro paragraph.
INTRO_ASSIGN_RE = re.compile(
    r'dataHealthIntro"\)\.textContent\s*=\s*(`[^`]*`|"[^"]*")'
)

# A hardcoded player count like "596-player" inside user-visible copy.
HARDCODED_COUNT_RE = re.compile(r"\b\d{2,4}-player\b")


def intro_copy_ok(literal: str) -> bool:
    """True when the intro literal interpolates the live universe and carries
    no hardcoded player count in its static text."""
    interpolates_universe = "${universe}" in literal
    # Strip ${...} interpolations so only static copy is scanned.
    static_text = re.sub(r"\$\{[^{}]*\}", "", literal)
    no_hardcoded_count = not HARDCODED_COUNT_RE.search(static_text)
    return interpolates_universe and no_hardcoded_count


def read_live_intro_literal() -> str:
    source = INDEX_HTML.read_text(encoding="utf-8")
    m = INTRO_ASSIGN_RE.search(source)
    if not m:
        raise AssertionError(
            "Could not locate the dataHealthIntro textContent assignment in "
            "app/trade-value-chart/index.html"
        )
    return m.group(1)


class TestIntroCopyDynamicUniverse(unittest.TestCase):
    def test_hardcoded_player_count_fails(self):
        """The pre-fix copy is rejected: hardcoded 596-player, no interpolation."""
        broken = (
            '"Coverage is measured against the 596-player canonical snapshot. '
            'Content, fit, and news dates identify the data actually powering '
            'the dashboard."'
        )
        self.assertFalse(
            intro_copy_ok(broken),
            "Guard must fail against the pre-fix hardcoded 596-player copy",
        )

    def test_live_intro_uses_dynamic_universe(self):
        """The shipped copy interpolates the live universe with no hardcoded count."""
        literal = read_live_intro_literal()
        self.assertTrue(
            intro_copy_ok(literal),
            f"dataHealthIntro must interpolate ${{universe}} and contain no "
            f"hardcoded player count; got: {literal[:120]}",
        )


if __name__ == "__main__":
    unittest.main()
