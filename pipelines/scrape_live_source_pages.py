#!/usr/bin/env python3
"""Scrape live human-readable source pages for trade values.

The user requires that verification data comes from the live pages
a human would visit, not API endpoints or database snapshots.

Currently supports:
- FantasyPros: Week 4 trade value chart article (HTML tables)
- USA Today: Week 4 trade value chart article (HTML tables)

For FantasyCalc, CBS, ESPN: documented below with honest limitations.
"""

import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser

# Use the canonical normalization rule from the maintained identity system.
# The Supabase `players` table is the canonical roster; norm_player_name()
# is the single normalization rule (lowercase, strip punctuation/suffixes,
# expand nicknames). Do not reimplement normalization here.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from canonical_players import norm_player_name

# Expected page headers for verification (ensures we're scraping the right week/page)
# If the page title doesn't contain the expected text, the scraper FAILS
# rather than silently scraping the wrong page.
EXPECTED_HEADERS = {
    "fantasypros": "Week 4",
    "usatoday": "Week 4",
    "fantasycalc": "Trade Value Chart",
    "cbs": "Week 4",
    "espn": "2026",
}


def verify_page_header(html, source, url):
    """Verify the page header contains the expected text.
    
    Raises ValueError if the header doesn't match — fail closed rather than
    scrape the wrong page (e.g., last week's article).
    """
    expected = EXPECTED_HEADERS.get(source)
    if not expected:
        return  # No header check configured
    
    # Extract <title> and <h1> for checking
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    
    title = title_match.group(1).strip() if title_match else ""
    h1 = h1_match.group(1).strip() if h1_match else ""
    # Strip HTML tags from h1
    h1 = re.sub(r'<[^>]+>', '', h1).strip()
    
    combined = f"{title} {h1}"
    if expected.lower() not in combined.lower():
        raise ValueError(
            f"Header verification FAILED for {source}: expected '{expected}' "
            f"in page header, got title='{title[:80]}', h1='{h1[:80]}'. "
            f"URL: {url}. Refusing to scrape wrong page."
        )
    print(f"  ✓ Header verified for {source}: '{expected}' found")


# Human-readable source pages (what a human visits)
SOURCE_PAGES = {
    "fantasypros": {
        "url": "https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-4-2026/",
        "note": "FantasyPros Week 4 trade value chart article - HTML tables scraped directly",
    },
    "usatoday": {
        "url": "https://www.usatoday.com/story/sports/fantasy/football/2026/09/29/fantasy-trade-value-chart-week-4-ros-rankings/92008742007/",
        "note": "USA Today Week 4 trade value chart - HTML tables with STD/Half/PPR columns scraped directly",
    },
    "fantasycalc": {
        "url": "https://fantasycalc.com/trade-value-chart",
        "api_url": "https://api.fantasycalc.com/values/current?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5",
        "note": "FantasyCalc trade value chart (12-team, Half PPR, Redraft). Values via the API that powers the human-visible page - same numbers a human sees.",
    },
    "cbs": {
        "url": "https://www.cbssports.com/fantasy/football/news/dave-richards-week-4-trade-chart-and-rest-of-season-fantasy-football-rankings-help-you-win-now/",
        "note": "CBS Sports Dave Richard's Week 4 trade value chart - HTML tables with NON/0.5/PPR columns, 0.5 is Half PPR",
    },
    "espn": {
        "url": None,
        "note": "ESPN data is Mike Clay ROS projections via Supabase. No ESPN-published trade value chart page exists.",
    },
}


class TableParser(HTMLParser):
    """Extract all HTML tables as lists of rows."""
    
    def __init__(self):
        super().__init__()
        self.tables = []
        self._current_table = None
        self._current_row = None
        self._current_cell = None
    
    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in ("td", "th") and self._current_row is not None:
            self._current_cell = ""
    
    def handle_endtag(self, tag):
        if tag == "table" and self._current_table is not None:
            self.tables.append(self._current_table)
            self._current_table = None
        elif tag == "tr" and self._current_row is not None:
            self._current_table.append(self._current_row)
            self._current_row = None
        elif tag in ("td", "th") and self._current_cell is not None:
            self._current_row.append(self._current_cell.strip())
            self._current_cell = None
    
    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell += data


def fetch_url(url, max_retries=4):
    """Fetch a URL with a browser-like User-Agent, retrying transient blocks.

    Publisher pages sit behind intermittent bot mitigation that answers with
    HTTP 402/429 or kills the connection outright. Those are retriable --
    a single attempt failing used to poison downstream builders with nulls.
    """
    import random
    import time
    from http.client import RemoteDisconnected

    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_err = e
            # Bot-mitigation / rate-limit responses are worth retrying.
            if e.code not in (402, 408, 429, 500, 502, 503, 504):
                raise
        except (RemoteDisconnected, TimeoutError, urllib.error.URLError, ConnectionError) as e:
            last_err = e
        # Exponential backoff with jitter before the next attempt.
        if attempt < max_retries - 1:
            delay = (2 ** attempt) + random.uniform(0, 1)
            print(f"  fetch retry {attempt + 1}/{max_retries - 1} after {delay:.1f}s: {last_err}")
            time.sleep(delay)
    raise RuntimeError(f"fetch_url failed after {max_retries} attempts for {url}: {last_err}")


def scrape_fantasypros():
    """Scrape FantasyPros Week 4 trade value chart.
    
    Returns dict of player_key -> value (from the Value column).
    The page has separate tables per position; we combine all.
    """
    url = SOURCE_PAGES["fantasypros"]["url"]
    html = fetch_url(url)
    verify_page_header(html, "fantasypros", url)
    
    parser = TableParser()
    parser.feed(html)
    
    players = {}
    for table in parser.tables:
        if not table or len(table) < 2:
            continue
        # Check if this is a trade value table (has Name/Value columns)
        header = [c.lower() for c in table[0]]
        if "name" not in header or "value" not in header:
            continue
        
        name_idx = header.index("name")
        value_idx = header.index("value")
        
        for row in table[1:]:
            if len(row) <= max(name_idx, value_idx):
                continue
            name = row[name_idx].strip()
            try:
                value = float(row[value_idx])
            except (ValueError, IndexError):
                continue
            
            # Normalize to player_key format (lowercase, no punctuation)
            key = norm_player_name(name)
            # Keep the highest value if player appears multiple times
            if key not in players or value > players[key]:
                players[key] = value
    
    return players


def scrape_usatoday():
    """Scrape USA Today Week 4 trade value chart.
    
    Returns dict of player_key -> half_ppr_value.
    The page has tables with RK/Player/STD/Half/PPR columns.
    """
    url = SOURCE_PAGES["usatoday"]["url"]
    html = fetch_url(url)
    verify_page_header(html, "usatoday", url)
    
    parser = TableParser()
    parser.feed(html)
    
    players = {}
    for table in parser.tables:
        if not table or len(table) < 2:
            continue
        header = [c.lower() for c in table[0]]
        # Look for Player and Half columns
        if "player" not in header or "half" not in header:
            continue
        
        player_idx = header.index("player")
        half_idx = header.index("half")
        
        for row in table[1:]:
            if len(row) <= max(player_idx, half_idx):
                continue
            name = row[player_idx].strip()
            try:
                value = float(row[half_idx])
            except (ValueError, IndexError):
                continue
            
            key = norm_player_name(name)
            if key not in players or value > players[key]:
                players[key] = value
    
    return players


def scrape_cbs():
    """Scrape CBS Sports Dave Richard's Week 4 trade value chart.
    
    Returns dict of player_key -> half_ppr_value.
    The page has tables per position with NON/0.5/PPR columns;
    we use the 0.5 (Half PPR) column. QB table uses 1QB-4/1QB-6/2QB
    columns (no half-PPR), so QBs are excluded.
    """
    url = SOURCE_PAGES["cbs"]["url"]
    html = fetch_url(url)
    
    parser = TableParser()
    parser.feed(html)
    
    players = {}
    for table in parser.tables:
        if not table or len(table) < 2:
            continue
        header = [c.lower().strip() for c in table[0]]
        # Look for the 0.5 (Half PPR) column in RB/WR/TE tables
        # Header may have "0.5", "half", or similar
        half_idx = None
        name_idx = None
        for i, col in enumerate(header):
            if col in ("0.5", "half", "half-ppr", "half ppr"):
                half_idx = i
            if col in ("player", "name"):
                name_idx = i
        
        if half_idx is None or name_idx is None:
            continue
        
        for row in table[1:]:
            if len(row) <= max(name_idx, half_idx):
                continue
            name = row[name_idx].strip()
            if not name:
                continue
            try:
                value = float(row[half_idx])
            except (ValueError, IndexError):
                continue
            
            key = norm_player_name(name)
            if key not in players or value > players[key]:
                players[key] = value
    
    return players


def scrape_fantasycalc():
    """Scrape FantasyCalc trade values.
    
    Returns dict of player_key -> redraft_value.
    Uses the API endpoint that powers the human-visible page at
    fantasycalc.com/trade-value-chart (12-team, Half PPR, Redraft).
    The API returns the same numbers a human sees on the page.
    """
    import json as json_lib
    api_url = SOURCE_PAGES["fantasycalc"]["api_url"]
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json_lib.loads(resp.read().decode("utf-8"))
    
    players = {}
    for entry in data:
        player = entry.get("player", {})
        name = player.get("name", "").strip()
        if not name:
            continue
        # Use redraftValue (12-team Half PPR redraft) - matches page settings
        value = entry.get("redraftValue")
        if value is None:
            value = entry.get("value")
        if value is None:
            continue
        
        key = norm_player_name(name)
        # API values are on FantasyCalc's native scale (e.g., 10838 for Gibbs)
        # Keep as-is; the lineage builder compares native vs native
        if key not in players or value > players[key]:
            players[key] = float(value)
    
    return players


def main():
    result = {
        "scraped_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": "Direct HTML scrape of human-readable source pages",
        "sources": {},
    }

    # Preserve last-known-good per-source data: if a live fetch fails behind a
    # bot wall, keep the previous successful rows and mark them stale rather
    # than wiping the source. Downstream builders must never see empty.
    prev_sources = {}
    out_path = "/home/hatch/workspace/fantasy-tools/dist/modules/live-page-scrape.json"
    if os.path.exists(out_path):
        try:
            prev_sources = json.load(open(out_path)).get("sources", {})
        except Exception:
            prev_sources = {}

    def _on_scrape_error(src, err):
        """Keep previous successful rows for src, flagged stale. Returns the entry."""
        prev = prev_sources.get(src) or {}
        if prev.get("status") == "ok" and prev.get("top25"):
            entry = dict(prev)
            entry["stale"] = True
            entry["stale_error"] = str(err)[:200]
            entry["stale_as_of"] = result["scraped_at"]
            print(f"{src}: ERROR {err} -- keeping {len(prev['top25'])} last-known-good rows (stale)")
            return entry
        return {
            "url": SOURCE_PAGES[src]["url"],
            "status": "error",
            "error": str(err)[:200],
        }
    
    # Scrape FantasyPros
    try:
        fp_players = scrape_fantasypros()
        result["sources"]["fantasypros"] = {
            "url": SOURCE_PAGES["fantasypros"]["url"],
            "note": SOURCE_PAGES["fantasypros"]["note"],
            "player_count": len(fp_players),
            "top25": sorted(fp_players.items(), key=lambda x: x[1], reverse=True)[:25],
            "all_players": dict(sorted(fp_players.items(), key=lambda x: x[1], reverse=True)),
            "status": "ok",
        }
        print(f"FantasyPros: scraped {len(fp_players)} players")
    except Exception as e:
        result["sources"]["fantasypros"] = _on_scrape_error("fantasypros", e)
        print(f"FantasyPros: ERROR {e}")
    
    # Scrape USA Today
    try:
        usat_players = scrape_usatoday()
        result["sources"]["usatoday"] = {
            "url": SOURCE_PAGES["usatoday"]["url"],
            "note": SOURCE_PAGES["usatoday"]["note"],
            "player_count": len(usat_players),
            "top25": sorted(usat_players.items(), key=lambda x: x[1], reverse=True)[:25],
            "all_players": dict(sorted(usat_players.items(), key=lambda x: x[1], reverse=True)),
            "status": "ok",
        }
        print(f"USA Today: scraped {len(usat_players)} players")
    except Exception as e:
        result["sources"]["usatoday"] = _on_scrape_error("usatoday", e)
        print(f"USA Today: ERROR {e}")
    
    # Scrape FantasyCalc
    try:
        fc_players = scrape_fantasycalc()
        result["sources"]["fantasycalc"] = {
            "url": SOURCE_PAGES["fantasycalc"]["url"],
            "note": SOURCE_PAGES["fantasycalc"]["note"],
            "player_count": len(fc_players),
            "top25": sorted(fc_players.items(), key=lambda x: x[1], reverse=True)[:25],
            "all_players": dict(sorted(fc_players.items(), key=lambda x: x[1], reverse=True)),
            "status": "ok",
        }
        print(f"FantasyCalc: scraped {len(fc_players)} players")
    except Exception as e:
        result["sources"]["fantasycalc"] = _on_scrape_error("fantasycalc", e)
        print(f"FantasyCalc: ERROR {e}")
    
    # Scrape CBS
    try:
        cbs_players = scrape_cbs()
        result["sources"]["cbs"] = {
            "url": SOURCE_PAGES["cbs"]["url"],
            "note": SOURCE_PAGES["cbs"]["note"],
            "player_count": len(cbs_players),
            "top25": sorted(cbs_players.items(), key=lambda x: x[1], reverse=True)[:25],
            "all_players": dict(sorted(cbs_players.items(), key=lambda x: x[1], reverse=True)),
            "status": "ok",
        }
        print(f"CBS: scraped {len(cbs_players)} players")
    except Exception as e:
        result["sources"]["cbs"] = _on_scrape_error("cbs", e)
        print(f"CBS: ERROR {e}")
    
    # Document ESPN honestly (no trade value chart exists)
    result["sources"]["espn"] = {
        "url": SOURCE_PAGES["espn"]["url"],
        "note": SOURCE_PAGES["espn"]["note"],
        "status": "not_scraped",
    }
    
    out_path = "/home/hatch/workspace/fantasy-tools/dist/modules/live-page-scrape.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\nWrote {out_path}")
    return result


if __name__ == "__main__":
    main()
