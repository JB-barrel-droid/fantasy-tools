"""Prefetch nflverse files with curl into the nflreadpy filesystem cache, then run
the nflverse loader. Workaround: python requests via the proxy gets
RemoteDisconnected on the release-assets signed URLs; curl is unaffected."""

import os
import subprocess
import sys
import tempfile

CACHE_DIR = "/home/hatch/workspace/football-signal/.cache/nflreadpy"
os.makedirs(CACHE_DIR, exist_ok=True)
os.environ["NFLREADPY_CACHE"] = "filesystem"
os.environ["NFLREADPY_CACHE_DIR"] = CACHE_DIR

sys.path.insert(0, "/home/hatch/workspace/football-signal/.venv/lib/python3.12/site-packages")
import polars as pl  # noqa: E402
from nflreadpy.downloader import get_downloader  # noqa: E402

BASE = "https://github.com/nflverse/nflverse-data/releases/download/"
specs = [
    (BASE + "teams/teams_colors_logos.parquet", {}),
    (BASE + "schedules/games.parquet", {}),
]
for season in (2024, 2025, 2026):
    specs.append((BASE + f"rosters/roster_{season}.parquet", {"season": season}))
    specs.append(
        (BASE + f"stats_player/stats_player_week_{season}.parquet",
         {"season": season, "summary_level": "week", "stat_type": "player"}))

dl = get_downloader()
for url, kw in specs:
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        tmp = f.name
    r = subprocess.run(
        ["curl", "-sSL", "--retry", "3", "--max-time", "180", "-o", tmp, url],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"curl failed for {url}: {r.stderr[-500:]}", flush=True)
        sys.exit(2)
    try:
        df = pl.read_parquet(tmp)
    except Exception as e:
        print(f"parse failed for {url}: {e}", flush=True)
        sys.exit(2)
    finally:
        os.unlink(tmp)
    dl.cache.set(url, df, **kw)
    print(f"cached {url} {df.shape}", flush=True)

print("== running loader ==", flush=True)
sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
sys.path.insert(0, "/home/hatch/workspace/football-signal")
import runpy  # noqa: E402

runpy.run_path("/home/hatch/workspace/football-signal/loaders/nflverse.py",
               run_name="__main__")
