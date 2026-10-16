"""JEG-684: NumberFire ROS puller, hermetic (fixture sliced from the real GraphQL response)."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import pull_numberfire_ros as p  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "numberfire_ros_sample.json"
DOC = json.loads(FIX.read_text(encoding="utf-8"))
FLOORS = {"QB": 4, "RB": 4, "WR": 4, "TE": 4}


def rows():
    return copy.deepcopy(DOC["data"]["getProjections"])


def snap(r=None, floors=FLOORS):
    return p.build_snapshot(rows() if r is None else r, floors=floors)


def code_of(r, floors=FLOORS):
    with pytest.raises(p.PullError) as e:
        snap(r, floors)
    return e.value.code


def test_parses_real_slice_and_drops_unpriced():
    s = snap()
    assert s["row_count"] == 16 and s["dropped"]["unpriced"] == 3
    allen = next(r for r in s["rows"] if r["player_name"] == "Josh Allen")
    assert (allen["pos"], allen["team"], allen["pass_cmp"], allen["pass_att"]) == ("QB", "BUF", 274.2, 398.92)
    assert allen["rush_yd"] == 467.48 and allen["fantasy"] == 284.82 and allen["overall_rank"] == 1


def test_zero_projection_is_unpriced_not_zero():
    assert all(r["fantasy"] > 0 for r in snap()["rows"])


def test_graphql_errors_are_layout():
    with pytest.raises(p.PullError) as e:
        p.extract_rows(json.dumps({"errors": [{}]}).ljust(p.MIN_BODY))
    assert e.value.code == "SOURCE_LAYOUT"


def test_empty_list_is_layout():
    with pytest.raises(p.PullError) as e:
        p.extract_rows(json.dumps({"data": {"getProjections": []}}))
    assert e.value.code == "SOURCE_LAYOUT"


def test_field_gone_is_layout():
    r = rows()
    for x in r:
        x.pop("targets")
    assert code_of(r) == "SOURCE_LAYOUT"


def test_bad_attempts_string_is_layout():
    r = rows()
    r[0]["completionsAttempts"] = "n/a"
    assert code_of(r) == "SOURCE_LAYOUT"


def test_negative_stat_is_range():
    r = rows()
    r[0]["rushingYards"] = -5
    assert code_of(r) == "VALUE_RANGE"


def test_fantasy_scale_change_is_range():
    r = rows()
    r[0]["fantasy"] = 2840.0
    assert code_of(r) == "VALUE_RANGE"


def test_position_floor():
    assert code_of(rows(), floors={**FLOORS, "TE": 5}) == "SOURCE_TRUNCATED"


def test_duplicate_id_fails():
    r = rows()
    r[1]["player"]["numberFireId"] = r[0]["player"]["numberFireId"]
    assert code_of(r) == "SOURCE_LAYOUT"


def test_non_skill_rows_dropped():
    r = rows()
    r.append({**copy.deepcopy(r[0]), "player": {"numberFireId": 1, "name": "X K", "position": "K"}})
    assert snap(r)["dropped"]["non_skill_position"] == 1


def test_fingerprint_moves_with_values():
    r = rows()
    r[0]["fantasy"] += 1
    assert snap()["fingerprint"] != snap(r)["fingerprint"]


def test_cli_fail_closed_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"errors":[{}]}')
    out = tmp_path / "out"
    assert p.main(["--out-dir", str(out), "--json", str(bad)]) == 1
    assert not (out / "snapshot.json").exists()
    assert "NUMBERFIRE PULL FAILED [SOURCE_LAYOUT]" in capsys.readouterr().err
