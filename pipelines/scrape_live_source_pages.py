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
import re
import urllib.request
from html.parser import HTMLParser

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
        "url": "https://fantasycalc.com",
        "note": "FantasyCalc web UI (dynamic). Values served via API which powers the human-visible page. API values ARE what the human sees.",
    },
    "cbs": {
        "url": None,
        "note": "CBS data via Supabase public.cbs_trade_values. No direct human-readable trade value page identified.",
    },
    "espn": {
        "url": None,
        "note": "ESPN data is Mike Clay ROS projections via Supabase. No ESPN-published trade value chart page exists.",
    },
}


def normalize_player_key(name):
    """Normalize player name to match lineage player_key format.
    
    Removes punctuation (hyphens, periods, apostrophes), common suffixes
    (Jr, Sr, II, III, IV, V), and lowercases.
    e.g., "Amon-Ra St. Brown" -> "amonra st brown"
         "Ja'Marr Chase" -> "jamarr chase"
         "Jaxon Smith-Njigba" -> "jaxon smithnjigba"
         "James Cook III" -> "james cook"
    """
    key = name.lower()
    # Remove common punctuation
    for char in ["-", ".", "'", "’"]:
        key = key.replace(char, "")
    # Remove common suffixes (as separate words)
    words = key.split()
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    if words and words[-1] in suffixes:
        words = words[:-1]
    key = " ".join(words)
    # Collapse multiple spaces
    key = " ".join(key.split())
    return key


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


def fetch_url(url):
    """Fetch a URL with a browser-like User-Agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def scrape_fantasypros():
    """Scrape FantasyPros Week 4 trade value chart.
    
    Returns dict of player_key -> value (from the Value column).
    The page has separate tables per position; we combine all.
    """
    url = SOURCE_PAGES["fantasypros"]["url"]
    html = fetch_url(url)
    
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
            key = normalize_player_key(name)
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
            
            key = normalize_player_key(name)
            if key not in players or value > players[key]:
                players[key] = value
    
    return players


def main():
    result = {
        "scraped_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "method": "Direct HTML scrape of human-readable source pages",
        "sources": {},
    }
    
    # Scrape FantasyPros
    try:
        fp_players = scrape_fantasypros()
        result["sources"]["fantasypros"] = {
            "url": SOURCE_PAGES["fantasypros"]["url"],
            "note": SOURCE_PAGES["fantasypros"]["note"],
            "player_count": len(fp_players),
            "top25": sorted(fp_players.items(), key=lambda x: x[1], reverse=True)[:25],
            "status": "ok",
        }
        print(f"FantasyPros: scraped {len(fp_players)} players")
    except Exception as e:
        result["sources"]["fantasypros"] = {
            "url": SOURCE_PAGES["fantasypros"]["url"],
            "status": "error",
            "error": str(e)[:200],
        }
        print(f"FantasyPros: ERROR {e}")
    
    # Scrape USA Today
    try:
        usat_players = scrape_usatoday()
        result["sources"]["usatoday"] = {
            "url": SOURCE_PAGES["usatoday"]["url"],
            "note": SOURCE_PAGES["usatoday"]["note"],
            "player_count": len(usat_players),
            "top25": sorted(usat_players.items(), key=lambda x: x[1], reverse=True)[:25],
            "status": "ok",
        }
        print(f"USA Today: scraped {len(usat_players)} players")
    except Exception as e:
        result["sources"]["usatoday"] = {
            "url": SOURCE_PAGES["usatoday"]["url"],
            "status": "error",
            "error": str(e)[:200],
        }
        print(f"USA Today: ERROR {e}")
    
    # Document the non-scrapable sources honestly
    for src in ["fantasycalc", "cbs", "espn"]:
        result["sources"][src] = {
            "url": SOURCE_PAGES[src]["url"],
            "note": SOURCE_PAGES[src]["note"],
            "status": "not_scraped",
        }
    
    out_path = "/home/hatch/workspace/fantasy-tools/dist/modules/live-page-scrape.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\nWrote {out_path}")
    return result


if __name__ == "__main__":
    main()
