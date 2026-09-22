#!/usr/bin/env python3
"""Reference compute: isotonic reindex + fixed-pie indexing for a candidate comparison section.

Pipeline stage: candidate comparison section (native values) -> reference compute.

Two steps, run per (combo, position):

1. ISOTONIC REINDEX. The source's native published values are translated onto
   the chart's canonical scale with a per-position non-decreasing (isotonic)
   fit, preserving rank order and within-position relative shape. The anchor is
   the fixture's ESPN leg for the same combo -- the repo-owned equivalent of
   the retired Monday rail. Fit needs >= 10 anchor-matched pairs per position;
   fewer fails closed (no pooled cross-position fit, ever).

2. FIXED-PIE INDEXING. After translation, each combo's total over its OWN
   priced set is compared to the anchor's total over that SAME set:
   factor = anchor_total(priced) / reindexed_total(priced). Recorded as
   index_total {target_total, pre_total, factor, n_priced} per position,
   mirroring the fixture shape. The dashboard applies the factor (or checks
   the pie) at display; reindexed values themselves are untouched.

Everything else is fail-closed: unknown combos, unknown positions (K/DST),
non-numeric values, and unmatched anchor pairs go to review, never guessed.

Reads:
  data/fixtures/current/comparison-sources-data.json   (anchor: ESPN leg)
  data/fixtures/current/players.json                   (position per slug)

Writes (under output/ only, never data/):
  output/comparison-reference/<source>-<asof>-reindexed.json
  (schema: trade-value-comparison-section-reindexed-v1)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from isotonic import isotonic_fit, isotonic_predict

REPO = Path(__file__).resolve().parent.parent
SCHEMA = "trade-value-comparison-section-reindexed-v1"
POSITIONS = ("QB", "RB", "WR", "TE")
MIN_FIT_PAIRS = 10


def _load_json(path):
    with open(path) as fh:
        return json.load(fh)


def _round1(x):
    return round(float(x), 1)


def reindex_section(candidate_path, fixture_path=None, players_path=None):
    """Translate one candidate section to the anchor scale.

    Returns (reindexed_section, review_rows). review_rows is a list of dicts
    {player_key, slug, combo, reason}.
    """
    cand = _load_json(candidate_path)
    # Accepts the candidate-section artifact (current builder shape) and the
    # legacy source-reference shape the stage was first written against.
    if cand.get("schema") not in (
        "trade-value-comparison-section-candidate-v1",
        "trade-value-source-reference-v1",
    ):
        raise SystemExit(f"reindex: unsupported candidate schema {cand.get('schema')}")
    fixture_path = fixture_path or REPO / "data/fixtures/current/comparison-sources-data.json"
    players_path = players_path or REPO / "data/fixtures/current/players.json"

    fixture = _load_json(fixture_path)
    players = _load_json(players_path)
    # Identity is resolved fail-closed: slug -> numeric player_key (from the
    # candidate's own player_keys, pinned at collection) -> position from
    # players.json. Never by name normalization.
    pos_by_key = {p["player_key"]: p["pos"] for p in players["players"]}

    espn = fixture["sources"].get("espn", {})
    espn_combos = espn.get("combos", {})
    source = cand.get("source_key") or cand.get("section_key")
    if not source:
        raise SystemExit("reindex: candidate is missing source_key/section_key")
    review = []
    out_combos = {}

    for combo_name, combo in cand.get("combos", {}).items():
        espn_combo = espn_combos.get(combo_name)
        if espn_combo is None:
            raise SystemExit(
                f"reindex: combo {combo_name!r} has no anchor in the ESPN leg -- refusing to guess"
            )
        anchor = espn_combo.get("values", {})
        native = combo.get("native", {})
        key_by_slug = combo.get("player_keys", {})
        pos_by_slug = {}
        for slug, key in key_by_slug.items():
            pos = pos_by_key.get(key)
            if pos is None:
                review.append(
                    {"player_key": key, "slug": slug, "combo": combo_name,
                     "reason": "player_key not in players.json -- identity unresolvable, skipped"})
            else:
                pos_by_slug[slug] = pos

        out_combo = {"reindexed": {}, "native": dict(native), "fit": {}, "n": {},
                       "index_total": {},
                       "player_keys": {s: key_by_slug.get(s) for s in native}}
        for pos in POSITIONS:
            pairs = []
            priced = []
            for slug, val in native.items():
                p = pos_by_slug.get(slug)
                if p != pos:
                    continue
                if slug not in anchor:
                    review.append(
                        {"player_key": combo.get("player_keys", {}).get(slug),
                         "slug": slug, "combo": combo_name,
                         "reason": "no anchor value for this position -- skipped, never imputed"}
                    )
                    continue
                try:
                    native_v = float(val)
                    anchor_v = float(anchor[slug])
                except (TypeError, ValueError):
                    review.append(
                        {"player_key": combo.get("player_keys", {}).get(slug),
                         "slug": slug, "combo": combo_name,
                         "reason": f"non-numeric value {val!r} -- skipped, never coerced"})
                    continue
                pairs.append((native_v, anchor_v))
                priced.append(slug)
            if len(pairs) < MIN_FIT_PAIRS:
                raise SystemExit(
                    f"reindex: {source}/{combo_name}/{pos} has {len(pairs)} anchor pairs "
                    f"(< {MIN_FIT_PAIRS}) -- failing closed, no pooled fit"
                )
            xs = [x for x, _ in pairs]
            ys = [y for _, y in pairs]
            fit_x, fit_y = isotonic_fit(xs, ys)
            reindexed = {slug: _round1(isotonic_predict(fit_x, fit_y, float(native[slug])))
                         for slug in priced}
            pre_total = sum(reindexed.values())
            target_total = sum(float(anchor[s]) for s in priced)
            if pre_total <= 0:
                raise SystemExit(
                    f"reindex: {source}/{combo_name}/{pos} pre_total={pre_total} -- cannot index the pie"
                )
            factor = target_total / pre_total
            # The pie is fixed: the stored reindexed values are the
            # isotonic outputs SCALED by the factor, so they sum to
            # target_total (within rounding). Recording the factor without
            # applying it silently breaks the fixed-pie invariant.
            scaled = {slug: _round1(val * factor)
                      for slug, val in reindexed.items()}
            out_combo["reindexed"].update(scaled)
            out_combo["fit"][pos] = {
                "method": "isotonic_pava",
                "anchor": "espn_leg",
                "n_pairs": len(pairs),
                "native_min": _round1(min(xs)),
                "native_max": _round1(max(xs)),
            }
            out_combo["n"][pos] = len(priced)
            out_combo["index_total"][pos] = {
                "target_total": _round1(target_total),
                "pre_total": _round1(pre_total),
                "factor": round(factor, 6),
                "n_priced": len(priced),
            }
        out_combos[combo_name] = out_combo

    # Anything the candidate priced outside QB/RB/WR/TE is not indexed.
    for combo_name, combo in cand.get("combos", {}).items():
        key_by_slug = combo.get("player_keys", {})
        pos_by_slug = {s: pos_by_key[k] for s, k in key_by_slug.items() if k in pos_by_key}
        for slug in combo.get("native", {}):
            if pos_by_slug.get(slug) not in POSITIONS:
                review.append(
                    {"player_key": key_by_slug.get(slug),
                     "slug": slug, "combo": combo_name,
                     "reason": f"position {pos_by_slug.get(slug)} not indexed -- skipped"}
                )

    section = {
        "schema": SCHEMA,
        "source_key": source,
        "stage": "reference_compute",
        "anchor": "espn_leg",
        "asof": cand.get("asof"),
        "reindex_status": "complete",
        "combos": out_combos,
        "review_rows": review,
        "candidate_source_file": str(candidate_path),
    }
    return section, review


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reindex a candidate comparison section.")
    ap.add_argument("candidate", help="candidate section JSON (trade-value-source-reference-v1)")
    ap.add_argument("--out", default=None,
                    help="output path (default output/comparison-reference/<source>-<date>-reindexed.json)")
    args = ap.parse_args(argv)

    section, review = reindex_section(args.candidate)
    out = Path(args.out) if args.out else (
        REPO / "output" / "comparison-reference"
        / f"{section['source_key']}-{date.today().isoformat()}-reindexed.json")
    if out.resolve().is_relative_to((REPO / "data").resolve()):
        raise SystemExit("refusing to write under data/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(section, indent=1) + "\n")
    print(f"reindexed section -> {out}")
    print(f"review rows: {len(review)}")
    for row in review[:20]:
        print("  review:", row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
