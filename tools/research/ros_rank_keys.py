"""JEG-1198/JEG-1251 research helper: canonical player_key joins from stored fixtures only.

Every name in the study inputs (published DDF capture, expert lists, StickToTheModel,
Karabell) is resolved to the numeric public.players `player_key` through the repo's one
resolver (pipelines/lib/canonical_players.resolve_with_reason, with the shared alias list),
built from the committed registry snapshot data/inputs/players_identity_snapshot.json.
No Supabase read: the alias list is forced to the committed JSON and the registry comes
from the snapshot, so a rerun is reproducible from the repo alone.

Joins are on player_key. A name that does not resolve to exactly one player_key
(unmatched, ambiguous, position conflict) is left out and logged with its reason, never
collapsed onto a near name. Two different source spellings in one list that resolve to
the same player_key are logged as a duplicate and the first row is kept.

The snapshot carries no active flag, so every row is treated as active: same-name,
same-position players are reported ambiguous instead of being broken by activity. That is
stricter than the bake, never looser.
"""
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("PLAYER_ALIASES_SOURCE", "json")  # stored fixture, not the live table

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
from canonical_players import Registry, resolve_with_reason  # noqa: E402  the one resolver
import player_aliases  # noqa: E402  owns the alias list's path (tests/test_player_aliases.py)

REGISTRY_PATH = REPO / "data/inputs/players_identity_snapshot.json"
ALIASES_PATH = Path(player_aliases.ALIAS_FILE)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rows():
    for r in json.loads(REGISTRY_PATH.read_text()):
        yield {"player_key": r["player_key"], "full_name": r["full_name"],
               "position": r.get("position"), "active": True}


REGISTRY = Registry(_rows())
_LOG = []          # every resolution: (list_id, name, pos, key, reason)
_CACHE = {}


def pk(name, pos, list_id):
    """player_key for a source name at a position, or None. Logs the outcome."""
    ck = (name, pos)
    if ck not in _CACHE:
        _CACHE[ck] = resolve_with_reason(name, position=pos, registry=REGISTRY)
    key, reason = _CACHE[ck]
    _LOG.append((list_id, name, pos, key, reason))
    return key


def put(d, name, pos, list_id, value):
    """d[player_key] = value; skips unresolved names and logs duplicate keys."""
    k = pk(name, pos, list_id)
    if k is None:
        return None
    if k in d:
        _LOG.append((list_id, name, pos, k, "duplicate_key"))
        return None
    d[k] = value
    return k


def join_report():
    """Counts by reason, and every non-ok row, per list."""
    by_list, seen_rows = {}, set()
    for list_id, name, pos, key, reason in _LOG:
        if (list_id, name, pos, reason) in seen_rows:  # a list read more than once counts once
            continue
        seen_rows.add((list_id, name, pos, reason))
        e = by_list.setdefault(list_id, {"counts": Counter(), "not_joined": []})
        e["counts"][reason] += 1
        if reason != "ok":
            e["not_joined"].append({"name": name, "pos": pos, "reason": reason,
                                    "player_key": key})
    out = {}
    for list_id, e in sorted(by_list.items()):
        seen, rows = set(), []
        for r in e["not_joined"]:
            t = (r["name"], r["pos"], r["reason"])
            if t not in seen:
                seen.add(t)
                rows.append(r)
        out[list_id] = {"counts": dict(e["counts"]), "not_joined": rows}
    return out


def provenance():
    return {
        "join": "public.players player_key via pipelines/lib/canonical_players.resolve_with_reason",
        "registry_snapshot": {"path": str(REGISTRY_PATH.relative_to(REPO)), "sha256": sha256(REGISTRY_PATH),
                              "rows": len(REGISTRY.by_key), "active_flag": "absent; all rows treated active"},
        "alias_list": {"path": str(ALIASES_PATH.relative_to(REPO)), "sha256": sha256(ALIASES_PATH),
                       "source": os.environ.get("PLAYER_ALIASES_SOURCE")},
    }
