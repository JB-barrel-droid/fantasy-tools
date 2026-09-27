#!/usr/bin/env python3
"""Three-line roster model for fantasy value diagnostics.

This is a small, auditable model boundary for the positional-count problem:

1. Dedicated starters are selected by position.
2. Flex starters are selected by raw projected points across flex-eligible
   positions.
3. Bench players are selected after lineup construction, with an explicit
   bench-starter tier and visible positional caps.

The output is diagnostic by design. It does not rewrite dashboard artifacts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
POSITIONS = ("QB", "RB", "WR", "TE")
DEFAULT_SCORING = "half_ppr"


@dataclass(frozen=True)
class PlayerRow:
    key: int
    name: str
    pos: str
    ppg: float


@dataclass(frozen=True)
class LeagueShape:
    teams: int
    slots: dict[str, int]
    flex: int
    bench: int
    flex_eligible: tuple[str, ...]
    bench_positions: tuple[str, ...]
    bench_starter_slots_per_team: int = 2
    bench_caps: dict[str, int] | None = None


def _rank_key(player: PlayerRow) -> tuple[float, str, int]:
    return (-player.ppg, player.name, player.key)


def load_players(path: Path, scoring: str) -> list[PlayerRow]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[PlayerRow] = []
    for player in payload.get("players", []):
        pos = player.get("pos")
        ppg = (player.get("espn_ppg") or {}).get(scoring)
        key = player.get("player_key")
        name = str(player.get("name") or "").strip()
        if pos in POSITIONS and isinstance(key, int) and name and isinstance(ppg, (int, float)):
            rows.append(PlayerRow(key=key, name=name, pos=pos, ppg=float(ppg)))
    return rows


def _line_from_selected(selected: list[PlayerRow]) -> float | None:
    return min((player.ppg for player in selected), default=None)


def _next_unselected_line(players: list[PlayerRow], selected_keys: set[int], pos: str) -> float | None:
    remaining = [player.ppg for player in players if player.pos == pos and player.key not in selected_keys]
    return max(remaining) if remaining else None


def build_model(players: list[PlayerRow], shape: LeagueShape) -> dict[str, Any]:
    active_positions = {
        pos
        for pos in POSITIONS
        if shape.slots.get(pos, 0) > 0
        or pos in shape.flex_eligible
        or pos in shape.bench_positions
    }
    ranked_by_pos = {
        pos: sorted([player for player in players if player.pos == pos], key=_rank_key)
        for pos in POSITIONS
    }
    roles: dict[int, str] = {}
    role_rows: dict[str, list[PlayerRow]] = {
        "dedicated_starter": [],
        "flex_starter": [],
        "bench_starter": [],
        "bench_depth": [],
    }

    def assign(player: PlayerRow, role: str) -> None:
        if player.key in roles:
            raise ValueError(f"player assigned twice: {player.name} ({player.key})")
        roles[player.key] = role
        role_rows[role].append(player)

    for pos in POSITIONS:
        count = shape.teams * int(shape.slots.get(pos, 0))
        for player in ranked_by_pos[pos][:count]:
            assign(player, "dedicated_starter")

    flex_pool = sorted(
        [
            player
            for player in players
            if player.pos in shape.flex_eligible and player.key not in roles
        ],
        key=_rank_key,
    )
    for player in flex_pool[: shape.teams * shape.flex]:
        assign(player, "flex_starter")

    bench_caps = dict(shape.bench_caps or {})
    key_to_player = {player.key: player for player in players}

    def bench_count(pos: str) -> int:
        return sum(1 for key, role in roles.items() if role.startswith("bench_") and key_to_player[key].pos == pos)

    def bench_candidates() -> list[PlayerRow]:
        candidates = []
        for player in players:
            if player.key in roles or player.pos not in shape.bench_positions:
                continue
            cap = bench_caps.get(player.pos)
            if cap is not None and bench_count(player.pos) >= cap:
                continue
            candidates.append(player)
        return sorted(candidates, key=_rank_key)

    bench_starter_slots = shape.teams * min(shape.bench, max(0, shape.bench_starter_slots_per_team))
    for _ in range(bench_starter_slots):
        candidates = bench_candidates()
        if not candidates:
            break
        assign(candidates[0], "bench_starter")

    bench_depth_slots = shape.teams * shape.bench - len(role_rows["bench_starter"])
    for _ in range(bench_depth_slots):
        candidates = bench_candidates()
        if not candidates:
            break
        assign(candidates[0], "bench_depth")

    selected_keys = set(roles)
    lineup_roles = {"dedicated_starter", "flex_starter"}
    roster_roles = {"dedicated_starter", "flex_starter", "bench_starter", "bench_depth"}
    counts: dict[str, dict[str, int]] = {}
    lines: dict[str, Any] = {
        "position_starter": {},
        "position_bench_starter": {},
        "position_waiver": {},
        "flex": _line_from_selected(role_rows["flex_starter"]),
        "bench_starter": _line_from_selected(role_rows["bench_starter"]),
    }
    pies: dict[str, float] = {}
    for pos in POSITIONS:
        counts[pos] = {
            "dedicated_starter": sum(1 for player in role_rows["dedicated_starter"] if player.pos == pos),
            "flex_starter": sum(1 for player in role_rows["flex_starter"] if player.pos == pos),
            "bench_starter": sum(1 for player in role_rows["bench_starter"] if player.pos == pos),
            "bench_depth": sum(1 for player in role_rows["bench_depth"] if player.pos == pos),
        }
        if pos not in active_positions:
            lines["position_starter"][pos] = None
            lines["position_bench_starter"][pos] = None
            lines["position_waiver"][pos] = None
            pies[pos] = 0.0
            continue
        position_lineup = [
            player
            for role in lineup_roles
            for player in role_rows[role]
            if player.pos == pos
        ]
        position_bench_starters = [player for player in role_rows["bench_starter"] if player.pos == pos]
        lines["position_starter"][pos] = _line_from_selected(position_lineup)
        lines["position_bench_starter"][pos] = _line_from_selected(position_bench_starters)
        lines["position_waiver"][pos] = _next_unselected_line(players, selected_keys, pos)
        waiver = lines["position_waiver"][pos]
        if waiver is None:
            pies[pos] = 0.0
        else:
            rostered = [
                player
                for role in roster_roles
                for player in role_rows[role]
                if player.pos == pos
            ]
            pies[pos] = sum(max(0.0, player.ppg - waiver) for player in rostered)

    total_lineup = sum(1 for role in roles.values() if role in lineup_roles)
    total_rostered = len(roles)
    expected_lineup = shape.teams * (sum(shape.slots.values()) + shape.flex)
    expected_rostered = expected_lineup + shape.teams * shape.bench
    validations = {
        "lineup_count_ok": total_lineup == expected_lineup,
        "rostered_count_ok": total_rostered == expected_rostered,
        "no_duplicate_assignments": len(selected_keys) == total_rostered,
        "bench_caps_ok": all(
            counts[pos]["bench_starter"] + counts[pos]["bench_depth"] <= cap
            for pos, cap in bench_caps.items()
        ),
        "flex_raw_ppg_ok": _validate_flex_raw_ppg(players, roles, shape),
        "waiver_lines_ok": all(
            (
                lines["position_waiver"][pos] == _next_unselected_line(players, selected_keys, pos)
                if pos in active_positions
                else lines["position_waiver"][pos] is None
            )
            for pos in POSITIONS
        ),
    }
    return {
        "shape": {
            "teams": shape.teams,
            "slots": dict(shape.slots),
            "flex": shape.flex,
            "bench": shape.bench,
            "flex_eligible": list(shape.flex_eligible),
            "bench_positions": list(shape.bench_positions),
            "bench_starter_slots_per_team": shape.bench_starter_slots_per_team,
            "bench_caps": bench_caps,
        },
        "counts": counts,
        "lines": lines,
        "pies": pies,
        "pie_shares": {
            pos: (100.0 * value / sum(pies.values()) if sum(pies.values()) else 0.0)
            for pos, value in pies.items()
        },
        "validations": validations,
        "players": [
            {
                "player_key": player.key,
                "name": player.name,
                "pos": player.pos,
                "ppg": player.ppg,
                "role": roles[player.key],
            }
            for role in ("dedicated_starter", "flex_starter", "bench_starter", "bench_depth")
            for player in role_rows[role]
        ],
    }


def _validate_flex_raw_ppg(players: list[PlayerRow], roles: dict[int, str], shape: LeagueShape) -> bool:
    dedicated = {key for key, role in roles.items() if role == "dedicated_starter"}
    selected_flex = {key for key, role in roles.items() if role == "flex_starter"}
    eligible = sorted(
        [
            player
            for player in players
            if player.pos in shape.flex_eligible and player.key not in dedicated
        ],
        key=_rank_key,
    )
    expected = {player.key for player in eligible[: shape.teams * shape.flex]}
    return selected_flex == expected


def parse_shape(args: argparse.Namespace) -> LeagueShape:
    slots = {"QB": args.qb, "RB": args.rb, "WR": args.wr, "TE": args.te}
    bench_caps = {}
    if args.qb_bench_cap is not None:
        bench_caps["QB"] = args.qb_bench_cap
    return LeagueShape(
        teams=args.teams,
        slots=slots,
        flex=args.flex,
        bench=args.bench,
        flex_eligible=tuple(args.flex_eligible.split(",")) if args.flex_eligible else (),
        bench_positions=tuple(args.bench_positions.split(",")) if args.bench_positions else (),
        bench_starter_slots_per_team=args.bench_starter_slots,
        bench_caps=bench_caps,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYERS)
    parser.add_argument("--scoring", default=DEFAULT_SCORING, choices=("standard", "half_ppr", "ppr"))
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--qb", type=int, default=1)
    parser.add_argument("--rb", type=int, default=2)
    parser.add_argument("--wr", type=int, default=3)
    parser.add_argument("--te", type=int, default=0)
    parser.add_argument("--flex", type=int, default=1)
    parser.add_argument("--bench", type=int, default=5)
    parser.add_argument("--flex-eligible", default="RB,WR")
    parser.add_argument("--bench-positions", default="QB,RB,WR")
    parser.add_argument("--bench-starter-slots", type=int, default=2)
    parser.add_argument("--qb-bench-cap", type=int, default=6)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = build_model(load_players(args.players, args.scoring), parse_shape(args))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)
    failed = [key for key, ok in result["validations"].items() if not ok]
    if failed:
        raise SystemExit(f"three-line model validation failed: {', '.join(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
