"""JEG-674: Dynasty Daddy puller, hermetic (fixture sliced from the real response)."""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import pull_dynasty_daddy as p  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "dynasty_daddy_sample.json"
RAW = json.loads(FIX.read_text(encoding="utf-8"))
FLOORS = {"QB": 2, "RB": 2, "WR": 2, "TE": 2}
NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def rows():
    return copy.deepcopy(RAW)


def snap(r=None, floors=FLOORS, now=NOW):
    return p.build_snapshot(rows() if r is None else r, now=now, floors=floors)


def code_of(r, **kw):
    with pytest.raises(p.PullError) as e:
        snap(r, **kw)
    return e.value.code


def test_parses_real_slice():
    s = snap()
    assert s["row_count"] == 16
    assert s["dropped"] == {"non_skill_position": 2, "unpriced": 2}
    gibbs = next(r for r in s["rows"] if r["player_name"] == "Jahmyr Gibbs")
    assert gibbs["values"]["1qb"]["value"] == 9999 and gibbs["values"]["sf"]["pos_rank"] == 2
    assert gibbs["ids"]["sleeper_id"] == "9221" and gibbs["ids"]["espn_id"] == "4429795"
    assert s["vintage_date"] == "2026-10-15"


def test_picks_are_dropped():
    assert all(r["pos"] in p.POSITIONS for r in snap()["rows"])


def test_zero_value_is_null_not_zero():
    r = rows()
    target = next(x for x in r if x["position"] == "RB" and x["trade_value"] > 0)
    target["sf_trade_value"] = 0
    s = snap(r)
    row = next(x for x in s["rows"] if x["name_id"] == target["name_id"])
    assert row["values"]["sf"] is None and row["values"]["1qb"]["value"] > 0


def test_ecr_derived_ranks_not_kept():
    blob = json.dumps(snap())
    assert "fantasypros_ros" not in blob and "avg_ros" not in blob
    assert any(r["fanduel_ros"] is not None or r["espn_ros"] is not None for r in snap()["rows"])


def test_stale_data_fails():
    late = datetime(2026, 10, 20, tzinfo=timezone.utc)
    assert code_of(rows(), now=late) == "SOURCE_STALE"


def test_value_out_of_range():
    r = rows()
    r[0]["trade_value"] = 99999
    assert code_of(r) == "VALUE_RANGE"


def test_field_gone_is_layout():
    r = rows()
    for x in r:
        x.pop("sf_trade_value")
    assert code_of(r) == "SOURCE_LAYOUT"


def test_not_a_list_is_layout():
    with pytest.raises(p.PullError) as e:
        p.extract_rows('{"error": "rate limited"}')
    assert e.value.code == "SOURCE_LAYOUT"


def test_position_floor():
    assert code_of(rows(), floors={**FLOORS, "QB": 9}) == "SOURCE_TRUNCATED"


def test_duplicate_name_id_fails():
    r = rows()
    r[1]["name_id"] = r[0]["name_id"]
    assert code_of(r) == "SOURCE_LAYOUT"


def test_fingerprint_moves_with_values():
    r = rows()
    r[0]["trade_value"] -= 1
    assert snap()["fingerprint"] != snap(r)["fingerprint"]


def test_cli_fail_closed_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    out = tmp_path / "out"
    assert p.main(["--out-dir", str(out), "--json", str(bad)]) == 1
    assert not (out / "snapshot.json").exists()
    assert "DYNASTYDADDY PULL FAILED [SOURCE_LAYOUT]" in capsys.readouterr().err
