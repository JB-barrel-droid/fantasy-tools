#!/usr/bin/env python3
"""JEG-242: Transform shared-batch70-views-v1 to comparison-sources-data.json format.

The new as-published VORP pipeline (build_imputed_vorps.py + build_reweighted_values.py)
produces shared-batch70-views-v1 artifacts with three views per source:
  - indexed: native publisher values
  - vorp: imputed VORP values
  - adj_values: 0-70 reweighted chart values

The existing chart views (curve-widget.js, comparison-dashboard.js) consume
comparison-sources-data.json with a different structure. This transformer bridges
the two formats for the as-published sources (fantasycalc, usatoday, fantasypros, cbs).

Usage:
    python3 pipelines/transform_batch70_to_comparison.py \
        --batch70 <shared-batch70-views-v1.json> \
        --comparison <comparison-sources-data.json> \
        --out <output.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# As-published sources handled by the new pipeline
AS_PUBLISHED_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "cbs")

# Map pipeline source names to comparison data source keys
# Note: pipeline uses "usat" but comparison uses "usatoday"
SOURCE_MAP = {
    "fantasycalc": "fantasycalc",
    "usat": "usatoday",
    "fantasypros": "fantasypros",
    "cbs": "cbs",
}


def transform(batch70_path: Path, comparison_path: Path, out_path: Path) -> int:
    """Transform batch70 views into comparison format for as-published sources."""
    batch70 = json.loads(batch70_path.read_text())
    comparison = json.loads(comparison_path.read_text())
    
    if batch70.get("schema") != "shared-batch70-views-v1":
        print("ERROR: Expected shared-batch70-views-v1 schema", file=sys.stderr)
        return 1
    
    batch_sources = batch70.get("sources", {})
    updated = 0
    
    for pipe_src, comp_src in SOURCE_MAP.items():
        if pipe_src not in batch_sources:
            print(f"  Skip {pipe_src}: not in batch70 output", file=sys.stderr)
            continue
        if comp_src not in comparison.get("sources", {}):
            print(f"  Skip {comp_src}: not in comparison data", file=sys.stderr)
            continue
        
        views = batch_sources[pipe_src]
        # The "adj_values" are the 0-70 chart values for the Adjusted view
        # The "vorp" are the imputed VORP values for the VORP view
        # The "indexed" are the native values for the Indexed view
        
        # Store the new pipeline output in the source's metadata
        # The views will read these via the existing comparison structure
        src_data = comparison["sources"][comp_src]
        src_data["_jeg242_batch70"] = {
            "schema": "shared-batch70-views-v1",
            "batch_scale": batch70.get("batch_scale"),
            "views": {
                "indexed": views.get("indexed", {}),
                "vorp": views.get("vorp", {}),
                "adj_values": views.get("adj_values", {}),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        updated += 1
        print(f"  Updated {comp_src} with batch70 views", file=sys.stderr)
    
    # Update metadata
    comparison["_jeg242_transform"] = {
        "transformed_at": datetime.now(timezone.utc).isoformat(),
        "batch70_schema": batch70.get("schema"),
        "sources_updated": updated,
    }
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {out_path} ({updated} sources updated)", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch70", type=Path, required=True,
                    help="shared-batch70-views-v1 JSON from build_reweighted_values.py")
    ap.add_argument("--comparison", type=Path, required=True,
                    help="comparison-sources-data.json to update")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output path")
    args = ap.parse_args(argv)
    return transform(args.batch70, args.comparison, args.out)


if __name__ == "__main__":
    sys.exit(main())
