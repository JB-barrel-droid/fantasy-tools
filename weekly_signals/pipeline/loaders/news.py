"""News recency loader (free, no auth — RSS).

Pulls Google News RSS per player for the current watchlist (players with
rank-gap signals + top ECR names) and stores items with publish timestamps.
This is the news-absorption / recency signal: a signal whose delta is
explained by fresh news (trade, injury update, depth-chart change) is
less "market insight" and more "stale expert rank".

Also pulls the league-wide Yahoo + ESPN NFL feeds for team-level news.

Run daily (cheap: ~250 small RSS fetches).
"""
import os
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-football-signal/bin"))
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-mgmt/bin"))

import sbclient  # noqa: E402
import mgmt  # noqa: E402
from engine.snapshot import norm  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.4 Safari/605.1.15",
      "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"}

LEAGUE_FEEDS = [
    ("yahoo-nfl", "https://sports.yahoo.com/nfl/rss/"),
    ("espn-nfl", "https://www.espn.com/espn/rss/nfl/news"),
]


def fetch_rss(url):
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, timeout=30).read()
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        src = it.findtext("source")
        try:
            published = (parsedate_to_datetime(pub).isoformat()
                         if pub else None)
        except (ValueError, TypeError):
            published = None
        if title and link:
            items.append({"title": title, "url": link,
                          "published_at": published,
                          "source": src.strip() if src else None})
    return items


def watchlist(week, season=2026, limit=200):
    """Players with rank-gap signals this week + top ECR names (from files)."""
    sig_path = os.path.join(BASE, "data", "signals_v4.json")
    names = []
    if os.path.exists(sig_path):
        sig = json.load(open(sig_path))
        names = [s["name"] for s in sig]
    ecr_path = os.path.join(BASE, "data", "ecr_pos.json")
    if os.path.exists(ecr_path):
        ecr = json.load(open(ecr_path))
        # ecr_pos.json: norm name -> {name, pos, team, rank_ecr, ...}
        ranked = sorted(
            ((v.get("rank_ecr", 999) if isinstance(v, dict) else 999, k)
             for k, v in ecr.items()))
        have = {norm(n) for n in names}
        for _, k in ranked:
            v = ecr[k]
            disp = v.get("name", k) if isinstance(v, dict) else k
            if norm(disp) not in have:
                names.append(disp)
                have.add(norm(disp))
            if len(names) >= limit:
                break
    return names[:limit]


def main(week=None, season=2026):
    if week is None:
        from engine.week import current_week
        week = current_week(season)
    from loaders.sleeper import load_players
    by_name, _, _ = load_players()

    names = watchlist(week, season)
    print(f"watchlist: {len(names)} players", flush=True)
    now = datetime.now(timezone.utc).isoformat()
    batch, n = [], 0
    for name in names:
        q = urllib.parse.quote(f"{name} NFL")
        url = (f"https://news.google.com/rss/search?q={q}"
               f"&hl=en-US&gl=US&ceid=US:en")
        try:
            items = fetch_rss(url)
        except Exception as e:
            print(f"  rss fail {name}: {str(e)[:60]}", flush=True)
            continue
        pid = (by_name.get(norm(name)) or {}).get("id")
        for it in items[:10]:
            it["player_id"] = pid
            it["player_name"] = name
            it["fetched_at"] = now
            batch.append(it)
        if len(batch) >= 200:
            n += _store(batch)
            batch = []
    # league feeds (team-level news, no player link)
    for feed_name, feed_url in LEAGUE_FEEDS:
        try:
            items = fetch_rss(feed_url)
        except Exception as e:
            print(f"  rss fail {feed_name}: {str(e)[:60]}", flush=True)
            continue
        for it in items[:30]:
            it["player_id"] = None
            it["player_name"] = None
            it["source"] = feed_name
            it["fetched_at"] = now
            batch.append(it)
    if batch:
        n += _store(batch)
    print(f"news: {n} items stored", flush=True)
    return {"stored": n, "players": len(names)}


def _store(batch):
    from sbclient import _request
    # dedupe within the batch (same story can match multiple players)
    seen, uniq = set(), []
    for it in batch:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        uniq.append(it)
    if not uniq:
        return 0
    _request("POST", "/rest/v1/news_items", body=uniq,
             params="?on_conflict=url", prefer="resolution=merge-duplicates")
    return len(uniq)


if __name__ == "__main__":
    main()
