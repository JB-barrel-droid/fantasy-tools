"""Sleeper weekly projection rows are parsed without the network (JEG-540)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines"))
import pull_sleeper_projections as sp  # noqa: E402


def test_rows_keep_points_map_gsis_and_skip_missing():
    entries = [
        {"player_id": "8154", "team": "ATL", "opponent": "LAR", "company": "rotowire", "updated_at": None,
         "player": {"first_name": "Brian", "last_name": "Robinson", "position": "RB"},
         "stats": {"pts_std": 3.86, "pts_half_ppr": 4.1, "pts_ppr": 4.35, "rush_yd": 19.3}},
        {"player_id": "999", "player": {"first_name": "No", "last_name": "Points"}, "stats": {"rush_yd": 2}},
    ]
    rows = sp.rows_from(entries, 2025, 5, "RB", {"8154": "00-0037746"})
    assert len(rows) == 1
    r = rows[0]
    assert (r["season"], r["week"], r["sleeper_id"], r["gsis_id"]) == (2025, 5, "8154", "00-0037746")
    assert (r["name"], r["pos"], r["team"], r["opponent"]) == ("Brian Robinson", "RB", "ATL", "LAR")
    assert (r["pts_std"], r["pts_half_ppr"], r["pts_ppr"]) == (3.86, 4.1, 4.35)


def test_parse_seasons_ranges_and_lists():
    assert sp.parse_seasons("2018-2020,2025") == [2018, 2019, 2020, 2025]
    assert sp.parse_seasons("1-3") == [1, 2, 3]
