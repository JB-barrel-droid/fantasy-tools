#!/usr/bin/env python3
"""Build aggregate diagnostics for the monitoring dashboard.

Checks:
1. Position totals per source — do they sum to reasonable values?
2. Cross-source player anomalies — players with unusually high disagreement
3. Curve shape checks — is the value distribution smooth?

Output: dist/modules/aggregate-diagnostics.json
"""

import json
from pathlib import Path
from collections import defaultdict
import statistics

REPO = Path(__file__).resolve().parent.parent

def load_fixture():
    path = REPO / "data/fixtures/current/comparison-sources-data.json"
    return json.load(open(path))

def load_player_trace():
    path = REPO / "dist/modules/player-trace.json"
    try:
        return json.load(open(path))
    except:
        return None

def build_diagnostics():
    fixture = load_fixture()
    trace = load_player_trace()
    
    diagnostics = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "position_totals": {},
        "anomalies": [],
        "curve_checks": {},
    }
    
    # 1. Position totals per source
    # We need position info - get from the fixture structure
    # For now, use the trace data which has player info
    if trace:
        for src in trace.get("sources", []):
            totals = defaultdict(float)
            counts = defaultdict(int)
            for player in trace.get("players", []):
                sdata = player.get("sources", {}).get(src, {})
                for combo_key, cdata in sdata.get("combos", {}).items():
                    val = cdata.get("fixture_reindexed") or cdata.get("reindexed_value")
                    if val and val > 0:
                        # We don't have position in trace, skip for now
                        # This would need position data from the canonical map
                        pass
            
            diagnostics["position_totals"][src] = {
                "note": "Position breakdown requires canonical position map - TODO"
            }
    
    # 2. Cross-source anomalies
    # Find players with high cross-source disagreement
    if trace:
        for player in trace.get("players", []):
            values = []
            for src in trace.get("sources", []):
                sdata = player.get("sources", {}).get(src, {})
                for combo_key, cdata in sdata.get("combos", {}).items():
                    # Use 12-team full_ppr or half_ppr for consistency
                    if "12" in combo_key:
                        val = cdata.get("fixture_reindexed") or cdata.get("reindexed_value")
                        if val and val > 0:
                            values.append((src, val))
                            break  # Only one combo per source
            
            if len(values) >= 3:  # Need at least 3 sources to compare
                vals = [v for _, v in values]
                min_v, max_v = min(vals), max(vals)
                mid = (max_v + min_v) / 2
                spread_pct = (max_v - min_v) / mid * 100 if mid > 0 else 0
                
                if spread_pct > 75:  # High disagreement threshold
                    diagnostics["anomalies"].append({
                        "player": player["name"],
                        "player_key": player["player_key"],
                        "spread_pct": round(spread_pct, 1),
                        "min": round(min_v, 1),
                        "max": round(max_v, 1),
                        "values": {src: round(v, 1) for src, v in values},
                        "severity": "high" if spread_pct > 100 else "medium",
                    })
        
        # Sort by spread descending
        diagnostics["anomalies"].sort(key=lambda x: x["spread_pct"], reverse=True)
        diagnostics["anomalies"] = diagnostics["anomalies"][:20]  # Top 20
    
    # 3. Curve shape checks
    # For each source, check if the value distribution is smooth (no spikes)
    if trace:
        for src in trace.get("sources", []):
            # Get all fixture values for this source, sorted
            all_vals = []
            for player in trace.get("players", []):
                sdata = player.get("sources", {}).get(src, {})
                for combo_key, cdata in sdata.get("combos", {}).items():
                    if "12" in combo_key:  # Use 12-team
                        val = cdata.get("fixture_reindexed") or cdata.get("reindexed_value")
                        if val and val > 0:
                            all_vals.append(val)
                            break
            
            if len(all_vals) > 10:
                all_vals.sort(reverse=True)
                # Check for spikes: value[i] should be <= value[i-1] * 1.5 (no 50% jumps)
                spikes = []
                for i in range(1, min(len(all_vals), 100)):  # Check top 100
                    if all_vals[i] > all_vals[i-1] * 1.5:
                        spikes.append({
                            "rank": i + 1,
                            "prev": round(all_vals[i-1], 1),
                            "curr": round(all_vals[i], 1),
                            "ratio": round(all_vals[i] / all_vals[i-1], 2),
                        })
                
                diagnostics["curve_checks"][src] = {
                    "n_players": len(all_vals),
                    "max": round(max(all_vals), 1),
                    "min": round(min(all_vals), 1),
                    "spikes": spikes[:5],  # Top 5 spikes
                    "smooth": len(spikes) == 0,
                }
    
    return diagnostics

def main():
    diag = build_diagnostics()
    out_path = REPO / "dist/modules/aggregate-diagnostics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(diag, open(out_path, "w"), indent=2)
    print(f"Wrote {out_path}")
    print(f"  Anomalies: {len(diag['anomalies'])}")
    print(f"  Curve checks: {len(diag['curve_checks'])}")

if __name__ == "__main__":
    main()
