#!/usr/bin/env python3
"""JEG-1198 option C: check that candidate ROS ranking pages read without sign-in.

Research only, run on a GitHub runner (the dev sandbox cannot reach these hosts).
For each start page (addresses a web search returned, 2026-10-29) it prints the
HTTP status, size, title, published/modified stamps, table and list counts, any
embedded rankings JSON (ecrData) with its first rows, and the links on the page
that look like ROS ranking pages, so the pullers are built on what the pages
really carry. It follows links only on the site's own domain, one level deep.
Writes nothing; prints summaries, never whole pages.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import subprocess
import sys
from urllib.parse import urljoin, urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

START = [
    # round 3 (2026-10-29): every href or option value mentioning ros on the FP pages; USAT table headers
    ("fp_ros_start", "https://www.fantasypros.com/nfl/rankings/?type=ros", None),
    ("fp_ros_overall", "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php", None),
    ("yahoo_usat", "https://sports.yahoo.com/articles/fantasy-football-week-8-trade-193343846.html", None),
]
ESPN_API = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/"
            "segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info")
FOLLOW_LIMIT = 8


def fetch(url: str) -> tuple[int | None, str]:
    p = subprocess.run(["curl", "-sS", "-L", "--compressed", "-o", "-", "-w", "\n%{http_code}",
                        "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9", "--max-time", "45", url],
                       capture_output=True, text=True, errors="replace")
    body, _, code = p.stdout.rpartition("\n")
    try:
        return int(code), body
    except ValueError:
        return None, p.stderr[:300]


def text(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def find_json_var(page: str, var: str):
    m = re.search(r"var\s+" + var + r"\s*=\s*", page)
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(page[m.end():])
        return obj
    except ValueError as e:
        return {"_parse_error": str(e)}


def summarize(tag: str, url: str, link_pat: str | None, depth: int = 0) -> list[str]:
    code, page = fetch(url)
    print(f"\n=== {tag} {url}\nstatus={code} bytes={len(page)}")
    if code != 200:
        print("snippet:", text(page)[:300])
        return []
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    print("title:", text(title.group(1))[:200] if title else None)
    for key in ("datePublished", "dateModified", "article:published_time", "article:modified_time"):
        m = re.search(r'"?' + re.escape(key) + r'"?\s*(?::|content=)\s*"([^"]+)"', page)
        if m:
            print(f"{key}: {m.group(1)}")
    for pat in (r"Updated:?\s*[^<]{0,60}", r"(?i)sign in to|subscribe to (read|continue)|paywall|premium content"):
        hits = re.findall(pat, page)[:3]
        if hits:
            print(f"marker {pat[:30]!r}: {[text(h)[:80] if isinstance(h, str) else h for h in hits]}")
    tables = re.findall(r"<table\b.*?</table>", page, re.S | re.I)
    print(f"tables={len(tables)} rows={[len(re.findall(r'<tr', t, re.I)) for t in tables][:20]}")
    for t in tables[:6]:
        rows = re.findall(r"<tr\b.*?</tr>", t, re.S | re.I)
        for r in rows[:3] + rows[-2:]:
            print("  tr:", text(r)[:160])
        print("  --")
    lis = [text(x) for x in re.findall(r"<li\b[^>]*>(.*?)</li>", page, re.S | re.I)]
    dollar = [x for x in lis if re.match(r"^\$\d+\s+\S", x)]
    print(f"li={len(lis)} dollar_li={len(dollar)} first={dollar[:5]}")
    paras = [text(x) for x in re.findall(r"<p\b[^>]*>(.*?)</p>", page, re.S | re.I)]
    ranked = [x for x in paras if re.match(r"^\d{1,3}[.)]\s+[A-Z]", x)]
    print(f"p={len(paras)} ranked_p={len(ranked)} first={ranked[:6]}")
    for var in ("ecrData", "sosData", "adpData"):
        obj = find_json_var(page, var)
        if obj is None:
            continue
        if isinstance(obj, dict):
            meta = {k: v for k, v in obj.items() if not isinstance(v, (list, dict))}
            print(f"{var} meta: {json.dumps(meta)[:700]}")
            players = obj.get("players") or []
            print(f"{var} players={len(players)}")
            for pl in players[:3]:
                print("  ", json.dumps(pl)[:600])
            if players:
                print("   positions:", sorted({str(p.get('player_position_id')) for p in players}))
    attrs = sorted({m for m in re.findall(r'(?:href|value|data-url|data-href)="([^"]*ros[^"]*)"', page, re.I)
                    if len(m) < 160})
    print(f"attrs mentioning ros: {len(attrs)}")
    for a in attrs[:60]:
        print("   ", a)
    if "usat" in tag:
        for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", page, re.S | re.I):
            h = text(m.group(1))
            if h:
                print("  heading:", h[:120])
    links = []
    if link_pat:
        host = urlparse(url).netloc
        for href in re.findall(r'href="([^"#]+)"', page):
            full = urljoin(url, htmllib.unescape(href))
            if urlparse(full).netloc == host and re.search(link_pat, urlparse(full).path, re.I) and full not in links:
                links.append(full)
        print(f"links matching {link_pat!r}: {len(links)}")
        for l in links[:40]:
            print("  ", l)
    return links


def espn_api() -> None:
    """ESPN's public fantasy API (the one pull_espn_projections.py reads daily):
    which rank fields does a player carry, and for which scoring periods?"""
    filt = {"players": {"filterSlotIds": {"value": [2]}, "limit": 3, "offset": 0,
                        "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "PPR"}}}
    p = subprocess.run(["curl", "-sS", "--max-time", "45", "-A", UA, "-H", "X-Fantasy-Source: kona",
                        "-H", "X-Fantasy-Platform: kona-web", "-H", "X-Fantasy-Filter: " + json.dumps(filt),
                        ESPN_API], capture_output=True, text=True)
    print("\n=== espn_api status bytes", len(p.stdout))
    try:
        players = json.loads(p.stdout)["players"]
    except Exception as e:  # noqa: BLE001
        print("unparseable:", e, p.stdout[:300])
        return
    for pl in players:
        inner = pl.get("player", {})
        print("player:", inner.get("fullName"), "keys:", sorted(inner.keys()))
        rk = inner.get("rankings") or {}
        print("  rankings periods:", sorted(rk.keys(), key=lambda k: int(k))[:30])
        for period in sorted(rk.keys(), key=lambda k: int(k))[-2:]:
            print(f"  period {period}:", json.dumps(rk[period])[:900])
        print("  draftRanksByRankType:", json.dumps(inner.get("draftRanksByRankType"))[:400])


def main() -> int:
    for tag, url, pat in START:
        summarize(tag, url, pat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
