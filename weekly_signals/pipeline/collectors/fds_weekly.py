"""First Down Studio weekly snapshot collector (free, keyless).

Fetches https://firstdown.studio/rankings/wr. The page's embedded Next.js
flight stream carries the FULL-WEEK snapshot for ALL positions (QB/RB/WR/TE
plus K) in one payload — no per-position fetching needed.

Extracts the translated stat estimates + derived fantasy points (standard,
half-PPR, full-PPR) with FDS's own per-stat vegas/projection attribution.

Writes data/fds_wk{N}.json. Fail-closed: any fetch/parse failure exits
non-zero WITHOUT writing a file (a stale or partial payload must never
masquerade as fresh).

IMPORTANT — provenance boundary: FDS publishes DERIVED values only. No raw
over/under lines, no odds, no bookmaker names, no disclosed full
translation methodology. This collector stores the derived numbers VERBATIM
with 'fds-derived' provenance. Nothing here may ever be written into
odds_history or presented as locally calculated from raw sportsbook odds.

Usage: python3 collectors/fds_weekly.py [--week N]
  --week defaults to the snapshot week reported by the page itself.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
DATA_DIR = os.path.join(BASE, "data")

PAGE_URL = "https://firstdown.studio/rankings/wr"
# Positions that belong in the fantasy signals universe. Kickers are parsed
# but excluded from the payload's players list (no signal universe for K).
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
# Translated stat estimate keys FDS publishes per position.
STAT_KEYS = ("passing_yards", "passing_touchdowns", "rushing_yards",
             "rushing_attempts", "receptions", "receiving_yards",
             "expected_touchdowns", "interceptions")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _js_decode(s):
    """Decode a JS double-quoted string literal's escape sequences."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            e = s[i + 1]
            if e == "n":
                out.append("\n"); i += 2
            elif e == "t":
                out.append("\t"); i += 2
            elif e == "r":
                out.append("\r"); i += 2
            elif e == '"':
                out.append('"'); i += 2
            elif e == "'":
                out.append("'"); i += 2
            elif e == "\\":
                out.append("\\"); i += 2
            elif e == "u" and i + 5 < n:
                out.append(chr(int(s[i + 2:i + 6], 16))); i += 6
            else:
                out.append(e); i += 2
        else:
            out.append(c); i += 1
    return "".join(out)


def fetch_page(url=PAGE_URL, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"FDS page HTTP {resp.status}: {url}")
        return resp.read().decode("utf-8", "replace")


def extract_snapshot(html):
    """Parse the flight stream -> (snapshot_meta, records).

    Raises on any structural surprise (fail-closed: never guess at the
    page's data format).
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>',
                        html, re.S)
    if not chunks:
        raise RuntimeError("FDS page: no Next.js flight chunks found; "
                           "page format changed?")
    stream = "".join(_js_decode(c) for c in chunks)
    m = re.search(
        r'"snapshot":\{"snapshot_id":"([^"]+)","season":(\d+),"week":(\d+),'
        r'"generated_at":"([^"]+)"', stream)
    if not m:
        raise RuntimeError("FDS page: snapshot metadata not found in flight "
                           "stream; page format changed?")
    meta = {"snapshot_id": m.group(1), "season": int(m.group(2)),
            "week": int(m.group(3)), "generated_at": m.group(4)}
    # The rows array: bracket-match from '"rows":[' over the decoded stream.
    # Record objects are still JSON-escaped once (\"), so match brackets
    # string-aware, then unescape once before json.loads.
    ri = stream.find('"rows":[')
    if ri < 0:
        raise RuntimeError("FDS page: snapshot rows array not found.")
    start = ri + len('"rows":[')
    depth, in_str, esc, j = 1, False, False, start
    while depth > 0:
        if j >= len(stream):
            raise RuntimeError("FDS page: unterminated rows array.")
        c = stream[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
        j += 1
    inner = stream[start:j - 1].replace('\\"', '"')
    try:
        records = json.loads("[" + inner + "]")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"FDS page: rows JSON parse failed: {e}")
    if not records:
        raise RuntimeError("FDS page: snapshot rows array is empty.")
    return meta, records


def build_payload(meta, records, page_url=PAGE_URL):
    players = []
    pos_counts = {}
    for r in records:
        pos = r.get("position")
        pos_counts[pos] = pos_counts.get(pos, 0) + 1
        if pos not in SKILL_POSITIONS:
            continue
        for pts_key in ("standard", "halfppr", "ppr"):
            if r.get(pts_key) is None:
                raise RuntimeError(
                    f"FDS record missing {pts_key}: {r.get('name')}")
        stats = {k: r[k] for k in STAT_KEYS if r.get(k) is not None}
        players.append({
            "name": r.get("name"),
            "team": r.get("team"),
            "opponent": r.get("opponent"),
            "position": pos,
            "game_key": r.get("game_key"),
            "game_details": r.get("game_details"),
            "kickoff_at": r.get("kickoff_at"),
            "standard": r["standard"],
            "halfppr": r["halfppr"],
            "ppr": r["ppr"],
            "stats": stats,
            "stat_sources": r.get("stat_sources") or {},
            "projected_fields": r.get("projected_fields") or [],
            "injury_status": r.get("injury_status"),
            "fds_updated_at": r.get("updated_at"),
        })
    if not players:
        raise RuntimeError("FDS page: no QB/RB/WR/TE records in snapshot.")
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "page_url": page_url,
        "snapshot_id": meta["snapshot_id"],
        "snapshot_generated_at": meta["generated_at"],
        "season": meta["season"],
        "week": meta["week"],
        "provenance": "fds-derived",
        "methodology_note": (
            "Derived fantasy points translated by First Down Studio from "
            "sportsbook prop markets (per-stat vegas/projection attribution "
            "as published by FDS). FDS discloses no raw lines/odds, no "
            "bookmaker names, and no full translation methodology. These "
            "numbers are NOT locally calculated from raw sportsbook odds and "
            "must never be presented as such."),
        "position_counts": pos_counts,
        "players": players,
    }


def main(week=None):
    html = fetch_page()
    meta, records = extract_snapshot(html)
    if week is not None and meta["week"] != week:
        raise RuntimeError(
            f"FDS snapshot is week {meta['week']}, requested week {week}; "
            "refusing to write a cross-week payload.")
    payload = build_payload(meta, records)
    path = os.path.join(DATA_DIR, f"fds_wk{payload['week']}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=1)
    os.replace(tmp, path)
    n_vegas = sum(1 for p in payload["players"]
                  if any(v == "vegas"
                         for v in p["stat_sources"].values()))
    print(f"FDS snapshot {payload['snapshot_id']}: week {payload['week']}, "
          f"generated {payload['snapshot_generated_at']}")
    print(f"  players: {len(payload['players'])} "
          f"({payload['position_counts']}), "
          f"{n_vegas} with >=1 vegas-sourced stat")
    print(f"  wrote {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None,
                    help="fail if the page snapshot is not this week")
    a = ap.parse_args()
    try:
        main(week=a.week)
    except Exception as e:
        print(f"FDS pull FAILED (fail-closed, no file written): {e}",
              file=sys.stderr)
        sys.exit(1)
