"""JEG-366: Layered player identity resolution.

Layer 3 (aliases):  verified spellings, data/inputs/player_aliases.json (the one
                    list every resolver shares) rewrite the name first.
Layer 2 (override): manual table data/inputs/player_identity_map.json. Always wins.
Layer 1 (base):     Sleeper NFL player database (data/inputs/sleeper_identity_base.json,
                    refreshed by .github/workflows/sleeper-identity-refresh.yml).
Unknown or ambiguous: None. Never guessed.

Sleeper disambiguation, in order, stopping at the first step that leaves
exactly one player:
  1. the name (canonical_players.norm_plain, same key as the manual table);
  2. the caller's position, when given;
  3. among those, the single player who is active AND on an NFL roster
     (a retired or free-agent namesake does not make a rostered player
     ambiguous). Two rostered namesakes at one position -> None.

Usage:
    from lib.layered_identity import resolve_identity
    resolve_identity("Kenny Gainwell")             # manual alias wins
    resolve_identity("Josh Allen", pos="QB")       # Sleeper, position-filtered
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_LIB = os.path.dirname(os.path.abspath(__file__))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
from canonical_players import norm_plain  # noqa: E402
import player_aliases  # noqa: E402 -- the one verified alias list

_INPUTS = Path(_LIB).parent.parent / "data" / "inputs"
BASE_SCHEMA = "sleeper-identity-base-v2"

_base: dict | None = None
_manual: dict | None = None


def _load_base() -> dict:
    global _base
    if _base is None:
        p = _INPUTS / "sleeper_identity_base.json"
        base = json.loads(p.read_text()) if p.exists() else {}
        # A v1 base (first-write-wins names) is unsafe to resolve against;
        # treat it as absent rather than guess.
        _base = base if base.get("schema") == BASE_SCHEMA else {"by_name": {}, "by_sleeper_id": {}}
    return _base


def _load_manual() -> dict:
    global _manual
    if _manual is None:
        p = _INPUTS / "player_identity_map.json"
        _manual = json.loads(p.read_text()) if p.exists() else {}
    return _manual


def _keys(name: str) -> list[str]:
    raw = str(name or "")
    return [k for k in dict.fromkeys([norm_plain(raw), raw.lower().strip()]) if k]


def resolve_manual(name: str) -> dict | None:
    spelled = player_aliases.canonical_spelling(name)
    aliased = norm_plain(str(spelled or "")) != norm_plain(str(name or ""))
    name = spelled
    manual = _load_manual()
    canon = manual.get("canonical", {})
    aliases = manual.get("alias_to_canonical", {})
    for key in _keys(name):
        if key in canon:
            e = canon[key]
            return {"name": e.get("name", name), "pos": e.get("pos"),
                    "team": e.get("team"),
                    "source": "manual-alias" if aliased else "manual"}
        if key in aliases and aliases[key] in canon:
            e = canon[aliases[key]]
            return {"name": e.get("name", name), "pos": e.get("pos"),
                    "team": e.get("team"), "source": "manual-alias"}
    return None


def sleeper_candidates(name: str, pos: str | None = None) -> list[dict]:
    """Every Sleeper player whose name key matches (and position, if given)."""
    base = _load_base()
    by_id = base.get("by_sleeper_id", {})
    # Sleeper may carry any verified spelling ("Kenny Gainwell", "Chig
    # Okonkwo"); look up every spelling of the same player, one hit per id.
    sids = []
    for spelling in player_aliases.spellings(str(name or "")):
        sids += base.get("by_name", {}).get(norm_plain(str(spelling or "")), [])
    out = []
    for sid in dict.fromkeys(sids):
        e = by_id.get(sid)
        if e is None:
            continue
        if pos and str(e.get("pos") or "").upper() != str(pos).upper():
            continue
        out.append({**e, "sleeper_id": sid})
    return out


def resolve_sleeper(name: str, pos: str | None = None) -> dict | None:
    cands = sleeper_candidates(name, pos)
    if len(cands) > 1:
        rostered = [c for c in cands if c.get("active") and c.get("team")]
        cands = rostered if len(rostered) == 1 else []
        source = "sleeper-rostered"
    else:
        source = "sleeper"
    if len(cands) != 1:
        return None
    c = cands[0]
    return {"name": c["name"], "pos": c.get("pos"), "team": c.get("team"),
            "sleeper_id": c["sleeper_id"], "source": source}


def resolve_identity(name: str, pos: str | None = None) -> dict | None:
    """Resolve a player name. Manual overrides win. None if unknown or ambiguous.

    Returns dict with: name, pos, team, source ("manual", "manual-alias",
    "sleeper" or "sleeper-rostered"); Sleeper hits also carry sleeper_id.
    """
    if not str(name or "").strip():
        return None
    hit = resolve_manual(name)
    if hit is not None:
        return hit
    return resolve_sleeper(name, pos)
