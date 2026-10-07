#!/usr/bin/env python3
"""Load pinnacle_implied + dfs_implied projection snapshots.

Usage: python3 bin/load_sharp_dfs.py [--week N] [--season 2026]
Idempotent: deterministic batch ids, delete-then-insert per batch.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.expanduser("~/workspace/football-signal"))
from engine.snapshot_sharp import main  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    main(season=a.season, week=a.week)
