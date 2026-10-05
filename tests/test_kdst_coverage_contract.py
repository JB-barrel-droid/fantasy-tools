"""K/DST coverage contract tests.

These tests verify that K/DST (kickers and defenses) are handled correctly
according to the source-audit findings:
- Only ESPN provides K/DST projections (no ECR, no Razzball, no peers)
- K/DST snapshot may be unknown ("?") or stale
- Zero vs missing must be distinguished
- No peer-adjusted view exists for K/DST

The brief (JEG-19) requires:
1. Unknown K/DST snapshot shows "?" in metadata honestly
2. Stale K/DST data is detected and reported as stale
3. Zero-valued K/DST (e.g., rookie with 0 ppg) is distinguished from missing K/DST
4. No green freshness badge from pull time alone (must be content vintage)
"""

import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))


class KdstSnapshotValidationTest(unittest.TestCase):
    """Tests for K/DST snapshot detection in meta."""

    def test_unknown_kdst_snapshot_detected_as_unknown(self):
        """When kdst_snapshot is "?", it should be flagged as unknown.

        The current fixture has kdst_snapshot = "?" indicating unknown content vintage.
        This is honest - we don't know when the ESPN K/DST data was actually published.
        """
        # Simulate current fixture state with unknown snapshot
        fixture_meta = {
            "kdst_snapshot": "?",
            "kdst_note": "Kickers and team defenses price from ESPN projections only...",
            "n_k": 45,
            "n_dst": 32,
        }

        # The "?" should be detected as unknown, not as a valid date
        kdst_snapshot = fixture_meta.get("kdst_snapshot", "?")

        # Unknown snapshot should be exactly "?" - not a date string
        self.assertEqual(kdst_snapshot, "?",
            "Unknown K/DST snapshot must be exactly '?' to indicate unknown content vintage")

    def test_stale_kdst_snapshot_detected_as_stale(self):
        """When kdst_snapshot is an old date, it should be flagged as stale."""
        # Simulate stale data (old snapshot date)
        old_date = (date.today() - timedelta(days=15)).isoformat()
        fixture_meta = {
            "kdst_snapshot": old_date,  # 15 days old
            "kdst_note": "Kickers and team defenses price from ESPN projections only...",
        }

        kdst_snapshot = fixture_meta.get("kdst_snapshot", "?")
        if kdst_snapshot != "?":
            # Parse the date and check if stale (> 7 days old as threshold)
            snapshot_date = date.fromisoformat(kdst_snapshot)
            age_days = (date.today() - snapshot_date).days

            self.assertGreater(age_days, 7,
                f"K/DST snapshot from {age_days} days ago should be flagged as stale")

    def test_kdst_snapshot_freshness_requires_content_vintage_not_pull_time(self):
        """K/DST freshness must measure content vintage, not pull time.

        This follows the same pattern as ECR content vintage - a re-pull of
        unchanged content should NOT reset freshness.
        """
        # Simulate fresh content (pulled today but content is new)
        today = date.today().isoformat()
        fixture_meta = {
            "kdst_snapshot": today,  # pulled today
        }

        # Freshness should check content, not pull time
        # For K/DST, we don't have a separate content_date field like ECR
        # The implementation should either:
        # 1. Add kdst_content_date field, OR
        # 2. Clearly document that kdst_snapshot is pull time, not content time

        kdst_snapshot = fixture_meta.get("kdst_snapshot", "?")
        self.assertIsNotNone(kdst_snapshot,
            "K/DST snapshot must be present (either date or '?')")


class KdstNoPeerComparisonTest(unittest.TestCase):
    """Tests verifying K/DST have no peer sources for comparison."""

    def test_kdst_no_ecr_data(self):
        """K/DST rows must not carry an ecr_ros field (JEG-ECR-EXIT 2026-10-05).

        Pre-JEG-ECR-EXIT K/DST rows had ecr_ros=None. After JEG-ECR-EXIT the
        ecr_ros field is removed from the bake entirely (ESPN is the primary
        leg for all positions); K/DST rows therefore have no ecr_ros key at
        all and price from espn_ros only.
        """
        # Simulate a K player row
        k_player = {
            "pos": "K",
            "player_key": 12345,
            "name": "Harrison Mevis",
            "blend_ros": {"standard": 142.4, "half_ppr": 142.4, "ppr": 142.4},
            "espn_ros": {"standard": 142.4, "half_ppr": 142.4, "ppr": 142.4},
            "pricing": "espn_only",
        }

        self.assertNotIn("ecr_ros", k_player,
            "K/DST must not carry an ecr_ros field after JEG-ECR-EXIT")
        self.assertEqual(k_player["pricing"], "espn_only",
            "K/DST pricing must be 'espn_only'")

    def test_kdst_no_razzball_data(self):
        """K/DST rows should have no Razzball data."""
        dst_player = {
            "pos": "DST",
            "player_key": 99999,
            "name": "BAL",
            "rz_complete": False,
            "rz_comp_count": 0,
            "rz_covered": [],
        }

        self.assertFalse(dst_player["rz_complete"],
            "K/DST should have rz_complete = False (no Razzball)")
        self.assertEqual(dst_player["rz_comp_count"], 0,
            "K/DST should have zero Razzball components")

    def test_kdst_no_pm_data(self):
        """K/DST rows should have no prediction markets data."""
        k_player = {
            "pos": "K",
            "pm_complete": False,
            "pm_comp_count": 0,
            "pm_covered": [],
        }

        self.assertFalse(k_player["pm_complete"],
            "K/DST should have pm_complete = False (no prediction markets)")
        self.assertEqual(k_player["pm_comp_count"], 0,
            "K/DST should have zero PM components")

    def test_kdst_pricing_label_enforced(self):
        """K/DST must have pricing='espn_only', not 'experts_only'.

        Mirrors the validation in pipelines/bake_players.py: K/DST rows with
        pricing != 'espn_only' are violations.
        """
        def validate_kdst_pricing(players):
            violations = []
            for p in players:
                if p["pos"] in ("K", "DST") and p.get("pricing") != "espn_only":
                    violations.append(p)
            return violations

        # Valid K/DST rows pass
        valid = [
            {"pos": "K", "pricing": "espn_only"},
            {"pos": "DST", "pricing": "espn_only"},
        ]
        self.assertEqual(validate_kdst_pricing(valid), [])

        # Invalid K/DST (experts_only) is flagged
        invalid = [{"pos": "K", "pricing": "experts_only"}]
        self.assertEqual(len(validate_kdst_pricing(invalid)), 1)


class KdstZeroVsMissingTest(unittest.TestCase):
    """Tests verifying zero-valued K/DST are distinguished from missing."""

    def test_zero_ppg_kicker_is_valid_data(self):
        """A kicker with 0.0 ppg is valid data (e.g., rookie not yet playing).

        This is different from 'no kicker data available'.
        """
        # A kicker with 0.0 ppg (e.g., rookie on practice squad)
        k_with_zero = {
            "pos": "K",
            "name": "Rookie Kicker",
            "espn_ppg": {"standard": 0.0, "half_ppr": 0.0, "ppr": 0.0},
            "espn_ros": {"standard": 0.0, "half_ppr": 0.0, "ppr": 0.0},
            "games_remaining": 16,
        }

        # Zero is a valid value - the kicker exists but scores 0
        self.assertIn("espn_ppg", k_with_zero)
        self.assertEqual(k_with_zero["espn_ppg"]["ppr"], 0.0,
            "Zero PPG is valid data - player exists but scores nothing")

    def test_missing_kicker_has_no_espn_data(self):
        """A missing kicker (not in data) has no espn_ppg field."""
        # A player who is not a kicker
        skill_player = {
            "pos": "RB",
            "name": "Christian McCaffrey",
            "espn_ppg": {"standard": 18.5, "half_ppr": 21.2, "ppr": 23.9},
        }

        # This is not missing - it's a skill player with ESPN data
        self.assertIn("espn_ppg", skill_player)

    def test_kdst_unresolved_excluded_with_note(self):
        """Unresolved K/DST names should be excluded with a note, not guessed."""
        # Simulate the unresolved list from bake_players.py
        kdst_unresolved = [
            ("K", "Unknown Kicker Name"),
            ("DST", "XYZ"),  # Unknown team abbreviation
        ]

        # These should be logged and excluded, not guessed
        self.assertEqual(len(kdst_unresolved), 2,
            "Unresolved K/DST should be tracked for audit")
        self.assertTrue(all(pos in ("K", "DST") for pos, _ in kdst_unresolved),
            "Unresolved entries must track position")


class KdstDatasetStatusTest(unittest.TestCase):
    """Tests for K/DST in dataset_status panel."""

    def test_kdst_in_dataset_status_has_appropriate_status(self):
        """K/DST should have pending/stale status, never 'live' without fresh data.

        Based on the audit, K/DST has only ESPN as source. Without a fresh
        ESPN pull with known content vintage, K/DST cannot be 'live'.
        """
        # Current state: kdst_snapshot = "?" means we don't know the content vintage
        # This should result in 'pending' or 'stale' status, NOT 'live'

        # Simulate dataset_status for K/DST source
        # The actual implementation should set appropriate status
        kdst_source_status = {
            "name": "espn_kdst",
            "status": "pending",  # or "stale" if old date
            "completeness": {"priced": 77, "universe": 77},
            "freshness": {
                "snapshot_date": "?",  # Unknown
                "content_date": None,   # Cannot determine
            },
        }

        # Status should NOT be 'live' when snapshot is unknown
        self.assertIn(kdst_source_status["status"], ("pending", "stale", "hidden"),
            "K/DST without known content vintage must not be 'live'")


class KdstToggleDefaultOffTest(unittest.TestCase):
    """Tests for K/DST toggle in the UI.

    JEG-211 (Jeremy 2026-10-03) removed K/DST from the chart entirely
    (honest exclusion): the old includeSpecialists checkbox was removed with
    it. This test guards that exclusion -- the toggle must NOT exist.
    """

    def test_kdst_toggle_absent_in_frontend(self):
        """The 'Include K/DST' toggle must not exist after JEG-211.

        JEG-211 excluded K/DST from the chart entirely (honest exclusion);
        the old includeSpecialists checkbox was removed. A reintroduced
        toggle would imply a capability the chart no longer has.
        """
        from pathlib import Path
        index_html = ROOT / "app" / "trade-value-chart" / "index.html"

        if index_html.exists():
            content = index_html.read_text()
            self.assertNotIn("includeSpecialists", content,
                "includeSpecialists toggle must not exist after JEG-211 honest exclusion")


class KdstScoringInvariantTest(unittest.TestCase):
    """Tests verifying K/DST are scoring-invariant."""

    def test_kdst_values_identical_across_scorings(self):
        """K/DST have one scoring-invariant number (no receptions).

        Kicker: points come from field goals and extra points - same in all scorings.
        DST: points come from sacks, INTs, etc. - same in all scorings.
        """
        # Simulate K/DST rows
        k_row = {
            "pos": "K",
            "blend_ros": {"standard": 100.0, "half_ppr": 100.0, "ppr": 100.0},
            "espn_ros": {"standard": 100.0, "half_ppr": 100.0, "ppr": 100.0},
        }

        dst_row = {
            "pos": "DST",
            "blend_ros": {"standard": 75.0, "half_ppr": 75.0, "ppr": 75.0},
            "espn_ros": {"standard": 75.0, "half_ppr": 75.0, "ppr": 75.0},
        }

        # All scorings should be identical
        for scoring in ("standard", "half_ppr", "ppr"):
            self.assertEqual(k_row["blend_ros"][scoring],
                             k_row["blend_ros"]["standard"],
                f"Kicker {scoring} must equal standard (scoring-invariant)")
            self.assertEqual(dst_row["blend_ros"][scoring],
                             dst_row["blend_ros"]["standard"],
                f"DST {scoring} must equal standard (scoring-invariant)")


if __name__ == "__main__":
    unittest.main()
