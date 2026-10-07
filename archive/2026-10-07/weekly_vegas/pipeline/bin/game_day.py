"""Game-day cards: same-day abbreviated X posts for non-Sunday games.

The Sunday chain (bin/weekly_chain.py) builds the full weekly queue, but
Thursday/Monday/Saturday games need same-day cards with fresh data, not
Sunday's snapshot. Intended schedule: twice on game days (10:00 and
15:00 America/Chicago).

Pipeline per run:
  1. Find non-Sunday games kicking off TODAY (America/Chicago date).
  2. Per game (idempotent): skip if a gameday post_queue row already exists
     for this game + week (any status) -> resolve the Odds API event ->
     force a FRESH props pull (per-event cache bypassed) -> readiness gate:
     skip quietly ("betting not open yet") when no player props are posted.
  3. ESPN ROS freshness gate (fail-closed): file recency on
     data/inputs/espn_projections.csv AND content-vintage check on the
     espn_snapshot_date embedded in that file (when ESPN last changed its
     numbers, NOT when we last downloaded them).
  4. engine/snapshot_v4.main(week) once + injury refresh once
     (both skipped in --dry-run).
  5. Recompute signals with the same logic as v4/compute_v4 (rank deltas,
     coverage gate, injury gate) but WITHOUT its post_queue draft rotation
     AND with the ESPN ROS leg replacing the retired ECR feed for both
     expert points and positional ranks (JEG-418). Filter post-worthy
     signals to the two teams; one abbreviated tweet per game.
  6. Movement arrows: per-side movement (vegas vs expert) vs the most
     recent prior projection_snapshots batch for the week, annotated only
     when |move| >= 1.0 implied PPR pts; over-long cards truncate to the
     top 6 signals by |Δ|.
  7. Write post_type='gameday', status='draft' rows (--dry-run prints only).

--dry-run semantics: no post_queue writes, no snapshot batches, no
injury-loader writes. The odds pull still runs (dedupe-guarded, needed for
the readiness gate); everything else is read-only.

Exit codes: 0 ok / nothing-to-do, 2 BLOCKED (stale ESPN pull, stale ESPN
content, or missing ESPN projections file).

Expert-leg source (JEG-418): ESPN ROS via
weekly_vegas/pipeline/data/espn_projections.csv (Mike Clay model, per ESPN).
The retired weekly-expert-projection feed is no longer read by game-day;
positional ranks for the rank-delta computation come from sorting ESPN's
own ROS half-PPR per position.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "collectors"))
sys.path.insert(0, os.path.expanduser("~/workspace/skills/the-odds-api/bin"))
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))

import sbclient  # noqa: E402
import odds_api  # noqa: E402
import oddsclient  # noqa: E402
from engine.week import current_week  # noqa: E402
from engine.disagreement import (  # noqa: E402
    rank_deltas_by_position, _x_len, _short_name,
)
from engine.vegas import (  # noqa: E402
    vegas_implied_points, vegas_provenance, completeness_gaps,
)
from engine.fds_fallback import (  # noqa: E402
    load_payload as fds_load_payload, index_payload as fds_index_payload,
    build_vegas_legs, validate_signal_rows, is_publishable,
)
from engine.source_priority import VEGAS_SOURCE_PRIORITY  # noqa: E402
from v4.compute_v4 import (  # noqa: E402
    load_props, norm,
)
from engine.snapshot_v4 import main as snapshot_main  # noqa: E402
from engine.snapshot import load_players, norm_loose  # noqa: E402

CT = ZoneInfo("America/Chicago")
# JEG-418: ESPN ROS expert-leg source (Mike Clay model per ESPN).
# Season file lives at <repo>/data/inputs/; the weekly per-week file is
# written next to it by pipelines/pull_espn_projections.py and used when
# present (per-week half_ppr), else we fall back to ROS / games_remaining.
ESPN_PROJECTIONS_CSV = os.path.join(BASE, "data", "..", "..", "data",
                                    "inputs", "espn_projections.csv")
ESPN_PROJECTIONS_CSV = os.path.normpath(ESPN_PROJECTIONS_CSV)
ESPN_WEEKLY_CSV = os.path.normpath(
    os.path.join(BASE, "data", "..", "..", "data", "inputs",
                 "espn_weekly_projections.csv"))
CACHE_DIR = os.path.join(BASE, "data", "odds_cache")
DAY_LABEL = {"Thursday": "TNF", "Monday": "MNF",
             "Saturday": "SAT", "Friday": "FRI"}
MOVE_THRESHOLD = 1.0  # annotate a side only when |move| >= 1.0 implied PPR pts
MAX_GAMEDAY_SIGNALS = 6  # per-card cap when the full card exceeds 280 chars


# ------------------------------------------- ESPN content-vintage helpers
# JEG-418: the expert numbers now come from ESPN ROS (Mike Clay model per
# ESPN). Same fail-closed two-layer philosophy as the old ECR gate:
#  1. Pull recency: data/inputs/espn_projections.csv mtime must be inside
#     the most recent refresh window. The puller runs daily at 06:10 CT and
#     rewrites the file only when ESPN's numbers actually change (hash
#     no-op), so an unchanged file means ESPN's content is itself stable.
#  2. Content vintage: the espn_snapshot_date column is the date ESPN's own
#     payload last changed. That is the "when the source last changed its
#     numbers" signal the old gate measured via projection_snapshots
#     fingerprinting. A re-pull that captures byte-identical numbers must
#     not reset this clock.
# Experts publish Tue-Sun, never Mondays; the puller is daily 06:10 CT, so a
# legitimate content gap is ~2-3 days. Content older than ESPN_MAX_AGE_DAYS
# means the experts haven't moved their numbers in too long -> stale for
# "Vegas vs experts" game-day cards. Fail-closed: any error computing the
# vintage blocks the run.
ESPN_MAX_AGE_DAYS = 3
ESPN_REFRESH_HOUR_CT = 9  # 06:10 CT daily; allow 3h slop before failing recency


def _espn_snapshot_date(csv_path):
    """Latest espn_snapshot_date in the CSV (the source-side "last changed"
    column, NOT the file mtime). Returns date or None on any error."""
    try:
        import csv as _csv
        with open(csv_path, newline="") as f:
            r = _csv.DictReader(f)
            latest = None
            for row in r:
                v = (row.get("espn_snapshot_date") or "").strip()
                if not v:
                    continue
                try:
                    d = datetime.fromisoformat(v).date()
                except ValueError:
                    continue
                if latest is None or d > latest:
                    latest = d
            return latest
    except (OSError, KeyError, ValueError):
        return None


def load_espn_ros(csv_path=None, week=None):
    """ESPN ROS expert leg -> (expert_pts, ecr_by_pos, meta, official).

    Returns the same shape that the retired ECR feed provided (see
    v4/compute_v4.load_ecr + loaders/fantasypros.read_projections_dict) so
    build_signals()'s downstream call to rank_deltas_by_position stays
    unchanged.

      expert_pts[k] = {'name', 'std', 'half', 'ppr'}  (per-player, for week N)
      ecr_by_pos[pos][k] = pos_rank int  (1 = best at the position)
      meta[k] = {'name', 'team', 'pos'}
      official[k] = pos_rank str  (e.g. 'WR3')

    For per-week expert points: prefer espn_weekly_projections.csv (per-week
    half_ppr), fall back to espn_projections.csv's ROS half_ppr split across
    ROS-weeks count. Positional ranks come from sorting ESPN's own ROS
    half_ppr desc within each position (Mike Clay's ordering is the
    ranking — same philosophy as FantasyPros ECR rank did, just sourced
    from ESPN now). Returns ({}, {}, {}, {}) on any read failure
    (fail-closed; caller blocks the run)."""
    csv_path = csv_path or ESPN_PROJECTIONS_CSV
    out_pts, out_by_pos, meta, official = {}, defaultdict(dict), {}, {}
    if not os.path.exists(csv_path):
        return out_pts, out_by_pos, meta, official
    try:
        import csv as _csv
        # Optional per-week file. The puller writes it when content
        # changes; an absent file means we split ROS evenly below.
        weekly = {}
        if os.path.exists(ESPN_WEEKLY_CSV):
            with open(ESPN_WEEKLY_CSV, newline="") as f:
                for r in _csv.DictReader(f):
                    try:
                        wk = int(r.get("week") or 0)
                    except ValueError:
                        continue
                    key = (r.get("player_norm") or "").strip()
                    if not key:
                        continue
                    try:
                        weekly[(key, wk)] = float(r.get("half_ppr") or 0.0)
                    except ValueError:
                        continue
        rows = []
        with open(csv_path, newline="") as f:
            for r in _csv.DictReader(f):
                key = (r.get("player_norm") or "").strip()
                if not key:
                    continue
                try:
                    half = float(r.get("ros_half_ppr") or 0.0)
                except ValueError:
                    continue
                rows.append({"key": key, "name": (r.get("player") or "").strip(),
                             "pos": (r.get("pos") or "").strip(),
                             "team": (r.get("team") or "").strip(),
                             "half": half,
                             "weeks_covered": (r.get("weeks_covered") or "").strip()})
        # Per-week expert points: prefer the weekly CSV's per-row half_ppr;
        # else split ROS evenly across the ROS weeks span.
        def per_week_half(p):
            if week is not None and (p["key"], int(week)) in weekly:
                return weekly[(p["key"], int(week))]
            try:
                a, b = p["weeks_covered"].split("-")
                n = max(1, int(b) - int(a) + 1)
            except (ValueError, AttributeError):
                n = 1
            return p["half"] / n
        for p in rows:
            hw = per_week_half(p)
            std = hw - 0.5 * 0  # half-ppr minus 0 receptions weight = same as half
            # PPR derivation (consistent with pull_espn_projections.py):
            #   half = std + 0.5*receptions;  ppr = half + 0.5*receptions
            # We don't have per-player receptions here, so we mirror the
            # vegas-leg derivation: std = half - 0.5*receptions (with
            # receptions=0 -> std == half), ppr = half + 0.5*receptions
            # (receptions=0 -> ppr == half). Game-day cards render PPR
            # only; std/ppr are present for engine.disagreement's contract.
            out_pts[p["key"]] = {"name": p["name"], "std": hw,
                                 "half": hw, "ppr": hw}
            meta[p["key"]] = {"name": p["name"], "team": p["team"],
                              "pos": p["pos"]}
        # Positional ranks from ESPN's own ROS ordering (Mike Clay).
        by_pos = defaultdict(list)
        for p in rows:
            if p["pos"]:
                by_pos[p["pos"]].append(p["key"])
        for pos, keys in by_pos.items():
            keys.sort(key=lambda k: -(out_pts[k]["half"] if k in out_pts else 0))
            for i, k in enumerate(keys, start=1):
                out_by_pos[pos][k] = i
                if k in meta:
                    official[k] = f"{pos}{i}"
    except (OSError, ValueError, KeyError):
        return {}, defaultdict(dict), {}, {}
    return out_pts, out_by_pos, meta, official


# ------------------------------------------------------------------ ESPN gate
def check_espn_gate(csv_path=None, now=None, season=2026, week=None):
    """Fail-closed ESPN ROS recency gate (two layers; JEG-418).

    1. Pull recency: data/inputs/espn_projections.csv mtime must be within
       the most recent daily refresh window (06:10 CT, hour-anchored). The
       puller is no-op when ESPN's numbers are unchanged, so an old mtime
       alone does not prove stale content — Layer 2 confirms.
    2. Content vintage: the espn_snapshot_date column inside the CSV is the
       date ESPN's payload last changed. That is the "when the source last
       changed its numbers" clock the old ECR gate measured via DB snapshot
       fingerprinting. A re-pull that captures byte-identical numbers must
       not reset it.
    Returns (ok, message); caller exits 2 on failure.
    """
    csv_path = csv_path or ESPN_PROJECTIONS_CSV
    now = now or datetime.now(CT)
    today = now.date()
    week = week if week is not None else current_week(season)
    # Layer 1: pull recency. Anchor on the most recent refresh-day at 09:00
    # CT (06:10 pull + 3h slop). Before today's anchor -> previous day.
    anchor = now.replace(hour=ESPN_REFRESH_HOUR_CT, minute=0, second=0,
                         microsecond=0)
    if anchor > now:
        anchor -= timedelta(days=1)
    try:
        mtime = datetime.fromtimestamp(
            os.path.getmtime(csv_path), tz=timezone.utc).astimezone(CT)
    except OSError:
        return False, f"BLOCKED: {csv_path} missing"
    if mtime < anchor:
        age = now - mtime
        return False, (f"BLOCKED: {csv_path} stale pull: "
                      f"mtime {mtime:%Y-%m-%d %H:%M %Z} < "
                      f"required {anchor:%Y-%m-%d %H:%M %Z} (age {age})")
    # Layer 2: ESPN content vintage (source-side change date).
    vintage = _espn_snapshot_date(csv_path)
    if vintage is None:
        return False, ("BLOCKED: could not determine ESPN content "
                       f"vintage from {csv_path} (fail-closed)")
    age_days = (today - vintage).days
    if age_days > ESPN_MAX_AGE_DAYS:
        return False, (f"BLOCKED: ESPN content stale: week-{week} ESPN "
                       f"projections unchanged since {vintage} "
                       f"({age_days}d > {ESPN_MAX_AGE_DAYS}d max)")
    return True, (f"ESPN fresh: pulled {mtime:%Y-%m-%d %H:%M %Z}; "
                  f"week-{week} ESPN content vintage {vintage} "
                  f"({age_days}d old)")


# ------------------------------------------------------------ game detection
def find_todays_games(season=2026, now=None):
    """Non-Sunday games kicking off today (America/Chicago date)."""
    now = now or datetime.now(CT)
    today = now.date()
    rows = sbclient.get_all(
        "games",
        f"?season=eq.{season}&status=neq.final"
        "&select=id,week,home_team_id,away_team_id,starts_at",
    )
    out = []
    for g in rows:
        sa = g.get("starts_at")
        if not sa:
            continue
        try:
            dt = datetime.fromisoformat(sa.replace("Z", "+00:00")).astimezone(CT)
        except Exception:
            continue
        if dt.date() == today and dt.weekday() != 6:  # 6 == Sunday
            out.append(dict(g, _kickoff_ct=dt))
    return sorted(out, key=lambda g: g["starts_at"])


def already_handled(away, home, week):
    """Idempotency: a gameday row for this game + week in any status."""
    rows = sbclient.get("post_queue", "?post_type=eq.gameday&select=id,note")
    prefix = f"gameday wk{week} {away}@{home}"
    return any((r.get("note") or "").startswith(prefix) for r in rows)


# ------------------------------------------------- odds event + fresh props
def resolve_event_id(game_id):
    """Map our games.id -> Odds API event id (free /events endpoint)."""
    games_idx = odds_api._games_index()
    events, _ = oddsclient.events()
    now = datetime.now(timezone.utc)
    for ev in sorted(events, key=lambda e: e.get("commence_time", "")):
        try:
            ct = datetime.fromisoformat(
                ev["commence_time"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ct <= now:
            continue
        if odds_api._match_game(ev, games_idx) == game_id:
            return ev["id"]
    return None


def fresh_pull(event_id):
    """Force a same-day pull: delete the 12h per-event cache, then snapshot.

    odds_history inserts are dedupe-guarded (identical re-runs write
    nothing), so a forced re-pull is safe.
    """
    p = os.path.join(CACHE_DIR, f"props_{event_id}.json")
    if os.path.exists(p):
        os.remove(p)
    return odds_api.snapshot(event_ids=[event_id])


def props_open(event_id):
    """Readiness gate: did the fresh pull find player props with data?"""
    p = os.path.join(CACHE_DIR, f"props_{event_id}.json")
    try:
        data = json.load(open(p))
    except Exception:
        return False
    for bm in data.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt.get("key", "").startswith("player_") and mkt.get("outcomes"):
                return True
    return False


# ------------------------------------------------------------- injury refresh
def refresh_injuries():
    """Same loader entry points as the Wed/Fri injury crons (league-wide)."""
    cmds = [
        [sys.executable, os.path.join(BASE, "loaders", "sleeper.py"),
         "--skip-players", "--skip-trending"],
        [sys.executable, os.path.join(BASE, "loaders", "nflverse.py"),
         "--injuries-only"],
    ]
    for cmd in cmds:
        name = os.path.basename(cmd[1])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            print(f"injuries {name}: rc={r.returncode} "
                  f"{(r.stdout or '')[-400:]}", flush=True)
            if r.returncode != 0:
                print(f"WARNING: {name} failed: {(r.stderr or '')[-300:]}",
                      flush=True)
        except Exception as e:
            print(f"WARNING: injury refresh {name} failed: {e}", flush=True)


# ------------------------------------------------------- signal computation
def build_signals(week, season=2026):
    """Same signal-building logic as v4/compute_v4.main, but WITHOUT the
    post_queue draft rotation (game-day must not disturb existing drafts)
    and with ESPN ROS replacing the retired ECR feed (JEG-418) for both
    expert points and positional ranks."""
    expert_pts, ecr_by_pos, meta, official = load_espn_ros(week=week)
    player_props, td_cover, _prop_meta = load_props()

    # Local raw-book leg (The Odds API -> engine.vegas). Under the
    # FDS-primary design (user-approved 2026-09-17) these numbers are the
    # AUDIT leg: computed into separate dicts first, then applied over the
    # FDS-primary build by the shared build_vegas_legs() entry point.
    local_by_pos = defaultdict(dict)
    local_extra = {}
    for player, props in player_props.items():
        k = norm(player)
        m = meta.get(k)
        if not m:
            continue
        pos = m["pos"]
        try:
            full = {sc: vegas_implied_points(props, position=pos, scoring=sc)
                    for sc in ("standard", "half_ppr", "ppr")}
            raw = {sc: full[sc]["points"] for sc in full}
            _ppr = full["ppr"]
        except Exception:
            continue
        local_by_pos[pos][k] = {"std": raw["standard"],
                                "half": raw["half_ppr"],
                                "ppr": raw["ppr"]}
        prov = vegas_provenance(_ppr["markets_used"], _ppr["td_source"], pos)
        local_extra[k] = {"name": player,
                          "td_p": td_cover.get(player),
                          "markets": sorted(_ppr["markets_used"]),
                          "provenance": prov,
                          "vegas_leg": "local",
                          "prov_gaps": completeness_gaps(
                              _ppr["markets_used"], _ppr["td_source"], pos)}

    # FDS-primary + local audit leg (2026-09-17): same shared entry point
    # as compute_v4 — FDS is the primary Vegas-leg backbone (points
    # recomputed LOCALLY from vegas-attributed translated stats only),
    # local raw-book numbers audit it. Never diverges from compute_v4.
    fds_index, fds_keys, local_keys = {}, set(), set()
    audit = {"disagreements": [], "counts": {}, "fds_counts": {}}
    try:
        _fds_payload = fds_load_payload(week)
    except ValueError as e:
        raise SystemExit(f"FDS fallback BLOCKED: {e}")
    if _fds_payload is not None:
        fds_index = fds_index_payload(_fds_payload)
        vegas_by_pos, extra, fds_keys, local_keys, audit = build_vegas_legs(
            local_by_pos, local_extra, fds_index,
            pos_of=lambda k: (meta.get(k) or {}).get("pos"),
            priority=VEGAS_SOURCE_PRIORITY)
        _fc, _ac = audit["fds_counts"], audit["counts"]
        print(f"FDS primary: added={_fc['added']} "
              f"(derived={_fc['added_derived']}, "
              f"partial={_fc['added_partial']}) {_fc['by_pos']} | "
              f"pos_mismatch={_fc['pos_mismatch']} | "
              f"skipped_not_sunday={_fc['skipped_not_sunday']} | "
              f"local audit: only={_ac['local_only']} "
              f"agree={_ac['agreements']} override={_ac['overrides']} "
              f"partial_xcheck={_ac['partial_crosschecks']}", flush=True)
        for _d in audit["disagreements"]:
            print(f"  AUDIT DISAGREEMENT: {_d['name']} ({_d['pos']}): "
                  f"deltas={_d['deltas']} -> local wins", flush=True)
    else:
        # No FDS payload: the audit leg is the only leg — local-only build.
        vegas_by_pos, extra = local_by_pos, local_extra
        local_keys = {k for d in local_by_pos.values() for k in d}

    expert_pts = {k: {"std": v["std"], "half": v["half"], "ppr": v["ppr"]}
                  for k, v in expert_pts.items()}
    signals = rank_deltas_by_position(vegas_by_pos, ecr_by_pos,
                                      expert_pts=expert_pts,
                                      official_pos_rank=official, meta=meta)
    for s in signals:
        k = s["player_key"]
        s["td_p_yes"] = extra.get(k, {}).get("td_p")
        # Completeness gate (user-approved 2026-09-12): ONLY 'complete' and
        # 'td-filled' Vegas rows are publishable. 'partial' rows are
        # informational only — never post-worthy. 'fds-derived' rows (FDS
        # fallback, 2026-09-17) ARE publishable but always labeled;
        # 'fds-partial' rows are informational only, like 'partial'.
        prov = extra.get(k, {}).get("provenance", "partial")
        s["vegas_provenance"] = prov
        s["vegas_leg"] = extra.get(k, {}).get("vegas_leg")
        # Per-stat provenance rides the row (vegas-attributed inputs vs
        # FDS projection output, shown separately). Local rows carry None.
        s["vegas_stats_used"] = extra.get(k, {}).get("vegas_stats_used")
        s["fds_projection_stats"] = extra.get(k, {}).get(
            "fds_projection_stats")
        s["fds_stat_sources"] = extra.get(k, {}).get("fds_stat_sources")
        if not is_publishable(prov) and s["post_worthy"]:
            gaps = extra.get(k, {}).get("prov_gaps", [])
            s["post_worthy"] = False
            s["worthy_reason"] = (
                "Only partial market data — shown for context, never flagged"
                + (f" (missing {', '.join(gaps)})" if gaps else ""))
    # Fail-closed provenance audit (same as compute_v4).
    validate_signal_rows(signals, fds_index, local_keys, fds_keys,
                         audit=audit, priority=VEGAS_SOURCE_PRIORITY)

    # injury gate (same as compute_v4): Out/IR/Doubtful/PUP are news-driven,
    # not signal; Questionable stays with a flag
    try:
        inj_rows = sbclient.get_all(
            "injuries", "?select=player_name,status,body_part")
        inj = {norm(r["player_name"]): r for r in inj_rows}
        for s in signals:
            r = inj.get(s["player_key"])
            if r and (r["status"] or "") in ("Out", "IR", "Doubtful", "PUP"):
                if s["post_worthy"]:
                    s["post_worthy"] = False
                    bp = r.get("body_part")
                    s["worthy_reason"] = (
                        f"{r['status']}{f' ({bp})' if bp else ''} — "
                        f"injury news, not a market signal")
            elif r and (r["status"] or "") == "Questionable":
                s["injury_flag"] = (
                    "Questionable"
                    + (f" ({r['body_part']})" if r.get("body_part") else ""))
    except Exception as e:
        print(f"WARNING: injury gate skipped: {e}", flush=True)
    return signals


# ------------------------------------------------- movement vs prior snapshot
def resolve_baseline_batch(week, season, cutoff_utc):
    """Most recent projection_snapshots batch for (season, week) written
    before cutoff_utc. cutoff_utc is the run's start time, so a fresh batch
    written by this run is never selected as its own baseline.
    Returns (batch_id, snapshot_at) or (None, None)."""
    rows = sbclient.get_all(
        "projection_snapshots",
        f"?season=eq.{season}&week=eq.{week}"
        "&select=batch_id,snapshot_at&limit=100000",
    )
    best = None
    for r in rows:
        sa = r.get("snapshot_at")
        if not sa:
            continue
        try:
            dt = datetime.fromisoformat(sa.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff_utc:
            continue
        if best is None or dt > best[1]:
            best = (r["batch_id"], dt)
    return best if best else (None, None)


def load_baseline_points(batch_id):
    """{player_id: {'vegas': pts, 'espn': pts}} — full_ppr rows only,
    since game-day cards render PPR points. Reuses the existing snapshot
    rows; no new tables.

    JEG-418: the expert-side source key moved from 'fantasypros' to 'espn'.
    Older snapshot batches written before the ESPN swap may still carry
    'fantasypros' rows; both keys are accepted as the expert leg so a
    freshly-written batch is compared against its own prior batch in the
    same series without a hard break."""
    rows = sbclient.get_all(
        "projection_snapshots",
        f"?batch_id=eq.{batch_id}&scoring_format=eq.full_ppr"
        "&select=player_id,source,projected_points&limit=100000",
    )
    out = {}
    for r in rows:
        d = out.setdefault(r["player_id"], {})
        if r["source"] == "vegas_implied":
            d["vegas"] = float(r["projected_points"])
        elif r["source"] in ("espn", "fantasypros"):
            d["espn"] = float(r["projected_points"])
    return out


def baseline_label(snapshot_at):
    """Header tag for the baseline: 'this AM' when the baseline snapshot is
    from today (CT), otherwise the weekday abbrev ('Wed')."""
    if snapshot_at.astimezone(CT).date() == datetime.now(CT).date():
        return "this AM"
    return snapshot_at.astimezone(CT).strftime("%a")


def attach_movement(signals, baseline_pts):
    """Per-side movement vs the baseline batch, attached as
    s['move_vegas'] / s['move_expert'] (None when the side is missing from
    the baseline — e.g. a player with no prior snapshot row)."""
    by_name, by_loose, _ = load_players()
    for s in signals:
        pl = (by_name.get(s["player_key"])
              or by_loose.get(norm_loose(s["player_key"])))
        s["move_vegas"] = s["move_expert"] = None
        base = baseline_pts.get(pl["id"]) if pl else None
        if not base:
            continue
        if base.get("vegas") is not None and s.get("vegas_ppr") is not None:
            s["move_vegas"] = s["vegas_ppr"] - base["vegas"]
        if base.get("espn") is not None and s.get("expert_ppr") is not None:
            s["move_expert"] = s["expert_ppr"] - base["espn"]


# ------------------------------------------------------------------- tweet
def _move_tag(x):
    """' ↓1.5' / ' ↑1.2' (one decimal), or '' when the side moved less than
    MOVE_THRESHOLD or has no baseline."""
    if x is None or abs(x) < MOVE_THRESHOLD:
        return ""
    return f" {'\u2191' if x > 0 else '\u2193'}{abs(x):.1f}"


def build_gameday_tweet(week, kickoff_ct, signals, move_baseline=None):
    """One abbreviated card per game. X-counted length asserted <= 280.

    move_baseline: snapshot_at of the baseline batch (drives the
    '(moves since …)' header tag), or None when no prior snapshot exists.
    When the full card exceeds 280 chars it is truncated to the top 6
    signals by |Δ|, then the smallest |Δ| lines are dropped until it fits.
    """
    label = DAY_LABEL.get(kickoff_ct.strftime("%A"),
                          kickoff_ct.strftime("%a").upper())
    header = f"MARKET vs EXPERTS \u2014 Wk {week} \u00b7 {label}"
    if move_baseline is not None:
        header += f" (moves since {baseline_label(move_baseline)})"
    ordered = sorted(signals,
                     key=lambda x: abs(x.get("pts_delta_ppr") or 0),
                     reverse=True)
    # movement tags are only meaningful with a baseline label in the header
    show_move = move_baseline is not None

    def render(sub):
        lines = []
        for s in sub:
            pd = s["pts_delta_ppr"] or 0.0
            arrow = "\u25b2" if pd > 0 else "\u25bc"
            sign = "+" if pd > 0 else ""
            mv = _move_tag(s.get("move_vegas")) if show_move else ""
            me = _move_tag(s.get("move_expert")) if show_move else ""
            lines.append(
                f"{arrow} {_short_name(s['name'])}, {s['pos']}, {s['team']}: "
                f"vegas {s['vegas_ppr']:.1f}{mv} "
                f"vs ECR {s['expert_ppr']:.1f}{me} "
                f"(\u0394 {sign}{pd:.1f})"
            )
        return header + "\n" + "\n".join(lines)

    tweet = render(ordered)
    if _x_len(tweet) > 280:
        kept = list(ordered[:MAX_GAMEDAY_SIGNALS])
        tweet = render(kept)
        while _x_len(tweet) > 280 and len(kept) > 1:
            kept.pop()
            tweet = render(kept)
    assert _x_len(tweet) <= 280, \
        f"gameday tweet too long ({_x_len(tweet)}): {tweet}"
    return tweet


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print tweets; no post_queue writes, no snapshot "
                         "batches, no injury-loader writes (the odds pull "
                         "still runs, dedupe-guarded, for the readiness gate)")
    ap.add_argument("--game-id", default=None,
                    help="testing override: run for this games.id instead of "
                         "today's games (skips pull/readiness when the game "
                         "has no upcoming odds event)")
    ap.add_argument("--window-hours", type=float, default=6,
                    help="DEPRECATED (2026-09-11): no longer used; kept so "
                         "older invocations don't break")
    ap.add_argument("--espn-csv", default=None,
                    help="testing override: path to ESPN ROS CSV for the "
                         "recency gate")
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()

    week = current_week(a.season)
    print(f"=== game-day cards: season {a.season} week {week} ===", flush=True)
    run_start_utc = datetime.now(timezone.utc)  # baseline cutoff: a batch
    # written by this run must never be its own movement baseline

    ok, msg = check_espn_gate(a.espn_csv, season=a.season, week=week)
    print(msg, flush=True)
    if not ok:
        sys.exit(2)

    if a.game_id:
        rows = sbclient.get(
            "games",
            f"?id=eq.{a.game_id}"
            "&select=id,week,home_team_id,away_team_id,starts_at,status")
        if not rows:
            print(f"no game with id {a.game_id}")
            sys.exit(1)
        games = rows
        print(f"--game-id override: testing with game {a.game_id} "
              f"(status {rows[0].get('status')})", flush=True)
    else:
        games = find_todays_games(a.season)
    if not games:
        print("no non-Sunday games today — nothing to do", flush=True)
        return 0

    team_abbr = {t["id"]: t.get("abbreviation") or "?"
                 for t in sbclient.get_all("teams", "?select=id,abbreviation")}

    ready = []
    for g in games:
        away = team_abbr.get(g["away_team_id"], "?")
        home = team_abbr.get(g["home_team_id"], "?")
        key = f"{away}@{home}"
        if already_handled(away, home, week):
            print(f"already handled: gameday wk{week} {key} — skipping",
                  flush=True)
            continue
        event_id = resolve_event_id(g["id"])
        if event_id:
            n, remaining = fresh_pull(event_id)
            print(f"fresh pull {key}: {n} rows written, "
                  f"quota remaining: {remaining}", flush=True)
            if not props_open(event_id):
                print(f"betting not open yet for {key} — skipping", flush=True)
                continue
        elif a.game_id:
            print(f"no upcoming odds event for {key} (--game-id test mode: "
                  f"using existing DB props)", flush=True)
        else:
            print(f"no upcoming odds event resolved for {key} — skipping",
                  flush=True)
            continue
        sa = g.get("starts_at")
        kickoff = (datetime.fromisoformat(sa.replace("Z", "+00:00"))
                   .astimezone(CT) if sa else datetime.now(CT))
        ready.append((g, away, home, kickoff))

    if not ready:
        print("no games with open betting — nothing to do", flush=True)
        return 0

    if not a.dry_run:
        snapshot_main(week=week, season=a.season)
        refresh_injuries()
    else:
        print("dry-run: skipping snapshot batch + injury-loader writes",
              flush=True)

    signals = build_signals(week, a.season)
    n_worthy = sum(1 for s in signals if s["post_worthy"])
    print(f"signals computed: {len(signals)} | post-worthy: {n_worthy}",
          flush=True)

    # movement baseline: most recent snapshot batch before this run started
    # (read-only; safe in --dry-run)
    base_id, base_at = resolve_baseline_batch(week, a.season, run_start_utc)
    if base_id:
        print(f"movement baseline: batch {base_id[:8]} "
              f"snapshot_at {base_at:%Y-%m-%d %H:%M %Z}", flush=True)
        attach_movement(signals, load_baseline_points(base_id))
        n_vm = sum(1 for s in signals if s.get("move_vegas") is not None)
        n_em = sum(1 for s in signals if s.get("move_expert") is not None)
        print(f"movement attached: {n_vm} vegas / {n_em} expert sides "
              f"have baseline rows", flush=True)
    else:
        base_at = None
        print("movement baseline: none (no prior snapshot batch) — "
              "no arrows, no header tag", flush=True)

    wrote = 0
    for g, away, home, kickoff in ready:
        want = {away, home}
        gs = [s for s in signals
              if s["post_worthy"] and s.get("team") in want
              and s.get("pts_delta_ppr") is not None]
        if not gs:
            print(f"no signals: {away}@{home} — no tweet", flush=True)
            continue
        tweet = build_gameday_tweet(week, kickoff, gs, move_baseline=base_at)
        print(f"--- gameday wk{week} {away}@{home} ({len(gs)} signals) ---")
        print(tweet, flush=True)
        if a.dry_run:
            continue
        sbclient.post("post_queue", {
            "post_type": "gameday",
            "post_text": tweet,
            "status": "draft",
            "note": f"gameday wk{week} {away}@{home} {len(gs)} signals",
        })
        wrote += 1
    print(f"=== game-day cards complete: {wrote} draft(s) written ===",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
