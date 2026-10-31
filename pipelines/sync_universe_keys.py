#!/usr/bin/env python3
"""Give every players.json player an identity in the comparison fixture.

GAP-UNIVERSE-CHART-ONLY (Jeremy, 2026-10-08): players priced by a published
chart or projection source but absent from ESPN's universe must get a row.
bake_players.py now bakes them into players.json (espn_status "absent").
The section builders and promotion only key a source row through the
fixture's own ``player_keys`` map (slug -> player_key; promotion never
introduces a new identity), so a new players.json player also needs a slug
there, or every chart that prices him drops him again (Tyreek Hill, CBS
Week 5).

This step adds the missing slugs (and their display name / team) before the
chain builds any section. It never renames or re-keys an existing slug, so
legacy slug quirks stay byte-for-byte. The slug is the legacy label
convention (canonical_players.norm_plain of the canonical name); a slug
already held by another player gets "-<player_key>" appended.

It also drops a slug whose player_key is no longer in players.json (JEG-1391):
a player row merged into another and deleted (JEG-1351 removed 4653, 4655 and
4660) otherwise stays in player_keys for good, and build_reference_data's
orphan check fails every chain run. A drop larger than MAX_PRUNE_SHARE of the
slugs is refused, so a short players.json can't empty the map; the orphan
check then fails loudly instead.

Usage: python3 pipelines/sync_universe_keys.py [--players P] [--fixture F]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402

FIXTURE_DIR = ROOT / "data" / "fixtures" / "current"
MAX_PRUNE_SHARE = 0.02


def sync(fixture: dict, players: list[dict]) -> list[tuple[str, int]]:
    """Add a player_keys slug for each players.json key the fixture lacks.

    Mutates ``fixture``; returns the (slug, player_key) pairs added.
    """
    player_keys = fixture.setdefault("player_keys", {})
    known = {k for k in player_keys.values() if isinstance(k, int)}
    display = fixture.get("display")
    teams = fixture.get("teams")
    added = []
    for p in sorted(players, key=lambda r: r.get("player_key", 0)):
        key = p.get("player_key")
        name = str(p.get("name") or "").strip()
        if not isinstance(key, int) or key in known or not name:
            continue
        slug = norm_plain(name)
        if not slug:
            continue
        if slug in player_keys:
            slug = f"{slug}-{key}"
            if slug in player_keys:
                continue
        player_keys[slug] = key
        known.add(key)
        if isinstance(display, dict):
            display.setdefault(slug, name)
        if isinstance(teams, dict) and p.get("team"):
            teams.setdefault(slug, p["team"])
        added.append((slug, key))
    return added


def prune(fixture: dict, players: list[dict]) -> list[tuple[str, int]]:
    """Drop each player_keys slug whose player_key is not in players.json,
    with its display name and team.

    Mutates ``fixture``; returns the (slug, player_key) pairs dropped. Drops
    nothing when ``players`` is empty or the drop would exceed
    MAX_PRUNE_SHARE of the slugs.
    """
    player_keys = fixture.get("player_keys")
    current = {p.get("player_key") for p in players if isinstance(p.get("player_key"), int)}
    if not isinstance(player_keys, dict) or not current:
        return []
    gone = sorted((slug, key) for slug, key in player_keys.items()
                  if isinstance(key, int) and key not in current)
    if not gone or len(gone) > MAX_PRUNE_SHARE * len(player_keys):
        return []
    for slug, _ in gone:
        del player_keys[slug]
        for side in ("display", "teams"):
            if isinstance(fixture.get(side), dict):
                fixture[side].pop(slug, None)
    return gone


def sync_files(players_path: Path, fixture_path: Path,
               removed: list | None = None) -> list[tuple[str, int]]:
    """Sync and prune the fixture file in place; returns the slugs added.

    Dropped slugs are appended to ``removed`` when a list is passed.
    """
    if not players_path.is_file() or not fixture_path.is_file():
        return []
    players = json.loads(players_path.read_text(encoding="utf-8")).get("players") or []
    raw = fixture_path.read_text(encoding="utf-8")
    fixture = json.loads(raw)
    dropped = prune(fixture, players)
    added = sync(fixture, players)
    if removed is not None:
        removed.extend(dropped)
    if added or dropped:
        # Keep the file's own layout (pretty with its indent, or compact).
        lines = raw.splitlines()
        second = lines[1] if len(lines) > 1 else ""
        indent = (len(second) - len(second.lstrip(" "))) or None
        text = (json.dumps(fixture, indent=indent) if indent
                else json.dumps(fixture, separators=(",", ":")))
        fixture_path.write_text(text + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    return added


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--players", default=str(FIXTURE_DIR / "players.json"))
    ap.add_argument("--fixture", default=str(FIXTURE_DIR / "comparison-sources-data.json"))
    args = ap.parse_args(argv)
    removed: list = []
    added = sync_files(Path(args.players), Path(args.fixture), removed)
    print(f"universe keys: {len(added)} players.json players added to the "
          f"fixture's player_keys" + (f": {added}" if added else ""))
    print(f"universe keys: {len(removed)} slugs dropped for players no longer in "
          f"players.json" + (f": {removed}" if removed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
