#!/usr/bin/env python3
"""JEG-366: Pull the Sleeper NFL player database as the identity base layer.

Sleeper /players/nfl is free and keyless and covers active rosters, practice
squads, IR and free agents. It sits UNDER the manual identity table
(data/inputs/player_identity_map.json), which always wins.

Output: data/inputs/sleeper_identity_base.json (schema sleeper-identity-base-v2)
  {
    "schema": "sleeper-identity-base-v2",
    "meta": {"pulled_at", "source", "n_players", "n_name_keys", "n_ambiguous_names"},
    "by_name": {"jamarr chase": ["7564"], "josh allen": ["4984", "..."]},
    "by_sleeper_id": {"7564": {"name", "pos", "team", "active", "status",
                               "injury_status", "depth_chart_position",
                               "depth_chart_order", "last_news",
                               "espn_id", "yahoo_id", "gsis_id", "sportradar_id"}}
  }

JEG-502 added the roster fields (injury_status, depth_chart_position,
depth_chart_order, last_news = date of Sleeper's latest news item) so the bake
can define the active NFL universe (pipelines/lib/nfl_universe.py). Additive:
the schema name is unchanged and identity resolution does not read them.

Rules (v1 got these wrong; see docs/claude-log/ 2026-10-05 entry):
  - Names are keyed with canonical_players.norm_plain, the same convention as
    the manual identity map, and map to a LIST of Sleeper ids. v1 kept the
    first player seen per name, so "josh allen" resolved to a free-agent guard.
  - No first-initial variants ("j allen" collided 1,218 ways in v1).
  - Fantasy positions only (QB/RB/WR/TE/K). Team defenses resolve through the
    canonical registry, not by person name.
  - Fail closed on a partial pull: fewer than MIN_FANTASY_PLAYERS rows exits
    non-zero and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.canonical_players import norm_plain  # noqa: E402

SCHEMA = "sleeper-identity-base-v2"
SLEEPER_URL = "https://api.sleeper.app/v1/players/nfl"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "inputs" / "sleeper_identity_base.json"
FANTASY_POSITIONS = ("QB", "RB", "WR", "TE", "K")
# 2026-10-05 pull: 4,234 rows at these positions (3,201 active). A pull far
# below that is truncated or an API change, never a real roster.
MIN_FANTASY_PLAYERS = 2500
CROSS_IDS = ("espn_id", "yahoo_id", "gsis_id", "sportradar_id")
ROSTER_FIELDS = ("injury_status", "depth_chart_position", "depth_chart_order")


def news_date(ms) -> str | None:
    """Sleeper news_updated (epoch milliseconds) -> 'YYYY-MM-DD' (UTC)."""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def pull_sleeper() -> dict:
    req = urllib.request.Request(SLEEPER_URL, headers={"User-Agent": "fantasy-tools/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def player_position(p: dict) -> str | None:
    return p.get("position") or (p.get("fantasy_positions") or [None])[0]


def build_base(sleeper_data: dict, pulled_at: str | None = None) -> dict:
    by_id: dict[str, dict] = {}
    by_name: dict[str, list[str]] = {}
    for pid, p in sleeper_data.items():
        full_name = (p.get("full_name") or "").strip()
        if not full_name:
            first, last = (p.get("first_name") or "").strip(), (p.get("last_name") or "").strip()
            full_name = f"{first} {last}".strip()
        pos = player_position(p)
        if not full_name or pos not in FANTASY_POSITIONS:
            continue
        entry = {
            "name": full_name,
            "pos": pos,
            "team": p.get("team"),
            "active": bool(p.get("active", False)),
            "status": p.get("status"),
        }
        for key in ROSTER_FIELDS:
            if p.get(key) not in (None, ""):
                entry[key] = p[key]
        last_news = news_date(p.get("news_updated"))
        if last_news:
            entry["last_news"] = last_news
        for key in CROSS_IDS:
            if p.get(key) not in (None, ""):
                entry[key] = str(p[key])
        by_id[str(pid)] = entry
        key = norm_plain(full_name)
        if key:
            by_name.setdefault(key, []).append(str(pid))
    for ids in by_name.values():
        ids.sort(key=lambda s: (len(s), s))
    return {
        "schema": SCHEMA,
        "meta": {
            "pulled_at": pulled_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "sleeper /players/nfl",
            "positions": list(FANTASY_POSITIONS),
            "n_players": len(by_id),
            "n_name_keys": len(by_name),
            "n_ambiguous_names": sum(1 for ids in by_name.values() if len(ids) > 1),
        },
        "by_name": dict(sorted(by_name.items())),
        "by_sleeper_id": dict(sorted(by_id.items(), key=lambda kv: (len(kv[0]), kv[0]))),
    }


def check_base(base: dict) -> list[str]:
    """Fail-closed sanity checks. Returns problems; empty means OK."""
    problems = []
    n = base["meta"]["n_players"]
    if n < MIN_FANTASY_PLAYERS:
        problems.append(f"only {n} fantasy-position players (< {MIN_FANTASY_PLAYERS}); partial pull?")
    by_id = base["by_sleeper_id"]
    for key, ids in base["by_name"].items():
        missing = [i for i in ids if i not in by_id]
        if missing:
            problems.append(f"by_name[{key!r}] references unknown ids {missing}")
            break
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--from-file", type=Path,
                    help="build from a saved /players/nfl response instead of the API")
    args = ap.parse_args(argv)
    raw = json.loads(args.from_file.read_text(encoding="utf-8")) if args.from_file else pull_sleeper()
    print(f"Got {len(raw)} raw Sleeper players", file=sys.stderr)
    base = build_base(raw)
    problems = check_base(base)
    if problems:
        for p in problems:
            print(f"FAIL-CLOSED: {p}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(base, indent=0, sort_keys=False) + "\n", encoding="utf-8")
    m = base["meta"]
    print(f"Wrote {args.out}: {m['n_players']} players, {m['n_name_keys']} names, "
          f"{m['n_ambiguous_names']} ambiguous")
    return 0


if __name__ == "__main__":
    sys.exit(main())
