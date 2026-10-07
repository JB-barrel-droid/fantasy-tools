"""FDS-primary weekly Vegas leg with local raw-book audit.

Precedence is governed by engine.source_priority.VEGAS_SOURCE_PRIORITY
("fds", "local"): First Down Studio is the PRIMARY coverage backbone
(free, full-slate, daily); locally calculated Vegas from raw sportsbook
odds (The Odds API) is the AUDIT leg. The priority is a config-level
switch — it is read here, never hardcoded in the merge logic.

How the two legs combine (user-approved 2026-09-17):
- FDS vegas-attributed translated stats are run through OUR OWN scoring
  math locally (compute_fds_points) to produce the primary Vegas leg
  for every FDS-covered Sunday player.
- Local raw-book numbers audit the primary: where local coverage is
  publishable ('complete'/'td-filled') and disagrees materially
  (|delta| >= AUDIT_DISAGREEMENT_THRESHOLD on any scoring leg), the
  raw-book number wins — raw books are the ground truth FDS claims to
  translate — and the disagreement is recorded as a QA finding. Where
  they agree, the FDS-primary number stands and the agreement is
  recorded. Partial local coverage never blocks the fuller FDS-primary
  inputs; it cross-checks informationally. Local-only players (e.g.
  Thursday games, outside FDS's Sunday scope) publish as local, as
  before.

PER-STAT PROVENANCE (user-approved 2026-09-17) — the load-bearing rule:
FDS attributes EACH translated stat as 'vegas' or 'projection'. Only
'vegas'-attributed stats may feed the Vegas leg. The fallback's Vegas
numbers are RECOMPUTED LOCALLY from the vegas-attributed translated stats
via our own disclosed scoring math (engine.scoring) — FDS's blended
derived points (standard/halfppr/ppr) are NEVER used, because they silently
blend vegas-attributed and projection-attributed inputs.

'projection'-attributed stats are FDS model output: they are carried on the
row as explicitly-labeled FDS projection info (fds_projection_stats),
shown separately where useful, but NEVER counted as Vegas, never placed in
a Vegas column, never blended into the points math.

Completeness (mirrors the local gate):
- 'fds-derived': every required stat for the position is vegas-attributed.
  Publishable — the fallback exists so Sunday's chain runs with coverage —
  but ALWAYS labeled, never presented as locally calculated from raw odds.
- 'fds-partial': a required stat is projection-attributed or missing.
  Computed and stored (informational only, like local 'partial' rows) but
  never post-worthy.

Hard boundaries (fail-closed):
- SCOPE: the FDS primary leg is authorized for Sunday games only.
  Non-Sunday kickoffs (Thursday, Monday night etc.) are never covered
  by FDS unless the user says so — those stay local-only.
- FDS numbers never enter odds_history and never pass through
  engine.vegas.vegas_implied_points (raw-odds math; feeding it derived
  values would fabricate provenance).
- Every row with a Vegas leg must have vegas_provenance in
  ALLOWED_PROVENANCE and vegas_leg in VEGAS_LEGS; validate_signal_rows()
  raises otherwise.
- Never-blend: exactly one PUBLISHED leg per row. An FDS-published row
  may carry a local audit (agreement recorded); a local-published row
  that was also FDS-covered must be a recorded disagreement override —
  local never silently displaces the primary.
- Vegas-column integrity: a row's vegas_std/half/ppr must equal a fresh
  local recomputation from its vegas_stats_used ONLY. If a
  projection-attributed stat ever leaks into the math, the recomputation
  diverges and the build fails.
"""

import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .scoring import fantasy_points, fantasy_points_or_null  # noqa: E402
from .source_priority import (  # noqa: E402
    VEGAS_SOURCE_PRIORITY, check_priority, check_fds_primary,
)
from .vegas import PUBLISHABLE_PROVENANCE  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root

CT = ZoneInfo("America/Chicago")


def is_sunday_kickoff(rec):
    """Authorization scope (user-approved 2026-09-17): the FDS fallback is
    wired for Sunday games ONLY. kickoff_at is evaluated in America/Chicago;
    a missing, naive, or unparseable kickoff fails closed (not Sunday) —
    Monday-night (or any non-Sunday) players never get FDS coverage unless
    the user separately authorizes it."""
    ka = rec.get("kickoff_at")
    if not ka:
        return False
    try:
        dt = datetime.fromisoformat(ka)
    except ValueError:
        return False
    if dt.tzinfo is None:
        return False
    return dt.astimezone(CT).weekday() == 6  # Monday=0 … Sunday=6


def is_pregame_kickoff(rec, now=None):
    """Pre-kickoff scope (2026-09-21): the FDS fallback is a pre-game
    coverage mechanism — a kicked-off game is unbettable, so its players
    never get FDS coverage, even on an authorized Sunday. kickoff_at must
    be aware, parseable, and strictly in the future; missing, naive,
    unparseable, or past kickoffs fail closed (not pregame)."""
    ka = rec.get("kickoff_at")
    if not ka:
        return False
    try:
        dt = datetime.fromisoformat(ka)
    except ValueError:
        return False
    if dt.tzinfo is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return dt > now

FDS_PROVENANCE = "fds-derived"      # publishable FDS fallback rows
FDS_PARTIAL = "fds-partial"        # informational only, never post-worthy
# PropLine-primary (2026-09-18): "propline" is the primary raw-price leg.
# VEGAS_SOURCE_PRIORITY in engine/source_priority.py is ("propline",
# "odds_api", "fds"); QUOTABLE_VEGAS_LEGS already lists propline.
VEGAS_LEGS = ("local", "fds", "propline")
ALLOWED_PROVENANCE = ("complete", "td-filled", "partial",
                      FDS_PROVENANCE, FDS_PARTIAL)

# FDS skill positions only. Kickers never enter the signals universe.
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

# FDS translated stat -> engine.scoring stat key, per position.
# expected_touchdowns is FDS's TOTAL expected TDs; for QBs the FDS number is
# non-passing TDs (verified 2026-09-17: Allen 2.0 pass TD vs 0.73 exp TD),
# so it takes the local 'rushing_tds' bucket — the same bucket
# vegas_implied_points uses for QB anytime-TD expectation. For RB/WR/TE it
# takes 'receiving_tds', the local non-QB bucket (both score 6.0, so the
# label is cosmetic and the total is exact).
FDS_SCORING_MAP = {
    "QB": {"passing_yards": "passing_yards",
           "passing_touchdowns": "passing_tds",
           "interceptions": "interceptions",
           "rushing_yards": "rushing_yards",
           "expected_touchdowns": "rushing_tds"},
    "RB": {"rushing_yards": "rushing_yards",
           "receptions": "receptions",
           "receiving_yards": "receiving_yards",
           "expected_touchdowns": "receiving_tds"},
    "WR": {"rushing_yards": "rushing_yards",
           "receptions": "receptions",
           "receiving_yards": "receiving_yards",
           "expected_touchdowns": "receiving_tds"},
    "TE": {"rushing_yards": "rushing_yards",
           "receptions": "receptions",
           "receiving_yards": "receiving_yards",
           "expected_touchdowns": "receiving_tds"},
}

# Required vegas-attributed stats per position (mirrors the local
# COMPLETENESS_LINES gate: yardage + TD coverage; WR/TE also receptions).
FDS_REQUIRED = {
    "QB": ("passing_yards", "expected_touchdowns"),
    "RB": ("rushing_yards", "expected_touchdowns"),
    "WR": ("receiving_yards", "receptions", "expected_touchdowns"),
    "TE": ("receiving_yards", "receptions", "expected_touchdowns"),
}


def norm(name):
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def is_publishable(prov):
    """Coverage gate: local complete/td-filled plus publishable FDS rows.
    'fds-partial' is informational only, like local 'partial'."""
    return prov in PUBLISHABLE_PROVENANCE or prov == FDS_PROVENANCE


def is_fds_prov(prov):
    return prov in (FDS_PROVENANCE, FDS_PARTIAL)


def load_payload(week):
    """Load data/fds_wk{N}.json. None when absent (fallback skipped,
    local-only build). Raises on a corrupt payload — fail loudly."""
    path = os.path.join(BASE, "data", f"fds_wk{week}.json")
    if not os.path.exists(path):
        return None
    try:
        p = json.load(open(path))
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"FDS payload corrupt: {path}: {e}")
    if p.get("provenance") != FDS_PROVENANCE:
        raise ValueError(f"FDS payload missing provenance marker: {path}")
    if p.get("week") != week:
        raise ValueError(
            f"FDS payload week {p.get('week')} != requested week {week}")
    if not isinstance(p.get("players"), list) or not p["players"]:
        raise ValueError(f"FDS payload has no players: {path}")
    return p


def index_payload(payload):
    """{norm_name: record} for QB/RB/WR/TE records."""
    idx = {}
    for pl in payload["players"]:
        if pl.get("position") not in SKILL_POSITIONS:
            continue
        name = pl.get("name") or ""
        if not name:
            continue
        idx.setdefault(norm(name), {
            "name": name,
            "pos": pl["position"],
            "team": pl.get("team"),
            "game_key": pl.get("game_key"),
            "kickoff_at": pl.get("kickoff_at"),
            "stats": pl.get("stats") or {},
            "stat_sources": pl.get("stat_sources") or {},
            "injury_status": pl.get("injury_status"),
            # FDS's own blended derived points, carried verbatim for the
            # calibration cross-check ONLY (collector stores them as
            # top-level standard/halfppr/ppr keys). They must never feed a
            # Vegas leg — compute_fds_points() recomputes locally instead.
            "fantasy_points": {
                "standard": pl.get("standard"),
                "halfppr": pl.get("halfppr"),
                "ppr": pl.get("ppr"),
            },
        })
    return idx


def _split_stats(rec):
    """Split a payload record's scoring-relevant stats by attribution.

    Returns (vegas_stats, projection_stats, missing):
    - vegas_stats: {fds_stat: value} with stat_sources == 'vegas'
    - projection_stats: {fds_stat: value} with stat_sources == 'projection'
      (FDS model output — informational only, never feeds the Vegas leg)
    - missing: scoring-relevant stats with no value/attribution
    """
    smap = FDS_SCORING_MAP[rec["pos"]]
    vegas_stats, projection_stats, missing = {}, {}, []
    for fds_stat in smap:
        src = rec["stat_sources"].get(fds_stat)
        val = rec["stats"].get(fds_stat)
        if val is None or src is None:
            missing.append(fds_stat)
        elif src == "vegas":
            vegas_stats[fds_stat] = val
        elif src == "projection":
            projection_stats[fds_stat] = val
        else:
            missing.append(fds_stat)  # unknown attribution: treat as missing
    return vegas_stats, projection_stats, missing


def compute_fds_points(rec):
    """Locally recompute fantasy points from vegas-attributed stats ONLY.

    FDS's own blended derived points are deliberately NOT used. Returns
    {'std','half','ppr', 'vegas_stats_used', 'projection_stats',
     'stat_sources', 'gaps', 'completeness'} where completeness is
    'fds-derived' (all required stats vegas-attributed, publishable) or
    'fds-partial' (informational only).
    """
    smap = FDS_SCORING_MAP[rec["pos"]]
    vegas_stats, projection_stats, missing = _split_stats(rec)
    scoring_stats = {smap[k]: v for k, v in vegas_stats.items()}
    # 2026-09-18: null — never zero — a leg no vegas-attributed stat can
    # move (mirrors the raw-book legs in translate_props_to_vegas).
    pts = {sc: fantasy_points_or_null(scoring_stats, scoring=sc)
           for sc in ("standard", "half_ppr", "ppr")}
    required = FDS_REQUIRED[rec["pos"]]
    gaps = [s for s in required
            if rec["stat_sources"].get(s) != "vegas"
            or rec["stats"].get(s) is None]
    completeness = FDS_PROVENANCE if not gaps else FDS_PARTIAL
    return {
        "std": pts["standard"], "half": pts["half_ppr"], "ppr": pts["ppr"],
        "vegas_stats_used": vegas_stats,
        "projection_stats": projection_stats,
        "stat_sources": {k: rec["stat_sources"].get(k) for k in smap},
        "gaps": gaps,
        "missing": missing,
        "completeness": completeness,
    }


def fds_row_detail(comp):
    """Schema-level per-stat provenance from a compute_fds_points result.

    Single source of the compute-keys -> schema-keys mapping
    (stat_sources -> fds_stat_sources, projection_stats ->
    fds_projection_stats). Uses .get: a missing key yields None and fails
    the batch downstream in validate_rows_v4 (SystemExit, never shipped
    quietly) — this mapping must never raise KeyError mid-build.
    """
    return {
        "vegas_stats_used": comp.get("vegas_stats_used"),
        "fds_stat_sources": comp.get("stat_sources"),
        "fds_projection_stats": comp.get("projection_stats"),
    }


# Audit leg (user-approved 2026-09-17): where publishable local raw-book
# numbers and the FDS-primary number disagree materially, the raw-book
# number wins (ground truth) and the disagreement is a QA finding.
# Threshold sits below the 2.0 post-worthy gate so audit flags never
# manufacture signals, and above typical translation noise.
AUDIT_DISAGREEMENT_THRESHOLD = 1.5


def merge_fds_primary(vegas_by_pos, extra, fds_index, pos_of,
                      priority=VEGAS_SOURCE_PRIORITY, sunday_only=True,
                      now=None):
    """FDS-primary merge: every FDS-covered Sunday player gets the primary
    Vegas leg, computed LOCALLY from vegas-attributed translated stats
    only. The local raw-book leg is applied afterwards by
    apply_local_audit() — it never runs first here.

    Position mismatch between FDS and the local authority skips the row
    (fail-closed against bad mappings). sunday_only (default True): the
    user authorized FDS for Sunday games only — non-Sunday kickoffs are
    skipped, never silently covered. A kicked-off game is unbettable, so
    FDS coverage is pre-kickoff only: players whose kickoff_at is not in
    the future are skipped (skipped_kicked_off), even on a Sunday.

    Returns (counts dict, fds_keys set) for logging/audit.
    """
    check_fds_primary(priority)
    counts = {"added": 0, "added_derived": 0, "added_partial": 0,
              "no_match": 0, "pos_mismatch": 0, "skipped_kicked_off": 0,
              "skipped_not_sunday": 0, "by_pos": {}}
    fds_keys = set()
    for key, rec in fds_index.items():
        if sunday_only and not is_sunday_kickoff(rec):
            counts["skipped_not_sunday"] += 1
            continue
        if not is_pregame_kickoff(rec, now=now):
            counts["skipped_kicked_off"] += 1
            continue
        pos = pos_of(key)
        if not pos:
            counts["no_match"] += 1
            continue
        if pos != rec["pos"]:
            counts["pos_mismatch"] += 1
            continue
        comp = compute_fds_points(rec)
        vegas_by_pos.setdefault(pos, {})[key] = {
            "std": comp["std"], "half": comp["half"], "ppr": comp["ppr"]}
        extra[key] = {
            "td_p": None,
            "markets": sorted(comp["vegas_stats_used"]),
            "provenance": comp["completeness"],
            "vegas_leg": "fds",
            "prov_gaps": comp["gaps"],
            # Schema-level per-stat provenance via the shared helper —
            # one mapping, never drifted between call sites.
            **fds_row_detail(comp),
            "fds_name": rec["name"],
            "fds_game": rec["game_key"],
        }
        fds_keys.add(key)
        counts["added"] += 1
        if comp["completeness"] == FDS_PROVENANCE:
            counts["added_derived"] += 1
        else:
            counts["added_partial"] += 1
        counts["by_pos"][pos] = counts["by_pos"].get(pos, 0) + 1
    return counts, fds_keys


def apply_local_audit(vegas_by_pos, extra, local_by_pos, local_extra,
                      fds_keys, priority=VEGAS_SOURCE_PRIORITY):
    """Apply the local raw-book audit leg over the FDS-primary build.

    local_by_pos / local_extra: local numbers keyed {pos: {key: {std,half,
    ppr}}} and per-key detail dicts (provenance, vegas_leg='local', ...),
    computed from raw sportsbook odds via engine.vegas — the same shape
    compute_v4 builds today, just kept separate until the audit.

    Rules:
    - Local-only key (not FDS-covered, e.g. Thursday games): published
      as local, exactly as before.
    - FDS-covered + local publishable ('complete'/'td-filled'): compare
      per scoring leg. |delta| >= AUDIT_DISAGREEMENT_THRESHOLD on any leg
      -> disagreement: the raw-book number wins (ground truth) and the
      disagreement is recorded as a QA finding. Agreement -> the
      FDS-primary number stands; the agreement is recorded.
    - FDS-covered + local partial: the fuller FDS-primary inputs stand;
      the partial local number cross-checks informationally only — it
      never blocks FDS and never overrides.

    Returns (disagreements list, counts dict). Disagreements are dicts
    with name/pos/deltas/max_abs/winner for the QA bundle.
    """
    check_fds_primary(priority)
    disagreements = []
    counts = {"local_only": 0, "agreements": 0, "overrides": 0,
              "partial_crosschecks": 0}
    for pos, players in local_by_pos.items():
        for key, pts in players.items():
            detail = local_extra.get(key, {})
            if key not in fds_keys:
                # Local-only (e.g. Thursday game): published as local.
                vegas_by_pos.setdefault(pos, {})[key] = dict(pts)
                extra[key] = dict(detail)
                counts["local_only"] += 1
                continue
            prov = detail.get("provenance")
            fds_pts = vegas_by_pos[pos][key]
            if prov not in PUBLISHABLE_PROVENANCE:
                # Partial local never blocks the fuller FDS-primary
                # inputs; recorded as an informational cross-check.
                note = extra[key].setdefault("audit", {})
                note["local_partial_crosscheck"] = {
                    "local_provenance": prov,
                    "local_pts": dict(pts),
                }
                counts["partial_crosschecks"] += 1
                continue
            deltas = {leg: round(pts[leg] - fds_pts[leg], 2)
                      for leg in ("std", "half", "ppr")}
            max_abs = max(abs(d) for d in deltas.values())
            if max_abs >= AUDIT_DISAGREEMENT_THRESHOLD:
                # Ground truth wins; the disagreement is a QA finding.
                fds_prov = extra[key].get("provenance")
                vegas_by_pos[pos][key] = dict(pts)
                new_detail = dict(detail)
                new_detail["audit"] = {
                    "disagreement_override": True,
                    "deltas_vs_fds_primary": deltas,
                    "max_abs_delta": max_abs,
                    "fds_primary_pts": dict(fds_pts),
                }
                extra[key] = new_detail
                disagreements.append({
                    "name": detail.get("name") or key,
                    "pos": pos,
                    "deltas": deltas,
                    "max_abs_delta": max_abs,
                    "winner": "local",
                    "fds_provenance": fds_prov,
                })
                counts["overrides"] += 1
            else:
                note = extra[key].setdefault("audit", {})
                note["local_agrees"] = True
                note["max_abs_delta_vs_local"] = max_abs
                counts["agreements"] += 1
    return disagreements, counts


def build_vegas_legs(local_by_pos, local_extra, fds_index, pos_of,
                     priority=VEGAS_SOURCE_PRIORITY, sunday_only=True,
                     now=None):
    """Shared FDS-primary entry point (compute_v4 and game_day must never
    diverge): FDS-primary merge first, then the local raw-book audit leg.

    Returns (vegas_by_pos, extra, fds_keys, local_keys, audit) where
    audit = {"disagreements": [...], "counts": {...}, "fds_counts": {...}}.
    """
    check_fds_primary(priority)
    vegas_by_pos, extra = {}, {}
    fds_counts, fds_keys = merge_fds_primary(
        vegas_by_pos, extra, fds_index, pos_of,
        priority=priority, sunday_only=sunday_only, now=now)
    disagreements, audit_counts = apply_local_audit(
        vegas_by_pos, extra, local_by_pos, local_extra, fds_keys,
        priority=priority)
    local_keys = {k for d in local_by_pos.values() for k in d}
    audit = {"disagreements": disagreements,
             "counts": audit_counts,
             "fds_counts": fds_counts}
    return vegas_by_pos, extra, fds_keys, local_keys, audit


def recompute_row_points(row):
    """Recompute a row's Vegas legs from its vegas_stats_used only.

    The Vegas-column integrity check: projection-attributed stats must
    never feed the math, so recomputing from the declared vegas inputs
    must reproduce the row exactly.
    """
    smap = FDS_SCORING_MAP[row["pos"]]
    vegas_stats = row.get("vegas_stats_used") or {}
    scoring_stats = {smap[k]: v for k, v in vegas_stats.items() if k in smap}
    return {sc: fantasy_points_or_null(scoring_stats, scoring=sc)
            for sc in ("standard", "half_ppr", "ppr")}


def validate_signal_rows(rows, fds_index, local_keys, fds_keys,
                         audit=None, priority=VEGAS_SOURCE_PRIORITY):
    """Fail-closed provenance audit over signal rows.

    - Any row with a non-null Vegas leg must carry vegas_provenance in
      ALLOWED_PROVENANCE and vegas_leg in VEGAS_LEGS.
    - Never-blend: exactly one PUBLISHED leg per row. An 'fds' row's key
      may also be in local_keys (the audit leg ran) — that is expected,
      not a blend. A 'local' row whose key is in fds_keys must be a
      recorded disagreement override (audit['disagreements']); local
      never silently displaces the FDS primary.
    - Vegas-column integrity: an 'fds' row's std/half/ppr must equal a fresh
      local recomputation from its vegas_stats_used ONLY — a
      projection-attributed stat leaking into any Vegas column fails here.
    - Every stat in vegas_stats_used must be 'vegas'-attributed in the
      payload.

    Raises ValueError on the first violation.
    """
    check_priority(priority)
    audit = audit or {}
    override_names = {d.get("name") for d in
                      audit.get("disagreements", [])}
    for r in rows:
        legs = [r.get("vegas_std"), r.get("vegas_half"), r.get("vegas_ppr")]
        if all(v is None for v in legs):
            continue
        name = r.get("name", "?")
        prov = r.get("vegas_provenance")
        leg = r.get("vegas_leg")
        if prov not in ALLOWED_PROVENANCE:
            raise ValueError(
                f"provenance FAIL: {name}: vegas_provenance={prov!r} not in "
                f"{ALLOWED_PROVENANCE} — missing label fails the build")
        if leg not in VEGAS_LEGS:
            raise ValueError(
                f"provenance FAIL: {name}: vegas_leg={leg!r} not in "
                f"{VEGAS_LEGS} — missing label fails the build")
        key = r.get("player_key")
        if leg == "fds":
            if key not in fds_keys:
                raise ValueError(
                    f"never-blend FAIL: {name}: fds leg but key not in the "
                    "FDS-primary added set")
            rec = fds_index.get(key)
            if rec is None:
                raise ValueError(
                    f"never-blend FAIL: {name}: fds leg but no payload record")
            # Every declared vegas input must actually be vegas-attributed.
            for st in (r.get("vegas_stats_used") or {}):
                if rec["stat_sources"].get(st) != "vegas":
                    raise ValueError(
                        f"per-stat FAIL: {name}: stat {st!r} fed the Vegas "
                        "leg but is not 'vegas'-attributed in the FDS "
                        "payload — projection stats must never feed Vegas")
            # Recompute from vegas inputs only; any leak diverges here.
            expect = recompute_row_points(
                {"pos": r.get("pos"), "vegas_stats_used": r.get("vegas_stats_used")})
            for col, sc in (("vegas_std", "standard"),
                            ("vegas_half", "half_ppr"),
                            ("vegas_ppr", "ppr")):
                if r.get(col) != expect[sc]:
                    raise ValueError(
                        f"vegas-column FAIL: {name}: {col}={r.get(col)} != "
                        f"recomputed {expect[sc]} from vegas-attributed "
                        "stats only — a projection stat leaked into a "
                        "Vegas column")
        elif leg == "propline":
            # PropLine-primary (2026-09-18): the FDS fallback fills gaps
            # only — a propline-leg row must never sit in the FDS added
            # set, or fallback output is masquerading as the primary leg.
            if key in fds_keys:
                raise ValueError(
                    f"never-blend FAIL: {name}: propline leg but key is in "
                    "the FDS fallback added set — FDS fills gaps, never "
                    "the primary")
        else:  # local leg
            if key in fds_keys and name not in override_names:
                raise ValueError(
                    f"never-blend FAIL: {name}: local leg displaces the "
                    "FDS primary without a recorded disagreement override "
                    "— local wins only on a material audit disagreement")
    return True


def fds_vintage_note(payload, vegas_stats_used=None):
    """Snapshot vintage_note for FDS-derived rows: provenance explicit and
    human-readable at the DB row level, including which stats fed the
    number (vegas-attributed only)."""
    used = (", ".join(sorted((vegas_stats_used or {})))
            or "none — no vegas-attributed stats")
    return (
        "fds-derived: fantasy points recomputed LOCALLY from First Down "
        "Studio's vegas-attributed translated stats only "
        f"({used}); FDS projection-attributed stats excluded. Snapshot "
        f"{payload.get('snapshot_id')}, generated "
        f"{payload.get('snapshot_generated_at')}, fetched "
        f"{payload.get('fetched_at')}. FDS discloses no raw lines/odds, no "
        "bookmaker names, no full translation methodology. NOT calculated "
        "from raw sportsbook odds.")
