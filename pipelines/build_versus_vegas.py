#!/usr/bin/env python3
"""Build an isolated, offline Versus Vegas review page from weekly-inputs v1.

No fetch, identity resolution, pricing, rank conversion, play gate or publication.
The shared validator owns weekly-input validity and content freshness. This
adapter exposes only weekly ECR and PropLine; other legs never supply a fill.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

if __package__:
    from .lib.weekly_inputs_contract import SCORINGS, errors, validate
else:  # Direct CLI execution puts pipelines/ on sys.path.
    from lib.weekly_inputs_contract import SCORINGS, errors, validate

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "versus-vegas"
# The producer uses fantasypros_ecr; the shared contract's older fixtures use
# fantasypros. Both name weekly ECR on the exact ecr_weekly leg, never a fill.
SOURCES = {"ecr": ("experts.ecr_weekly", ("fantasypros_ecr", "fantasypros")),
           "vegas": ("vegas", ("propline",))}


def build_view(doc: dict) -> dict:
    """Preserve source values; subtract only comparable, complete weekly points.

    Difference is descriptive, never a verified play or calibrated signal.
    A partially covered row remains unflagged even for its populated scoring.
    """
    issues = validate(doc)
    if errors(issues):
        raise ValueError("Invalid weekly inputs: " + "; ".join(
            f"{i.path}: {i.code}" for i in errors(issues)))
    legs = {}
    for side, (leg_id, sources) in SOURCES.items():
        meta = doc["legs"].get(leg_id)
        if meta and meta["source"] not in sources:
            raise ValueError(f"{leg_id} must use {' or '.join(sources)}; got {meta['source']}")
        legs[side] = meta

    def value_for(player, side, scoring):
        leg_id, _ = SOURCES[side]
        meta = legs[side]
        cell = player["legs"].get(leg_id)
        value = cell["values"].get(scoring) if cell else None
        reason = None
        if value is None:
            reason = ((cell or {}).get("missing_reason") or {}).get(scoring)
            reason = reason or (meta or {}).get("missing_reason")
            reason = reason or ("Scoring format not supplied" if meta else "Weekly input not supplied")
        return {"value": value, "reason": reason,
                "units": meta["units"] if meta else None,
                "provenance": cell["provenance"] if cell else "missing"}

    rows = []
    for player in doc["players"]:
        row = {key: player[key] for key in ("player_key", "name", "team", "position")}
        row["unresolved_reason"] = player.get("unresolved_reason")
        row["resolved_by"] = player.get("resolved_by")
        row["source_ids"] = player.get("source_ids", {})
        row["scoring"] = {}
        for scoring in SCORINGS:
            cells = {side: value_for(player, side, scoring) for side in SOURCES}
            populated = sum(c["value"] is not None for c in cells.values())
            coverage = ("both" if populated == 2 else "partial" if populated else "missing")
            reasons = []
            if player["player_key"] is None:
                reasons.append("Unresolved identity")
            for side, cell in cells.items():
                meta = legs[side]
                label = "ECR" if side == "ecr" else "PropLine"
                if cell["value"] is None:
                    reasons.append(f"{label}: {cell['reason']}")
                elif cell["provenance"] != "complete":
                    reasons.append(f"{label}: {cell['provenance']} input")
                if meta and meta["availability"] != "unavailable" and meta["freshness"] != "current":
                    reasons.append(f"{label}: {meta['freshness']}")
            if populated == 2 and any(c["units"] != "fantasy_points" for c in cells.values()):
                reasons.append("Ranks and points are shown in source units; no conversion available")
            difference = None
            direction = None
            if not reasons:
                difference = cells["vegas"]["value"] - cells["ecr"]["value"]
                direction = "Vegas higher" if difference > 0 else "ECR higher" if difference < 0 else "Equal"
            row["scoring"][scoring] = {**cells, "coverage": coverage,
                "difference": difference, "direction": direction,
                "reason": "; ".join(reasons) or None}
        rows.append(row)
    return {"schema": "versus-vegas-view", "schema_version": "1.0.0",
            "season": doc["season"], "content_week": doc["content_week"],
            "built_at": doc["built_at"], "producer": doc["producer"],
            "legs": legs, "players": rows,
            "warnings": [asdict(i) for i in issues if i.severity == "warning"],
            "plays": [], "plays_reason": "Verified plays await the shared weekly comparison and play gate."}


def render_html(view: dict) -> str:
    # Input strings cannot break out of the application/json script element.
    payload = json.dumps(view, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    return (ASSETS / "template.html").read_text().replace(
        "/* VERSUS_STYLE */", (ASSETS / "style.css").read_text()).replace(
        "/* VERSUS_SCRIPT */", (ASSETS / "view.js").read_text()).replace(
        "__VERSUS_DATA__", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Stored weekly-inputs JSON; no network reads")
    parser.add_argument("--out", type=Path, required=True, help="Local preview HTML (outside dist)")
    args = parser.parse_args()
    if args.out.resolve().is_relative_to((ROOT / "dist").resolve()):
        parser.error("Use a local preview path outside dist; live publication is not wired")
    if args.out.resolve() == args.input.resolve():
        parser.error("Output must not overwrite the source input")
    try:
        raw = args.input.read_bytes()
        view = build_view(json.loads(raw))
        view["input_sha256"] = hashlib.sha256(raw).hexdigest()
        rendered = render_html(view)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered)
    print(f"Built local Versus Vegas preview: {args.out} ({len(view['players'])} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
