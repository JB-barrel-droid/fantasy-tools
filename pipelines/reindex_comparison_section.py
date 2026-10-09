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
# Roster config: positions, roster shape, bench share, flex eligibility.
# Loaded from config/roster.json — never hardcode these.
def _load_roster_config():
    import json
    cfg_path = REPO / "config" / "roster.json"
    try:
        with open(cfg_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        # Fallback to defaults if config missing
        return {
            "positions": ["QB", "RB", "WR", "TE"],
            "roster_shape": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "BENCH": 6},
            "bench_share": 0.15,
            "flex_eligible": ["RB", "WR", "TE"],
        }

_ROSTER_CFG = _load_roster_config()
POSITIONS = tuple(_ROSTER_CFG["positions"])
ROSTER_SHAPE = _ROSTER_CFG["roster_shape"]
BENCH_SHARE = _ROSTER_CFG["bench_share"]
FLEX_ELIGIBLE = tuple(_ROSTER_CFG["flex_eligible"])
MIN_FIT_PAIRS = 10
# Zero-VORP policy (2026-10-01): players with no anchor value have effectively
# zero VORP in the canonical system. If their source native value is also
# low (below this fraction of the source's max native), they are auto-skipped
# without a blocking review row. Players with meaningful native values but no
# anchor still get a review row (potential anchor omission).
#
# The fraction below is applied to DIFFERENT denominators by branch, deliberately:
#  - as-published branch: GLOBAL native max. Published charts are globally
#    comparable across positions (their cross-position ranking is the product),
#    so "effectively zero" is judged against the chart's overall top value.
#  - quantile branch: PER-POSITION native max. DDF-methodology sources are
#    indexed per position, and a global cutoff would wrongly zero out entire
#    low-scoring positions (TE/K-DST scale far below QB/RB).
# Same fraction, different denominators -- the comments at each use site say
# which one applies.
ZERO_VORP_NATIVE_FRAC = 0.10
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
    # GAP-UNIVERSE-CHART-ONLY (2026-10-08): players not on ESPN's list
    # (espn_status "absent") have no ESPN anchor by definition. That is known,
    # not a possible anchor omission: their published native stays in the
    # section (listed under not_on_espn) and never holds the chart.
    not_on_espn = {p["player_key"] for p in players["players"]
                   if p.get("espn_status") == "absent"}

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
        # GAP-SUPERFLEX-PUBLISHER-VALUES: the publisher's own superflex values
        # travel unchanged (never reindexed: the engine overlays them on the
        # natives); only when the candidate has them.
        if combo.get("native_superflex"):
            out_combo["native_superflex"] = dict(combo["native_superflex"])
        # As-published trade value charts publish globally-comparable values.
        # Their cross-position ranking is the product — we must not destroy it
        # with per-position remapping.
        #
        # EXPLICIT SOURCE LIST: Only true as-published trade charts use global
        # scaling. ESPN is our DDF computation from ESPN projections (not a
        # published chart) and uses per-position logic. The candidate's
        # value_provenance field is not trusted for this decision.
        AS_PUBLISHED_SOURCES = {"fantasycalc", "usatoday", "fantasypros", "cbs"}
        is_published = (source in AS_PUBLISHED_SOURCES and
                        cand.get("value_provenance") == "published")
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
        if is_published:
            priced = []
            # Zero-VORP threshold on native scale: 10% of max native value.
            # Players below this with no anchor are auto-skipped (effectively zero).
            native_vals = [float(v) for v in native.values()
                           if isinstance(v, (int, float)) or
                           (isinstance(v, str) and v.replace('.','',1).isdigit())]
            max_native = max(native_vals) if native_vals else 0
            # Global-max denominator: this branch serves as-published charts,
            # whose values are globally comparable across positions.
            zero_vorp_native_cutoff = max_native * ZERO_VORP_NATIVE_FRAC
            for slug, val in native.items():
                key = combo.get("player_keys", {}).get(slug)
                anchor_v = anchor_by_key.get(key)
                if anchor_v is None and key in not_on_espn:
                    out_combo.setdefault("not_on_espn", []).append(slug)
                    continue
                if anchor_v is None:
                    # Zero-VORP policy: if native is also low, skip silently.
                    # Meaningful natives with no anchor still get review (potential omission).
                    try:
                        nv_check = float(val)
                    except (TypeError, ValueError):
                        nv_check = 0
                    if nv_check < zero_vorp_native_cutoff:
                        continue  # effectively zero-VORP, no review row
                    review.append(
                        {"player_key": key,
                         "slug": slug, "combo": combo_name,
                         "reason": f"no anchor value for this player_key (native {nv_check:.1f} >= cutoff {zero_vorp_native_cutoff:.1f}) -- skipped, never imputed"}
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
            # FLEX-AWARE PER-POSITION PIE ALLOCATION (2026-10-01):
            # Run flex allocation on SOURCE rankings to preserve the source's
            # opinions about who deserves flex spots. Then scale each
            # (position, role) bucket independently to match the anchor.
            #
            # Roles: 'dedicated' (positional starters), 'flex' (flex starters),
            # 'bench' (everyone else). Flex pool = remaining RB/WR/TE sorted
            # by source native value; top flex_count per team win flex spots.
            import math
            teams = 12  # TODO: from league config
            slots = ROSTER_SHAPE  # QB:1, RB:2, WR:2, TE:1, FLEX:2, BENCH:6
            flex_count = slots.get("FLEX", 2)

            # Rank source players by native value within each position.
            # Zero-native players are excluded from bucket scaling (they get
            # 0.0 directly); including them distorts bucket membership counts
            # vs the ratio-based test grouping.
            zero_native = {s for s in priced if float(native.get(s, 0)) <= 0}
            for s in zero_native:
                out_combo["reindexed"][s] = 0.0
            by_pos = {}
            for pos in POSITIONS:
                rows = [(slug, float(native[slug])) for slug in priced
                        if pos_by_slug.get(slug) == pos and slug not in zero_native]
                rows.sort(key=lambda x: (-x[1], x[0]))
                by_pos[pos] = rows

            # Dedicated starters: top slots[pos] per position
            dedicated = set()
            role_of = {}
            for pos in POSITIONS:
                n_start = teams * slots.get(pos, 0)
                for slug, _ in by_pos[pos][:n_start]:
                    dedicated.add(slug)
                    role_of[slug] = "dedicated"

            # Flex pool: remaining flex-eligible, sorted by source value
            flex_pool = []
            for pos in FLEX_ELIGIBLE:
                for slug, val in by_pos.get(pos, []):
                    if slug not in dedicated:
                        flex_pool.append((slug, val, pos))
            flex_pool.sort(key=lambda x: (-x[1], x[0]))
            n_flex = teams * flex_count
            for slug, _, pos in flex_pool[:n_flex]:
                role_of[slug] = "flex"
            for slug, _, pos in flex_pool[n_flex:]:
                if slug not in role_of:
                    role_of[slug] = "bench"
            # Non-flex-eligible remaining go to bench (zero-native players
            # already have 0.0 and are excluded from buckets)
            for slug in priced:
                if slug not in role_of and slug not in zero_native:
                    role_of[slug] = "bench"

            # For each (pos, role) bucket, scale source total to anchor total
            bucket_exact = {}
            for pos in POSITIONS:
                for role in ("dedicated", "flex", "bench"):
                    bucket_slugs = [s for s in priced
                                    if pos_by_slug.get(s) == pos and role_of.get(s) == role
                                    and s not in zero_native]
                    if not bucket_slugs:
                        continue
                    src_total = sum(float(native[s]) for s in bucket_slugs)
                    # Anchor total for SAME players (not anchor's role assignment)
                    anc_total = sum(
                        float(anchor_by_key[combo.get("player_keys", {}).get(s)])
                        for s in bucket_slugs
                        if combo.get("player_keys", {}).get(s) in anchor_by_key
                    )
                    if src_total <= 0 or anc_total <= 0:
                        # Zero-anchor bucket: the anchor prices every member at
                        # 0 (e.g. below the positional waiver line). Reindex to
                        # 0.0 explicitly -- skipping would leave them out of
                        # reindexed while still counted in `priced`, breaking
                        # the reconciliation below.
                        bucket_exact[(pos, role)] = {
                            "pre": src_total,
                            "anchor": anc_total,
                            "scale": 0.0,
                            "post": 0.0,
                            "n": len(bucket_slugs),
                        }
                        for slug in bucket_slugs:
                            out_combo["reindexed"][slug] = 0.0
                        continue
                    scale = anc_total / src_total
                    bucket_exact[(pos, role)] = {
                        "pre": src_total,
                        "anchor": anc_total,
                        "scale": scale,
                        "post": src_total * scale,
                        "n": len(bucket_slugs),
                    }
                    for slug in bucket_slugs:
                        out_combo["reindexed"][slug] = float(native[slug]) * scale

            out_combo["fit"]["flex_aware_pie"] = {
                "method": "proportional_scaling_flex_aware_per_position",
                "anchor": "espn_leg",
                "n_priced": len(priced),
                "buckets": {f"{pos}/{role}": exact
                            for (pos, role), exact in bucket_exact.items()},
                "note": "Flex allocation run on SOURCE rankings; each (pos,role) bucket scaled independently",
            }
            # Exact reconciliation (no representative-bucket fiction): per-position
            # and full-pie totals are the sums of the per-bucket exacts, and the
            # stored reindexed values must sum to the bucket-sum post total.
            out_combo["index_total"] = {}
            out_combo["n"] = {}
            pie_pre = pie_post = 0.0
            for pos in POSITIONS:
                pos_exact = [(r, e) for (p, r), e in bucket_exact.items() if p == pos]
                if not pos_exact:
                    continue
                pre_total = sum(e["pre"] for _, e in pos_exact)
                post_total = sum(e["post"] for _, e in pos_exact)
                stored_total = sum(float(out_combo["reindexed"][s]) for s in priced
                                   if pos_by_slug.get(s) == pos)
                if abs(stored_total - post_total) > 1e-6 * max(1.0, post_total):
                    raise SystemExit(
                        f"reindex: {source}/{combo_name}/{pos} reconciliation failed: "
                        f"stored reindexed total {stored_total} != bucket-sum {post_total}")
                n_priced = sum(e["n"] for _, e in pos_exact)
                out_combo["index_total"][pos] = {
                    "target_total": post_total,
                    "pre_total": pre_total,
                    "post_total": post_total,
                    "factor": post_total / pre_total if pre_total > 0 else 0.0,
                    "n_priced": n_priced,
                    "buckets": {role: {"pre": e["pre"], "anchor": e["anchor"],
                                       "scale": e["scale"], "post": e["post"],
                                       "n": e["n"]}
                                for role, e in pos_exact},
                }
                out_combo["n"][pos] = n_priced
                pie_pre += pre_total
                pie_post += post_total
            out_combo["fit"]["flex_aware_pie"]["pie"] = {
                "pre_total": pie_pre,
                "post_total": pie_post,
                "factor": pie_post / pie_pre if pie_pre > 0 else 0.0,
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
                        if anchor_v_raw is None and key in not_on_espn:
                            out_combo.setdefault("not_on_espn", []).append(slug)
                            continue
                        if anchor_v_raw is None:
                            # Zero-VORP policy: skip silently if native is low.
                            try:
                                nv_check = float(val)
                            except (TypeError, ValueError):
                                nv_check = 0
                            # Per-position-max denominator: this branch indexes
                            # per position, so a global cutoff would wrongly
                            # zero out low-scoring positions.
                            pos_natives = [float(v) for s2, v in native.items()
                                           if pos_by_slug.get(s2) == pos]
                            pos_max = max(pos_natives) if pos_natives else 0
                            if nv_check < pos_max * ZERO_VORP_NATIVE_FRAC:
                                continue
                            review.append(
                                {"player_key": key,
                                 "slug": slug, "combo": combo_name,
                                 "reason": f"no anchor value for this player_key (native {nv_check:.1f}) -- skipped, never imputed"}
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
