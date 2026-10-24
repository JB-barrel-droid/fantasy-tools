#!/usr/bin/env python3
"""Write the frozen Health check fixtures (JEG-1011) to tests/fixtures/audit/.

Source: dumps from tools/audit_health_dump.py (reduced getInspection() shapes). Frozen means
the tests read these files and nobody edits them without a logged justification
(docs/health-check-thresholds.md, docs/claude-log). Re-running this script after the engine
changes would replace them, so it refuses to overwrite an existing fixture.

  healthy_week7.json            week 7, PPR, 12 teams, 7 sources, no perturbation
  perturbed_espn_starter.json   healthy, with every ESPN starter's Adjusted value x 1.2
  missing_cbs.json              healthy with CBS Sports removed (6 sources)
  extreme_8team_halfppr.json    week 7, half PPR, 8 teams (the engine's smallest league, widest roster share; the
                                spec's 4-team case is not a setting the engine accepts: teams are 8, 10, 12 or 14)
  history_week5.json            week 5, PPR, 12 teams

Usage: python3 tools/audit_health_fixtures.py --dump DIR   (DIR has w7_ppr_12, w5_ppr_12 and w7_half_ppr_8)
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "audit"


def write(name: str, doc: dict):
    path = OUT / name
    if path.exists():
        print(f"skip {name}: frozen fixture already exists", file=sys.stderr)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    print("wrote", path.relative_to(ROOT), path.stat().st_size, "bytes", file=sys.stderr)


def perturb_starters(doc: dict, src: str, factor: float) -> dict:
    out = copy.deepcopy(doc)
    for player in out["inspection"]["players"][src].values():
        if player["role"] == "starter":
            player["adjusted"] *= factor
    out["perturbation"] = {"source": src, "starters_x": factor}
    return out


def drop_source(doc: dict, src: str) -> dict:
    out = copy.deepcopy(doc)
    insp = out["inspection"]
    insp["valuePipeline"]["sources"].pop(src, None)
    insp["valuePipeline"]["included"] = [k for k in insp["valuePipeline"]["included"] if k != src]
    insp["players"].pop(src, None)
    for row in insp["rows"].values():
        row["indexed"].pop(src, None)
    out["perturbation"] = {"removed": src}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", required=True, help="dir with w7_ppr_12.json and w5_ppr_12.json")
    args = ap.parse_args(argv)
    dump = Path(args.dump)
    healthy = json.loads((dump / "w7_ppr_12.json").read_text())
    healthy.pop("liveMatch", None)
    write("healthy_week7.json", healthy)
    write("perturbed_espn_starter.json", perturb_starters(healthy, "espn", 1.2))
    write("missing_cbs.json", drop_source(healthy, "cbs"))
    week5 = json.loads((dump / "w5_ppr_12.json").read_text())
    week5.pop("liveMatch", None)
    write("history_week5.json", week5)
    small = json.loads((dump / "w7_half_ppr_8.json").read_text())
    small.pop("liveMatch", None)
    write("extreme_8team_halfppr.json", small)


if __name__ == "__main__":
    main()
