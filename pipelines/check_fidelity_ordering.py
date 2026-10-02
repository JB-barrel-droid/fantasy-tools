#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any

def load_fixture_data(fixture_path):
    with open(fixture_path, "r") as f:
        return json.load(f)

def get_native_and_reindexed(data, source):
    results = []
    if source not in data.get("sources", {}):
        return results
    source_data = data["sources"][source]
    combos = source_data.get("combos", {})
    for combo_name, combo_data in combos.items():
        fit = combo_data.get("fit", {})
        native_values = None
        reindexed_values = None
        if "native" in fit:
            native_values = fit["native"]
        elif "flex_aware_pie" in fit:
            fap = fit["flex_aware_pie"]
            if "native" in fap:
                native_values = fap["native"]
            if "reindexed" in fap:
                reindexed_values = fap["reindexed"]
        if "reindexed" in fit:
            reindexed_values = fit["reindexed"]
        if native_values and reindexed_values:
            results.append({"combo": combo_name, "native": native_values, "reindexed": reindexed_values})
    return results

def find_ordering_flips(native_values, reindexed_values):
    flips = []
    players = set(native_values.keys()) & set(reindexed_values.keys())
    native_sorted = sorted(players, key=lambda p: native_values[p], reverse=True)
    reindexed_sorted = sorted(players, key=lambda p: reindexed_values[p], reverse=True)
    native_rank = {player: rank for rank, player in enumerate(native_sorted)}
    reindexed_rank = {player: rank for rank, player in enumerate(reindexed_sorted)}
    for i, player_a in enumerate(native_sorted):
        for player_b in native_sorted[i+1:]:
            if reindexed_rank[player_a] > reindexed_rank[player_b]:
                flips.append({"player_a": player_a, "player_b": player_b, "native_a": native_values[player_a], "native_b": native_values[player_b], "reindexed_a": reindexed_values[player_a], "reindexed_b": reindexed_values[player_b]})
    return flips

def check_source_flips(data, source):
    result = {"source": source, "combos": []}
    combos_data = get_native_and_reindexed(data, source)
    for combo in combos_data:
        flips = find_ordering_flips(combo["native"], combo["reindexed"])
        combo_result = {"combo": combo["combo"], "n_players": len(combo["native"]), "flips_found": len(flips), "flips": flips}
        result["combos"].append(combo_result)
    return result

def main():
    fixture_path = Path(__file__).parent.parent / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    if len(sys.argv) > 1:
        fixture_path = Path(sys.argv[1])
    if not fixture_path.exists():
        print(f"Error: Fixture not found: {fixture_path}", file=sys.stderr)
        sys.exit(1)
    data = load_fixture_data(fixture_path)
    sources_to_check = ["fantasycalc", "usatoday", "fantasypros", "cbs"]
    all_results = {"fixture": str(fixture_path), "sources": []}
    total_flips = 0
    for source in sources_to_check:
        source_result = check_source_flips(data, source)
        source_flips = sum(c["flips_found"] for c in source_result["combos"])
        source_result["total_flips"] = source_flips
        total_flips += source_flips
        all_results["sources"].append(source_result)
    all_results["total_flips"] = total_flips
    print(json.dumps(all_results, indent=2))
    sys.exit(1 if total_flips > 0 else 0)

if __name__ == "__main__":
    main()

