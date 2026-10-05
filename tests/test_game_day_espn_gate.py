"""JEG-418 regression: game-day pipeline's expert-leg freshness gate now
reads ESPN ROS content vintage, not the retired ECR feed.

Mirrors the (no-longer-extant) ECR gate tests' philosophy: assert the gate
FAILS on the wrong state and PASSES on the right one, so a regression
where someone wires the gate back to fantasypros / ECR / projection_snapshots
or short-circuits the freshness check fails closed.

Gate contract (game_day.check_espn_gate):
  Layer 1 (pull recency): ESPN CSV mtime must be >= the most recent daily
    refresh anchor (06:10 CT, plus 3h slop, i.e. 09:00 CT).
  Layer 2 (content vintage): espn_snapshot_date column inside the CSV must
    be within ESPN_MAX_AGE_DAYS of today. A byte-identical re-pull that
    does NOT advance the snapshot_date fails closed.

State isolation: each test writes its own fixture CSV in a temp dir and
passes it via the gate's csv_path parameter. No live sbclient reads.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Make the pipeline bin/ importable so we exercise the real gate functions.
BASE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.normpath(os.path.join(
    BASE, "..", "weekly_vegas", "pipeline"))
sys.path.insert(0, os.path.join(PIPELINE, "bin"))
sys.path.insert(0, PIPELINE)
sys.path.insert(0, os.path.expanduser("~/workspace/skills/the-odds-api/bin"))
sys.path.insert(0, os.path.expanduser(
    "~/workspace/skills/supabase-football-signal/bin"))

# Import the real engine package; stub only engine.week.current_week so
# the gate's week= default does not hit sbclient.
import engine.week  # noqa: E402
engine.week.current_week = lambda season: 4

import game_day  # noqa: E402


CT = ZoneInfo("America/Chicago")
HEADER = ("player,player_norm,pos,team,has_espn_projection,eligible,"
          "r_pass_yds,r_pass_tds,r_rush_yds,r_rush_tds,r_receptions,"
          "r_rec_yds,r_rec_tds,ros_half_ppr,weeks_covered,"
          "season_block_half_ppr,espn_snapshot_date\n")


def _make_csv(tmp, snapshot_date, mtime_dt):
    """Write a minimal ESPN ROS CSV with the given snapshot date, then
    backdate its mtime to mtime_dt. Returns the CSV path."""
    path = os.path.join(tmp, "espn_projections.csv")
    with open(path, "w", newline="") as f:
        f.write(HEADER)
        f.write(f"Josh Allen,josh allen,QB,BUF,True,True,3163.3,20.7,"
                f"438.3,10.2,0.0,0.0,0.0,314.36,5-18,338.58,"
                f"{snapshot_date}\n")
        f.write(f"Jahmyr Gibbs,jahmyr gibs,RB,DET,True,True,0.0,0.0,"
                f"1289.8,13.7,61.4,497.8,3.1,310.26,5-18,333.82,"
                f"{snapshot_date}\n")
    ts = mtime_dt.astimezone(timezone.utc).timestamp()
    os.utime(path, (ts, ts))
    return path


def _now_ct(hour=12, minute=0):
    """Fixed 'now' anchor so the gate's hour-based layer 1 is deterministic."""
    return datetime(2026, 10, 5, hour, minute, 0, tzinfo=CT)


# --------------------------------------------------------------------- pass

def test_gate_passes_on_fresh_csv():
    """Happy path: file pulled this AM, ESPN snapshot from today. PASS."""
    now = _now_ct(hour=12)
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_csv(tmp, "2026-10-05",
                         now - timedelta(hours=2))
        ok, msg = game_day.check_espn_gate(
            csv_path=path, now=now, season=2026, week=4)
    assert ok is True, msg
    assert "ESPN fresh" in msg
    assert "week-4" in msg


def test_gate_passes_on_recent_yesterday_snapshot():
    """Yesterday's snapshot (1 day old, within ESPN_MAX_AGE_DAYS=3) PASSes.
    This is the common case during bye weeks / injury-light slates when ESPN's
    numbers don't move day-to-day but the puller still ran."""
    now = _now_ct(hour=12)
    snap = (now - timedelta(days=1)).date().isoformat()
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_csv(tmp, snap, now - timedelta(hours=2))
        ok, msg = game_day.check_espn_gate(
            csv_path=path, now=now, season=2026, week=4)
    assert ok is True, msg
    assert "1d old" in msg


def test_gate_fails_when_csv_missing():
    """Layer 1 file-recency guard: missing CSV -> BLOCKED, fail-closed."""
    now = _now_ct(hour=12)
    ok, msg = game_day.check_espn_gate(
        csv_path="/nonexistent/espn_projections.csv",
        now=now, season=2026, week=4)
    assert ok is False, msg
    assert "BLOCKED" in msg
    assert "missing" in msg


def test_gate_fails_when_csv_stale_pull():
    """Layer 1 pull-recency guard: file mtime older than the daily-refresh
    anchor (09:00 CT). Even with a fresh snapshot date, a stale pull fails
    closed so we never post from an obviously-unrefreshed fixture."""
    now = _now_ct(hour=12)
    snap = now.date().isoformat()
    with tempfile.TemporaryDirectory() as tmp:
        # File pulled 3 days ago, BEFORE today's 09:00 anchor.
        path = _make_csv(tmp, snap, now - timedelta(days=3, hours=4))
        ok, msg = game_day.check_espn_gate(
            csv_path=path, now=now, season=2026, week=4)
    assert ok is False, msg
    assert "BLOCKED" in msg
    assert "stale pull" in msg


def test_gate_fails_when_snapshot_date_stale():
    """Layer 2 content-vintage guard: espn_snapshot_date older than
    ESPN_MAX_AGE_DAYS. The puller writes the CSV only when ESPN's hash
    changes, so a stale snapshot_date means ESPN's numbers haven't moved in
    too long for a game-day 'Vegas vs experts' card."""
    now = _now_ct(hour=12)
    snap = (now - timedelta(days=game_day.ESPN_MAX_AGE_DAYS + 1)
            ).date().isoformat()
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_csv(tmp, snap, now - timedelta(hours=2))
        ok, msg = game_day.check_espn_gate(
            csv_path=path, now=now, season=2026, week=4)
    assert ok is False, msg
    assert "BLOCKED" in msg
    assert "ESPN content stale" in msg
    assert f"{game_day.ESPN_MAX_AGE_DAYS + 1}d >" in msg


def test_gate_fails_when_snapshot_date_missing():
    """Layer 2 content-vintage guard: missing espn_snapshot_date column or
    no parseable value. Treats it as unverifiable -> fail-closed."""
    now = _now_ct(hour=12)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "espn_projections.csv")
        with open(path, "w", newline="") as f:
            f.write(HEADER)
            f.write("Josh Allen,josh allen,QB,BUF,True,True,3163.3,"
                    "20.7,438.3,10.2,0.0,0.0,0.0,314.36,5-18,"
                    "338.58,\n")  # empty snapshot date
        ts = (now - timedelta(hours=2)).astimezone(timezone.utc).timestamp()
        os.utime(path, (ts, ts))
        ok, msg = game_day.check_espn_gate(
            csv_path=path, now=now, season=2026, week=4)
    assert ok is False, msg
    assert "BLOCKED" in msg
    assert "could not determine ESPN content vintage" in msg


def test_gate_rejects_legacy_ecr_inputs():
    """JEG-418 acceptance criterion: the gate no longer reads any ECR
    inputs. A regression that wires `data/ecr_pos.json` back in must fail
    this test (the function signature no longer accepts an ecr_path)."""
    import inspect
    sig = inspect.signature(game_day.check_espn_gate)
    assert "ecr_path" not in sig.parameters, (
        "check_espn_gate still accepts an ecr_path argument — the "
        "ECR gate has been re-wired. This is exactly the JEG-418 "
        "regression we are guarding against."
    )
    assert "csv_path" in sig.parameters


def test_game_day_module_does_not_import_ecr_sources():
    """JEG-418 acceptance criterion: grep-clean source. A regression that
    re-introduces a fantasypros import, ECR_PATH, or ecr_pos reference must
    fail this test."""
    import re
    src_path = os.path.join(PIPELINE, "bin", "game_day.py")
    with open(src_path) as f:
        src = f.read()
    # Strip docstrings/comments would be nice but is fragile; do a strict
    # regex on the actual identifiers and import targets the gate cares
    # about. If any of these match, the ECR feed has crept back in.
    # Docstring prose may cite the retired feed by path-style reference
    # (e.g. "v4/compute_v4.load_ecr"); only real code usage counts, so the
    # usage patterns below exclude matches preceded by / or .
    bad_patterns = [
        (r"\bECR_PATH\b", "ECR_PATH constant"),
        (r"data/ecr_pos\.json", "ecr_pos.json file path"),
        (r"from\s+loaders\.fantasypros\s+import", "loaders.fantasypros import"),
        (r"(?<![/.])\bread_projections_dict\b", "read_projections_dict usage"),
        (r"(?<!/)\bcompute_v4\.load_ecr\b", "v4.compute_v4.load_ecr usage"),
    ]
    hits = []
    for pat, label in bad_patterns:
        for m in re.finditer(pat, src):
            line_no = src[:m.start()].count("\n") + 1
            hits.append(f"{label} on line {line_no}")
    assert not hits, (
        "game_day.py still references retired ECR/FantasyPros inputs: "
        + "; ".join(hits)
    )


def test_load_espn_ros_builds_expert_pts_and_positional_ranks():
    """The downstream expert-leg loader (replacing v4.compute_v4.load_ecr
    + loaders.fantasypros.read_projections_dict) must return the same
    shape build_signals feeds into rank_deltas_by_position: per-player
    half/std/ppr, an opinionated pos_rank per position, and a meta dict.
    Regression here would break game-day cards silently."""
    snap = "2026-10-05"
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_csv(tmp, snap, datetime.now(CT))
        pts, by_pos, meta, official = game_day.load_espn_ros(
            csv_path=path, week=5)
    # Per-player expert points — same shape as the old ECR feed.
    assert "josh allen" in pts
    assert "jahmyr gibs" in pts
    for k, v in pts.items():
        assert set(v.keys()) >= {"name", "std", "half", "ppr"}, k
        assert v["half"] > 0, k  # the fixture's half-ppr is non-zero
    # Positional ranks — one entry per position, deterministic ordering.
    assert "QB" in by_pos and "RB" in by_pos
    for pos, ranks in by_pos.items():
        # Ranks are contiguous integers starting at 1.
        rs = sorted(ranks.values())
        assert rs == list(range(1, len(rs) + 1)), (pos, rs)
        # 'official' keys line up with rank 1..N per position.
        for k, r in ranks.items():
            assert official[k].startswith(pos), (k, official[k])
            assert official[k] == f"{pos}{r}", (k, official[k])
    # Meta: every player with expert points has a meta row too.
    for k in pts:
        assert k in meta
        assert meta[k]["pos"] in ("QB", "RB", "WR", "TE")