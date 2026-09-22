"""No-market-read flags: fantasy-relevant players the books refuse to price.

User-approved 2026-09-12. This is a NEW signal category, not a points
delta — it flags players where ECR (experts) has a real projection but
Vegas posted no production prop lines at all.

Definition
----------
- Relevant: ECR full-PPR projection >= positional floor (QB 10 / RB 7 /
  WR 7 / TE 5) — the same floors as the points-signal gate.
- No market read: zero non-TD prop markets in the latest (week-scoped)
  odds pull. Non-TD markets are the production line markets
  (player_pass_yds, player_rush_yds, player_receptions,
  player_reception_yds). Anytime-TD-only counts as NO read — a TD line
  alone is not a pricing of the player's production. A QB with only a
  player_pass_tds line likewise counts as no read (a TD line is a TD
  line).
- Timing: the flag is only meaningful at a late-pregame snapshot.
  Evaluated at signal-computation time and ALWAYS stamped with
  market_read_as_of (the newest prop recorded_at actually consumed).
  Midweek absences may just be unposted lines; the authoritative
  evaluation is the Sunday-morning weekly chain run.

Rationale (revealed preference): a book leaves handle on the table for
a relevant player only when the pricing risk beats the hold — i.e. the
player's production is too uncertain to price without getting picked
off. The absence of a line IS the variance signal.

Rules
-----
- Informational only. post_worthy is ALWAYS False — no approved post
  format exists for this category, so flag rows must never enter the
  post queue.
- Persisted per week (no_market_read_flags) so the Tuesday scorecard
  can validate the hypothesis: does this cohort boom/bust more than
  same-tier prop'd players?
"""

import sys
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
if BASE not in sys.path:
    sys.path.insert(0, BASE)
SB = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
if SB not in sys.path:
    sys.path.insert(0, SB)

import sbclient  # noqa: E402
from engine.snapshot import norm, load_players, load_week_games  # noqa: E402

# Relevance bar: same positional floors as the points-signal gate.
POS_FLOOR = {"QB": 10.0, "RB": 7.0, "WR": 7.0, "TE": 5.0}

# Production line markets. TD markets (player_anytime_td, player_pass_tds)
# deliberately excluded: a TD line alone is not a pricing of production.
PRODUCTION_MARKETS = frozenset({
    "player_pass_yds", "player_rush_yds",
    "player_receptions", "player_reception_yds",
})


def compute_flags(ecr_proj, meta, official, ecr_by_pos, player_props,
                  market_read_as_of, started_teams=None):
    """Build no-market-read flag dicts.

    ecr_proj: {norm_name: {'name','std','half','ppr','td_exp'}} (ECR feed)
    meta: {norm_name: {'name','team','pos'}} (ECR ranks file)
    official: {norm_name: 'QB12'} display rank strings
    ecr_by_pos: {pos: {norm_name: numeric rank}}
    player_props: {raw_player_name: {market: entry}} (week-scoped pull)
    market_read_as_of: newest prop recorded_at consumed (ISO string)
    started_teams: {team abbreviation} whose game has already kicked off.
        Once a game starts, books pull props — "no line" then means "game
        over", not "books refuse to price". Those players are excluded.

    Returns flag dicts shaped like disagreement signals (so they ride the
    signals JSON), with category='no_market_read' and post_worthy=False.
    """
    started_teams = started_teams or set()
    has_read = {
        norm(p) for p, mkts in (player_props or {}).items()
        if set(mkts or {}) & PRODUCTION_MARKETS
    }
    flags = []
    for k, e in ecr_proj.items():
        m = meta.get(k)
        if not m:
            continue
        if m.get("team") in started_teams:
            continue
        pos = m.get("pos")
        floor = POS_FLOOR.get(pos)
        if floor is None:
            continue
        ppr = e.get("ppr")
        if ppr is None or ppr < floor:
            continue
        if k in has_read:
            continue
        flags.append({
            "category": "no_market_read",
            "player_key": k,
            "pos": pos,
            "name": m.get("name", e.get("name", k)),
            "team": m.get("team", ""),
            # standard signal keys, neutral where there is no Vegas side
            "vegas_std": None,
            "vegas_half": None,
            "vegas_ppr": None,
            "expert_std": e.get("std"),
            "expert_half": e.get("half"),
            "expert_ppr": round(ppr, 2),
            "pts_delta_ppr": None,
            "vegas_pos_rank": None,
            "ecr_pos_rank": (ecr_by_pos.get(pos) or {}).get(k),
            "ecr_official": official.get(k, ""),
            "n_pos": None,
            "delta": 0,
            "abs_delta": 0,
            "direction": "no_market",
            "post_worthy": False,
            "worthy_reason": ("no market read — informational only "
                              "(no approved post format)"),
            "market_read_as_of": market_read_as_of,
        })
    flags.sort(key=lambda f: -(f["expert_ppr"] or 0))
    return flags


def started_teams_for_week(season, week, now=None):
    """{team abbreviation} whose week game has already kicked off.

    Objective clock rule (starts_at <= now, UTC) — game-status fields lag.
    """
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    games_by_id, _ = load_week_games(season, week)
    teams = {t["id"]: t["abbreviation"] for t in
             sbclient.get_all("teams", "?select=id,abbreviation")}
    out = set()
    for g in games_by_id.values():
        sa = g.get("starts_at")
        if not sa:
            continue
        try:
            dt = datetime.fromisoformat(str(sa))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt <= now:
            out.add(teams.get(g.get("home_team_id")))
            out.add(teams.get(g.get("away_team_id")))
    return out


def _resolve_ids(flags, season, week):
    """Best-effort player_id / game_id for each flag.

    player_id via the shared players-table crosswalk (name-based, offensive
    rows preferred); None for rookies with no players row (same known gap
    as the FP loader). game_id via team abbreviation -> team_id -> the
    week's game for that team.
    """
    by_name, by_loose, _by_id = load_players()
    teams = {t["abbreviation"]: t["id"] for t in
             sbclient.get_all("teams", "?select=id,abbreviation")}
    _games_by_id, games_by_team = load_week_games(season, week)
    for f in flags:
        pl = by_name.get(f["player_key"])
        f["player_id"] = pl["id"] if pl else None
        team_id = teams.get(f["team"])
        g = games_by_team.get(team_id) if team_id else None
        f["game_id"] = g["id"] if g else None
    return flags


def persist_flags(flags, season, week):
    """Idempotent per-week persist: replace this week's rows, then insert.

    Never called in dry-run (verification-only must not mutate). Does not
    touch post_queue.
    """
    _resolve_ids(flags, season, week)
    sbclient.delete("no_market_read_flags",
                    f"?season=eq.{season}&week=eq.{week}")
    rows = [{
        "season": season,
        "week": week,
        "player_name": f["name"],
        "player_id": f.get("player_id"),
        "game_id": f.get("game_id"),
        "position": f["pos"],
        "team": f["team"],
        "ecr_points": f["expert_ppr"],
        "ecr_pos_rank": f.get("ecr_pos_rank"),
        "market_read_as_of": f.get("market_read_as_of"),
    } for f in flags]
    for i in range(0, len(rows), 200):
        sbclient.post("no_market_read_flags", rows[i:i + 200])
    return len(rows)
