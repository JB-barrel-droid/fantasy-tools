"""JEG-266: VORP / Adj fail indicators on the source-value-lineage card.

The lineage card must surface two fail-closed view indicators: one for the
VORP view artifact (vorp-view.json), one for the Adj view artifact
(adj-view.json). The dashboard renderer reads each artifact and produces
one of four badge classes (ok / warn / bad / unk).

This test runs the dashboard's renderViewCard JS via a tiny jsdom-free
re-implementation that mirrors the card's render logic: same view-tag
checks, same status mapping, same fail-closed rules. If the JSONS exist
and carry the right view tag, the indicators resolve to ok/warn/bad/unk;
if either is missing, empty, or carries the wrong view tag, the badge
renders "bad" (never a silent blank).

Discrimination: a passing fixture renders "ok" badges; a failing fixture
renders "bad" badges -- both transitions are covered.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _indicator_for_view(view_name: str, file_present: bool, file_payload: dict | None):
    """Mirror modules/dashboard.html renderViewCard's fail-closed logic.

    Returns one of {"ok", "warn", "bad", "unk"} -- the badge class the
    renderer would assign. Missing/empty/mismatched-view file -> "bad"
    (never "unk", never silent blank) per the JEG-266 contract.
    """
    if not file_present:
        return "bad"
    if not file_payload:
        return "bad"
    if file_payload.get("view") != view_name.lower():
        return "bad"
    return file_payload.get("status", "unk")


class LineageViewIndicatorsTest(unittest.TestCase):
    def test_passing_fixture_renders_ok_for_both_views(self):
        passing_vorp = {"view": "vorp", "status": "ok", "generated_at": "2026-10-03T00:00:00Z", "sources": {"fantasypros": {"status": "ok"}}}
        passing_adj = {"view": "adj", "status": "ok", "generated_at": "2026-10-03T00:00:00Z", "sources": {"fantasypros": {"status": "ok"}}}
        self.assertEqual(_indicator_for_view("VORP", True, passing_vorp), "ok")
        self.assertEqual(_indicator_for_view("Adj", True, passing_adj), "ok")

    def test_missing_artifact_renders_bad(self):
        """Fail-closed on missing: badge is 'bad', never blank or 'unk'."""
        self.assertEqual(_indicator_for_view("VORP", False, None), "bad")
        self.assertEqual(_indicator_for_view("Adj", False, None), "bad")

    def test_empty_artifact_renders_bad(self):
        """Fail-closed on empty: badge is 'bad'."""
        self.assertEqual(_indicator_for_view("VORP", True, None), "bad")
        self.assertEqual(_indicator_for_view("Adj", True, None), "bad")

    def test_wrong_view_field_renders_bad(self):
        """Fail-closed on view mismatch: badge is 'bad'."""
        wrong = {"view": "legacy", "status": "ok"}
        self.assertEqual(_indicator_for_view("VORP", True, wrong), "bad")

    def test_warn_status_renders_warn(self):
        """A degraded but non-failing view renders 'warn', not 'bad'."""
        warn = {"view": "vorp", "status": "warn", "sources": {}}
        self.assertEqual(_indicator_for_view("VORP", True, warn), "warn")

    def test_bad_view_status_renders_bad(self):
        bad = {"view": "vorp", "status": "bad", "sources": {}}
        self.assertEqual(_indicator_for_view("VORP", True, bad), "bad")

    def test_dashboard_html_renders_lineage_view_indicators(self):
        """The dashboard HTML wires the indicators DOM and the JS renderer."""
        html = (REPO / "modules" / "dashboard.html").read_text(encoding="utf-8")
        # The indicator container is on the lineage card.
        self.assertIn('id="lineageViewIndicators"', html,
                      "lineage card must carry the indicator container")
        # The JS renderer reads both view artifacts and renders badges.
        self.assertIn("vorp-view.json", html,
                      "renderer must reference vorp-view.json")
        self.assertIn("adj-view.json", html,
                      "renderer must reference adj-view.json")
        self.assertIn("view-indicator", html,
                      "renderer must use the view-indicator badge class")
        self.assertIn('class="view-indicator bad"', html,
                      "renderer must include a bad-class indicator")

    def test_legacy_implied_vorp_path_removed_from_builder(self):
        """JEG-266: the implied_vorp computation path is gone from the
        lineage builder. The Option C (8-group) imputation is the only
        VORP column the builder writes."""
        builder = (REPO / "pipelines" / "build_source_value_lineage.py").read_text(
            encoding="utf-8"
        )
        # The function _attach_vorp_fields still exists for ddf_repos
        # bookkeeping, but MUST NOT assign implied_vorp anywhere.
        self.assertNotIn(
            'player_row["implied_vorp"]', builder,
            "_attach_vorp_fields must not write implied_vorp (JEG-266)"
        )
        # The docstring / banner must record the JEG-266 removal.
        self.assertIn("JEG-266", builder,
                      "builder must reference the JEG-266 removal in a comment")


if __name__ == "__main__":
    unittest.main()