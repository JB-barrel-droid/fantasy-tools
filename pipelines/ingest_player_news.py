#!/usr/bin/env python3
"""Build the player-news fixture from a JSON or JSONL news feed."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "raw" / "player-news.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "fixtures" / "current" / "player-news.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
COMPARISON = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"

VALUE_WORDS = re.compile(
    r"\b(injury|injured|practice|limited|out|questionable|doubtful|suspend|"
    r"suspension|discipline|snap|role|starter|backup|depth|target|touch|carry|"
    r"route|usage|trade|contract|holdout|return|active|inactive|bench|waiver|"
    r"fantasy|value)\b",
    re.I,
)
PERSONAL_ONLY = re.compile(r"\b(birthday|wedding|charity|family|vacation|podcast|interview only)\b", re.I)
VALUE_TAGS = {"injury", "availability", "role", "usage", "depth", "discipline", "suspension", "transaction", "fantasy", "player_value"}


def load_players() -> tuple[dict[str, int], str | None]:
    payload = json.loads(PLAYERS.read_text(encoding="utf-8"))
    by_name = {
        str(player.get("name") or player.get("full_name") or "").strip().lower(): int(player["player_key"])
        for player in payload.get("players", [])
        if player.get("player_key") and (player.get("name") or player.get("full_name"))
    }
    return by_name, payload.get("meta", {}).get("as_of")


def trade_values_published_at(fallback: str | None) -> str | None:
    if COMPARISON.exists():
        comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
        if comparison.get("built_at"):
            return comparison["built_at"]
    return fallback


def load_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("items", []) or payload.get("news", [])
    return []


def normalized_player_key(entry: dict[str, Any], by_name: dict[str, int]) -> int | None:
    raw_key = entry.get("player_key")
    if isinstance(raw_key, int):
        return raw_key
    if isinstance(raw_key, str) and raw_key.isdigit():
        return int(raw_key)
    name = str(entry.get("player") or entry.get("player_name") or entry.get("name") or "").strip().lower()
    return by_name.get(name)


def is_value_news(entry: dict[str, Any]) -> bool:
    title = str(entry.get("title") or entry.get("headline") or "").strip()
    summary = str(entry.get("summary") or entry.get("description") or "").strip()
    tags = [str(value or "").lower() for value in (entry.get("tags") or [])]
    tags.extend(str(entry.get(key) or "").lower() for key in ("category", "topic"))
    if not title or PERSONAL_ONLY.search(title):
        return False
    return any(tag in VALUE_TAGS for tag in tags) or VALUE_WORDS.search(title) or VALUE_WORDS.search(summary)


def clean_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(entry.get("title") or entry.get("headline") or "").strip(),
        "summary": str(entry.get("summary") or entry.get("description") or "").strip(),
        "url": str(entry.get("url") or "").strip(),
        "source": str(entry.get("source") or "News").strip(),
        "published_at": entry.get("published_at") or entry.get("published") or None,
        "tags": entry.get("tags") if isinstance(entry.get("tags"), list) else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    by_name, player_snapshot = load_players()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in load_entries(args.input):
        if not isinstance(entry, dict) or not is_value_news(entry):
            continue
        player_key = normalized_player_key(entry, by_name)
        if player_key is None:
            continue
        grouped.setdefault(str(player_key), []).append(clean_entry(entry))

    for entries in grouped.values():
        entries.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "trade_values_published_at": trade_values_published_at(player_snapshot),
            "schema": "player-news-v1",
            "note": "Generated from play/value related news only. Personal items are filtered out; suspensions and availability items are kept.",
        },
        "news_by_player_key": grouped,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} with {sum(len(v) for v in grouped.values())} news items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
