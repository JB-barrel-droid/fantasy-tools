#!/usr/bin/env python3
"""JEG-1198 option C, round 6: expert consensus cuts and each expert's own ROS list; RotoBaller.

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
    print("\n##### expert consensus: scoring and position cuts")
    for slug in ("ros-ppr-overall", "ros-overall", "ros-half-point-ppr-overall", "ros-qb", "ros-half-point-ppr-rb",
                 "ros-ppr-rb", "ros-rb", "ros-half-point-ppr-wr", "ros-half-point-ppr-te"):
        u = f"https://www.fantasypros.com/nfl/rankings/{slug}.php"
        c, pg = fetch(u)
        print(f"--- {slug} status={c} bytes={len(pg)} ecr={ecr_summary(pg) if c == 200 else None}")
    print("\n##### expert consensus: each expert's own ROS list")
    code, page = fetch(FP_START)
    tables = re.findall(r"<table\b.*?</table>", page, re.S | re.I)
    experts = []
    if len(tables) > 1:
        for row in re.findall(r"<tr\b.*?</tr>", tables[1], re.S | re.I):
            hrefs = [h.replace("&amp;", "&") for h in re.findall(r'href="([^"]+)"', row)]
            rk = [h for h in hrefs if h.startswith("/nfl/rankings/") and "type=ros" in h]
            if rk:
                experts.append((text(row)[:70], rk[0]))
    print(f"experts with a ROS list link: {len(experts)}")
    for label, h in experts[:12]:
        for scoring in ("HALF", "PPR"):
            u = urljoin(FP_START, h.replace("scoring=HALF", f"scoring={scoring}"))
            c, pg = fetch(u)
            tabs = re.findall(r"<table\b.*?</table>", pg, re.S | re.I)
            rows = re.findall(r"<tr\b.*?</tr>", tabs[0], re.S | re.I) if tabs else []
            body = [text(r) for r in rows[1:]]
            pos = {}
            for r in body:
                m = re.search(r"\b(QB|RB|WR|TE|K|DST)\d+\b", r)
                if m:
                    pos[m.group(1)] = pos.get(m.group(1), 0) + 1
            locked = sum(1 for r in rows if re.search(r"(?i)lock|blur|premium|upgrade", r))
            upd = re.search(r"(?i)updated[^<]{0,40}", pg)
            print(f"--- {label} [{scoring}] status={c} rows={len(body)} by_pos={pos} locked_rows={locked} "
                  f"updated={text(upd.group(0)) if upd else None} last={body[-1][:60] if body else None}")


def rotoballer():
    print("\n##### RotoBaller ROS page")
    code, page = fetch(RB_ROS)
    sel = re.search(r'<select[^>]+id="select_ranking".*?</select>', page, re.S)
    print("select_ranking:", re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', sel.group(0)) if sel else None)
    main = re.search(r'<div[^>]+class="[^"]*(?:entry|post-content|article)[^"]*".*', page, re.S)
    body = main.group(0) if main else page
    for needle in ("spreadsheet=", "ROS", "Rest of Season", "rankings-table", "tablepress", "data-src", "google.com/spreadsheets"):
        for a2 in around(body, needle, 150, 300, 2):
            print(f"  [{needle}] ...{text(a2)[:380]}...")
    types = re.findall(r'<option[^>]*value="([^"]*)"', sel.group(0)) if sel else []
    for t in types[:6]:
        u = f"https://www.rotoballer.com/api/rbapps/nfl/get_nfl_ranking.php?pos=RB&type={t}"
        c, b2 = fetch(u, "application/json")
        print(f"--- type={t!r} status={c} bytes={len(b2)} head={re.sub(r'\\s+', ' ', b2[:200])}")


if __name__ == "__main__":
    for f in (fp, rotoballer):
        try:
            f()
        except Exception as e:  # keep going past one bad source
            print(f"!!! {f.__name__}: {type(e).__name__}: {e}")
