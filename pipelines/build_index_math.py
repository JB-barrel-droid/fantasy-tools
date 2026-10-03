#!/usr/bin/env python3
"""Build native-only Indexed target arithmetic for published trade charts.

No VORP, DDF, isotonic fit, or fixture reindexed values enter this diagnostic.
This is a target rescale report, not verification of currently rendered values.
The standalone legacy verify_ddf_leg helper remains for existing Adj audits.
Output: dist/modules/index-math.json.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
LEG_DIR = REPO / "data" / "ddf-two-tier"
OUTPUT = REPO / "dist" / "modules" / "index-math.json"

SOURCES = ["espn", "cbs", "cbsros", "razzball", "fantasycalc", "fantasypros", "usatoday"]
SRC_LABEL = {
    "espn": "ESPN",
    "cbs": "CBS",
    "cbsros": "CBS ROS",
    "razzball": "Razzball",
    "fantasycalc": "FantasyCalc",
    "fantasypros": "FantasyPros",
    "usatoday": "USA Today",
}

def verify_ddf_leg(src, label, bake_mark, leg_filename):
    """Verify a DDF-methodology source: fixture values == DDF leg values.

    Parametrized over ESPN (bake '-espn-', file ddf_leg.json), CBS ROS
    (bake '-cbsros-', file ddf_leg_cbsros.json), and Razzball
    (bake '-razzball-', file ddf_leg_razzball.json). Non-ESPN leg filenames
    are deliberately distinct so the ESPN globs never pick them up.
    """
    fixture = json.loads(FIXTURE.read_text())
    src_data = fixture["sources"][src]
    
    # Load DDF legs - pick the NEWEST vintage for each scoring
    # (glob order is filesystem-dependent; older legs like 20260921 must not shadow 20260929)
    legs = {}
    for scoring in ["ppr", "half_ppr", "standard"]:
        # Collect all matching legs, pick the one with the newest bake_id (date prefix)
        candidates = []
        for leg_path in LEG_DIR.glob(f"*/{leg_filename}"):
            leg = json.loads(leg_path.read_text())
            bake_id = leg.get("bake_id", "")
            # 12-team legs only: the combos under test are *_12. (String sort
            # on bake_id would otherwise prefer "-8t-" over "-12t-".)
            if bake_mark.format(scoring=scoring) in bake_id and "-12t-" in bake_id:
                candidates.append((bake_id, leg))
        if candidates:
            # Sort by bake_id descending (newest date first: ddf-20260929 > ddf-20260921)
            candidates.sort(key=lambda x: x[0], reverse=True)
            bake_id, leg = candidates[0]
            legs[scoring] = {
                row["player_norm"]: round(row["value"], 1)
                for row in leg.get("values", [])
                if row.get("player_norm") and isinstance(row.get("value"), (int, float))
            }
    
    results = {
        "methodology": "DDF two-tier",
        "formula": "native (ppg) → DDF value-above-waivers → scale to 70 → values",
        "steps": [
            f"1. Start with {label} per-game projection (native/ppg)",
            "2. Compute value-above-waivers via DDF two-tier (positional scarcity, starter/bench weights)",
            "3. Scale to 70-point index (fixed-pie methodology)",
            "4. Round to 1 decimal → fixture values",
        ],
        "combos": {},
        "status": "ok",
        "mismatches": [],
    }
    
    scoring_map = {"ppr": "full_12", "half_ppr": "half_12", "standard": "standard_12"}
    total_checked = 0
    total_matched = 0
    
    for scoring, combo_name in scoring_map.items():
        if scoring not in legs:
            continue
        combo = src_data["combos"].get(combo_name, {})
        fixture_vals = combo.get("values", {})
        leg_vals = legs[scoring]
        
        combo_result = {
            "checked": 0,
            "matched": 0,
            "samples": [],
        }
        
        # Check top 20 by fixture value
        sorted_fixture = sorted(fixture_vals.items(), key=lambda x: x[1], reverse=True)[:20]
        for slug, fval in sorted_fixture:
            lval = leg_vals.get(slug)
            if lval is None:
                continue
            combo_result["checked"] += 1
            total_checked += 1
            if abs(fval - lval) < 0.05:  # Allow rounding
                combo_result["matched"] += 1
                total_matched += 1
            else:
                results["mismatches"].append({
                    "combo": combo_name,
                    "player": slug,
                    "fixture": fval,
                    "leg": lval,
                    "diff": round(fval - lval, 3),
                })
        
        # Samples for display
        for slug, fval in sorted_fixture[:3]:
            native = combo.get("native", {}).get(slug)
            lval = leg_vals.get(slug)
            combo_result["samples"].append({
                "player": slug,
                "native": native,
                "leg_value": lval,
                "fixture_value": fval,
                "match": abs(fval - lval) < 0.05 if lval else False,
            })
        
        results["combos"][combo_name] = combo_result
    
    if results["mismatches"]:
        results["status"] = "bad"
        results["reason"] = f"{len(results['mismatches'])} mismatches"
    else:
        results["reason"] = f"All {total_matched}/{total_checked} verified exact"
    
    return results

def simple_native_rescale(native):
    """Indexed trade charts: one positive factor; no VORP, DDF or fit metadata."""
    if not isinstance(native, dict) or not native:
        raise ValueError("native trade chart unavailable")
    if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                             or not math.isfinite(v) or v < 0) for v in native.values()):
        raise ValueError("invalid native trade value")
    priced = [v for v in native.values() if v is not None]
    if not priced or max(priced) <= 0:
        raise ValueError("no positive native maximum to rescale")
    factor = 70.0 / max(priced)
    if not math.isfinite(factor):
        raise ValueError("native rescale factor is not finite")
    return factor, {key: value * factor if value is not None else None
                    for key, value in native.items()}


def verify_reindexed(src):
    """Native-only Indexed target arithmetic; not rendered chart verification."""
    fixture = json.loads(FIXTURE.read_text())
    src_data = fixture.get("sources", {}).get(src, {})
    results = {
        "view": "indexed", "methodology": "simple-native-rescale",
        "formula": "indexed = native * 70 / max(native)",
        "steps": ["1. Read the publisher's native trade values for the exact combo",
                  "2. Multiply every priced value by 70 / maximum native value",
                  "3. Preserve genuine zero and missing values; no VORP or roster adjustment",
                  "4. Target arithmetic only; rendered Indexed wiring is not certified"],
        "combos": {}, "status": "warn", "mismatches": [],
        "reason": "Native-only target rescale; rendered Indexed values have not been verified.",
    }
    for combo_name, combo in src_data.get("combos", {}).items():
        if not isinstance(combo, dict):
            continue
        try:
            factor, indexed = simple_native_rescale(combo.get("native"))
        except ValueError as exc:
            results["combos"][combo_name] = {"status": "unk", "reason": str(exc), "samples": []}
            continue
        priced = sorted(((k,v) for k,v in combo["native"].items() if v is not None),
                        key=lambda row: (-row[1], row[0]))
        results["combos"][combo_name] = {
            "status": "warn", "factor": factor, "n_native": len(priced),
            "rendered_verified": False,
            "samples": [{"player": k, "native": v, "reindexed": indexed[k],
                         "match": None} for k,v in priced[:3]],
        }
    if not results["combos"]:
        results["status"] = "unk"
        results["reason"] = "No native trade chart combos available."
    return results

def main():
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {},
    }
    
    # Indexed applies only to native published trade charts. Projection sources
    # have no Indexed trade values; their DDF verification is an Adj diagnostic.
    report["view"] = "indexed"
    report["model"] = "simple-native-rescale"
    report["rendered_verified"] = False
    for src in ["cbs", "fantasycalc", "fantasypros", "usatoday"]:
        report["sources"][src] = verify_reindexed(src)
        report["sources"][src]["label"] = SRC_LABEL[src]

    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUTPUT}")
    for src, r in report["sources"].items():
        print(f"  {src}: {r['status']} - {r['reason']}")

if __name__ == "__main__":
    main()
