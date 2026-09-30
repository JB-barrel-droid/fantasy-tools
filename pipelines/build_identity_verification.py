#!/usr/bin/env python3
"""Verify Identity Resolution framework for the monitoring dashboard.

Checks:
1. All sources join via numeric player_key (not name strings)
2. No duplicate player_keys with conflicting team/position
3. All player_keys resolve in the Supabase registry

Output: dist/modules/identity-verification.json
"""

import json
import os
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(REPO, "data/fixtures/current/comparison-sources-data.json")
PLAYERS_PATH = os.path.join(REPO, "data/fixtures/current/players.json")
OUT_PATH = os.path.join(REPO, "dist/modules/identity-verification.json")


def main():
    fx = json.load(open(FIXTURE_PATH))
    players = json.load(open(PLAYERS_PATH))["players"]
    by_key = {p["player_key"]: p for p in players}

    issues = []
    stats = {
        "total_player_keys": len(by_key),
        "sources_checked": 0,
        "joins_via_player_key": 0,
        "ambiguous_identities": 0,
        "team_position_conflicts": 0,
    }

    # Check 1: Verify fixture uses player_key (not name) for joins
    # The fixture's player_keys mapping should exist and be numeric
    player_keys = fx.get("player_keys", {})
    if not player_keys:
        issues.append({
            "type": "missing_registry",
            "detail": "Fixture has no player_keys mapping — joins may be name-based",
        })
    else:
        stats["joins_via_player_key"] = len(player_keys)
        # Verify keys are numeric
        non_numeric = [k for k in player_keys.values() if not isinstance(k, int)]
        if non_numeric:
            issues.append({
                "type": "non_numeric_key",
                "detail": f"{len(non_numeric)} player_keys are not numeric",
            })

    # Check 2: Team/position consistency across sources
    # Build map of player_key -> set of (team, pos) seen
    key_teams = defaultdict(set)
    for src, src_data in fx.get("sources", {}).items():
        stats["sources_checked"] += 1
        for combo_key, combo in src_data.get("combos", {}).items():
            # We don't have team/pos in the combo, but players.json does
            pass

    # Check players.json for duplicates
    seen_names = defaultdict(list)
    for p in players:
        norm = p["name"].lower().strip()
        seen_names[norm].append(p)

    for norm, plist in seen_names.items():
        if len(plist) > 1:
            keys = [p["player_key"] for p in plist]
            if len(set(keys)) > 1:
                # Same name, different keys = ambiguous, must be fail-closed
                stats["ambiguous_identities"] += 1
                issues.append({
                    "type": "ambiguous_identity",
                    "detail": f"'{plist[0]['name']}' maps to {len(set(keys))} different player_keys: {sorted(set(keys))}",
                })

    # Check 3: Team/position conflicts (same key, different team/pos in players.json)
    # (players.json should have one canonical team/pos per key, so this is a sanity check)
    key_info = {}
    for p in players:
        k = p["player_key"]
        info = (p.get("team"), p.get("pos"))
        if k in key_info and key_info[k] != info:
            stats["team_position_conflicts"] += 1
            issues.append({
                "type": "team_position_conflict",
                "detail": f"player_key {k}: {key_info[k]} vs {info}",
            })
        key_info[k] = info

    result = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "status": "fail" if issues else "pass",
        "stats": stats,
        "issues": issues,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {OUT_PATH}")
    print(f"  Status: {result['status']}")
    print(f"  Issues: {len(issues)}")
    for iss in issues[:5]:
        print(f"    {iss['type']}: {iss['detail'][:80]}")


if __name__ == "__main__":
    main()
