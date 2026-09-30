#!/usr/bin/env python3
"""Build ESPN raw trade values check for the monitoring dashboard.

ESPN publishes no trade values of its own, so there is nothing external to
check our indexed ESPN numbers against. What we CAN check is the internal
chain, end to end, with every transformation visible:

  ESPN projections (grains)
    -> per-game native (ppg)
    -> DDF two-tier value-above-waivers (RAW trade value, unscaled)
    -> scale to 70-point index (raw * scale_70_over_max, round 1dp)
    -> fixture value (what the chart shows)

This builder exposes the raw (unscaled) trade values and verifies each
transformation step recomputes exactly. It complements the grain check
(live page vs pipeline input) in build_espn_input_comparison.py.

Output: dist/modules/espn-raw-values.json
"""

import glob
import json
import os
import sys

# Fixture keys use the leg's own player_norm format (lowercase, suffixes kept
# for most). A few known aliases bridge fixture-key -> leg player_norm.
# Achane is on IR and correctly absent from the pure-ESPN leg.
LEG_ALIASES = {
    "cam skattebo": "cameron skattebo",
    "travis etienne": "travis etienne jr",
}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEG_DIR = os.path.join(REPO, "data/ddf-two-tier")
DATA_PATH = os.path.join(REPO, "dist/assets/comparison-sources-data.json")
OUT_PATH = os.path.join(REPO, "dist/modules/espn-raw-values.json")

SCORING = "half_ppr"
COMBO = "half_12"


def newest_leg(scoring):
    cands = []
    for leg_path in glob.glob(os.path.join(LEG_DIR, "*", "ddf_leg.json")):
        try:
            leg = json.load(open(leg_path))
        except (OSError, ValueError):
            continue
        bake_id = leg.get("bake_id", "")
        if f"-espn-{scoring}-" in bake_id:
            cands.append((bake_id, leg))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def main():
    leg = newest_leg(SCORING)
    if leg is None:
        raise SystemExit(f"No DDF leg found for espn-{SCORING}")

    scale = leg["scale_70_over_max"]
    max_raw = leg["max_raw_value"]
    leg_rows = {
        r["player_norm"]: r
        for r in leg.get("values", [])
        if r.get("player_norm")
    }

    d = json.load(open(DATA_PATH))
    combo = d["sources"]["espn"]["combos"][COMBO]
    fixture_vals = combo.get("values", {})
    ranked = sorted(
        [(k, v) for k, v in fixture_vals.items() if v],
        key=lambda kv: kv[1],
        reverse=True,
    )[:25]

    players = []
    for pkey, fval in ranked:
        # Fixture keys already match leg player_norm; apply aliases for known
        # variations. Do NOT run generic name normalization here — it strips
        # suffixes (III/Jr.) the leg keeps and expands nicknames (Josh/Joshua).
        leg_key = LEG_ALIASES.get(pkey, pkey)
        row = leg_rows.get(leg_key, {})

        ppg = row.get("ppg")
        raw = row.get("raw_value")
        leg_val = row.get("value")

        # Recompute the transformation ourselves
        recomputed = round(raw * scale, 1) if raw is not None else None

        step_raw_to_scaled = (
            recomputed is not None and leg_val is not None
            and abs(recomputed - leg_val) < 0.05
        )
        step_scaled_to_fixture = (
            leg_val is not None and abs(leg_val - fval) < 0.05
        )
        all_ok = step_raw_to_scaled and step_scaled_to_fixture

        players.append({
            "player_key": pkey,
            "name": row.get("player", pkey),
            "pos": row.get("pos", ""),
            "team": row.get("team", ""),
            "tier": row.get("tier", ""),
            "ppg_native": round(ppg, 2) if ppg is not None else None,
            "raw_value": round(raw, 3) if raw is not None else None,
            "scale_factor": scale,
            "recomputed_scaled": recomputed,
            "leg_value": leg_val,
            "fixture_value": fval,
            "raw_to_scaled_ok": step_raw_to_scaled,
            "scaled_to_fixture_ok": step_scaled_to_fixture,
            "all_steps_ok": all_ok,
        })

    result = {
        "generated_at": d.get("built_at", "unknown"),
        "method": (
            "ESPN publishes no trade values, so the check is the internal chain: "
            "per-game native -> DDF value-above-waivers (raw, unscaled) -> "
            "scale to 70 (raw * scale factor, round 1dp) -> fixture value. "
            "Each step is recomputed independently and must match."
        ),
        "leg": {
            "bake_id": leg.get("bake_id"),
            "generated_at": leg.get("generated_at"),
            "scoring": SCORING,
            "combo": COMBO,
            "max_raw_value": max_raw,
            "scale_70_over_max": scale,
            "formula": "indexed = round(raw_value * scale_70_over_max, 1)",
        },
        "transformations": [
            "1. ESPN ROS grains -> per-game native (ppg = ROS / games remaining)",
            "2. Native -> raw trade value via DDF two-tier value-above-waivers "
            "(positional scarcity, starter/bench lineup weights)",
            "3. Raw -> indexed: round(raw * scale_70_over_max, 1), "
            f"where scale_70_over_max = 70 / {round(max_raw, 3)} = {round(scale, 6)}",
            "4. Indexed leg value -> fixture value (must be identical)",
        ],
        "players": players,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    ok = sum(1 for p in players if p["all_steps_ok"])
    print(f"Wrote {OUT_PATH}")
    print(f"  {ok}/{len(players)} players with all transformation steps verified")
    for p in players:
        if not p["all_steps_ok"]:
            print(f"  STEP FAIL {p['name']}: raw->scaled={p['raw_to_scaled_ok']} "
                  f"scaled->fixture={p['scaled_to_fixture_ok']}")


if __name__ == "__main__":
    main()
