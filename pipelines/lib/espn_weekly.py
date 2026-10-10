"""ESPN weekly blocks -> per player per week rows (JEG-521 G4 a/b).

pull_espn_projections.py already fetches, for every QB/RB/WR/TE, ESPN's
weekly actual blocks (statSourceId 0) and weekly projection blocks
(statSourceId 1), split 1 = one scoring period (one NFL week). Before G4 it
used the actuals only to detect played weeks and dropped them. This module
turns both into plain rows so save_espn_weekly.py can store them.

Pure functions, no network: tests/test_espn_weekly_store.py pins them.

Stat ids: the seven calibrated 2026-09-16 against nflverse (see the pull's
docstring) plus 20 = interceptions thrown and 58 = targets. Interceptions are
needed because public.v_player_game_actuals scores -2 per interception; id 20
is checked by the saver against the nflverse rows already in
public.player_game_stats for 2026 weeks 1-4 (the comparison is in the run
summary, so a wrong id shows up as QB disagreements, not silently).

Scoring for stored points follows public.v_player_game_actuals exactly
(pass yards / 25, pass TD 4, interception -2, rush and receiving yards / 10,
rush and receiving TD 6, receptions 0 / 0.5 / 1). It is NOT the ESPN leg's
half-PPR in pull_espn_projections.W, which leaves interceptions out; stored
projections and stored actuals use one formula so projection minus actual is
a like-for-like number.

Per-game basis (MR-20): a weekly projection is ESPN's projection for that
scheduled week of the player's team. It is 0 (or the block is missing) when
ESPN projects him out or his team is on bye, so the rows are per TEAM week,
not per game played. The basis is written on every stored row.
"""
from __future__ import annotations

SEASON_ID = 2026

# ESPN stat id -> the stat key public.player_game_stats.stats uses (nflverse
# naming), so ESPN rows and the existing rows read the same way.
STAT_KEYS = (
    ("3", "passing_yards"),
    ("4", "passing_tds"),
    ("20", "interceptions"),
    ("24", "rushing_yards"),
    ("25", "rushing_tds"),
    ("53", "receptions"),
    ("42", "receiving_yards"),
    ("43", "receiving_tds"),
    ("58", "targets"),
)

POS_IDS = {"QB": 1, "RB": 2, "WR": 3, "TE": 4}

ACTUAL, PROJECTION = 0, 1
BASIS = "team_week"  # MR-20: see module docstring

# ESPN team abbreviations -> public.teams.abbreviation
TEAM_ALIASES = {"WSH": "WAS", "JAC": "JAX", "LAR": "LA"}
# public.teams carries stale duplicate rows (canonical_players._STALE_ABBR)
STALE_TEAM_ABBR = {"LAR": "LA", "JAC": "JAX", "STL": "LA", "OAK": "LV", "SD": "LAC", "WSH": "WAS"}

RECEPTION_POINTS = {"standard": 0.0, "half_ppr": 0.5, "full_ppr": 1.0}


def points(stats: dict, scoring: str) -> float:
    """Fantasy points from a stats dict, the v_player_game_actuals formula."""
    g = lambda k: float(stats.get(k) or 0)  # noqa: E731
    base = (g("passing_yards") / 25 + g("passing_tds") * 4
            - g("interceptions") * 2
            + g("rushing_yards") / 10 + g("rushing_tds") * 6
            + g("receiving_yards") / 10 + g("receiving_tds") * 6)
    return base + g("receptions") * RECEPTION_POINTS[scoring]


def map_stats(raw: dict) -> dict:
    """ESPN {stat id: value} -> {passing_yards: ..., ...}; absent ids are 0."""
    raw = {str(k): v for k, v in (raw or {}).items()}
    return {key: _num(raw.get(sid, 0)) for sid, key in STAT_KEYS}


def _num(v):
    try:
        x = float(v or 0)
    except (TypeError, ValueError):
        return 0
    return int(x) if x == int(x) else round(x, 4)


def weekly_rows(payloads_by_pos: dict, source: int, team_map: dict,
                season: int = SEASON_ID) -> tuple[list[dict], list[str]]:
    """Rows for one stat source (ACTUAL or PROJECTION) from the pull's payloads.

    payloads_by_pos: {"QB": [espn player entry, ...], ...} exactly as
    pull_espn_projections.fetch_position returns them.
    team_map: {ESPN proTeamId: abbreviation}.

    One row per (ESPN player id, week): the first block wins (the pull's
    rule); duplicates and position-slot mismatches are reported, not kept.
    The team is the block's own proTeamId when ESPN gives one (a player
    traded mid-season keeps the team he played for that week), else the
    player's current team.
    """
    rows, notes, seen = [], [], set()
    for pos, entries in payloads_by_pos.items():
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            pl = entry.get("player") or {}
            pid = pl.get("id", entry.get("id"))
            name = pl.get("fullName", "")
            if pid is None:
                notes.append(f"no-espn-id: {name!r}")
                continue
            if pl.get("defaultPositionId") != POS_IDS.get(pos):
                continue  # the pull reports these (pos-slot-mismatch)
            player_team = team_map.get(_int(pl.get("proTeamId")), "")
            for s in pl.get("stats") or []:
                if (s.get("seasonId") != season or s.get("statSourceId") != source
                        or s.get("statSplitTypeId") != 1):
                    continue
                wk = s.get("scoringPeriodId")
                if not isinstance(wk, int) or not 1 <= wk <= 18:
                    continue
                raw = s.get("stats") or {}
                if source == ACTUAL and not raw:
                    continue  # an empty actual block is not a stat line
                key = (str(pid), wk)
                if key in seen:
                    notes.append(f"dup-block: {name!r} week {wk} source {source}; first kept")
                    continue
                seen.add(key)
                team = team_map.get(_int(s.get("proTeamId")), "") or player_team
                rows.append({
                    "espn_id": str(pid), "name": name, "pos": pos,
                    "team": TEAM_ALIASES.get(team, team), "week": wk,
                    "season": season, "stats": map_stats(raw),
                })
    rows.sort(key=lambda r: (r["week"], r["pos"], r["espn_id"]))
    return rows, notes


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0
