"""The proposed nflverse history loader builds clean rows from the repo files (JEG-525 item e)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines"))
import load_nflverse_history as L  # noqa: E402


def test_rows_match_the_repo_files_and_pass_the_checks():
    actuals, weeks = L.actual_rows(), L.team_week_rows()
    assert len(actuals) == 61977
    assert len({(r["season"], r["team"]) for r in weeks}) == 352
    assert L.check(actuals, weeks) == []


def test_check_catches_a_duplicate_and_an_orphan_week():
    weeks = [{"season": 2020, "week": 1, "team": "BUF"}]
    row = {"season": 2020, "week": 1, "gsis_id": "00-1", "player_name": "x", "position": "RB", "team": "BUF",
           "actual_std": 1.0, "actual_half": 1.0, "actual_ppr": 1.0}
    assert any("duplicate" in p for p in L.check([row, dict(row)], weeks))
    assert any("did not play" in p for p in L.check([{**row, "week": 2}], weeks))


def test_dry_run_writes_nothing(capsys):
    assert L.main([]) == 0
    assert "dry run" in capsys.readouterr().out
