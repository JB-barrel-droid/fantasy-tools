#!/usr/bin/env python3
"""JEG-209/240: full-precision shared batch70 candidate views.

Policy targets (remaining reference/control/integration work is JEG241–243):
1. LINEAR allocation — no squared premium. Budget share = VORP / sum(VORP).
2. BLEND reference — group budgets from the DDF blend leg's pie totals, not ESPN alone.
3. 70 ANCHOR — one maximum across all included sources; one common factor.
4. INVERSIONS — within-position (bench > starter) ironed out; cross-position allowed.
5. 8-BOX CONTROLS — CLI requires all eight explicit user weights; verified defaults pending JEG243.

Input: imputed VORP artifact from build_imputed_vorps.py
Output: chart values 0-70 per player per source (three views: Indexed, VORP, Adj Values)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .build_imputed_vorps import (RosterConfig, _canonical_number, _finite_sum,
                                     _nonnegative_finite, _unique_object)
else:
    from build_imputed_vorps import (RosterConfig, _canonical_number, _finite_sum,
                                    _nonnegative_finite, _unique_object)

# 8 groups for budget allocation
GROUPS = [
    ("QB", "starter"), ("QB", "bench"),
    ("RB", "starter"), ("RB", "bench"),
    ("WR", "starter"), ("WR", "bench"),
    ("TE", "starter"), ("TE", "bench"),
]

DISPLAY_MAX = 70.0


def load_group_budgets(
    ddf_leg_path: Path,
    controls_path: Path | None = None,
) -> dict[tuple[str, str], float]:
    """Legacy calibration reader, unused by the batch CLI.

    Verified linear blend defaults require the separate JEG243 contract.

    Decision 2: blend (not ESPN alone) as pinned economics reference.
    Decision 5: defaults from pipeline, user-adjustable via --controls JSON.
    Controls format: {"QB/starter": 123.4, ...} — overrides specific boxes.
    """
    leg = json.loads(ddf_leg_path.read_text())
    budgets = {}
    for pos, role in GROUPS:
        # DDF leg calibration: {POS: {starter_raw, bench_raw, pie}}
        cal = leg["calibration"][pos]
        key = "starter_raw" if role == "starter" else "bench_raw"
        budgets[(pos, role)] = float(cal[key])

    if controls_path:
        overrides = json.loads(controls_path.read_text())
        for k, v in overrides.items():
            pos, role = k.split("/")
            budgets[(pos, role)] = float(v)

    return budgets


def _validate_budgets(budgets):
    if not isinstance(budgets, dict) or set(budgets) != set(GROUPS):
        raise ValueError("exact eight group budgets required")
    return {g: _nonnegative_finite(v, f"budget {g}") for g, v in budgets.items()}


def _validate_imputed(imputed):
    if not isinstance(imputed, dict):
        raise ValueError("imputed player mapping required")
    seen = set()
    for key, rec in imputed.items():
        number = _canonical_number(key)
        if number in seen:
            raise ValueError("duplicate canonical key alias")
        seen.add(number)
        if not isinstance(rec, dict) or not isinstance(rec.get("group"), str):
            raise ValueError("malformed imputed row")
        parts = rec["group"].split("|")
        if len(parts) != 2 or parts[0] not in ("QB", "RB", "WR", "TE") or parts[1].lower() not in ("starter", "bench", "cut"):
            raise ValueError("unknown imputed position/role")
        u = _nonnegative_finite(rec.get("imputed_vorp"), f"VORP {key}")
        if parts[1].lower() == "cut" and u != 0:
            raise ValueError("Cut VORP must be genuine zero")


def linear_reweight(imputed, budgets):
    """Full-precision group proportions; unavailable funded pools reject."""
    budgets = _validate_budgets(budgets)
    _validate_imputed(imputed)
    groups = {g: [] for g in GROUPS}
    result = {}
    for key, rec in imputed.items():
        pos, role = rec["group"].split("|")
        if role.lower() == "cut":
            result[key] = 0.0
        else:
            groups[pos, role.lower()].append(key)
    for g, keys in groups.items():
        total = _finite_sum((imputed[k]["imputed_vorp"] for k in keys), f"VORP sum {g}")
        if budgets[g] > 0 and total == 0:
            raise ValueError(f"funded group {g} has no positive source pool")
        for key in keys:
            result[key] = _nonnegative_finite(imputed[key]["imputed_vorp"]/total*budgets[g] if total else 0.0,
                                               f"provisional {key}")
    return result


def iron_within_position_inversions(
    values: dict[str, float],
    imputed: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Iron out within-position inversions (bench player > starter at same position).

    Decision 4: within-position inversions are bugs, iron them out.
    Cross-position inversions (bench RB > starter TE) are legitimate economics — leave them.

    Linear rescale preserves order within (pos, role) groups, so true inversions
    should not occur. This is a safety net: if a bench player's value exceeds
    the lowest starter at the same position, clamp it.
    """
    # Group by position, separate starter/bench
    by_pos: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for pkey, rec in imputed.items():
        pos, role = rec["group"].split("|")
        role = role.lower()
        if role == "cut":
            continue
        by_pos.setdefault(pos, {"starter": [], "bench": []})
        by_pos[pos][role].append((pkey, values[pkey]))

    result = dict(values)
    for pos, roles in by_pos.items():
        if not roles["starter"] or not roles["bench"]:
            continue
        min_starter = min(v for _, v in roles["starter"])
        for pkey, val in roles["bench"]:
            if val > min_starter:
                # Iron out: clamp bench to just below lowest starter
                result[pkey] = min_starter * 0.999

    return result


def apply_70_anchor(values, *, batch_maximum):
    """Scale by a supplied shared batch maximum; never derive a local scale."""
    if not isinstance(values, dict):
        raise ValueError("provisional player mapping required")
    maximum = _nonnegative_finite(batch_maximum, "batch maximum")
    if maximum == 0:
        raise ValueError("positive batch maximum required")
    scale = _nonnegative_finite(DISPLAY_MAX/maximum, "batch scale")
    result = {}
    for key, value in values.items():
        value = _nonnegative_finite(value, f"provisional {key}")
        if value > maximum:
            raise ValueError("player exceeds declared batch maximum")
        result[key] = _nonnegative_finite(value*scale, f"adjusted {key}")
    return result


def _prepare_values(imputed, budgets):
    values = linear_reweight(imputed, budgets)
    ironed = iron_within_position_inversions(values, imputed)
    if ironed != values:
        raise ValueError("within-position inversion needs conserving budget constraint (JEG241); refusing player clamp")
    return values


def build_three_views(imputed, native_values, budgets, *, batch_maximum):
    """Single-source adapter requires the caller's common batch maximum."""
    values = _prepare_values(imputed, budgets)
    return {"indexed": dict(native_values),
            "vorp": {k: r["imputed_vorp"] for k, r in imputed.items()},
            "adj_values": apply_70_anchor(values, batch_maximum=batch_maximum)}


def build_batch_three_views(imputed_sources, native_sources, budgets):
    """One source manifest, unit allocation fractions and one maximum70 scale."""
    if not isinstance(imputed_sources, dict) or not imputed_sources or not isinstance(native_sources, dict) or set(imputed_sources) != set(native_sources):
        raise ValueError("nonempty matching source manifests required")
    if any(not isinstance(s, str) or not s for s in imputed_sources):
        raise ValueError("explicit source names required")
    budgets = _validate_budgets(budgets)
    total = _finite_sum(budgets.values(), "budget sum")
    if total == 0:
        raise ValueError("positive budget required")
    fractions = {g: b/total for g, b in budgets.items()}
    if any(budgets[g] > 0 and fractions[g] == 0 for g in GROUPS):
        raise ValueError("allocation fraction underflow")
    provisional = {}
    for source, pool in imputed_sources.items():
        _validate_imputed(pool)
        native = native_sources[source]
        if not isinstance(native, dict) or (native and set(native) != set(pool)):
            raise ValueError("native pool must match imputed keys, or explicitly be unavailable")
        for key, value in native.items():
            _nonnegative_finite(value, f"native {source}/{key}")
        provisional[source] = _prepare_values(pool, fractions)
    maximum = max((v for pool in provisional.values() for v in pool.values()), default=0.0)
    if maximum <= 0:
        raise ValueError("positive comparison batch peak required")
    scale = _nonnegative_finite(DISPLAY_MAX/maximum, "batch scale")
    outputs = {}
    for source, values in provisional.items():
        adjusted = apply_70_anchor(values, batch_maximum=maximum)
        outputs[source] = {"indexed": dict(native_sources[source]),
                           "vorp": {k: r["imputed_vorp"] for k, r in imputed_sources[source].items()},
                           "adj_values": adjusted}
        if not math.isclose(_finite_sum(adjusted.values(), "adjusted sum"), scale, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("source total does not conserve shared budget")
    return {"schema": "shared-batch70-views-v1", "artifact_status": "candidate", "batch_scale": scale,
            "provisional_maximum": maximum, "total_budget_per_source": scale,
            "allocation_fractions": {f"{p}/{r}": v for (p, r), v in fractions.items()},
            "group_budgets": {f"{p}/{r}": scale*v for (p, r), v in fractions.items()},
            "sources": outputs}


SOURCE_KINDS = {"fantasycalc": "published", "usat": "published", "fantasypros": "published",
                "cbs": "published", "espn": "granular", "cbsros": "granular", "razzball": "granular"}


def load_source_batch(path):
    """Read pinned source artifacts; missing sources need explicit exclusions."""
    batch_bytes = path.read_bytes()
    raw = json.loads(batch_bytes, object_pairs_hook=_unique_object)
    if not isinstance(raw, dict) or raw.get("schema") != "vorp-source-batch-v1":
        raise ValueError("versioned source batch required")
    sources, excluded = raw.get("sources"), raw.get("excluded_sources")
    if (not isinstance(sources, dict) or not sources or not isinstance(excluded, dict)
            or set(sources) & set(excluded) or set(sources) | set(excluded) != set(SOURCE_KINDS)
            or any(not isinstance(v, str) or not v.strip() for v in excluded.values())):
        raise ValueError("every source must be included or explicitly excluded with a reason")
    config = RosterConfig.from_manifest(raw.get("configuration"))
    imputed, natives, pins = {}, {}, {}
    common = ("teams", "scoring", "slots", "flex_count", "flex_eligible")
    for source, entry in sources.items():
        if not isinstance(entry, dict) or set(entry) != {"values", "manifest"} or any(not isinstance(v, str) for v in entry.values()):
            raise ValueError("source artifact and sidecar paths required")
        value_bytes = (path.parent / entry["values"]).read_bytes()
        meta_bytes = (path.parent / entry["manifest"]).read_bytes()
        pool = json.loads(value_bytes, object_pairs_hook=_unique_object)
        meta = json.loads(meta_bytes, object_pairs_hook=_unique_object)
        digest = hashlib.sha256(value_bytes).hexdigest()
        if not isinstance(meta, dict) or meta.get("output_sha256") != digest:
            raise ValueError("source artifact/manifest hash mismatch")
        kind = SOURCE_KINDS[source]
        expected = (("option-c-imputation-manifest-v1", "eight-group-proportional-v1") if kind == "published"
                    else ("granular-vorp-manifest-v1", "ppg-above-waiver-v1"))
        if (meta.get("schema"), meta.get("method")) != expected:
            raise ValueError("source VORP method/schema mismatch")
        source_config = meta.get("publisher_roster" if kind == "published" else "source_config")
        if kind == "published":
            RosterConfig.from_manifest(source_config)
        else:
            fields = {"schema", "teams", "scoring", "slots", "flex_count", "flex_eligible", "bench_mix"}
            if (not isinstance(source_config, dict) or set(source_config) != fields
                    or source_config["schema"] != "granular-roster-config-v1"
                    or not isinstance(source_config["bench_mix"], dict)
                    or set(source_config["bench_mix"]) != {"QB", "RB", "WR", "TE"}
                    or any(type(v) is not int or v < 0 for v in source_config["bench_mix"].values())):
                raise ValueError("invalid granular source configuration")
            RosterConfig(source_config["teams"], source_config["slots"], source_config["flex_count"],
                         sum(source_config["bench_mix"].values()), source_config["scoring"],
                         source_config["flex_eligible"])
        if not isinstance(source_config, dict) or any(source_config.get(k) != config.manifest()[k] for k in common):
            raise ValueError("source configuration mismatch")
        _validate_imputed(pool)
        imputed[source] = pool
        natives[source] = ({k: rec.get("native") for k, rec in pool.items()} if kind == "published" else {})
        pins[source] = {"values_sha256": digest, "manifest_sha256": hashlib.sha256(meta_bytes).hexdigest(),
                        "manifest": meta}
    return imputed, natives, {"batch_sha256": hashlib.sha256(batch_bytes).hexdigest(),
                             "configuration": config.manifest(), "excluded_sources": excluded, "input_pins": pins}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Shared batch70 candidate; explicit source manifest and eight controls required.")
    ap.add_argument("--batch", type=Path, required=True, help="vorp-source-batch-v1 JSON")
    ap.add_argument("--controls", type=Path, required=True, help="JSON: all eight POS/role nonnegative weights")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    imputed, native, pins = load_source_batch(args.batch)
    control_bytes = args.controls.read_bytes()
    raw = json.loads(control_bytes, object_pairs_hook=_unique_object)
    if not isinstance(raw, dict) or set(raw) != {f"{p}/{r}" for p,r in GROUPS}:
        raise ValueError("complete explicit eight controls required; default reference contract pending JEG243")
    budgets = {g: raw[f"{g[0]}/{g[1]}"] for g in GROUPS}
    result = build_batch_three_views(imputed, native, budgets)
    result["manifest"] = {**pins, "controls_sha256": hashlib.sha256(control_bytes).hexdigest()}
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"Wrote shared batch70 views for {len(result['sources'])} sources -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
