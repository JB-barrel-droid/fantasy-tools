#!/usr/bin/env python3
"""JEG-1198 option C, round 7: raw shapes of the expert ROS pages; RotoBaller post body. Round 6: expert consensus cuts and each expert's own ROS list; RotoBaller.

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
    print("\n##### round 7: raw shapes for the expert pages")
    code, page = fetch(FP_START)
    tables = re.findall(r"<table\b.*?</table>", page, re.S | re.I)
    rows = re.findall(r"<tr\b.*?</tr>", tables[1], re.S | re.I) if len(tables) > 1 else []
    print("expert table header:", re.sub(r"\s+", " ", rows[0])[:600] if rows else None)
    print("expert row raw:", re.sub(r"\s+", " ", rows[1])[:900] if len(rows) > 1 else None)
    print("expert rows total:", len(rows) - 1)
    for scoring in ("HALF", "STD"):
        u = f"https://www.fantasypros.com/nfl/rankings/pat-fitzmaurice.php?type=ros&scoring={scoring}"
        c, pg = fetch(u)
        t = re.search(r"<title[^>]*>(.*?)</title>", pg, re.S | re.I)
        tabs = re.findall(r"<table\b.*?</table>", pg, re.S | re.I)
        trs = re.findall(r"<tr\b.*?</tr>", tabs[0], re.S | re.I) if tabs else []
        print(f"--- {u} status={c} title={text(t.group(1))[:140] if t else None} rows={len(trs) - 1}")
        for r in trs[:3]:
            print("  raw row:", re.sub(r"\s+", " ", r)[:700])
        for kw in ("Updated", "updated", "last_updated", "Last Updated"):
            for a2 in around(pg, kw, 80, 160, 2):
                if "2026" in a2 or "/20" in a2:
                    print(f"  [{kw}] {text(a2)[:220]}")
        for v in re.findall(r"var\s+([A-Za-z_]\w*)\s*=\s*[\[{]", pg)[:12]:
            print("  js var:", v)


def rotoballer():
    code, page = fetch(RB_ROS)
    for a2 in around(page, 'href="https://googl', 50, 300, 3):
        print("  [googl]", re.sub(r"\s+", " ", a2)[:350])
    m = re.search(r'id="post-217928".{0,6000}', page, re.S)
    print("  post body text:", text(m.group(0))[:1500] if m else None)


if __name__ == "__main__":
    for f in (fp, rotoballer):
        try:
            f()
        except Exception as e:  # keep going past one bad source
            print(f"!!! {f.__name__}: {type(e).__name__}: {e}")
