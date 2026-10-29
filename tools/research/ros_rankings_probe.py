#!/usr/bin/env python3
"""JEG-1198 option C, round 4: check Jeremy's added sources for public ROS pages.

Research only, run on a GitHub runner. Jeremy, 2026-10-29: "try fantasylife,
footballguys, rotoballer, roto street journal, and multiple cuts of the fantasypros
data". Start pages are addresses a web search returned. For each it prints status,
size, title, stamps, tables, sign-up or paywall markers, embedded JSON blobs (their
keys only), same-site script and API addresses the page itself names, and links
that look like ROS ranking pages. Expert-consensus ROS pages it finds on the
consensus site's own links are followed and their ecrData summarized. Reads only,
no sign-in, prints summaries, never whole pages.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import subprocess
from urllib.parse import urljoin, urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
START = [
    ("fantasylife_ros", "https://www.fantasylife.com/fantasy-football-rankings/rest-of-season"),
    ("rotoballer_ros", "https://www.rotoballer.com/fantasy-football-rankings-rest-of-season-ros"),
    ("footballguys_ros_wk8", "https://www.footballguys.com/article/2026-rest-of-season-rankings-week08"),
    ("rsj_ros_wk8", "https://www.rotostreetjournal.com/2026/10/26/rest-of-season-rankings-fantasy-football-2026-week-8-ros-update/"),
    ("fp_ros_start", "https://www.fantasypros.com/nfl/rankings/?type=ros"),
    ("fp_ros_half", "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php"),
]
FP_ROS_RE = re.compile(r"^/nfl/rankings/ros-[a-z0-9-]+\.php$")


def fetch(url):
    p = subprocess.run(["curl", "-sS", "-L", "--compressed", "-o", "-", "-w", "\n%{http_code}",
                        "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9", "--max-time", "45", url],
                       capture_output=True, text=True, errors="replace")
    body, _, code = p.stdout.rpartition("\n")
    try:
        return int(code), body
    except ValueError:
        return None, p.stderr[:300]


def text(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def ecr_summary(page):
    m = re.search(r"var\s+ecrData\s*=\s*", page)
    if not m:
        return None
    try:
        d, _ = json.JSONDecoder().raw_decode(page[m.end():])
    except ValueError as e:
        return f"parse error {e}"
    players = d.get("players") or []
    pos = {}
    for p in players:
        pos[p.get("player_position_id")] = pos.get(p.get("player_position_id"), 0) + 1
    return {k: d.get(k) for k in ("ranking_type_name", "scoring", "position_id", "total_experts",
                                  "last_updated", "last_updated_ts", "year", "week")} | {
        "players": len(players), "by_pos": pos,
        "first": [(p.get("rank_ecr"), p.get("player_name"), p.get("pos_rank")) for p in players[:3]]}


def summarize(tag, url):
    code, page = fetch(url)
    print(f"\n=== {tag} {url}\nstatus={code} bytes={len(page)}")
    if code != 200 or len(page) < 2000:
        print("snippet:", text(page)[:300])
        return page if code == 200 else ""
    host = urlparse(url).netloc
    t = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    print("title:", text(t.group(1))[:160] if t else None)
    for key in ("datePublished", "dateModified"):
        m = re.search(r'"' + key + r'"\s*:\s*"([^"]+)"', page)
        if m:
            print(f"{key}: {m.group(1)}")
    for pat in (r"(?i)insider account|subscribe to (read|continue)|premium|fantasylife\+|sign up|log ?in to"):
        hits = sorted({text(h if isinstance(h, str) else h[0]) for h in re.findall(pat, page)})[:6]
        print("gate markers:", hits)
    tables = re.findall(r"<table\b.*?</table>", page, re.S | re.I)
    print(f"tables={len(tables)} rows={[len(re.findall(r'<tr', x, re.I)) for x in tables][:12]}")
    for x in tables[:3]:
        rows = re.findall(r"<tr\b.*?</tr>", x, re.S | re.I)
        print("  table sample:", [text(r)[:90] for r in rows[:4]])
    lis = [text(x) for x in re.findall(r"<li\b[^>]*>(.*?)</li>", page, re.S | re.I)]
    ranked = [x for x in lis if re.match(r"^(QB|RB|WR|TE)?\d{1,3}[\s.:)-]", x)]
    print(f"li={len(lis)} ranked-looking li={len(ranked)} sample={ranked[:6]}")
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if nd:
        try:
            d = json.loads(nd.group(1))
            pp = d.get("props", {}).get("pageProps", {})
            print("__NEXT_DATA__ pageProps keys:", list(pp)[:30])
            print("  buildId:", d.get("buildId"), "page:", d.get("page"))
            blob = json.dumps(pp)
            print("  pageProps bytes:", len(blob), "mentions 'rank':", blob.count('"rank'))
        except ValueError as e:
            print("__NEXT_DATA__ parse error", e)
    nf = re.findall(r'self\.__next_f\.push', page)
    if nf:
        chunk = "".join(re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S))
        print(f"next_f pushes={len(nf)} bytes={len(chunk)} rank-ish={len(re.findall(r'(?i)ranking|consensus', chunk))}")
        for kw in ("playerName", "player_name", "consensus", "\\\"rank\\\""):
            i = chunk.find(kw)
            if i >= 0:
                print(f"  around {kw!r}:", chunk[max(0, i - 120):i + 200].replace("\\\"", '"')[:320])
    for var in re.findall(r"var\s+([A-Za-z_]\w*(?:Data|Rankings|rankings|data))\s*=\s*[\[{]", page)[:10]:
        print("js var:", var)
    srcs = sorted({s for s in re.findall(r'<script[^>]+src="([^"]+)"', page)})
    print("scripts:", [s for s in srcs if urlparse(urljoin(url, s)).netloc.endswith(host.split(".", 1)[-1])][:12])
    apis = sorted({a for a in re.findall(r'["\'](https?://[^"\']*(?:api|json|graphql|sheets)[^"\']*|/[a-z0-9_/-]*(?:api|json)[^"\']*)["\']', page)})
    print("api-ish addresses named on the page:", apis[:25])
    iframes = re.findall(r'<iframe[^>]+src="([^"]+)"', page)
    print("iframes:", iframes[:6])
    links = sorted({urljoin(url, h) for h in re.findall(r'href="([^"#]+)"', page)
                    if re.search(r"(?i)rest-of-season|ros|spreadsheet", h)})
    print("ros-ish links:", links[:30])
    e = ecr_summary(page)
    if e:
        print("ecrData:", e)
    return page


def main():
    fp_seen = set()
    for tag, url in START:
        page = summarize(tag, url)
        if tag.startswith("fp_") and page:
            for h in re.findall(r'(?:href|value)="([^"]+)"', page):
                u = urljoin(url, h)
                pu = urlparse(u)
                if pu.netloc == "www.fantasypros.com" and FP_ROS_RE.match(pu.path):
                    fp_seen.add(f"https://www.fantasypros.com{pu.path}")
    print("\n=== consensus ROS pages linked on the consensus site:", sorted(fp_seen))
    for u in sorted(fp_seen)[:16]:
        code, page = fetch(u)
        print(f"\n--- {u} status={code} bytes={len(page)}")
        print("ecrData:", ecr_summary(page) if code == 200 else None)


if __name__ == "__main__":
    main()
