"""Build the weekly staged_bundle_*.json for the Supabase weekly_dashboard loader.

JEG-421: re-points the EXPERT leg from retired ECR to ESPN projections (Mike
Clay model, ROS). Vegas leg and shape match the last known-good bundle in
sources_refresh_runlog/staged_bundle_2026-10-03.json.

Outputs: data/weekly/staged_bundle_<stamp>.json
Inputs (no ECR reads anywhere — gated by grep):
  - data/inputs/espn_projections.csv (ESPN ROS expert leg; replaces ECR)
  - data/inputs/player_identity_map.json (player universe + pos/team keys)
  - weekly_vegas/pipeline/data/propline_cache/ (optional; vegas leg)
  - weekly_vegas/pipeline/data/signals_v4.json (optional; vegas if present)

Validates locally against the loader's checks:
  - meta.week/season/built_at sane (week 1..25, season 2020..2100, built_at str)
  - player rows are objects; player_key non-empty
  - every row is FULL (vegas_leg present) or STUB (no_market_read)
  - dedupe: at most one FULL per player_key, at most one STUB
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_WEEKLY = os.path.join(REPO, "data", "weekly")
ESPN_CSV = os.path.join(REPO, "data", "inputs", "espn_projections.csv")
IDENTITY = os.path.join(REPO, "data", "inputs", "player_identity_map.json")
SIGNALS_V4 = os.path.join(
    REPO, "weekly_vegas", "pipeline", "data", "signals_v4.json"
)

# ESPN uses half-PPR natively; std = half - 0.5*receptions/game,
# full = half + 0.5*receptions/game. ROS is season totals; per-game =
# ros / weeks_remaining. Staged_bundle's expert_* values are weekly points
# (matches the loader's read on v4 bundle fields).

# ---------- helpers ----------
def _norm(name):
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def _load_espn_ros(week, season):
    """Return {player_norm: {pos, team, half_ppr, std, full, receptions_week,
        espn_snapshot_date}}. expert_* values are PER-GAME weekly points.
    """
    if not os.path.isfile(ESPN_CSV):
        raise SystemExit(f"BLOCKED: ESPN ROS CSV missing: {ESPN_CSV}")
    out = {}
    with open(ESPN_CSV) as f:
        for r in csv.DictReader(f):
            if not r.get("has_espn_projection", "").lower().startswith("t"):
                continue
            try:
                rec = float(r["r_receptions"] or 0)
                half = float(r["ros_half_ppr"] or 0)
                # weeks_covered is "5-18" -> 14 weeks. ROS per-game:
                wks = 14
                m = re.match(r"(\d+)-(\d+)", r.get("weeks_covered") or "")
                if m:
                    wks = max(1, int(m.group(2)) - int(m.group(1)) + 1)
                half_pg = half / wks
                std_pg = half_pg - 0.5 * (rec / wks)
                full_pg = half_pg + 0.5 * (rec / wks)
            except (ValueError, ZeroDivisionError):
                continue
            out[_norm(r["player"])] = {
                "name": r["player"],
                "pos": r["pos"],
                "team": r["team"],
                "half": round(half_pg, 2),
                "std": round(std_pg, 2),
                "ppr": round(full_pg, 2),
                "espn_snapshot_date": r.get("espn_snapshot_date", ""),
            }
    return out


def _load_identity_universe():
    """Return list of {player_key, name, pos, team} from the shared snapshot.

    Filters to skill positions the bundle supports (QB/RB/WR/TE). Excludes
    DST/K because the loader treats them differently downstream.
    """
    if not os.path.isfile(IDENTITY):
        return []
    raw = json.load(open(IDENTITY))
    players = raw.get("players") if isinstance(raw, dict) else raw
    out = []
    for p in players or []:
        pos = (p.get("pos") or "").upper()
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        key = (p.get("player_key") or _norm(p.get("name") or "")).strip().lower()
        if not key:
            continue
        out.append({
            "player_key": key,
            "name": p.get("name") or key,
            "pos": pos,
            "team": (p.get("team") or "").upper(),
        })
    return out


def _load_existing_signals():
    """Pull Vegas leg numbers from signals_v4.json when present (no ECR)."""
    if not os.path.isfile(SIGNALS_V4):
        return {}
    try:
        rows = json.load(open(SIGNALS_V4))
    except Exception:
        return {}
    out = {}
    for r in rows:
        k = (r.get("player_key") or "").strip().lower()
        if not k:
            continue
        out[k] = r
    return out


def _pos_rank(scores):
    """Return {player_key: rank_within_pos} from a {key: pts} dict."""
    by_pos = defaultdict(list)
    for k, p in scores.items():
        # caller must inject pos via meta; here we sort on pts desc.
        by_pos["_"].append((-p, k))
    out = {}
    for k, lst in by_pos.items():
        lst.sort()
        for i, (_, key) in enumerate(lst, 1):
            out[key] = i
    return out


def _classify(row):
    """Mirror the loader's classify(): FULL iff vegas_leg is non-null;
    STUB iff category == 'no_market_read'. Anything else is invalid.
    """
    if row.get("vegas_leg") is not None:
        return "FULL"
    if row.get("category") == "no_market_read":
        return "STUB"
    return None


def _dedupe(players):
    """Mirror the loader's dedupe(): keep one FULL per key, else lone STUB.
    Returns (deduped_dict, errors_list).
    """
    best = {}
    errors = []
    for idx, row in enumerate(players):
        if not isinstance(row, dict):
            errors.append(f"row {idx}: not an object")
            continue
        key = (row.get("player_key") or "").strip().lower()
        if not key:
            errors.append(f"row {idx}: missing player_key")
            continue
        shape = _classify(row)
        if shape is None:
            errors.append(
                f"player {key}: unrecognized shape "
                f"(no vegas_leg and category={row.get('category')!r})")
            continue
        prior = best.get(key)
        if prior is None:
            best[key] = (shape, row)
            continue
        if shape == "FULL" and prior[0] == "FULL":
            errors.append(f"player {key}: two FULL rows")
        elif shape == "STUB" and prior[0] == "STUB":
            errors.append(f"player {key}: two STUB rows")
        elif shape == "FULL":
            best[key] = (shape, row)
    return {k: v[1] for k, v in best.items()}, errors


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    week = a.week
    season = a.season
    if week is None:
        # Default to last-known-good week when caller omits (avoids forcing
        # a network clock read); the producer is staged for an explicit week.
        week = 4

    espn = _load_espn_ros(week, season)
    universe = _load_identity_universe()
    existing = _load_existing_signals()

    if not espn:
        print("BLOCKED: ESPN ROS CSV had zero eligible rows; cannot build "
              "expert leg.", file=sys.stderr)
        sys.exit(2)

    # Build per-player bundle rows. Vegas leg comes from existing signals
    # when available; otherwise the row is a no_market_read STUB (the engine
    # pattern: ESPN-leg expert reads with no Vegas-priced props this week).
    players = []
    n_espn_join = 0
    n_vegas_full = 0
    n_vegas_partial = 0
    n_no_vegas = 0
    n_post_worthy = 0
    pos_level_pts_sum = defaultdict(lambda: [0.0, 0])  # [sum_vegas - espn, n]

    pos_rank_espn = defaultdict(dict)
    pos_rank_vegas = defaultdict(dict)
    # Pre-rank ESPN expert points per position
    for k, v in espn.items():
        pos_rank_espn[v["pos"]][k] = v["half"]

    # First pass: collect vegas pts per pos for rank
    vegas_pts = {}
    for k, v in espn.items():
        if k in existing and (existing[k].get("vegas_half") is not None):
            vegas_pts[k] = float(existing[k]["vegas_half"])

    # Build the rows
    for k, e in espn.items():
        sig = existing.get(k, {})
        vegas_half = sig.get("vegas_half")
        vegas_std = sig.get("vegas_std")
        vegas_ppr = sig.get("vegas_ppr")
        vegas_leg = sig.get("vegas_leg")
        vegas_prov = sig.get("vegas_provenance")
        if vegas_leg is not None:
            if vegas_prov == "complete":
                n_vegas_full += 1
            elif vegas_prov == "partial":
                n_vegas_partial += 1
            n_espn_join += 1
        else:
            n_no_vegas += 1

        ecr_rank = pos_rank_espn.get(e["pos"], {}).get(k)
        # ESPN provides no formal pos rank string; mirror the bundle's
        # `ecr_official` field by composing `ESPN{pos}{rank}` for the
        # post-worthy card.
        espn_official = f"ESPN{e['pos']}{ecr_rank}" if ecr_rank else None
        vegas_rank = None  # populated below if vegas_half present

        if vegas_half is not None and ecr_rank:
            pos_level_pts_sum[e["pos"]][0] += vegas_half - e["half"]
            pos_level_pts_sum[e["pos"]][1] += 1
            pos_rank_vegas[e["pos"]][k] = vegas_half

        pts_delta = (vegas_ppr - e["ppr"]) if (vegas_ppr is not None) else None
        post_worthy = bool(
            vegas_leg is not None
            and vegas_prov in ("complete", "td-filled")
            and pts_delta is not None
            and abs(pts_delta) >= 2.0
        )
        if post_worthy:
            n_post_worthy += 1

        row = {
            "player_key": k,
            "name": e["name"],
            "pos": e["pos"],
            "team": e["team"],
            "vegas_std": vegas_std,
            "vegas_half": vegas_half,
            "vegas_ppr": vegas_ppr,
            # EXPERT LEG: ESPN ROS replaces ECR
            "expert_std": e["std"],
            "expert_half": e["half"],
            "expert_ppr": e["ppr"],
            "expert_source": "espn_ros",
            "pts_delta_ppr": pts_delta,
            "ecr_pos_rank": ecr_rank,
            "ecr_official": espn_official,
            "n_pos": len(pos_rank_espn.get(e["pos"], {})),
            "vegas_pos_rank": None,
            "delta": None,
            "abs_delta": None,
            "direction": "flat",
            "pos_level_gap": None,
            "pts_delta_adj": pts_delta,
            "post_worthy": post_worthy,
            "worthy_reason": (
                None if post_worthy else
                ("partial market data" if vegas_prov == "partial" else None)
            ),
            "td_p_yes": sig.get("td_p_yes"),
            "expert_td_exp": None,
            "vegas_provenance": vegas_prov,
            "vegas_leg": vegas_leg,
            "vegas_stats_used": sig.get("vegas_stats_used"),
            "fds_projection_stats": sig.get("fds_projection_stats"),
            "fds_stat_sources": sig.get("fds_stat_sources"),
            "coverage_ok": vegas_prov in ("complete", "td-filled"),
            "injury_flag": sig.get("injury_flag"),
            "injury_note": sig.get("injury_note"),
            # ESPN ROS projection detail (per-game weekly, derived from ROS)
            "espn_week_n": week,
            "espn_proj_std": e["std"],
            "espn_proj_half": e["half"],
            "espn_proj_ppr": e["ppr"],
            # Legacy contract aliases: the API view
            # (sql/contract/weekly_dashboard_api_contract.sql) selects
            # signal->>'espn_half' etc. Keep them populated from the same
            # ESPN expert values so the contract holds across the ECR exit.
            "espn_std": e["std"],
            "espn_half": e["half"],
            "espn_ppr": e["ppr"],
            "espn_snapshot_date": e["espn_snapshot_date"],
        }

        if vegas_leg is None:
            # STUB row: no Vegas this week -> category marker for the loader
            row["category"] = "no_market_read"
            row["vegas_leg"] = None
            row["vegas_std"] = None
            row["vegas_half"] = None
            row["vegas_ppr"] = None
            row["post_worthy"] = False
            row["worthy_reason"] = "no market read this week"
            row["coverage_ok"] = False
        players.append(row)

    # Augment with universe-only players missing from ESPN ROS so the bundle
    # includes players the loader might encounter (QB/RB/WR/TE). They carry
    # no expert leg, so they MUST be no_market_read STUBs (loader contract:
    # STUB iff category == "no_market_read").
    seen = {p["player_key"] for p in players}
    for u in universe:
        if u["player_key"] in seen:
            continue
        players.append({
            "player_key": u["player_key"],
            "name": u["name"],
            "pos": u["pos"],
            "team": u["team"],
            "vegas_std": None,
            "vegas_half": None,
            "vegas_ppr": None,
            "expert_std": None,
            "expert_half": None,
            "expert_ppr": None,
            "expert_source": None,
            "ecr_pos_rank": None,
            "ecr_official": None,
            "category": "no_market_read",
            "post_worthy": False,
            "worthy_reason": "no market read this week",
            "vegas_leg": None,
            "vegas_provenance": "none",
            "coverage_ok": False,
            "injury_flag": None,
        })

    # Compute vegas pos ranks + pos-level gap
    for pos, members in pos_rank_vegas.items():
        ranked = sorted(members.items(), key=lambda kv: -kv[1])
        for i, (k, _) in enumerate(ranked, 1):
            for r in players:
                if r["player_key"] == k:
                    r["vegas_pos_rank"] = i
                    if r.get("ecr_pos_rank") is not None:
                        d = i - r["ecr_pos_rank"]
                        r["delta"] = d
                        r["abs_delta"] = abs(d)
                        if d > 0:
                            r["direction"] = "experts_high"
                        elif d < 0:
                            r["direction"] = "vegas_high"
                        else:
                            r["direction"] = "flat"
                    break

    pos_level_gap = {}
    for pos, (s, n) in pos_level_pts_sum.items():
        pos_level_gap[pos] = round(s / n, 2) if n else None
    for r in players:
        if r["pos"] in pos_level_gap:
            r["pos_level_gap"] = pos_level_gap[r["pos"]]

    # Sort: post-worthy first, then by pos, then name
    players.sort(key=lambda p: (
        0 if p.get("post_worthy") else 1, p["pos"], p["name"]))

    meta = {
        "week": week,
        "season": season,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_file": (
            "football-signal/data/signals_wk{}_v4.json".format(week)
            if existing else
            "data/inputs/espn_projections.csv"
        ),
        "source_mtime": datetime.now(timezone.utc).isoformat(),
        "n_players": len(players),
        "n_with_vegas_coverage": n_vegas_full,
        "n_vegas_full": n_vegas_full,
        "n_vegas_partial": n_vegas_partial,
        "n_vegas_any": n_vegas_full + n_vegas_partial,
        "n_no_vegas": n_no_vegas,
        "n_post_worthy": n_post_worthy,
        "n_with_espn_weekly": n_espn_join,
        "espn_weekly_as_of": datetime.now(timezone.utc).isoformat(),
        "espn_scoring_note": (
            "ESPN ROS (Mike Clay model, half-PPR native); per-game = "
            "ROS totals / weeks_covered; std/ppr derived +/-0.5 per reception."),
        "scorings": ["std", "half", "ppr"],
        "labels": {
            "vegas": "Vegas (props-implied)",
            "expert": "ESPN (Mike Clay model)",
            "espn": "ESPN (Mike Clay model)",
        },
        "audit_disagreements": [],
        "audit_counts": {"local_only": 0, "agreements": 0, "overrides": 0,
                          "partial_crosschecks": 0},
        "vegas_source_priority": ["propline", "odds_api", "fds"],
        "expert_source": "espn_ros",
        "expert_leg_replaces": "ecr",
    }

    bundle = {"meta": meta, "players": players}

    # Validate locally against the loader contract before writing.
    if not (1 <= meta["week"] <= 25):
        raise SystemExit(f"BLOCKED: meta.week invalid: {meta['week']}")
    if not (2020 <= meta["season"] <= 2100):
        raise SystemExit(f"BLOCKED: meta.season invalid: {meta['season']}")
    if not meta["built_at"]:
        raise SystemExit("BLOCKED: meta.built_at missing")
    deduped, errors = _dedupe(players)
    if errors:
        # The loader exits 2 on these; we surface them too.
        for e in errors[:10]:
            print(f"  DEDUPE ERROR: {e}", file=sys.stderr)
        raise SystemExit(f"BLOCKED: {len(errors)} dedupe errors")
    if not deduped:
        raise SystemExit("BLOCKED: dedupe produced zero rows")

    os.makedirs(DATA_WEEKLY, exist_ok=True)
    stamp_name = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = os.path.join(DATA_WEEKLY,
                            f"staged_bundle_wk{week}_{stamp_name}.json")
    with open(out_path, "w") as f:
        json.dump(bundle, f, indent=1)
    print(f"wrote {out_path}")
    print(f"  meta.week={meta['week']} season={meta['season']}")
    print(f"  n_players={len(players)} | n_deduped={len(deduped)}")
    print(f"  vegas_full={n_vegas_full} partial={n_vegas_partial} "
          f"no_vegas={n_no_vegas} | espn_join={n_espn_join}")
    print(f"  post_worthy={n_post_worthy}")
    print(f"  pos_level_gap (vegas-espn, half PPR): "
          + ", ".join(f"{p}={pos_level_gap[p]:+.2f}"
                      for p in sorted(pos_level_gap) if pos_level_gap[p] is not None))
    print(f"  bundle sha256={_sha(out_path)[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
