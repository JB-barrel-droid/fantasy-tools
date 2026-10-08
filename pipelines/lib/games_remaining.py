"""Games remaining per team for the ESPN rest-of-season window.

ESPN's rest-of-season projection (data/inputs/espn_projections.csv) sums the
weekly projection blocks over the weeks it has not seen played; the CSV
records that window per row as ``weeks_covered`` ("5-18"). A per-game rate is
that sum divided by the games the team actually plays inside the same window:
the window length, minus one if the team's bye falls inside it.

This is the one place that number is computed. bake_players.py (players.json
espn_ppg / blend_ppg / pm_ppg / rz_ros, the browser's live pools) and
build_ddf_two_tier_leg.py (the baked ESPN DDF leg) both call it, so the
browser and the baked leg divide by the same count.

It deliberately does not depend on anyone marking games final (GAP-GAMES-
REMAINING-STALE: Supabase public.games stopped at week 2 final, which gave
15 or 16 games where the truth was 13). Byes are fixed for the season and
live in data/inputs/nfl_byes_2026.json; the bake cross-checks that table
against the Supabase schedule and fails closed when they disagree.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BYES_PATH = ROOT / "data" / "inputs" / "nfl_byes_2026.json"

# Source spellings -> the bye table's (Supabase teams.abbreviation) spelling.
TEAM_ALIASES = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX", "STL": "LA",
                "OAK": "LV", "SD": "LAC"}

_WINDOW_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


def canonical_team(team):
    t = (team or "").strip().upper()
    return TEAM_ALIASES.get(t, t)


def load_byes(path=BYES_PATH):
    """Return ({team: bye_week}, (first_week, last_week)). Fail closed."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    first, last = data["regular_season_weeks"]
    byes = {canonical_team(t): int(w) for t, w in data["byes"].items()}
    if len(byes) != 32:
        raise SystemExit(f"FAIL-CLOSED: bye table {path} has {len(byes)} teams, not 32.")
    bad = {t: w for t, w in byes.items() if not first <= w <= last}
    if bad:
        raise SystemExit(f"FAIL-CLOSED: bye weeks outside {first}-{last}: {bad}")
    return byes, (first, last)


def parse_window(text):
    m = _WINDOW_RE.match(text or "")
    if not m:
        raise SystemExit(f"FAIL-CLOSED: unparseable weeks_covered {text!r}.")
    start, end = int(m.group(1)), int(m.group(2))
    if not 1 <= start <= end <= 18:
        raise SystemExit(f"FAIL-CLOSED: weeks_covered {text!r} outside weeks 1-18.")
    return start, end


def window_from_rows(rows):
    """The single ROS window ("5-18") every ESPN row covers. Fail closed on
    a missing column or on rows that disagree (a mixed pull)."""
    windows = {(r.get("weeks_covered") or "").strip() for r in rows}
    windows.discard("")
    if len(windows) != 1:
        raise SystemExit(
            "FAIL-CLOSED: ESPN weeks_covered must be one window across the CSV, "
            f"got {sorted(windows)[:5]}; per-game rates would be undeterminable.")
    return parse_window(next(iter(windows)))


def window_from_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return window_from_rows(csv.DictReader(f))


def games_in_window(team, window, byes):
    """Games ``team`` plays in weeks window[0]..window[1]; None if the team is
    unknown (never guessed)."""
    t = canonical_team(team)
    if t not in byes:
        return None
    start, end = window
    return (end - start + 1) - (1 if start <= byes[t] <= end else 0)


def games_by_team(window, byes):
    return {t: games_in_window(t, window, byes) for t in sorted(byes)}


def schedule_problems(byes, weeks, game_rows, team_abbr):
    """Compare the bye table with a schedule (Supabase public.games rows with
    week/home_team_id/away_team_id). Each team must play exactly one game in
    every regular-season week except its bye. Returns a list of problems."""
    first, last = weeks
    played = {}
    for g in game_rows:
        wk = g.get("week")
        if not isinstance(wk, int) or not first <= wk <= last:
            continue
        for tid in (g.get("home_team_id"), g.get("away_team_id")):
            t = canonical_team(team_abbr.get(tid))
            if t:
                played.setdefault(t, []).append(wk)
    problems = []
    for t, bye in sorted(byes.items()):
        wks = played.get(t, [])
        expected = [w for w in range(first, last + 1) if w != bye]
        if sorted(wks) != expected:
            missing = sorted(set(expected) - set(wks))
            extra = sorted(w for w in set(wks) if wks.count(w) > 1 or w == bye)
            problems.append(f"{t}: bye table says week {bye}; schedule missing "
                            f"weeks {missing}, doubled/bye weeks {extra}")
    unknown = sorted(set(played) - set(byes))
    if unknown:
        problems.append(f"schedule teams not in bye table: {unknown}")
    return problems
