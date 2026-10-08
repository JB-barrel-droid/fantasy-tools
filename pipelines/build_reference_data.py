#!/usr/bin/env python3
"""Validate the finished reference artifacts that feed the dashboard.

This is intentionally a thin boundary today. The source collectors are not all
inside this repo yet, so the current job is to prove the checked-in reference
artifacts are coherent before the dashboard build consumes them. As each source
collector moves into the repo, its compute step should land behind this command
without changing the operator workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from check_reference_freshness import DEFAULT_ENFORCED_KEYS, build_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "data" / "fixtures" / "current"
DEFAULT_OUTPUT = ROOT / "output" / "reference-build-report.json"
DEFAULT_FRESHNESS = ROOT / "output" / "reference-freshness.json"
REQUIRED_FILES = ("players.json", "comparison-sources-data.json", "player-news.json")
REQUIRED_LIVE_SOURCES = (
    "usatoday",
    "fantasycalc",
    "fantasypros",
    "cbs",
    "espn",
    "cbsros",
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted",
)
# The only sections whose absence fails the build (the anchor every curve is
# indexed to). Other REQUIRED_LIVE_SOURCES must be live when present.
ANCHOR_SOURCES = ("espn",)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(message: str) -> None:
    raise SystemExit(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def validate_players(payload: dict[str, Any]) -> dict[str, Any]:
    players = payload.get("players")
    meta = payload.get("meta", {})
    require(isinstance(players, list) and players, "players.json must contain players[]")
    seen_keys: set[int] = set()
    missing_identity = 0
    for player in players:
        key = player.get("player_key")
        name = str(player.get("name") or player.get("full_name") or "").strip()
        if not isinstance(key, int) or not name or not player.get("pos"):
            missing_identity += 1
            continue
        require(key not in seen_keys, f"duplicate player_key in players.json: {key}")
        seen_keys.add(key)
    require(missing_identity == 0, f"{missing_identity} player rows are missing identity fields")
    return {
        "player_count": len(players),
        "as_of": meta.get("as_of"),
        "espn_snapshot": meta.get("espn_snapshot"),
    }


def validate_comparison(payload: dict[str, Any], player_keys: set[int]) -> dict[str, Any]:
    sources = payload.get("sources")
    source_validation = payload.get("source_validation", {})
    source_player_keys = payload.get("player_keys", {})
    require(isinstance(sources, dict) and sources, "comparison-sources-data.json must contain sources{}")
    # GAP-MISSING-SECTION-REFUSES-RENDER: only the anchor's absence stops the
    # build. Every curve is indexed to ESPN, so without it there is nothing
    # honest to publish. Any other expected section that is missing is
    # DROPPED: the page shows that source as unavailable and renders the rest
    # (product-data.js getMissingSources), so holding the whole deploy on it
    # would only keep the site on an older build. A section that IS present
    # must still be live.
    missing_anchor = [source for source in ANCHOR_SOURCES if source not in sources]
    require(not missing_anchor,
            f"comparison artifact is missing the anchor section: {', '.join(missing_anchor)}")
    dropped = [source for source in REQUIRED_LIVE_SOURCES if source not in sources]
    if dropped:
        print(f"WARNING: comparison artifact is missing sources {', '.join(dropped)}; "
              "the page shows them as unavailable and renders the rest.", file=sys.stderr)
    not_live = [source for source in REQUIRED_LIVE_SOURCES
                if source in sources and source_validation.get(source) != "live"]
    require(not not_live, f"required sources are not live: {', '.join(not_live)}")
    require(isinstance(source_player_keys, dict) and source_player_keys, "comparison artifact must contain player_keys{}")
    orphaned = sorted(
        key for key in set(source_player_keys.values())
        if isinstance(key, int) and key not in player_keys
    )
    require(not orphaned, f"comparison artifact references unknown player_key values: {orphaned[:5]}")
    return {
        "built_at": payload.get("built_at"),
        "source_count": len(sources),
        "required_live_sources": list(REQUIRED_LIVE_SOURCES),
        "anchor_sources": list(ANCHOR_SOURCES),
        "dropped_sources": dropped,
        "source_validation": source_validation,
    }


def validate_news(payload: dict[str, Any], player_keys: set[int]) -> dict[str, Any]:
    meta = payload.get("meta", {})
    news_by_player = payload.get("news_by_player_key", {})
    require(isinstance(meta, dict), "player-news.json must contain meta{}")
    require(isinstance(news_by_player, dict), "player-news.json must contain news_by_player_key{}")
    orphaned = sorted(
        int(key) for key in news_by_player
        if str(key).isdigit() and int(key) not in player_keys
    )
    require(not orphaned, f"player-news artifact references unknown player_key values: {orphaned[:5]}")
    return {
        "generated_at": meta.get("generated_at"),
        "source_refresh_at": meta.get("source_refresh_at"),
        "matched_item_count": meta.get("matched_item_count"),
        "unmatched_item_count": meta.get("unmatched_item_count"),
        "review_queue_count": meta.get("review_queue_count"),
    }


def build_reference_report(
    fixtures: Path,
    freshness_output: Path,
    today: date,
    max_age_days: int,
    enforced_keys: tuple[str, ...] = DEFAULT_ENFORCED_KEYS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    for name in REQUIRED_FILES:
        require((fixtures / name).exists(), f"missing required fixture: {fixtures / name}")

    players = load_json(fixtures / "players.json")
    comparison = load_json(fixtures / "comparison-sources-data.json")
    news = load_json(fixtures / "player-news.json")

    player_summary = validate_players(players)
    player_keys = {
        player["player_key"]
        for player in players["players"]
        if isinstance(player.get("player_key"), int)
    }
    comparison_summary = validate_comparison(comparison, player_keys)
    news_summary = validate_news(news, player_keys)
    freshness = build_report(fixtures, freshness_output, today, max_age_days, enforced_keys)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fixture_dir": str(fixtures),
        "status": "ok",
        "players": player_summary,
        "comparison": comparison_summary,
        "news": news_summary,
        "freshness_summary": freshness["summary"],
        "artifact_hashes": freshness["artifact_hashes"],
    }, freshness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--freshness-output", type=Path, default=DEFAULT_FRESHNESS)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--max-age-days", type=int, default=2)
    parser.add_argument("--enforce-key", action="append", dest="enforce_keys")
    parser.add_argument("--enforce-freshness", action="store_true")
    args = parser.parse_args()

    today = date.fromisoformat(args.today)
    enforce_keys = tuple(args.enforce_keys or DEFAULT_ENFORCED_KEYS)
    report, freshness = build_reference_report(
        args.fixtures,
        args.freshness_output,
        today,
        args.max_age_days,
        enforce_keys,
    )
    if args.enforce_freshness and freshness["summary"]["enforced_expired_count"]:
        expired = [item for item in freshness["items"] if item["enforced"] and not item["freshness_ok"]]
        details = "; ".join(
            f"{item['key']}={item.get('value')} age_days={item.get('age_days')}"
            for item in expired
        )
        fail(f"reference freshness gate failed: {details}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.freshness_output.parent.mkdir(parents=True, exist_ok=True)
    args.freshness_output.write_text(
        json.dumps(freshness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Reference artifacts OK: {args.fixtures}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
