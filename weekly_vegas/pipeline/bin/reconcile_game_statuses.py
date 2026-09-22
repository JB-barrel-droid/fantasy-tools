"""Reconcile Supabase games table statuses with nflverse results.

The nflverse loader deliberately never updates game rows (status/scores stay
as first recorded), so games inserted as "scheduled" stay that way forever.
This script marks games "final" once nflverse reports scores, keeping the
games-remaining truth used by build_values.py (and K/DST ROS math) correct.

Matching: games.metadata->>'nflverse_game_id' = nflverse game_id.
Idempotent: only updates rows whose status is not already 'final'.

Usage: /home/hatch/workspace/football-signal/.venv/bin/python bin/reconcile_game_statuses.py [--season 2026]
"""
import json
import sys

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-mgmt/bin")
sys.path.insert(0, "/home/hatch/workspace/football-signal")
from mgmt import query  # noqa: E402
import nflreadpy as nfl  # noqa: E402

SEASON = int(sys.argv[sys.argv.index("--season") + 1]) if "--season" in sys.argv else 2026

sched = nfl.load_schedules([SEASON])
final_ids = set()
for r in sched.iter_rows(named=True):
    if r["game_type"] not in ("REG", "POST"):
        continue
    if r["home_score"] is not None:
        final_ids.add(r["game_id"])
print(f"nflverse: {len(final_ids)} final games in {SEASON}", flush=True)

rows = query(
    "SELECT id, status, metadata->>'nflverse_game_id' AS ngid"
    f" FROM games WHERE season = {SEASON};"
)
to_final = [r["id"] for r in rows
            if r["ngid"] in final_ids and r["status"] != "final"]
print(f"supabase: {len(rows)} games, {len(to_final)} need status -> final", flush=True)

updated = 0
for i in range(0, len(to_final), 200):
    chunk = to_final[i:i + 200]
    ids = ",".join(f"'{u}'" for u in chunk)
    res = query(f"UPDATE games SET status='final' WHERE id IN ({ids});")
    updated += len(chunk)
print(f"updated {updated} rows", flush=True)

# Report the resulting games-remaining per team for the build log.
gr = query(
    "SELECT t.abbreviation AS abbr, COUNT(*) AS left"
    " FROM games g JOIN teams t ON t.id IN (g.home_team_id, g.away_team_id)"
    f" WHERE g.season = {SEASON} AND g.status <> 'final'"
    " GROUP BY t.abbreviation ORDER BY t.abbreviation;"
)
print("games remaining:", {r["abbr"]: int(r["left"]) for r in gr}, flush=True)
