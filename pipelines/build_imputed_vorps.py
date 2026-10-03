#!/usr/bin/env python3
"""Build imputed VORP per JEG-180 methodology.

For each as-published source (FantasyCalc, FantasyPros,  USA Today, CBS):
    - infer roster construction from published values (Flex = top flex-eligible
      non-starters by value; Bench = top remaining by value),
    - map Flex -> Starter for the 8-group model,
    - for each of 8 groups (pos in {QBRB,WR,TE} x role in {starter,bench}):
        alloc_factor = our_group_VORP / sum(publisher_values_in_group)
    - imputed_vorp[player] = published_value[player] * alloc_factor

Conservation: total imputed VORP in each group equals our group VORP exactly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

DEFAULT_TEAMS = 12
DEFAULT_SLOTS_PER_TEAM = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
DEFAULT_FLEX_PER_TEAM = 1
DEFAULT_BENCH_PER_TEAM = 6
DEFAULT_FLEX_ELIGIBLE = ("RB", "WR", "TE")
POSITION_ORDER = ("QB", "RB", "WR", "TE")
EIGHT_GROUPS = tuple((pos, role) for pos in POSITION_ORDER for role in ("starter", "bench"))
DEFAULT_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "cbs")
DEFAULT_DDF_LEG = "data/ddf-two-tier/ddf-20260930-espn-half_ppr-12t-0p15/ddf_leg.json"


@dataclass(frozen=True)
class RosterShape:
    teams: int = DEFAULT_TEAMS
    slots: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_SLOTS_PER_TEAM))
    flex_count: int = DEFAULT_FLEX_PER_TEAM
    bench: int = DEFAULT_BENCH_PER_TEAM
    flex_eligible: Sequence[str] = DEFAULT_FLEX_ELIGIBLE

    def __post_init__(self) -> None:
        if self.teams <= 0:
            raise ValueError("teams must be positive")
        for pos, count in self.slots.items():
            if count < 0:
                raise ValueError(f"negative slot count for {pos}")
        if self.flex_count < 0 or self.bench < 0:
            raise ValueError("flex_count and bench must be non-negative")

    @property
    def dedicated_per_team(self) -> Dict[str, int]:
        return dict(self.slots)

    @property
    def total_starter_slots(self) -> Dict[str, int]:
        """Dedicated + flex allocated by D'Hondt (JEG-61 allocator)."""
        dedicated = self.dedicated_per_team
        total_dedicated = sum(dedicated.values())
        total_flex = self.teams * self.flex_count
        if total_flex == 0 or total_dedicated == 0:
            return {p: self.teams * c for p, c in dedicated.items()}
        weights = {p: c / total_dedicated for p, c in dedicated.items()}
        flex_alloc = {p: int(weights[p] * total_flex) for p in dedicated}
        remainder = total_flex - sum(flex_alloc.values())
        order = sorted(
            dedicated.keys(),
            key=lambda p: (-(weights[p] * total_flex - flex_alloc[p]), POSITION_ORDER.index(p)),
        )
        for pos in order[:remainder]:
            flex_alloc[pos] += 1
        return {
            p: self.teams * dedicated[p] + flex_alloc.get(p, 0) for p in dedicated
        }

    @property
    def bench_slots(self) -> int:
        return self.teams * self.bench


@dataclass(frozen=True)
class PlayerRecord:
    player_key: int
    name: str
    pos: str


@dataclass(frozen=True)
class GroupKey:
    pos: str
    role: str


def load_players(fixture_path: str) -> Tuple[Dict[int, PlayerRecord], Mapping]:
    """Load players.json fixtureand the nested source data sections."""
    with open(fixture_path) as f:
        fixture = json.load(f)
    players: Dict[int, PlayerRecord] = {}
    for row in fixture.get("players", []):
        player_key = row.get("player_key")
        if not isinstance(player_key, int):
            continue
        players[player_key] = PlayerRecord(
            player_key=player_key,
            name=row.get("name") or row.get("full_name") or "",
            pos=row.get("pos") or row.get("position") or "",
        )
    sources_data = (
        fixture.get("sources_data")
        or fixture.get("sources")
        or fixture.get("source_values")
        or {}
    )
    return players, sources_data


def build_source_value_table(
    source: str,
    sources_data: Mapping,
    players: Mapping[int, PlayerRecord],
) -> Dict[int, float]:
    """Extract (player_key -> as-published value) for `source`."""
    candidates = (source, f"{source}_native", f"{source}_values")
    for key in candidates:
        block = sources_data.get(key)
        if not isinstance(block, Mapping):
            continue
        sample_keys = list(block.keys())[:5]
        if sample_keys and all(isinstance(k, int) for k in sample_keys):
            return {int(k): float(v) for k, v in block.items() if v is not None}
        name_to_key = {p.name.strip().lower(): pk for pk, p in players.items() if p.name}
        out: Dict[int, float] = {}
        for name, val in block.items():
            if val is None:
                continue
            pk = name_to_key.get(str(name).strip().lower())
            if pk is None:
                continue
            out[pk] = float(val)
        if out:
            return out
    # Fallback: scan nested blocks for source.
    for top_key, top_val in sources_data.items():
        if not isinstance(top_val, Mapping) or source not in top_key.lower():
            continue
        if not top_val:
            continue
        first = next(iter(top_val.values()))
        if isinstance(first, Mapping):
            sub = first.get("values") or first.get("native") or {}
            if isinstance(sub, Mapping):
                name_to_key = {
                    p.name.strip().lower(): pk for pk, p in players.items() if p.name
                }
                out = {}
                for name, val in sub.items():
                    if val is None:
                        continue
                    pk = name_to_key.get(str(name).strip().lower())
                    if pk is None:
                        continue
                    out[pk] = float(val)
                if out:
                    return out
    raise KeyError(f"No source value table found for {source!r}")


def assign_roles(
    values: Mapping[int, float],
    players: Mapping[int, PlayerRecord],
    shape: RosterShape,
) -> Dict[int, GroupKey]:
    """Infer roles from as-published values + roster slots.

    Step 1: dedicated slots by top per-position by value.
    Step 2: flex slots by top flex-eligible non-starters by value.
    Step 3: bench by top remaining by value.
   Returns {player_key: GroupKey}; players not selected are omitted (waiver).
    """
    valid = set(POSITION_ORDER)
    rows = []
    for pk, val in values.items():
        p = players.get(pk)
        if not p or p.pos not in valid:
            continue
        if not isinstance(val, (int, float)) or val <= 0:
            continue
        rows.append((float(val), pk, p.pos))
    rows.sort(key=lambda r: (-r[0], r[1]))
    roles: Dict[int, GroupKey] = {}
    counts = {p: 0 for p in POSITION_ORDER}
    dedicated_target = {
        p: shape.teams * shape.dedicated_per_team.get(p, 0) for p in POSITION_ORDER
    }
    # 1. Dedicated slots
    for val, pk, pos in rows:
        if counts[pos] < dedicated_target.get(pos, 0):
            roles[pk] = GroupKey(pos=pos, role="starter")
            counts[pos] += 1
    # 2. Flex (D'Hondt allocation already computed in shape.total_starter_slots)
    flex_targets = shape.total_starter_slots
    for val, pk, pos in rows:
        if pk in roles:
            continue
        if pos not in shape.flex_eligible:
            continue
        if counts[pos] < flex_targets.get(pos, 0):
            roles[pk] = GroupKey(pos=pos, role="starter")
            counts[pos] += 1
    # 3. Bench
    bench_target = shape.bench_slots
    bench_count = 0
    for val, pk, pos in rows:
        if pk in roles:
            continue
        if bench_count < bench_target:
            roles[pk] = GroupKey(pos=pos, role="bench")
            bench_count += 1
    return roles


def load_ddf_group_vorps(leg_path: str) -> Dict[Tuple[str, str], float]:
    """Return (position, role) -> our group VORP from a DDF leg (JEG-206).

    Reads calibration.<POS>.starter_raw / .bench_raw. These are the raw
    position-level values above the waiver line summed across the entire starter
    and bench sets respectively.
    """
    with open(leg_path) as f:
        leg = json.load(f)
    cal = leg.get("calibration") or {}
    out: Dict[Tuple[str, str], float] = {}
    for pos in POSITION_ORDER:
        block = cal.get(pos) or {}
        out[(pos, "starter")] = float(block.get("starter_raw") or 0.0)
        out[(pos, "bench")] = float(block.get("bench_raw") or 0.0)
    missing = [g for g in EIGHT_GROUPS if g not in out]
    if missing:
        raise ValueError(f"DDF leg {leg_path} missing groups: {missing}")
    return out


def compute_imputed_vorps(
    values: Mapping[int, float],
    roles: Mapping[int, GroupKey],
    group_vorps: Mapping[Tuple[str, str], float],
) -> Dict[int, float]:
    """8-group proportional imputed VORP.

    alloc_factor = our_group_VORP / sum(publisher_values_in_group)
    imputed_vorp[player] = published_value * alloc_factor

    Conservation: total imputed VORP per group == our_group_VORP exactly.
    """
    group_sums: Dict[Tuple[str, str], float] = {g: 0.0 for g in EIGHT_GROUPS}
    for pk, val in values.items():
        r = roles.get(pk)
        if r is None:
            continue
        group_sums[(r.pos, r.role)] += float(val)
    factors: Dict[Tuple[str, str], float] = {}
    for g in EIGHT_GROUPS:
        s = group_sums[g]
        target = group_vorps.get(g, 0.0)
        factors[g] = (target / s) if s > 0 else 0.0
    out: Dict[int, float] = {}
    for pk, val in values.items():
        r = roles.get(pk)
        if r is None:
            continue
        out[pk] = float(val) * factors[(r.pos, r.role)]
    return out


def build_imputed_vorps(
    fixture_path: str,
    ddf_leg_path: str,
    sources: Sequence[str] = DEFAULT_SOURCES,
    shape: Optional[RosterShape] = None,
) -> Dict:
    shape = shape or RosterShape()
    players, sources_data = load_players(fixture_path)
    group_vorps = load_ddf_group_vorps(ddf_leg_path)
    artifact = {
        "meta": {
            "fixture": fixture_path,
            "ddf_leg": ddf_leg_path,
            "sources": list(sources),
            "shape": {
                "teams": shape.teams,
                "slots": shape.dedicated_per_team,
                "flex": shape.flex_count,
                "bench": shape.bench,
                "total_starter_slots": shape.total_starter_slots,
                "bench_slots": shape.bench_slots,
            },
            "group_vorps": {f"{p}/{r}": v for (p, r), v in group_vorps.items()},
        },
        "sources": {},
    }
    for source in sources:
        values = build_source_value_table(source, sources_data, players)
        roles = assign_roles(values, players, shape)
        imputed = compute_imputed_vorps(values, roles, group_vorps)
        artifact["sources"][source] = {
            "roles": {str(pk): {"pos": r.pos, "role": r.role} for pk, r in roles.items()},
            "values": {str(pk): round(v, 6) for pk, v in imputed.items()},
            "group_totals": {
                f"{p}/{r}": round(sum(
                    imputed[pk] for pk, rr in roles.items() if rr.pos == p and rr.role == r
                ), 6)
                for (p, r) in EIGHT_GROUPS
            },
        }
    return artifact


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build JEG-180 imputed VORP artifact.")
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--ddf-leg", default=DEFAULT_DDF_LEG)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sources", nargs="+", default=list(DEFAULT_SOURCES))
    args = ap.parse_args(argv)
    artifact = build_imputed_vorps(args.fixture, args.ddf_leg, args.sources)
    out_path = args.out
    if out_path and os.path.dirname(out_path):
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())