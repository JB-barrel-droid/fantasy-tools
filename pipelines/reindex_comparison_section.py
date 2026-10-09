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

Published trade charts (fantasycalc, usatoday, fantasypros, cbs) skip both
steps above: they are indexed with ONE factor per combo
(order_preserving_rescale, JEG-482), so the chart's own ranking is kept
exactly, across and within positions.

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


RESCALE_METHOD = "order_preserving_rescale"
RESCALE_FIT_KEY = "order_preserving_rescale"  # fit[...] key the published branch writes


def published_priced(native, key_by_slug, anchor_by_key, combo_name, not_on_espn=frozenset()):
    """The players a published chart x combo is indexed over, its review rows,
    and the chart-only players among them.

    A player is priced when the anchor prices it (numeric key join) and both
    values are numeric and non-negative. A player not on ESPN's list
    (players.json espn_status "absent", GAP-UNIVERSE-CHART-ONLY / JEG-486) is
    priced with anchor 0.0, like a player ESPN lists at 0: he gets the chart's
    one factor like everyone else and is listed as not_on_espn. Any other
    player the anchor does not price is skipped: silently when its native is
    below ZERO_VORP_NATIVE_FRAC of the chart's top native (global max:
    published charts are globally comparable across positions), else with a
    review row (potential anchor omission).

    Returns (priced, review, anchor_of, chart_only) where anchor_of is
    {slug: anchor value} for every priced slug.
    """
    review = []
    priced = []
    anchor_of = {}
    chart_only = []
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
        key = key_by_slug.get(slug)
        anchor_v = anchor_by_key.get(key)
        if anchor_v is None and key in not_on_espn:
            chart_only.append(slug)
            anchor_v = 0.0
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
        anchor_of[slug] = av
    return priced, review, anchor_of, chart_only


def order_preserving_rescale(native, priced, anchor_of, pos_by_slug, uncalibrated=()):
    """Index one published chart x combo with ONE factor (JEG-482).

    native: {slug: native value}; priced: slugs to index; anchor_of: {slug:
    anchor value} for every priced slug; pos_by_slug: {slug: position}. Only
    QB/RB/WR/TE are indexed (others are review rows, as before).

    factor = anchor_total(priced) / native_total(priced); every priced player
    is native * factor, stored unrounded. A positive factor applied to every
    player cannot reorder two of them, so the chart's own ranking survives
    exactly (pipelines/check_rank_guard.py holds every saved combo to it).

    index_total[pos]: target_total = the anchor's total over the chart's
    players at that position (the pie the *_adjusted series is rescaled to),
    pre_total = the chart's native total there, post_total = the stored
    indexed total there (not equal to target_total: the chart keeps its own
    split between positions), factor = the chart's single factor. Over the
    calibrated players the chart's total is the anchor's.

    uncalibrated: slugs indexed with the factor but left out of it -- the
    chart-only players (not on ESPN's list, JEG-486), whom the anchor does not
    price at all (the browser's live anchor has no entry for them either, so
    the browser and the pipeline measure the factor on the same players).

    Returns None when either total is not positive.
    """
    slugs = [s for s in priced if pos_by_slug.get(s) in POSITIONS]
    skip = set(uncalibrated)
    calib = [s for s in slugs if s not in skip]
    native_total = sum(float(native[s]) for s in calib)
    anchor_total = sum(max(0.0, float(anchor_of[s])) for s in calib)
    if native_total <= 0 or anchor_total <= 0:
        return None
    factor = anchor_total / native_total
    reindexed = {s: float(native[s]) * factor for s in slugs}
    index_total = {}
    for pos in POSITIONS:
        at = [s for s in slugs if pos_by_slug.get(s) == pos]
        if not at:
            continue
        index_total[pos] = {
            "target_total": sum(max(0.0, float(anchor_of[s])) for s in at),
            "pre_total": sum(float(native[s]) for s in at),
            "post_total": sum(reindexed[s] for s in at),
            "factor": factor,
            "n_priced": len(at),
        }
    fit = {
        "method": RESCALE_METHOD,
        "anchor": "espn_leg",
        "factor": factor,
        "native_total": native_total,
        "anchor_total": anchor_total,
        "n_priced": len(slugs),
        "n_uncalibrated": len(slugs) - len(calib),
        "note": ("Indexed = native x one factor per chart and combo (JEG-482); "
                 "the chart's own order is kept across and within positions."),
    }
    return {"reindexed": reindexed, "index_total": index_total, "fit": fit}


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
    # GAP-UNIVERSE-CHART-ONLY (JEG-486): players not on ESPN's list
    # (espn_status "absent") have no ESPN anchor by definition. That is known,
    # not a possible anchor omission: they never hold the chart and are listed
    # under not_on_espn. A published chart indexes them with its one factor.
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
        # INDEXED = ONE ORDER-PRESERVING RESCALE (JEG-482). methodology.md,
        # The Three Views #3: "the original published trade charts are indexed
        # to match the value range of the other charts". One factor per chart
        # x combo, so the chart keeps its own ranking across AND within
        # positions (Jeremy, 2026-10-08: "There shouldn't be some secondary
        # correction layer"). Per-position and starter/bench repricing belongs
        # only to the VORP vs waivers and Adjusted views.
        #
        #   factor  = anchor_total(priced) / native_total(priced)
        #   indexed = native * factor            (every priced player)
        #
        # so the chart's pie over the players it prices equals the anchor's
        # over the same players. Removed: the per-(position, role) bucket
        # scaling of 2026-10-01 (d4629423 per-position pie, 6a824749
        # flex-aware buckets), which scaled each bucket to the anchor's total
        # for it and so reordered players across positions and across the
        # starter / flex / bench boundaries.
        if is_published:
            priced, rows, anchor_of, chart_only = published_priced(
                native, combo.get("player_keys", {}), anchor_by_key, combo_name, not_on_espn)
            review.extend(rows)
            if chart_only:
                out_combo["not_on_espn"] = chart_only
            rescaled = order_preserving_rescale(native, priced, anchor_of, pos_by_slug, chart_only)
            if rescaled is None:
                raise SystemExit(
                    f"reindex: {source}/{combo_name} has no positive native or anchor total "
                    "over its priced players -- cannot index")
            out_combo["reindexed"].update(rescaled["reindexed"])
            out_combo["fit"][RESCALE_FIT_KEY] = rescaled["fit"]
            out_combo["index_total"] = rescaled["index_total"]
            out_combo["n"] = {pos: t["n_priced"] for pos, t in rescaled["index_total"].items()}
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
