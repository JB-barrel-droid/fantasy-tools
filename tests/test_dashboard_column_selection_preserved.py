"""Regression: cycling scoring/teams must not destroy the user's column picks.

ensureAvailableSelection() runs whenever the scoring/teams combo changes.
On 2026-10-01 it destructively pruned state.columns to the keys available
in the NEW combo:

    state.columns = state.columns.filter(key => allowed.has(key));

So toggling extra columns on (e.g. CBS Adjusted), switching to a combo
where that source is paused/unavailable, and switching back permanently
lost the picks -- the chips flipped off and never came back. visibleColumns()
already filters the stored selection against the currently-available keys
at render time, so the destructive mutation was both redundant and lossy.

This test fails against the pruned state (a state.columns reassignment
inside ensureAvailableSelection) and passes once the selection is preserved.
"""
import re
import unittest
from pathlib import Path

JS = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "trade-value-chart"
    / "assets"
    / "comparison-dashboard.js"
)


def _fn_body(text, name):
    m = re.search(rf"function {name}\(\) \{{(.*?)\n  \}}", text, re.DOTALL)
    assert m, f"{name}() not found -- test wiring is stale"
    return m.group(1)


class ColumnSelectionPreservedTest(unittest.TestCase):
    def test_ensure_available_selection_does_not_reassign_columns(self):
        body = _fn_body(JS.read_text(), "ensureAvailableSelection")
        self.assertNotRegex(
            body,
            r"state\.columns\s*=",
            "ensureAvailableSelection() must not reassign state.columns; "
            "visibleColumns() already filters against available keys at render time.",
        )

    def test_visible_columns_still_filters_by_availability(self):
        """The render-time filter is what keeps unavailable columns hidden."""
        body = _fn_body(JS.read_text(), "visibleColumns")
        self.assertIn("allowed.has(key)", body)


if __name__ == "__main__":
    unittest.main()
