"""Strict identity boundary for normalized FantasyPros Market intake rows.

The live HTML row adapter is not yet verified. This accepts the shared
source-snapshot row vocabulary, not guessed FantasyPros field names.
FantasyPros player IDs remain source IDs: never interpret one as player_key.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

PIPELINES = Path(__file__).resolve().parents[1]
if str(PIPELINES) not in sys.path:
    sys.path.insert(0, str(PIPELINES))

from lib.canonical_players import load_registry, resolve_with_reason  # noqa: E402
from lib.nfl_universe import board_team as norm_team  # noqa: E402


class IdentityError(ValueError):
    pass


def map_rows(rows, *, players_path):
    """Map every skill row or raise; no partial list can escape on a miss.

    Shared canonical resolver/aliases first, then exact position AND team
    against canonical keyed records. Even a sole name match must pass both.
    K/DST remain in the raw capture, and are excluded from chart rows with a
    receipt, matching the chart's existing treatment. Null values survive.
    """
    records = json.loads(Path(players_path).read_text())["players"]
    by_key = {}
    for player in records:
        key = player.get("player_key")
        if isinstance(key, bool) or not isinstance(key, int) or key in by_key:
            raise IdentityError("invalid or duplicate canonical player_key")
        by_key[key] = player
    registry = load_registry(rows=[{
        "player_key": key, "full_name": p["name"], "position": p["pos"],
        "active": p.get("active", True),
    } for key, p in by_key.items()])
    mapped, excluded = [], []
    source_ids, keys = set(), set()
    for row in rows:
        source_id = row.get("source_player_id")
        if isinstance(source_id, bool) or not isinstance(source_id, (str, int)) or not str(source_id).strip():
            raise IdentityError("missing FantasyPros playerId")
        token = str(source_id)
        if token in source_ids:
            raise IdentityError(f"duplicate FantasyPros playerId {token}")
        source_ids.add(token)
        pos = row.get("pos")
        if pos in ("K", "DST"):
            excluded.append({"source_player_id": source_id, "pos": pos, "reason": "K/DST excluded from chart"})
            continue
        team = row.get("team")
        if pos not in ("QB", "RB", "WR", "TE") or not isinstance(team, str) or not team.strip():
            raise IdentityError(f"{token}: position and team required")
        value = row.get("native_value")
        if "native_value" not in row or (value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= 1000
        )):
            raise IdentityError(f"{token}: invalid native market value")
        key, reason = resolve_with_reason(row.get("player_name"), position=pos, registry=registry)
        if key is None:
            raise IdentityError(f"{token}: canonical identity {reason}")
        player = by_key[key]
        if player["pos"] != pos or norm_team(player.get("team")) != norm_team(team):
            raise IdentityError(f"{token}: canonical position/team mismatch")
        if player["player_key"] in keys:
            raise IdentityError(f"{token}: multiple FantasyPros IDs resolve to player_key {player['player_key']}")
        keys.add(player["player_key"])
        mapped.append({**row, "player_key": player["player_key"], "canonical_name": player["name"]})
    return mapped, excluded
