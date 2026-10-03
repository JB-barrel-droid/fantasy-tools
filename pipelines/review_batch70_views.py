#!/usr/bin/env python3
"""JEG-242: schema-specific review for shared-batch70-views-v1 candidate artifacts.

The existing comparison review cannot consume the new three-view candidate
schema (the handoff doc calls this out explicitly), so this review gates the
candidate artifacts that build_reweighted_values.py emits before any refresh,
view wiring, or promotion step may consume them.

What this review checks (fail-closed; every failure names its gate):
  1. Schema/version/status: shared-batch70-views-v1, artifact_status == "candidate".
     A promoted/reviewed artifact needs a different review path; anything else
     fails here, never silently passes.
  2. Scale integrity: batch_scale / provisional_maximum / total_budget_per_source
     are positive finite; total_budget_per_source == batch_scale.
  3. Allocation: allocation_fractions covers exactly the eight POS/role groups,
     sums to 1; group_budgets == batch_scale * fraction per group.
  4. Views: every source carries exactly {indexed, vorp, adj_values}.
     Published sources: indexed contains only genuine publisher natives and may
     be a strict subset of vorp/adj_values when AVG backstops players the
     publisher did not rank. Derived AVG and granular sources carry no
     as-published native trade values, so indexed must be EMPTY; vorp/adj_values
     stay nonempty with identical key sets. All values finite and >= 0.
  5. One common 70 anchor: the global adj_values maximum is 70 (tight
     tolerance) and no source exceeds it. Per-source independent 70 peaks are
     the legacy reindex signature, not this pipeline's output.
  6. Budget conservation: each source's adj_values sum equals
     total_budget_per_source (tight tolerance). This is the discriminator
     against the old per-source normalization, which destroys the common
     budget (JEG-240 class defect).
  7. Manifest provenance: batch_sha256 present; configuration validates as an
     explicit RosterConfig; every known source is either included or explicitly
     excluded with a reason; per-source input pins carry 64-hex hashes and the
     approved imputation manifest schema/method for its kind.
  8. Hash admission (--batch): the supplied batch file's sha256 matches the
     manifest's batch_sha256; each source's artifact/sidecar paths resolve
     relative to the batch file and their hashes match the pins; the sidecar
     manifest's output_sha256 matches the artifact bytes; the source
     configuration matches the batch configuration on teams/scoring/slots/
     flex. This re-verifies the admission chain independently of the builder.
  9. Control provenance is SURFACED, never approved: control_origin,
     reference policy status/horizon/decision_url (or explicit-weights hash)
     are printed for the human promoter. Weight approval stays with Jeremy.

Exit codes: 0 = all gates pass; 1 = one or more gate failures (each named);
2 = usage / unreadable input.

Usage:
    python3 pipelines/review_batch70_views.py --artifact <candidate.json>
        [--batch <vorp-source-batch-v1.json>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from build_imputed_vorps import GROUPS, RosterConfig  # noqa: E402
from build_reweighted_values import SOURCE_KINDS  # noqa: E402

DISPLAY_MAX = 70.0
EXPECTED_SCHEMA = "shared-batch70-views-v1"
EXPECTED_STATUS = "candidate"
# (manifest schema, manifest method) per source kind.
EXPECTED_MANIFEST = {
    "published": {
        ("option-c-imputation-manifest-v1", "eight-group-proportional-v1"),
        ("option-c-imputation-manifest-v1", "eight-group-proportional-v1+avg-backstop-v1"),
    },
    "derived": {
        ("option-c-imputation-manifest-v1", "cross-source-average-v1"),
    },
    "granular": {
        ("granular-vorp-manifest-v1", "ppg-above-waiver-v1"),
    },
}
GROUP_KEYS = {f"{p}/{r}" for p, r in GROUPS}
REL_TOL = 1e-9
ABS_TOL = 1e-9


class GateFailure(Exception):
    pass


def _is_sha256(s) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(
        c in "0123456789abcdef" for c in s.lower()
    )


def _finite_nonneg(v, what) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise GateFailure(f"{what}: not a number ({v!r})")
    f = float(v)
    if not math.isfinite(f):
        raise GateFailure(f"{what}: not finite ({v!r})")
    if f < 0:
        raise GateFailure(f"{what}: negative ({v!r})")
    return f


def _close(a, b, what) -> None:
    if not math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL):
        raise GateFailure(f"{what}: {a!r} != {b!r}")


def _load_json(path: Path, what: str):
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise GateFailure(f"{what}: unreadable ({e})")
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError as e:
        raise GateFailure(f"{what}: invalid JSON ({e})")


def check_top_level(doc) -> None:
    if not isinstance(doc, dict):
        raise GateFailure("top level: not an object")
    if doc.get("schema") != EXPECTED_SCHEMA:
        raise GateFailure(
            f"schema: {doc.get('schema')!r} != {EXPECTED_SCHEMA!r} "
            "(legacy/unwired artifact)"
        )
    if doc.get("artifact_status") != EXPECTED_STATUS:
        raise GateFailure(
            f"artifact_status: {doc.get('artifact_status')!r} != {EXPECTED_STATUS!r}; "
            "this review only admits candidates"
        )


def check_scale(doc) -> tuple[float, float]:
    scale = _finite_nonneg(doc.get("batch_scale"), "batch_scale")
    maximum = _finite_nonneg(doc.get("provisional_maximum"), "provisional_maximum")
    total = _finite_nonneg(doc.get("total_budget_per_source"), "total_budget_per_source")
    if scale == 0 or maximum == 0 or total == 0:
        raise GateFailure("scale: batch_scale/provisional_maximum/total_budget must be positive")
    _close(total, scale, "total_budget_per_source vs batch_scale")
    return scale, maximum


def check_allocation(doc, scale: float) -> None:
    fracs = doc.get("allocation_fractions")
    if not isinstance(fracs, dict) or set(fracs) != GROUP_KEYS:
        raise GateFailure(
            f"allocation_fractions: must cover exactly the 8 groups, got "
            f"{sorted(fracs) if isinstance(fracs, dict) else type(fracs).__name__}"
        )
    vals = {k: _finite_nonneg(v, f"allocation_fractions[{k}]") for k, v in fracs.items()}
    _close(sum(vals.values()), 1.0, "allocation_fractions sum")
    budgets = doc.get("group_budgets")
    if not isinstance(budgets, dict) or set(budgets) != GROUP_KEYS:
        raise GateFailure("group_budgets: must cover exactly the 8 groups")
    for k in GROUP_KEYS:
        b = _finite_nonneg(budgets[k], f"group_budgets[{k}]")
        _close(b, scale * vals[k], f"group_budgets[{k}] vs scale*fraction")


def check_views(doc, scale: float) -> dict:
    sources = doc.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise GateFailure("sources: nonempty mapping required")
    maxima = {}
    for name, views in sources.items():
        if not isinstance(views, dict) or set(views) != {"indexed", "vorp", "adj_values"}:
            raise GateFailure(
                f"sources[{name}]: must carry exactly indexed/vorp/adj_values"
            )
        kind = SOURCE_KINDS.get(name)
        if kind is None:
            raise GateFailure(f"sources[{name}]: unknown source kind")
        indexed_map = views["indexed"]
        if kind in ("granular", "derived"):
            if not isinstance(indexed_map, dict) or indexed_map:
                raise GateFailure(
                    f"sources[{name}]: {kind} source must carry an empty "
                    "indexed map (it has no as-published natives)"
                )
            indexed_keys = set()
        else:
            if not isinstance(indexed_map, dict) or not indexed_map:
                raise GateFailure(
                    f"sources[{name}].indexed: nonempty mapping required "
                    "for published sources"
                )
            for k, v in indexed_map.items():
                _finite_nonneg(v, f"sources[{name}].indexed[{k}]")
            indexed_keys = set(indexed_map)
        keysets = []
        for view in ("vorp", "adj_values"):
            mapping = views[view]
            if not isinstance(mapping, dict) or not mapping:
                raise GateFailure(f"sources[{name}].{view}: nonempty mapping required")
            for k, v in mapping.items():
                _finite_nonneg(v, f"sources[{name}].{view}[{k}]")
            keysets.append(set(mapping))
        if keysets[0] != keysets[1]:
            raise GateFailure(
                f"sources[{name}]: vorp/adj_values key sets differ "
                "(view wiring mismatch)"
            )
        if kind == "published" and not indexed_keys.issubset(keysets[0]):
            raise GateFailure(
                f"sources[{name}]: indexed contains keys absent from "
                "vorp/adj_values (invented or stale native rows)"
            )
        adj = views["adj_values"]
        peak = max(adj.values())
        if peak > DISPLAY_MAX * (1 + REL_TOL) + ABS_TOL:
            raise GateFailure(
                f"sources[{name}]: adj_values peak {peak} exceeds the 70 anchor"
            )
        total = math.fsum(adj.values())
        _close(total, scale, f"sources[{name}]: adj_values sum vs total_budget_per_source")
        maxima[name] = peak
    global_max = max(maxima.values())
    _close(global_max, DISPLAY_MAX, "global adj_values maximum vs 70 anchor")
    return maxima


def check_manifest(doc) -> dict:
    manifest = doc.get("manifest")
    if not isinstance(manifest, dict):
        raise GateFailure("manifest: missing (unwired artifact has no provenance)")
    if not _is_sha256(manifest.get("batch_sha256")):
        raise GateFailure("manifest.batch_sha256: not a 64-hex digest")
    try:
        config = RosterConfig.from_manifest(manifest.get("configuration"))
    except (ValueError, TypeError, AttributeError) as e:
        raise GateFailure(f"manifest.configuration: invalid RosterConfig ({e})")
    excluded = manifest.get("excluded_sources")
    if not isinstance(excluded, dict):
        raise GateFailure("manifest.excluded_sources: mapping required")
    sources = doc.get("sources", {})
    for name in sources:
        if name not in SOURCE_KINDS:
            raise GateFailure(f"sources[{name}]: unknown source kind")
        if name in excluded:
            raise GateFailure(f"sources[{name}]: included and excluded")
    for name in SOURCE_KINDS:
        if name not in sources and name not in excluded:
            raise GateFailure(
                f"source {name}: neither included nor explicitly excluded"
            )
        if name in excluded and (
            not isinstance(excluded[name], str) or not excluded[name].strip()
        ):
            raise GateFailure(f"excluded_sources[{name}]: reason required")
    pins = manifest.get("input_pins")
    if not isinstance(pins, dict) or set(pins) != set(sources):
        raise GateFailure("manifest.input_pins: must pin exactly the included sources")
    for name, pin in pins.items():
        if not isinstance(pin, dict):
            raise GateFailure(f"input_pins[{name}]: not an object")
        for field in ("values_sha256", "manifest_sha256", "manifest"):
            if field not in pin:
                raise GateFailure(f"input_pins[{name}]: missing {field}")
        if not _is_sha256(pin["values_sha256"]) or not _is_sha256(pin["manifest_sha256"]):
            raise GateFailure(f"input_pins[{name}]: hashes must be 64-hex digests")
        meta = pin["manifest"]
        expected = EXPECTED_MANIFEST[SOURCE_KINDS[name]]
        actual = (meta.get("schema"), meta.get("method")) if isinstance(meta, dict) else None
        if actual not in expected:
            raise GateFailure(
                f"input_pins[{name}]: manifest (schema, method) "
                f"{actual if actual is not None else '?'} not in {sorted(expected)} "
                "(method mismatch)"
            )
    return manifest


def check_batch_admission(doc, manifest, batch_path: Path) -> None:
    batch, batch_bytes = _load_json(batch_path, "batch file")
    batch_digest = hashlib.sha256(batch_bytes).hexdigest()
    if batch_digest != manifest["batch_sha256"]:
        raise GateFailure(
            "batch admission: batch file sha256 does not match manifest.batch_sha256 "
            "(stale or substituted batch)"
        )
    if not isinstance(batch, dict) or batch.get("schema") != "vorp-source-batch-v1":
        raise GateFailure("batch admission: not a vorp-source-batch-v1 document")
    batch_sources = batch.get("sources", {})
    config = manifest["configuration"]
    common = ("teams", "scoring", "slots", "flex_count", "flex_eligible")
    for name, entry in batch_sources.items():
        if not isinstance(entry, dict) or set(entry) != {"values", "manifest"}:
            raise GateFailure(f"batch admission: sources[{name}] needs values+manifest paths")
        for field in ("values", "manifest"):
            target = batch_path.parent / entry[field]
            try:
                content = target.read_bytes()
            except OSError as e:
                raise GateFailure(
                    f"batch admission: sources[{name}].{field} unreadable ({e})"
                )
            digest = hashlib.sha256(content).hexdigest()
            pin_field = "values_sha256" if field == "values" else "manifest_sha256"
            if digest != manifest["input_pins"][name][pin_field]:
                raise GateFailure(
                    f"batch admission: sources[{name}].{field} hash != pinned "
                    f"{pin_field} (artifact substituted after batch)"
                )
            if field == "manifest":
                meta = json.loads(content)
                values_target = batch_path.parent / entry["values"]
                values_digest = hashlib.sha256(values_target.read_bytes()).hexdigest()
                if meta.get("output_sha256") != values_digest:
                    raise GateFailure(
                        f"batch admission: sources[{name}] sidecar output_sha256 != "
                        "artifact bytes (sidecar/artifact mismatch)"
                    )
                src_config_key = (
                    "publisher_roster"
                    if SOURCE_KINDS[name] in ("published", "derived")
                    else "source_config"
                )
                src_config = meta.get(src_config_key)
                if not isinstance(src_config, dict) or any(
                    src_config.get(k) != config.get(k) for k in common
                ):
                    raise GateFailure(
                        f"batch admission: sources[{name}] configuration != batch "
                        "configuration (mixed-config batch)"
                    )


def report_control_provenance(manifest) -> list[str]:
    lines = []
    origin = manifest.get("control_origin")
    lines.append(f"control_origin: {origin}")
    if origin == "linear_blend_reference":
        ref = manifest.get("reference", {})
        policy = ref.get("policy", {}) if isinstance(ref, dict) else {}
        status = policy.get("status")
        lines.append(f"blend policy status: {status}")
        lines.append(f"blend horizon: {policy.get('horizon')}")
        lines.append(f"blend decision_url: {policy.get('decision_url')}")
        lines.append(f"blend reference_sha256: {ref.get('reference_sha256')}")
        if status != "reviewed":
            lines.append(
                "NOTE: blend reference is not reviewed; weight approval stays "
                "with Jeremy (candidate reference is informational only)."
            )
    elif origin == "explicit_user_weights":
        lines.append(f"explicit weights sha256: {manifest.get('controls_sha256')}")
    else:
        lines.append("WARNING: unrecognized control_origin; weights are unaccounted")
    return lines


def review(artifact_path: Path, batch_path: Path | None) -> list[str]:
    """Run all gates; return report lines. Raises GateFailure on any failure."""
    doc, _ = _load_json(artifact_path, "candidate artifact")
    report = [f"artifact: {artifact_path}"]
    check_top_level(doc)
    report.append("gate 1/8 schema+status: OK (shared-batch70-views-v1 candidate)")
    scale, maximum = check_scale(doc)
    report.append(
        f"gate 2/8 scale: OK (batch_scale={scale:.6f}, provisional_maximum={maximum:.6f})"
    )
    check_allocation(doc, scale)
    report.append("gate 3/8 allocation: OK (8 groups, fractions sum to 1)")
    maxima = check_views(doc, scale)
    report.append(
        "gate 4-6/8 views: OK "
        f"({len(maxima)} sources; per-source peaks "
        + ", ".join(f"{s}={m:.2f}" for s, m in sorted(maxima.items()))
        + "; global max 70; budgets conserved)"
    )
    manifest = check_manifest(doc)
    report.append("gate 7/8 manifest: OK (pins, config, exclusions)")
    if batch_path is not None:
        check_batch_admission(doc, manifest, batch_path)
        report.append("gate 8/8 batch admission: OK (hashes chain to batch file)")
    else:
        report.append("gate 8/8 batch admission: SKIPPED (--batch not supplied)")
    report.extend(report_control_provenance(manifest))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", type=Path, required=True,
                    help="shared-batch70-views-v1 candidate JSON")
    ap.add_argument("--batch", type=Path, default=None,
                    help="vorp-source-batch-v1 JSON the candidate was built from")
    args = ap.parse_args(argv)
    try:
        report = review(args.artifact, args.batch)
    except GateFailure as e:
        print(f"REVIEW FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 -- input errors are gate input errors
        print(f"REVIEW ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print("\n".join(report))
    print("REVIEW PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
