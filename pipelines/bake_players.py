#!/usr/bin/env python3
"""Repo-owned players.json bake for the trade-value chart.

Deterministic: same inputs -> byte-identical players.json. The ONLY writer
of data/fixtures/current/players.json — never hand-edit that file.

Inputs (all repo-local unless noted):
  - Supabase (via the supabase-football-signal skill):
      fp_season_latest_norm  (ECR expert projections, latest snapshot)
      fp_season_projections  (ECR content-vintage comparison)
      season_actuals_ytd     (banked actuals, subtracted from the ECR leg)
      teams, games           (games-remaining math)
      players                (canonical names, via lib.canonical_players)
  - data/inputs/espn_projections.csv        (ESPN season projections, ROS)
  - data/inputs/prediction_markets_season.csv (PM season ladders, ROS)
  - data/inputs/razzball_projections.csv    (Razzball per-game projections)
  - data/inputs/espn_k_ppg_2026-09-21.json  (ESPN kicker per-game rates)
  - data/inputs/espn_dst_ros_2026-09-21.json (ESPN DST per-game rates)
  - data/inputs/ecr_draft.json              (preseason draft ECR ranks)

Outputs:
  - data/fixtures/current/players.json      (the chart fixture)
  - data/fixtures/current/actuals_<today>.json (key-keyed banked actuals,
      for future prior-week movement)
  - data/fixtures/snapshots/players_<date>.json (pre-rebuild snapshot of
      the previous fixture, for genuine bake-over-bake deltas)

Fail-closed gates (each aborts the build, never publishes partial data):
  - ECR content vintage > 3 days (byte-identical re-pulls reset nothing)
  - season_actuals_ytd stat_keys with no ACT_MAP mapping
  - canonical-name gate: every display name == players.full_name for its key
  - source-accounting audit: pricing labels, ESPN-purity, Razzball doubling guard
  - ESPN purity (user directive 2026-09-21): every ESPN-labeled field is
    sourced ONLY from ESPN projections. K/DST price from ESPN only
    (pricing="espn_only"); skill players are 100% ECR (pricing="experts_only").

Ported from the retired trade-value/build_values.py (2026-09-22) with one
deliberate fix: the retired bake appended K/DST rows with pricing="espn"
but a later universal loop overwrote every row's pricing to "experts_only"
while the comments claimed K/DST were ESPN-priced. This bake sets the
pricing label per position and the audit rejects any other label.
"""

from __future__ import annotations

import argparse
import csv
import json
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

PM_COMPS = dict(ESPN_COMPS)  # same r_* column contract

RZ_LEGS = (("rz_std_ppg", "standard"),
           ("rz_half_ppr_ppg", "half_ppr"),
           ("rz_ppr_ppg", "ppr"))

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


def _intake_csv(path, comp_map, elig_col, label, registry):
    """Generic component CSV intake -> {player_key: {comp: value}}.

    Only non-blank cells become priced components (never zero-filled).
    Returns (med, snapshot_date, rows, unresolved).
    """
    med, snap = {}, None
    n_rows = n_unres = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            n_rows += 1
            d = (r.get("razzball_snapshot_date")
                 or r.get("espn_snapshot_date")
                 or r.get("prediction_markets_snapshot_date") or "").strip()
            if d:
                snap = d if snap is None else max(snap, d)
            if not _elig_flag(r.get(elig_col)):
                continue
            key = _resolve_csv_row(r.get("player", ""), (r.get("pos") or "").strip(),
                                   label, registry)
            if key is None:
                n_unres += 1
                continue
            comps = {}
            for csv_col, comp in comp_map.items():
                raw = r.get(csv_col)
                if raw is None or str(raw).strip() == "":
                    continue
                comps[comp] = float(raw)
            if comps:
                if key in med:
                    print(f"{label} intake WARNING: duplicate key: {key} "
                          f"({r.get('player')})")
                med[key] = comps
    print(f"{label} intake: {len(med)} eligible players "
          f"({n_rows} rows, {n_unres} unresolved), snapshot {snap}")
    return med, snap


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


def pts(stats, scoring):
    return fantasy_points(stats, scoring)

# ---------------------------------------------------------------------------
# Main bake
# ---------------------------------------------------------------------------

def bake(args):
    registry = load_registry()

    # ---- ECR intake -------------------------------------------------------
    snap_rows = query_all("fp_season_projections",
                          "?select=snapshot_date&order=snapshot_date.desc&limit=1")
    if not snap_rows:
        raise SystemExit("FAIL-CLOSED: fp_season_projections is empty — "
                         "no ECR snapshot to bake from.")
    ecr_snapshot_date = str(snap_rows[0]["snapshot_date"])

    ecr_rows = query_all(
        "fp_season_latest_norm",
        "?select=player_key,player_norm,position,team,passing_yards,passing_tds,"
        "rushing_yards,rushing_tds,receptions,receiving_yards,receiving_tds"
        f"&player_key=not.is.null&snapshot_date=eq.{ecr_snapshot_date}")

    # ---- ECR content vintage (fail-closed) ---------------------------------
    # Content = the 7 stat components + proj_half_ppr per player. Players
    # present in only one of two snapshots don't reset the vintage (board
    # churn isn't a re-rank). Vintage = earliest snapshot_date whose content
    # is identical to the current snapshot's.
    CONTENT_COLS = ("passing_yards", "passing_tds", "rushing_yards",
                    "rushing_tds", "receptions", "receiving_yards",
                    "receiving_tds", "proj_half_ppr")

    def _snapshot_content(snap):
        rows = query_all(
            "fp_season_projections",
            "?select=player_key," + ",".join(CONTENT_COLS) +
            f"&snapshot_date=eq.{snap}&player_key=not.is.null")
        return {int(r["player_key"]): tuple(r[c] for c in CONTENT_COLS)
                for r in rows}

    def _content_identical(a, b):
        shared = set(a) & set(b)
        return bool(shared) and all(a[pid] == b[pid] for pid in shared)

    date_rows = query_all("fp_season_projections",
                          "?select=snapshot_date&order=snapshot_date.asc")
    snap_dates = sorted({str(r["snapshot_date"]) for r in date_rows
                         if str(r["snapshot_date"]) <= ecr_snapshot_date})
    ecr_content_date = ecr_snapshot_date
    if snap_dates:
        cur_content = _snapshot_content(snap_dates[-1])
        for d in reversed(snap_dates[:-1]):
            if _content_identical(cur_content, _snapshot_content(d)):
                ecr_content_date = d
            else:
                break
    ecr_content_date = str(ecr_content_date)

    # ECR content-staleness gate: a byte-identical re-pull resets nothing.
    try:
        age_days = (_date.today() - _date.fromisoformat(ecr_content_date)).days
    except ValueError:
        raise SystemExit(
            f"FAIL-CLOSED: ECR content date undeterminable ({ecr_content_date!r}). "
            "Refusing to build chart without verifiable expert vintage.")
    if age_days > 3:
        raise SystemExit(
            f"FAIL-CLOSED: ECR content stale: expert projections unchanged since "
            f"{ecr_content_date} ({age_days}d > 3d max). Refusing to build chart "
            "on stale experts.")

    # ---- Source intakes ----------------------------------------------------
    espn_med, espn_snapshot_date = _intake_csv(
        args.espn_csv, ESPN_COMPS, "eligible", "espn", registry)
    pm_med, pm_snapshot_date = _intake_csv(
        args.pm_csv, PM_COMPS, "has_prediction_market_line", "pm", registry)
    rz_med, rz_snapshot_date = _intake_razzball(args.razzball_csv, registry)

    # ---- Actuals ------------------------------------------------------------
    actual_rows = query_all(
        "season_actuals_ytd",
        "?select=player_key,stat_key,actual&player_key=not.is.null")
    ACT_MAP = {
        "season_pass_yds": "passing_yards",
        "season_pass_tds": "passing_tds",
        "season_rush_yds": "rushing_yards",
        "season_rush_tds": "rushing_tds",
        "season_rec_yds": "receiving_yards",
        "season_receptions": "receptions",
        "season_rec_tds": "receiving_tds",
    }
    unmapped = sorted({r["stat_key"] for r in actual_rows
                       if r["stat_key"].startswith("season_")
                       and r["stat_key"] not in ACT_MAP})
    if unmapped:
        raise SystemExit("FAIL-CLOSED: season_actuals_ytd stat_keys with no ACT_MAP "
                         f"mapping: {unmapped} — refusing to build.")
    actuals = {}  # player_key -> {component: value}
    for r in actual_rows:
        ak = int(r["player_key"])
        comp = ACT_MAP.get(r["stat_key"])
        if comp:
            actuals.setdefault(ak, {})[comp] = float(r["actual"])

    # ---- Games remaining -----------------------------------------------------
    team_rows = query_all("teams", "?select=id,abbreviation&abbreviation=not.is.null")
    team_abbr = {r["id"]: r["abbreviation"] for r in team_rows}
    game_rows = query_all(
        "games", "?select=home_team_id,away_team_id,status&season=eq.2026")
    games_left = {}
    for g in game_rows:
        if g["status"] == "final":
            continue
        for tid in (g["home_team_id"], g["away_team_id"]):
            abbr = team_abbr.get(tid)
            if abbr:
                games_left[abbr] = games_left.get(abbr, 0) + 1

    # ---- Skill-player rows ----------------------------------------------------
    players = []
    for r in ecr_rows:
        key = int(r["player_key"])
        pos = r["position"]
        team = r["team"]
        a = actuals.get(key, {})

        # ECR projections are full-season: banked actuals removed for ROS.
        ecr_ros = {c: float(r[c] or 0) - a.get(c, 0.0) for c in COMPS}

        v = espn_med.get(key, {})
        espn_complete = pos in NEED and all(c in v for c in NEED[pos])
        # ECR-LADEN (2026-09-16): the board's primary number IS the ECR leg.
        # ESPN does not enter the blend; it lives only in the comparison
        # columns (espn_ros / espn_filled_ros), where ESPN takes precedence
        # within the column, no averaging, like-for-like.
        blend = {c: ecr_ros[c] for c in COMPS}
        espn_covered = sorted(c for c in COMPS if c in v)
        espn_ros = espn_filled_ros = None
        if espn_covered:
            espn_ros = {s: pts({c: v[c] for c in espn_covered}, s)
                        for s in SCORINGS}
        if espn_complete:
            espn_filled_ros = {
                s: pts({c: v[c] if c in v else ecr_ros[c] for c in COMPS}, s)
                for s in SCORINGS}

        pm = pm_med.get(key, {})
        pm_complete = pos in NEED and all(c in pm for c in NEED[pos])
        pm_covered = sorted(c for c in COMPS if c in pm)
        pm_ros = pm_filled_ros = None
        if pm_covered:
            pm_ros = {s: pts({c: pm[c] for c in pm_covered}, s)
                      for s in SCORINGS}
        if pm_complete:
            pm_filled_ros = {
                s: pts({c: pm[c] if c in pm else ecr_ros[c] for c in COMPS}, s)
                for s in SCORINGS}

        z = rz_med.get(key, {})
        rz_complete = (pos in ("QB", "RB", "WR", "TE")
                       and all(s in z for s in SCORINGS))
        rz_covered = sorted(s for s in SCORINGS if s in z)

        row = {
            "player_key": key,
            "name": require_canonical_name(key, registry=registry),
            "pos": pos,
            "team": team,
            "ecr_ros": {s: pts(ecr_ros, s) for s in SCORINGS},
            "espn_complete": bool(espn_complete),
            "espn_comp_count": sum(1 for c in COMPS if c in v),
            "espn_covered": espn_covered,
            "pm_complete": bool(pm_complete),
            "pm_comp_count": sum(1 for c in COMPS if c in pm),
            "pm_covered": pm_covered,
            "rz_complete": bool(rz_complete),
            "rz_comp_count": len(rz_covered),
            "rz_covered": rz_covered,
            "blend_ros": {s: pts(blend, s) for s in SCORINGS},
            # pricing label: the board's primary number is 100% ECR.
            "pricing": "experts_only",
        }
        if espn_ros is not None:
            row["espn_ros"] = espn_ros
        if espn_complete:
            row["espn_filled_ros"] = espn_filled_ros
            row["delta_espn_ecr"] = round(espn_filled_ros["ppr"] - row["ecr_ros"]["ppr"], 2)
        if pm_ros is not None:
            row["pm_ros"] = pm_ros
        if pm_complete:
            row["pm_filled_ros"] = pm_filled_ros
            row["delta_pm_ecr"] = round(pm_filled_ros["ppr"] - row["ecr_ros"]["ppr"], 2)

        # per-game points: ROS fantasy points / team games remaining
        gr = games_left.get({"LAR": "LA", "JAC": "JAX"}.get(team, team))
        row["games_remaining"] = gr
        if gr:
            row["blend_ppg"] = {s: round(v / gr, 2) for s, v in row["blend_ros"].items()}
            row["ecr_ppg"] = {s: round(v / gr, 2) for s, v in row["ecr_ros"].items()}
            if espn_ros is not None:
                row["espn_ppg"] = {s: round(row["espn_ros"][s] / gr, 2)
                                   for s in SCORINGS}
            if espn_complete:
                row["espn_filled_ppg"] = {s: round(espn_filled_ros[s] / gr, 2)
                                          for s in SCORINGS}
                row["delta_espn_ecr_ppg"] = round(
                    row["espn_filled_ppg"]["ppr"] - row["ecr_ppg"]["ppr"], 2)
            if pm_ros is not None:
                row["pm_ppg"] = {s: round(row["pm_ros"][s] / gr, 2)
                                 for s in SCORINGS}
            if pm_complete:
                row["pm_filled_ppg"] = {s: round(pm_filled_ros[s] / gr, 2)
                                        for s in SCORINGS}
                row["delta_pm_ecr_ppg"] = round(
                    row["pm_filled_ppg"]["ppr"] - row["ecr_ppg"]["ppr"], 2)
            # Razzball: rz_ros = rz_ppg x the pipeline's OWN games_remaining.
            # Razzball's displayed Games/totals are doubled (Allen: 32 games)
            # and are NEVER used. The source-accounting audit below fails the
            # build if rz_filled_ros != rz_ppg x games_remaining.
            if rz_complete:
                row["rz_ppg"] = {s: round(z[s], 2) for s in SCORINGS}
                row["rz_ros"] = {s: round(z[s] * gr, 2) for s in SCORINGS}
                row["rz_filled_ppg"] = dict(row["rz_ppg"])
                row["rz_filled_ros"] = dict(row["rz_ros"])
                row["delta_rz_ecr"] = round(
                    row["rz_filled_ros"]["ppr"] - row["ecr_ros"]["ppr"], 2)
                row["delta_rz_ecr_ppg"] = round(
                    row["rz_filled_ppg"]["ppr"] - row["ecr_ppg"]["ppr"], 2)
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
    for name, ppg in sorted(k_ppg.items(), key=lambda kv: -kv[1]):
        kk = resolve(name, position="K", registry=registry)
        if kk is None:
            kdst_unresolved.append(("K", name))
            continue
        gr = 16  # kickers: ROS weeks 3-18
        ros = round(ppg * gr, 2)
        same3 = {"standard": ros, "half_ppr": ros, "ppr": ros}
        ppg3 = {"standard": ppg, "half_ppr": ppg, "ppr": ppg}
        players.append({
            "player_key": kk,
            "name": require_canonical_name(kk, registry=registry),
            "pos": "K",
            "team": None,
            "ecr_ros": None, "blend_ros": dict(same3),
            "ecr_ppg": None, "blend_ppg": dict(ppg3),
            "espn_ppg": dict(ppg3), "espn_ros": dict(same3),
            "games_remaining": gr,
            # K/DST price from ESPN only — never experts_only.
            "pricing": "espn_only",
            "espn_complete": True, "espn_comp_count": 1, "espn_covered": ["k"],
            "pm_complete": False, "pm_comp_count": 0, "pm_covered": [],
            "rz_complete": False, "rz_comp_count": 0, "rz_covered": [],
            "prior_ecr_ros": None, "prior_blend_ros": None,
        })
    for abbr, ppg in sorted(dst_ppg.items(), key=lambda kv: -kv[1]):
        kk = resolve(abbr, position="DST", registry=registry)
        if kk is None:
            kdst_unresolved.append(("DST", abbr))
            continue
        gr = 15  # DST: 15 games remaining (all byes in weeks 3-18)
        ros = round(ppg * gr, 2)
        same3 = {"standard": ros, "half_ppr": ros, "ppr": ros}
        ppg3 = {"standard": ppg, "half_ppr": ppg, "ppr": ppg}
        players.append({
            "player_key": kk,
            "name": require_canonical_name(kk, registry=registry),
            "pos": "DST",
            "team": abbr,
            "ecr_ros": None, "blend_ros": dict(same3),
            "ecr_ppg": None, "blend_ppg": dict(ppg3),
            "espn_ppg": dict(ppg3), "espn_ros": dict(same3),
            "games_remaining": gr,
            "pricing": "espn_only",
            "espn_complete": True, "espn_comp_count": 1, "espn_covered": ["dst"],
            "pm_complete": False, "pm_comp_count": 0, "pm_covered": [],
            "rz_complete": False, "rz_comp_count": 0, "rz_covered": [],
            "prior_ecr_ros": None, "prior_blend_ros": None,
        })
    if kdst_unresolved:
        print(f"K/DST ESPN unresolved (excluded): {kdst_unresolved}",
              file=sys.stderr)

    # rank by primary (ECR-based) full-PPR value for convenience
    players.sort(key=lambda p: p["blend_ros"]["ppr"], reverse=True)

    # ---- prior ECR snapshot: ROS values for week-over-week movement ---------
    date_list = sorted({str(r["snapshot_date"]) for r in date_rows})
    prior_date = date_list[-2] if len(date_list) >= 2 else None
    prior_ecr_ros, prior_blend_ros = {}, {}
    if prior_date:
        actuals_file = FIXTURE_DIR / f"actuals_{prior_date}.json"
        prior_actuals = {}
        if actuals_file.exists():
            prior_json = json.load(open(actuals_file))
            # Support legacy norm-keyed files and current key-keyed files.
            for k, v in prior_json.items():
                try:
                    prior_actuals[int(k)] = v
                    continue
                except (ValueError, TypeError):
                    pass
                pk = None
                try:
                    pk = resolve_skill(k, registry=registry)
                except Exception:
                    pk = None
                if pk is not None:
                    prior_actuals[pk] = v
        prior_rows = query_all(
            "fp_season_projections",
            "?select=player_key,passing_yards,passing_tds,rushing_yards,"
            "rushing_tds,receptions,receiving_yards,receiving_tds"
            f"&snapshot_date=eq.{prior_date}&player_key=not.is.null")
        for r in prior_rows:
            pk = int(r["player_key"])
            pa = prior_actuals.get(pk, {})
            ros = {c: float(r[c] or 0) - pa.get(c, 0.0) for c in COMPS}
            full = {s: pts(ros, s) for s in SCORINGS}
            prior_ecr_ros[pk] = full
            prior_blend_ros[pk] = full  # primary was ECR-laden then too
    for p in players:
        pk = p["player_key"]
        if pk in prior_ecr_ros:
            p["prior_ecr_ros"] = prior_ecr_ros[pk]
            p["prior_blend_ros"] = prior_blend_ros[pk]
        elif "prior_ecr_ros" not in p:
            p["prior_ecr_ros"] = None
            p["prior_blend_ros"] = None

    # ---- positional shade / demeaned deltas -----------------------------------
    def _shade(leg_ppg, leg_complete, label):
        out = {}
        for pos in ("QB", "RB", "WR", "TE"):
            vals = [r[leg_ppg]["ppr"] - r[leg_complete]["ppr"] for r in players
                    if r["pos"] == pos and r.get(leg_ppg) and r.get(leg_complete)]
            # leg_ppg is the ECR leg, leg_complete the comparison leg:
            # shade = mean(ecr_ppg - comparison_ppg); positive = comparison cooler.
            out[pos] = {"ppr": round(sum(vals) / len(vals), 3)} if vals else {"ppr": 0.0}
        return out

    shade_ppg = _shade("ecr_ppg", "espn_filled_ppg", "espn")
    pm_shade_ppg = _shade("ecr_ppg", "pm_filled_ppg", "pm")
    rz_shade_ppg = _shade("ecr_ppg", "rz_filled_ppg", "rz")
    for p in players:
        if p.get("delta_espn_ecr_ppg") is not None:
            p["delta_espn_ecr_ppg_demeaned"] = round(
                p["delta_espn_ecr_ppg"] - shade_ppg[p["pos"]]["ppr"], 2)
            p["espn_adj_ppg"] = round(
                (p.get("espn_filled_ppg") or {}).get("ppr", 0)
                + shade_ppg[p["pos"]]["ppr"], 2)
        if p.get("delta_pm_ecr_ppg") is not None:
            p["delta_pm_ecr_ppg_demeaned"] = round(
                p["delta_pm_ecr_ppg"] - pm_shade_ppg[p["pos"]]["ppr"], 2)
        if p.get("delta_rz_ecr_ppg") is not None:
            p["delta_rz_ecr_ppg_demeaned"] = round(
                p["delta_rz_ecr_ppg"] - rz_shade_ppg[p["pos"]]["ppr"], 2)

    # ---- source-accounting audit (fail-closed) ---------------------------------
    # Every row must account for its sources. Pricing labels are set per
    # position above and are NEVER overwritten by a universal loop (the
    # retired bake's defect). ESPN-purity: K/DST rows must be ESPN-only
    # (espn_ros present, ecr_ros None); espn_* fields on skill rows are
    # built from espn_med only.
    violations = []
    for p in players:
        pid = f"{p['name']} (key={p['player_key']})"
        pricing = p.get("pricing")
        if p["pos"] in ("K", "DST"):
            if pricing != "espn_only":
                violations.append(f"{pid}: K/DST pricing must be 'espn_only', "
                                  f"got '{pricing}'")
            if p.get("ecr_ros") is not None:
                violations.append(f"{pid}: K/DST ecr_ros must be None "
                                  "(ESPN-purity: no expert data in K/DST)")
            if not p.get("espn_ros"):
                violations.append(f"{pid}: K/DST espn_ros missing")
        else:
            if pricing != "experts_only":
                violations.append(f"{pid}: skill pricing must be 'experts_only', "
                                  f"got '{pricing}'")
            if p.get("blend_ros") is None or p.get("ecr_ros") is None:
                violations.append(f"{pid}: skill row missing ecr/blend legs")
        # ESPN-filled consistency: espn_filled_ros == ESPN comps + ECR fill.
        if p.get("espn_filled_ros") and p["pos"] not in ("K", "DST"):
            v = espn_med.get(p["player_key"], {})
            a = actuals.get(p["player_key"], {})
            check = {s: pts({c: v[c] if c in v else
                             (float(next((r[c] for r in ecr_rows
                                          if int(r["player_key"]) == p["player_key"]), 0))
                              - a.get(c, 0.0))
                             for c in COMPS}, s) for s in SCORINGS}
            for s in SCORINGS:
                if abs(check[s] - p["espn_filled_ros"][s]) > 0.01:
                    violations.append(
                        f"{pid}: espn_filled_ros[{s}] inconsistent with "
                        "ESPN-med + ECR-fill recomputation")
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

    # ---- preseason ECR ranks ----------------------------------------------------
    ranks, pecr_report = load_preseason_ecr_ranks(registry=registry)
    annotate_rows(players, ranks)
    print(f"preseason ECR ranks: {pecr_report['resolved']} resolved, "
          f"{pecr_report['unmatched']} unmatched")

    # ---- meta ---------------------------------------------------------------------
    def _shade_phrase(sh, pos, cooler, warmer):
        s = sh[pos]["ppr"]
        d = cooler if s > 0.05 else warmer if s < -0.05 else "level"
        return f"{pos} {s:+} ({d})"

    today = str(_date.today())
    meta = {
        "as_of": today,
        "ecr_snapshot": ecr_snapshot_date,
        "ecr_content_date": ecr_content_date,
        "prior_ecr_snapshot": str(prior_date) if prior_date else None,
        "espn_snapshot": str(espn_snapshot_date),
        "pm_snapshot": str(pm_snapshot_date),
        "rz_snapshot": str(rz_snapshot_date),
        "n_players": len(players),
        "n_espn_complete": sum(1 for p in players if p["espn_complete"]),
        "n_pm_complete": sum(1 for p in players if p["pm_complete"]),
        "n_pm_covered": sum(1 for p in players if p.get("pm_comp_count", 0) > 0),
        "n_rz_complete": sum(1 for p in players if p["rz_complete"]),
        "n_k": sum(1 for p in players if p["pos"] == "K"),
        "n_dst": sum(1 for p in players if p["pos"] == "DST"),
        "kdst_snapshot": kdst_snapshot,
        "kdst_note": ("Kickers and team defenses price from ESPN projections "
                      "only (ESPN-purity directive, 2026-09-21): no expert/ECR "
                      "data anywhere in the K/DST leg. K ROS = ESPN per-game "
                      "rates x 16 (weeks 3-18); DST ROS = ESPN per-game rates "
                      "x 15 (all byes in weeks 3-18). Scoring-invariant: one "
                      "number serves standard/half/full."),
        "actuals_note": (f"YTD actuals subtracted from the ECR leg only "
                         f"({len(actuals)} players with banked stats). "
                         "The ESPN intake is already rest-of-season — no "
                         "actuals subtraction on the ESPN leg. Actuals exclude "
                         "INTs/fumbles by design (scoring_note)."),
        "scoring_note": "No INT/fumble data in season sources; values exclude them.",
        "ppg_note": ("Per-game points = ROS fantasy points / team games "
                     "remaining (final games excluded)."),
        "espn_note": ("espn_ros/espn_ppg = pure ESPN read over priced components "
                      "only (espn_covered lists them; never zero-filled). "
                      "espn_filled_ros/espn_filled_ppg = ESPN where priced, ECR "
                      "fills the rest (ESPN takes precedence, no averaging); "
                      "delta_espn_ecr(_ppg) is filled minus full ECR. Every "
                      "ESPN-labeled field is sourced ONLY from ESPN projections."),
        "pm_note": ("pm_ros/pm_ppg = pure prediction-markets read over priced "
                    "components only (pm_covered lists them; never zero-filled). "
                    "pm_filled_ros/pm_filled_ppg = prediction markets where "
                    "priced, ECR fills the rest (PM takes precedence, no "
                    "averaging); delta_pm_ecr(_ppg) is filled minus full ECR. "
                    "Source: raw Kalshi/Polymarket season ladders (own isotonic "
                    "math, local liquidity gate) — crowd wisdom, NOT sportsbook "
                    "money. Season receptions ladders have no liquid two-sided "
                    "market, so pass-catchers' pure reads exclude reception "
                    "points by construction; complete reads (all NEED components "
                    "priced) are a minority — see pm_complete/pm_covered."),
        "rz_note": ("rz_ppg = pure Razzball per-game projection read "
                    "(rz_std_ppg / rz_half_ppr_ppg / rz_ppr_ppg — already pure "
                    "per-game rates). rz_ros = rz_ppg x the pipeline's own "
                    "games_remaining: Razzball's displayed Games column and "
                    "counting totals are DOUBLED (e.g. Josh Allen: 32 games) "
                    "and are never used as ROS totals — the source-accounting "
                    "audit fails the build if rz_filled_ros != rz_ppg x "
                    "games_remaining. rz_filled_ppg/rz_filled_ros = Razzball "
                    "where priced (complete reads need no component fill); "
                    "the ECR fallback for unpriced players happens at the "
                    "rails layer like ESPN/PM. delta_rz_ecr(_ppg) is filled "
                    "minus full ECR. Verified independent third projection "
                    "source 2026-09-17 (rank corr vs ECR 0.78-0.91, never "
                    "0.99+; deviations largely independent of ESPN). "
                    "K/DST have no Razzball projections (ESPN-priced)."),
        "method_note": ("Primary trade value (blend_ros/blend_ppg): since 2026-09-16 "
                        "the primary value IS the ECR leg — expert stat projections "
                        "translated to fantasy points with banked actuals removed "
                        "(rest-of-season). ESPN does not enter the primary value; "
                        "it lives only in the comparison columns (espn_ros / "
                        "espn_filled_ros: ESPN projections only). K/DST player "
                        "pricing is ESPN (2026-09-21 vintage). The chart engine "
                        "applies the DDF value-above-waivers methodology: raw value "
                        "is projected points above the positional waiver line; each "
                        "1-point slice is priced on a two-tier marginal curve "
                        "(bench rate below the starter line, starter rate above, "
                        "smooth S-curve glide of 25% of starter-minus-waiver); "
                        "bench totals exactly 15% and starters 85% per position "
                        "before rounding; 70-point display scale."),
        "shade_baseline_ppg": shade_ppg,
        "disagree_baseline_note": (
            "Empirical ESPN-vs-ECR direction, measured as mean(ecr_ppg - "
            "espn_filled_ppg) over espn_complete players (full-PPR /g: " +
            ", ".join(_shade_phrase(shade_ppg, pos, "ESPN cooler", "ESPN warmer")
                       for pos in ("QB", "RB", "WR", "TE")) +
            "). Positive shade = ESPN cooler than ECR; negative = ESPN warmer. "
            "delta_espn_ecr_demeaned subtracts the player's positional baseline, "
            "and espn_adj_ppg translates ESPN points onto the experts' level, so "
            "the disagreement section's rank gaps are genuine ordering differences, "
            "not shade."),
        "pricing_note": ("pricing labels are per-position: 'experts_only' for "
                         "QB/RB/WR/TE (primary value 100% ECR), 'espn_only' for "
                         "K/DST (ESPN-purity directive). The source-accounting "
                         "audit rejects any other label."),
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

    # Bank key-keyed actuals for future prior-week movement.
    actuals_path = FIXTURE_DIR / f"actuals_{today}.json"
    actuals_path.write_text(json.dumps(
        {str(k): v for k, v in sorted(actuals.items())}, indent=1))
    print(f"banked actuals -> {actuals_path.name} ({len(actuals)} players)")

    # sanity: top 8 primary-value PPR
    for p in players[:8]:
        print(p["name"], p["pos"], p["team"], p["blend_ros"]["ppr"],
              "espn" if p["espn_complete"] else "ecr-only",
              "+pm" if p.get("pm_complete") else "")

    return {"meta": meta, "n_players": len(players)}


def main():
    ap = argparse.ArgumentParser(description="Repo-owned players.json bake")
    ap.add_argument("--espn-csv", default=str(INPUTS_DIR / "espn_projections.csv"))
    ap.add_argument("--pm-csv", default=str(INPUTS_DIR / "prediction_markets_season.csv"))
    ap.add_argument("--razzball-csv", default=str(INPUTS_DIR / "razzball_projections.csv"))
    ap.add_argument("--k-json", default=str(INPUTS_DIR / "espn_k_ppg_2026-09-21.json"))
    ap.add_argument("--dst-json", default=str(INPUTS_DIR / "espn_dst_ros_2026-09-21.json"))
    args = ap.parse_args()
    result = bake(args)
    print(json.dumps({k: v for k, v in result["meta"].items()
                      if k in ("as_of", "ecr_snapshot", "ecr_content_date",
                               "n_players", "n_espn_complete", "n_pm_complete",
                               "n_rz_complete", "n_k", "n_dst")}, indent=1))


if __name__ == "__main__":
    main()
