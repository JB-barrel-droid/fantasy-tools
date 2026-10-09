#!/usr/bin/env python3
"""JEG-502: add active NFL players missing from public.players.

Every players.json row ties back to the canonical players table (JEG-438).
The active NFL universe (pipelines/lib/nfl_universe.py, from the Sleeper
identity base) holds players the table has never seen: undrafted rookies,
practice-squad call-ups, late signings. This step inserts them so the bake
can give them a row under a real player_key.

Rules (additive only: an existing row is never updated, re-keyed or removed):
  - A universe player gets a row only when the bake's own resolver
    (resolve(name, pos), then a unique skill-position name) finds no
    players-table row for him, and no row already carries his Sleeper id
    (metadata.sleeper_id).
  - Skipped, never guessed: a name the table already holds at a skill
    position (a new namesake would make position-less lookups of the
    existing player ambiguous), and two missing players sharing one name.
    Both are listed in the output for review.
  - player_key = the table's max + 1, in Sleeper-id order. full_name is
    Sleeper's spelling; metadata carries sleeper_id, team and the source.

Runs in sleeper-identity-refresh.yml after the base is refreshed (main only).

Usage: python3 pipelines/sync_sleeper_players.py [--write] [--base P]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import (  # noqa: E402
    load_registry, norm_player_name, resolve, resolve_skill, SKILL_POSITIONS,
)
import nfl_universe  # noqa: E402

BASE = ROOT / "data" / "inputs" / "sleeper_identity_base.json"
SOURCE = "sleeper-identity-refresh (JEG-502)"
_STALE_ABBR = {"LAR": "LA", "JAC": "JAX", "STL": "LA", "OAK": "LV", "SD": "LAC"}


def resolve_key(name, pos, registry):
    """The bake's rule (bake_players.nfl_universe_keys)."""
    key = resolve(name, position=pos, registry=registry)
    if key is None:
        key = resolve_skill(name, registry=registry)
    if key is None:
        return None
    return key if (registry.by_key.get(key) or {}).get("position") in SKILL_POSITIONS else None


def plan(base: dict, registry, known_sleeper_ids: set[str], team_ids: dict[str, str]) -> dict:
    """{"insert": [row, ...], "skipped": [{sleeper_id, name, pos, reason}, ...]}."""
    universe = nfl_universe.active_universe(base)
    missing = {sid: rec for sid, rec in universe.items()
               if sid not in known_sleeper_ids and resolve_key(rec["name"], rec["pos"], registry) is None}
    names: dict[str, list[str]] = {}
    for sid, rec in missing.items():
        names.setdefault(norm_player_name(rec["name"]), []).append(sid)
    skill_names = {norm_player_name(e["full_name"]) for e in registry.by_key.values()
                   if e["position"] in SKILL_POSITIONS}
    next_key = max(registry.by_key, default=0) + 1
    insert, skipped = [], []
    for sid in sorted(missing, key=lambda s: (len(s), s)):
        rec = missing[sid]
        norm = norm_player_name(rec["name"])
        reason = None
        if norm in skill_names:
            reason = "the players table already has a skill-position player with this name"
        elif len(names[norm]) > 1:
            reason = "two missing players share this name"
        if reason:
            skipped.append({"sleeper_id": sid, "name": rec["name"], "pos": rec["pos"], "reason": reason})
            continue
        team = rec["team"]
        insert.append({
            "player_key": next_key,
            "full_name": rec["name"],
            "position": rec["pos"],
            "active": True,
            "team_id": team_ids.get(team) if team else None,
            "metadata": {"sleeper_id": sid, "team": team or None, "source": SOURCE,
                         "roster_status": rec["roster_status"]},
        })
        next_key += 1
    return {"insert": insert, "skipped": skipped, "n_universe": len(universe), "n_missing": len(missing)}


def _team_ids(sb) -> dict[str, str]:
    out = {}
    for t in sorted(sb.get_all("teams", "?select=id,abbreviation&abbreviation=not.is.null"),
                    key=lambda t: str(t["id"])):
        abbr = (t.get("abbreviation") or "").strip().upper()
        if abbr and abbr not in _STALE_ABBR and abbr not in out:
            out[abbr] = t["id"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--write", action="store_true", help="insert (default: dry run)")
    args = ap.parse_args(argv)
    import sbclient  # noqa: PLC0415 -- gh_sbclient shim in CI
    base = json.loads(args.base.read_text(encoding="utf-8"))
    registry = load_registry()
    known = {str(r["sleeper_id"]) for r in sb_get_sleeper_ids(sbclient)}
    result = plan(base, registry, known, _team_ids(sbclient))
    print(f"universe {result['n_universe']}, not on the players table {result['n_missing']}: "
          f"insert {len(result['insert'])}, skipped {len(result['skipped'])}")
    for s in result["skipped"]:
        print(f"  skipped {s['name']} ({s['pos']}, sleeper {s['sleeper_id']}): {s['reason']}")
    for r in result["insert"][:10]:
        print(f"  + {r['player_key']} {r['full_name']} {r['position']} {r['metadata']['team']}")
    if args.write and result["insert"]:
        sbclient.post("players", result["insert"], prefer="return=minimal")
        print(f"inserted {len(result['insert'])} players")
    elif not args.write:
        print("dry run: nothing written")
    return 0


def sb_get_sleeper_ids(sb) -> list[dict]:
    return sb.get_all("players", "?select=sleeper_id:metadata->>sleeper_id&metadata->>sleeper_id=not.is.null")


if __name__ == "__main__":
    sys.exit(main())
