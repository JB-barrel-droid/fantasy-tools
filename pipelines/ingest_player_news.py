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
from datetime import datetime, time as day_time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "raw" / "player-news.jsonl"
DEFAULT_RAW_STORE = ROOT / "data" / "raw" / "player-news-articles.json"
DEFAULT_ADJUSTMENTS = ROOT / "data" / "raw" / "player-news-adjustments.json"
DEFAULT_CHECKED = ROOT / "data" / "raw" / "news-checked.json"
DEFAULT_CONSUMED = ROOT / "data" / "raw" / "news-consumed.json"
DEFAULT_OUTPUT = ROOT / "data" / "fixtures" / "current" / "player-news.json"
DEFAULT_UNMATCHED = ROOT / "output" / "player-news-unmatched.json"
DEFAULT_REVIEW = ROOT / "output" / "player-news-review-queue.json"
DEFAULT_MUSE_RAW = ROOT / "data" / "raw" / "muse-player-news"
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
LOW_SIGNAL_REVIEW = re.compile(
    r"\b(injury report|injur(?:y|ies) tracker|live updates|in-game injury updates|"
    r"panic meter|schedule, inactives|week \d+ injuries)\b",
    re.I,
)
TRUSTED_SOURCES = re.compile(
    r"\b(schefter|rapoport|garafolo|fowler|pelissero|team statement|coach|press conference|official)\b",
    re.I,
)
ACTIONABLE_TOPICS = {"injury", "suspension"}
CHECKED_DISPOSITIONS = {"already-priced", "monitoring", "not-material"}
FEED_LABELS = {
    "pft": "ProFootballTalk",
    "espn-nfl": "ESPN NFL",
    "cbs-nfl": "CBS Sports NFL",
    "yahoo-nfl": "Yahoo Sports NFL",
}


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
        entries = (
            payload.get("items")
            or payload.get("news")
            or payload.get("articles")
            or payload.get("entries")
            or payload.get("checked")
            or []
        )
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


def parse_datetime_object(value: Any) -> datetime | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    try:
        return datetime.fromisoformat(parsed.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


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


def latest_default_watchlist_path() -> Path | None:
    if not DEFAULT_MUSE_RAW.exists():
        return None
    matches = sorted(DEFAULT_MUSE_RAW.glob("news-watchlist*.json"))
    return matches[-1] if matches else None


def load_watchlist(path: Path | None, identities: list[PlayerIdentity], by_name: dict[str, PlayerIdentity], top: int) -> list[PlayerIdentity]:
    if path and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        names = payload.get("players", []) if isinstance(payload, dict) else payload
        players: dict[int, PlayerIdentity] = {}
        for name in names if isinstance(names, list) else []:
            player = by_name.get(normalize_phrase(name))
            if player:
                players[player.player_key] = player
        if players:
            return list(players.values())[: max(0, top)]
    return identities[: max(0, top)]


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


def matched_list_players(entry: dict[str, Any], by_name: dict[str, PlayerIdentity]) -> list[PlayerIdentity]:
    matched = entry.get("matched")
    if not isinstance(matched, list):
        return []
    players: dict[int, PlayerIdentity] = {}
    for name in matched:
        player = by_name.get(normalize_phrase(name))
        if player:
            players[player.player_key] = player
    return sorted(players.values(), key=lambda item: (item.rank_score, item.name))


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
    players, reason, candidates = entry_players(entry, identities, by_name)
    if len(players) == 1:
        return players[0], None, players
    if len(players) > 1:
        return None, "multiple_full_name_matches", players
    return None, reason, candidates


def entry_players(entry: dict[str, Any], identities: list[PlayerIdentity], by_name: dict[str, PlayerIdentity]) -> tuple[list[PlayerIdentity], str | None, list[PlayerIdentity]]:
    explicit = explicit_player(entry, by_name)
    if explicit:
        return [explicit], None, [explicit]
    matched = matched_list_players(entry, by_name)
    if matched:
        return matched, None, matched
    matches = headline_matches(entry, identities)
    if matches:
        return matches, None, matches
    return [], "no_full_name_match", []


def source_reliability(entry: dict[str, Any]) -> str:
    text = " ".join(str(entry.get(key) or "") for key in ("source", "title", "summary", "description"))
    return "trusted" if TRUSTED_SOURCES.search(text) else "standard"


def source_name(entry: dict[str, Any]) -> str:
    raw = str(entry.get("source") or entry.get("feed") or "News").strip()
    return FEED_LABELS.get(raw, raw)


def clean_entry(entry: dict[str, Any], player: PlayerIdentity, tags: list[str]) -> dict[str, Any]:
    title = str(entry.get("title") or entry.get("headline") or "").strip()
    summary = str(entry.get("summary") or entry.get("description") or "").strip()
    return {
        "title": title,
        "summary": summary,
        "url": str(entry.get("url") or entry.get("link") or "").strip(),
        "source": source_name(entry),
        "published_at": parse_datetime(entry.get("published_at") or entry.get("published")),
        "tags": tags,
        "player": player.name,
        "player_key": player.player_key,
        "source_reliability": source_reliability(entry),
    }


def load_consumed(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if key and value}


def load_adjustments(path: Path, by_name: dict[str, PlayerIdentity], consumed: dict[str, str]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
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
            "consumed": bool(entry.get("consumed", False)) or str(entry["id"]) in consumed,
            "consumed_at": consumed.get(str(entry["id"])),
        }
        grouped.setdefault(str(player.player_key), []).append(normalized)
    for entries in grouped.values():
        entries.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return grouped, invalid


def load_checked(path: Path) -> list[dict[str, Any]]:
    checked = []
    for entry in load_entries(path):
        disposition = str(entry.get("disposition") or "").strip()
        if disposition == "no-action":
            entry = {**entry, "disposition": "not-material", "original_disposition": disposition}
            disposition = "not-material"
        if disposition in CHECKED_DISPOSITIONS:
            checked.append(entry)
    return checked


def adjustment_cover_dates(adjustments: dict[str, list[dict[str, Any]]]) -> dict[int, datetime]:
    covered: dict[int, datetime] = {}
    for player_key, entries in adjustments.items():
        for entry in entries:
            parsed = parse_datetime_object(entry.get("date"))
            if parsed is None:
                continue
            key = int(player_key)
            covered[key] = max(covered.get(key, parsed), parsed)
    return covered


def checked_cover_dates(checked: list[dict[str, Any]], by_name: dict[str, PlayerIdentity]) -> dict[int, datetime]:
    covered: dict[int, datetime] = {}
    for entry in checked:
        player = explicit_player(entry, by_name)
        parsed = parse_datetime_object(entry.get("date_checked") or entry.get("asof"))
        if player is None or parsed is None:
            continue
        covered[player.player_key] = max(covered.get(player.player_key, parsed), parsed)
    return covered


def suppress_review_item(player_key: int, published_at: str | None, adjusted: dict[int, datetime], checked: dict[int, datetime]) -> bool:
    published = parse_datetime_object(published_at)
    if published is None:
        return False
    if player_key in adjusted and published.date() <= (adjusted[player_key] + timedelta(days=2)).date():
        return True
    if player_key in checked and published.date() <= checked[player_key].date():
        return True
    return False


def review_key(item: dict[str, Any]) -> tuple[int, str]:
    title = normalize_phrase(item.get("headline") or item.get("url") or "")
    return int(item["player_key"]), title


def prune_review_queue(
    candidates: list[dict[str, Any]],
    adjusted: dict[int, datetime],
    checked: dict[int, datetime],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kept: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    counts = {"already_reviewed": 0, "low_signal": 0, "duplicate": 0}
    for item in candidates:
        player_key = int(item["player_key"])
        if suppress_review_item(player_key, item.get("published_at"), adjusted, checked):
            counts["already_reviewed"] += 1
            continue
        if int(item.get("matched_player_count") or 1) > 1 and LOW_SIGNAL_REVIEW.search(str(item.get("headline") or "")):
            counts["low_signal"] += 1
            continue
        key = review_key(item)
        if key in seen:
            counts["duplicate"] += 1
            continue
        seen.add(key)
        kept.append({key: value for key, value in item.items() if key != "matched_player_count"})
    return kept, counts


def assert_injury_data_fresh(args: argparse.Namespace) -> None:
    if not args.require_fresh_injury_data:
        return
    zone = ZoneInfo(args.timezone)
    now = datetime.fromisoformat(args.today.replace("Z", "+00:00")) if args.today else datetime.now(zone)
    if now.tzinfo is None:
        now = now.replace(tzinfo=zone)
    now = now.astimezone(zone)
    friday_evening = now.weekday() > 4 or (now.weekday() == 4 and now.time() >= day_time(18, 0))
    if not friday_evening:
        return
    raw_freshness = args.injury_data_updated_at
    if args.injury_freshness_file and args.injury_freshness_file.exists():
        payload = json.loads(args.injury_freshness_file.read_text(encoding="utf-8"))
        raw_freshness = payload.get("updated_at") or payload.get("generated_at") or payload.get("as_of") or raw_freshness
    updated = parse_datetime_object(raw_freshness)
    if updated is None:
        raise SystemExit("Refusing to build after Friday evening: injury data freshness is unknown.")
    updated_local = updated.astimezone(zone)
    if updated_local.weekday() < 4 or (updated_local.weekday() == 4 and updated_local.time() < day_time(18, 0)):
        raise SystemExit(
            f"Refusing to build after Friday evening: injury data is stale "
            f"({updated_local.isoformat(timespec='minutes')})."
        )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Optional JSON/JSONL item feed to merge.")
    parser.add_argument("--raw-store", type=Path, default=DEFAULT_RAW_STORE, help="Persistent raw article store keyed by URL.")
    parser.add_argument("--adjustments", type=Path, default=DEFAULT_ADJUSTMENTS, help="Curated adjustment JSON/JSONL file.")
    parser.add_argument("--checked-log", type=Path, default=DEFAULT_CHECKED, help="Checked-but-not-adjusted JSON/JSONL log.")
    parser.add_argument("--consumed-log", type=Path, default=DEFAULT_CONSUMED, help="Consumed adjustment id map.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--unmatched-output", type=Path, default=DEFAULT_UNMATCHED)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--fetch-rss", action="store_true", help="Fetch the four league-wide keyless RSS feeds.")
    parser.add_argument("--fetch-google-news", action="store_true", help="Also fetch Google News RSS for the top watchlist players.")
    parser.add_argument("--watchlist-top", type=int, default=200, help="Player count for Google News watchlist.")
    parser.add_argument("--watchlist", type=Path, default=None, help="Optional Muse-style JSON watchlist for Google News pulls.")
    parser.add_argument("--require-fresh-injury-data", action="store_true", help="After Friday 6pm local time, fail closed unless injury data freshness is Friday evening or newer.")
    parser.add_argument("--injury-data-updated-at", default=None, help="Timestamp proving supplemental injury data freshness.")
    parser.add_argument("--injury-freshness-file", type=Path, default=None, help="JSON file carrying updated_at/generated_at/as_of for injury data.")
    parser.add_argument("--today", default=None, help="Override current time for freshness checks.")
    parser.add_argument("--timezone", default="America/Chicago", help="Local timezone for late-week injury freshness checks.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between feed requests, in seconds.")
    args = parser.parse_args()

    identities, by_name, player_snapshot = load_players()
    assert_injury_data_fresh(args)
    entries = dedupe_entries(load_entries(args.raw_store) + load_entries(args.input))

    fetched_count = 0
    watchlist_path = args.watchlist or latest_default_watchlist_path()
    watchlist_count = 0
    if args.fetch_rss or args.fetch_google_news:
        watchlist = load_watchlist(watchlist_path, identities, by_name, args.watchlist_top) if args.fetch_google_news else []
        watchlist_count = len(watchlist)
        fetched = fetch_rss_entries(args.fetch_google_news, watchlist, args.delay)
        fetched_count = len(fetched)
        entries = dedupe_entries(entries + fetched)
        write_json(args.raw_store, {"items": entries, "meta": {"updated_at": utc_now(), "schema": "raw-player-news-v1"}})

    grouped: dict[str, list[dict[str, Any]]] = {}
    unmatched: list[dict[str, Any]] = []
    review_candidates: list[dict[str, Any]] = []
    matched_count = 0
    value_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tags = topic_tags(entry)
        if not is_value_news(entry, tags):
            continue
        value_count += 1
        players, reason, candidates = entry_players(entry, identities, by_name)
        if not players:
            unmatched.append(
                {
                    "title": str(entry.get("title") or entry.get("headline") or "").strip(),
                    "url": str(entry.get("url") or entry.get("link") or "").strip(),
                    "source": source_name(entry),
                    "published_at": parse_datetime(entry.get("published_at") or entry.get("published")),
                    "tags": tags,
                    "reason": reason,
                    "candidate_players": [{"player": candidate.name, "player_key": candidate.player_key} for candidate in candidates],
                }
            )
            continue
        for player in players:
            cleaned = clean_entry(entry, player, tags)
            grouped.setdefault(str(player.player_key), []).append(cleaned)
            matched_count += 1
            if ACTIONABLE_TOPICS.intersection(tags):
                review_candidates.append(
                    {
                        "player": player.name,
                        "player_key": player.player_key,
                        "team": player.team,
                        "pos": player.pos,
                        "topics": tags,
                        "matched_player_count": len(players),
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

    consumed = load_consumed(args.consumed_log)
    adjustments, invalid_adjustments = load_adjustments(args.adjustments, by_name, consumed)
    checked = load_checked(args.checked_log)
    adjusted_cover = adjustment_cover_dates(adjustments)
    checked_cover = checked_cover_dates(checked, by_name)
    review_queue, review_suppression_counts = prune_review_queue(review_candidates, adjusted_cover, checked_cover)
    suppressed_review_count = sum(review_suppression_counts.values())

    payload = {
        "meta": {
            "generated_at": utc_now(),
            "trade_values_published_at": trade_values_published_at(player_snapshot),
            "schema": "player-news-v2",
            "feeds": [{"source": source, "url": url} for source, url in RSS_FEEDS],
            "google_news_watchlist_top": args.watchlist_top if args.fetch_google_news else 0,
            "google_news_watchlist_path": str(watchlist_path) if args.fetch_google_news and watchlist_path else None,
            "google_news_watchlist_count": watchlist_count,
            "fetched_count": fetched_count,
            "raw_item_count": len(entries),
            "value_item_count": value_count,
            "matched_item_count": matched_count,
            "unmatched_item_count": len(unmatched),
            "adjustment_count": sum(len(values) for values in adjustments.values()),
            "invalid_adjustment_count": len(invalid_adjustments),
            "checked_but_not_adjusted_count": len(checked),
            "review_queue_count": len(review_queue),
            "suppressed_review_count": suppressed_review_count,
            "review_suppression_counts": review_suppression_counts,
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
