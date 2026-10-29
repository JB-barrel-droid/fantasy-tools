#!/usr/bin/env python3
"""JEG-1198 option C, round 5: look closer at what round 4 found.

Research only, run on a GitHub runner. Jeremy, 2026-10-29: "try fantasylife,
footballguys, rotoballer, roto street journal, and multiple cuts of the fantasypros
data". Round 4 showed: the expert-consensus ROS page lists its experts with links;
RotoBaller's ROS page names its own ranking endpoint; Fantasy Life fills its table
from page data. This round prints the context around those, follows the expert links
and the RotoBaller endpoint the page itself names (same site, no sign-in), and
summarizes what each returns. Prints summaries, never whole pages.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import subprocess
from urllib.parse import urljoin, urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
FP_START = "https://www.fantasypros.com/nfl/rankings/?type=ros"
FP_HALF = "https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php"
RB_ROS = "https://www.rotoballer.com/fantasy-football-rankings-rest-of-season-ros"
FL_ROS = "https://www.fantasylife.com/fantasy-football-rankings/rest-of-season"


def fetch(url, accept=None):
    cmd = ["curl", "-sS", "-L", "--compressed", "-o", "-", "-w", "\n%{http_code}", "-A", UA,
           "-H", "Accept-Language: en-US,en;q=0.9", "--max-time", "45"]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    p = subprocess.run(cmd + [url], capture_output=True, text=True, errors="replace")
    body, _, code = p.stdout.rpartition("\n")
    try:
        return int(code), body
    except ValueError:
        return None, p.stderr[:300]


def text(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def around(page, needle, before=200, after=400, n=3):
    out, i = [], 0
    while len(out) < n:
        i = page.find(needle, i)
        if i < 0:
            break
        out.append(re.sub(r"\s+", " ", page[max(0, i - before):i + after]))
        i += len(needle)
    return out


def json_var(page, var):
    m = re.search(r"var\s+" + var + r"\s*=\s*", page)
    if not m:
        return None
    try:
        return json.JSONDecoder().raw_decode(page[m.end():])[0]
    except ValueError as e:
        return f"parse error {e}"


def ecr_summary(page):
    d = json_var(page, "ecrData")
    if not isinstance(d, dict):
        return d
    players = d.get("players") or []
    pos = {}
    for p in players:
        pos[p.get("player_position_id")] = pos.get(p.get("player_position_id"), 0) + 1
    return {k: d.get(k) for k in ("ranking_type_name", "scoring", "position_id", "total_experts",
                                  "last_updated")} | {"players": len(players), "by_pos": pos,
            "first": [(p.get("rank_ecr"), p.get("player_name")) for p in players[:3]]}


def fp():
    print("\n##### expert consensus: expert list and cuts")
    code, page = fetch(FP_START)
    print("start status", code, len(page))
    tables = re.findall(r"<table\b.*?</table>", page, re.S | re.I)
    links = []
    if len(tables) > 1:
        for row in re.findall(r"<tr\b.*?</tr>", tables[1], re.S | re.I)[:12]:
            hrefs = re.findall(r'href="([^"]+)"', row)
            print("  expert row:", text(row)[:110], "| hrefs:", hrefs[:3])
            links += [urljoin(FP_START, h) for h in hrefs if "rankings" in h or "experts" in h]
    code, half = fetch(FP_HALF)
    eg = json_var(half, "expertGroupsData")
    print("expertGroupsData type:", type(eg).__name__,
          (list(eg)[:20] if isinstance(eg, dict) else (eg[:3] if isinstance(eg, list) else eg)))
    sd = json_var(half, "seasonData")
    print("seasonData:", str(sd)[:300])
    for s in sorted(set(re.findall(r"ros-[a-z0-9-]+\.php", half)))[:40]:
        print("  ros page named in the page:", s)
    for s in sorted(set(re.findall(r'(?:scoring|filter|type)=[A-Za-z_-]+', half)))[:30]:
        print("  query option named:", s)
    seen = set()
    for u in links:
        pu = urlparse(u)
        if pu.netloc != "www.fantasypros.com" or u in seen:
            continue
        seen.add(u)
        if len(seen) > 6:
            break
        c, pg = fetch(u)
        t = re.search(r"<title[^>]*>(.*?)</title>", pg, re.S | re.I)
        tabs = re.findall(r"<table\b.*?</table>", pg, re.S | re.I)
        rows = [text(r)[:80] for t2 in tabs[:1] for r in re.findall(r"<tr\b.*?</tr>", t2, re.S | re.I)[:4]]
        gate = sorted({m.group(0).lower() for m in re.finditer(r"(?i)premium|sign ?in|upgrade|locked|subscribe", pg)})[:6]
        print(f"\n--- expert link {u} status={c} bytes={len(pg)}\n  title: {text(t.group(1))[:120] if t else None}"
              f"\n  ecrData: {ecr_summary(pg)}\n  tables={len(tabs)} rows={rows}\n  gate: {gate}")


def rotoballer():
    print("\n##### RotoBaller ROS page")
    code, page = fetch(RB_ROS)
    print("status", code, len(page))
    for needle in ("get_nfl_ranking", "spreadsheet", "Rufe", "Updated", "rest-of-season"):
        for a in around(page, needle, 250, 450, 2):
            print(f"  [{needle}] ...{a}...")
    calls = sorted(set(re.findall(r"/api/rbapps/nfl/get_nfl_ranking\.php\?pos=[^\"'&\s]*(?:&[^\"'\s]*)?", page)))
    print("endpoint forms named:", calls[:10])
    params = sorted(set(re.findall(r"get_nfl_ranking\.php\?pos=['\"]?\s*\+?\s*([A-Za-z_]+)", page)))
    print("pos param expressions:", params[:10])
    for pos in ("Overall", "QB", "RB"):
        u = f"https://www.rotoballer.com/api/rbapps/nfl/get_nfl_ranking.php?pos={pos}"
        c, body = fetch(u, "application/json")
        print(f"\n--- {u} status={c} bytes={len(body)}\n  head: {re.sub(r'\s+', ' ', body[:500])}")


def fantasylife():
    print("\n##### Fantasy Life ROS page")
    code, page = fetch(FL_ROS)
    chunk = "".join(re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S)).replace('\\"', '"')
    print("status", code, "flight bytes", len(chunk))
    for needle in ("consensus", "Consensus", "ranking", "api.", "https://", "rest-of-season", "ros"):
        for a in around(chunk, needle, 120, 260, 2):
            print(f"  [{needle}] ...{a}...")


if __name__ == "__main__":
    for f in (fp, rotoballer, fantasylife):
        try:
            f()
        except Exception as e:  # keep going past one bad source
            print(f"!!! {f.__name__}: {type(e).__name__}: {e}")
