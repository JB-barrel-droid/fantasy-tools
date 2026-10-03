#!/usr/bin/env python3
"""JEG-182: 8-group proportional imputed VORP (JEG-180 methodology).

For each as-published source (FantasyCalc, USA Today, FantasyPros, CBS):
1. Infer roster: flex = top flex-eligible non-starters by value; bench = top remaining.
2. For each of 8 groups: alloc_factor = our_group_VORP / sum(publisher_values_in_group).
3. Imputed VORP = published_value * alloc_factor.

Our group VORPs come from JEG-206 (pipelines/build_ddf_groups.py).
This is the production implementation of the Option C Sheet logic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

# 8 groups: (position, role). Flex maps to Starter.
GROUPS = [
    ("QB", "starter"), ("QB", "bench"),
    ("RB", "starter"), ("RB", "bench"),
    ("WR", "starter"), ("WR", "bench"),
    ("TE", "starter"), ("TE", "bench"),
]

FLEX_ELIGIBLE = ("RB", "WR", "TE")

# Standard roster: 12 teams, 1 QB / 2 RB / 3 WR / 1 TE / 1 flex / 6 bench
TEAMS = 12
DEDICATED = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
FLEX_PER_TEAM = 1
BENCH_PER_TEAM = 6


@dataclass(frozen=True)
class RosterConfig:
    teams: int
    slots: dict[str, int]
    flex_count: int
    bench_total: int
    scoring: str
    flex_eligible: tuple[str, ...] = FLEX_ELIGIBLE

    def __post_init__(self):
        counts = {"teams": self.teams, "flex_count": self.flex_count, "bench_total": self.bench_total}
        if not isinstance(self.slots, dict) or set(self.slots) != set(DEDICATED):
            raise ValueError("roster slots must define exactly QB/RB/WR/TE")
        counts.update(self.slots)
        if any(type(v) is not int or v < 0 for v in counts.values()) or self.teams == 0:
            raise ValueError("roster counts must be nonnegative integers, teams positive")
        if self.scoring not in ("standard", "half_ppr", "ppr"):
            raise ValueError("unsupported roster scoring")
        if not isinstance(self.flex_eligible, (list, tuple)) or any(
            p not in FLEX_ELIGIBLE for p in self.flex_eligible
        ) or len(set(self.flex_eligible)) != len(self.flex_eligible):
            raise ValueError("invalid/duplicate flex positions")
        if self.flex_count and not self.flex_eligible:
            raise ValueError("positive flex count requires eligible positions")
        object.__setattr__(self, "slots", MappingProxyType(dict(self.slots)))
        object.__setattr__(self, "flex_eligible", tuple(self.flex_eligible))

    def manifest(self):
        return {"schema": "option-c-publisher-roster-v1", "teams": self.teams,
                "slots": dict(self.slots), "flex_count": self.flex_count,
                "flex_eligible": list(self.flex_eligible), "bench_total": self.bench_total,
                "scoring": self.scoring}

    @classmethod
    def from_manifest(cls, raw):
        fields = {"schema", "teams", "slots", "flex_count", "flex_eligible", "bench_total", "scoring"}
        if not isinstance(raw, dict) or set(raw) != fields or raw["schema"] != "option-c-publisher-roster-v1":
            raise ValueError("explicit versioned publisher roster config required")
        return cls(**{k: v for k, v in raw.items() if k != "schema"})


# Compatibility for arithmetic callers only; CLI always requires explicit config.
DEFAULT_ROSTER = RosterConfig(12, DEDICATED, 1, 72, "half_ppr")


def _canonical_number(key):
    if type(key) is int:
        number = key
    elif isinstance(key, str) and key.isascii() and key.isdigit() and str(int(key)) == key:
        number = int(key)
    else:
        raise ValueError(f"expected supplied numeric canonical key: {key!r}")
    if number <= 0:
        raise ValueError("canonical key must be positive")
    return number


def _nonnegative_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected finite nonnegative number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label}: number out of range") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label}: expected finite nonnegative number")
    return number


def _validate_values(values):
    if not isinstance(values, dict):
        raise ValueError("values must be a player-key mapping")
    seen = set()
    for key, row in values.items():
        number = _canonical_number(key)
        if number in seen:
            raise ValueError(f"duplicate canonical key alias: {key}")
        seen.add(number)
        if not isinstance(row, (list, tuple)) or len(row) != 2 or not isinstance(row[0], str) or row[0] not in DEDICATED:
            raise ValueError(f"player {key}: expected skill position and native value")
        _nonnegative_finite(row[1], f"player {key} native")


def _finite_sum(values, label):
    try:
        total = math.fsum(values)
    except OverflowError as exc:
        raise ValueError(f"{label}: aggregate overflow") from exc
    return _nonnegative_finite(total, label)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def infer_roster(
    values: dict[str, tuple[str, float]],
    roster: RosterConfig = DEFAULT_ROSTER,
    *,
    require_complete: bool = False,
) -> dict[str, str]:
    """Dedicated -> flex -> bench -> cut, ties by ascending numeric key.

    Explicit configs support any valid shape. Default supports legacy arithmetic
    callers; only require_complete=True certifies requested roster counts.
    Numeric key format validation does not certify canonical fixture membership.
    """
    if not isinstance(roster, RosterConfig):
        raise ValueError("validated RosterConfig required")
    _validate_values(values)
    ranked = sorted(values.items(), key=lambda kv: (-kv[1][1], _canonical_number(kv[0])))
    roles = {key: "cut" for key in values}
    for pos in DEDICATED:
        pool = [key for key, (p, _) in ranked if p == pos]
        need = roster.teams * roster.slots[pos]
        if require_complete and len(pool) < need:
            raise ValueError(f"incomplete dedicated {pos} pool: {len(pool)} < {need}")
        for key in pool[:need]:
            roles[key] = "starter"
    flex_pool = [key for key, (pos, _) in ranked if roles[key] == "cut" and pos in roster.flex_eligible]
    n_flex = roster.teams * roster.flex_count
    if require_complete and len(flex_pool) < n_flex:
        raise ValueError("incomplete eligible flex pool")
    for key in flex_pool[:n_flex]:
        roles[key] = "starter"
    remaining = [key for key, _ in ranked if roles[key] == "cut"]
    if require_complete and len(remaining) < roster.bench_total:
        raise ValueError("incomplete bench pool")
    for key in remaining[:roster.bench_total]:
        roles[key] = "bench"
    return roles


def compute_imputed_vorps(
    values: dict[str, tuple[str, float]],
    our_group_vorps: dict[tuple[str, str], float],
    roster: RosterConfig = DEFAULT_ROSTER,
    *,
    require_complete: bool = False,
) -> dict[str, dict[str, Any]]:
    """Compute imputed VORP per player via 8-group proportional allocation.

    values: {player_key: (position, published_value)}
    our_group_vorps: {(position, role): total_vorp} from JEG-206

    Returns: {player_key: {"group": "POS|role", "alloc_factor": float,
                           "imputed_vorp": float, "native": float}}
    """
    if not isinstance(our_group_vorps, dict) or set(our_group_vorps) != set(GROUPS):
        raise ValueError("group targets must contain exactly the eight skill position/role groups")
    targets = {g: _nonnegative_finite(our_group_vorps[g], f"target {g}") for g in GROUPS}
    roles = infer_roster(values, roster, require_complete=require_complete)

    # Sum publisher values per group
    group_sums: dict[tuple[str, str], list[float]] = {
        g: [] for g in GROUPS
    }
    for pkey, (pos, val) in values.items():
        role = roles.get(pkey)
        if role == "cut":
            continue  # explicit zero row, outside the eight groups
        group_sums[(pos, role)].append(val)

    # Allocation factor per group
    alloc: dict[tuple[str, str], float] = {}
    for g in GROUPS:
        s = _finite_sum(group_sums[g], f"native sum {g}")
        if s == 0 and targets[g] > 0:
            raise ValueError(f"infeasible group {g}: positive target without positive native pool")
        alloc[g] = _nonnegative_finite(targets[g] / s if s else 0.0, f"factor {g}")

    # Imputed VORP per player
    result = {}
    for pkey, (pos, val) in values.items():
        role = roles.get(pkey)
        if role == "cut":
            result[pkey] = {"group": f"{pos}|Cut", "alloc_factor": 0.0,
                            "imputed_vorp": 0.0, "native": val}
            continue
        g = (pos, role)
        imputed = _nonnegative_finite(val * alloc[g], f"imputed {pkey}")
        result[pkey] = {
            "group": f"{pos}|{role.title()}",
            "alloc_factor": alloc[g],
            "imputed_vorp": imputed,
            "native": val,
        }
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--values", type=Path, required=True,
                    help="JSON: {player_key: [position, published_value]}")
    ap.add_argument("--group-vorps", type=Path, required=True,
                    help="JSON: JEG-206 output (dist/modules/ddf-group-vorps.json)")
    ap.add_argument("--roster-config", type=Path, required=True,
                    help="JSON: option-c-publisher-roster-v1; explicit shape, scoring and bench_total")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    value_bytes, group_bytes, config_bytes = (p.read_bytes() for p in (args.values, args.group_vorps, args.roster_config))
    values = json.loads(value_bytes, object_pairs_hook=_unique_object)
    gv_raw = json.loads(group_bytes, object_pairs_hook=_unique_object)
    roster = RosterConfig.from_manifest(json.loads(config_bytes, object_pairs_hook=_unique_object))
    if not isinstance(gv_raw, dict):
        raise ValueError("group artifact must be an object")
    target_roster = gv_raw.get("roster")
    if (type(gv_raw.get("teams")) is not int or gv_raw["teams"] != roster.teams
            or gv_raw.get("scoring") != roster.scoring or not isinstance(target_roster, dict)
            or target_roster.get("slots") != dict(roster.slots)
            or type(target_roster.get("flex_count")) is not int or target_roster["flex_count"] != roster.flex_count
            or target_roster.get("flex_eligible") != list(roster.flex_eligible)):
        raise ValueError("publisher config does not match target teams/scoring/slots/flex")
    if not isinstance(gv_raw, dict) or not isinstance(gv_raw.get("groups"), list):
        raise ValueError("group artifact must have a groups list")
    target_slots = target_roster.get("slots")
    target_bench_mix = target_roster.get("bench_mix")
    if (not isinstance(target_slots, dict) or any(type(v) is not int or v < 0 for v in target_slots.values())
            or not isinstance(target_bench_mix, dict) or set(target_bench_mix) != set(DEDICATED)
            or any(type(v) is not int or v < 0 for v in target_bench_mix.values())):
        raise ValueError("target slots and bench_mix require explicit nonnegative integer counts")
    our_vorps = {}
    for row in gv_raw["groups"]:
        if not isinstance(row, dict) or not {"position", "role", "total_vorp"}.issubset(row):
            raise ValueError("malformed group target row")
        group = row["position"], row["role"]
        if group not in GROUPS or group in our_vorps:
            raise ValueError(f"unknown or duplicate group target: {group}")
        our_vorps[group] = row["total_vorp"]

    result = compute_imputed_vorps(values, our_vorps, roster, require_complete=True)
    manifest = {"schema": "option-c-imputation-manifest-v1", "method": "eight-group-proportional-v1",
                "publisher_roster": roster.manifest(), "target_group_roster": target_roster,
                "target_units": gv_raw.get("units"), "target_bench_total": sum(target_bench_mix.values()),
                "input_sha256": {"values": hashlib.sha256(value_bytes).hexdigest(),
                                 "group_targets": hashlib.sha256(group_bytes).hexdigest(),
                                 "roster_config": hashlib.sha256(config_bytes).hexdigest()},
                "role_counts": {r: sum(rec["group"].endswith("|" + r.title()) for rec in result.values())
                                for r in ("starter", "bench", "cut")}}
    # Serialize both before writing either; metadata failure cannot overwrite output.
    result_json = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    manifest["output_sha256"] = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(result_json, encoding="utf-8")
    args.out.with_suffix(args.out.suffix + ".manifest.json").write_text(manifest_json, encoding="utf-8")
    print(f"Wrote {len(result)} imputed VORPs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
