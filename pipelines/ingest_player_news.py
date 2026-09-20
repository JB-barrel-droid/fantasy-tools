#!/usr/bin/env python3
"""Build the player-news fixture and review queues from RSS or JSON inputs."""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "raw" / "player-news.jsonl"
DEFAULT_RAW_STORE = ROOT / "data" / "raw" / "player-news-articles.json"
DEFAULT_ADJUSTMENTS = ROOT / "data" / "raw" / "player-news-adjustments.json"
DEFAULT_CHECKED = ROOT / "data" / "raw" / "news-checked.json"
DEFAULT_OUTPUT = ROOT / "data" / "fixtures" / "current" / "player-news.json"
DEFAULT_UNMATCHED = ROOT / "output" / "player-news-unmatched.json"
DEFAULT_REVIEW = ROOT / "output" / "player-news-review-queue.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
COMPARISON = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"

RSS_FEEDS = [
    ("ProFootballTalk", "https://profootballtalk.nbcsports.com/feed/"),
    ("ESPN NFL", "https://www.espn.com/espn/rss/nfl/news"),
    ("CBS Sports NFL", "https://www.cbssports.com/rss/headlines/nfl/"),
    ("Yahoo Sports NFL", "https://sports.yahoo.com/nfl/rss.xml"),
]
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
USER_AGENT = "Mozilla/5.0 (compatible; TradeValueDashboardNews/1.0; +https://chatgpt.com)"

TOPIC_RULES = {
    "injury": re.compile(
        r"\b(injur\w*|hurt|sidelined|surger\w*|acl|mcl|concussion|hamstring|"
        r"questionable|doubtful|ir|pup|will miss|ruled out|out for|game-time decision|"
        r"dnp|limited in practice|torn|sprain|fracture)\b",
        re.I,
    ),
    "signing": re.compile(
        r"\b(sign|signs|signed|signing|agree to terms|deal|contract|extension|"
        r"released|cut|waived|claimed|trade|trades|traded|free agent|workout|"
        r"visit|acquir\w*|re-sign)\b",
        re.I,
    ),
    "role": re.compile(
        r"\b(starter|named the starter|depth chart|demot\w*|promot\w*|benched|"
        r"first-team reps|snaps|starting job|lead back|wr1|rb1)\b",
        re.I,
    ),
    "suspension": re.compile(r"\b(suspend\w*|peds|gambling)\b", re.I),
    "retirement": re.compile(r"\b(retire\w*|hang it up|hang them up|calling it a career)\b", re.I),
}
VALUE_TAGS = {
    "injury",
    "availability",
    "role",
    "usage",
    "depth",
    "discipline",
    "suspension",
    "transaction",
    "signing",
    "retirement",
    "fantasy",
    "player_value",
}
VALUE_WORDS = re.compile(
    r"\b(injury|injured|practice|limited|out|questionable|doubtful|suspend|"
    r"suspension|discipline|snap|role|starter|backup|depth|target|touch|carry|"
    r"route|usage|trade|contract|holdout|return|active|inactive|bench|waiver|"
    r"fantasy|value|ir|pup)\b",
    re.I,
)
PERSONAL_ONLY = re.compile(r"\b(birthday|wedding|charity|family|vacation|podcast|interview only)\b", re.I)
TRUSTED_SOURCES = re.compile(
    r"\b(schefter|rapoport|garafolo|fowler|pelissero|team statement|coach|press conference|official)\b",
    re.I,
)
ACTIONABLE_TOPICS = {"injury", "suspension"}
CHECKED_DISPOSITIONS = {"already-priced", "monitoring", "not-material"}


@dataclass(frozen=True)
class PlayerIdentity:
    player_key: int
    name: str
    team: str
    pos: str
    aliases: tuple[str, ...]
    rank_score: float


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_phrase(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&amp;", " and ")
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def player_aliases(name: str) -> tuple[str, ...]:
    base = normalize_phrase(name)
    aliases = {base}
    tokens = base.split()
    if len(tokens) >= 3 and all(len(token) == 1 for token in tokens[:-1]):
        aliases.add("".join(tokens[:-1]) + " " + tokens[-1])
    if len(tokens) >= 3 and all(len(token) == 1 for token in tokens[:2]):
        aliases.add("".join(tokens[:2]) + " " + " ".join(tokens[2:]))
    return tuple(sorted((alias for alias in aliases if alias), key=lambda item: (-len(item), item)))


def load_players() -> tuple[list[PlayerIdentity], dict[str, PlayerIdentity], str | None]:
    payload = json.loads(PLAYERS.read_text(encoding="utf-8"))
    identities: list[PlayerIdentity] = []
    by_name: dict[str, PlayerIdentity] = {}
    for player in payload.get("players", []):
        name = str(player.get("name") or player.get("full_name") or "").strip()
        key = player.get("player_key")
        if not name or not isinstance(key, int):
            continue
        rank = player.get("preseason_ecr_rank")
        rank_score = float(rank) if isinstance(rank, int) else 9999.0
        identity = PlayerIdentity(
            player_key=key,
            name=name,
            team=str(player.get("team") or "").strip(),
            pos=str(player.get("pos") or "").strip(),
            aliases=player_aliases(name),
            rank_score=rank_score,
        )
        identities.append(identity)
        by_name[normalize_phrase(name)] = identity
        for alias in identity.aliases:
            by_name.setdefault(alias, identity)
    identities.sort(key=lambda item: (item.rank_score, item.name))
    return identities, by_name, payload.get("meta", {}).get("as_of")


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
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        entries = payload.get("items") or payload.get("news") or payload.get("articles") or []
        return [item for item in entries if isinstance(item, dict)]
    return []


def parse_datetime(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        try:
            dt = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def strip_markup(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def item_identity(entry: dict[str, Any]) -> str:
    url = str(entry.get("url") or entry.get("link") or "").strip()
    if url:
        return url
    guid = str(entry.get("guid") or entry.get("id") or "").strip()
    if guid:
        return guid
    return " :: ".join(
        str(entry.get(key) or "").strip()
        for key in ("source", "title", "published_at")
        if str(entry.get(key) or "").strip()
    )


def dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for entry in entries:
        identity = item_identity(entry)
        if not identity:
            continue
        current = seen.get(identity)
        if current is None:
            seen[identity] = entry
        else:
            seen[identity] = {**current, **{key: value for key, value in entry.items() if value not in (None, "", [])}}
    return list(seen.values())


def xml_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text
    for child in element:
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in {name.lower().rsplit("}", 1)[-1] for name in names} and child.text:
            return child.text
    return ""


def parse_rss(xml_text_value: str, source: str, feed_url: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text_value)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    parsed: list[dict[str, Any]] = []
    for item in items:
        link = xml_text(item, ("link", "{http://www.w3.org/2005/Atom}link"))
        if not link:
            for child in item:
                if child.tag.rsplit("}", 1)[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    break
        parsed.append(
            {
                "title": strip_markup(xml_text(item, ("title",))),
                "summary": strip_markup(xml_text(item, ("description", "summary", "content"))),
                "url": link.strip(),
                "guid": xml_text(item, ("guid", "id")).strip(),
                "source": source,
                "feed_url": feed_url,
                "published_at": parse_datetime(xml_text(item, ("pubDate", "published", "updated"))),
            }
        )
    return [entry for entry in parsed if entry.get("title")]


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def fetch_feed(source: str, url: str) -> list[dict[str, Any]]:
    return parse_rss(fetch_url(url), source, url)


def fetch_rss_entries(include_google: bool, watchlist: list[PlayerIdentity], delay: float) -> list[dict[str, Any]]:
    fetched: list[dict[str, Any]] = []
    for source, url in RSS_FEEDS:
        fetched.extend(fetch_feed(source, url))
        time.sleep(delay)
    if include_google:
        for player in watchlist:
            query = urllib.parse.quote_plus(f"{player.name} NFL")
            fetched.extend(fetch_feed(f"Google News: {player.name}", GOOGLE_NEWS_URL.format(query=query)))
            time.sleep(delay)
    return fetched


def topic_tags(entry: dict[str, Any]) -> list[str]:
    raw_tags = [str(value or "").lower() for value in (entry.get("tags") or []) if value]
    raw_tags.extend(str(entry.get(key) or "").lower() for key in ("category", "topic", "kind"))
    text = " ".join(str(entry.get(key) or "") for key in ("title", "headline", "summary", "description", "note"))
    tags = {tag for tag in raw_tags if tag in VALUE_TAGS}
    tags.update(topic for topic, rule in TOPIC_RULES.items() if rule.search(text))
    return sorted(tags)


def is_value_news(entry: dict[str, Any], tags: list[str]) -> bool:
    title = str(entry.get("title") or entry.get("headline") or "").strip()
    summary = str(entry.get("summary") or entry.get("description") or "").strip()
    if not title or PERSONAL_ONLY.search(title):
        return False
    return any(tag in VALUE_TAGS for tag in tags) or VALUE_WORDS.search(title) or VALUE_WORDS.search(summary)


def explicit_player(entry: dict[str, Any], by_name: dict[str, PlayerIdentity]) -> PlayerIdentity | None:
    raw_key = entry.get("player_key")
    if isinstance(raw_key, int):
        return next((player for player in by_name.values() if player.player_key == raw_key), None)
    if isinstance(raw_key, str) and raw_key.isdigit():
        key = int(raw_key)
        return next((player for player in by_name.values() if player.player_key == key), None)
    name = normalize_phrase(entry.get("player") or entry.get("player_name") or entry.get("name") or "")
    return by_name.get(name)


def headline_matches(entry: dict[str, Any], identities: list[PlayerIdentity]) -> list[PlayerIdentity]:
    text = normalize_phrase(" ".join(str(entry.get(key) or "") for key in ("title", "headline", "summary", "description")))
    if not text:
        return []
    padded = f" {text} "
    matches: dict[int, PlayerIdentity] = {}
    for player in identities:
        for alias in player.aliases:
            if f" {alias} " in padded:
                matches[player.player_key] = player
                break
    return sorted(matches.values(), key=lambda item: (item.rank_score, item.name))


def matched_player(entry: dict[str, Any], identities: list[PlayerIdentity], by_name: dict[str, PlayerIdentity]) -> tuple[PlayerIdentity | None, str | None, list[PlayerIdentity]]:
    explicit = explicit_player(entry, by_name)
    if explicit:
        return explicit, None, [explicit]
    matches = headline_matches(entry, identities)
    if len(matches) == 1:
        return matches[0], None, matches
    if len(matches) > 1:
        return None, "ambiguous_player_name", matches
    return None, "no_full_name_match", []


def source_reliability(entry: dict[str, Any]) -> str:
    text = " ".join(str(entry.get(key) or "") for key in ("source", "title", "summary", "description"))
    return "trusted" if TRUSTED_SOURCES.search(text) else "standard"


def clean_entry(entry: dict[str, Any], player: PlayerIdentity, tags: list[str]) -> dict[str, Any]:
    title = str(entry.get("title") or entry.get("headline") or "").strip()
    summary = str(entry.get("summary") or entry.get("description") or "").strip()
    return {
        "title": title,
        "summary": summary,
        "url": str(entry.get("url") or entry.get("link") or "").strip(),
        "source": str(entry.get("source") or "News").strip(),
        "published_at": parse_datetime(entry.get("published_at") or entry.get("published")),
        "tags": tags,
        "player": player.name,
        "player_key": player.player_key,
        "source_reliability": source_reliability(entry),
    }


def load_adjustments(path: Path, by_name: dict[str, PlayerIdentity]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    invalid: list[dict[str, Any]] = []
    for entry in load_entries(path):
        player = explicit_player(entry, by_name)
        required = {"id", "date", "player", "kind", "source", "note"}
        missing = sorted(field for field in required if not entry.get(field))
        if player is None or missing:
            invalid.append({**entry, "missing_fields": missing, "match_error": None if player else "no_player_match"})
            continue
        normalized = {
            "id": str(entry["id"]),
            "date": str(entry["date"]),
            "player": player.name,
            "player_key": player.player_key,
            "team": str(entry.get("team") or player.team),
            "kind": str(entry.get("kind") or "").lower(),
            "injury": entry.get("injury"),
            "status": entry.get("status"),
            "weeks_out": entry.get("weeks_out"),
            "weeks_out_range": entry.get("weeks_out_range"),
            "skip_form": bool(entry.get("skip_form", False)),
            "beneficiaries": entry.get("beneficiaries") if isinstance(entry.get("beneficiaries"), list) else [],
            "beneficiary_review": str(entry.get("beneficiary_review") or ""),
            "source": str(entry.get("source") or ""),
            "note": str(entry.get("note") or ""),
            "consumed": bool(entry.get("consumed", False)),
        }
        grouped.setdefault(str(player.player_key), []).append(normalized)
    for entries in grouped.values():
        entries.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return grouped, invalid


def load_checked(path: Path) -> list[dict[str, Any]]:
    checked = []
    for entry in load_entries(path):
        disposition = str(entry.get("disposition") or "").strip()
        if disposition in CHECKED_DISPOSITIONS:
            checked.append(entry)
    return checked


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Optional JSON/JSONL item feed to merge.")
    parser.add_argument("--raw-store", type=Path, default=DEFAULT_RAW_STORE, help="Persistent raw article store keyed by URL.")
    parser.add_argument("--adjustments", type=Path, default=DEFAULT_ADJUSTMENTS, help="Curated adjustment JSON/JSONL file.")
    parser.add_argument("--checked-log", type=Path, default=DEFAULT_CHECKED, help="Checked-but-not-adjusted JSON/JSONL log.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--unmatched-output", type=Path, default=DEFAULT_UNMATCHED)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--fetch-rss", action="store_true", help="Fetch the four league-wide keyless RSS feeds.")
    parser.add_argument("--fetch-google-news", action="store_true", help="Also fetch Google News RSS for the top watchlist players.")
    parser.add_argument("--watchlist-top", type=int, default=200, help="Player count for Google News watchlist.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between feed requests, in seconds.")
    args = parser.parse_args()

    identities, by_name, player_snapshot = load_players()
    entries = dedupe_entries(load_entries(args.raw_store) + load_entries(args.input))

    fetched_count = 0
    if args.fetch_rss or args.fetch_google_news:
        watchlist = identities[: max(0, args.watchlist_top)] if args.fetch_google_news else []
        fetched = fetch_rss_entries(args.fetch_google_news, watchlist, args.delay)
        fetched_count = len(fetched)
        entries = dedupe_entries(entries + fetched)
        write_json(args.raw_store, {"items": entries, "meta": {"updated_at": utc_now(), "schema": "raw-player-news-v1"}})

    grouped: dict[str, list[dict[str, Any]]] = {}
    unmatched: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []
    matched_count = 0
    value_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tags = topic_tags(entry)
        if not is_value_news(entry, tags):
            continue
        value_count += 1
        player, reason, candidates = matched_player(entry, identities, by_name)
        if player is None:
            unmatched.append(
                {
                    "title": str(entry.get("title") or entry.get("headline") or "").strip(),
                    "url": str(entry.get("url") or entry.get("link") or "").strip(),
                    "source": str(entry.get("source") or "News").strip(),
                    "published_at": parse_datetime(entry.get("published_at") or entry.get("published")),
                    "tags": tags,
                    "reason": reason,
                    "candidate_players": [{"player": candidate.name, "player_key": candidate.player_key} for candidate in candidates],
                }
            )
            continue
        cleaned = clean_entry(entry, player, tags)
        grouped.setdefault(str(player.player_key), []).append(cleaned)
        matched_count += 1
        if ACTIONABLE_TOPICS.intersection(tags):
            review_queue.append(
                {
                    "player": player.name,
                    "player_key": player.player_key,
                    "team": player.team,
                    "pos": player.pos,
                    "topics": tags,
                    "source_reliability": cleaned["source_reliability"],
                    "headline": cleaned["title"],
                    "url": cleaned["url"],
                    "published_at": cleaned["published_at"],
                    "adjustment_schema_hint": {
                        "id": "player-event-date",
                        "date": "YYYY-MM-DD",
                        "player": player.name,
                        "team": player.team,
                        "kind": "injury or suspension",
                        "injury": None,
                        "status": None,
                        "weeks_out": None,
                        "weeks_out_range": [None, None],
                        "skip_form": False,
                        "beneficiaries": [],
                        "beneficiary_review": "",
                        "source": "reporter/outlet, YYYY-MM-DD",
                        "note": "",
                    },
                }
            )

    for entries_for_player in grouped.values():
        entries_for_player.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)

    adjustments, invalid_adjustments = load_adjustments(args.adjustments, by_name)
    checked = load_checked(args.checked_log)

    payload = {
        "meta": {
            "generated_at": utc_now(),
            "trade_values_published_at": trade_values_published_at(player_snapshot),
            "schema": "player-news-v2",
            "feeds": [{"source": source, "url": url} for source, url in RSS_FEEDS],
            "google_news_watchlist_top": args.watchlist_top if args.fetch_google_news else 0,
            "fetched_count": fetched_count,
            "raw_item_count": len(entries),
            "value_item_count": value_count,
            "matched_item_count": matched_count,
            "unmatched_item_count": len(unmatched),
            "adjustment_count": sum(len(values) for values in adjustments.values()),
            "invalid_adjustment_count": len(invalid_adjustments),
            "checked_but_not_adjusted_count": len(checked),
            "note": "Generated from play/value related news only. Personal items are filtered out; ambiguous player names are not guessed.",
        },
        "news_by_player_key": grouped,
        "adjustments_by_player_key": adjustments,
        "checked_but_not_adjusted": checked,
    }
    write_json(args.output, payload)
    write_json(
        args.unmatched_output,
        {
            "meta": {"generated_at": payload["meta"]["generated_at"], "count": len(unmatched)},
            "items": unmatched,
            "invalid_adjustments": invalid_adjustments,
        },
    )
    write_json(args.review_output, {"meta": {"generated_at": payload["meta"]["generated_at"], "count": len(review_queue)}, "items": review_queue})
    print(
        f"Wrote {args.output} with {matched_count} matched value-news items, "
        f"{sum(len(values) for values in adjustments.values())} adjustments, and {len(unmatched)} unmatched review items."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
