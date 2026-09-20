#!/usr/bin/env python3
"""Audit finished trade-value references for freshness without mutating data."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "data" / "fixtures" / "current"
DEFAULT_OUTPUT = ROOT / "output" / "reference-freshness.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
      for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def status_for(value: Any, today: date) -> str:
    observed = parse_date(value)
    if observed is None:
        return "unknown"
    if observed == today:
        return "same_day"
    if observed < today:
        return "stale"
    return "future_dated"


def prior_items(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    return {item["key"]: item for item in payload.get("items", []) if isinstance(item, dict) and item.get("key")}


def make_item(key: str, label: str, value: Any, today: date, prior: dict[str, dict[str, Any]]) -> dict[str, Any]:
    previous = prior.get(key, {})
    changed = previous.get("value") != value
    note = "changed" if changed else "unchanged"
    return {
        "key": key,
        "label": label,
        "value": value,
        "status": status_for(value, today),
        "changed_since_prior_report": changed,
        "note": note,
    }


def build_report(fixtures: Path, output: Path, today: date) -> dict[str, Any]:
    players = load_json(fixtures / "players.json")
    comparison = load_json(fixtures / "comparison-sources-data.json")
    news = load_json(fixtures / "player-news.json")
    previous = prior_items(output)

    player_meta = players.get("meta", {})
    news_meta = news.get("meta", {})
    items = [
        make_item("players.as_of", "Players artifact as_of", player_meta.get("as_of"), today, previous),
        make_item("players.ecr_content_date", "Expert/ECR content date", player_meta.get("ecr_content_date"), today, previous),
        make_item("players.espn_snapshot", "ESPN projection snapshot", player_meta.get("espn_snapshot"), today, previous),
        make_item("players.pm_snapshot", "Prediction-market snapshot", player_meta.get("pm_snapshot"), today, previous),
        make_item("players.kdst_snapshot", "K/DST snapshot", player_meta.get("kdst_snapshot"), today, previous),
        make_item("comparison.built_at", "Comparison source artifact build time", comparison.get("built_at"), today, previous),
        make_item("news.generated_at", "Player-news artifact generation time", news_meta.get("generated_at"), today, previous),
        make_item("news.trade_values_published_at", "Trade-value publication timestamp", news_meta.get("trade_values_published_at"), today, previous),
    ]

    hashes = {
        name: sha256(fixtures / name)
        for name in ("players.json", "comparison-sources-data.json", "player-news.json")
    }
    all_same_day = all(item["status"] == "same_day" for item in items if item["status"] != "unknown")
    stale = [item for item in items if item["status"] == "stale"]
    unknown = [item for item in items if item["status"] == "unknown"]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "fixture_dir": str(fixtures),
        "summary": {
            "all_known_dates_same_day": all_same_day,
            "stale_count": len(stale),
            "unknown_count": len(unknown),
            "unchanged_count": sum(1 for item in items if not item["changed_since_prior_report"]),
        },
        "source_validation": comparison.get("source_validation", {}),
        "artifact_hashes": hashes,
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args()

    today = date.fromisoformat(args.today)
    report = build_report(args.fixtures, args.output, today)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {args.output}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
