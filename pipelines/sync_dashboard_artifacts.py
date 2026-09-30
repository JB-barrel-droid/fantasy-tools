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
WEEKLY_VEGAS = ROOT / "weekly_vegas" / "dashboard"
WAIVER_WIRE = ROOT / "waiver_wire" / "dashboard"
DIST = ROOT / "dist"
REFERENCE_FRESHNESS = ROOT / "output" / "reference-freshness.json"
RUNTIME_IMPORT_HEALTH = ROOT / "output" / "source-import-health.json"
FIXTURE_IMPORT_HEALTH = FIXTURES / "source-import-health.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def replace_inline_players(index_html: str, players: dict) -> str:
    start_marker = '<script id="players-data" type="application/json">'
    end_marker = "</script>"
    start = index_html.index(start_marker) + len(start_marker)
    end = index_html.index(end_marker, start)
    payload = json.dumps(players, separators=(",", ":"), ensure_ascii=False)
    return index_html[:start] + payload + index_html[end:]


METHODOLOGY_POSITION_SOURCES = [
    ("usatoday", "USA Today", "full_12"),
    ("fantasycalc", "FantasyCalc", "full_12_qb1"),
    ("fantasypros", "FantasyPros", "full_12"),
    ("cbs", "CBS", "full_12"),
    ("espn", "ESPN", "full_12"),
]
METHODOLOGY_ADJUSTED_PAIRS = [
    ("usatoday", "usatoday_adjusted", "USA Today", "full_12"),
    ("fantasycalc", "fantasycalc_adjusted", "FantasyCalc", "full_12_qb1"),
    ("fantasypros", "fantasypros_adjusted", "FantasyPros", "full_12"),
    ("cbs", "cbs_adjusted", "CBS", "full_12"),
]


def build_methodology_payload(fixtures: Path, players_data: dict) -> dict:
    """Bake the numbers behind the 'How we make the charts comparable' section.

    position_shares: per-position share of each source's fixed pie (Full PPR,
    12 teams) -- the 'same pie, different slicing' visual.
    adjustments: biggest as-published -> adjusted movers per adjusted series --
    the 'correcting house habits' visual. Derived from the same fixture the
    curves render, so the section can never drift from the chart.
    """
    comp = read_json(fixtures / "comparison-sources-data.json")
    name2key = comp.get("player_keys", {})
    by_key = {p["player_key"]: p for p in players_data.get("players", [])}

    def pos_of(name: str) -> str:
        return (by_key.get(name2key.get(name)) or {}).get("pos", "?")

    def display_name(name: str) -> str:
        return (by_key.get(name2key.get(name)) or {}).get("name") or name.title()

    position_shares = {}
    for src, label, combo in METHODOLOGY_POSITION_SOURCES:
        series = comp["sources"].get(src, {}).get("combos", {}).get(combo, {})
        # ESPN's DDF-methodology leg is stored under "values" (never reindexed);
        # as-published series use "reindexed".
        vals = series.get("reindexed") or series.get("values") or {}
        total = sum(vals.values())
        shares = {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0}
        for name, value in vals.items():
            pos = pos_of(name)
            if pos in shares:
                shares[pos] += value
        position_shares[src] = {
            "label": label,
            "shares": (
                {p: round(s / total * 100) for p, s in shares.items()} if total else shares
            ),
            "n": len(vals),
        }

    adjustments = {}
    for pub, adj, label, combo in METHODOLOGY_ADJUSTED_PAIRS:
        pub_vals = comp["sources"].get(pub, {}).get("combos", {}).get(combo, {}).get("reindexed") or {}
        adj_vals = comp["sources"].get(adj, {}).get("combos", {}).get(combo, {}).get("reindexed") or {}
        movers = []
        for name, before in pub_vals.items():
            if name in adj_vals and before > 8:
                after = adj_vals[name]
                movers.append((after - before, name, before, after))
        movers.sort(key=lambda m: -abs(m[0]))
        adjustments[pub] = {
            "label": label,
            "movers": [
                {
                    "name": display_name(name),
                    "pos": pos_of(name),
                    "before": round(before, 1),
                    "after": round(after, 1),
                    "delta": round(delta, 1),
                }
                for delta, name, before, after in movers[:6]
            ],
        }

    return {
        "scoring": "full",
        "teams": 12,
        "position_shares": position_shares,
        "adjustments": adjustments,
    }


def replace_inline_methodology(index_html: str, payload: dict) -> str:
    start_marker = '<script id="methodology-data" type="application/json">'
    end_marker = "</script>"
    start = index_html.index(start_marker) + len(start_marker)
    end = index_html.index(end_marker, start)
    baked = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return index_html[:start] + baked + index_html[end:]


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
    stamped = re.sub(
        r'(<span id="buildStamp">)Build [^<]*(</span>)',
        lambda m: m.group(1) + "Build " + tag + m.group(2),
        stamped,
    )
    # Cache-bust every local asset with the SAME build tag.
    #
    # These ?v= tokens used to be hand-written strings ("20260920-curve-all-
    # scale"). They were never bumped, so the asset URL stayed byte-identical
    # across deploys and returning browsers kept serving the cached file. A
    # deploy that fixed a blank chart therefore left the chart blank for
    # anyone who had loaded the page before -- the server had the fix and the
    # browser would not ask for it. Tying the token to the build tag means a
    # new commit always produces a new URL.
    return re.sub(
        r'(<script src="assets/[A-Za-z0-9._-]+\.js)(\?v=[^"]*)?(")',
        lambda m: m.group(1) + "?v=" + tag + m.group(3),
        stamped,
    )


def import_health_source() -> Path:
    """Prefer the latest runtime gate output; fall back to the committed fixture."""
    if RUNTIME_IMPORT_HEALTH.is_file():
        try:
            payload = read_json(RUNTIME_IMPORT_HEALTH)
            if payload.get("schema") == "trade-value-import-health-v1":
                return RUNTIME_IMPORT_HEALTH
        except (OSError, json.JSONDecodeError):
            pass
    return FIXTURE_IMPORT_HEALTH


def main() -> int:
    players = read_json(FIXTURES / "players.json")
    import_health = import_health_source()
    freshness = build_report(FIXTURES, REFERENCE_FRESHNESS, date.today(), import_health_path=import_health)
    REFERENCE_FRESHNESS.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_FRESHNESS.write_text(json.dumps(freshness, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    (APP / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES / "comparison-sources-data.json", APP / "assets" / "comparison-sources-data.json")
    shutil.copy2(FIXTURES / "player-news.json", APP / "assets" / "player-news.json")
    shutil.copy2(REFERENCE_FRESHNESS, APP / "assets" / "reference-freshness.json")

    index_path = APP / "index.html"
    index_html = replace_inline_players(index_path.read_text(encoding="utf-8"), players)
    methodology = build_methodology_payload(FIXTURES, players)
    index_html = replace_inline_methodology(index_html, methodology)
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
    shutil.copy2(import_health, dist_modules / "source-import-health.json")

    # Each dashboard publishes from its own segmented source tree:
    # weekly_vegas/ (Vegas-vs-ECR signals) and waiver_wire/ (waiver board).
    # The published dist/ slugs are unchanged.
    for slug, source_dir in (("weekly-signals", WEEKLY_VEGAS), ("waiver-dashboard", WAIVER_WIRE)):
        source = source_dir / "index.html"
        target = DIST / slug
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target / "index.html")

    print(f"Dashboard artifacts synced to app/trade-value-chart and dist{f' (build {tag})' if tag else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
