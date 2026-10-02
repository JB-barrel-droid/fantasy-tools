#!/usr/bin/env python3
"""Unit tests for pipelines/check_source_vintage.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add pipelines to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

# Import the module under test
import check_source_vintage


class TestGetFixtureVintage:
    """Tests for get_fixture_vintage function."""

    def test_fantasycalc_uses_content_vintage(self):
        """fantasycalc should read content_vintage key."""
        fixture_data = {
            "sources": {
                "fantasycalc": {
                    "content_vintage": "Week 4",
                    "other_field": "value"
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("fantasycalc", fixture_data)
        assert result == "Week 4"

    def test_usatoday_uses_content_vintage(self):
        """usatoday should read content_vintage key."""
        fixture_data = {
            "sources": {
                "usatoday": {
                    "content_vintage": "2026-09-29",
                    "other_field": "value"
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("usatoday", fixture_data)
        assert result == "2026-09-29"

    def test_fantasypros_uses_content_vintage(self):
        """fantasypros should read content_vintage key."""
        fixture_data = {
            "sources": {
                "fantasypros": {
                    "content_vintage": "2026-09-29",
                    "other_field": "value"
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("fantasypros", fixture_data)
        assert result == "2026-09-29"

    def test_espn_uses_espn_snapshot(self):
        """ESPN should read espn_snapshot key."""
        fixture_data = {
            "sources": {
                "espn": {
                    "espn_snapshot": "2026-09-30",
                    "other_field": "value"
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("espn", fixture_data)
        assert result == "2026-09-30"

    def test_cbs_uses_content_vintage(self):
        """CBS should read content_vintage key."""
        fixture_data = {
            "sources": {
                "cbs": {
                    "content_vintage": "Week 4",
                    "other_field": "value"
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("cbs", fixture_data)
        assert result == "Week 4"

    def test_cbsros_uses_vintage(self):
        """CBSROS should read vintage key."""
        fixture_data = {
            "sources": {
                "cbsros": {
                    "vintage": "2026-09-30",
                    "other_field": "value"
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("cbsros", fixture_data)
        assert result == "2026-09-30"

    def test_razzball_uses_vintage(self):
        """Razzball should read vintage key."""
        fixture_data = {
            "sources": {
                "razzball": {
                    "vintage": "2026-10-01",
                    "other_field": "value"
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("razzball", fixture_data)
        assert result == "2026-10-01"

    def test_missing_source_returns_none(self):
        """Missing source should return None."""
        fixture_data = {"sources": {}}
        result = check_source_vintage.get_fixture_vintage("fantasycalc", fixture_data)
        assert result is None

    def test_fallback_to_vintage_key(self):
        """Should fallback to vintage key if preferred key is missing."""
        fixture_data = {
            "sources": {
                "fantasycalc": {
                    "vintage": "Week 3"
                    # no content_vintage
                }
            }
        }
        result = check_source_vintage.get_fixture_vintage("fantasycalc", fixture_data)
        assert result == "Week 3"


class TestCheckAllSources:
    """Tests for check_all_sources function."""

    @patch.object(check_source_vintage, "DEFAULT_FIXTURE_PATH")
    @patch.object(check_source_vintage, "get_current_vintage")
    def test_changed_detected(self, mock_get_vintage, mock_fixture_path):
        """Should report changed=True when vintage differs."""
        # Setup mock fixture path
        mock_fixture_path.exists.return_value = True
        mock_fixture_path.read_text.return_value = json.dumps({
            "sources": {
                "fantasycalc": {
                    "content_vintage": "Week 3"
                }
            }
        })

        # Current DB returns different vintage
        mock_get_vintage.return_value = "Week 5"

        result = check_source_vintage.check_all_sources()

        assert result["changed"] is True
        assert result["sources"]["fantasycalc"]["changed"] is True
        assert result["sources"]["fantasycalc"]["current_vintage"] == "Week 5"
        assert result["sources"]["fantasycalc"]["fixture_vintage"] == "Week 3"

    @patch.object(check_source_vintage, "DEFAULT_FIXTURE_PATH")
    @patch.object(check_source_vintage, "get_current_vintage")
    def test_unchanged_same_vintage(self, mock_get_vintage, mock_fixture_path):
        """Should report changed=False when vintage matches."""
        mock_fixture_path.exists.return_value = True
        mock_fixture_path.read_text.return_value = json.dumps({
            "sources": {
                "fantasycalc": {"content_vintage": "Week 4"},
                "usatoday": {"content_vintage": "Week 4"},
                "fantasypros": {"content_vintage": "Week 4"},
                "espn": {"espn_snapshot": "Week 4"},
                "cbs": {"content_vintage": "Week 4"},
                "cbsros": {"vintage": "Week 4"},
                "razzball": {"vintage": "Week 4"},
            }
        })

        # Current DB returns same vintage for every chain source
        mock_get_vintage.return_value = "Week 4"

        result = check_source_vintage.check_all_sources()

        assert result["changed"] is False
        assert result["sources"]["fantasycalc"]["changed"] is False
        assert result["sources"]["fantasycalc"]["current_vintage"] == "Week 4"
        assert result["sources"]["fantasycalc"]["fixture_vintage"] == "Week 4"

    @patch.object(check_source_vintage, "DEFAULT_FIXTURE_PATH")
    @patch.object(check_source_vintage, "get_current_vintage")
    def test_undeterminable_vintage_reports_changed(self, mock_get_vintage, mock_fixture_path):
        """Should report changed=True when vintage cannot be determined (error case).

        This tests the fail-closed path: if we can't determine the vintage,
        we should treat it as a change to trigger a rebuild.
        """
        mock_fixture_path.exists.return_value = True
        mock_fixture_path.read_text.return_value = json.dumps({
            "sources": {
                "fantasycalc": {
                    "content_vintage": "Week 4"
                }
            }
        })

        # get_current_vintage raises SystemExit (fail-closed)
        mock_get_vintage.side_effect = SystemExit("Fail closed: vintage undeterminable")

        result = check_source_vintage.check_all_sources()

        assert result["changed"] is True
        assert result["sources"]["fantasycalc"]["changed"] is True
        assert result["sources"]["fantasycalc"]["error"] is not None
        assert result["sources"]["fantasycalc"]["current_vintage"] is None

    @patch.object(check_source_vintage, "DEFAULT_FIXTURE_PATH")
    def test_missing_fixture_raises(self, mock_fixture_path):
        """Should raise SystemExit when fixture is missing."""
        mock_fixture_path.exists.return_value = False

        with pytest.raises(SystemExit, match="Fixture not found"):
            check_source_vintage.check_all_sources()


class TestDeriveDbVintage:
    """Tests for _derive_db_vintage function."""

    def test_derives_date_from_source_content_date(self):
        """Should derive vintage from source_content_date."""
        rows = [
            {"source_content_date": "2026-09-29"},
            {"source_content_date": "2026-09-29"},
        ]
        result = check_source_vintage._derive_db_vintage(rows, "fantasycalc")
        assert result == "2026-09-29"

    def test_derives_date_from_espn_snapshot_date(self):
        """Should derive vintage from espn_snapshot_date for ESPN."""
        rows = [
            {"espn_snapshot_date": "2026-09-30"},
            {"espn_snapshot_date": "2026-09-30"},
        ]
        result = check_source_vintage._derive_db_vintage(rows, "espn")
        assert result == "2026-09-30"

    def test_derives_week_from_week_column(self):
        """Should derive vintage from week column."""
        rows = [
            {"week": "4"},
            {"week": "4"},
        ]
        result = check_source_vintage._derive_db_vintage(rows, "fantasycalc")
        assert result == "Week 4"

    def test_mixed_dates_fails_closed(self):
        """Should raise SystemExit on mixed dates."""
        rows = [
            {"source_content_date": "2026-09-29"},
            {"source_content_date": "2026-09-30"},
        ]
        with pytest.raises(SystemExit, match="Fail closed: mixed"):
            check_source_vintage._derive_db_vintage(rows, "fantasycalc")

    def test_mixed_weeks_fails_closed(self):
        """Should raise SystemExit on mixed weeks."""
        rows = [
            {"week": "3"},
            {"week": "4"},
        ]
        with pytest.raises(SystemExit, match="Fail closed: mixed"):
            check_source_vintage._derive_db_vintage(rows, "fantasycalc")

    def test_no_vintage_fails_closed(self):
        """Should raise SystemExit when vintage is undeterminable."""
        rows = [{}, {}]
        with pytest.raises(SystemExit, match="Fail closed: vintage undeterminable"):
            check_source_vintage._derive_db_vintage(rows, "fantasycalc")


class TestMain:
    """Tests for main function."""

    @patch("check_source_vintage.check_all_sources")
    def test_json_output(self, mock_check, capsys):
        """Should output JSON when --json flag is provided."""
        mock_check.return_value = {
            "changed": True,
            "sources": {
                "fantasycalc": {
                    "current_vintage": "Week 5",
                    "fixture_vintage": "Week 4",
                    "changed": True
                }
            }
        }

        # argparse reads the real sys.argv via its own sys import, so patch
        # the real argv (patching check_source_vintage.sys does not affect it).
        with patch.object(sys, "argv", ["check_source_vintage.py", "--json"]):
            with pytest.raises(SystemExit) as exc:
                check_source_vintage.main()

        # changed=True -> exit 1
        assert exc.value.code == 1
        printed = capsys.readouterr().out
        assert '"changed": true' in printed
        assert '"fantasycalc"' in printed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
