#!/usr/bin/env python3
"""JEG-242: Orchestrate the as-published VORP pipeline (imputed -> reweighted).

Real orchestration over the reviewed producers -- not a scaffold. Resolves
Jeremy's pinned blend reference (data/reference/jeg242-blend-controls-v1.json)
into the explicit inputs the reviewed refresh path requires, then delegates to
pipelines/refresh_vorp_views.py, which runs:

  build_imputed_vorps.py -> build_reweighted_values.py --controls <extracted>
      -> review_batch70_views.py (fail-closed gate) -> versioned run manifest

CANDIDATE-ONLY: artifacts land under --out-dir. Nothing is written to
Supabase, nothing is promoted, nothing touches the live views. Promotion
consumes only reviewed candidates through a separate reviewed step.

Fail-closed:
  - the reference's ddf_groups_sha256 pin is verified against the actual leg
    bytes before anything runs (a swapped leg aborts).
  - the 8 group-VORP targets (rebuilt from the pinned leg, or supplied via
    --group-vorps) must match the reference budgets; a mismatch aborts --
    the imputation targets and the reweight controls can never silently
    disagree.
  - --controls are extracted mechanically from the reference budgets (Jeremy's
    2026-10-03 policy: DDF 8-group, 15% bench default adjustable, ROS); no
    weights are invented here.
  - any producer or review failure aborts with a nonzero exit and names the
    failing step.

Usage:
    python3 pipelines/run_as_published_vorp.py \
        --values-dir <dir of <source>.json publisher natives> \
        --roster-config <option-c-publisher-roster-v1> \
        --out-dir <candidates land here> \
        [--reference data/reference/jeg242-blend-controls-v1.json] \
        [--group-vorps <JEG-206 ddf-group-vorps.json override>] \
        [--granular-dir <dir>] [--excluded <json>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from refresh_vorp_views import refresh as refresh_views  # noqa: E402
from build_ddf_groups import build_groups_from_leg  # noqa: E402

DEFAULT_REFERENCE = ROOT / "data" / "reference" / "jeg242-blend-controls-v1.json"
REFERENCE_SCHEMA = "jeg242-blend-controls-v1"
GROUPS = [
    ("QB", "starter"), ("QB", "bench"),
    ("RB", "starter"), ("RB", "bench"),
    ("WR", "starter"), ("WR", "bench"),
    ("TE", "starter"), ("TE", "bench"),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_reference(path: Path) -> dict:
    raw = path.read_bytes()
    ref = json.loads(raw)
    if not isinstance(ref, dict) or ref.get("schema") != REFERENCE_SCHEMA:
        raise ValueError(f"reference schema must be {REFERENCE_SCHEMA}: {path}")
    if not isinstance(ref.get("budgets"), dict) or set(ref["budgets"]) != {f"{p}/{r}" for p, r in GROUPS}:
        raise ValueError("reference must carry exactly the eight group budgets")
    source = ref.get("source")
    if not isinstance(source, dict) or not source.get("ddf_leg") or not source.get("ddf_groups_sha256"):
        raise ValueError("reference must pin source.ddf_leg and source.ddf_groups_sha256")
    ref["_path"] = path
    ref["_sha256"] = hashlib.sha256(raw).hexdigest()
    return ref


def _verify_leg_pin(ref: dict) -> Path:
    leg_path = ROOT / ref["source"]["ddf_leg"]
    if not leg_path.is_file():
        raise ValueError(f"pinned DDF leg not found: {leg_path}")
    actual = _sha256(leg_path)
    pinned = ref["source"]["ddf_groups_sha256"]
    if actual != pinned:
        raise ValueError(
            f"leg sha mismatch: pinned {pinned[:16]}... != actual {actual[:16]}... "
            f"({leg_path}); re-pin the reference, never bypass")
    return leg_path


def _group_totals(artifact: dict) -> dict:
    totals = {}
    for row in artifact.get("groups", []):
        totals[(row["position"], row["role"])] = row["total_vorp"]
    if set(totals) != set(GROUPS):
        raise ValueError("group artifact must carry exactly the eight groups")
    return totals


def _check_budgets_match(totals: dict, budgets: dict, where: str) -> None:
    for pos, role in GROUPS:
        key = f"{pos}/{role}"
        if abs(totals[(pos, role)] - budgets[key]) > 1e-4:
            raise ValueError(
                f"group-VORP target {key} ({totals[(pos, role)]}) disagrees with "
                f"reference budget ({budgets[key]}) from {where}; aborting")


def _resolve_group_vorps(ref: dict, override: Path | None, work: Path) -> tuple[Path, dict]:
    """Return (group_vorps_path, provenance). Rebuilds from the pinned leg unless overridden."""
    if override is not None:
        artifact = json.loads(override.read_bytes())
        _check_budgets_match(_group_totals(artifact), ref["budgets"], f"override {override}")
        return override, {"mode": "override", "path": str(override), "sha256": _sha256(override)}
    leg_path = _verify_leg_pin(ref)
    out_path = work / "group_vorps.from_pinned_leg.json"
    artifact = build_groups_from_leg(leg_path, out_path)
    _check_budgets_match(_group_totals(artifact), ref["budgets"], f"pinned leg {leg_path}")
    return out_path, {"mode": "rebuilt_from_pinned_leg", "leg": str(leg_path),
                      "leg_sha256": ref["source"]["ddf_groups_sha256"],
                      "sha256": _sha256(out_path)}


def _extract_controls(ref: dict, work: Path) -> tuple[Path, dict]:
    """Mechanically extract the eight explicit weights from the reference budgets."""
    controls = {f"{p}/{r}": ref["budgets"][f"{p}/{r}"] for p, r in GROUPS}
    out_path = work / "controls.from_reference.json"
    out_path.write_text(json.dumps(controls, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path, {"mode": "extracted_from_reference_budgets",
                      "reference_sha256": ref["_sha256"],
                      "controls_sha256": _sha256(out_path),
                      "control_origin": "explicit_user_weights",
                      "policy": ref.get("policy", {})}


def orchestrate(args) -> int:
    out_dir = Path(args.out_dir)
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    try:
        ref = _load_reference(Path(args.reference))
        group_vorps_path, group_provenance = _resolve_group_vorps(
            ref, Path(args.group_vorps) if args.group_vorps else None, work)
        controls_path, controls_provenance = _extract_controls(ref, work)
    except (ValueError, OSError) as e:
        print(f"ORCHESTRATION FAILED at reference resolution: {e}", file=sys.stderr)
        return 2

    refresh_args = types.SimpleNamespace(
        values_dir=args.values_dir,
        group_vorps=str(group_vorps_path),
        roster_config=args.roster_config,
        controls=str(controls_path),
        reference=None,
        granular_dir=args.granular_dir,
        excluded=args.excluded,
        out_dir=str(out_dir),
    )
    code = refresh_views(refresh_args)
    if code != 0:
        print("ORCHESTRATION FAILED at refresh_vorp_views; see log above", file=sys.stderr)
        return 1

    provenance = {
        "schema": "jeg242-orchestration-v1",
        "orchestrated_at": datetime.now(timezone.utc).isoformat(),
        "reference": {"path": str(ref["_path"]), "sha256": ref["_sha256"],
                      "schema": REFERENCE_SCHEMA},
        "group_vorps": group_provenance,
        "controls": controls_provenance,
        "refresh": "pipelines/refresh_vorp_views.py (impute -> reweight --controls -> review)",
        "promotion": "none: candidate only; promotion is a separate reviewed step",
    }
    (out_dir / "orchestrator.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ORCHESTRATION OK: candidate -> {out_dir}/candidate.json "
          f"(reference {ref['_sha256'][:12]}..., leg pin verified)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--values-dir", required=True, help="dir of <source>.json publisher natives")
    ap.add_argument("--roster-config", required=True, help="option-c-publisher-roster-v1 JSON")
    ap.add_argument("--out-dir", required=True, help="candidates land here")
    ap.add_argument("--reference", default=str(DEFAULT_REFERENCE),
                    help="jeg242-blend-controls-v1 reference (default: pinned)")
    ap.add_argument("--group-vorps", default=None,
                    help="JEG-206 ddf-group-vorps.json override (default: rebuild from pinned leg)")
    ap.add_argument("--granular-dir", default=None)
    ap.add_argument("--excluded", default=None, help="JSON: source -> explicit exclusion reason")
    args = ap.parse_args(argv)
    try:
        return orchestrate(args)
    except Exception as e:  # noqa: BLE001 -- fail closed on unexpected errors
        print(f"ORCHESTRATION FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
