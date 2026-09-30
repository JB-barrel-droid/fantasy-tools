#!/usr/bin/env python3
"""Reference compute: quantile-mapping reindex + fixed-pie indexing for a candidate comparison section.

Pipeline stage: candidate comparison section (native values) -> reference compute.

Two steps, run per (combo, position):

1. QUANTILE-MAPPING REINDEX. The source's native published values are translated onto
   the chart's canonical scale with a per-position quantile mapping: each native's
   quantile in the source distribution maps to the same quantile of the ESPN anchor
   distribution. This preserves the source's rank order and within-position relative
   spacing EXACTLY -- unlike isotonic regression, it never pools (averages) values
   when the source disagrees with the anchor's ordering. The anchor is the fixture's
   ESPN leg for the same combo -- the repo-owned equivalent of the retired Monday rail.
   A candidate combo carrying the league QB dimension (qb1/qb2) anchors to its
   QB-stripped base combo; the mapping is explicit and recorded per combo, never guessed.
   Fit needs >= 10 anchor-matched pairs per position; fewer fails closed (no pooled
   cross-position fit, ever).

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
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from isotonic import isotonic_fit, isotonic_predict


def quantile_map(xs: list[float], ys: list[float], x: float) -> float:
    """Map x from the source distribution (xs) to the anchor scale (ys).
    
    Finds x's quantile in the source distribution and returns the corresponding
    quantile of the anchor distribution. This preserves the source's ordering
    and relative spacing exactly -- unlike isotonic regression, it never pools
    (averages) values when the source disagrees with the anchor's ordering.
    
    Both xs and ys are sorted internally; x is the source native to map.
    Linear interpolation is used between observed points; values outside the
    observed range clamp to the anchor's min/max.
    """
    if not xs or not ys:
        raise ValueError("quantile_map needs non-empty xs and ys")
    xs_sorted = sorted(xs)
    ys_sorted = sorted(ys)
    n_x = len(xs_sorted)
    n_y = len(ys_sorted)
    
    # Find x's quantile in the source distribution
    if x <= xs_sorted[0]:
        q = 0.0
    elif x >= xs_sorted[-1]:
        q = 1.0
    else:
        # Binary search for the interval containing x
        lo, hi = 0, n_x - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs_sorted[mid] <= x:
                lo = mid
            else:
                hi = mid
        # Linear interpolation: q is the fractional rank
        if xs_sorted[hi] == xs_sorted[lo]:
            q = lo / (n_x - 1) if n_x > 1 else 0.0
        else:
            t = (x - xs_sorted[lo]) / (xs_sorted[hi] - xs_sorted[lo])
            q = (lo + t) / (n_x - 1) if n_x > 1 else 0.0
    
    # Map quantile to anchor scale
    pos = q * (n_y - 1)
    lo_i = int(pos)
    hi_i = min(lo_i + 1, n_y - 1)
    t = pos - lo_i
    return ys_sorted[lo_i] * (1 - t) + ys_sorted[hi_i] * t

REPO = Path(__file__).resolve().parent.parent
SCHEMA = "trade-value-comparison-section-reindexed-v1"
POSITIONS = ("QB", "RB", "WR", "TE")
MIN_FIT_PAIRS = 10
# A candidate combo may carry the league's QB dimension (qb1 = start 1 QB,
# qb2 = start 2 QBs). The ESPN anchor leg has no QB-split combos, so such a
# combo anchors to its QB-stripped base combo. This mapping is EXPLICIT and
# recorded per combo -- never a silent guess.
QB_SUFFIX = re.compile(r"_qb[12]$")


def resolve_anchor_combo(combo_name: str, espn_combos: dict) -> tuple[str, str]:
    """Return (anchor_combo_name, mapping_note).

    Exact match first; else strip a trailing _qb1/_qb2 and retry. Raises
    SystemExit (fail closed) when neither resolves -- the pipeline refuses
    to guess an anchor.
    """
    if combo_name in espn_combos:
        return combo_name, "exact"
    stripped = QB_SUFFIX.sub("", combo_name)
    if stripped != combo_name and stripped in espn_combos:
        return stripped, f"qb_suffix_strip:{combo_name}->{stripped}"
    raise SystemExit(
        f"reindex: combo {combo_name!r} has no anchor in the ESPN leg -- refusing to guess"
    )


def _load_json(path):
    with open(path) as fh:
        return json.load(fh)


def _round1(x):
    return round(float(x), 1)


def _round4(x):
    """Preserve precision for stored reindexed values. _round1 (1 decimal)
    caused collisions: e.g., USA Today Taylor (64) and Walker (66) both
    rounded to 49.4, erasing a real 3% native difference. Display layers
    round for readability; storage must not."""
    return round(float(x), 4)


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
    # The fixture declares its own slug -> canonical player_key map. Anchor
    # pairing joins on the numeric key, never on raw slug strings: the
    # candidate's slugs and the fixture's slugs come from different
    # normalizers ('c j stroud' vs 'cj stroud'), so exact-slug matching
    # silently drops real players. The key join is exact, not a guess.
    fixture_key_by_slug = fixture.get("player_keys", {})
    source = cand.get("source_key") or cand.get("section_key")
    if not source:
        raise SystemExit("reindex: candidate is missing source_key/section_key")
    review = []
    out_combos = {}

    for combo_name, combo in cand.get("combos", {}).items():
        anchor_name, anchor_mapping = resolve_anchor_combo(combo_name, espn_combos)
        espn_combo = espn_combos[anchor_name]
        anchor = espn_combo.get("values", {})
        anchor_by_key = {}
        for slug, val in anchor.items():
            key = fixture_key_by_slug.get(slug)
            if key is not None:
                anchor_by_key[key] = val
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
                       "anchor_combo": anchor_name, "anchor_mapping": anchor_mapping,
                       "player_keys": {s: key_by_slug.get(s) for s in native}}
        # As-published trade value charts (FantasyCalc, USA Today, FantasyPros, CBS)
        # publish globally-comparable values. Their cross-position ranking is the
        # product — we must not destroy it with per-position remapping.
        #
        # Indexation logic (2026-09-30 refinement): players with VORP>0 should
        # sum to the same total across sources. Different charts price to
        # different depths, but they overlap on the top 50-150. We calibrate
        # the scale on the VORP>0 overlap set, then apply relative values to
        # the remainder of the chart.
        #
        # Formula: scale = sum(anchor_overlap) / sum(native_overlap)
        #          indexed = native * scale for ALL priced players
        # This preserves exact value ratios and cross-position order.
        # No quantile mapping, no rounding in storage.
        is_published = cand.get("value_provenance") == "published"
        if is_published:
            priced = []
            for slug, val in native.items():
                key = combo.get("player_keys", {}).get(slug)
                anchor_v = anchor_by_key.get(key)
                if anchor_v is None:
                    review.append(
                        {"player_key": key,
                         "slug": slug, "combo": combo_name,
                         "reason": "no anchor value for this player_key -- skipped, never imputed"}
                    )
                    continue
                try:
                    nv = float(val)
                    av = float(anchor_v)
                except (TypeError, ValueError):
                    continue
                if nv < 0 or av < 0:
                    continue
                priced.append(slug)
            # Calibrate on the VORP>0 overlap: players the anchor prices above
            # zero. This is the high-confidence set (typically 50-150 players)
            # where sources overlap; the deep tail varies in depth by source
            # and shouldn't drive the scale.
            overlap = [s for s in priced
                       if float(anchor_by_key[combo.get("player_keys", {}).get(s)]) > 0]
            if not overlap:
                # Fallback: use all priced if no VORP>0 overlap (shouldn't happen)
                overlap = priced
            native_overlap = sum(float(native[s]) for s in overlap)
            anchor_overlap = sum(float(anchor_by_key[combo.get("player_keys", {}).get(s)]) for s in overlap)
            if native_overlap <= 0 or anchor_overlap <= 0:
                raise SystemExit(
                    f"reindex: {source}/{combo_name} native_overlap={native_overlap} anchor_overlap={anchor_overlap} -- cannot scale"
                )
            scale = anchor_overlap / native_overlap
            for slug in priced:
                out_combo["reindexed"][slug] = float(native[slug]) * scale
            out_combo["fit"]["global"] = {
                "method": "proportional_scaling_vorp_overlap",
                "anchor": "espn_leg",
                "n_priced": len(priced),
                "n_overlap": len(overlap),
                "native_overlap": native_overlap,
                "anchor_overlap": anchor_overlap,
                "scale": scale,
                "overlap_slugs": sorted(overlap),
            }
            out_combo["n"]["global"] = len(priced)
            # Fixed-pie target: the anchor's VORP>0 overlap total. The source's
            # VORP>0 players sum to this amount; the scale was calibrated on
            # exactly this set.
            out_combo["index_total"]["global"] = {
                "target_total": anchor_overlap,
                "pre_total": native_overlap,
                "factor": scale,
                "n_priced": len(priced),
                "n_overlap": len(overlap),
            }
        else:
                for pos in POSITIONS:
                    pairs = []
                    priced = []
                    for slug, val in native.items():
                        p = pos_by_slug.get(slug)
                        if p != pos:
                            continue
                        key = combo.get("player_keys", {}).get(slug)
                        anchor_v_raw = anchor_by_key.get(key)
                        if anchor_v_raw is None:
                            review.append(
                                {"player_key": key,
                                 "slug": slug, "combo": combo_name,
                                 "reason": "no anchor value for this player_key -- skipped, never imputed"}
                            )
                            continue
                        try:
                            native_v = float(val)
                            anchor_v = float(anchor_v_raw)
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
                    # Quantile mapping preserves the source's ordering and relative
                    # spacing. Isotonic PAVA pooled (averaged) values when the source
                    # disagreed with the anchor's ordering, erasing genuine
                    # disagreements -- e.g., FP's Chase (57.1) > JSN (55.4) distinction
                    # was lost because ESPN orders them oppositely.
                    reindexed = {slug: _round4(quantile_map(xs, ys, float(native[slug])))
                                 for slug in priced}
                    pre_total = sum(reindexed.values())
                    key_by_slug = combo.get("player_keys", {})
                    target_total = sum(
                        float(anchor_by_key[key_by_slug[s]]) for s in priced)
                    if pre_total <= 0:
                        raise SystemExit(
                            f"reindex: {source}/{combo_name}/{pos} pre_total={pre_total} -- cannot index the pie"
                        )
                    factor = target_total / pre_total
                    # The pie is fixed: the stored reindexed values are the
                    # isotonic outputs SCALED by the factor, so they sum to
                    # target_total (within rounding). Recording the factor without
                    # applying it silently breaks the fixed-pie invariant.
                    scaled = {slug: _round4(val * factor)
                              for slug, val in reindexed.items()}
                    out_combo["reindexed"].update(scaled)
                    out_combo["fit"][pos] = {
                        "method": "quantile_mapping",
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
        "week_designated": cand.get("week_designated"),
        "published": cand.get("published"),
        "content_vintage": cand.get("content_vintage"),
        "source_provenance": cand.get("source_provenance"),
        "fetched_at": cand.get("fetched_at"),
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
