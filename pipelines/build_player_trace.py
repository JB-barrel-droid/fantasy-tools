#!/usr/bin/env python3
"""Build player trace data for the monitoring dashboard.

For each player, traces their value through the pipeline stages:
  snapshot -> section -> reindexed -> fixture

This powers the "Player Trace" dashboard section, letting Jeremy see
exactly how a number flows through the pipeline and where it changes.

Output: dist/modules/player-trace.json
"""

import json
import glob
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

# Sources to trace (the main ones, not _adjusted)
SOURCES = ["espn", "fantasycalc", "fantasypros", "usatoday", "cbs", "cbsros"]


def norm_name(n):
    """Normalize a name for matching: lowercase, underscores/hyphens to spaces, strip."""
    if not isinstance(n, str):
        return str(n)
    return n.lower().replace("_", " ").replace("-", " ").strip()


def load_fixture():
    """Load the current fixture."""
    path = REPO / "data/fixtures/current/comparison-sources-data.json"
    return json.load(open(path))

def find_latest_snapshot(source):
    """Find the latest snapshot.json for a source."""
    pattern = str(REPO / "data/raw/sources" / source / "*" / "snapshot.json")
    files = sorted(glob.glob(pattern))
    # Skip archived/corrupt
    files = [f for f in files if "_archived" not in f and "corrupt" not in f]
    return files[-1] if files else None

def find_latest_section(source):
    """Find the latest section file for a source."""
    pattern = str(REPO / "output/comparison-candidates" / source / "*" / "*-section.json")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None

def find_latest_reindexed(source):
    """Find the latest reindexed file for a source."""
    pattern = str(REPO / "output/comparison-reference" / f"{source}-*-reindexed.json")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None

def get_player_name(player_key, fixture):
    """Get player name from fixture by player_key."""
    # The fixture has player_keys mapping, but we need a reverse lookup
    # For now, use the canonical name from any source
    for src, sdata in fixture.get("sources", {}).items():
        for combo_key, combo in sdata.get("combos", {}).items():
            pk = combo.get("player_keys", {})
            # pk maps sid -> player_key, we need reverse
            for sid, pkey in pk.items():
                if pkey == player_key:
                    # Try to get name from sid (often "first last" format)
                    return sid.replace("_", " ").title()
    return f"Player {player_key}"

def build_trace():
    """Build the trace data."""
    fixture = load_fixture()
    
    # Collect all player_keys from the fixture
    all_players = {}
    for src in SOURCES:
        if src not in fixture.get("sources", {}):
            continue
        sdata = fixture["sources"][src]
        for combo_key, combo in sdata.get("combos", {}).items():
            pk = combo.get("player_keys", {})
            for sid, pkey in pk.items():
                if pkey not in all_players:
                    all_players[pkey] = {
                        "player_key": pkey,
                        "name": sid.replace("_", " ").title() if isinstance(sid, str) else str(sid),
                        "sources": {}
                    }
    
    # For each source, trace each player through stages
    for src in SOURCES:
        # Load snapshot
        snap_path = find_latest_snapshot(src)
        snap_data = {}
        if snap_path:
            try:
                snap = json.load(open(snap_path))
                rows = snap.get("rows", [])
                for row in rows:
                    # Match by player_key if available, else by name
                    pkey = row.get("player_key")
                    if pkey:
                        snap_data[pkey] = {
                            "native_value": row.get("native_value"),
                            "value": row.get("value"),
                        }
            except Exception as e:
                print(f"Warning: could not load snapshot for {src}: {e}")
        
        # Load section
        sec_path = find_latest_section(src)
        sec_data = {}
        if sec_path:
            try:
                sec = json.load(open(sec_path))
                for combo_key, combo in sec.get("combos", {}).items():
                    native = combo.get("native", {})
                    pk = combo.get("player_keys", {})
                    for sid, pkey in pk.items():
                        if pkey not in sec_data:
                            sec_data[pkey] = {}
                        sec_data[pkey][combo_key] = {
                            "native": native.get(sid),
                        }
            except Exception as e:
                print(f"Warning: could not load section for {src}: {e}")
        
        # Load reindexed
        reidx_path = find_latest_reindexed(src)
        reidx_data = {}
        if reidx_path:
            try:
                reidx = json.load(open(reidx_path))
                for combo_key, combo in reidx.get("combos", {}).items():
                    reindexed = combo.get("reindexed", {})
                    native = combo.get("native", {})
                    pk = combo.get("player_keys", {})
                    for sid, pkey in pk.items():
                        if pkey not in reidx_data:
                            reidx_data[pkey] = {}
                        reidx_data[pkey][combo_key] = {
                            "reindexed": reindexed.get(sid),
                            "native": native.get(sid),
                        }
            except Exception as e:
                print(f"Warning: could not load reindexed for {src}: {e}")
        
        # Load fixture values
        # Note: fixture combos store values under 'reindexed' (when present) or 'values',
        # keyed by display name (not sid). Match by normalized name.
        if src in fixture.get("sources", {}):
            sdata = fixture["sources"][src]
            # Build name index for this source from player_keys across combos
            name_to_pkey = {}
            for ckey, cdata in sdata.get("combos", {}).items():
                for sid, pkey in cdata.get("player_keys", {}).items():
                    name_to_pkey[norm_name(sid)] = pkey
            # Fall back to global player names
            for pkey, pdata in all_players.items():
                name_to_pkey.setdefault(norm_name(pdata["name"]), pkey)

            for combo_key, combo in sdata.get("combos", {}).items():
                value_dict = combo.get("reindexed") or combo.get("values") or {}
                native_dict = combo.get("native") or {}
                pk = combo.get("player_keys", {})
                rev_pk = {v: k for k, v in pk.items()}
                for vname, vval in value_dict.items():
                    # Resolve player_key: try player_keys first, then normalized name
                    pkey = None
                    sid = None
                    # player_keys maps sid -> pkey; vname may be the sid
                    if vname in pk:
                        pkey = pk[vname]
                        sid = vname
                    else:
                        pkey = name_to_pkey.get(norm_name(vname))
                        sid = vname
                    if pkey is None or pkey not in all_players:
                        continue
                    pdata = all_players[pkey]
                    if src not in pdata["sources"]:
                        pdata["sources"][src] = {"combos": {}}
                    if combo_key not in pdata["sources"][src]["combos"]:
                        pdata["sources"][src]["combos"][combo_key] = {}
                    pdata["sources"][src]["combos"][combo_key]["fixture_reindexed"] = vval
                    nval = native_dict.get(sid)
                    if nval is not None:
                        pdata["sources"][src]["combos"][combo_key]["fixture_native"] = nval
        
        # Merge stage data into player records
        for pkey, pdata in all_players.items():
            if src not in pdata["sources"]:
                pdata["sources"][src] = {"combos": {}}
            
            # Add snapshot data
            if pkey in snap_data:
                pdata["sources"][src]["snapshot"] = snap_data[pkey]
            
            # Add section data (use first combo for simplicity, or merge)
            if pkey in sec_data:
                # Take the first combo's native
                for combo_key, cdata in sec_data[pkey].items():
                    if combo_key not in pdata["sources"][src]["combos"]:
                        pdata["sources"][src]["combos"][combo_key] = {}
                    pdata["sources"][src]["combos"][combo_key]["section_native"] = cdata["native"]
                    break
            
            # Add reindexed data
            if pkey in reidx_data:
                for combo_key, cdata in reidx_data[pkey].items():
                    if combo_key not in pdata["sources"][src]["combos"]:
                        pdata["sources"][src]["combos"][combo_key] = {}
                    pdata["sources"][src]["combos"][combo_key]["reindexed_native"] = cdata["native"]
                    pdata["sources"][src]["combos"][combo_key]["reindexed_value"] = cdata["reindexed"]
                    break
    
    # Convert to list, sort by name
    players = sorted(all_players.values(), key=lambda x: x["name"])
    
    output = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "sources": SOURCES,
        "stages": ["snapshot", "section", "reindexed", "fixture"],
        "stage_logic": {
            "snapshot": "Raw values from the source's published page. native_value = genuine published number; value = may be transformed.",
            "section": "Pipeline's working copy. Uses native_value (not value) for as-published sources.",
            "reindexed": "Values mapped to 0-70 scale via isotonic regression against ESPN anchor. Preserves rank order.",
            "fixture": "Final published values. What the chart displays."
        },
        "players": players,
    }
    
    return output

def main():
    trace = build_trace()
    out_path = REPO / "dist/modules/player-trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(trace, open(out_path, "w"), indent=2)
    print(f"Wrote {out_path} with {len(trace['players'])} players")

if __name__ == "__main__":
    main()
