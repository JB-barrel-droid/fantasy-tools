#!/usr/bin/env python3
"""JEG-242: copied-dashboard preview with numerical three-view parity.

Item (3) of the JEG-242 integration handoff: build an opt-in local preview
that loads a REVIEWED shared-batch70-views-v1 candidate into a COPIED output
dashboard (production untouched) and proves the three per-view display maps
are numerically identical to what the candidate carries.

What this script does:
  1. Fail-closed gate: pipelines/review_batch70_views.py must pass on the
     candidate (+batch). Any gate failure aborts before anything is written.
  2. Derives the three per-view DISPLAY maps exactly as the preview renders
     them:
       - indexed:    native * 70 / provisional_maximum (ONE common all-source
                    peak; see below). Only genuine as-published native rows
                    are rendered. AVG and granular sources have no native
                    publisher values; backstopped publisher rows also remain
                    absent from Indexed rather than receiving invented natives.
       - vorp:      the candidate's imputed value-above-waivers map, verbatim.
       - adj_values: the candidate's shared-model reweighted map, verbatim.
  3. Numerical parity checks (independent re-derivation, tight tolerance):
       - the candidate's stored `indexed` map equals the batch artifacts'
         native maps exactly (catches per-source-peaked or tampered natives);
       - display_indexed * provisional_maximum / 70 recovers the native map
         (catches any scaling other than the common all-source peak);
       - every key in the candidate maps appears in the display maps and vice
         versa (genuine 0.0 values are KEPT; absent keys stay absent).
  4. Copies app/trade-value-chart into <out-dir>/preview-dashboard (isolated;
     production paths are never touched) and drops
     assets/vorp-views-preview.json plus preview.manifest.json pinning every
     input hash, the scaling arithmetic, and the review report.

This is a DATA-layer preview. The production curve-widget.js view rendering
for vorp/adj is still pending placeholders (JEG-210); when the widget's views
become data-backed they consume the same preview payload contract.

Usage:
    python3 pipelines/preview_vorp_views.py --candidate <candidate.json> \\
        --batch <vorp-source-batch-v1.json> --out-dir <preview-dir>

Exit codes: 0 = preview built and parity holds; 1 = a parity/gate failure
(each named); 2 = usage / unreadable input.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from review_batch70_views import main as review_main  # noqa: E402

PREVIEW_SCHEMA = "vorp-views-preview-v1"
MANIFEST_SCHEMA = "vorp-views-preview-manifest-v1"
DISPLAY_MAX = 70.0
RELTOL = 1e-9


def _fail(msg: str) -> int:
    print(f"PREVIEW FAILED: {msg}", file=sys.stderr)
    return 1


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path, what: str):
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ValueError(f"cannot read {what} {path}: {e}") from e
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON in {what} {path}: {e}") from e


class _UniqueDict(dict):
    pass


def _unique_object(pairs):
    d = _UniqueDict()
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate key {k!r}")
        d[k] = v
    return d


def _run_review(candidate: Path, batch: Path) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = review_main(["--artifact", str(candidate), "--batch", str(batch)])
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception as e:  # noqa: BLE001 -- review input errors are preview input errors
        return 1, f"review crashed: {type(e).__name__}: {e}"
    return code, out.getvalue() + err.getvalue()


def _batch_native_maps(batch_doc, batch_path: Path, sources: set[str]) -> dict[str, dict[str, float]]:
    """Independent native maps re-derived from the batch's source artifacts.

    For published kinds the imputed artifact carries per-record "native"
    (as-published trade values). Granular kinds (ppg-above-waiver method)
    carry no native trade values: their map is empty, and Indexed stays
    unavailable for them by design (handoff: "Granular Indexed remains
    unavailable").
    """
    from build_reweighted_values import SOURCE_KINDS  # noqa: E402

    natives: dict[str, dict[str, float]] = {}
    entries = batch_doc.get("sources") or {}
    for src in sources:
        kind = SOURCE_KINDS.get(src)
        if kind is None:
            raise ValueError(f"unknown source {src!r}: not a registered SOURCE_KIND")
        entry = entries.get(src)
        if entry is None:
            raise ValueError(f"source {src!r} present in candidate but missing from batch")
        if kind == "published":
            pool, _ = _load_json(batch_path.parent / entry["values"], f"values for {src}")
            native_map: dict[str, float] = {}
            for key, rec in pool.items():
                val = rec.get("native")
                # AVG-backstopped rows intentionally have native=None. They
                # belong in VORP/Adjusted but must not be fabricated in Indexed.
                if val is None:
                    continue
                if not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
                    raise ValueError(f"source {src} player {key}: bad native {val!r}")
                native_map[key] = float(val)
            natives[src] = native_map
        else:
            natives[src] = {}
    return natives


def _zero_count(mapping: dict[str, float]) -> int:
    return sum(1 for v in mapping.values() if v == 0.0)


def build_preview(candidate: Path, batch: Path, out_dir: Path) -> int:
    candidate_doc, candidate_bytes = _load_json(candidate, "candidate")
    batch_doc, batch_bytes = _load_json(batch, "batch")

    code, review_report = _run_review(candidate, batch)
    if code != 0:
        print(review_report, file=sys.stderr)
        return _fail("schema-specific review did not pass; preview not built")

    sources = candidate_doc.get("sources")
    if not isinstance(sources, dict) or not sources:
        return _fail("candidate has no sources")

    peak = candidate_doc.get("provisional_maximum")
    if not isinstance(peak, (int, float)) or not math.isfinite(peak) or peak <= 0:
        return _fail(f"bad provisional_maximum {peak!r}")
    peak = float(peak)
    expected_scale = DISPLAY_MAX / peak
    actual_scale = candidate_doc.get("batch_scale")
    if not isinstance(actual_scale, (int, float)) or not math.isclose(
        actual_scale, expected_scale, rel_tol=RELTOL, abs_tol=1e-12
    ):
        return _fail(
            f"batch_scale {actual_scale!r} != 70/provisional_maximum ({expected_scale!r})"
        )

    natives = _batch_native_maps(batch_doc, batch, set(sources))

    views: dict[str, dict] = {"indexed": {}, "vorp": {}, "adj_values": {}}
    exclusions: dict[str, dict[str, str]] = {}
    zero_accounting: dict[str, dict[str, int]] = {}
    player_counts: dict[str, dict[str, int]] = {}

    for src, per_view in sources.items():
        if not isinstance(per_view, dict):
            return _fail(f"source {src}: per-view maps missing")
        for view in ("indexed", "vorp", "adj_values"):
            if view not in per_view or not isinstance(per_view[view], dict):
                return _fail(f"source {src}: view {view!r} missing or not a map")

        stored_indexed = {k: float(v) for k, v in per_view["indexed"].items()}
        native_map = natives[src]
        if native_map:
            # The candidate stores the UNSCALED native map; prove it.
            if set(stored_indexed) != set(native_map):
                return _fail(
                    f"source {src}: candidate indexed keys != batch native keys "
                    f"(tampered or mismatched-vintage natives)"
                )
            for k, nv in native_map.items():
                if not math.isclose(stored_indexed[k], nv, rel_tol=RELTOL, abs_tol=1e-12):
                    return _fail(
                        f"source {src} player {k}: candidate indexed {stored_indexed[k]!r} "
                        f"!= batch native {nv!r} (native map tampered)"
                    )
            display_indexed: dict = {
                k: nv * DISPLAY_MAX / peak for k, nv in native_map.items()
            }
            # Independent re-derivation: display * peak / 70 recovers natives.
            for k, nv in native_map.items():
                back = display_indexed[k] * peak / DISPLAY_MAX
                if not math.isclose(back, nv, rel_tol=RELTOL, abs_tol=1e-12):
                    return _fail(
                        f"source {src} player {k}: indexed re-derivation failed "
                        f"({back!r} != native {nv!r}); not the common all-source peak"
                    )
            views["indexed"][src] = display_indexed
        else:
            reason = (
                "source has no as-published native trade values for this candidate; "
                "Indexed view is unavailable while VORP/Adjusted remain valid"
            )
            views["indexed"][src] = {"unavailable": reason}
            exclusions.setdefault(src, {})["indexed"] = reason

        # vorp / adj_values are carried verbatim. They must agree with one
        # another; a publisher's native map may be a strict subset when AVG
        # backstops missing league-cohort players.
        mapped_nonindexed = {}
        for view in ("vorp", "adj_values"):
            stored = {k: float(v) for k, v in per_view[view].items()}
            mapped_nonindexed[view] = stored
            views[view][src] = stored
        if set(mapped_nonindexed["vorp"]) != set(mapped_nonindexed["adj_values"]):
            return _fail(f"source {src}: vorp/adj_values key sets differ")
        if native_map and not set(native_map).issubset(set(mapped_nonindexed["vorp"])):
            return _fail(
                f"source {src}: native keys are not a subset of VORP/Adjusted "
                "(stale or invented native rows)"
            )

        zero_accounting[src] = {
            view: _zero_count(views[view][src]) for view in ("indexed", "vorp", "adj_values")
            if isinstance(views[view][src], dict) and "unavailable" not in views[view][src]
        }
        player_counts[src] = {
            view: len(views[view][src]) for view in ("indexed", "vorp", "adj_values")
            if "unavailable" not in views[view][src]
        }

    out = Path(out_dir)
    if out.exists():
        return _fail(f"out-dir {out} already exists (refusing to overwrite)")
    dashboard_src = ROOT / "app" / "trade-value-chart"
    if not dashboard_src.is_dir():
        return _fail(f"dashboard source dir missing: {dashboard_src}")
    dashboard_dst = out / "preview-dashboard"
    shutil.copytree(dashboard_src, dashboard_dst)

    preview_payload = {
        "schema": PREVIEW_SCHEMA,
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "batch_sha256": hashlib.sha256(batch_bytes).hexdigest(),
        "provisional_maximum": peak,
        "batch_scale": float(actual_scale),
        "arithmetic": "indexed_display = native * 70 / provisional_maximum (one common all-source peak); vorp and adj_values are the candidate maps verbatim",
        "native_maps": natives,
        "views": views,
        "exclusions": exclusions,
        "zero_accounting": zero_accounting,
        "player_counts": player_counts,
    }
    payload_bytes = json.dumps(
        preview_payload, indent=2, sort_keys=True, allow_nan=False
    ).encode("utf-8")
    (dashboard_dst / "assets" / "vorp-views-preview.json").write_bytes(payload_bytes)

    # Round-trip integrity: what landed on disk is what we derived.
    reread = json.loads(
        (dashboard_dst / "assets" / "vorp-views-preview.json").read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
    )
    if reread["views"] != preview_payload["views"]:
        return _fail("preview payload changed between derivation and disk (write corruption)")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "candidate": str(candidate),
        "batch": str(batch),
        "input_sha256": {
            "candidate": hashlib.sha256(candidate_bytes).hexdigest(),
            "batch": hashlib.sha256(batch_bytes).hexdigest(),
        },
        "preview_payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "provisional_maximum": peak,
        "batch_scale": float(actual_scale),
        "sources_previewed": sorted(sources),
        "indexed_unavailable": sorted(exclusions),
        "review_report": review_report.strip().splitlines(),
        "promotion": "none: preview only; nothing promoted, production untouched",
    }
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)
    (out / "preview.manifest.json").write_text(manifest_json, encoding="utf-8")

    print(
        f"PREVIEW OK: {dashboard_dst} ({len(sources)} sources, "
        f"{len(exclusions)} indexed-excluded, peak={peak:.6f})"
    )
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", type=Path, required=True,
                    help="reviewed shared-batch70-views-v1 candidate JSON")
    ap.add_argument("--batch", type=Path, required=True,
                    help="vorp-source-batch-v1 JSON the candidate was built from")
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="preview dir to create (refused if it exists)")
    args = ap.parse_args(argv)
    try:
        return build_preview(args.candidate, args.batch, args.out_dir)
    except ValueError as e:
        return _fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
