#!/usr/bin/env python3
"""Rebuild the fixture's ESPN comparison section from the fresh DDF two-tier legs.

Pipeline stage: DDF leg -> ESPN section. The DDF two-tier leg
(pipelines/build_ddf_two_tier_leg.py) is the pipeline's authoritative
bottom-up ESPN valuation (ESPN-pure, never blended). This script projects
it into the comparison fixture's ``sources.espn`` section shape so the
rendered "ESPN adjusted" curve reflects the latest ESPN vintage.

What it does (deterministic, no hand-edits):
- Loads the fresh DDF legs for ppr, half_ppr, standard (09-29 bakes).
- For each scoring, maps DDF 70-scale values onto the fixture's 596-player
  universe via the fixture's own player_keys slugs.
- Players priced by the DDF leg get fresh values DIRECTLY from the leg
  (no rescale to a stale pie). Players outside the leg are EXCLUDED
  (ESPN-purity: no ECR fill — if ESPN has no projection, there is no ESPN value).
- The positional pie (index_total target_total) is measured from the FRESH
  data, not carried forward from a stale canonical pie. This ensures the
  "ESPN adjusted" curve reflects current ESPN projections, not old levels.
- Recomputes index_total factors with the repo's fixed-pie methodology.
- Stamps espn_snapshot with the DDF leg's espn_snapshot_date and
  fetched_at with now. Updates espn_priced_pids from the fresh legs.

Writes only the sources.espn section of
data/fixtures/current/comparison-sources-data.json. All other sections
untouched. Fails closed if any fresh leg is missing or the fixture's
espn section is absent.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
LEG_DIR = REPO / "data" / "ddf-two-tier"

# DDF leg scoring -> fixture combo scoring word.
SCORING_MAP = {"ppr": "full", "half_ppr": "half", "standard": "standard"}
TEAM_COUNTS = [8, 10, 12, 14]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def find_fresh_leg(scoring: str) -> Path:
    """Newest DDF leg for a scoring (by espn_snapshot_date, then generated_at)."""
    cands = []
    for leg_path in LEG_DIR.glob("*/ddf_leg.json"):
        try:
            leg = json.loads(leg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        bake_id = leg.get("bake_id", "")
        if f"-espn-{scoring}-" not in bake_id and not bake_id.endswith(f"-espn-{scoring}"):
            # bake_id looks like ddf-20260929-espn-half_ppr-12t-0p15
            parts = bake_id.split("-espn-")
            if len(parts) != 2 or not parts[1].startswith(scoring + "-"):
                continue
        inputs = leg.get("inputs", {})
        cands.append((
            inputs.get("espn_snapshot_date", ""),
            leg.get("generated_at", ""),
            leg_path,
        ))
    if not cands:
        raise SystemExit(f"No DDF leg found for scoring {scoring!r} under {LEG_DIR}")
    cands.sort()
    return cands[-1][2]


def load_leg_values(leg_path: Path) -> dict[int, float]:
    """player_key (numeric) -> DDF 70-scale value. Joins are by numeric key,
    never by name string (slug variations like cam/cameron break string joins)."""
    leg = json.loads(leg_path.read_text(encoding="utf-8"))
    out = {}
    for row in leg.get("values", []):
        key = row.get("player_key")
        val = row.get("value")
        if key is not None and isinstance(val, (int, float)):
            out[int(key)] = float(val)
    return out


def load_leg_ppg(leg_path: Path) -> dict[int, float]:
    """player_key (numeric) -> per-game ESPN projection (for natives)."""
    leg = json.loads(leg_path.read_text(encoding="utf-8"))
    out = {}
    for row in leg.get("values", []):
        key = row.get("player_key")
        ppg = row.get("ppg")
        if key is not None and isinstance(ppg, (int, float)):
            out[int(key)] = float(ppg)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--players", type=Path, default=PLAYERS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write the fixture.")
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    players = json.loads(args.players.read_text(encoding="utf-8"))

    espn_section = fixture.get("sources", {}).get("espn")
    if espn_section is None:
        raise SystemExit("Fixture has no sources.espn section; refusing to create one.")

    player_keys = fixture.get("player_keys", {})  # slug -> player_key
    key_to_slug = {}
    for slug, key in player_keys.items():
        # First slug wins on duplicate keys; keys are unique per player.
        key_to_slug.setdefault(int(key), slug)
    key_to_pos = {p["player_key"]: p["pos"] for p in players.get("players", [])
                  if p.get("player_key") is not None and p.get("pos")}
    slug_to_pos = {}
    for slug, key in player_keys.items():
        pos = key_to_pos.get(key)
        if pos:
            slug_to_pos[slug] = pos

    # Load fresh legs.
    legs = {}
    leg_ppgs = {}
    vintages = set()
    for scoring in SCORING_MAP:
        leg_path = find_fresh_leg(scoring)
        leg = json.loads(leg_path.read_text(encoding="utf-8"))
        legs[scoring] = load_leg_values(leg_path)
        leg_ppgs[scoring] = load_leg_ppg(leg_path)
        vintages.add(leg.get("inputs", {}).get("espn_snapshot_date"))
        print(f"  {scoring}: {leg.get('bake_id')} ({len(legs[scoring])} values)")
    if len(vintages) != 1:
        raise SystemExit(f"Leg vintages disagree: {sorted(vintages)}; refusing to mix.")
    vintage = vintages.pop()
    print(f"  vintage: {vintage}")

    new_section = copy.deepcopy(espn_section)
    new_priced = set()
    for scoring, combo_word in SCORING_MAP.items():
        ddf_vals = legs[scoring]
        for teams in TEAM_COUNTS:
            combo_name = f"{combo_word}_{teams}"
            combo = new_section["combos"].get(combo_name)
            if combo is None:
                raise SystemExit(f"Fixture espn section missing combo {combo_name!r}")

            # Use fresh DDF values directly (NO rescale to stale pie).
            # The DDF leg is the authoritative bottom-up ESPN valuation;
            # its values reflect the current ESPN vintage. Rescaling to an
            # old "canonical pie" would pin the level to stale data.
            # ESPN-PURITY: Start empty, only DDF-leg players get values.
            # Players without ESPN projections are excluded (no ECR fill).
            # IDENTITY: join leg -> fixture by numeric player_key, never by
            # name slug (cam/cameron, etienne/etienne jr variations break
            # string joins and silently drop players).
            fresh_vals = {}
            fresh_native = {}
            ddf_ppg = leg_ppgs[scoring]
            for pkey, dval in ddf_vals.items():
                slug = key_to_slug.get(pkey)
                if slug is None:
                    continue  # DDF player not in fixture player_keys; skip (fail-closed)
                # Use the fresh DDF value directly, no stale-pie rescale.
                fresh_vals[slug] = round(dval, 1)
                new_priced.add(slug)
                # Natives are per-game ESPN projections; refresh from the leg's ppg.
                if pkey in ddf_ppg:
                    fresh_native[slug] = round(ddf_ppg[pkey], 2)
            combo["values"] = fresh_vals
            combo["native"] = fresh_native
            combo["n"] = len(fresh_vals)

            # Recompute fixed-pie index_total per position from FRESH data.
            # The target_total is the fresh pie (sum of fresh values), not a
            # stale canonical pie carried forward. This ensures the rendered
            # curve reflects current ESPN projections.
            index_total = {}
            for pos in ("QB", "RB", "WR", "TE"):
                pos_slugs = [s for s in fresh_vals if slug_to_pos.get(s) == pos]
                pre_total = round(sum(fresh_vals[s] for s in pos_slugs), 1)
                # Target: the FRESH pie total (measured from current data).
                target = pre_total
                factor = 1.0  # No rescale; values are already on the fresh pie.
                index_total[pos] = {
                    "target_total": target,
                    "pre_total": pre_total,
                    "factor": round(factor, 6),
                    "n_priced": len(pos_slugs),
                }
            combo["index_total"] = index_total

    new_section["espn_snapshot"] = vintage
    new_section["espn_status"] = {
        "stale": False,
        "vintage": vintage,
        "reason": (
            "ESPN's fantasy projections (Mike Clay model per ESPN) refit "
            f"through the DDF two-tier leg at vintage {vintage}."
        ),
    }
    new_section["fetched_at"] = utc_now()
    new_section["espn_priced_pids"] = sorted(new_priced)
    new_section["provenance_note"] = (
        f"ESPN's per-game numbers where they exist ({len(new_priced)} "
        f"players with ESPN season projections, via ESPN (Mike Clay model)). "
        "ESPN-pure: no ECR fill — players without ESPN projections are excluded. "
        "Valued through the DDF two-tier leg (ESPN-pure). "
        "Same valuation math as our column, no Monday adjustments."
    )
    new_section["rails"] = (
        "pipelines/build_espn_section_from_ddf_leg.py (DDF two-tier leg, "
        "fresh values direct, pie measured from current data)"
    )

    if args.dry_run:
        print("dry-run: not writing")
        return 0

    fixture["sources"]["espn"] = new_section
    args.fixture.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote espn section ({len(new_priced)} ESPN-priced players, "
          f"vintage {vintage}) -> {args.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
