#!/usr/bin/env python3
"""Sync finished fixture artifacts into the static dashboard and dist output."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from check_reference_freshness import build_report


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
FIXTURES = ROOT / "data" / "fixtures" / "current"
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
    index_path.write_text(replace_inline_players(index_path.read_text(encoding="utf-8"), players), encoding="utf-8")

    DIST.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "icon.jpg", "space.json"):
      shutil.copy2(APP / name, DIST / name)
    copy_tree(APP / "assets", DIST / "assets")
    static = DIST / "static"
    static.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "icon.jpg", "space.json"):
      shutil.copy2(APP / name, static / name)
    copy_tree(APP / "assets", static / "assets")
    server = DIST / "server"
    server.mkdir(parents=True, exist_ok=True)
    (server / "index.js").write_text(
        'export default {\n'
        '  async fetch() {\n'
        '    return new Response("Trade Value Dashboard static assets are served by Sites.", {\n'
        '      status: 404,\n'
        '      headers: {"content-type": "text/plain; charset=utf-8"}\n'
        '    });\n'
        '  }\n'
        '};\n',
        encoding="utf-8",
    )
    print("Dashboard artifacts synced to app/trade-value-chart and dist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
