"""Sleeper/RotoWire projection id mapping and loader (JEG-949). No network, no Supabase."""
import csv
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
import sleeper_projection_idmap as im  # noqa: E402
import sleeper_projection_loader as ld  # noqa: E402

SNAP = [
    {"player_key": 10, "full_name": "Tyler Conklin", "position": "TE", "gsis_id": "00-0034270"},
    {"player_key": 11, "full_name": "Ryan Izzo", "position": "TE", "gsis_id": "00-0034439"},
    {"player_key": 12, "full_name": "Justin Herbert", "position": "QB", "gsis_id": "00-0036355"},
    {"player_key": 13, "full_name": "Sam Darnold", "position": "QB", "gsis_id": "00-0033106"},
    {"player_key": 14, "full_name": "Pat Example", "position": "WR", "gsis_id": ""},
]
DP = {"sleeper": {"5133": {"00-0034270"}, "5094": {"00-0034439"}, "6797": {"00-0036355"}},
      "sportradar": {"sr-conklin": {"00-0034270"}}, "espn": {}}
SLEEPER = {"5133": {"sportradar_id": "sr-conklin"}, "6797": {}}


def pp(name, pos, gsis=(), ppr=100.0):
    return {"name": name, "pos": pos, "gsis": set(gsis), "rows": 10, "seasons": {"2024"}, "ppr": ppr}


def by_id(rows):
    return {r["sleeper_id"]: r for r in rows}


def test_gsis_from_dynastyprocess_when_sleeper_has_none():
    m = by_id(im.build_idmap({"6797": pp("Justin Herbert", "QB")}, SLEEPER, DP, SNAP))["6797"]
    assert (m["status"], m["gsis_id"], m["player_key"], m["gsis_source"]) == ("matched", "00-0036355", 12, "dp_sleeper")


def test_swapped_sleeper_gsis_is_a_conflict_not_a_silent_wrong_join():
    # Sleeper's own gsis for Conklin (5133) is Izzo's; DynastyProcess says otherwise.
    m = by_id(im.build_idmap({"5133": pp("Tyler Conklin", "TE", ["00-0034439"])}, SLEEPER, DP, SNAP))["5133"]
    assert m["status"] == "conflict" and m["player_key"] == "" and m["gsis_id"] == ""


def test_conflict_guard_catches_first_answer_wins_breakage(monkeypatch):
    """Simulated broken resolver (first answer wins) maps Conklin to Izzo; the real one must not."""
    def first_wins(sid, proj_gsis, rec, dp):
        g = sorted(proj_gsis)
        return (g[0], "sleeper", "gsis") if g else ("", "", "unmapped")
    monkeypatch.setattr(im, "resolve_gsis", first_wins)
    broken = by_id(im.build_idmap({"5133": pp("Tyler Conklin", "TE", ["00-0034439"])}, SLEEPER, DP, SNAP))["5133"]
    assert broken["status"] != "conflict"          # the broken state is detectable by this test
    monkeypatch.undo()
    good = by_id(im.build_idmap({"5133": pp("Tyler Conklin", "TE", ["00-0034439"])}, SLEEPER, DP, SNAP))["5133"]
    assert good["status"] == "conflict"


def test_name_mismatch_is_review_not_matched():
    m = by_id(im.build_idmap({"77": pp("Someone Else", "QB", ["00-0036355"])}, {}, DP, SNAP))["77"]
    assert m["status"] == "name_review" and m["player_key"] == ""


def test_exact_name_candidate_is_suggestion_only():
    m = by_id(im.build_idmap({"88": pp("Pat Example", "WR")}, {}, DP, SNAP))["88"]
    assert m["status"] == "unmapped" and m["player_key"] == "" and m["suggested_player_key"] == 14


def test_gsis_not_in_players_keeps_gsis_without_key():
    m = by_id(im.build_idmap({"99": pp("Retired Guy", "WR", ["00-0000001"])}, {}, DP, SNAP))["99"]
    assert (m["status"], m["gsis_id"], m["player_key"]) == ("gsis_not_in_players", "00-0000001", "")


def test_match_report_counts_rows_and_gsis_rate():
    rows = im.build_idmap({"6797": pp("Justin Herbert", "QB"), "99": pp("Retired Guy", "WR", ["00-0000001"]),
                           "5133": pp("Tyler Conklin", "TE", ["00-0034439"])}, SLEEPER, DP, SNAP)
    rep = im.match_report(rows)
    assert rep["all"]["rows"] == 30 and rep["all"]["rows_matched"] == 10
    assert rep["gsis_resolved_row_rate"]["all"] == round(20 / 30, 4)


def _write_proj(path, rows):
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["season", "week", "sleeper_id", "gsis_id", "name", "pos", "team",
                                           "opponent", "company", "updated_at", "pts_std", "pts_half_ppr", "pts_ppr"])
        w.writeheader()
        for r in rows:
            w.writerow({"opponent": "", "company": "rotowire", "updated_at": "", "pts_std": 1, "pts_half_ppr": 1, **r})


def test_loader_uses_idmap_gsis_not_the_projection_file_column(tmp_path):
    p = tmp_path / "p.csv.gz"
    _write_proj(p, [{"season": 2024, "week": 1, "sleeper_id": "5133", "gsis_id": "00-0034439",
                     "name": "Tyler Conklin", "pos": "TE", "team": "NYJ", "pts_ppr": 7.5}])
    idmap = {"5133": {"sleeper_id": "5133", "status": "matched", "gsis_id": "00-0034270", "player_key": "10"}}
    r = ld.load_projections(proj_path=p, idmap=idmap)[0]
    assert (r["gsis_id"], r["player_key"]) == ("00-0034270", 10)


def test_loader_hides_identity_for_non_usable_status(tmp_path):
    p = tmp_path / "p.csv.gz"
    _write_proj(p, [{"season": 2024, "week": 1, "sleeper_id": "5133", "gsis_id": "00-0034439",
                     "name": "Tyler Conklin", "pos": "TE", "team": "NYJ", "pts_ppr": 7.5}])
    idmap = {"5133": {"sleeper_id": "5133", "status": "conflict", "gsis_id": "", "player_key": ""}}
    r = ld.load_projections(proj_path=p, idmap=idmap)[0]
    assert r["gsis_id"] == "" and r["player_key"] is None


def test_pairs_never_zero_fill_missing_actuals():
    rows = [{"season": 2024, "week": 1, "gsis_id": "g1", "player_key": 1, "projection": 9.0},
            {"season": 2024, "week": 1, "gsis_id": "g2", "player_key": 2, "projection": 8.0},
            {"season": 2024, "week": 1, "gsis_id": "", "player_key": None, "projection": 7.0}]
    pairs, cov = ld.projection_actual_pairs(rows=rows, actuals={(2024, 1, "g1"): 12.0})
    assert [p["actual"] for p in pairs] == [12.0]
    assert cov == {"projection_rows": 3, "no_identity": 1, "no_actual_row": 1, "paired": 1}


# ---- committed artifacts ----
def test_committed_idmap_covers_every_projected_player_and_matches_snapshot():
    idmap = ld.load_idmap()
    with gzip.open(ld.PROJ, "rt") as fh:
        projected = {r["sleeper_id"] for r in csv.DictReader(fh)}
    assert set(idmap) == projected
    snap = {r["player_key"]: r for r in json.loads((ROOT / "data/inputs/players_identity_snapshot.json").read_text())}
    for m in idmap.values():
        if m["status"] == "matched":
            assert snap[int(m["player_key"])]["gsis_id"] == m["gsis_id"]
        else:
            assert m["player_key"] == ""


def test_committed_idmap_has_no_duplicate_player_key_or_gsis():
    matched = [m for m in ld.load_idmap().values() if m["status"] == "matched"]
    assert len({m["player_key"] for m in matched}) == len(matched)
    assert len({m["gsis_id"] for m in matched}) == len(matched)


def test_committed_report_gsis_rate_floor_and_known_conflicts_stay_unmapped():
    rep = json.loads((ROOT / "data/inputs/sleeper_projection_idmap_report.json").read_text())
    assert rep["gsis_resolved_row_rate"]["qb_rb_wr_te"] >= 0.99
    idmap = ld.load_idmap()
    assert idmap["5133"]["status"] == "conflict" and idmap["5094"]["status"] == "conflict"
