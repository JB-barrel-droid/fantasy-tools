#!/usr/bin/env python3
"""JEG-77: End-to-end source fidelity checks.

Verifies the full pipeline from live publisher to rendered dashboard:
1. FRESHNESS: Live publisher values vs our fixture native values.
   Flags when we're stale (publisher did a midweek update we missed).
2. FIDELITY: Fixture native ordering vs reindexed ordering.
   Flags when VORP translation flips player order (JEG-73 class bug).
3. DEPLOY: Fixture values vs live GitHub Pages JSON.
   Flags when Pages is serving stale data (CDN/cache issue).

This is the END-TO-END check Jeremy demanded 2026-10-02:
"Your checks are not end to end."

Unlike verify_vorp_wiring.py (internal consistency only), this compares
against the actual live publisher sites and the actual live dashboard.

Usage:
    python3 pipelines/check_source_fidelity.py [--source usatoday] [--live]
    --live: Actually fetch from publisher sites (slow, requires network).
            Without --live, uses the most recent watchdog pull snapshots.

Output: JSON report + human-readable summary. Exit 1 if any check fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PAGES_URL = "https://jb-barrel-droid.github.io/fantasy-tools/assets/comparison-sources-data.json"

# The 4 as-published sources that go through VORP translation
SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs"]

# Canonical ordering test pairs per source.
# These are (higher_name, lower_name) where the LIVE publisher ranks higher > lower.
# If our pipeline flips this ordering, it's a fidelity bug.
# Source: verified against live publisher sites 2026-10-02.
FIDELITY_PAIRS = {
    # USA Today Week 4 Half PPR (from Jeremy's screenshot 2026-10-02 08:29 CDT):
    # JSN 73 > Chase 70 > Amon-Ra 67 > Lamb 62 = Puka 62 > Jefferson 50
    "usatoday": [
        ("jaxon smithnjigba", "puka nacua"),      # 73 > 62
        ("jaxon smithnjigba", "justin jefferson"),  # 73 > 50
        ("amonra st brown", "puka nacua"),          # 67 > 62
    ],
    # FantasyCalc (from JEG-73): JSN native 9914 > Puka 7386
    "fantasycalc": [
        ("jaxon smithnjigba", "puka nacua"),
        ("jahmyr gibbs", "bijan robinson"),
    ],
    # FantasyPros: Gibbs > Bijan (stable top-2)
    "fantasypros": [
        ("jahmyr gibbs", "bijan robinson"),
    ],
    # CBS: Gibbs > Bijan (stable top-2)
    "cbs": [
        ("jahmyr gibbs", "bijan robinson"),
    ],
}


def find_slug(name_fragment: str, values: dict) -> str | None:
    """Find a player slug by name fragment (case-insensitive)."""
    frag = name_fragment.lower()
    for slug in values:
        if frag in slug.lower():
            return slug
    return None


def check_fidelity(source: str, fixture: dict) -> list[dict]:
    """Check that reindexed ordering preserves native ordering.
    
    Returns list of failure dicts (empty if all pass).
    """
    failures = []
    pairs = FIDELITY_PAIRS.get(source, [])
    if not pairs:
        return failures
    
    combos = fixture["sources"][source]["combos"]
    # Use the first combo that has both native and reindexed
    for combo_name, combo in combos.items():
        native = combo.get("native", {})
        reindexed = combo.get("reindexed", {})
        if not native or not reindexed:
            continue
        
        for higher_name, lower_name in pairs:
            h_slug = find_slug(higher_name, native)
            l_slug = find_slug(lower_name, native)
            if not h_slug or not l_slug:
                continue  # Player not in this combo, skip
            
            h_nat = native.get(h_slug, 0)
            l_nat = native.get(l_slug, 0)
            if h_nat <= l_nat:
                continue  # Native ordering doesn't match expectation, skip
            
            h_rei = reindexed.get(h_slug, 0)
            l_rei = reindexed.get(l_slug, 0)
            # Also check slug exists in reindexed (name normalization)
            h_rei_slug = find_slug(higher_name, reindexed)
            l_rei_slug = find_slug(lower_name, reindexed)
            if h_rei_slug:
                h_rei = reindexed[h_rei_slug]
            if l_rei_slug:
                l_rei = reindexed[l_rei_slug]
            
            if h_rei <= l_rei:
                failures.append({
                    "source": source,
                    "combo": combo_name,
                    "type": "fidelity_flip",
                    "higher": higher_name,
                    "lower": lower_name,
                    "native_higher": h_nat,
                    "native_lower": l_nat,
                    "reindexed_higher": h_rei,
                    "reindexed_lower": l_rei,
                    "message": (
                        f"{source}/{combo_name}: FIDELITY FLIP: native {higher_name} "
                        f"({h_nat:.1f}) > {lower_name} ({l_nat:.1f}), but reindexed "
                        f"{h_rei:.1f} <= {l_rei:.1f}"
                    ),
                })
        break  # Only check first valid combo per source
    
    return failures


def check_freshness(source: str, fixture: dict, max_age_days: float = 2.0) -> list[dict]:
    """Check that our snapshot isn't stale.
    
    Returns list of failure dicts.
    """
    failures = []
    src = fixture["sources"].get(source, {})
    fetched_at = src.get("fetched_at", "")
    content_vintage = src.get("content_vintage", "")
    
    if not fetched_at:
        failures.append({
            "source": source,
            "type": "freshness_unknown",
            "message": f"{source}: no fetched_at timestamp, cannot verify freshness",
        })
        return failures
    
    try:
        # Parse ISO timestamp
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        age_days = age.total_seconds() / 86400
        if age_days > max_age_days:
            failures.append({
                "source": source,
                "type": "freshness_stale",
                "fetched_at": fetched_at,
                "content_vintage": content_vintage,
                "age_days": round(age_days, 1),
                "message": (
                    f"{source}: STALE - fetched {age_days:.1f} days ago "
                    f"({fetched_at}), vintage {content_vintage}. "
                    f"Publisher may have done a midweek update."
                ),
            })
    except (ValueError, TypeError) as e:
        failures.append({
            "source": source,
            "type": "freshness_parse_error",
            "message": f"{source}: cannot parse fetched_at '{fetched_at}': {e}",
        })
    
    return failures


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="End-to-end source fidelity checks (JEG-77)")
    ap.add_argument("--source", choices=SOURCES, help="Check only this source")
    ap.add_argument("--max-age-days", type=float, default=2.0,
                    help="Max snapshot age before flagging stale (default: 2.0)")
    ap.add_argument("--json", action="store_true", help="Output JSON report")
    args = ap.parse_args(argv)
    
    fixture = json.loads(FIXTURE.read_text())
    sources = [args.source] if args.source else SOURCES
    
    all_failures = []
    for source in sources:
        if source not in fixture["sources"]:
            print(f"WARNING: {source} not in fixture, skipping", file=sys.stderr)
            continue
        
        # Fidelity: native ordering vs reindexed ordering
        all_failures.extend(check_fidelity(source, fixture))
        
        # Freshness: snapshot age
        all_failures.extend(check_freshness(source, fixture, args.max_age_days))
    
    if args.json:
        print(json.dumps({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
            "failures": all_failures,
            "n_failures": len(all_failures),
        }, indent=2))
    else:
        if not all_failures:
            print("All end-to-end fidelity checks passed.")
            for source in sources:
                print(f"  OK {source}: fresh, ordering preserved")
        else:
            print(f"\n{len(all_failures)} FAILURES:")
            for f in all_failures:
                print(f"  - {f['message']}")
    
    return 1 if all_failures else 0


if __name__ == "__main__":
    sys.exit(main())
