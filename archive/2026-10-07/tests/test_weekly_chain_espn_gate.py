"""JEG-419: weekly_chain.py ESPN expert-leg gate.

The chain's expert-leg gate moved from the retired ECR feed to ESPN's
rest-of-season projections (output/espn_pull/files/espn_weekly_projections.csv).
These tests drive check_espn_gate with fixture CSVs: the gate must fail
closed on a missing file, an unverifiable vintage, and a stale snapshot,
and pass on a fresh one. A re-pull of unchanged content must NOT reset
the vintage clock (freshness = content vintage, never pull time).
"""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "weekly_vegas", "pipeline", "bin"))

from weekly_chain import check_espn_gate, ESPN_MAX_AGE_DAYS  # noqa: E402

HEADER = ["player", "pos", "half_ppr", "espn_snapshot_date"]


def _csv(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    return path


def _row(snap):
    return {"player": "Test Player", "pos": "QB",
            "half_ppr": "20.5", "espn_snapshot_date": snap}


def test_gate_passes_on_fresh_snapshot():
    p = _csv([_row("2026-10-05")])
    ok, msg = check_espn_gate(csv_path=p, today="2026-10-05")
    assert ok, msg
    os.unlink(p)


def test_gate_passes_within_max_age():
    p = _csv([_row("2026-10-03")])
    ok, msg = check_espn_gate(csv_path=p, today="2026-10-05")
    assert ok, msg
    os.unlink(p)


def test_gate_blocks_missing_file():
    ok, msg = check_espn_gate(csv_path="/nonexistent/espn.csv",
                              today="2026-10-05")
    assert not ok
    assert "pull_espn_projections" in msg


def test_gate_blocks_stale_snapshot():
    p = _csv([_row("2026-09-28")])  # 7d old, max is ESPN_MAX_AGE_DAYS
    ok, msg = check_espn_gate(csv_path=p, today="2026-10-05")
    assert not ok
    assert "7d old" in msg
    os.unlink(p)


def test_gate_blocks_unverifiable_vintage():
    p = _csv([{"player": "Test Player", "pos": "QB", "half_ppr": "20.5",
               "espn_snapshot_date": ""}])
    ok, msg = check_espn_gate(csv_path=p, today="2026-10-05")
    assert not ok
    assert "unverifiable" in msg
    os.unlink(p)


def test_repull_of_unchanged_content_does_not_reset_clock():
    # Same snapshot date, file rewritten today: vintage still governs.
    p = _csv([_row("2026-09-28")])
    os.utime(p, None)  # bump mtime to "now"
    ok, _ = check_espn_gate(csv_path=p, today="2026-10-05")
    assert not ok  # still blocked: content is 7d old
    os.unlink(p)


def test_gate_uses_latest_snapshot_date():
    p = _csv([_row("2026-09-28"), _row("2026-10-05")])
    ok, msg = check_espn_gate(csv_path=p, today="2026-10-05")
    assert ok, msg
    os.unlink(p)


def test_max_age_is_three_days():
    assert ESPN_MAX_AGE_DAYS == 3
