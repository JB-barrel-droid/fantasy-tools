#!/usr/bin/env python3
"""JEG-1354: keep public.players.active in step with the active NFL universe.

players.active was set once, by the archived nflverse loader
(archive/2026-10-07/weekly_vegas/pipeline/loaders/nflverse.py: `status ==
"ACT"` on the first roster season it saw, "No upserts"), and nothing has
refreshed it since. On 2026-10-29 it was false for 857 of 1,517 QB/RB/WR/TE
rows, starters included (Brock Purdy, CeeDee Lamb, Christian McCaffrey).
The resolver every saver uses reads it (canonical_players.resolve_with_reason:
a position conflict on an all-inactive name is skipped silently, JEG-539), so
a stale false hides a real conflict.

"Active" here is the one definition the bake already uses: in the active NFL
universe (pipelines/lib/nfl_universe.py, from the committed Sleeper identity
base). Rules, ids first and never a guess:

  - Set true: a universe player resolves to a row through PlayerIndex
    (Sleeper id, then gsis id, then the position-checked canonical name
    resolver, the same chain player_status_history uses). A row two universe
    players resolve to is skipped and listed.
  - Set false: only a row tied by id (metadata.sleeper_id, or the gsis id on
    the Sleeper base record) to a Sleeper skill player who is not in the
    universe, and that no universe player resolves to. A row reached by name
    only, or not reached at all, keeps its flag: a missed name match must
    not turn a current player off.
  - Nothing else on the row changes. Non-skill rows are never touched.
  - Refuses to write when the plan would change more than MAX_CHANGE_SHARE
    of the skill rows (a broken base or players read).

Usage: python3 pipelines/sync_players_active.py [--write] [--base P]
       (default: dry run; prints counts and samples)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import nfl_universe  # noqa: E402
from player_key_index import PlayerIndex  # noqa: E402

BASE = ROOT / "data" / "inputs" / "sleeper_identity_base.json"
SKILL = set(nfl_universe.UNIVERSE_POSITIONS)
ID_HOWS = {"sleeper_id", "gsis_id"}
MAX_CHANGE_SHARE = 0.75
PATCH_BATCH = 200


def plan(base: dict, players: list[dict]) -> dict:
    """{"activate": [row], "deactivate": [row], "skipped": [...], counts}.

    A row is {"player_key", "full_name", "position", "sleeper_id", "how"}.
    """
    index = PlayerIndex(players, base)
    universe = nfl_universe.active_universe(base)
    skill_rows = {e["player_key"]: e for e in index.by_key.values() if e["position"] in SKILL}

    claims: dict[int, list[tuple[str, str]]] = {}
    unresolved = 0
    for sid, rec in universe.items():
        e, how = index.resolve_sleeper(sid, rec["name"], rec["pos"])
        if e is None or e["player_key"] not in skill_rows:
            unresolved += 1
            continue
        claims.setdefault(e["player_key"], []).append((sid, how))

    in_universe, skipped = {}, []
    for key, hits in claims.items():
        if len(hits) == 1:
            in_universe[key] = hits[0]
        else:
            skipped.append({"player_key": key, "full_name": skill_rows[key]["full_name"],
                            "reason": "two universe players resolve to this row: "
                                      + ", ".join(sorted(s for s, _ in hits))})
    claimed = set(claims)

    # Rows tied by id to a Sleeper skill player who is out of the universe.
    out_by_id: dict[int, str] = {}
    for sid, entry in (base.get("by_sleeper_id") or {}).items():
        if sid in universe or entry.get("pos") not in SKILL:
            continue
        # resolve_sleeper still falls back to the base record's own name when the
        # name argument is empty; the how-not-in-ID_HOWS check below is the guard.
        e, how = index.resolve_sleeper(sid, "", entry.get("pos"))
        if e is None or how not in ID_HOWS or e["player_key"] not in skill_rows:
            continue
        if e["player_key"] in claimed:
            continue
        out_by_id.setdefault(e["player_key"], sid)

    def row(key, sid, how):
        e = skill_rows[key]
        return {"player_key": key, "full_name": e["full_name"], "position": e["position"],
                "sleeper_id": sid, "how": how}

    activate = [row(k, sid, how) for k, (sid, how) in sorted(in_universe.items())
                if not skill_rows[k]["active"]]
    deactivate = [row(k, sid, "id, out of universe") for k, sid in sorted(out_by_id.items())
                  if skill_rows[k]["active"]]
    return {
        "activate": activate, "deactivate": deactivate, "skipped": skipped,
        "n_skill_rows": len(skill_rows), "n_universe": len(universe),
        "n_universe_resolved": len(in_universe), "n_universe_unresolved": unresolved,
        "n_out_by_id": len(out_by_id),
        "n_unchanged_unreached": len(set(skill_rows) - set(in_universe) - set(out_by_id)),
    }


def too_big(result: dict) -> bool:
    n = len(result["activate"]) + len(result["deactivate"])
    return result["n_skill_rows"] == 0 or n > MAX_CHANGE_SHARE * result["n_skill_rows"]


def write(sb, result: dict) -> None:
    for flag, rows in ((True, result["activate"]), (False, result["deactivate"])):
        keys = [r["player_key"] for r in rows]
        for i in range(0, len(keys), PATCH_BATCH):
            chunk = ",".join(str(k) for k in keys[i:i + PATCH_BATCH])
            sb.patch("players", {"active": flag}, f"?player_key=in.({chunk})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--write", action="store_true", help="patch players.active (default: dry run)")
    args = ap.parse_args(argv)
    import sbclient  # noqa: PLC0415 -- gh_sbclient shim in CI
    base = json.loads(args.base.read_text(encoding="utf-8"))
    players = sbclient.get_all("players", "?select=id,player_key,full_name,position,active,metadata")
    result = plan(base, players)
    print(f"skill rows {result['n_skill_rows']}; universe {result['n_universe']} "
          f"(resolved to a row {result['n_universe_resolved']}, "
          f"unresolved {result['n_universe_unresolved']}); "
          f"out of universe by id {result['n_out_by_id']}; "
          f"unreached, unchanged {result['n_unchanged_unreached']}")
    print(f"set active=true {len(result['activate'])}, set active=false "
          f"{len(result['deactivate'])}, skipped {len(result['skipped'])}")
    for label, rows in (("+", result["activate"]), ("-", result["deactivate"])):
        for r in rows[:15]:
            print(f"  {label} {r['player_key']} {r['full_name']} ({r['position']}) via {r['how']}")
    for s in result["skipped"]:
        print(f"  skipped {s['player_key']} {s['full_name']}: {s['reason']}")
    if too_big(result):
        print(f"FAILED: plan changes more than {MAX_CHANGE_SHARE:.0%} of skill rows; nothing written",
              file=sys.stderr)
        return 1
    # Every key, so a write can be undone from the run log.
    for label, rows in (("true", result["activate"]), ("false", result["deactivate"])):
        if rows:
            print(f"set {label} player_keys: " + ",".join(str(r["player_key"]) for r in rows))
    if args.write:
        write(sbclient, result)
        print(f"written: {len(result['activate'])} true, {len(result['deactivate'])} false")
    else:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
