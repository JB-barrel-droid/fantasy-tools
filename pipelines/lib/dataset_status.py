"""dataset_status block for the trade-value-chart artifact.

Repo-owned port of trade-value/dataset_status.py (2026-09-22).

One entry per underlying dataset: display name, completeness (priced /
universe, explicit nulls never zero-filled), freshness (snapshot/pull date
AND content date where they differ — content vintage is the freshness that
matters), delta from prior (genuine only — a prior that cannot be verified
is reported "unavailable", never invented), and a stale flag with a
plain-language reason.

Brutally honest by design: the user does not trust the data right now, so
"unknown" is stated, never greenwashed.

Conventions (mirror pipelines/bake_players.py meta):
- Freshness gates measure when the SOURCE's numbers changed (content
  vintage), never download time. A byte-identical re-pull resets nothing.
- Missing values are null, never zero.
- Fail-closed-ish: the anchor (players.json meta + player records) must be
  present and sane or the builder raises. Per-dataset side inputs degrade
  to explicit "unavailable" entries — loud in the UI, never silent.

The full source taxonomy (12 entries) is preserved: our_value, ecr, espn,
prediction_markets, fantasycalc, usatoday, fantasypros, fantasycalc_adjusted,
usatoday_adjusted, fantasypros_adjusted, razzball, kdst. Nothing may be
dropped — a missing side input degrades its entry to explicit "unavailable",
never to omission.

Manipulation taxonomy (user-facing copy rule: say "value above waivers",
never "VORP"):
  trade-value-methodology = raw projections/stats -> value-above-waivers
                            methodology applied (positional waiver lines,
                            smoothed starter/bench lineup weights, 70-pt scale).
  reindexed-as-given     = their published values, only isotonic-reindexed
                            onto the chart's 0-70 scale; no methodology applied.

Interface: build_dataset_status(meta, players, snapshot_dir=None,
comparison_asset=None, fc_cache=None). The surgical main() path of the
original is retired: the repo bake is the only writer of players.json.

Repo-port changes vs the original:
- All hardcoded ~/workspace paths removed; side inputs are optional
  parameters that degrade to explicit "unavailable" when absent.
- UNIVERSE is derived from the baked player list, not hardcoded 596.
- K/DST entry reflects the 2026-09-21 ESPN-purity directive: K/DST price
  from ESPN projections (no expert blend).
- Razzball entry reflects the leg being baked (status live once the bake
  emits rz_* fields).
"""

import glob as _glob
import json
import os
import statistics
from datetime import datetime, timezone


def _utcnow():    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Manipulation taxonomy for the definitions table (user-facing copy rule:
# say "value above waivers", never "VORP").
#   trade-value-methodology = raw projections/stats -> value-above-waivers
#                             methodology applied (positional waiver lines,
#                             smoothed starter/bench lineup weights, 70-pt
#                             scale).
#   reindexed-as-given      = their published values, only isotonic-reindexed
#                             onto the chart's 0-70 scale; no methodology.
_METHOD_TV = ("trade-value-methodology", "Our methodology")
_METHOD_GIVEN = ("reindexed-as-given", "As published (reindexed)")


def _leg(v, leg="ppr"):
    if isinstance(v, dict):
        return v.get(leg)
    return v


def _ddf_prior_bake_delta(players, as_of, snapshot_dir=None):
    """Genuine bake-over-bake delta vs the most recent dated players.json
    snapshot older than this bake (data/fixtures/snapshots/players_<date>.json,
    written by the bake before each rebuild). Matches players by name and
    compares the full-PPR blend_ros leg. Returns a text summary or None.
    """
    try:
        cands = []
        if snapshot_dir:
            for f in _glob.glob(os.path.join(snapshot_dir, "players_*.json")):
                try:
                    d = json.load(open(f))
                    cands.append((d["meta"]["as_of"], f))
                except Exception:
                    continue
        priors = [(d_, f) for d_, f in cands if d_ < as_of]
        if not priors:
            return None
        prior_date, prior_file = sorted(priors)[-1]
        pmap = {p["name"]: p for p in
                json.load(open(prior_file))["players"]}
        dl = []
        for p in players:
            pr = pmap.get(p["name"])
            if not pr:
                continue
            c, v = _leg(p.get("blend_ros")), _leg(pr.get("blend_ros"))
            if isinstance(c, (int, float)) and isinstance(v, (int, float)):
                dl.append(c - v)
        if not dl:
            return None
        chg = sum(1 for x in dl if x != 0)
        return (prior_date, len(dl), chg, statistics.median(dl),
                sum(abs(x) for x in dl) / len(dl))
    except Exception:
        return None


def _fantasycalc_prior_delta(fc_cache=None):
    """Like-for-like FantasyCalc delta: Week 1 pull vs Week 2 snapshot —
    same scoring, team count, and row format — matched by player name.
    Returns a text summary or None.
    """
    try:
        if not fc_cache:
            return None

        def _latest(pat):
            cands = []
            for f in _glob.glob(os.path.join(fc_cache, pat)):
                try:
                    d = json.load(open(f))
                    cands.append((d.get("fetched_at", ""), f))
                except Exception:
                    continue
            return sorted(cands)[-1] if cands else (None, None)

        (pd_, pf) = _latest("fantasycalc_half_12.json")
        (cd_, cf) = _latest("fantasycalc_half_12_qb1.json")
        if not pf or not cf:
            return None
        prow = {r["name"]: r["value"] for r in json.load(open(pf))["rows"]
                if r.get("value") is not None}
        dl = []
        for r in json.load(open(cf))["rows"]:
            v, c = prow.get(r["name"]), r.get("value")
            if isinstance(c, (int, float)) and isinstance(v, (int, float)):
                dl.append(c - v)
        if not dl:
            return None
        chg = sum(1 for x in dl if x != 0)
        return (pd_[:10], cd_[:10], len(dl), chg, statistics.median(dl),
                sum(abs(x) for x in dl) / len(dl))
    except Exception:
        return None


def _fc_prior_entry(fc_cache=None):
    """Prior sub-block for the FantasyCalc entry (genuine Week 1 pull vs the
    Week 2 snapshot when both are present; explicit unavailable otherwise)."""
    fc_delta = _fantasycalc_prior_delta(fc_cache)
    if fc_delta:
        pd_, cd_, n_cmp, n_chg, med, mean_abs = fc_delta
        return {
            "available": True, "prior_date": pd_,
            "delta_summary": (
                f"Week 2 snapshot ({cd_}) vs Week 1 pull ({pd_}), 12-team "
                f"half-PPR: {n_chg} of {n_cmp} players moved; median move "
                f"{med:+.1f}, mean absolute move {mean_abs:.1f} "
                "(FantasyCalc's own value units).")}
    return {
        "available": False, "prior_date": None,
        "delta_summary": "No verified prior FantasyCalc pull retained — "
                         "no verified delta."}


def _delta_summary(players, cur_key, prior_key, leg="ppr"):
    """Median/mean move between two per-player value fields.

    Values are per-scoring legs ({standard, half_ppr, ppr}); the delta is
    computed on the full-PPR leg (the tweets' scoring). Returns
    (n_compared, n_changed, median_signed, mean_abs) or None when either
    field is absent.
    """
    def _leg2(v):
        if isinstance(v, dict):
            return v.get(leg)
        return v
    pairs = [(_leg2(p.get(cur_key)), _leg2(p.get(prior_key))) for p in players]
    pairs = [(c, pr) for c, pr in pairs
             if isinstance(c, (int, float)) and isinstance(pr, (int, float))]
    if not pairs:
        return None
    deltas = [c - pr for c, pr in pairs]
    changed = sum(1 for d in deltas if d != 0)
    return (len(pairs), changed,
            statistics.median(deltas),
            sum(abs(d) for d in deltas) / len(deltas))


def _comparison_sources(comparison_asset=None):
    """Side input: the comparison-sources asset (FantasyCalc / USA Today /
    FantasyPros / adjusted legs). Returns {} when unavailable — callers render
    explicit 'unavailable' entries, never guesses."""
    try:
        if not comparison_asset:
            return {}
        with open(comparison_asset) as f:
            d = json.load(f)
        return d.get("sources", {}) or {}
    except (OSError, ValueError):
        return {}


def _combo_player_count(source, prefer=()):
    """Player count from a representative scoring combo of a comparison
    source. Returns None when the structure is unexpected."""
    try:
        combos = source.get("combos") or {}
        keys = [k for k in prefer if k in combos] or sorted(combos)
        if not keys:
            return None
        inner = combos[keys[0]]
        sub = next(iter(inner.values()))
        return len(sub)
    except (AttributeError, StopIteration, TypeError):
        return None


def _comparison_entry(source_key, src, *, name, role, method,
                      method_description, completeness_note,
                      ui_note, prior=None, fit_note=None):
    """A comparison-source entry (FantasyCalc / USA Today / FantasyPros and
    their bias-adjusted variants). Missing side input degrades to an explicit
    'unavailable' entry — the entry is never dropped."""
    count = _combo_player_count(src, prefer=("half_12", "half_12_qb1",
                                            "full_12", "full_12_qb1",
                                            "standard_12"))
    if not src:
        return {
            "key": source_key, "name": name, "role": role,
            "method": method[0], "method_group": method[1],
            "method_description": method_description,
            "status": "pending", "shown_in_ui": False,
            "completeness": {"priced": None, "universe": None,
                             "note": "Comparison-sources asset unavailable "
                                     "at bake time — no verified read."},
            "freshness": {"snapshot_date": None, "content_date": None,
                          "note": "Comparison-sources asset unavailable "
                                  "at bake time."},
            "prior": {"available": False, "prior_date": None,
                      "delta_summary": "No verified prior."},
            "stale": False, "stale_reason": None,
            "caveat": "Source unavailable at bake time — treat as missing, "
                      "not as zero.",
            "ui_note": ui_note,
        }
    fetched = str(src.get("fetched_at") or "?")[:10]
    content = str(src.get("week_designated") or "?")
    if fit_note:
        content = f"{content} ({fit_note})"
    return {
        "key": source_key, "name": name, "role": role,
        "method": method[0], "method_group": method[1],
        "method_description": method_description,
        "status": "live", "shown_in_ui": True,
        "completeness": {"priced": count, "universe": None,
                         "note": completeness_note},
        "freshness": {"snapshot_date": fetched, "content_date": content,
                      "note": "Frozen weekly snapshot, pulled once per week."
                      if not fit_note else
                      "Frozen to the fit bake; re-fits on new source pulls."},
        "prior": prior or {"available": False, "prior_date": None,
                           "delta_summary": "No verified prior."},
        "stale": False, "stale_reason": None,
        "caveat": None,
        "ui_note": ui_note,
    }


def build_dataset_status(meta, players, snapshot_dir=None,
                         comparison_asset=None, fc_cache=None,
                         rz_live=True):
    """Build the dataset_status block from baked players.json content.

    rz_live: True when the bake emits Razzball leg fields (the repo bake
    always does); flips the Razzball entry from pending to live.
    """
    if not isinstance(meta, dict) or not meta.get("as_of"):
        raise ValueError("dataset_status: players.json meta missing as_of")
    if not players or len(players) < 500:
        raise ValueError(
            f"dataset_status: player universe too small ({len(players or [])})")
    as_of = str(meta["as_of"])
    n = len(players)

    # ---- our_value: DDF current (the chart's primary value) ----------------
    # Genuine bake-over-bake delta: the bake snapshots players.json to
    # data/fixtures/snapshots/players_<date>.json before each rebuild, so
    # the most recent snapshot older than this bake is the true prior.
    snap = _ddf_prior_bake_delta(players, as_of, snapshot_dir)
    expert_delta = _delta_summary(players, "blend_ros", "prior_blend_ros")
    if snap:
        prior_date, n_cmp, n_chg, med, mean_abs = snap
        ddf_delta_text = (
            f"Genuine prior bake (players_{prior_date}.json): {n_chg} of "
            f"{n_cmp} players changed value vs the {prior_date} "
            f"bake; median move {med:+.1f}, mean absolute move {mean_abs:.2f} "
            f"full-PPR trade-value points.")
        ddf_prior = {"available": True, "prior_date": prior_date,
                     "delta_summary": ddf_delta_text}
        if expert_delta:
            ddf_prior["expert_leg_note"] = (
                "Separately, prior_blend_ros measures the EXPERT-LEG move "
                "only (ECR-laden, no ESPN): "
                f"{expert_delta[1]} of {expert_delta[0]} players moved vs the "
                f"{meta.get('prior_ecr_snapshot')} expert snapshot — "
                "projections byte-identical.")
    elif expert_delta:
        n_cmp, n_chg, med, mean_abs = expert_delta
        ddf_prior = {
            "available": True,
            "prior_date": str(meta.get("prior_ecr_snapshot") or "?"),
            "delta_summary": (
                "No dated bake snapshot found — falling back to the "
                "expert-leg move only (prior_blend_ros is ECR-laden, no "
                f"ESPN): {n_chg} of {n_cmp} players moved vs the "
                f"{meta.get('prior_ecr_snapshot')} expert snapshot "
                "(full-PPR legs).")}
    else:
        ddf_prior = {"available": False, "prior_date": None,
                     "delta_summary": "No dated bake snapshot and no prior "
                                      "expert snapshot in this file — no "
                                      "verified delta."}
    ddf_entry = {
        "key": "our_value",
        "name": "current model value",
        "role": "The chart's primary trade value — our model's read, the number the tweets quote (full PPR).",
        "method": _METHOD_TV[0],
        "method_group": _METHOD_TV[1],
        "method_description": (
            "ECR stat projections translated to fantasy points, "
            "then run through the current value-above-waivers methodology: "
            "positional waiver lines, smoothed starter/bench lineup weights, "
            "70-point scale. Since 2026-09-16 the primary value is 100% "
            "ECR-sourced — ESPN does not enter it."),
        "status": "live",
        "shown_in_ui": True,
        "completeness": {
            "priced": n, "universe": n,
            "note": "Every charted player carries a current value model value."},
        "freshness": {
            "snapshot_date": as_of, "content_date": as_of,
            "note": "Computed at bake time from the expert (ECR) leg."},
        "prior": ddf_prior,
        "stale": False,
        "stale_reason": None,
        "caveat": ("The primary value is currently 100% expert (ECR) "
                   "projections — see ECR entry for freshness. "
                   "ESPN does not enter the primary value; it lives only in "
                   "the comparison columns."),
        "ui_note": "Shown as 'Our value' throughout the dashboard.",
    }

    # ---- ECR (expert consensus) ------------------------------------------
    ecr_snapshot = str(meta.get("ecr_snapshot") or "?")
    ecr_content = str(meta.get("ecr_content_date") or "?")
    try:
        ecr_age = (datetime.strptime(as_of, "%Y-%m-%d").date()
                   - datetime.strptime(ecr_content, "%Y-%m-%d").date()).days
    except ValueError:
        ecr_age = None
    ecr_stale = ecr_age is None or ecr_age > 3
    ecr_delta = _delta_summary(players, "ecr_ros", "prior_ecr_ros")
    if ecr_delta and ecr_delta[1] == 0:
        ecr_delta_text = (
            f"No changes: expert projections byte-identical across the "
            f"{ecr_content}, {meta.get('prior_ecr_snapshot')} and "
            f"{ecr_snapshot} snapshots.")
    elif ecr_delta:
        ecr_delta_text = (
            f"{ecr_delta[1]} of {ecr_delta[0]} players repriced vs "
            f"{meta.get('prior_ecr_snapshot')}.")
    else:
        ecr_delta_text = "Prior expert snapshot not retained — no verified delta."
    ecr_entry = {
        "key": "ecr",
        "name": "Expert consensus (ECR)",
        "role": "Expert projection baseline and the fill leg for unpriced components.",
        "method": _METHOD_TV[0],
        "method_group": _METHOD_TV[1],
        "method_description": (
            "Expert stat projections translated to fantasy points, then run "
            "through the current value-above-waivers methodology — the same "
            "math as the chart's primary value (positional waiver lines, "
            "smoothed starter/bench lineup weights, 70-point scale)."),
        "status": "stale" if ecr_stale else "live",
        "shown_in_ui": False,
        "completeness": {
            "priced": n, "universe": n,
            "note": "Full universe coverage when live."},
        "freshness": {
            "snapshot_date": ecr_snapshot, "content_date": ecr_content,
            "note": ("Pull date is not freshness: a byte-identical re-pull "
                     "does not reset the content clock.")},
        "prior": {"available": True,
                  "prior_date": str(meta.get("prior_ecr_snapshot") or "?"),
                  "delta_summary": ecr_delta_text},
        "stale": ecr_stale,
        "stale_reason": (
            f"Expert projections unchanged since {ecr_content} "
            f"({ecr_age} days). Every ECR-derived value is hidden in the "
            f"dashboard until the experts publish fresh numbers."
            if ecr_stale else None),
        "caveat": None,
        "ui_note": ("Hidden while stale: pricing-model picker, curve ECR model, "
                    "side-by-side view, value/PPG disagreement lenses and the "
                    "Trade Designer's perceived-value column are greyed out. "
                    "ESPN-vs-experts RANK comparison remains available."),
    }

    # ---- ESPN --------------------------------------------------------------
    espn_snapshot = str(meta.get("espn_snapshot") or "?")
    n_espn = meta.get("n_espn_complete")
    espn_entry = {
        "key": "espn",
        "name": "ESPN",
        "role": "Market leg: ESPN season projections (Mike Clay model) — expert/model numbers, explicitly not sportsbook money.",
        "method": _METHOD_TV[0],
        "method_group": _METHOD_TV[1],
        "method_description": (
            "ESPN stat projections where priced (ECR fills the rest, no "
            "averaging) translated to fantasy points, then run through the "
            "current value-above-waivers methodology — the same math as the "
            "chart's primary value. No Monday adjustments."),
        "status": "live",
        "shown_in_ui": True,
        "completeness": {
            "priced": n_espn, "universe": n,
            "note": ("Pure read over priced components only — never "
                     "zero-filled. espn_filled_* fills the rest from ECR.")},
        "freshness": {
            "snapshot_date": espn_snapshot, "content_date": espn_snapshot,
            "note": ("Daily morning pull. Content change vs the prior pull is "
                     "not verifiable — only the current pull is retained.")},
        "prior": {"available": False, "prior_date": None,
                  "delta_summary": "Prior ESPN pull not retained — no verified delta."},
        "stale": False,
        "stale_reason": None,
        "caveat": ("espn_filled_* values include an ECR-filled share for "
                   "unpriced components — see ECR entry for expert freshness."),
        "ui_note": "Powers the 'Where ESPN disagrees' rank view. Does not enter the primary value.",
    }

    # ---- Prediction markets --------------------------------------------------
    pm_snapshot = str(meta.get("pm_snapshot") or "?")
    pm_entry = {
        "key": "prediction_markets",
        "name": "Prediction markets",
        "role": "Market leg: raw Kalshi/Polymarket season ladders through our own isotonic math and liquidity gate — crowd wisdom, NOT sportsbook money.",
        "method": _METHOD_TV[0],
        "method_group": _METHOD_TV[1],
        "method_description": (
            "Prediction-market-implied stat medians (raw Kalshi/Polymarket "
            "ladders, our own isotonic math) where priced, ECR fills the "
            "rest, translated to fantasy points, then run through the current "
            "value-above-waivers methodology — the same math as the chart's "
            "primary value."),
        "status": "live",
        "shown_in_ui": True,
        "completeness": {
            "priced": meta.get("n_pm_complete"), "universe": n,
            "note": (f"{meta.get('n_pm_covered')} players have at least one "
                     f"priced component. Season receptions ladders have no "
                     f"liquid two-sided market, so pass-catchers' pure reads "
                     f"exclude reception points by construction. Never "
                     f"zero-filled.")},
        "freshness": {
            "snapshot_date": pm_snapshot, "content_date": pm_snapshot,
            "note": "Ladder snapshot date from the pull."},
        "prior": {"available": False, "prior_date": None,
                  "delta_summary": "Ladder snapshots are overwritten in place — no prior retained, no verified delta."},
        "stale": False,
        "stale_reason": None,
        "caveat": ("Thin coverage is the story here: only "
                   f"{meta.get('n_pm_complete')} of {n} players are fully "
                   f"priced. Treat unpriced players as 'no market read', not "
                   f"as zeros."),
        "ui_note": "Curve widget source toggle (off by default).",
    }

    # ---- Razzball ------------------------------------------------------------
    rz_entry = {
        "key": "razzball",
        "name": "Razzball",
        "role": "Third projection leg (verified independent of ECR and ESPN, 2026-09-17).",
        "method": _METHOD_TV[0],
        "method_group": _METHOD_TV[1],
        "method_description": (
            "Razzball's published per-game projections (rest-of-season via "
            "our own games remaining; their doubled games/totals fields are "
            "never used) run through the current value-above-waivers "
            "methodology — the same math as the chart's primary value."),
        "status": "live" if rz_live else "pending",
        "shown_in_ui": bool(rz_live),
        "completeness": {
            "priced": meta.get("n_rz_complete"), "universe": n,
            "note": ("Razzball where priced, ECR fallback. Rank correlation "
                     "vs ECR 0.78–0.91, never 0.99+ — verified independent "
                     "2026-09-17.")} if rz_live else {
            "priced": None, "universe": n,
            "note": "Not in this bake."},
        "freshness": {
            "snapshot_date": str(meta.get("rz_snapshot") or "?"),
            "content_date": str(meta.get("rz_snapshot") or "?"),
            "note": "Daily morning pull."} if rz_live else {
            "snapshot_date": None, "content_date": None,
            "note": "No Razzball fields in players.json yet."},
        "prior": {"available": False, "prior_date": None,
                  "delta_summary": "No prior bake — leg not yet live."
                  if not rz_live else "Prior Razzball pull not retained — no verified delta."},
        "stale": False,
        "stale_reason": None,
        "caveat": None,
        "ui_note": "Curve-widget source toggle (off by default)." if rz_live
                   else "Will appear as a curve-widget source toggle (off by default) once baked.",
    }

    # ---- Kickers & defenses -----------------------------------------------------
    # 2026-09-21 ESPN-purity directive: K/DST price from ESPN projections
    # only — no expert blend.
    n_k = meta.get("n_k")
    n_dst = meta.get("n_dst")
    kdst_snapshot = str(meta.get("kdst_snapshot") or "?")
    kdst_entry = {
        "key": "kdst",
        "name": "Kickers & defenses",
        "role": "K/DST values price from ESPN projections only — no expert numbers anywhere in the K/DST leg (ESPN-purity directive, 2026-09-21).",
        "method": _METHOD_TV[0],
        "method_group": _METHOD_TV[1],
        "method_description": (
            "ESPN's K/DST season stat projections translated to fantasy "
            "points, then run through the current value-above-waivers "
            "methodology — the same math as the chart's primary value. "
            "No expert/ECR input enters K/DST pricing."),
        "status": "live",
        "shown_in_ui": True,
        "completeness": {
            "priced": (n_k or 0) + (n_dst or 0), "universe": None,
            "note": (f"{n_k} kickers + {n_dst} defenses. Scoring-invariant: one "
                     "number serves standard/half/full.")},
        "freshness": {
            "snapshot_date": kdst_snapshot, "content_date": kdst_snapshot,
            "note": ("ESPN K/DST projection files; K season stats update "
                     "weekly, DST ROS refreshes on the morning pull.")},
        "prior": {"available": False, "prior_date": None,
                  "delta_summary": "No verified prior delta."},
        "stale": False,
        "stale_reason": None,
        "caveat": None,
        "ui_note": "Shown in the main board like any other position.",
    }

    # ---- Comparison sources (optional side input) ------------------------------
    # FantasyCalc / USA Today / FantasyPros (as published, reindexed) and
    # their bias-adjusted variants (corrected toward our methodology via
    # source_value_adjustments fits). The comparison-sources asset is the
    # single side input: data/fixtures/current/comparison-sources-data.json.
    src = _comparison_sources(comparison_asset)

    fc_entry = _comparison_entry(
        "fantasycalc", src.get("fantasycalc"),
        name="FantasyCalc",
        role="Comparison source: crowd trade values from completed real trades.",
        method=_METHOD_GIVEN,
        method_description=(
            "FantasyCalc's published crowd trade values, isotonic-reindexed "
            "onto the chart's 0-70 scale against our own values. No current "
            "value model methodology applied — shown as published, biases "
            "and all."),
        completeness_note=(
            "QB/RB/WR/TE only — no K/DST coverage. Native unit is "
            "FantasyCalc's own ~2–10,500 crowd-value scale, not points."),
        ui_note="Chart Comparison tab: 'FantasyCalc' source column.",
        prior=_fc_prior_entry(fc_cache))

    usatoday_entry = _comparison_entry(
        "usatoday", src.get("usatoday"),
        name="USA Today",
        role="Comparison source: USA Today editorial trade value chart.",
        method=_METHOD_GIVEN,
        method_description=(
            "USA Today's published chart values (QB values are implied from "
            "their single 1QB column), isotonic-reindexed onto the 0-70 scale "
            "against our own values. No current value model methodology "
            "applied — shown as published, biases and all."),
        completeness_note=(
            "QB/RB/WR/TE only — no K/DST coverage. Editorial chart points on "
            "their own ~0–70 scale, per scoring column."),
        ui_note="Chart Comparison tab: 'USA Today' source column.",
        prior={"available": False, "prior_date": None,
               "delta_summary": (
                   "A Week 1 file exists (233 players, Sep 12) but carries a "
                   "single value per player with undocumented scoring basis "
                   "— not like-for-like comparable to the Week 2 per-scoring "
                   "columns, so no verified delta.")})

    fantasypros_entry = _comparison_entry(
        "fantasypros", src.get("fantasypros"),
        name="FantasyPros",
        role="Comparison source: FantasyPros analyst-consensus editorial trade value chart.",
        method=_METHOD_GIVEN,
        method_description=(
            "FantasyPros' published base Value column (scoring-agnostic, "
            "reused across the three scoring combos), isotonic-reindexed onto "
            "the 0-70 scale against our own values. No current value model "
            "methodology or positional reweighting applied — shown as "
            "published, biases and all."),
        completeness_note=(
            f"QB/RB/WR/TE only — no K/DST coverage. "
            f"{_combo_player_count(src.get('fantasypros') or {}) or '?'} of "
            f"{n} chart players priced. Native unit is FantasyPros "
            "analyst-consensus chart points (~1.0–75.1 scale)."),
        ui_note="Chart Comparison tab: 'FantasyPros' source column.",
        prior={"available": False, "prior_date": None,
               "delta_summary": "First FantasyPros snapshot — no prior."})

    def _adjusted_entry(key, label, short):
        prov = ((src.get(key) or {}).get("provenance_note") or "")
        fit = None
        for tok in prov.split():
            if tok.startswith("fit"):
                fit = tok.strip("(,)").strip(").")
                break
        return _comparison_entry(
            key, src.get(key),
            name=f"{label} (bias-adjusted)",
            role=f"Comparison source: {label} values corrected toward our methodology.",
            method=_METHOD_TV,
            method_description=(
                f"{label}'s published values corrected by the "
                f"source_value_adjustments fit (bake {fit}) — per-position x "
                "role linear correction against the Monday reassessed "
                "methodology leg. Already on the 0-70 scale." if fit else
                f"{label}'s published values corrected by the "
                "source_value_adjustments fit — per-position x role linear "
                "correction against the Monday reassessed methodology leg. "
                "Already on the 0-70 scale."),
            completeness_note="QB/RB/WR/TE only — no K/DST coverage.",
            ui_note=f"Chart Comparison tab: '{short} Adjusted' source column.",
            fit_note=f"fit {fit}" if fit else None,
            prior={"available": False, "prior_date": None,
                   "delta_summary": "First bias-adjusted bake — no prior."})

    fc_adj_entry = _adjusted_entry("fantasycalc_adjusted", "FantasyCalc", "FC")
    usat_adj_entry = _adjusted_entry("usatoday_adjusted", "USA Today", "USAT")
    fp_adj_entry = _adjusted_entry("fantasypros_adjusted", "FantasyPros", "FP")

    datasets = [ddf_entry, ecr_entry, espn_entry, pm_entry,
                fc_entry, usatoday_entry, fantasypros_entry,
                fc_adj_entry, usat_adj_entry, fp_adj_entry,
                rz_entry, kdst_entry]
    summary = {
        "live": sum(1 for d in datasets if d["status"] == "live"),
        "stale": sum(1 for d in datasets if d["status"] == "stale"),
        "pending": sum(1 for d in datasets if d["status"] == "pending"),
        "hidden_in_ui": sum(1 for d in datasets if not d["shown_in_ui"]),
    }
    return {
        "built_at": _utcnow(),
        "as_of": as_of,
        "summary": summary,
        "ui_hint": {
            "start_collapsed": True,
            "panel_title": "Data health: what's under this chart",
        },
        "datasets": datasets,
    }
