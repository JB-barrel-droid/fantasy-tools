#!/usr/bin/env python3
"""JEG-242: candidate refresh for the three-view (Indexed/VORP/Adj) pipeline.

This is the missing refresh wiring the parent defect names: the reviewed
producers (pipelines/build_imputed_vorps.py -> pipelines/backstop_shallow_sources.py
-> pipelines/build_reweighted_values.py)
had no refresh, promotion, or view path invoking them. This script wires them
into a versioned refresh path with pipelines/review_batch70_views.py as the
fail-closed gate.

CANDIDATE-ONLY: artifacts land under --out-dir with a versioned run manifest.
Nothing is written to Supabase, nothing is promoted, nothing touches the live
views or the browser path. Promotion consumes only candidates that pass the
review, through a separate reviewed step.

Fail-closed:
  - exactly one of --controls / --reference is required and forwarded to
    build_reweighted_values unchanged. No default weights are invented here;
    weight approval stays with Jeremy (review gate 9 surfaces provenance).
  - every published source in the values dir is imputed; every known source
    not supplied is EXCLUDED with an explicit reason (overridable via
    --excluded). The batch contract rejects silent gaps.
  - any producer or review failure aborts with a nonzero exit and names the
    failing step. The run manifest is written only after the review passes.

Usage:
    python3 pipelines/refresh_vorp_views.py \
        --values-dir <dir of <source>.json publisher natives> \
        --group-vorps <JEG-206 ddf-group-vorps.json> \
        --roster-config <option-c-publisher-roster-v1> \
        --controls <eight explicit weights> | --reference <linear-blend-reference-v1> \
        [--granular-dir <dir of pre-built granular imputed artifacts>] \
        [--excluded <json: source -> reason>] \
        --out-dir <candidates land here>
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from build_imputed_vorps import main as impute_main  # noqa: E402
from build_imputed_vorps import RosterConfig, _unique_object  # noqa: E402
from build_reweighted_values import SOURCE_KINDS  # noqa: E402
from build_reweighted_values import main as reweight_main  # noqa: E402
from backstop_shallow_sources import main as backstop_main  # noqa: E402
from review_batch70_views import main as review_main  # noqa: E402

SCHEMA = "vorp-views-refresh-run-v1"
PUBLISHED = tuple(s for s, k in SOURCE_KINDS.items() if k == "published")
DERIVED = tuple(s for s, k in SOURCE_KINDS.items() if k == "derived")
GRANULAR = tuple(s for s, k in SOURCE_KINDS.items() if k == "granular")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capture(fn, *argv) -> tuple[int, str]:
    """Run a producer main(argv); convert exceptions to a nonzero exit."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = fn(list(argv))
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        print(f"SystemExit({e.code})", file=err)
    except Exception as e:  # noqa: BLE001 -- producer input errors are refresh input errors
        code = 1
        print(f"{type(e).__name__}: {e}", file=err)
    return code, out.getvalue() + err.getvalue()


def refresh(args) -> int:
    values_dir = Path(args.values_dir)
    out_dir = Path(args.out_dir)
    roster_bytes = Path(args.roster_config).read_bytes()
    roster = RosterConfig.from_manifest(json.loads(roster_bytes, object_pairs_hook=_unique_object))

    supplied = {}
    for src in PUBLISHED:
        cand = values_dir / f"{src}.json"
        if cand.is_file():
            supplied[src] = cand
    if not supplied:
        print(f"REFRESH FAILED: no publisher values found in {values_dir} "
              f"(expected one of {[s + '.json' for s in PUBLISHED]})", file=sys.stderr)
        return 2

    excluded = dict(json.loads(Path(args.excluded).read_bytes())) if args.excluded else {}
    for src in PUBLISHED:
        if src not in supplied and src not in excluded:
            excluded[src] = "not supplied to this refresh run"

    granular_dir = Path(args.granular_dir) if args.granular_dir else None
    granular = {}
    for src in GRANULAR:
        if granular_dir is not None:
            vals = granular_dir / f"{src}.json"
            manifest = granular_dir / f"{src}.json.manifest.json"
            if vals.is_file() and manifest.is_file():
                granular[src] = (vals, manifest)
                continue
        if src not in excluded:
            excluded[src] = "granular imputed artifact not supplied to this refresh run"

    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    step_log: list[str] = []
    input_pins: dict[str, str] = {
        "group_vorps": _sha256(Path(args.group_vorps)),
        "roster_config": hashlib.sha256(roster_bytes).hexdigest(),
    }
    batch_sources: dict[str, dict[str, str]] = {}
    for src, values_path in supplied.items():
        imputed_path = work / f"imputed_{src}.json"
        code, log = _capture(
            impute_main,
            "--values", str(values_path),
            "--group-vorps", str(args.group_vorps),
            "--roster-config", str(args.roster_config),
            "--out", str(imputed_path),
        )
        step_log.append(f"impute {src}: exit={code}\n{log}")
        if code != 0:
            print(f"REFRESH FAILED at imputation for {src}:\n{log}", file=sys.stderr)
            return 1
        input_pins[f"values/{src}"] = _sha256(values_path)
        batch_sources[src] = {
            "values": imputed_path.name,
            "manifest": imputed_path.name + ".manifest.json",
        }

    for src, (vals, manifest) in granular.items():
        dest_vals = work / f"granular_{src}.json"
        dest_manifest = work / f"granular_{src}.json.manifest.json"
        dest_vals.write_bytes(vals.read_bytes())
        dest_manifest.write_bytes(manifest.read_bytes())
        input_pins[f"granular/{src}"] = _sha256(vals)
        batch_sources[src] = {"values": dest_vals.name, "manifest": dest_manifest.name}

    batch = {
        "schema": "vorp-source-batch-v1",
        "configuration": roster.manifest(),
        "sources": batch_sources,
        "excluded_sources": excluded,
    }

    # AVG/backstop is an actual stage of the reviewed pipeline, not a sidecar
    # utility. With two or more published sources, derive the league-cohort AVG
    # line and backstop any publisher missing members of that cohort. With only
    # one published source, AVG is impossible by definition and is explicitly
    # excluded rather than invented.
    pre_backstop_path = work / "batch.pre-backstop.json"
    pre_backstop_path.write_text(json.dumps(batch, indent=2, sort_keys=True))
    if len(supplied) >= 2:
        code, log = _capture(
            backstop_main,
            "--batch", str(pre_backstop_path),
            "--out-dir", str(work),
        )
        step_log.append(f"avg/backstop: exit={code}\n{log}")
        if code != 0:
            print(f"REFRESH FAILED at avg/backstop:\n{log}", file=sys.stderr)
            return 1
        augmented_path = work / "vorp-source-batch-augmented-v1.json"
        batch_path = work / "batch.json"
        batch_path.write_bytes(augmented_path.read_bytes())
        batch = json.loads(batch_path.read_bytes())
        batch_sources = dict(batch["sources"])
        excluded = dict(batch["excluded_sources"])
    else:
        for src in DERIVED:
            excluded.setdefault(src, "cross-source average requires at least 2 published sources")
        batch["excluded_sources"] = excluded
        batch_path = work / "batch.json"
        batch_path.write_text(json.dumps(batch, indent=2, sort_keys=True))
    input_pins["pre_backstop_batch"] = _sha256(pre_backstop_path)
    if len(supplied) >= 2:
        input_pins["backstopped_batch"] = _sha256(batch_path)

    candidate_path = out_dir / "candidate.json"
    weight_args = ["--controls", str(args.controls)] if args.controls else ["--reference", str(args.reference)]
    if args.controls:
        input_pins["controls"] = _sha256(Path(args.controls))
    else:
        input_pins["reference"] = _sha256(Path(args.reference))
    code, log = _capture(reweight_main, "--batch", str(batch_path), *weight_args, "--out", str(candidate_path))
    step_log.append(f"reweight: exit={code}\n{log}")
    if code != 0:
        print(f"REFRESH FAILED at reweight:\n{log}", file=sys.stderr)
        return 1

    code, report = _capture(review_main, "--artifact", str(candidate_path), "--batch", str(batch_path))
    step_log.append(f"review: exit={code}\n{report}")
    if code != 0:
        print(f"REFRESH FAILED at schema-specific review:\n{report}", file=sys.stderr)
        return 1

    candidate_bytes = candidate_path.read_bytes()
    manifest = {
        "schema": SCHEMA,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "steps": ["impute", "avg_backstop", "reweight", "review"] if len(supplied) >= 2
                 else ["impute", "reweight", "review"],
        "sources_included": sorted(batch_sources),
        "excluded_sources": excluded,
        "avg_backstop": batch.get("_backstop"),
        "weight_selection": "controls" if args.controls else "reference",
        "input_sha256": input_pins,
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "batch_sha256": _sha256(batch_path),
        "review_report": report.strip().splitlines(),
        "promotion": "none: candidate only; promotion is a separate reviewed step",
    }
    # Serialize before writing; a metadata failure cannot leave a partial manifest.
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)
    (out_dir / "refresh-run.manifest.json").write_text(manifest_json, encoding="utf-8")
    print(f"REFRESH OK: candidate -> {candidate_path} "
          f"({len(batch_sources)} sources, {len(excluded)} excluded)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--values-dir", required=True, help="dir of <source>.json publisher natives")
    ap.add_argument("--group-vorps", required=True, help="JEG-206 ddf-group-vorps.json")
    ap.add_argument("--roster-config", required=True, help="option-c-publisher-roster-v1 JSON")
    selection = ap.add_mutually_exclusive_group(required=True)
    selection.add_argument("--controls", help="JSON: all eight explicit user weights")
    selection.add_argument("--reference", help="linear-blend-reference-v1 defaults")
    ap.add_argument("--granular-dir", default=None,
                    help="dir of pre-built granular imputed artifacts (<source>.json + manifest)")
    ap.add_argument("--excluded", default=None, help="JSON: source -> explicit exclusion reason")
    ap.add_argument("--out-dir", required=True, help="candidates land here")
    args = ap.parse_args(argv)
    try:
        return refresh(args)
    except Exception as e:  # noqa: BLE001 -- fail closed on unexpected errors
        print(f"REFRESH FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
