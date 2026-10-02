"""Load FantasyPros ECR + projection CSVs into Supabase.

Reads data/fantasypros/{ecr,proj}_{qb,rb,wr,te}_wk{N}.csv (downloaded via the
browser task; the account owner authorized pulling weekly ECR/projection data).

Writes:
  - ECR CSVs  -> rankers (one 'FantasyPros ECR' row, idempotent) + ranker_rankings
  - proj CSVs -> projection_snapshots, source='fantasypros', all three scoring
    formats via engine.scoring (or staged JSON if the table doesn't exist yet)

Header-tolerant: projection stat columns are mapped POSITIONALLY per position
(FantasyPros repeats headers like YDS/TDS across passing/rushing/receiving
sections), but the header row is validated against the expected keyword
sequence before any row is trusted. A mismatch aborts that file loudly instead
of silently misaligning stats.

Usage:
  python3 loaders/fantasypros.py --week 1 --season 2026 [--as-of 2026-09-10T12:00:00-05:00]
  python3 loaders/fantasypros.py --self-test
"""
import argparse
import csv
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
DATA_DIR = os.path.join(BASE, "data", "fantasypros")
SB = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
for _p in (BASE, SB):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import sbclient
from engine import snapshot as snap
from engine.scoring import fantasy_points

POSITIONS = ["qb", "rb", "wr", "te", "k", "dst"]

# Expected stat-column keyword sequence AFTER the player/team columns, per
# position. Each entry: (keyword must appear in header cell, stat_key or None).
PROJ_SCHEMA = {
    # QB: Player, Team, ATT CMP YDS TDS INTS | ATT YDS TDS | FL FPTS
    "qb": [("att", "pass_att"), ("cmp", "cmp"), ("yds", "passing_yards"),
           ("td", "passing_tds"), ("int", "interceptions"),
           ("att", "rush_att"), ("yds", "rushing_yards"), ("td", "rushing_tds"),
           ("fl", "fumbles_lost"), ("fpts", None)],
    # RB: Player, Team, ATT YDS TDS | REC YDS TDS | FL FPTS
    "rb": [("att", "rush_att"), ("yds", "rushing_yards"), ("td", "rushing_tds"),
           ("rec", "receptions"), ("yds", "receiving_yards"), ("td", "receiving_tds"),
           ("fl", "fumbles_lost"), ("fpts", None)],
    # WR: Player, Team, REC YDS TDS | ATT YDS TDS | FL FPTS
    "wr": [("rec", "receptions"), ("yds", "receiving_yards"), ("td", "receiving_tds"),
           ("att", "rush_att"), ("yds", "rushing_yards"), ("td", "rushing_tds"),
           ("fl", "fumbles_lost"), ("fpts", None)],
    # TE: Player, Team, REC YDS TDS | FL FPTS
    "te": [("rec", "receptions"), ("yds", "receiving_yards"), ("td", "receiving_tds"),
           ("fl", "fumbles_lost"), ("fpts", None)],
    # K: Player, Team, FG FGA XPT FPTS (no PPR component; FPTS used as-is)
    "k": [("fg", "fg_made"), ("fga", "fg_att"), ("xpt", "pat_made"),
          ("fpts", None)],
    # DST: Player, SACK INT FR FF TD SAFETY PA YDS AGN FPTS (no Team column;
    # player name is the full team name, e.g. "Seattle Seahawks")
    "dst": [("sack", "sacks"), ("int", "interceptions"),
            ("fr", "fumble_recoveries"), ("ff", "forced_fumbles"),
            ("td", "def_tds"), ("safety", "safeties"),
            ("pa", "points_allowed"), ("ydsagn", "yards_allowed"),
            ("fpts", None)],
}

# Header column where the stat block starts. Every position's CSV has
# Player[, Team] first; DST has no Team column.
PROJ_STAT_OFFSET = {"dst": 2}  # 2026-09-16: real DST export has an (empty)
# Team column at index 1; stat columns start at index 2 like every position.

# Positions whose projected points are the source's own FPTS column used
# directly for all three scoring formats (no engine.scoring translation):
# K and DST have no reception component, so standard == half_ppr == full_ppr.
FPTS_DIRECT = {"k", "dst"}


def norm_header(h):
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def find_col(headers, *cands):
    """Return index of first header matching any candidate (normalized)."""
    nh = [norm_header(h) for h in headers]
    for c in cands:
        if c in nh:
            return nh.index(c)
    return None


def parse_num(v):
    try:
        return float((v or "").strip().replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def parse_int(v):
    try:
        return int(float((v or "").strip().replace(",", "")))
    except (ValueError, AttributeError):
        m = re.search(r"\d+", str(v or ""))
        return int(m.group()) if m else None


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    # drop fully-blank rows
    rows = [r for r in rows if any(c.strip() for c in r)]
    return rows[0], rows[1:]


# Canonical identity (2026-09-18): FantasyPros names resolve through the
# players table to a numeric player_key via engine/canonical_players.
# The private ALIASES table is dead (subsumed by the shared NICKNAMES).
# Returns the registry entry (player_key, uuid, team_id, ...) or None
# (fail-closed on ambiguity/no-match).
def match_player(name, registry=None):
    from engine.canonical_players import resolve_skill, load_registry
    reg = registry or load_registry()
    key = resolve_skill(name, registry=reg)
    if key is None:
        return None
    return reg.by_key.get(key)


# ECR types: weekly (in-season, per week), draft (preseason redraft),
# ros (rest-of-season, pulled mid-season), dynasty (long-term value).
# CSV naming: ecr_{pos}_wk{N}.csv (weekly), ecr_draft_{pos}.csv,
#             ecr_ros_{pos}_wk{N}.csv, ecr_dynasty_{pos}.csv
ECR_TYPES = ["weekly", "draft", "ros", "dynasty"]
ECR_LABEL = {"weekly": "Weekly", "draft": "Draft",
             "ros": "ROS", "dynasty": "Dynasty"}


def ecr_csv_path(ecr_type, pos, week):
    if ecr_type == "weekly":
        return os.path.join(DATA_DIR, f"ecr_{pos}_wk{week}.csv")
    if ecr_type == "ros":
        return os.path.join(DATA_DIR, f"ecr_ros_{pos}_wk{week}.csv")
    if ecr_type == "draft":
        return os.path.join(DATA_DIR, f"ecr_draft_{pos}.csv")
    if ecr_type == "dynasty":
        return os.path.join(DATA_DIR, f"ecr_dynasty_{pos}.csv")
    raise ValueError(f"unknown ecr_type {ecr_type}")


# JEG-86 / Jeremy 2026-10-02: the dataset's week must come from the page
# evidence, not from the caller's --week. For the CSV path the URL slug
# analog is the filename week: ecr_qb_wk4.csv -> 4, proj_wr_wk5.csv -> 5.
# The page headline analog is whatever evidence the upstream page puller
# (ops/watchdog/pull_fantasypros.py) cached; that lives in a sidecar JSON
# named <csv>.week.json next to the CSV. We validate filename week against
# the requested --week and against the sidecar, fail-closed on any mismatch.
_FP_WEEK_FROM_FILENAME = re.compile(r"_wk(\d+)(?:\.csv)?$", re.I)


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def extract_week_from_filename(path: str) -> int | None:
    """Extract week number from the CSV filename (URL-slug analog).

    Matches `_wk<N>` immediately before the `.csv` suffix (or at end of
    stem). e.g. "ecr_qb_wk4.csv" -> 4, "proj_wr_wk5.csv" -> 5,
    "ecr_ros_qb_wk3.csv" -> 3. Returns None for non-week-stamped files
    (draft / dynasty / season snapshots) so the guard only fires for files
    that actually encode a week.
    """
    base = os.path.basename(path)
    m = _FP_WEEK_FROM_FILENAME.search(base)
    return int(m.group(1)) if m else None


def fp_week_sidecar_path(csv_path: str) -> str:
    """Path to the week_evidence sidecar JSON cached by the page puller."""
    return csv_path + ".week.json"


def validate_filename_week_consistency(csv_path: str,
                                       requested_week: int | None) -> dict:
    """Validate the CSV filename's week against the requested --week, and
    against any cached week_evidence sidecar from the page puller.

    Fail-closed: raises RuntimeError on any mismatch. A dataset without a
    validated week is worse than no dataset.

    The CSV loader is week-stamped by its filename (the URL-slug analog for
    the snapshot path). The page-pull sidecar (writeable by
    ops/watchdog/pull_fantasypros.py) carries the page headline evidence;
    when present, the filename week must agree with the headline week —
    the same URL==title check as the page puller, just one hop downstream.
    """
    filename_week = extract_week_from_filename(csv_path)
    if filename_week is None:
        # Draft / dynasty / season-snapshot CSVs are not week-stamped; only
        # fail if the caller explicitly asked for a non-zero week, which is a
        # caller/snapshot mismatch we should never silently accept.
        if requested_week not in (None, 0):
            raise RuntimeError(
                "FantasyPros CSV %s has no week in filename but caller "
                "requested week=%d. Refusing to label without week evidence."
                % (csv_path, requested_week))
        return {"week": 0, "week_filename": None,
                "week_requested": requested_week, "week_titles": []}

    if requested_week is not None and filename_week != requested_week:
        raise RuntimeError(
            "FantasyPros CSV filename week (%d) != requested week (%d) "
            "(path=%s). Refusing to label dataset without week evidence."
            % (filename_week, requested_week, csv_path))

    sidecar = read_json(fp_week_sidecar_path(csv_path))
    sidecar_week = (sidecar or {}).get("week")
    sidecar_titles = ((sidecar or {}).get("week_evidence") or {}).get(
        "week_titles") or []
    if sidecar_week is not None and sidecar_week != filename_week:
        raise RuntimeError(
            "FantasyPros CSV filename week (%d) != page puller week (%d) "
            "(path=%s, sidecar=%s). Page evidence does not match the "
            "snapshot; refusing to label dataset."
            % (filename_week, sidecar_week, csv_path,
               fp_week_sidecar_path(csv_path)))

    return {
        "week": filename_week,
        "week_filename": filename_week,
        "week_requested": requested_week,
        "week_titles": sidecar_titles,
        "week_sidecar_week": sidecar_week,
    }


def upsert_ranker(pos, ecr_type="weekly"):
    """One rankers row per position per ECR type ('FantasyPros Weekly ECR QB').

    Per-position rankers keep the delete+refresh scoped: ranker_rankings has no
    position column, so a single shared ranker would let one position's
    refresh wipe the others."""
    if ecr_type not in ECR_TYPES:
        raise ValueError(f"unknown ecr_type {ecr_type}")
    name = f"FantasyPros {ECR_LABEL[ecr_type]} ECR {pos.upper()}"
    found = sbclient.get("rankers", f"?select=id,ecr_type&display_name=eq.{name.replace(' ', '%20')}&limit=1")
    if found:
        rid = found[0]["id"]
        if found[0].get("ecr_type") != ecr_type:
            sbclient.patch("rankers", {"ecr_type": ecr_type},
                           f"?id=eq.{rid}")
        return rid
    rid = str(uuid.uuid4())
    sbclient.post("rankers", [{
        "id": rid, "display_name": name, "ecr_type": ecr_type,
        "affiliation": "FantasyPros", "active": True,
        "metadata": {"kind": "consensus", "cadence": "weekly"
                     if ecr_type in ("weekly", "ros") else "static",
                     "position": pos},
    }])
    return rid


def load_ecr(pos, week, season, recorded_at, ecr_type="weekly"):
    path = ecr_csv_path(ecr_type, pos, week)
    if not os.path.exists(path):
        return {"skipped": f"missing {path}"}
    # JEG-86 / Jeremy 2026-10-02: the dataset's week must come from page
    # evidence, not from the caller. Validate the CSV filename week against
    # the caller's --week before any row is trusted; fail closed otherwise.
    week_evidence = validate_filename_week_consistency(path, week)
    headers, rows = read_csv(path)
    i_player = find_col(headers, "player", "playername")
    i_rank = find_col(headers, "rk", "rank", "ecr", "rankecr", "thisweekrk")
    i_team = find_col(headers, "team")
    i_proj = find_col(headers, "projfpts", "fpts", "proj")
    if i_player is None or i_rank is None:
        raise ValueError(f"{path}: cannot find player/rank columns in {headers}")
    ranker_id = upsert_ranker(pos, ecr_type)
    from engine.canonical_players import load_registry
    _reg = load_registry()
    # week scoping: weekly/ros are week-stamped (ros = "as of week N");
    # draft/dynasty are not week-scoped -> week 0
    w = week if ecr_type in ("weekly", "ros") else 0
    # idempotent refresh: drop this scope's rows for this position's ranker
    sbclient.delete("ranker_rankings",
                    f"?ranker_id=eq.{ranker_id}&season=eq.{season}&week=eq.{w}")
    out, gaps, seen = [], [], set()
    ranks = {}  # player_id -> position rank, reused by load_projections
    for r in rows:
        if len(r) < len(headers):
            continue  # tier separator / ragged row
        name = r[i_player].strip()
        if not name:
            continue
        key = snap.norm(name)
        if key in seen:
            gaps.append(f"{name} (dup row, kept best rank)")
            continue
        seen.add(key)
        pl = match_player(name, _reg)
        if pl is None:
            gaps.append(name)
            continue
        rank = parse_int(r[i_rank])
        out.append({
            "ranker_id": ranker_id, "player_id": pl["uuid"],
            "player_key": pl["player_key"],
            "season": season, "week": w,
            "ranking": rank, "position_rank": rank,
            "projected_points": parse_num(r[i_proj]) if i_proj is not None else None,
            "recorded_at": recorded_at,
        })
        if rank is not None:
            ranks[pl["uuid"]] = rank
    for i in range(0, len(out), 200):
        sbclient.post("ranker_rankings", out[i:i + 200])
    return {"ranker_id": ranker_id, "rows": len(out), "gaps": gaps,
            "ranks": ranks}


def validate_proj_headers(pos, headers):
    """Check the stat columns follow the expected keyword sequence. Returns the
    column indexes aligned to PROJ_SCHEMA[pos], or raises."""
    offset = PROJ_STAT_OFFSET.get(pos, 2)
    # first `offset` columns should start with a player-ish column
    if find_col(headers[:offset + 1], "player", "playername") is None:
        raise ValueError(f"no player column in first {offset + 1} headers: {headers[:offset + 2]}")
    schema = PROJ_SCHEMA[pos]
    stat_headers = headers[offset:offset + len(schema)]
    idx = []
    for j, (kw, _key) in enumerate(schema):
        h = norm_header(stat_headers[j]) if j < len(stat_headers) else ""
        # keyword match: 'yds' matches 'yds', 'passyds', etc.; 'td' must not
        # match 'tds' confusion — accept either
        ok = kw in h or (kw == "td" and "td" in h)
        if not ok:
            raise ValueError(
                f"header mismatch at stat col {j}: expected keyword '{kw}', "
                f"got '{stat_headers[j] if j < len(stat_headers) else None}'. "
                f"Full headers: {headers}")
        idx.append(offset + j)
    return idx


def load_projections(pos, week, season, snapshot_at, batch_id, ecr_ranks=None):
    """Parse one projections CSV; returns (rows, gaps). Rows are accumulated
    by main() and written once so the pending-JSON path can't clobber.

    ecr_ranks: optional {player_id: position_rank} from load_ecr() so the
    snapshot rows carry the ECR rank (v_latest_signals needs it for rank_gap).
    """
    path = os.path.join(DATA_DIR, f"proj_{pos}_wk{week}.csv")
    if not os.path.exists(path):
        return None
    # JEG-86 / Jeremy 2026-10-02: validate the snapshot week from filename +
    # optional page-puller sidecar against the caller's --week. Fail closed.
    week_evidence = validate_filename_week_consistency(path, week)
    headers, rows = read_csv(path)
    col_idx = validate_proj_headers(pos, headers)
    schema = PROJ_SCHEMA[pos]
    from engine.canonical_players import load_registry
    _reg = load_registry()
    _, by_team = snap.load_week_games(season, week)
    ecr_ranks = ecr_ranks or {}
    out_rows, gaps = [], []
    for r in rows:
        name = r[0].strip()
        if not name:
            continue
        pl = match_player(name, _reg)
        if pl is None:
            gaps.append(name)
            continue
        stats = {}
        for j, (_kw, key) in enumerate(schema):
            if key:
                stats[key] = parse_num(r[col_idx[j]])
        game = by_team.get(pl["team_id"])
        if game is None:
            gaps.append(f"{name} (no week-{week} game)")
            continue
        if pos in FPTS_DIRECT:
            # K/DST: no reception component and no engine.scoring table, so
            # the source's own FPTS is the median for all three formats.
            fpts_col = col_idx[[kw for kw, _ in schema].index("fpts")]
            fp_pts = parse_num(r[fpts_col])
        for fmt in ("standard", "half_ppr", "full_ppr"):
            if pos in FPTS_DIRECT:
                projected = fp_pts
            else:
                scoring_key = "ppr" if fmt == "full_ppr" else fmt
                projected = fantasy_points(stats, scoring_key)
            out_rows.append({
                "batch_id": batch_id, "player_id": pl["uuid"],
                "player_key": pl["player_key"], "game_id": game["id"],
                "season": season, "week": week, "source": "fantasypros",
                "scoring_format": fmt,
                "projected_points": projected,
                "ecr_rank": ecr_ranks.get(pl["uuid"]),
                "vegas_rank": None,
                "snapshot_at": snapshot_at,
                "vintage_note": "FantasyPros consensus projections CSV",
            })
    return out_rows, gaps


def read_projections_dict(week, data_dir=None):
    """Expert points from the ECR feed's weekly projections CSVs.

    Returns {norm_name: {'name','std','half','ppr','td_exp'}} — the same
    shape as the old ESPN loader (v4.compute_v4.load_espn_full) keyed by
    engine.snapshot.norm, so it drops into rank_deltas_by_position as
    expert_pts. 'td_exp' is the expected total TDs (passing + rushing +
    receiving) from the CSV's granular stat columns. Reads the CSVs
    directly (no players-table join), so loader mapping gaps don't apply.
    Raises FileNotFoundError when a position CSV is missing.
    """
    data_dir = data_dir or DATA_DIR
    out = {}
    for pos in POSITIONS:
        if pos in FPTS_DIRECT:
            # K/DST are not part of rank-delta expert comparisons
            # (no ECR rank feed); skip rather than mis-scoring.
            continue
        path = os.path.join(data_dir, f"proj_{pos}_wk{week}.csv")
        if not os.path.exists(path):
            raise FileNotFoundError(f"missing {path}")
        headers, rows = read_csv(path)
        col_idx = validate_proj_headers(pos, headers)
        schema = PROJ_SCHEMA[pos]
        for r in rows:
            name = (r[0] or "").strip()
            if not name:
                continue
            stats = {}
            for j, (_kw, key) in enumerate(schema):
                if key:
                    stats[key] = parse_num(r[col_idx[j]] if col_idx[j] < len(r) else "")
            if not any(stats.values()):
                continue
            out[snap.norm(name)] = {
                "name": name,
                "std": fantasy_points(stats, "standard"),
                "half": fantasy_points(stats, "half_ppr"),
                "ppr": fantasy_points(stats, "ppr"),
                "td_exp": (stats.get("passing_tds", 0.0)
                           + stats.get("rushing_tds", 0.0)
                           + stats.get("receiving_tds", 0.0)),
            }
    return out


def self_test():
    """Validate the positional schemas against synthetic FP-style headers."""
    cases = {
        "qb": ["Player", "Team", "ATT", "CMP", "YDS", "TDS", "INTS",
               "ATT", "YDS", "TDS", "FL", "FPTS"],
        "rb": ["Player", "Team", "ATT", "YDS", "TDS",
               "REC", "YDS", "TDS", "FL", "FPTS"],
        "wr": ["Player", "Team", "REC", "YDS", "TDS",
               "ATT", "YDS", "TDS", "FL", "FPTS"],
        "te": ["Player", "Team", "REC", "YDS", "TDS", "FL", "FPTS"],
        "k": ["Player", "Team", "FG", "FGA", "XPT", "FPTS"],
        "dst": ["Player", "SACK", "INT", "FR", "FF", "TD", "SAFETY",
                "PA", "YDS AGN", "FPTS"],
    }
    for pos, hdr in cases.items():
        idx = validate_proj_headers(pos, hdr)
        off = PROJ_STAT_OFFSET.get(pos, 2)
        assert idx == list(range(off, off + len(PROJ_SCHEMA[pos]))), pos
    # a bad header must raise, not misalign
    try:
        validate_proj_headers("qb", ["Player", "Team", "REC", "YDS", "TDS",
                                     "FL", "FPTS", "X", "X", "X", "X", "X"])
        raise AssertionError("bad headers did not raise")
    except ValueError:
        pass
    print("self-test OK: 6 schemas validate, misalignment raises")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--as-of", default=None,
                    help="ISO timestamp for recorded_at/snapshot_at; defaults to now")
    ap.add_argument("--ecr-only", action="store_true")
    ap.add_argument("--proj-only", action="store_true")
    ap.add_argument("--ecr-type", default="weekly",
                    choices=ECR_TYPES,
                    help="which ECR to load (default weekly)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
        return
    ts = a.as_of or datetime.now(timezone.utc).isoformat()
    batch_id = str(uuid.uuid4())
    all_proj_rows = []
    # projections are weekly-only; non-weekly ECR runs skip them
    ecr_only = a.ecr_only or a.ecr_type != "weekly"
    for pos in POSITIONS:
        ecr_ranks = {}
        if not a.proj_only:
            try:
                r = load_ecr(pos, a.week, a.season, ts, ecr_type=a.ecr_type)
                ecr_ranks = r.get("ranks", {})
                print(f"ecr_{a.ecr_type}_{pos}:", {k: (v if k != "gaps" else f"{len(v)} gaps: {v[:6]}")
                                      for k, v in r.items() if k != "ranks"})
            except FileNotFoundError:
                print(f"ecr_{a.ecr_type}_{pos}: missing file, skipped")
        if not ecr_only:
            res = load_projections(pos, a.week, a.season, ts, batch_id,
                                   ecr_ranks)
            if res is None:
                print(f"proj_{pos}: missing file, skipped")
            else:
                rows, gaps = res
                all_proj_rows.extend(rows)
                print(f"proj_{pos}: {len(rows)} rows, {len(rows)//3} players, "
                      f"{len(gaps)} gaps: {gaps[:6] if gaps else []}")
    if all_proj_rows and not ecr_only:
        dest, info = snap.write_rows(all_proj_rows, batch_id)
        print(f"projections -> {dest}: {info} ({len(all_proj_rows)} rows)")
    print("batch_id:", batch_id)


if __name__ == "__main__":
    main()
