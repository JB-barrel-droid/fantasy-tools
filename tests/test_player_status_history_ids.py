"""JEG-575: status rows resolve through the live Sleeper record's gsis_id."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

from player_key_index import PlayerIndex  # noqa: E402
from save_player_status_history import build_rows  # noqa: E402

PLAYERS = [
    {"id": "u1", "player_key": 1, "full_name": "Zed Quarry", "position": "WR",
     "metadata": {"gsis_id": "00-0099999"}},
]


def _live(**kw):
    return {"position": "WR", "team": "KC", "full_name": "Totally Different Name", **kw}


def test_live_gsis_resolves_player_with_no_base_entry():
    index = PlayerIndex(PLAYERS, {"by_sleeper_id": {}})
    rows, how = build_rows({"900": _live(gsis_id="00-0099999")}, index, "2026-10-12", "t")
    assert rows[0]["player_key"] == 1
    assert how == {"gsis_id": 1}


def test_without_live_gsis_same_record_is_unresolved():
    index = PlayerIndex(PLAYERS, {"by_sleeper_id": {}})
    rows, how = build_rows({"900": _live()}, index, "2026-10-12", "t")
    assert rows[0]["player_key"] is None
    assert how == {"unresolved": 1}


def test_live_gsis_wins_over_base():
    base = {"by_sleeper_id": {"900": {"gsis_id": "00-0000000"}}}
    index = PlayerIndex(PLAYERS + [{"id": "u2", "player_key": 2, "full_name": "Other", "position": "WR",
                                    "metadata": {"gsis_id": "00-0000000"}}], base)
    rows, _ = build_rows({"900": _live(gsis_id="00-0099999")}, index, "2026-10-12", "t")
    assert rows[0]["player_key"] == 1
