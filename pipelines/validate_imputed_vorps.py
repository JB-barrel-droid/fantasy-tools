#!/usr/bin/env python3
"""JEG-212: Validate imputed VORPs before they go live on the chart.

Five checks run before the imputed VORP pipeline goes live, catching data
issues early:

0. Input completeness: the artifact has >=1 source with >=1 assignable
   player, and group totals cover all 8 groups. FAIL on vacuous inputs.
1. Group-total reconciliation: sum of imputed VORPs per group == JEG-206
   group total (within relative tolerance). FAIL on mismatch.
2. Non-negative check: all imputed VORPs >= 0. FAIL on negative.
3. Ordering sanity: within each group, imputed VORP ordering matches
   publisher native ordering (higher native -> higher imputed, since
   alloc_factor > 0). WARN on inversions.
4. Divergence flags: |imputed_vorp - ddf_vorp| / ddf_vorp > 50% flagged
   for human review. FLAG only (does not fail).

Usage:
  python pipelines/validate_imputed_vorps.py \\
    --imputed-artifact dist/modules/source-value-lineage.json \\
    --group-totals data/ddf-group-vorps.json \\
    [--tolerance 0.01] \\
    [--output report.json]

Exit codes:
  0 = all fail-checks passed (warnings/flags do not affect exit code)
  1 = at least one fail-check violated
"""

import argparse
import json
import os
import sys

# Default relative tolerance for group-total reconciliation (1%).
# alloc_factor is rounded to 4dp and imputed_vorp to 2dp; 1% comfortably
# exceeds the rounding error while catching real data drift.
DEFAULT_TOLERANCE = 0.01

# Divergence threshold for flagging (50% relative).
DIVERGENCE_THRESHOLD = 0.50

# The 8 groups defined by JEG-206. flex maps to Starter.
EXPECTED_GROUPS = [
    f"{pos}|{role}" for pos in ("QB", "RB", "WR", "TE")
    for role in ("Starter", "Bench")
]


def load_imputed_artifact(path):
    """Load imputed VORP artifact. Returns {src_key: [player_records]}.

    Accepts two shapes:
      A) Lineage artifact (dist/modules/source-value-lineage.json):
         {"sources": {src: {"top25": [player_records]}}}
         (or {"players": [...]} for a future full-population artifact)
      B) Flat shape: {src_key: [player_records]}
    """
    with open(path) as f:
        doc = json.load(f)

    if isinstance(doc, dict) and "sources" in doc:
        out = {}
        for src_key, src_data in doc["sources"].items():
            if not isinstance(src_data, dict):
                continue
            # Prefer "players" (full population) over "top25" (dashboard subset).
            players = src_data.get("players") or src_data.get("top25") or []
            out[src_key] = players
        return out

    # Flat shape: top-level keys are source names.
    if isinstance(doc, dict):
        return {k: v for k, v in doc.items() if isinstance(v, list)}

    raise ValueError(
        f"Cannot parse imputed VORP artifact at {path}: unrecognized shape"
    )


def _canonical_group_label(position, role):
    """Return "QB|Starter" style label regardless of input casing."""
    pos = str(position).strip().upper()
    role_cap = str(role).strip().capitalize()  # "starter" -> "Starter"
    return f"{pos}|{role_cap}"


def load_group_totals(path):
    """Load JEG-206 group totals. Returns {group_label: float}.

    Accepts both shapes JEG-206 has shipped:
      A) Canonical (current main): {"groups": [
            {"position": "QB", "role": "starter", "total_vorp": 200.0},
            ... 8 rows]}
      B) Dict shorthand (some spec docs / drafts):
            {"groups": {"QB|Starter": 200.0, ...}}
    Returns a dict keyed by canonical "QB|Starter" labels so the rest of
    the validator can compare against its EXPECTED_GROUPS keys.
    """
    with open(path) as f:
        doc = json.load(f)
    raw = (doc or {}).get("groups")
    clean = {}
    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            pos = row.get("position")
            role = row.get("role")
            v = row.get("total_vorp")
            if pos is None or role is None or v is None:
                continue
            try:
                clean[_canonical_group_label(pos, role)] = float(v)
            except (TypeError, ValueError):
                continue
    elif isinstance(raw, dict):
        for k, v in raw.items():
            try:
                clean[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    return clean


def check_input_completeness(artifact, group_totals):
    """Check 0: the inputs themselves are complete. FAIL (fail-closed) on:
    - an artifact with no sources at all (vacuous pass otherwise),
    - a source with zero assignable players,
    - group_totals missing any of the 8 EXPECTED_GROUPS.

    Returns (passed, violations, details).
    """
    violations = []
    details = {"per_source": {}}

    if not artifact:
        violations.append({
            "kind": "empty_artifact",
            "detail": "imputed VORP artifact contains no sources",
        })
        return False, violations, details

    for src_key, players in artifact.items():
        n_assigned = sum(1 for _ in _iter_assigned(players))
        details["per_source"][src_key] = {"assignable_players": n_assigned}
        if n_assigned == 0:
            violations.append({
                "kind": "empty_source",
                "source": src_key,
                "detail": "source has zero assignable players",
            })

    missing_groups = [g for g in EXPECTED_GROUPS if g not in group_totals]
    details["missing_groups"] = missing_groups
    for g in missing_groups:
        violations.append({
            "kind": "missing_group_total",
            "group": g,
            "detail": "JEG-206 group total missing; reconciliation would pass vacuously",
        })

    return (len(violations) == 0), violations, details


def _iter_assigned(players):
    """Yield (player_record, group, imputed_vorp, native, ddf_vorp) for players
    that have a group assignment and a numeric imputed_vorp.

    Players missing any of those fields are skipped (fail-closed: a partial
    record cannot be validated).
    """
    for p in players:
        g = p.get("group")
        iv = p.get("imputed_vorp")
        if g is None or iv is None:
            continue
        try:
            iv_f = float(iv)
        except (TypeError, ValueError):
            continue
        nat = p.get("native")
        try:
            nat_f = float(nat) if nat is not None else None
        except (TypeError, ValueError):
            nat_f = None
        # ddf_rebuilt is the canonical field on the lineage artifact; ddf_vorp
        # is the name used in the JEG-212 brief. Accept either.
        dv = p.get("ddf_rebuilt")
        if dv is None:
            dv = p.get("ddf_vorp")
        try:
            dv_f = float(dv) if dv is not None else None
        except (TypeError, ValueError):
            dv_f = None
        yield p, g, iv_f, nat_f, dv_f


def check_group_total_reconciliation(artifact, group_totals, tolerance):
    """Check 1: sum(imputed_vorp) per group == JEG-206 group total.

    Returns (passed, violations, details).
    """
    violations = []
    details = {
        "tolerance_relative": tolerance,
        "per_source": {},
    }

    for src_key, players in artifact.items():
        group_sums = {}
        for _p, g, iv, _nat, _dv in _iter_assigned(players):
            group_sums[g] = group_sums.get(g, 0.0) + iv

        per_src = {
            "group_sums": {g: round(group_sums.get(g, 0.0), 2) for g in EXPECTED_GROUPS},
            "group_totals": {g: round(float(group_totals.get(g, 0.0)), 2) for g in EXPECTED_GROUPS},
            "matches": {},
            "missing_groups": [],
        }

        for group_label in EXPECTED_GROUPS:
            actual = group_sums.get(group_label, 0.0)
            expected = float(group_totals.get(group_label, 0.0))
            if expected == 0.0 and actual == 0.0:
                per_src["matches"][group_label] = True
                continue
            if group_label not in group_totals:
                per_src["missing_groups"].append(group_label)
                per_src["matches"][group_label] = None
                continue
            denom = abs(expected) if expected != 0.0 else 1.0
            diff_pct = abs(actual - expected) / denom
            match = diff_pct <= tolerance
            per_src["matches"][group_label] = match
            if not match:
                violations.append({
                    "source": src_key,
                    "group": group_label,
                    "actual": round(actual, 2),
                    "expected": round(expected, 2),
                    "diff_relative": round(diff_pct, 4),
                })

        details["per_source"][src_key] = per_src

    return (len(violations) == 0), violations, details


def check_non_negative(artifact):
    """Check 2: all imputed_vorp >= 0. FAIL on negative.

    Returns (passed, violations, details).
    """
    violations = []
    details = {"per_source": {}}
    for src_key, players in artifact.items():
        negatives = []
        for p, _g, iv, _nat, _dv in _iter_assigned(players):
            if iv < 0.0:
                negatives.append({
                    "player_key": p.get("player_key"),
                    "imputed_vorp": round(iv, 2),
                })
        details["per_source"][src_key] = {
            "negative_count": len(negatives),
            "negatives": negatives,
        }
        for n in negatives:
            violations.append({"source": src_key, **n})
    return (len(violations) == 0), violations, details


def check_ordering_sanity(artifact):
    """Check 3: within each group, imputed_vorp ordering matches native ordering.

    Since imputed_vorp = native * alloc_factor (alloc_factor > 0, constant
    per group), the two orderings are mathematically identical. An inversion
    means the alloc factor is wrong, the native column is wrong, or the
    imputed column is wrong -- in any case a real bug worth a warning.

    Returns (passed, warnings, details). This check never fails: it warns.
    """
    warnings = []
    details = {"per_source": {}}
    for src_key, players in artifact.items():
        by_group = {}
        for p, g, iv, nat, _dv in _iter_assigned(players):
            if nat is None:
                continue
            by_group.setdefault(g, []).append((p.get("player_key"), nat, iv))

        inversions = []
        for group_label, members in by_group.items():
            if len(members) < 2:
                continue
            # Sort by imputed_vorp descending; check native is also descending.
            by_imputed = sorted(members, key=lambda x: -x[2])
            natives_in_order = [m[1] for m in by_imputed]
            for i in range(len(natives_in_order) - 1):
                if natives_in_order[i] < natives_in_order[i + 1]:
                    inversions.append({
                        "group": group_label,
                        "higher_imputed_player": by_imputed[i][0],
                        "higher_imputed_value": round(by_imputed[i][2], 2),
                        "lower_imputed_player": by_imputed[i + 1][0],
                        "lower_imputed_value": round(by_imputed[i + 1][2], 2),
                        "inverted_native_value": round(natives_in_order[i], 2),
                        "expected_native_value": round(natives_in_order[i + 1], 2),
                    })

        details["per_source"][src_key] = {
            "inversion_count": len(inversions),
            "inversions": inversions,
        }
        for inv in inversions:
            warnings.append({"source": src_key, **inv})
    return True, warnings, details


def check_divergence_flags(artifact, threshold=DIVERGENCE_THRESHOLD):
    """Check 4: |imputed_vorp - ddf_vorp| / ddf_vorp > 50% flagged for review.

    Flagged players need human eyes; this never fails the gate, it only
    surfaces names for review.

    Returns (passed, flags, details).
    """
    flags = []
    details = {"threshold_relative": threshold,
                "per_source": {}}
    for src_key, players in artifact.items():
        flagged = []
        for p, _g, iv, _nat, dv in _iter_assigned(players):
            if dv is None or dv == 0.0:
                continue
            divergence = abs(iv - dv) / abs(dv)
            if divergence > threshold:
                flagged.append({
                    "player_key": p.get("player_key"),
                    "imputed_vorp": round(iv, 2),
                    "ddf_vorp": round(dv, 2),
                    "divergence_pct": round(divergence * 100.0, 1),
                })
        details["per_source"][src_key] = {
            "flagged_count": len(flagged),
            "flagged": flagged,
        }
        for f in flagged:
            flags.append({"source": src_key, **f})
    return True, flags, details


def run_validation(artifact, group_totals, tolerance=DEFAULT_TOLERANCE):
    """Run all 5 checks. Returns the report dict."""
    c0_pass, c0_viol, c0_det = check_input_completeness(artifact, group_totals)
    c1_pass, c1_viol, c1_det = check_group_total_reconciliation(
        artifact, group_totals, tolerance
    )
    c2_pass, c2_viol, c2_det = check_non_negative(artifact)
    c3_pass, c3_warn, c3_det = check_ordering_sanity(artifact)
    c4_pass, c4_flag, c4_det = check_divergence_flags(artifact)

    fail_checks_passed = c0_pass and c1_pass and c2_pass
    overall_pass = fail_checks_passed  # warn/flag checks never fail

    return {
        "overall_pass": overall_pass,
        "checks": {
            "input_completeness": {
                "passed": c0_pass,
                "severity": "fail",
                "violation_count": len(c0_viol),
                "violations": c0_viol,
                "details": c0_det,
            },
            "group_total_reconciliation": {
                "passed": c1_pass,
                "severity": "fail",
                "violation_count": len(c1_viol),
                "violations": c1_viol,
                "details": c1_det,
            },
            "non_negative": {
                "passed": c2_pass,
                "severity": "fail",
                "violation_count": len(c2_viol),
                "violations": c2_viol,
                "details": c2_det,
            },
            "ordering_sanity": {
                "passed": c3_pass,
                "severity": "warn",
                "warning_count": len(c3_warn),
                "warnings": c3_warn,
                "details": c3_det,
            },
            "divergence_flags": {
                "passed": c4_pass,
                "severity": "flag",
                "flag_count": len(c4_flag),
                "flags": c4_flag,
                "details": c4_det,
            },
        },
        "summary": {
            "total_checks": 5,
            "fail_checks_passed": c0_pass and c1_pass and c2_pass,
            "warn_checks_clean": len(c3_warn) == 0,
            "flag_checks_clean": len(c4_flag) == 0,
            "total_violations": len(c0_viol) + len(c1_viol) + len(c2_viol),
            "total_warnings": len(c3_warn),
            "total_flags": len(c4_flag),
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="JEG-212: Validate imputed VORPs before they go live."
    )
    parser.add_argument(
        "--imputed-artifact", required=True,
        help="Path to imputed VORP artifact JSON"
    )
    parser.add_argument(
        "--group-totals", required=True,
        help="Path to JEG-206 group totals JSON"
    )
    parser.add_argument(
        "--tolerance", type=float, default=DEFAULT_TOLERANCE,
        help="Relative tolerance for group-total reconciliation (default 0.01)"
    )
    parser.add_argument(
        "--output",
        help="Path to write JSON report (default stdout)"
    )
    args = parser.parse_args()

    artifact = load_imputed_artifact(args.imputed_artifact)
    group_totals = load_group_totals(args.group_totals)

    report = run_validation(artifact, group_totals, tolerance=args.tolerance)

    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w") as f:
            f.write(rendered + "\n")
    else:
        print(rendered)

    sys.exit(0 if report["overall_pass"] else 1)


if __name__ == "__main__":
    main()