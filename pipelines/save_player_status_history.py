#!/usr/bin/env python3
"""Daily Sleeper roster and injury status history (JEG-521 G4 c).

public.injuries keeps only the latest status per player (unique on name,
team, source), so games missed cannot be reconstructed from it. This writes
one row per QB/RB/WR/TE per day to public.player_status_history (approved by
Jeremy 2026-10-09; supabase/migrations/jeg521_g4_weekly_store_20261009.sql).

Who is kept: every Sleeper player at QB/RB/WR/TE who is on an NFL team, or
who carries an injury status (a released injured player is still news).
Columns are Sleeper's own fields, unchanged: status, injury_status,
injury_body_part, injury_start_date, practice_participation,
depth_chart_position, depth_chart_order, news_updated, plus team and position
that day. player_key is resolved by ids (pipelines/lib/player_key_index.py);
an unresolved player is still stored with player_key null, so history is
never lost to an identity gap.

snapshot_date is the America/Chicago date. A second run the same day
overwrites that day's row (upsert on snapshot_date, sleeper_id), so the
Sunday pre-kickoff run replaces the morning row with the game-day status.

Fail closed: a pull with fewer than MIN_ROWS kept players writes nothing.

Usage: python3 pipelines/save_player_status_history.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from player_key_index import PlayerIndex  # noqa: E402

SLEEPER_BASE = ROOT / "data" / "inputs" / "sleeper_identity_base.json"
SUMMARY = ROOT / "output" / "player-status-history.json"
POSITIONS = ("QB", "RB", "WR", "TE")
# 2026-10-09 identity base: 4,234 fantasy-position players, 837 of them on a
# team at QB/RB/WR/TE; the first live dry run (2026-10-10) kept 957 with the
# injured free agents. Well below that is a truncated pull. (The earlier
# floor of 1500 assumed ~2,400 rostered and failed every real pull.)
MIN_ROWS = 700
FIELDS = ("status", "injury_status", "injury_body_part", "injury_start_date",
          "practice_participation", "depth_chart_position", "depth_chart_order")


def _date(v):
    if v in (None, ""):
        return None
    s = str(v)
    return s[:10] if len(s) >= 10 and s[4] == "-" else None


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def build_rows(sleeper: dict, index: PlayerIndex, snapshot_date: str, fetched_at: str):
    rows, how = [], {}
    for sid, p in sleeper.items():
        pos = p.get("position") or (p.get("fantasy_positions") or [None])[0]
        if pos not in POSITIONS:
            continue
        if not p.get("team") and not p.get("injury_status"):
            continue
        name = (p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
        e, why = index.resolve_sleeper(sid, name, pos)
        how[why if e else "unresolved"] = how.get(why if e else "unresolved", 0) + 1
        news = p.get("news_updated")
        row = {
            "snapshot_date": snapshot_date, "source": "sleeper", "sleeper_id": str(sid),
            "player_key": e["player_key"] if e else None, "full_name": name,
            "position": pos, "team": p.get("team"),
            "status": p.get("status"), "injury_status": p.get("injury_status"),
            "injury_body_part": p.get("injury_body_part"),
            "injury_start_date": _date(p.get("injury_start_date")),
            "practice_participation": p.get("practice_participation"),
            "depth_chart_position": p.get("depth_chart_position"),
            "depth_chart_order": _int(p.get("depth_chart_order")),
            "news_updated": (datetime.fromtimestamp(int(news) / 1000, tz=timezone.utc)
                             .isoformat(timespec="seconds") if _int(news) else None),
            "fetched_at": fetched_at,
        }
        rows.append(row)
    rows.sort(key=lambda r: (len(r["sleeper_id"]), r["sleeper_id"]))
    return rows, how


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summary", type=Path, default=SUMMARY)
    a = ap.parse_args(argv)
    from pull_sleeper_identity import pull_sleeper  # noqa: PLC0415
    try:
        import sbclient as sb  # noqa: PLC0415
    except ImportError:
        import gh_sbclient as sb  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    snapshot_date = now.astimezone(ZoneInfo("America/Chicago")).date().isoformat()
    sleeper = pull_sleeper()
    players = sb.get_all("players", "?select=id,player_key,full_name,position,active,metadata")
    index = PlayerIndex(players, json.load(open(SLEEPER_BASE)))
    rows, how = build_rows(sleeper, index, snapshot_date, now.isoformat(timespec="seconds"))
    summary = {"run_at": now.isoformat(timespec="seconds"), "snapshot_date": snapshot_date,
               "rows": len(rows), "resolved_by": how, "dry_run": a.dry_run,
               "status_counts": {}}
    for r in rows:
        k = r["injury_status"] or r["status"] or "none"
        summary["status_counts"][k] = summary["status_counts"].get(k, 0) + 1
    if len(rows) < MIN_ROWS:
        print(f"FAILED: only {len(rows)} players kept (floor {MIN_ROWS}); nothing written",
              file=sys.stderr)
        return 1
    if not a.dry_run:
        for i in range(0, len(rows), 500):
            sb.post("player_status_history", rows[i:i + 500],
                    params="?on_conflict=snapshot_date,sleeper_id",
                    prefer="resolution=merge-duplicates,return=minimal")
        summary["written"] = len(rows)
    a.summary.parent.mkdir(parents=True, exist_ok=True)
    a.summary.write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
