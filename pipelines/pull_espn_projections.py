#!/usr/bin/env python3
"""ESPN projections pull -> files/espn_projections.csv (+ weekly file).

WHAT THIS IS: ESPN's own season/weekly fantasy projections (Mike Clay's
model powers the ESPN fantasy game, per ESPN). These are EXPERT/MODEL
numbers, NOT market money. Labeled "ESPN projections" everywhere -- never
Vegas, never market, never consensus.

SNAPSHOT MODEL (same as pull_sharplineup_ros.py): this scheduled script is
the ONLY thing that touches the network. It persists everything to our
CSVs. Nothing reads ESPN live. A dead API -> FAILED log line + nonzero
exit; snapshot preserved.

WIRED 2026-09-16 (user decision): this leg feeds the trade-value chart's
ESPN leg and the compare dashboard. The leg is ESPN's fantasy
projections (Mike Clay model per ESPN) -- explicitly NOT
sportsbook/market money; label "ESPN projections" everywhere, never
Vegas, never market, never consensus.

CADENCE: daily 06:10 CT, CONDITIONAL. ESPN exposes no timestamp, so the
script hashes the normalized parsed payload and compares it to the stored
hash:
  - hash unchanged (and not --force) -> log "no update, snapshot current",
    exit 0, CSVs untouched
  - hash changed or --force -> full pull + snapshot rewrite

METHODOLOGY (empirically determined 2026-09-16, see pull log):
  - Stat IDs calibrated against nflverse 2026 week-1 actuals (never the
    stale community doc):
      3=pass_yds, 4=pass_tds, 24=rush_yds, 25=rush_tds,
      53=receptions, 42=rec_yds, 43=rec_tds
    (id 23 = rush attempts, unscored; id 58 = targets, unscored)
  - Blocks filtered to seasonId=2026 ONLY. ESPN's feed mixes 2025 blocks
    into the same stats array with no other discriminator (caught: Josh
    Allen's 2025 week-1 394-yd game sitting beside his 2026 334-yd game).
  - ROS semantics: ESPN's season block (source=1, period=0, split=0) is a
    full-season forecast built on PROJECTED (not actual) week 1 -- it is
    neither clean ROS nor banked+ROS (Gibbs rush: season block 1429 vs
    wk1proj+rest 1678, 15% drift). The unambiguous ROS leg is therefore
    SUM of weekly projection blocks (source=1, split=1, seasonId=2026)
    over weeks not yet played. Played weeks are detected empirically from
    actuals blocks (source=0); the season block is stored as the
    season_block_half_ppr diagnostic column so drift stays auditable.
  - No duplicate (source, period, split, seasonId) blocks observed for
    2026 projections; duplicates would be logged, first wins.

IDENTITY: resolved through the shared Supabase IdentityMap snapshot
(lottery/bin/identity.py). FAIL CLOSED: unknown names, ambiguous heuristic
matches, and position mismatches are logged and EXCLUDED -- never written
under a guessed identity.
"""
import csv
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BIN = Path(__file__).resolve().parent
# Support --out and --meta args for GitHub Actions (defaults to goal dir paths)
_args = sys.argv[1:]
_out_idx = _args.index("--out") if "--out" in _args else -1
_meta_idx = _args.index("--meta") if "--meta" in _args else -1

REPO = BIN.parent
GOAL = BIN.parent.parent                      # football-signal-database-and-app
if not (GOAL / "files").is_dir():
    # JEG-102: repo / CI layout. There is no goal workspace beside the repo; keep
    # working files inside the repo's gitignored output/ instead of beside it.
    GOAL = REPO / "output" / "espn_pull"
FILES = GOAL / "files"
HIDDEN = GOAL / "hidden_files"
LOG = HIDDEN / "espn_projections_runs.log"
SEASON_CSV = Path(_args[_out_idx + 1]) if _out_idx >= 0 and _out_idx + 1 < len(_args) else FILES / "espn_projections.csv"
WEEKLY_CSV = FILES / "espn_weekly_projections.csv"
META = Path(_args[_meta_idx + 1]) if _meta_idx >= 0 and _meta_idx + 1 < len(_args) else HIDDEN / "espn_projections_meta.json"
SIDECAR = HIDDEN / "espn_ros_ppg.json"
FORCE = "--force" in _args  # bypass the hash no-op (backfills only)

sys.path.insert(0, str(BIN))
# Migrated from waiver_wire/pipeline/bin/identity (archived 2026-10-07).
# The legacy shim in pipelines/lib/ preserves the identical public API
# (norm_name, IdentityMap, SNAP). New identity work uses layered_identity.
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
import legacy_identity as ident  # noqa: E402  (shared Supabase IdentityMap snapshot)

# SNAP now points at data/inputs/ directly; the fallback path is kept for
# any layout that still has an alternate snapshot.
IDENTITY_SNAPSHOT = (Path(ident.SNAP) if Path(ident.SNAP).exists()
                     else REPO / "data" / "inputs" / "player_identity_map.json")

API = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/"
       "segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info")
TEAMS_API = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36",
      "X-Fantasy-Source": "kona",
      "X-Fantasy-Platform": "kona-web"}
SEASON_ID = 2026
# slotId -> position (ESPN defaultPositionId uses the same codes)
SLOTS = ((0, "QB"), (2, "RB"), (4, "WR"), (6, "TE"))
POSITIONS = ("QB", "RB", "WR", "TE")
POS_IDS = {"QB": 1, "RB": 2, "WR": 3, "TE": 4}

# ESPN stat id -> our ROS column (calibrated 2026-09-16 vs nflverse wk1)
STATMAP = (("3", "r_pass_yds"), ("4", "r_pass_tds"),
           ("24", "r_rush_yds"), ("25", "r_rush_tds"),
           ("53", "r_receptions"), ("42", "r_rec_yds"), ("43", "r_rec_tds"))
# half-PPR weights (same as the vegas leg: no INT/fumbles, books don't price)
W = {"r_pass_yds": 0.04, "r_pass_tds": 4.0, "r_rush_yds": 0.10,
     "r_rush_tds": 6.0, "r_receptions": 0.5, "r_rec_yds": 0.10,
     "r_rec_tds": 6.0}

# Fallback team map (fetched live each run; this is 2026-09-16's copy)
TEAM_FALLBACK = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR",
    15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
    21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA",
    27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}


def now_ct():
    return datetime.now(ZoneInfo("America/Chicago"))


def ensure_output_dirs():
    """JEG-102: the goal workspace had files/ and hidden_files/; a CI checkout does not.
    The atomic writers below put their temp files in these directories."""
    for d in (FILES, HIDDEN):
        d.mkdir(parents=True, exist_ok=True)


def log_line(status, detail):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{now_ct().strftime('%Y-%m-%d %H:%M %Z')} | "
                f"espn-projections-pull | {status}: {detail}\n")


def api_get(url, xfilter=None):
    h = dict(UA)
    if xfilter is not None:
        h["X-Fantasy-Filter"] = json.dumps(xfilter)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_position(slot, source):
    """One polite request per (position, source). No split-type filter so
    each player carries season + weekly blocks in one response."""
    filt = {"players": {
        "filterSlotIds": {"value": [slot]},
        "filterStatsForSourceIds": {"value": [source]},
        "sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 3,
                                "value": "1120260"},
        "limit": 400, "offset": 0}}
    return api_get(API, filt)["players"]


def _validate_team_map(m):
    """Integrity contract for the team map (live or fallback): exactly 32
    teams, unique integer ids, unique uppercase abbreviations. Raises on
    failure — a corrupt map would silently misattribute teams (fail-closed)."""
    ids = list(m.keys())
    abbrs = list(m.values())
    assert len(m) == 32, f"team map has {len(m)} teams, expected 32"
    assert len(set(ids)) == 32, "duplicate team ids in team map"
    assert len(set(abbrs)) == 32, "duplicate abbreviations in team map"
    assert all(isinstance(i, int) for i in ids), "non-integer team id"
    assert all(isinstance(a, str) and a.isupper() and a.isalpha()
               and 2 <= len(a) <= 3 for a in abbrs), \
        f"bad abbreviation in team map: {abbrs}"
    return m


def load_team_map(problems):
    try:
        d = api_get(TEAMS_API)
        m = {int(t["team"]["id"]): t["team"]["abbreviation"]
             for t in d["sports"][0]["leagues"][0]["teams"]}
        return _validate_team_map(m)  # raises unless exactly 32 valid teams
    except AssertionError as e:
        problems.append(f"team-map-invalid ({e}); using baked fallback")
    except Exception as e:  # noqa: BLE001
        problems.append(f"team-map-fetch-failed ({e}); using baked fallback")
    problems.append("team-map-verified-fallback: 32/32 teams, ids+abbrs unique")
    return _validate_team_map(dict(TEAM_FALLBACK))


def resolve_identity(imap, name, pos, problems):
    """ESPN name -> (canonical_key, display) or None (fail closed)."""
    key = ident.norm_name(name)
    canon = None
    if key in imap.alias_to_canonical:
        canon = imap.alias_to_canonical[key]
    elif key in imap.chart_keys:
        canon = key
    else:
        h = imap.heuristic(key)
        if h:
            canon = h
            problems.append(f"heuristic-identity: {name!r} -> {canon!r} "
                            f"(add to registry)")
    if canon is None:
        problems.append(f"identity-unresolved: {name!r} ({pos})")
        return None
    entry = imap.canonical.get(canon, {})
    if entry.get("pos") and entry["pos"] != pos:
        problems.append(f"identity-pos-mismatch: {name!r} ESPN={pos} "
                        f"registry={entry['pos']}")
        return None
    return canon, (entry.get("name") or
                   " ".join(w.capitalize() for w in canon.split(" ")))


def main():
    problems = []
    t0 = time.time()

    # ---- 0. fetch: 4 positions x (projections + actuals) ----
    proj, acts = {}, {}
    try:
        for slot, pos in SLOTS:
            proj[pos] = fetch_position(slot, 1)
            time.sleep(0.5)
            acts[pos] = fetch_position(slot, 0)
            time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        log_line("FAILED", f"source=espn; pull failed ({e}). "
                           f"0 rows written; snapshot preserved")
        print(f"FAILED: pull: {e}", file=sys.stderr)
        return 1
    n_players = sum(len(v) for v in proj.values())
    print(f"fetched {n_players} player payloads "
          f"({time.time()-t0:.1f}s)", flush=True)

    team_map = load_team_map(problems)
    imap = ident.IdentityMap(
        chart_keys=json.load(open(IDENTITY_SNAPSHOT))["canonical"].keys(),
        snapshot_path=IDENTITY_SNAPSHOT)

    # ---- 1. played weeks, detected empirically from 2026 actuals ----
    actual_counts = {}
    for pos in POSITIONS:
        for p in acts[pos]:
            if not isinstance(p, dict):
                continue
            pl = p.get("player", {})
            for s in pl.get("stats", []):
                if (s.get("seasonId") == SEASON_ID
                        and s.get("statSourceId") == 0
                        and s.get("statSplitTypeId") == 1
                        and (s.get("stats") or {})):
                    actual_counts[s.get("scoringPeriodId")] = \
                        actual_counts.get(s.get("scoringPeriodId"), 0) + 1
    played = sorted(w for w, c in actual_counts.items()
                    if isinstance(w, int) and 1 <= w <= 18 and c >= 20)
    ros_weeks = [w for w in range(1, 19) if w not in played]
    print(f"played weeks (empirical): {played}; ROS weeks: "
          f"{ros_weeks[0]}-{ros_weeks[-1]}", flush=True)
    if not ros_weeks:
        log_line("FAILED", "source=espn; no ROS weeks detected; "
                           "0 rows written; snapshot preserved")
        print("FAILED: no ROS weeks", file=sys.stderr)
        return 1

    # ---- 2. parse + identity (fail closed) ----
    priced, seen = [], set()
    dup_blocks = 0
    for pos in POSITIONS:
        for p in proj[pos]:
            if not isinstance(p, dict):
                continue
            pl = p.get("player", {})
            name = pl.get("fullName", "")
            dpid = pl.get("defaultPositionId")
            if dpid != POS_IDS[pos]:
                # slot filter is positional; a mismatch is a data oddity
                problems.append(f"pos-slot-mismatch: {name!r} slot={pos} "
                                f"defaultPositionId={dpid}; skipped")
                continue
            res = resolve_identity(imap, name, pos, problems)
            if res is None:
                continue
            canon, display = res
            if canon in seen:
                problems.append(f"identity-collision: {name!r} -> "
                                f"{canon!r} already priced; excluded")
                continue
            # collect 2026 projection blocks
            weekly, season_blk = {}, None
            n_dup = 0
            for s in pl.get("stats", []):
                if s.get("seasonId") != SEASON_ID or s.get("statSourceId") != 1:
                    continue
                sp, splt = s.get("scoringPeriodId"), s.get("statSplitTypeId")
                if splt == 1 and isinstance(sp, int) and 1 <= sp <= 18:
                    if sp in weekly:
                        n_dup += 1
                        continue  # first wins; logged below
                    weekly[sp] = {str(k): v
                                  for k, v in (s.get("stats") or {}).items()}
                elif sp == 0 and splt == 0 and season_blk is None:
                    season_blk = {str(k): v
                                  for k, v in (s.get("stats") or {}).items()}
            if n_dup:
                dup_blocks += n_dup
                problems.append(f"dup-weekly-block: {display} "
                                f"{n_dup} duplicate 2026 weekly blocks; "
                                f"first kept")
            if not weekly:
                problems.append(f"no-weekly-blocks: {display} ({pos}); "
                                f"excluded")
                continue
            tid = pl.get("proTeamId") or 0
            team = team_map.get(int(tid), "")
            seen.add(canon)
            priced.append({"canon": canon, "display": display, "pos": pos,
                           "team": team, "weekly": weekly,
                           "season_blk": season_blk or {}})

    print(f"identity-resolved: {len(priced)} players", flush=True)

    # ---- 3. weekly components -> ROS sums, scoring ----
    rcols = [c for _, c in STATMAP]
    for p in priced:
        # per-week component dicts (all 18 weeks, for the weekly file)
        p["weeks"] = {}
        for w in range(1, 19):
            st = p["weekly"].get(w, {})
            p["weeks"][w] = {col: float(st.get(sid, 0) or 0)
                             for sid, col in STATMAP}
        ros = {c: round(sum(p["weeks"][w][c] for w in ros_weeks), 1)
               for c in rcols}
        p["ros"] = ros
        p["ros_half_ppr"] = round(sum(ros[c] * W[c] for c in rcols), 2)
        sb = p["season_blk"]
        sb_pts = sum(float(sb.get(sid, 0) or 0) * W[col]
                     for sid, col in STATMAP)
        p["season_block_half_ppr"] = round(sb_pts, 2)
        p["eligible"] = (
            ("r_pass_yds" in ros and ros["r_pass_yds"] != 0) if p["pos"] == "QB"
            else ("r_rush_yds" in ros and ros["r_rush_yds"] != 0)
            if p["pos"] == "RB"
            else (ros.get("r_rec_yds", 0) != 0 or
                  ros.get("r_receptions", 0) != 0))

    priced.sort(key=lambda p: -p["ros_half_ppr"])

    # ---- 4. change detection: hash of normalized payload ----
    h = hashlib.sha256()
    for p in priced:
        h.update(p["canon"].encode())
        h.update(p["pos"].encode())
        for w in range(1, 19):
            for c in rcols:
                h.update(f"{w}:{c}:{p['weeks'][w][c]:.4f}|".encode())
    digest = h.hexdigest()[:32]
    vintage = now_ct().strftime("%Y-%m-%d")

    prev = {}
    try:
        prev = json.load(open(META))
    except Exception:  # noqa: BLE001
        pass
    if not FORCE and prev.get("payload_hash") == digest:
        log_line("SUCCESS",
                 f"source=espn projections; no update, snapshot current "
                 f"(payload hash {digest} unchanged since "
                 f"{prev.get('vintage', '?')}); CSVs untouched")
        print(f"no update: payload hash unchanged ({digest}); CSVs untouched")
        return 0

    # ---- 5. atomic writes ----
    ensure_output_dirs()
    def fmt1(x):
        return f"{x:.1f}"

    def fmt2(x):
        return f"{x:.2f}"

    season_cols = (["player", "player_norm", "pos", "team",
                   "has_espn_projection", "eligible"] + rcols +
                   ["ros_half_ppr", "weeks_covered", "season_block_half_ppr",
                    "espn_snapshot_date"])
    with tempfile.NamedTemporaryFile("w", dir=str(FILES), delete=False,
                                     newline="") as tf:
        w = csv.writer(tf)
        w.writerow(season_cols)
        for p in priced:
            w.writerow([p["display"], p["canon"], p["pos"], p["team"],
                        "True", "True" if p["eligible"] else "False"] +
                       [fmt1(p["ros"][c]) for c in rcols] +
                       [fmt2(p["ros_half_ppr"]),
                        f"{ros_weeks[0]}-{ros_weeks[-1]}",
                        fmt2(p["season_block_half_ppr"]), vintage])
        tmp_season = tf.name
    weekly_cols = (["player", "pos", "team", "week"] + rcols +
                   ["half_ppr", "espn_snapshot_date"])
    with tempfile.NamedTemporaryFile("w", dir=str(FILES), delete=False,
                                     newline="") as tf:
        w = csv.writer(tf)
        w.writerow(weekly_cols)
        for p in priced:
            for wk in range(1, 19):
                wk_pts = sum(p["weeks"][wk][c] * W[c] for c in rcols)
                w.writerow([p["display"], p["pos"], p["team"], wk] +
                           [fmt1(p["weeks"][wk][c]) for c in rcols] +
                           [fmt2(wk_pts), vintage])
        tmp_weekly = tf.name
    meta = {"source": "espn", "leg_label": "ESPN projections",
            "model": "Mike Clay (per ESPN: powers the ESPN fantasy game)",
            "vintage": vintage, "payload_hash": digest,
            "season_id": SEASON_ID, "played_weeks": played,
            "ros_weeks": ros_weeks,
            "stat_keys": {sid: col for sid, col in STATMAP},
            "stat_key_calibration": "nflverse 2026 week-1 actuals, 2026-09-16",
            "ros_method": "sum of weekly projection blocks over unplayed "
                          "weeks; ESPN season block is a full-season "
                          "forecast on projected (not actual) week 1, "
                          "stored as season_block_half_ppr diagnostic",
            "coverage": {pos: sum(1 for p in priced if p["pos"] == pos)
                         for pos in POSITIONS},
            "n_priced": len(priced),
            "n_problems": len(problems)}
    with tempfile.NamedTemporaryFile("w", dir=str(HIDDEN), delete=False) as tf:
        json.dump(meta, tf, indent=1)
        tmp_meta = tf.name
    # ROS ppg sidecar (per-scoring legs): team bye = the ROS week where
    # the MAX weekly half_ppr across that team's priced players is 0
    # (team-level, so injured players can't fake a bye);
    # games_remaining = len(ros_weeks) - (1 if bye in ros_weeks else 0).
    # standard/full-PPR legs derive from receptions (verified 2026-09-16:
    # PPR - Standard equals receptions exactly):
    #   standard = half - 0.5*receptions; ppr = half + 0.5*receptions.
    team_wk_max = {}
    for p in priced:
        if not p["team"]:
            continue
        d = team_wk_max.setdefault(p["team"], {})
        for wk in ros_weeks:
            pts = sum(p["weeks"][wk][c] * W[c] for c in rcols)
            if pts > d.get(wk, 0.0):
                d[wk] = pts
    team_bye = {}
    for tm, d in team_wk_max.items():
        zero = [wk for wk in ros_weeks if d.get(wk, 0.0) == 0.0]
        team_bye[tm] = zero[0] if zero else None
    side_players = {}
    for p in priced:
        bye = team_bye.get(p["team"])
        gr = len(ros_weeks) - (1 if bye in ros_weeks else 0)
        half = p["ros_half_ppr"]
        rec = p["ros"]["r_receptions"]
        ros_std = round(half - 0.5 * rec, 2)
        ros_ppr = round(half + 0.5 * rec, 2)
        side_players[p["canon"]] = {
            "display": p["display"], "pos": p["pos"], "team": p["team"],
            "player_norm": p["canon"],
            "games_remaining": gr, "bye_week": bye,
            "espn_complete": bool(p["eligible"]),
            "ros": {"standard": ros_std, "half_ppr": half, "ppr": ros_ppr},
            "ppg": {
                "standard": round(ros_std / gr, 2) if gr else 0.0,
                "half_ppr": round(half / gr, 2) if gr else 0.0,
                "ppr": round(ros_ppr / gr, 2) if gr else 0.0},
        }
    sidecar = {"source": "espn", "leg_label": "ESPN projections",
               "vintage": vintage, "payload_hash": digest,
               "ros_weeks": ros_weeks, "players": side_players}
    with tempfile.NamedTemporaryFile("w", dir=str(HIDDEN), delete=False) as tf:
        json.dump(sidecar, tf, indent=1)
        tmp_side = tf.name
    os.replace(tmp_season, SEASON_CSV)
    os.replace(tmp_weekly, WEEKLY_CSV)
    os.replace(tmp_meta, META)
    os.replace(tmp_side, SIDECAR)

    # ---- 6. log ----
    excl = [x for x in problems
            if x.startswith(("identity-unresolved", "identity-pos-mismatch",
                             "identity-collision", "no-weekly-blocks",
                             "pos-slot-mismatch"))]
    n_elig = sum(1 for p in priced if p["eligible"])
    detail = (f"source=espn projections (Mike Clay model); vintage={vintage}; "
              f"hash={digest}; {len(priced)} priced ({n_elig} eligible) / "
              f"{len(excl)} excluded"
              + (f" ({'; '.join(excl[:12])}"
                 + ("; ..." if len(excl) > 12 else "") + ")" if excl else "") +
              f"; ROS=weeks {ros_weeks[0]}-{ros_weeks[-1]} weekly-sum "
              f"(played weeks detected: {played}); "
              f"stat keys 3/4/24/25/53/42/43 calibrated vs nflverse wk1; "
              f"season_block stored as diagnostic; "
              f"weekly file: {len(priced) * 18} player-weeks")
    log_line("SUCCESS", detail)
    for x in problems:
        print("  note: " + x, file=sys.stderr)
    print(f"wrote {len(priced)} season rows + {len(priced) * 18} weekly rows "
          f"(vintage {vintage}, hash {digest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
