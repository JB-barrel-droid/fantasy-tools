"""JEG-366: Layered player identity resolution.

Layer 1 (base): Sleeper NFL player database (~12k players).
Layer 2 (override): Manual table (data/inputs/player_identity_map.json) — always wins.
Unknown: fails closed (never guessed).

Usage:
    from layered_identity import resolve_identity
    result = resolve_identity("Josh Allen")  # manual override wins over Sleeper
"""

from __future__ import annotations

import json
from pathlib import Path

_INPUTS = Path(__file__).resolve().parent.parent.parent / "data" / "inputs"

_base: dict | None = None
_manual: dict | None = None


def _load_base() -> dict:
    global _base
    if _base is None:
        p = _INPUTS / "sleeper_identity_base.json"
        _base = json.loads(p.read_text()) if p.exists() else {"by_name": {}}
    return _base


def _load_manual() -> dict:
    global _manual
    if _manual is None:
        p = _INPUTS / "player_identity_map.json"
        _manual = json.loads(p.read_text()) if p.exists() else {}
    return _manual


def resolve_identity(name: str) -> dict | None:
    """Resolve a player name. Manual overrides win. Returns None if unknown.

    Returns dict with: name, pos, team, source ("manual" or "sleeper").
    """
    key = name.lower().strip()
    manual = _load_manual()

    # Layer 2: manual canonical
    canon = manual.get("canonical", {})
    if key in canon:
        e = canon[key]
        return {"name": e.get("name", name), "pos": e.get("pos"),
                "team": e.get("team"), "source": "manual"}
    # Layer 2: manual aliases
    aliases = manual.get("alias_to_canonical", {})
    if key in aliases:
        canon_key = aliases[key]
        e = canon.get(canon_key, {})
        return {"name": e.get("name", name), "pos": e.get("pos"),
                "team": e.get("team"), "source": "manual-alias"}

    # Layer 1: Sleeper base
    base = _load_base()
    hit = base.get("by_name", {}).get(key)
    if hit:
        return {"name": hit["name"], "pos": hit["pos"],
                "team": hit["team"], "source": "sleeper"}

    # Unknown: fail closed
    return None
