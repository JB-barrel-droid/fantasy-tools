#!/usr/bin/env python3
"""Build the CBS-ROS (rest-of-season projections) section of the fixture.

CBS-ROS analog of pipelines/build_espn_section_from_ddf_leg.py. Takes the
freshest CBS ROS DDF leg (data/ddf-two-tier/*-cbsros-*/ddf_leg_cbsros.json)
and writes it into fixture sources.cbsros as {scoring}_{teams} combos:

    standard_8/10/12/14, half_8/10/12/14, full_8/10/12/14

Each combo carries: values (norm-name -> rounded indexed value),
native (norm-name -> per-game projection), n, index_total.

CBS-ROS-purity (mirrors the ESPN rule): everywhere the pipeline labels data
as CBS ROS, the numbers come from CBS's rest-of-season projections only,
never blended from experts. Players without CBS ROS projections are
excluded, not ECR-filled.

No `_adjusted` variant is built for CBS ROS: the adjusted family carries
bias-correction cells fitted against actuals from a prior season, and no
CBS-ROS cells have been fitted (documented, not silently omitted).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEG_DIR = ROOT / "data" / "ddf-two-tier"
LEG_FILENAME = "ddf_leg_cbsros.json"
LEG_BAKE_MARK = "-cbsros-"
SOURCE_KEY = "cbsros"
SOURCE_URL = "https://www.cbssports.com/fantasy/football/stats/QB/2026/restofseason/projections/nonppr/"
COMBO_KEYS = [f"{s}_{t}" for s in ("full", "half", "standard") for t in (8, 10, 12, 14)]
SCORING_LEG = {"full": "ppr", "half": "half_ppr", "standard": "standard"}
# Bench share from shared config (config/roster.json) — never hardcode.
def _load_bench_share():
    import json
    cfg = Path(__file__).resolve().parent.parent / "config" / "roster.json"
    try:
        return json.load(open(cfg))["bench_share"]
    except (OSError, json.JSONDecodeError, KeyError):
        return 0.15
DEFAULT_BENCH_SHARE = _load_bench_share()


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_fixture(path: Path, fixture: dict) -> None:
    path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def find_fresh_leg(scoring: str, teams: int) -> Path | None:
    """Freshest CBS-ROS leg for this scoring/teams pair.

    Deliberately globs ddf_leg_cbsros.json (never */ddf_leg.json): the ESPN
    leg filename is shared by several ESPN-path tools.
    """
    hits = []
    for leg_path in LEG_DIR.glob(f"*/{LEG_FILENAME}"):
        try:
            doc = json.loads(leg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        bake_id = doc.get("bake_id", "")
        if LEG_BAKE_MARK not in bake_id:
            continue
        inputs = doc.get("inputs", {})
        if inputs.get("scoring") == scoring and inputs.get("teams") == teams:
            hits.append((inputs.get("cbsros_snapshot_date", ""), doc.get("generated_at", ""), leg_path))
    if not hits:
        return None
    hits.sort(reverse=True)
    return hits[0][2]


def load_slug_to_pos(fixture: dict) -> dict[str, str]:
    """slug -> position via numeric player_key (never by name string)."""
    players_path = ROOT / "data" / "fixtures" / "current" / "players.json"
    players = json.loads(players_path.read_text(encoding="utf-8")).get("players", [])
    key_to_pos = {p["player_key"]: p["pos"] for p in players
                  if p.get("player_key") is not None and p.get("pos")}
    player_keys = fixture.get("player_keys") or {}
    return {slug: key_to_pos[key] for slug, key in player_keys.items()
            if key in key_to_pos}


def section_from_leg(fixture: dict, source_url: str, combo_keys: list[str]) -> dict:
    slug_to_pos = load_slug_to_pos(fixture)
    values_by_combo = {}
    vintage = None
    for combo in combo_keys:
        scoring_prefix, _, teams_s = combo.rpartition("_")
        scoring = SCORING_LEG[scoring_prefix]
        teams = int(teams_s)
        leg_path = find_fresh_leg(scoring, teams)
        if leg_path is None:
            raise SystemExit(f"Fail closed: no CBS ROS leg for scoring={scoring} teams={teams}; "
                             f"run pipelines/build_cbsros_ddf_leg.py first.")
        cbs_leg = json.loads(leg_path.read_text(encoding="utf-8"))
        values = {v["player_norm"]: round(v["value"], 1) for v in cbs_leg["values"]}
        native = {v["player_norm"]: round(v["ppg"], 3) for v in cbs_leg["values"]}
        # Fixed-pie index_total per position, measured from the FRESH data
        # (same shape as the ESPN section; factor 1.0 = no stale-pie rescale).
        index_total = {}
        for pos in ("QB", "RB", "WR", "TE"):
            pos_slugs = [s for s in values if slug_to_pos.get(s) == pos]
            pre_total = round(sum(values[s] for s in pos_slugs), 1)
            index_total[pos] = {
                "target_total": pre_total,
                "pre_total": pre_total,
                "factor": 1.0,
                "n_priced": len(pos_slugs),
            }
        values_by_combo[combo] = {
            "values": values,
            "native": native,
            "n": len(values),
            "index_total": index_total,
        }
        vintage = vintage or cbs_leg.get("inputs", {}).get("cbsros_snapshot_date")
    return {
        "provenance": "published",   # CBS ROS is source-authored; we only rescore receptions.
        "source_url": source_url,
        # CBS ROS is rest-of-season projections, not a week-designated trade
        # chart. The monitor's C10 rendered-output check allows exactly this
        # label (same as ESPN); a missing label reads as a bad week stamp.
        "week_designated": "rest of season",
        "method": ("CBS rest-of-season projections (nonppr page; half/full PPR "
                   "computed as CBS fpts + 0.5/1.0 per reception, per-game = ROS/gp), "
                   "translated to the 0-70 scale with the DDF two-tier "
                   "value-above-waivers method. CBS projections only; no expert blend."),
        "method_group": "ddf-methodology",
        "combos": values_by_combo,
        "vintage": vintage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path,
                        default=ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json")
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--combo-keys", nargs="+", default=COMBO_KEYS)
    args = parser.parse_args()

    fixture = load_fixture(args.fixture)
    sources = fixture.get("sources", {})
    section = section_from_leg(fixture, args.source_url, list(args.combo_keys))
    sources[SOURCE_KEY] = section
    fixture["sources"] = sources
    # The section exists with fresh legs -> mark live (mirrors the adjusted
    # builder stamping its own flags; base-source flags are fixture-maintained).
    validation = fixture.get("source_validation") or {}
    validation[SOURCE_KEY] = "live"
    fixture["source_validation"] = validation
    save_fixture(args.fixture, fixture)
    n = {c: section["combos"][c]["n"] for c in args.combo_keys}
    print(f"Wrote sources.{SOURCE_KEY} ({len(args.combo_keys)} combos): {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
