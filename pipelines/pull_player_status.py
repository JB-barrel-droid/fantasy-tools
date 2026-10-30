#!/usr/bin/env python3
"""Publish display-only Sleeper status, independently of the identity/value bake.

The existing player-status-history workflow pulls this daily (13:10 UTC and
Sunday 16:30 UTC). No keys, identity resolution, database writes or value math.
Missing ids/statuses stay missing; an empty status never means healthy.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pull_sleeper_identity import build_base, check_base, pull_sleeper

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/inputs/player_status.json"
SCHEMA = "sleeper-player-status-v1"
MIN_TEAM_PLAYERS = 700
POSITIONS = {"QB", "RB", "WR", "TE", "K"}


def build_snapshot(raw, as_of):
    base = build_base(raw, pulled_at=as_of)
    problems = check_base(base)
    players = {
        sid: {"team": p["team"], "pos": p["pos"], "injury_status": p.get("injury_status")}
        for sid, p in base["by_sleeper_id"].items() if p.get("team")
    }
    snapshot = {"schema": SCHEMA, "source": "Sleeper",
                "source_url": "https://api.sleeper.app/v1/players/nfl",
                "as_of": as_of, "by_sleeper_id": players}
    problems.extend(check_snapshot(snapshot))
    if problems:
        raise ValueError("FAIL-CLOSED: " + "; ".join(problems))
    return snapshot


def check_snapshot(snapshot):
    problems = []
    if snapshot.get("schema") != SCHEMA:
        problems.append("unknown status schema")
    try:
        at = datetime.fromisoformat(snapshot["as_of"].replace("Z", "+00:00"))
        if at.utcoffset() is None:
            raise ValueError("missing timezone")
    except (KeyError, TypeError, ValueError, AttributeError):
        problems.append("status has no dated, timezone-aware as_of")
    players = snapshot.get("by_sleeper_id")
    if not isinstance(players, dict) or len(players) < MIN_TEAM_PLAYERS:
        problems.append(f"fewer than {MIN_TEAM_PLAYERS} team-backed players; partial pull?")
        return problems
    for sid, p in players.items():
        if (not sid.isdecimal() or not isinstance(p, dict) or not p.get("team")
                or p.get("pos") not in POSITIONS
                or (p.get("injury_status") is not None and not isinstance(p["injury_status"], str))):
            problems.append(f"invalid status record for Sleeper id {sid}")
            break
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--raw-out", type=Path, help="ephemeral raw response for the existing history saver; avoids a second API call")
    args = parser.parse_args(argv)
    raw = pull_sleeper()
    # Stamp the successful observation, never the build/deploy time.
    snapshot = build_snapshot(raw, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if args.raw_out:
        args.raw_out.write_text(json.dumps(raw), encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(args.out)
    print(f"Sleeper status as of {snapshot['as_of']}: {len(snapshot['by_sleeper_id'])} team-backed players -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
