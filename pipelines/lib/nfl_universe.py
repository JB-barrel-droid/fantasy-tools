"""JEG-502: the active NFL player universe (QB/RB/WR/TE) for players.json.

Jeremy, 2026-10-09 (GL-20): "All players in the active NFL universe should be
available in the search; even if they are not rostered, on practice squads,
etc. The user knowing they are a 0 is better than the user questioning why
they aren't in the tool."

Source: the Sleeper identity base (data/inputs/sleeper_identity_base.json,
refreshed Tue + Thu by sleeper-identity-refresh.yml from Sleeper
/players/nfl). Dates are measured from the base's own meta.pulled_at, so the
same base always gives the same universe.

Definition of "active" (a QB/RB/WR/TE is in the universe when either holds):
  1. On an NFL team: Sleeper `team` is set (53-man roster, practice squad,
     injured reserve, PUP and the other reserve lists: Sleeper keeps the team
     on all of them) AND a sign of life: a Sleeper news item within
     RECENT_NEWS_DAYS of the pull (`last_news`) or Sleeper status "Practice
     Squad". Sleeper never clears a retired
     player's team (Ben Roethlisberger is still PIT, last news 2022).
  2. Free agent: no team, Sleeper `active` is true, and a news item within
     RECENT_NEWS_DAYS of the pull. This keeps players released or unsigned
     this year and drops long-retired players Sleeper still flags active.

Roster status (one code per player, first match wins):
  practice_squad   Sleeper status "Practice Squad"; or on a team, status
                   Active, with no depth-chart slot (inferred: Sleeper lists
                   practice-squad players this way; roster_status_inferred)
  injured_reserve  on a team, injury_status "IR" (or status Injured Reserve)
  pup              on a team, injury_status "PUP" and status Inactive (or
                   status Physically Unable to Perform)
  reserve          on a team, status Inactive for another reason
                   (suspended, non-football injury, exempt)
  active_roster    on a team, status Active, with a depth-chart slot
  free_agent       no team (rule 2)
"""

from __future__ import annotations

from datetime import date

UNIVERSE_POSITIONS = ("QB", "RB", "WR", "TE")
RECENT_NEWS_DAYS = 365
# Jeremy 2026-10-09 (JEG-502): free agents need news in the last 90 days, so
# long-gone names (Antonio Brown, T.Y. Hilton) drop out of search.
FREE_AGENT_NEWS_DAYS = 90
PLACEHOLDER_NAMES = {"duplicate player"}

# Sleeper team codes that differ from the board's (games_remaining aliases).
_TEAM_FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS"}

STATUS_LABELS = {
    "active_roster": "Active roster",
    "practice_squad": "Practice squad",
    "injured_reserve": "Injured reserve",
    "pup": "Physically unable to perform list",
    "reserve": "Reserve list",
    "free_agent": "Free agent",
}
STATUS_ORDER = tuple(STATUS_LABELS)

DEFINITION = (
    "Every QB/RB/WR/TE Sleeper lists on an NFL team (active roster, practice "
    "squad, injured reserve, PUP and other reserve lists), plus free agents "
    f"Sleeper flags active. A rostered player needs a Sleeper news item in the {RECENT_NEWS_DAYS} "
    f"days before the identity pull, a free agent one in the {FREE_AGENT_NEWS_DAYS} days "
    "(a rostered player may instead carry "
    "Sleeper's practice-squad status), which drops "
    "retired players Sleeper still lists on a team. Practice squad is "
    "Sleeper's status, or inferred for a rostered player with no depth-chart slot.")

def board_team(team: str | None) -> str:
    t = (team or "").strip().upper()
    return _TEAM_FIX.get(t, t)


def roster_status(entry: dict) -> tuple[str, bool]:
    """(status code, inferred?) for one Sleeper base entry already in the universe."""
    status = (entry.get("status") or "").strip()
    injury = (entry.get("injury_status") or "").strip().upper()
    if not entry.get("team"):
        return "free_agent", False
    if status == "Practice Squad":
        return "practice_squad", False
    if injury == "IR" or status == "Injured Reserve":
        return "injured_reserve", False
    if status == "Physically Unable to Perform" or (injury == "PUP" and status != "Active"):
        return "pup", False
    if status != "Active":
        return "reserve", False
    if entry.get("depth_chart_order") in (None, ""):
        return "practice_squad", True
    return "active_roster", False


def _pulled_on(base: dict) -> date:
    pulled = ((base.get("meta") or {}).get("pulled_at") or "")[:10]
    return date.fromisoformat(pulled)


def _recent_news(entry: dict, pulled_on: date, window: int = RECENT_NEWS_DAYS) -> bool:
    try:
        news = date.fromisoformat(entry.get("last_news") or "")
    except ValueError:
        return False
    return (pulled_on - news).days <= window


def in_universe(entry: dict, pulled_on: date) -> bool:
    if entry.get("pos") not in UNIVERSE_POSITIONS:
        return False
    if (entry.get("name") or "").strip().lower() in PLACEHOLDER_NAMES:
        return False
    if entry.get("team"):
        # Sleeper never clears the team of a retired player (Ben
        # Roethlisberger: PIT, last news 2022), so a team needs a sign of
        # life: news this year or Sleeper's own practice-squad status. (An
        # injury designation is not one: Sleeper keeps stale ones, e.g. a
        # 2021 "Questionable" on a player with no news since.)
        return _recent_news(entry, pulled_on) or entry.get("status") == "Practice Squad"
    return bool(entry.get("active")) and _recent_news(entry, pulled_on, FREE_AGENT_NEWS_DAYS)


def active_universe(base: dict) -> dict[str, dict]:
    """{sleeper_id: record} for every player in the universe.

    record: name, pos, team (board code, "" for a free agent), roster_status,
    roster_status_label, roster_status_inferred, injury_status,
    depth_chart_position, depth_chart_order, sleeper_id.
    """
    pulled_on = _pulled_on(base)
    out = {}
    for sid, entry in (base.get("by_sleeper_id") or {}).items():
        if not in_universe(entry, pulled_on):
            continue
        code, inferred = roster_status(entry)
        out[sid] = {
            "sleeper_id": sid,
            "name": entry["name"],
            "pos": entry["pos"],
            "team": board_team(entry.get("team")),
            "roster_status": code,
            "roster_status_label": STATUS_LABELS[code],
            "roster_status_inferred": inferred,
            "injury_status": entry.get("injury_status"),
            "depth_chart_position": entry.get("depth_chart_position"),
            "depth_chart_order": entry.get("depth_chart_order"),
        }
    return out


def assign_keys(universe: dict[str, dict], resolve_key) -> dict[str, int]:
    """{sleeper_id: player_key}.

    resolve_key(name, pos) -> canonical player_key or None (fail-closed, the
    bake's own resolver). A canonical key two universe players both resolve to
    stays with the one on a team when exactly one is. A player with no key is
    left out (every row ties back to the players table, JEG-438): the Sleeper
    identity refresh inserts the missing ones (sync_sleeper_players.py).
    """
    claims: dict[int, list[str]] = {}
    for sid, rec in universe.items():
        key = resolve_key(rec["name"], rec["pos"])
        if key is not None:
            claims.setdefault(int(key), []).append(sid)
    keys: dict[str, int] = {}
    for key, sids in claims.items():
        if len(sids) == 1:
            keys[sids[0]] = key
            continue
        rostered = [s for s in sids if universe[s]["team"]]
        if len(rostered) == 1:
            keys[rostered[0]] = key
    return keys


def unpriced_reason(rec: dict) -> str:
    """Why a universe player has a row but no source prices him."""
    where = f" ({rec['team']})" if rec.get("team") else ""
    return f"{rec['roster_status_label']}{where}. No chart or projection prices this player."


def summary(players: list[dict], base: dict, unkeyed: list[dict] | None = None) -> dict:
    """meta.universe counts for players.json and the fidelity pulse."""
    by_status = {code: 0 for code in STATUS_ORDER}
    n_unknown = 0
    for p in players:
        code = p.get("roster_status")
        if code in by_status:
            by_status[code] += 1
        else:
            n_unknown += 1
    return {
        "definition": DEFINITION,
        "identity_base_pulled_at": (base.get("meta") or {}).get("pulled_at"),
        "n_rows": len(players),
        "n_nfl_active": sum(by_status.values()),
        "by_roster_status": by_status,
        "n_not_in_nfl_active": n_unknown,
        "n_practice_squad_inferred": sum(1 for p in players if p.get("roster_status_inferred")),
        "n_universe_only": sum(1 for p in players if p.get("universe_only")),
        # Universe players with no players-table row yet (no row this bake).
        "n_not_on_players_table": len(unkeyed or []),
        "not_on_players_table": sorted(f"{u['name']} ({u['pos']}, {u['team'] or 'free agent'})"
                                       for u in (unkeyed or []))[:50],
    }
