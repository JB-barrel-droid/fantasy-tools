#!/usr/bin/env python3
"""Repo-owned players.json bake for the trade-value chart.

Deterministic: same inputs -> byte-identical players.json. The PRIMARY and
scheduled writer of data/fixtures/current/players.json — never hand-edit
that file.

Writer contract (JEG-423, verified 2026-10-05): bake_players.py is the only
scheduled writer; no workflow (rebuild-chain.yml etc.) or Makefile target
writes the fixture through anything else. One surgical, manual-only tool
also writes the fixture, in an emergency path when the full bake cannot
run (e.g. Supabase unreachable); it is called by no automation and touches
only its own field family, so baked values are untouched:
  - pipelines/annotate_cbsros_ppg.py — refreshes cbsros_* fields + the
    cbsros meta block from the latest CBS ROS snapshot (same intake the
    full bake uses; the bake normally writes these itself).
(Note: pipelines/refresh_players_espn_fields.py was retired by JEG-402 and
is no longer a writer.)
Anything else claiming to write players.json is a bug.

Inputs (all repo-local unless noted):
  - Supabase (via the supabase-football-signal skill):
      teams, games           (games-remaining math, team-id -> abbr)
      players                (canonical names + position + team_id,
                              via lib.canonical_players)
  - data/inputs/espn_projections.csv        (ESPN season projections, ROS)
                                              -- PRIMARY PROJECTION LEG
  - data/inputs/razzball_projections.csv    (Razzball per-game projections)
  - data/inputs/espn_k_ppg_2026-09-21.json  (ESPN kicker per-game rates)
  - data/inputs/espn_dst_ros_2026-09-21.json (ESPN DST per-game rates)
  - data/inputs/ecr_draft.json              (preseason draft ECR ranks,
                                              preseason reference only)

Outputs:
  - data/fixtures/current/players.json      (the chart fixture)
  - data/fixtures/current/actuals_<today>.json (key-keyed banked actuals,
      for future prior-week movement)
  - data/fixtures/snapshots/players_<date>.json (pre-rebuild snapshot of
      the previous fixture, for genuine bake-over-bake deltas)

Fail-closed gates (each aborts the build, never publishes partial data):
  - ESPN intake priced zero (no NPC projections to set the primary value)
  - canonical-name gate: every display name == players.full_name for its key
  - source-accounting audit: pricing labels, ESPN-purity, Razzball doubling guard
  - ESPN purity (user directive 2026-09-21, extended 2026-10-05): every
    ESPN-labeled field is sourced ONLY from ESPN projections. The PRIMARY
    leg (blend_ros/blend_ppg) is 100% ESPN for skill players (pricing=
    "espn_only"); ESPN-purity now applies to skill players as the
    primary leg, not just K/DST. K/DST are also ESPN-priced.

Ported from the retired trade-value/build_values.py (2026-09-22) with one
deliberate fix: the retired bake appended K/DST rows with pricing="espn"
but a later universal loop overwrote every row's pricing to "experts_only"
while the comments claimed K/DST were ESPN-priced. This bake sets the
pricing label per position and the audit rejects any other label.

JEG-ECR-EXIT (2026-10-05): the prior blend (ECR-laden, 2026-09-16) is
replaced by ESPN as the primary leg. ESPN is already rest-of-season
(no actuals subtraction). Full-season ECR content / tables / loaders /
checks have been retired.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "pipelines" / "lib"
sys.path.insert(0, str(LIB))

from canonical_players import (  # noqa: E402
    load_registry, resolve, resolve_skill, require_canonical_name,
    assert_canonical_names, norm_plain,
)
from scoring import fantasy_points  # noqa: E402
from dataset_status import build_dataset_status  # noqa: E402
from games_remaining import (  # noqa: E402
    load_byes, schedule_problems, window_from_csv, games_by_team,
    canonical_team, PPG_DECIMALS,
)
from preseason_ecr import (  # noqa: E402
    load_preseason_ecr_ranks, annotate_rows, provenance_note as pecr_note,
)

SKILL_BIN = os.environ.get(
    "SUPABASE_FOOTBALL_SIGNAL_BIN",
    os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"),
)

FIXTURE_DIR = ROOT / "data" / "fixtures" / "current"
SNAPSHOT_DIR = ROOT / "data" / "fixtures" / "snapshots"
INPUTS_DIR = ROOT / "data" / "inputs"


# ---------------------------------------------------------------------------
# Supabase query layer (PostgREST via the skill's sbclient)
# ---------------------------------------------------------------------------

def _sbclient():
    if SKILL_BIN not in sys.path:
        sys.path.insert(0, SKILL_BIN)
    import sbclient
    return sbclient


def query_all(table, params):
    """get_all wrapper returning a list of row dicts."""
    return _sbclient().get_all(table, params)


# ---------------------------------------------------------------------------
# Intake helpers
# ---------------------------------------------------------------------------

COMPS = ["passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
         "receptions", "receiving_yards", "receiving_tds"]

NEED = {
    "QB": ["passing_yards", "passing_tds"],
    "RB": ["rushing_yards", "rushing_tds"],
    "WR": ["receiving_yards", "receptions", "receiving_tds"],
    "TE": ["receiving_yards", "receptions", "receiving_tds"],
}

ESPN_COMPS = {
    "r_pass_yds": "passing_yards",
    "r_pass_tds": "passing_tds",
    "r_rush_yds": "rushing_yards",
    "r_rush_tds": "rushing_tds",
    "r_receptions": "receptions",
    "r_rec_yds": "receiving_yards",
    "r_rec_tds": "receiving_tds",
}

RZ_LEGS = (("rz_std_ppg", "standard"),
           ("rz_half_ppr_ppg", "half_ppr"),
           ("rz_ppr_ppg", "ppr"))

# Team-abbreviation variants for the games-remaining lookup.
# The games table (via teams.abbreviation) is canonical; source CSVs use
# variants. ESPN's CSV uses WSH for Washington (canonical WAS) — same class
# as the long-standing LAR->LA / JAC->JAX variants. canonical_players
# documents ESPN's LAR/WSH vs canonical LA/WAS for DST tokens.
_TEAM_ABBR_FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS"}

# Stale teams-table rows (STL/SD/OAK/LAR alongside LA/LAC/LV) that must map
# to the current abbreviation before the games-remaining lookup. Mirrors
# canonical_players._STALE_ABBR.
_STALE_TEAM_FIX = {"LAR": "LA", "JAC": "JAX", "STL": "LA",
                  "OAK": "LV", "SD": "LAC"}


def _resolve_team_abbr(espn_team, key, registry, team_abbr):
    """Resolve the display/games team abbreviation for one baked row.

    Primary: the ESPN CSV team, normalized through _TEAM_ABBR_FIX.
    Fallback: the canonical registry's team_id -> teams-table abbreviation
    (normalized through _STALE_TEAM_FIX) when the CSV is silent — the
    module docstring's long-standing contract. Returns "" only when neither
    source knows the team; the caller treats "" as unknown (no per-game
    fields), never as a guess.
    """
    team = (espn_team or "").strip().upper()
    if team:
        return _TEAM_ABBR_FIX.get(team, team)
    entry = registry.by_key.get(key) if registry is not None else None
    tid = entry.get("team_id") if entry else None
    abbr = (team_abbr.get(tid) or "").strip().upper() if tid else ""
    return _STALE_TEAM_FIX.get(abbr, abbr)

# CBS ROS snapshot columns (pre-computed per-game rates: ROS totals / gp).
CBSROS_LEGS = (("per_game_standard", "standard"),
               ("per_game_half_ppr", "half_ppr"),
               ("per_game_ppr", "ppr"))

CBSROS_SNAPSHOT_DIR = ROOT / "data" / "raw" / "sources" / "cbsros"
RAZZBALL_SNAPSHOT_DIR = ROOT / "data" / "raw" / "sources" / "razzball"

SCORINGS = ("standard", "half_ppr", "ppr")


def _elig_flag(v):
    return str(v or "").strip().lower() in ("true", "1", "yes")


def _resolve_csv_row(name, pos, source_label, registry):
    name = (name or "").strip()
    if not name:
        return None
    try:
        if pos in ("QB", "RB", "WR", "TE"):
            return resolve(name, position=pos, registry=registry)
        return resolve_skill(name, registry=registry)
    except Exception as e:  # noqa: BLE001 - fail-closed, logged
        print(f"{source_label} intake: unresolved '{name}' ({pos}): {e}",
              flush=True)
        return None


def _intake_razzball(path, registry):
    med, snap = {}, None
    n_rows = n_unres = n_incomplete = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            n_rows += 1
            d = (r.get("razzball_snapshot_date") or "").strip()
            if d:
                snap = d if snap is None else max(snap, d)
            key = _resolve_csv_row(r.get("player", ""), (r.get("pos") or "").strip(),
                                   "razzball", registry)
            if key is None:
                n_unres += 1
                continue
            ppg = {}
            for csv_col, s in RZ_LEGS:
                raw = r.get(csv_col)
                if raw is None or str(raw).strip() == "":
                    continue
                ppg[s] = float(raw)
            if len(ppg) == 3:
                if key in med:
                    print(f"razzball intake WARNING: duplicate key: {key} "
                          f"({r.get('player')})")
                med[key] = ppg
            else:
                n_incomplete += 1
    print(f"razzball intake: {len(med)} priced players "
          f"({n_rows} rows, {n_incomplete} partial-ppg excluded), "
          f"snapshot {snap}, {n_unres} unresolved")
    return med, snap


def _latest_razzball_snapshot():
    """Newest data/raw/sources/razzball/<date>/snapshot.json by vintage_date.

    import_supabase_references.py --source razzball writes it from the latest
    public.razzball_projections vintage. None when there is none.
    """
    best, best_vintage = None, ""
    for p in sorted(RAZZBALL_SNAPSHOT_DIR.glob("*/snapshot.json")):
        try:
            v = str(json.loads(p.read_text(encoding="utf-8")).get("vintage_date") or "")
        except Exception:  # noqa: BLE001 - unparseable snapshot is skipped
            continue
        if v and (v, p.parent.name) > (best_vintage, best.parent.name if best else ""):
            best, best_vintage = p, v
    return best


def _intake_razzball_snapshot(snapshot_path, registry):
    """Razzball snapshot (Supabase import) intake -> {player_key: {scoring: ppg}}.

    GAP-RAZZBALL-SUFFIX-POOL (2026-10-08): the browser's Razzball (rz_ppg)
    was baked from data/inputs/razzball_projections.csv, a 2026-09-22 file
    nothing refreshed, while the chain's Razzball section moved on. This
    reads the snapshot the chain's Razzball legs read, so both price one
    vintage. Identity is the row's player_key (the saver's verified key);
    a row without one (a file-built snapshot) resolves by name, fail-closed.
    Only rows with all three published per-game columns are priced.
    """
    snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    vintage = snap.get("vintage_date")
    if not vintage:
        raise SystemExit("FAIL-CLOSED: Razzball snapshot has no vintage_date.")
    med = {}
    n_rows = n_unres = n_incomplete = 0
    for r in snap.get("rows", []):
        n_rows += 1
        key = r.get("player_key")
        if not isinstance(key, int) or isinstance(key, bool):
            key = _resolve_csv_row(r.get("player_name", ""), (r.get("pos") or "").strip(),
                                   "razzball", registry)
        if key is None:
            n_unres += 1
            continue
        ppg = {}
        for col, s in RZ_LEGS:
            v = r.get(col)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                ppg[s] = float(v)
        if len(ppg) == 3:
            if key in med:
                print(f"razzball intake WARNING: duplicate key: {key} "
                      f"({r.get('player_name')})")
            med[key] = ppg
        else:
            n_incomplete += 1
    print(f"razzball intake: {len(med)} priced players "
          f"({n_rows} rows, {n_incomplete} partial-ppg excluded), "
          f"snapshot {vintage} ({snapshot_path}), {n_unres} unresolved")
    return med, vintage


def razzball_intake(args, registry):
    """The browser's Razzball: the imported snapshot, else the legacy CSV."""
    rz_snapshot = getattr(args, "razzball_snapshot", None)
    if rz_snapshot:
        return _intake_razzball_snapshot(rz_snapshot, registry)
    print("razzball intake WARNING: no Razzball snapshot; reading the "
          f"committed CSV {args.razzball_csv}. players.json rz_snapshot must "
          "match the Razzball section vintage or validate fails "
          "(tests/test_razzball_refresh.py).")
    return _intake_razzball(args.razzball_csv, registry)


def _latest_cbsros_snapshot():
    """Return the latest data/raw/sources/cbsros/<date>/snapshot.json path.

    Latest = max vintage_date among snapshots that parse; ties broken by
    directory name. Fail-closed: SystemExit when none parse.
    """
    cands = sorted(CBSROS_SNAPSHOT_DIR.glob("*/snapshot.json"))
    best, best_vintage = None, ""
    for p in cands:
        try:
            v = str(json.loads(p.read_text(encoding="utf-8"))
                    .get("vintage_date") or "")
        except Exception:  # noqa: BLE001 - unparseable snapshot is skipped
            continue
        if (v, p.parent.name) > (best_vintage, best.parent.name if best else ""):
            best, best_vintage = p, v
    if best is None:
        raise SystemExit(
            "FAIL-CLOSED: no parseable CBS ROS snapshot under "
            f"{CBSROS_SNAPSHOT_DIR} — refusing to bake without CBS data.")
    return best


def _intake_cbsros(snapshot_path, registry):
    """CBS ROS snapshot intake -> {player_key: {scoring: per-game ppg}}.

    The snapshot carries pre-computed per-game rates (per_game_standard /
    per_game_half_ppr / per_game_ppr = ROS totals / gp). Only rows with all
    three scorings finite are priced (never partially). Identity is the
    row's player_key (the saver's verified key, carried by
    export_cbsros_snapshot.py and the Supabase import); a row without one
    (a file-built snapshot) resolves by name through the canonical naming
    table, fail-closed. Returns (med, vintage).

    GAP-CBSROS-BAKE-IDENTITY (2026-10-08): re-resolving the saved
    player_norm by name dropped 'chigoziem okonkwo' and 'mitch trubisky'
    (the saver and the legs applied verified aliases the registry once lacked; it now reads the same list),
    so the browser priced a different TE pool from the section.
    """
    snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    vintage = snap.get("vintage_date")
    if not vintage:
        raise SystemExit("FAIL-CLOSED: CBS ROS snapshot has no vintage_date.")
    med = {}
    n_rows = n_unres = n_incomplete = 0
    for r in snap.get("rows", []):
        n_rows += 1
        key = r.get("player_key")
        if not isinstance(key, int) or isinstance(key, bool):
            key = _resolve_csv_row(r.get("player_name", ""),
                                   (r.get("pos") or "").strip(),
                                   "cbsros", registry)
        if key is None:
            n_unres += 1
            continue
        ppg = {}
        for col, s in CBSROS_LEGS:
            v = r.get(col)
            if isinstance(v, (int, float)) and math.isfinite(v):
                ppg[s] = float(v)
        if len(ppg) == 3:
            if key in med:
                print(f"cbsros intake WARNING: duplicate key: {key} "
                      f"({r.get('player_name')})")
            med[key] = ppg
        else:
            n_incomplete += 1
    print(f"cbsros intake: {len(med)} priced players "
          f"({n_rows} rows, {n_incomplete} partial-ppg excluded), "
          f"vintage {vintage}, {n_unres} unresolved")
    return med, vintage


def pts(stats, scoring):
    return fantasy_points(stats, scoring)

# ---------------------------------------------------------------------------
# Main bake
# ---------------------------------------------------------------------------

def fetch_espn_intake(path, registry):
    """ESPN skill-player intake from data/inputs/espn_projections.csv.

    Returns (espn_med, espn_snapshot_date). espn_med maps player_key ->
    {"comps": {...}, "pos": ..., "team": ...}. Fails closed when the CSV
    prices zero eligible skill players — never bakes a chart with
    silently missing primary-leg intake.

    JEG-ECR-EXIT (2026-10-05): replaces fetch_ecr_intake(). The prior
    fetch_ecr_intake() lived on full-season ECR tables
    (fp_season_latest_norm / fp_season_projections); ESPN is already
    rest-of-season so no snapshot_date / content-vintage gate applies.
    """
    espn_med, snap = {}, None
    n_rows = n_unres = n_unpriced = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            n_rows += 1
            d = (r.get("espn_snapshot_date") or "").strip()
            if d:
                snap = d if snap is None else max(snap, d)
            if not _elig_flag(r.get("eligible")):
                continue
            pos = (r.get("pos") or "").strip()
            key = _resolve_csv_row(r.get("player", ""), pos, "espn", registry)
            if key is None:
                n_unres += 1
                continue
            comps = {}
            for csv_col, comp in ESPN_COMPS.items():
                raw = r.get(csv_col)
                if raw is None or str(raw).strip() == "":
                    continue
                comps[comp] = float(raw)
            if not comps:
                n_unpriced += 1
                continue
            if key in espn_med:
                print(f"espn intake WARNING: duplicate key: {key} "
                      f"({r.get('player')})")
            espn_med[key] = {
                "comps": comps,
                "pos": pos,
                "team": (r.get("team") or "").strip(),
            }
    print(f"espn intake: {len(espn_med)} priced players "
          f"({n_rows} rows, {n_unpriced} unpriced excluded, "
          f"{n_unres} unresolved), snapshot {snap}")
    if not espn_med:
        raise SystemExit("FAIL-CLOSED: ESPN intake priced 0 skill players — "
                         "refusing to bake a chart with no primary-leg input.")
    return espn_med, snap


SKILL_POS = ("QB", "RB", "WR", "TE")


def espn_zero_universe(espn_csv, comparison_fixture, espn_med, registry):
    """Skill players the board carries at an ESPN value of zero (JEG-392).

    JEG-ECR-EXIT narrowed the board to ESPN's 348 *eligible* skill players,
    which orphaned 185 identities the comparison artifact still prices and
    made every downstream universe assumption (pie totals, bench mix, CBS
    ROS coverage, the source-chain coverage review) fail. ESPN's own
    projection for those players is zero, so carrying them at zero is the
    ESPN-only value, not a fill:

      - "ineligible": listed in the ESPN CSV with eligible=False (ESPN
        projects 0; includes season-ending IR, which the chart badges via
        the comparison artifact's espn_zeroed list per the IR rule).
      - "absent": not in the ESPN CSV at all, but priced/keyed by the
        comparison artifact (ESPN publishes no projection = 0).

    Returns {player_key: {"pos", "team", "espn_status"}}. Never includes a
    key already in espn_med; identity still resolves fail-closed through the
    canonical registry (unresolvable names are skipped, never guessed).
    """
    out = {}
    with open(espn_csv, newline="") as f:
        for r in csv.DictReader(f):
            if _elig_flag(r.get("eligible")):
                continue
            pos = (r.get("pos") or "").strip()
            if pos not in SKILL_POS:
                continue
            key = _resolve_csv_row(r.get("player", ""), pos, "espn-zero",
                                   registry)
            if key is None or key in espn_med or key in out:
                continue
            out[key] = {"pos": pos, "team": (r.get("team") or "").strip(),
                        "espn_status": "ineligible"}
    if comparison_fixture and Path(comparison_fixture).exists():
        payload = json.loads(Path(comparison_fixture).read_text(encoding="utf-8"))
        for key in set((payload.get("player_keys") or {}).values()):
            if not isinstance(key, int) or key in espn_med or key in out:
                continue
            entry = registry.by_key.get(key) if registry is not None else None
            if not entry or entry.get("position") not in SKILL_POS:
                continue
            out[key] = {"pos": entry["position"], "team": "",
                        "espn_status": "absent"}
    n_inel = sum(1 for v in out.values() if v["espn_status"] == "ineligible")
    print(f"espn zero universe: {len(out)} skill players at ESPN 0 "
          f"({n_inel} ineligible, {len(out) - n_inel} absent from ESPN CSV)")
    return out


def team_games_remaining(game_rows, team_abbr, espn_csv):
    """{team: games inside ESPN's ROS window}, (first, last ROS week).

    The window is the ESPN CSV's own weeks_covered (what its ROS totals sum
    over); byes come from data/inputs/nfl_byes_2026.json, verified against
    the schedule rows (Supabase public.games: week/home/away) -- fail closed
    on any disagreement. games.status is deliberately not read: nothing
    keeps it current (GAP-GAMES-REMAINING-STALE).
    """
    byes, season_weeks = load_byes()
    problems = schedule_problems(byes, season_weeks, game_rows, team_abbr)
    if problems:
        raise SystemExit("FAIL-CLOSED: bye table disagrees with the Supabase "
                         "schedule:\n  " + "\n  ".join(problems))
    window = window_from_csv(espn_csv)
    return games_by_team(window, byes), window


def bake(args):
    registry = load_registry()

    # JEG-405 (2026-10-05): assign `today` once at the top of bake().
    # The prior-snapshot scan below reads it before the meta block ran,
    # which raised UnboundLocalError on any bake with an existing snapshot.
    today = str(_date.today())

    # ---- ESPN intake (PRIMARY LEG) -----------------------------------------
    # JEG-ECR-EXIT (2026-10-05): ESPN replaces ECR as the primary blend
    # leg. ESPN is already rest-of-season (no actuals subtraction). No
    # content-vintage gate: ESPN is daily-morning pulled and overwritten
    # in place; freshness is checked at the source pull, not here.
    espn_med, espn_snapshot_date = fetch_espn_intake(args.espn_csv, registry)

    # ---- Other comparison intakes (unchanged) --------------------------------
    rz_med, rz_snapshot_date = razzball_intake(args, registry)
    cbsros_snapshot = args.cbsros_snapshot or _latest_cbsros_snapshot()
    cbsros_med, cbsros_snapshot_date = _intake_cbsros(cbsros_snapshot,
                                                      registry)

    # ---- Games remaining -----------------------------------------------------
    team_rows = query_all("teams", "?select=id,abbreviation&abbreviation=not.is.null")
    team_abbr = {r["id"]: r["abbreviation"] for r in team_rows}
    # GAP-GAMES-REMAINING-STALE (2026-10-08): games remaining = the games each
    # team plays inside ESPN's own ROS window (the CSV's weeks_covered), from
    # the season's bye table -- never from games.status, which nothing keeps
    # current (it stopped at week 2 final, giving 15/16 where the truth was 13).
    # The bye table is cross-checked against the Supabase schedule; any
    # disagreement aborts the bake.
    game_rows = query_all(
        "games", "?select=week,home_team_id,away_team_id&season=eq.2026")
    games_left, ros_window = team_games_remaining(game_rows, team_abbr,
                                                  args.espn_csv)
    print(f"games remaining: ESPN ROS weeks {ros_window[0]}-{ros_window[1]}, "
          f"per team {sorted(set(games_left.values()))}")

    # ---- Skill-player rows ----------------------------------------------------
    # Iterate over ESPN intake keys (every charted skill player has an
    # ESPN projection). pos / team come from the ESPN CSV row; fall back
    # to the canonical registry when the CSV is silent on one (DST / K
    # rows are appended separately below).
    espn_zero = espn_zero_universe(
        args.espn_csv, getattr(args, "comparison_fixture", None), espn_med,
        registry)
    skill_rows = [(k, r, None) for k, r in espn_med.items()]
    skill_rows += [(k, {"comps": {}, "pos": z["pos"], "team": z["team"]},
                    z["espn_status"]) for k, z in sorted(espn_zero.items())]

    players = []
    for key, espn_row, espn_status in skill_rows:
        v = espn_row["comps"]
        pos = espn_row["pos"]
        # Team: ESPN CSV first (variant-normalized), canonical registry
        # fallback when the CSV is silent.
        team = _resolve_team_abbr(espn_row["team"], key, registry,
                                  team_abbr)

        # ESPN-PRIMARY (2026-10-05, JEG-ECR-EXIT): the board's primary
        # number IS the ESPN leg. ESPN is already rest-of-season so
        # espn_ros_comps is taken as-is (no actuals subtraction). Missing
        # components default to 0.0 — fantasy_points() treats 0 identically
        # to "missing" (stats.get(k, 0.0)) so no KeyError and no fill.
        espn_ros_comps = {c: v.get(c, 0.0) for c in COMPS}
        blend = dict(espn_ros_comps)  # primary = ESPN comps
        espn_complete = pos in NEED and all(c in v for c in NEED[pos])
        espn_covered = sorted(c for c in COMPS if c in v)

        z = rz_med.get(key, {})
        rz_complete = (pos in ("QB", "RB", "WR", "TE")
                       and all(s in z for s in SCORINGS))
        rz_covered = sorted(s for s in SCORINGS if s in z)

        c = cbsros_med.get(key, {})
        cbsros_complete = (pos in ("QB", "RB", "WR", "TE")
                           and all(s in c for s in SCORINGS))
        cbsros_covered = sorted(s for s in SCORINGS if s in c)

        row = {
            "player_key": key,
            "name": require_canonical_name(key, registry=registry),
            "pos": pos,
            "team": team,
            # Primary leg = ESPN (already ROS, no actuals subtraction).
            "espn_ros": {s: pts(blend, s) for s in SCORINGS},
            "espn_complete": bool(espn_complete),
            "espn_comp_count": sum(1 for c in COMPS if c in v),
            "espn_covered": espn_covered,
            "rz_complete": bool(rz_complete),
            "rz_comp_count": len(rz_covered),
            "rz_covered": rz_covered,
            "cbsros_complete": bool(cbsros_complete),
            "cbsros_comp_count": len(cbsros_covered),
            "cbsros_covered": cbsros_covered,
            "blend_ros": {s: pts(blend, s) for s in SCORINGS},
            # pricing label: the board's primary number is 100% ESPN.
            # ESPN-purity (extended 2026-10-05) now covers skill players
            # too — the primary blend is ESPN-sourced for every position.
            "pricing": "espn_only",
        }
        if espn_status:
            # JEG-392: ESPN projects this player at zero (ineligible or not
            # published). The ESPN-only primary value is therefore 0.
            row["espn_zeroed"] = True
            row["espn_status"] = espn_status

        # per-game points: ROS fantasy points / team games remaining
        # (team already variant-normalized by _resolve_team_abbr).
        gr = games_left.get(canonical_team(team))
        row["games_remaining"] = gr
        # JEG-392: ESPN-zeroed rows publish no ESPN per-game projection and
        # no ESPN-relative deltas (ESPN has none to compare against), the
        # same contract the pre-JEG-ECR-EXIT fixture used for ESPN-unpriced
        # players. The chart's ESPN pools (curves, waiver lines, bench mix)
        # therefore see exactly the ESPN-priced players, as before.
        has_espn = not espn_status
        if gr:
            if has_espn:
                row["blend_ppg"] = {s: round(v / gr, PPG_DECIMALS) for s, v in row["blend_ros"].items()}
                row["espn_ppg"] = {s: round(v / gr, PPG_DECIMALS) for s, v in row["espn_ros"].items()}
            # Razzball: rz_ros = rz_ppg x the pipeline's OWN games_remaining.
            # Razzball's displayed Games/totals are doubled (Allen: 32 games)
            # and are NEVER used. The source-accounting audit below fails the
            # build if rz_filled_ros != rz_ppg x games_remaining.
            if rz_complete:
                row["rz_ppg"] = {s: round(z[s], PPG_DECIMALS) for s in SCORINGS}
                row["rz_ros"] = {s: round(z[s] * gr, 2) for s in SCORINGS}
                row["rz_filled_ppg"] = dict(row["rz_ppg"])
                row["rz_filled_ros"] = dict(row["rz_ros"])
                if has_espn:
                    row["delta_rz_espn"] = round(
                        row["rz_filled_ros"]["ppr"] - row["espn_ros"]["ppr"], 2)
                    row["delta_rz_espn_ppg"] = round(
                        row["rz_filled_ppg"]["ppr"] - row["espn_ppg"]["ppr"], 2)
            # CBS ROS: per-game rates are pre-computed in the snapshot
            # (per_game_standard/half_ppr/ppr = ROS totals / gp). No ROS
            # fill here: the curve re-prices live from cbsros_ppg via the
            # two-tier math (JEG-33); the comparison dashboard reads the
            # baked cbsros DDF leg.
            if cbsros_complete:
                row["cbsros_ppg"] = {s: round(c[s], PPG_DECIMALS) for s in SCORINGS}
        players.append(row)

    # ---- Kickers & team defenses: ESPN projections only ----------------------
    # ESPN-purity directive (2026-09-21): every ESPN-labeled value comes from
    # ESPN projections only — no expert blend anywhere in K/DST pricing.
    # K: ESPN per-game rates (filterSlotIds [17]). DST: ESPN per-game
    # component recipe (filterSlotIds [16]).
    k_data = json.load(open(args.k_json))
    dst_data = json.load(open(args.dst_json))
    k_ppg = {k["name"]: k["ppg"] for k in k_data["kickers"]}
    dst_ppg = {d["abbr"]: d["ppg"] for d in dst_data["defenses"]}
    kdst_snapshot = str(k_data.get("snapshot_date") or dst_data.get("snapshot_date")
                        or "?")
    kdst_unresolved = []
    window_len = ros_window[1] - ros_window[0] + 1

    def kdst_games(team, required=False):
        games = games_left.get(canonical_team(team)) if team else None
        if games:
            return games
        if required:
            raise SystemExit(f"FAIL-CLOSED: no games remaining for K/DST team {team!r}.")
        return window_len

    for name, ppg in sorted(k_ppg.items(), key=lambda kv: -kv[1]):
        kk = resolve(name, position="K", registry=registry)
        if kk is None:
            kdst_unresolved.append(("K", name))
            continue
        # GAP-KDST-GAMES-FIXED: the kicker's team's games inside ESPN's ROS
        # window, the same count skill players use (was a fixed 16). The K
        # input carries no team abbreviation, so the team comes from the
        # canonical registry; a kicker with no team divides by the window
        # length, as the leg does for teamless rows.
        gr = kdst_games(_resolve_team_abbr(None, kk, registry, team_abbr))
        ros = round(ppg * gr, 2)
        same3 = {"standard": ros, "half_ppr": ros, "ppr": ros}
        ppg3 = {"standard": ppg, "half_ppr": ppg, "ppr": ppg}
        players.append({
            "player_key": kk,
            "name": require_canonical_name(kk, registry=registry),
            "pos": "K",
            "team": None,
            "espn_ros": dict(same3), "blend_ros": dict(same3),
            "espn_ppg": dict(ppg3), "blend_ppg": dict(ppg3),
            "games_remaining": gr,
            # K/DST price from ESPN only — never experts_only.
            "pricing": "espn_only",
            "espn_complete": True, "espn_comp_count": 1, "espn_covered": ["k"],
            "rz_complete": False, "rz_comp_count": 0, "rz_covered": [],
            "cbsros_complete": False, "cbsros_comp_count": 0, "cbsros_covered": [],
            "prior_espn_ros": None, "prior_blend_ros": None,
        })
    for abbr, ppg in sorted(dst_ppg.items(), key=lambda kv: -kv[1]):
        kk = resolve(abbr, position="DST", registry=registry)
        if kk is None:
            kdst_unresolved.append(("DST", abbr))
            continue
        # GAP-KDST-GAMES-FIXED: games inside ESPN's ROS window (was a fixed
        # 15). A defense's team is always known; fail closed if it is not.
        gr = kdst_games(_TEAM_ABBR_FIX.get(abbr, abbr), required=True)
        ros = round(ppg * gr, 2)
        same3 = {"standard": ros, "half_ppr": ros, "ppr": ros}
        ppg3 = {"standard": ppg, "half_ppr": ppg, "ppr": ppg}
        players.append({
            "player_key": kk,
            "name": require_canonical_name(kk, registry=registry),
            "pos": "DST",
            "team": _TEAM_ABBR_FIX.get(abbr, abbr),
            "espn_ros": dict(same3), "blend_ros": dict(same3),
            "espn_ppg": dict(ppg3), "blend_ppg": dict(ppg3),
            "games_remaining": gr,
            "pricing": "espn_only",
            "espn_complete": True, "espn_comp_count": 1, "espn_covered": ["dst"],
            "rz_complete": False, "rz_comp_count": 0, "rz_covered": [],
            "cbsros_complete": False, "cbsros_comp_count": 0, "cbsros_covered": [],
            "prior_espn_ros": None, "prior_blend_ros": None,
        })
    if kdst_unresolved:
        print(f"K/DST ESPN unresolved (excluded): {kdst_unresolved}",
              file=sys.stderr)

    # rank by primary (ESPN-based) full-PPR value for convenience
    players.sort(key=lambda p: p["blend_ros"]["ppr"], reverse=True)

    # ---- prior bake snapshot: ROS values for week-over-week movement ---------
    # JEG-ECR-EXIT (2026-10-05): the prior section previously read
    # fp_season_projections at a prior snapshot_date and subtracted banked
    # actuals. With ECR retired, the prior is sourced from the previous
    # baked fixture (data/fixtures/snapshots/players_<date>.json), written
    # by every bake just before the rebuild. blend_ros is now ESPN-primary
    # so prior_blend_ros / prior_espn_ros carry the same value.
    prior_date = None
    prior_espn_ros, prior_blend_ros = {}, {}
    snap_candidates = []
    for sp in SNAPSHOT_DIR.glob("players_*.json"):
        try:
            d = json.loads(sp.read_text()).get("meta", {}).get("as_of", "")
            if d and d < today:
                snap_candidates.append((d, sp))
        except Exception:
            continue
    if snap_candidates:
        prior_date, prior_path = sorted(snap_candidates)[-1]
        prior_payload = json.load(open(prior_path))
        for pp in prior_payload.get("players", []):
            pk = pp.get("player_key")
            if pk is None:
                continue
            prior_espn_ros[pk] = pp.get("espn_ros")
            prior_blend_ros[pk] = pp.get("blend_ros")
        print(f"prior bake: {prior_path.name} "
              f"({len(prior_espn_ros)} players with espn_ros/blend_ros)")
    for p in players:
        pk = p["player_key"]
        if pk in prior_espn_ros:
            p["prior_espn_ros"] = prior_espn_ros[pk]
            p["prior_blend_ros"] = prior_blend_ros[pk]
        elif "prior_espn_ros" not in p:
            p["prior_espn_ros"] = None
            p["prior_blend_ros"] = None

    # ---- positional shade / demeaned deltas -----------------------------------
    # JEG-ECR-EXIT (2026-10-05): the shade baseline was ESPN-vs-ECR
    # (ESPN reads compared to the ECR primary). With ESPN now primary,
    # the comparison shade stays meaningful (Razzball vs ESPN) but
    # the ECR-vs-ESPN shade disappears (it is now zero by construction).
    def _shade(leg_ppg, leg_complete, label):
        out = {}
        for pos in ("QB", "RB", "WR", "TE"):
            vals = [r[leg_ppg]["ppr"] - r[leg_complete]["ppr"] for r in players
                    if r["pos"] == pos and r.get(leg_ppg) and r.get(leg_complete)
                    # JEG-392: ESPN-zeroed rows measure ESPN's absence, not
                    # its bias; they must not move the positional shade.
                    and not r.get("espn_zeroed")]
            # leg_ppg is the comparison leg, leg_complete is ESPN (primary):
            # shade = mean(comparison_ppg - espn_ppg); positive = ESPN cooler.
            out[pos] = {"ppr": round(sum(vals) / len(vals), 3)} if vals else {"ppr": 0.0}
        return out

    rz_shade_ppg = _shade("rz_filled_ppg", "espn_ppg", "rz")
    # ESPN-vs-ESPN shade is zero by construction (ESPN primary vs itself);
    # keep an empty entry so the meta.disagree_baseline_note can still
    # reference shade_ppg without a structural fork.
    shade_ppg = {p: {"ppr": 0.0} for p in ("QB", "RB", "WR", "TE")}
    for p in players:
        if p.get("delta_rz_espn_ppg") is not None:
            p["delta_rz_espn_ppg_demeaned"] = round(
                p["delta_rz_espn_ppg"] - rz_shade_ppg[p["pos"]]["ppr"], 2)

    # ---- source-accounting audit (fail-closed) ---------------------------------
    # Every row must account for its sources. Pricing labels are set per
    # position above and are NEVER overwritten by a universal loop (the
    # retired bake's defect). ESPN-purity (extended 2026-10-05): every
    # ESPN-labeled value comes from ESPN projections only. The primary
    # blend is 100% ESPN for skill players too — espn_ros IS the primary.
    violations = []
    for p in players:
        pid = f"{p['name']} (key={p['player_key']})"
        pricing = p.get("pricing")
        if p["pos"] in ("K", "DST"):
            if pricing != "espn_only":
                violations.append(f"{pid}: K/DST pricing must be 'espn_only', "
                                  f"got '{pricing}'")
            if not p.get("espn_ros"):
                violations.append(f"{pid}: K/DST espn_ros missing")
        else:
            if pricing != "espn_only":
                violations.append(f"{pid}: skill pricing must be 'espn_only' "
                                  f"(ESPN-primary, JEG-ECR-EXIT), got '{pricing}'")
            if p.get("blend_ros") is None or p.get("espn_ros") is None:
                violations.append(f"{pid}: skill row missing espn/blend legs")
            # ESPN comps consistency: espn_ros must equal pts(espn_ros_comps).
            espn_entry = espn_med.get(p["player_key"])
            if espn_entry:
                v = espn_entry["comps"]
                comps_full = {c: v.get(c, 0.0) for c in COMPS}
                check = {s: pts(comps_full, s) for s in SCORINGS}
                for s in SCORINGS:
                    if abs(check[s] - p["espn_ros"][s]) > 0.01:
                        violations.append(
                            f"{pid}: espn_ros[{s}] inconsistent with "
                            "ESPN-med recomputation")
                        break
        # Razzball doubling guard: rz_filled_ros == rz_ppg x games_remaining.
        if p.get("rz_filled_ros"):
            gr = p.get("games_remaining")
            z = rz_med.get(p["player_key"], {})
            for s in SCORINGS:
                if abs(p["rz_filled_ros"][s] - round(z.get(s, 0) * (gr or 0), 2)) > 0.01:
                    violations.append(
                        f"{pid}: rz_filled_ros[{s}] != rz_ppg x games_remaining "
                        "(Razzball doubled-games guard)")
                    break
        if p.get("rz_complete") and not p.get("rz_filled_ros"):
            violations.append(f"{pid}: complete Razzball coverage but "
                              "rz_filled_ros missing")
    if violations:
        raise SystemExit("SOURCE-ACCOUNTING AUDIT FAILED:\n  " +
                         "\n  ".join(violations))
    print(f"source-accounting audit passed ({len(players)} players)")

    # ---- preseason ECR ranks (preseason reference only, post-ECR-EXIT) ------
    # ECR ranks are preseason-snapshot ranks (data/inputs/ecr_draft.json) —
    # they describe draft rankings before the season started, not the
    # full-season ECR leg that the bake used to consume. Kept for the
    # preseason-rank comparison column; not a runtime input.
    ranks, pecr_report = load_preseason_ecr_ranks(registry=registry)
    annotate_rows(players, ranks)
    print(f"preseason ECR ranks: {pecr_report['resolved']} resolved, "
          f"{pecr_report['unmatched']} unmatched")

    # ---- meta ---------------------------------------------------------------------
    # JEG-405: `today` is assigned once at the top of bake(); do not reassign.
    meta = {
        "as_of": today,
        "prior_blend_snapshot": str(prior_date) if prior_date else None,
        "espn_snapshot": str(espn_snapshot_date),
        "rz_snapshot": str(rz_snapshot_date),
        "cbsros_snapshot": str(cbsros_snapshot_date),
        "n_players": len(players),
        "n_espn_complete": sum(1 for p in players if p["espn_complete"]),
        "n_rz_complete": sum(1 for p in players if p["rz_complete"]),
        "n_cbsros_complete": sum(1 for p in players
                                 if p.get("cbsros_complete")),
        "n_k": sum(1 for p in players if p["pos"] == "K"),
        "n_dst": sum(1 for p in players if p["pos"] == "DST"),
        "kdst_snapshot": kdst_snapshot,
        "kdst_note": ("Kickers and team defenses price from ESPN projections "
                      "only (ESPN-purity directive, 2026-09-21): no expert/ECR "
                      "data anywhere in the K/DST leg. K and DST ROS = ESPN "
                      "per-game rate x the team's games inside ESPN's ROS "
                      "window (same count as skill players; a kicker with no "
                      "registry team uses the window length). Scoring-"
                      "invariant: one number serves standard/half/full."),
        "scoring_note": "No INT/fumble data in season sources; values exclude them.",
        "ppg_note": ("Per-game points = ROS fantasy points / the games the "
                     "team plays inside ESPN's ROS window (weeks_covered "
                     "minus the bye when it falls inside)."),
        "ros_weeks": f"{ros_window[0]}-{ros_window[1]}",
        "espn_note": ("espn_ros/espn_ppg = ESPN primary leg: pure ESPN read "
                      "over priced components, with missing components "
                      "defaulting to 0 (never zero-filled from another input). "
                      "JEG-ECR-EXIT (2026-10-05): ESPN is now the primary leg "
                      "for skill players — espn_ros IS blend_ros for skill "
                      "rows. Every ESPN-labeled field is sourced ONLY from "
                      "ESPN projections."),
        "rz_note": ("rz_ppg = pure Razzball per-game projection read "
                    "(rz_std_ppg / rz_half_ppr_ppg / rz_ppr_ppg — already pure "
                    "per-game rates). rz_ros = rz_ppg x the pipeline's own "
                    "games_remaining: Razzball's displayed Games column and "
                    "counting totals are DOUBLED (e.g. Josh Allen: 32 games) "
                    "and are never used as ROS totals — the source-accounting "
                    "audit fails the build if rz_filled_ros != rz_ppg x "
                    "games_remaining. rz_filled_ppg/rz_filled_ros = Razzball "
                    "where priced (complete reads need no component fill). "
                    "delta_rz_espn(_ppg) is filled minus full ESPN. Verified "
                    "independent third projection source 2026-09-17 (rank corr "
                    "vs ECR 0.78-0.91, never 0.99+; deviations largely "
                    "independent of ESPN). K/DST have no Razzball projections "
                    "(ESPN-priced). Source: the Razzball snapshot imported from "
                    "public.razzball_projections (the same vintage the "
                    "comparison chain's Razzball section is built from); "
                    "rz_snapshot is its vintage."),
        "cbsros_note": ("cbsros_ppg = pure CBS rest-of-season per-game "
                        "projection read (per_game_standard / per_game_half_ppr "
                        "/ per_game_ppr from the CBS ROS snapshot = ROS totals "
                        "/ gp). CBS publishes nonppr totals only; half_ppr/ppr "
                        "add 0.5/1.0 per reception. The curve re-prices live "
                        "from cbsros_ppg through the shared two-tier "
                        "value-above-waivers math (source's own pool and pies, "
                        "never ESPN's). K/DST have no CBS ROS projections."),
        "method_note": ("Primary trade value (blend_ros/blend_ppg): JEG-ECR-EXIT "
                        "(2026-10-05) the primary value IS the ESPN leg — ESPN "
                        "season projections (already rest-of-season, no actuals "
                        "subtraction) translated to fantasy points with the DDF "
                        "value-above-waivers methodology applied. Razzball "
                        "/ CBS ROS live in the comparison columns (no ESPn now "
                        "primary). K/DST player pricing is ESPN (2026-09-21 "
                        "vintage). The chart engine applies the DDF "
                        "value-above-waivers methodology: raw value is projected "
                        "points above the positional waiver line; each 1-point "
                        "slice is priced on a two-tier marginal curve (bench "
                        "rate below the starter line, starter rate above, smooth "
                        "S-curve glide of 25% of starter-minus-waiver); bench "
                        "totals exactly 15% and starters 85% per position before "
                        "rounding; 70-point display scale."),
        "shade_baseline_ppg": shade_ppg,
        "disagree_baseline_note": (
            "JEG-ECR-EXIT (2026-10-05): the prior ESPN-vs-ECR shade baseline "
            "is gone (ESPN is the primary leg, so ESPN-vs-ESPN is zero by "
            "construction). The Razzball comparison shade is still "
            "measured against ESPN: rz_shade_ppg = mean(rz_filled_ppg - "
            "espn_ppg). Positive shade = comparison cooler than ESPN; "
            "negative = warmer. delta_rz_espn_ppg_demeaned "
            "subtract the positional baseline so rank gaps are genuine "
            "ordering differences, not shade."),
        "pricing_note": ("pricing labels are uniform 'espn_only' across all "
                         "positions (JEG-ECR-EXIT 2026-10-05): the primary "
                         "value IS ESPN, with ESPN-purity (every ESPN-labeled "
                         "field sourced ONLY from ESPN projections) extended "
                         "from K/DST-only (2026-09-21) to all charted "
                         "positions. The source-accounting audit rejects any "
                         "other label."),
    }

    # Fail-closed name gate: every display name == players.full_name for its key.
    assert_canonical_names(
        [(p["player_key"], p["name"]) for p in players],
        registry=registry, context="players.json")
    meta["dataset_status"] = build_dataset_status(
        meta, players, snapshot_dir=str(SNAPSHOT_DIR), rz_live=True)
    meta["preseason_ecr"] = pecr_note()

    # ---- snapshot the previous fixture, then write ------------------------------
    out_path = FIXTURE_DIR / "players.json"
    if out_path.exists():
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        prev = json.load(open(out_path))
        prev_asof = (prev.get("meta") or {}).get("as_of", "unknown")
        snap_path = SNAPSHOT_DIR / f"players_{prev_asof}.json"
        if not snap_path.exists():
            snap_path.write_text(json.dumps(prev, indent=1))
            print(f"snapshotted previous fixture -> {snap_path.name}")

    payload = {"meta": meta, "players": players}
    out_path.write_text(json.dumps(payload, indent=1))
    print(f"wrote {out_path} ({len(players)} players)")

    # JEG-ECR-EXIT (2026-10-05): actuals were subtracted from the (now
    # retired) ECR leg. ESPN is already rest-of-season — no actuals needed.
    # The actuals_<date>.json banking is dropped; prior bake deltas now come
    # from the snapshotted previous fixture (data/fixtures/snapshots/).

    # sanity: top 8 primary-value PPR
    for p in players[:8]:
        print(p["name"], p["pos"], p["team"], p["blend_ros"]["ppr"],
              "espn" if p["espn_complete"] else "espn-partial")

    return {"meta": meta, "n_players": len(players)}


def main():
    ap = argparse.ArgumentParser(description="Repo-owned players.json bake")
    ap.add_argument("--espn-csv", default=str(INPUTS_DIR / "espn_projections.csv"))
    ap.add_argument("--razzball-snapshot", default=None,
                    help="Razzball snapshot.json (import_supabase_references.py "
                         "--source razzball); default: latest under "
                         "data/raw/sources/razzball/, else --razzball-csv")
    ap.add_argument("--razzball-csv", default=None,
                    help="legacy Razzball CSV; used only when no snapshot "
                         "exists (or when given explicitly)")
    ap.add_argument("--cbsros-snapshot", default=None,
                    help="CBS ROS snapshot.json path; default: latest dated "
                         "snapshot under data/raw/sources/cbsros/")
    ap.add_argument("--comparison-fixture",
                    default=str(FIXTURE_DIR / "comparison-sources-data.json"),
                    help="comparison artifact whose keyed identities the board "
                         "must carry (JEG-392); ESPN-absent ones bake at 0")
    ap.add_argument("--k-json", default=str(INPUTS_DIR / "espn_k_ppg_2026-09-21.json"))
    ap.add_argument("--dst-json", default=str(INPUTS_DIR / "espn_dst_ros_2026-09-21.json"))
    args = ap.parse_args()
    if args.razzball_snapshot is None and args.razzball_csv is None:
        latest = _latest_razzball_snapshot()
        args.razzball_snapshot = str(latest) if latest else None
    if args.razzball_csv is None:
        args.razzball_csv = str(INPUTS_DIR / "razzball_projections.csv")
    result = bake(args)
    print(json.dumps({k: v for k, v in result["meta"].items()
                      if k in ("as_of", "prior_blend_snapshot",
                               "n_players", "n_espn_complete",
                               "n_rz_complete", "n_cbsros_complete",
                               "n_k", "n_dst")}, indent=1))


if __name__ == "__main__":
    main()
