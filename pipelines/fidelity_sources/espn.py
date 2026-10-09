"""ESPN season projections reader for the fidelity pulse (JEG-480).

Publisher: ESPN's fantasy API (the projections that power the ESPN fantasy
game), read as JSON:

  players  https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/
           segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info
           One request per position slot (QB 0, RB 2, WR 4, TE 6). ESPN only
           honours the player filter (slot, stat sources, sort, limit) when it
           is sent as the X-Fantasy-Filter request header; without it the
           endpoint answers 50 unsorted players. The filter asks for stat
           sources 0 (actuals) and 1 (projections), sorted by ESPN's 2026
           projected total ("1120260"), limit 400 per slot.
  teams    https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026?view=proTeamSchedules_wl
           settings.proTeams: id -> abbrev (and byeWeek). Only used for
           PubRow.team; a failed team read is a note, not an error.

ESPN position ids (player.defaultPositionId), mapped explicitly:
  1 QB, 2 RB, 3 WR, 4 TE (5 K and 16 D/ST are not read).
A player returned for a slot whose defaultPositionId is another position is
skipped there (the slot filter matches eligibility, not position); he is read
under his own position's slot.

Stat ids (ESPN's numbering, restated from the ingest's calibration):
  3 pass yards, 4 pass TDs, 24 rush yards, 25 rush TDs,
  53 receptions, 42 receiving yards, 43 receiving TDs.

Rest-of-season window (restated rule): a week 1..18 counts as played when at
least 20 distinct players carry a non-empty 2026 actuals block for it
(seasonId 2026, statSourceId 0, statSplitTypeId 1, scoringPeriodId = week).
The ROS weeks are 1..18 minus the played weeks (stored as weeks_covered,
e.g. "5-18").

Stage 1 (publisher_vs_stored) unit: rest-of-season fantasy-point TOTALS.
Summing rule (restated, not imported):
  - per player, the weekly projection blocks: seasonId 2026, statSourceId 1,
    statSplitTypeId 1, scoringPeriodId 1..18 (first block wins on a
    duplicate week; ESPN's season block, split 0, is NOT used: it is a
    full-season forecast, not the weekly sum);
  - each stat summed over the ROS weeks (a missing stat or week is 0) and
    rounded to 1 decimal (Python round): r_pass_yds ... r_receptions;
  - half PPR = round(0.04 pass yds + 4 pass TD + 0.1 rush yds + 6 rush TD
                     + 0.5 receptions + 0.1 rec yds + 6 rec TD, 2)
    computed from the rounded components (no INT, fumble or 2-pt terms);
  - full PPR = half + 0.5 x receptions, standard = half - 0.5 x receptions
    (receptions = the rounded ROS receptions), each rounded to 2 decimals.
Stored side: ros_half_ppr and r_receptions of public.espn_season_projections
(full/std by the same reception rule).

Stage 2 (stored_vs_chart) unit: per-game points, printed by the chart with 2
decimals: (ROS total for the scoring) / games remaining, where games
remaining = number of weeks in the row's weeks_covered window, minus 1 when
the player's team's bye falls inside it; a player with no team divides by
the window length. Byes: data/inputs/nfl_byes_2026.json (fixed for the
season; ESPN's proTeams.byeWeek agrees for 32 of 32 teams on 2026-10-08).
The team comes from ctx (see _team_of); a player whose team cannot be
determined returns no chart value (never guessed).
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

_PIPELINES = Path(__file__).resolve().parents[1]
if str(_PIPELINES) not in sys.path:
    sys.path.insert(0, str(_PIPELINES))

import fidelity_pulse as fp  # noqa: E402

SOURCE = "espn"
STORED_TABLE = "espn_season_projections"
SNAPSHOT_COLUMN = "espn_snapshot_date"
STORED_SELECT = "player_key,player_norm,scoring,ros_half_ppr,r_receptions,weeks_covered,espn_snapshot_date,created_at"
CHART_DECIMALS = 2

SEASON = 2026
API = (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/"
       "segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info")
TEAMS_API = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}?view=proTeamSchedules_wl"
SLOTS = ((0, "QB"), (2, "RB"), (4, "WR"), (6, "TE"))
POSITION_IDS = {1: "QB", 2: "RB", 3: "WR", 4: "TE"}
LIMIT = 400
SORT_TOTAL = f"11{SEASON}0"
PLAYED_MIN_PLAYERS = 20

# (ESPN stat id, ROS component, half-PPR points per unit)
STATS = (("3", "r_pass_yds", 0.04), ("4", "r_pass_tds", 4.0),
         ("24", "r_rush_yds", 0.10), ("25", "r_rush_tds", 6.0),
         ("53", "r_receptions", 0.5), ("42", "r_rec_yds", 0.10), ("43", "r_rec_tds", 6.0))

BYES_PATH = _PIPELINES.parent / "data" / "inputs" / f"nfl_byes_{SEASON}.json"
# Team spellings -> the bye table's (Supabase teams.abbreviation) spelling.
TEAM_ALIASES = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX", "STL": "LA", "OAK": "LV", "SD": "LAC"}
WINDOW = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


# --------------------------------------------------------------------------
# Publisher
# --------------------------------------------------------------------------

def player_filter(slot: int) -> dict:
    return {"players": {"filterSlotIds": {"value": [slot]},
                        "filterStatsForSourceIds": {"value": [0, 1]},
                        "sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 3, "value": SORT_TOTAL},
                        "limit": LIMIT, "offset": 0}}


def _accepts_headers(fn) -> bool:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return "headers" in params or any(p.kind is p.VAR_KEYWORD for p in params.values())


def _get(fetch, url: str, headers: dict | None = None):
    """(status, text, url) through the framework's Fetcher (fetch.get) or a plain callable.
    Returns None when headers are needed and the fetcher cannot send them."""
    fn = fetch.get if hasattr(fetch, "get") else fetch
    if headers:
        if not _accepts_headers(fn):
            return None
        return fn(url, headers=headers)
    return fn(url)


def played_weeks(players: list[dict]) -> list[int]:
    """Weeks 1..18 with 2026 actuals for at least PLAYED_MIN_PLAYERS distinct players."""
    seen: dict[int, set] = {}
    for p in players:
        pl = p.get("player") or {}
        for s in pl.get("stats") or []:
            wk = s.get("scoringPeriodId")
            if (s.get("seasonId") == SEASON and s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 1
                    and isinstance(wk, int) and 1 <= wk <= 18 and s.get("stats")):
                seen.setdefault(wk, set()).add(pl.get("id"))
    return sorted(w for w, ids in seen.items() if len(ids) >= PLAYED_MIN_PLAYERS)


def weekly_blocks(pl: dict) -> tuple[dict[int, dict], int]:
    """{week: stats} of the 2026 weekly projection blocks, and the number of duplicate blocks dropped."""
    weeks: dict[int, dict] = {}
    dups = 0
    for s in pl.get("stats") or []:
        wk = s.get("scoringPeriodId")
        if (s.get("seasonId") != SEASON or s.get("statSourceId") != 1 or s.get("statSplitTypeId") != 1
                or not isinstance(wk, int) or not 1 <= wk <= 18):
            continue
        if wk in weeks:
            dups += 1
            continue
        weeks[wk] = {str(k): v for k, v in (s.get("stats") or {}).items()}
    return weeks, dups


def _stat(stats: dict, sid: str) -> float:
    v = stats.get(sid)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0.0
    return float(v)


def ros_totals(weeks: dict[int, dict], ros_weeks: list[int]) -> dict:
    """The summing rule in the module docstring: rounded ROS components and the three scoring totals."""
    comps = {col: round(sum(_stat(weeks.get(w, {}), sid) for w in ros_weeks), 1) for sid, col, _ in STATS}
    half = round(sum(comps[col] * pts for _, col, pts in STATS), 2)
    rec = comps["r_receptions"]
    return {"components": comps, "half": half,
            "full": round(half + 0.5 * rec, 2), "std": round(half - 0.5 * rec, 2)}


def team_map(fetch) -> tuple[dict[int, str], str | None]:
    status, text, _ = _get(fetch, TEAMS_API)
    if status != 200 or not text:
        return {}, f"team list HTTP {status}: {TEAMS_API}; teams left blank"
    try:
        teams = json.loads(text)["settings"]["proTeams"]
        out = {int(t["id"]): str(t["abbrev"]) for t in teams if int(t["id"]) != 0}
    except (ValueError, KeyError, TypeError) as e:
        return {}, f"team list unreadable ({type(e).__name__}); teams left blank"
    return out, None


def parse_players(payloads: dict[str, list[dict]], teams: dict[int, str]) -> tuple[list[fp.PubRow], dict]:
    """PubRows (ROS totals, std|1 / half|1 / full|1) from the per-position payloads; and parse facts."""
    every = [p for ps in payloads.values() for p in ps if isinstance(p, dict)]
    played = played_weeks(every)
    ros_weeks = [w for w in range(1, 19) if w not in played]
    rows: list[fp.PubRow] = []
    facts = {"played_weeks": played, "ros_weeks": ros_weeks, "other_position": 0, "duplicates": 0,
             "no_weekly": [], "dup_blocks": 0}
    if not ros_weeks:
        return rows, facts
    seen: set = set()
    for pos, players in payloads.items():
        for p in players:
            if not isinstance(p, dict):
                continue
            pl = p.get("player") or {}
            if POSITION_IDS.get(pl.get("defaultPositionId")) != pos:
                facts["other_position"] += 1
                continue
            pid = pl.get("id", p.get("id"))
            if pid in seen:
                facts["duplicates"] += 1
                continue
            name = str(pl.get("fullName") or "").strip()
            if not name:
                continue
            weeks, dups = weekly_blocks(pl)
            facts["dup_blocks"] += dups
            if not weeks:
                facts["no_weekly"].append(name)
                continue
            seen.add(pid)
            tot = ros_totals(weeks, ros_weeks)
            team = teams.get(pl.get("proTeamId")) if isinstance(pl.get("proTeamId"), int) else None
            rows.append(fp.PubRow(name, pos, team, {"std|1": f"{tot['std']:.2f}", "half|1": f"{tot['half']:.2f}",
                                                    "full|1": f"{tot['full']:.2f}"}))
    return rows, facts


def read_publisher(fetch) -> dict:
    base = {"rows": [], "url": API, "vintage": None, "dates": {"dateModified": None}, "notes": []}
    payloads: dict[str, list[dict]] = {}
    for slot, pos in SLOTS:
        got = _get(fetch, API, {"Accept": "application/json", "X-Fantasy-Source": "kona",
                                "X-Fantasy-Platform": "kona-web",
                                "X-Fantasy-Filter": json.dumps(player_filter(slot))})
        if got is None:
            return {**base, "error": "the fetcher cannot send request headers; ESPN needs the X-Fantasy-Filter "
                                     "header (without it the API answers 50 unsorted players)"}
        status, text, _ = got
        if status != 200 or not text:
            return {**base, "error": f"ESPN players API HTTP {status} for slot {slot} ({pos})"}
        try:
            players = json.loads(text)["players"]
        except (ValueError, KeyError, TypeError) as e:
            return {**base, "error": f"ESPN players API answer for slot {slot} ({pos}) has no players list "
                                     f"({type(e).__name__})"}
        if not isinstance(players, list) or not players:
            return {**base, "error": f"ESPN players API returned no players for slot {slot} ({pos})"}
        payloads[pos] = players

    teams, team_note = team_map(fetch)
    rows, facts = parse_players(payloads, teams)
    notes = [team_note] if team_note else []
    if not facts["ros_weeks"]:
        return {**base, "notes": notes, "error": "no rest-of-season weeks: every week 1-18 has 2026 actuals"}
    weeks = facts["ros_weeks"]
    notes.append(f"rest-of-season weeks {weeks[0]}-{weeks[-1]} (played weeks with actuals: {facts['played_weeks']})")
    if facts["no_weekly"]:
        notes.append(f"{len(facts['no_weekly'])} players without 2026 weekly projection blocks skipped: "
                     f"{facts['no_weekly'][:5]}")
    if facts["dup_blocks"]:
        notes.append(f"{facts['dup_blocks']} duplicate 2026 weekly projection blocks (first kept)")
    if facts["duplicates"]:
        notes.append(f"{facts['duplicates']} players returned under two slots (first kept)")
    by_pos = {pos: sum(1 for r in rows if r.pos == pos) for _, pos in SLOTS}
    empty = [pos for pos, n in by_pos.items() if n == 0]
    if empty:
        return {**base, "notes": notes, "error": f"no {', '.join(empty)} players with weekly projections parsed"}
    return {**base, "rows": rows, "notes": notes, "error": None,
            "ros_weeks": f"{weeks[0]}-{weeks[-1]}", "counts": by_pos}


# --------------------------------------------------------------------------
# Stored
# --------------------------------------------------------------------------

def _float(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and fp.NUMBER.match(v.strip()):
        return float(v)
    return None


def stored_publisher_values(row: dict) -> dict[str, float]:
    """Stage 1: ROS totals. half = ros_half_ppr; full/std = half +/- 0.5 x r_receptions."""
    half = _float(row.get("ros_half_ppr"))
    if half is None:
        return {}
    out = {"half|1": half}
    rec = _float(row.get("r_receptions"))
    if rec is not None:
        out["full|1"] = half + 0.5 * rec
        out["std|1"] = half - 0.5 * rec
    return out


def parse_window(text) -> tuple[int, int] | None:
    m = WINDOW.match(str(text or ""))
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    return (start, end) if 1 <= start <= end <= 18 else None


def canonical_team(team) -> str:
    t = str(team or "").strip().upper()
    return TEAM_ALIASES.get(t, t)


_BYES: dict[str, int] | None = None


def load_byes(path: Path = BYES_PATH) -> dict[str, int]:
    global _BYES
    if _BYES is None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        _BYES = {canonical_team(t): int(w) for t, w in data["byes"].items()}
    return _BYES


def _dst_team_abbr(reg) -> dict:
    """team_id -> abbreviation from the registry's team-defense tokens: canonical_players.load_registry
    adds each teams.abbreviation as a lower-case token pointing at that team's DST player, whose entry
    carries the team_id. Empty when the registry was built without the teams table."""
    out = {}
    tokens = getattr(reg, "dst_by_token", None) or {}
    by_key = getattr(reg, "by_key", None) or {}
    for tok, key in tokens.items():
        e = by_key.get(key) or {}
        if e.get("team_id") and 2 <= len(tok) <= 3 and tok.isalpha():
            out.setdefault(e["team_id"], set()).add(tok.upper())
    return {tid: abbrs.pop() for tid, abbrs in out.items() if len(abbrs) == 1}


def _team_of(key, ctx: dict) -> tuple[bool, str | None]:
    """(known, team abbreviation or None for a player with no team).

    Order: ctx["team_of"](player_key) if given; else the registry's team_id
    (ctx["ident"].reg.by_key[key]["team_id"]) mapped by ctx["team_abbr"]
    ({team_id: abbreviation}, public.teams) or, failing that, by the
    registry's team-defense tokens."""
    if callable(ctx.get("team_of")):
        team = ctx["team_of"](key)
        return True, (team or None)
    ident = ctx.get("ident")
    reg = getattr(ident, "reg", None)
    e = (getattr(reg, "by_key", None) or {}).get(int(key)) if key is not None and reg is not None else None
    if e is None:
        return False, None
    tid = e.get("team_id")
    if not tid:
        return True, None
    abbr = (ctx.get("team_abbr") or {}).get(tid)
    if abbr is None:
        cache = ctx.setdefault("_espn_dst_team_abbr", _dst_team_abbr(reg))
        abbr = cache.get(tid)
    return (True, abbr) if abbr else (False, None)


def games_remaining(key, window: tuple[int, int], ctx: dict) -> int | None:
    known, team = _team_of(key, ctx)
    if not known:
        return None
    start, end = window
    if team is None:
        return end - start + 1
    byes = ctx.get("byes") or load_byes()
    bye = byes.get(canonical_team(team))
    if bye is None:
        return None
    return (end - start + 1) - (1 if start <= bye <= end else 0)


def stored_chart_values(row: dict, ctx: dict) -> dict[str, float]:
    """Stage 2: per-game points = ROS total / games the team plays in weeks_covered (bye excluded)."""
    totals = stored_publisher_values(row)
    window = parse_window(row.get("weeks_covered"))
    if not totals or window is None:
        return {}
    games = games_remaining(row.get("player_key"), window, ctx)
    if not games:
        return {}
    return {grain: value / games for grain, value in totals.items()}
