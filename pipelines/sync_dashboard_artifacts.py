#!/usr/bin/env python3
"""Sync finished fixture artifacts into the static dashboard and dist output."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from check_reference_freshness import build_report


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
FIXTURES = ROOT / "data" / "fixtures" / "current"
MODULES = ROOT / "modules"
WEEKLY_SIGNALS = ROOT / "weekly_signals" / "dashboard"
DIST = ROOT / "dist"
REFERENCE_FRESHNESS = ROOT / "output" / "reference-freshness.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def replace_inline_players(index_html: str, players: dict) -> str:
    start_marker = '<script id="players-data" type="application/json">'
    end_marker = "</script>"
    start = index_html.index(start_marker) + len(start_marker)
    end = index_html.index(end_marker, start)
    payload = json.dumps(players, separators=(",", ":"), ensure_ascii=False)
    return index_html[:start] + payload + index_html[end:]


def copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def build_tag() -> str | None:
    """Identity of the commit this build came from: tv-YYYYMMDD-HHMM-<sha>.

    Derived from HEAD's own commit time, not from now(), so re-running sync on
    the same commit produces the same tag. deploy.sh used to stamp this from
    the wall clock at deploy time; folding it in here keeps `make sync` the
    single publish path without making every sync dirty index.html.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "show", "-s", "--format=%cd-%h", "--date=format:%Y%m%d-%H%M", "HEAD"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    tag = out.stdout.strip()
    return f"tv-{tag}" if out.returncode == 0 and tag else None


def stamp_build_tag(index_html: str, tag: str) -> str:
    stamped = re.sub(
        r'(<meta name="trade-chart-build" content=")[^"]*(">)',
        lambda m: m.group(1) + tag + m.group(2),
        index_html,
    )
    return re.sub(
        r'(<span id="buildStamp">)Build [^<]*(</span>)',
        lambda m: m.group(1) + "Build " + tag + m.group(2),
        stamped,
    )


def main() -> int:
    players = read_json(FIXTURES / "players.json")
    freshness = build_report(FIXTURES, REFERENCE_FRESHNESS, date.today())
    REFERENCE_FRESHNESS.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_FRESHNESS.write_text(json.dumps(freshness, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    (APP / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES / "comparison-sources-data.json", APP / "assets" / "comparison-sources-data.json")
    shutil.copy2(FIXTURES / "player-news.json", APP / "assets" / "player-news.json")
    shutil.copy2(REFERENCE_FRESHNESS, APP / "assets" / "reference-freshness.json")

    index_path = APP / "index.html"
    index_html = replace_inline_players(index_path.read_text(encoding="utf-8"), players)
    tag = build_tag()
    if tag:
        index_html = stamp_build_tag(index_html, tag)
    index_path.write_text(index_html, encoding="utf-8")

    # dist/ is exactly what GitHub Pages publishes -- nothing else.
    #
    # This used to also write dist/static/ (a byte-identical second copy of
    # the whole site, which doubled the deployed payload for nothing) and
    # dist/server/index.js (a Cloudflare-style worker stub that Pages never
    # executes). Both were Muse hosting leftovers, as was space.json.
    DIST.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "icon.jpg"):
        shutil.copy2(APP / name, DIST / name)
    copy_tree(APP / "assets", DIST / "assets")

    # The module monitor and the health artifact it reads. Previously both
    # were hand-copied into dist/, so dist/modules/ silently drifted from
    # modules/; generating them here is what keeps the monitor honest.
    dist_modules = DIST / "modules"
    dist_modules.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MODULES / "dashboard.html", dist_modules / "dashboard.html")
    shutil.copy2(FIXTURES / "source-import-health.json", dist_modules / "source-import-health.json")

    weekly_page = WEEKLY_SIGNALS / "index.html"
    for slug in ("weekly-signals", "waiver-dashboard"):
        target = DIST / slug
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(weekly_page, target / "index.html")

    print(f"Dashboard artifacts synced to app/trade-value-chart and dist{f' (build {tag})' if tag else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
