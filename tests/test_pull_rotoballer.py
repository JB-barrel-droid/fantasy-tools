"""JEG-671: RotoBaller trade value puller, hermetic (fixtures sliced from the real Week 5 article)."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import pull_rotoballer as p  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
BODY = (FIX / "rotoballer_week5_sample.html").read_text(encoding="utf-8")
SEARCH = (FIX / "rotoballer_search_sample.html").read_text(encoding="utf-8")
WEEK5_DAY = date(2026, 10, 9)  # NFL week 5
URL = "https://example.test/week5"


def snap(body=BODY, today=WEEK5_DAY, **kw):
    return p.build_snapshot(body, URL, today=today, **kw)


def code_of(body=BODY, today=WEEK5_DAY, **kw):
    with pytest.raises(p.PullError) as e:
        snap(body, today, **kw)
    return e.value.code


def test_parses_real_page():
    s = snap()
    assert (s["article_week"], s["season"], s["published_at"]) == (5, 2026, "2026-10-09")
    assert s["row_count"] == 200 and s["scoring"] is None
    top = s["rows"][0]
    assert (top["player_name"], top["pos"], top["rank"], top["trade_value"]) == ("Jahmyr Gibbs", "RB", 1, 100)
    assert top["rotoballer_id"] == 23200


def test_name_suffix_after_link_is_kept():
    names = {r["player_name"] for r in snap()["rows"]}
    assert "Kenneth Walker III" in names


def test_newer_nfl_week_is_stale():
    assert code_of(today=date(2026, 10, 16)) == "SOURCE_STALE"  # NFL week 6, article Week 5


def test_other_season_is_stale():
    assert code_of(BODY.replace("(2026)", "(2025)", 1)) == "SOURCE_STALE"


def test_stale_guard_catches_week1_article():
    old = BODY.replace("Week 5", "Week 1", 1)
    assert code_of(old, today=date(2026, 10, 9)) == "SOURCE_STALE"
    assert snap(old, today=date(2026, 9, 10))["article_week"] == 1


def test_title_week_gone_is_layout():
    assert code_of(BODY.replace("Week 5", "Latest", 1)) == "SOURCE_LAYOUT"


def test_table_gone_is_layout():
    assert code_of(BODY.replace("<table", "<div").replace("</table>", "</div>")) == "SOURCE_LAYOUT"


def test_tiny_body_is_blocked():
    assert code_of("<html><title>Week 5 (2026)</title>login</html>") == "SOURCE_BLOCKED"


def test_value_out_of_range():
    assert code_of(BODY.replace("<td>100</td>", "<td>1000</td>", 1)) == "VALUE_RANGE"


def test_bad_row_is_layout():
    assert code_of(BODY.replace("<td>100</td>", "<td>n/a</td>", 1)) == "SOURCE_LAYOUT"


def test_position_floor():
    assert code_of(BODY.replace("<td>QB</td>", "<td>DST</td>")) == "SOURCE_TRUNCATED"


def test_non_skill_rows_dropped_not_kept():
    s = snap(BODY.replace("<td>TE</td>", "<td>K</td>", 3), floors={"TE": 1})
    assert s["dropped"]["non_skill_position"] == 3
    assert all(r["pos"] in p.POSITIONS for r in s["rows"])


def test_discovery_picks_newest_week_of_season():
    url = p.newest_article_url(SEARCH, 2026)
    assert "week-5-" in url and url.endswith("/1961768")
    assert p.newest_article_url(SEARCH, 2025) is None
    assert "dynasty" not in url


def test_fingerprint_moves_with_values():
    assert snap()["fingerprint"] != snap(BODY.replace("<td>92</td>", "<td>91</td>", 1))["fingerprint"]


def test_cli_fail_closed_writes_nothing(tmp_path, capsys):
    rc = p.main(["--out-dir", str(tmp_path), "--html", str(FIX / "rotoballer_week5_sample.html"), "--today", "2026-10-16"])
    assert rc == 1 and not (tmp_path / "snapshot.json").exists()
    assert "ROTOBALLER PULL FAILED [SOURCE_STALE]" in capsys.readouterr().err


def test_cli_writes_snapshot(tmp_path):
    rc = p.main(["--out-dir", str(tmp_path), "--html", str(FIX / "rotoballer_week5_sample.html"), "--today", "2026-10-09"])
    assert rc == 0
    assert json.loads((tmp_path / "snapshot.json").read_text())["row_count"] == 200
