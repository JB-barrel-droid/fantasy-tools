#!/usr/bin/env python3
"""JEG-366: Pull Sleeper NFL player database as the identity backbone.

Sleeper /players/nfl is free, keyless, ~12k players covering active rosters,
practice squads, IR, and free agents — well beyond fantasy relevance.

This builds the comprehensive base layer. The manual table
(data/inputs/player_identity_map.json) remains as the override layer on top
for edge cases and corrections.

Output: data/inputs/sleeper_identity_base.json
  {
    "meta": {"pulled_at": ..., "n_players": ...},
    "by_name": {"josh allen": {"sleeper_id": ..., "pos": ..., "team": ...}},
    "by_sleeper_id": {...}
  }

Name matching: lowercase full_name + common variants (first initial + last,
suffixes stripped). Manual overrides always win.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SLEEPER_URL = "https://api.sleeper.app/v1/players/nfl"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "inputs" / "sleeper_identity_base.json"

# Positions we care about for fantasy identity (still store all, but flag relevance)
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def normalize_name(name: str) -> str:
    """Lowercase, strip suffixes (Jr/Sr/II/III/IV/V), collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def name_variants(full_name: str) -> list[str]:
    """Generate lookup variants for a name."""
    variants = [normalize_name(full_name)]
    parts = normalize_name(full_name).split()
    if len(parts) >= 2:
        # First initial + last name (e.g. "j allen")
        variants.append(f"{parts[0][0]} {parts[-1]}")
    return list(dict.fromkeys(variants))


def pull_sleeper() -> dict:
    req = urllib.request.Request(
        SLEEPER_URL, headers={"User-Agent": "fantasy-tools/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def build_base(sleeper_data: dict) -> dict:
    by_name: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    n_skipped = 0

    for pid, p in sleeper_data.items():
        full_name = (p.get("full_name") or "").strip()
        if not full_name:
            n_skipped += 1
            continue
        pos = p.get("position") or (p.get("fantasy_positions") or [None])[0]
        entry = {
            "sleeper_id": pid,
            "name": full_name,
            "pos": pos,
            "team": p.get("team"),
            "active": p.get("active", False),
            "status": p.get("status"),
            "fantasy_relevant": pos in FANTASY_POSITIONS,
        }
        by_id[pid] = entry
        for variant in name_variants(full_name):
            # First write wins for collisions; manual overrides handle conflicts
            if variant not in by_name:
                by_name[variant] = entry

    return {
        "meta": {
            "pulled_at": datetime.now(timezone.utc).isoformat(),
            "source": "sleeper /players/nfl",
            "n_players": len(by_id),
            "n_name_keys": len(by_name),
            "n_skipped_no_name": n_skipped,
        },
        "by_name": by_name,
        "by_sleeper_id": by_id,
    }


def main() -> int:
    print("Pulling Sleeper NFL players...", file=sys.stderr)
    data = pull_sleeper()
    print(f"Got {len(data)} raw players", file=sys.stderr)
    base = build_base(data)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(base, indent=1))
    meta = base["meta"]
    print(f"Wrote {OUT_PATH}: {meta['n_players']} players, {meta['n_name_keys']} name keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
