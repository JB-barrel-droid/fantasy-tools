"""DraftKings main-slate salary loader (free, no auth — public endpoints).

Two-step flow:
  1. lobby/getcontests?sport=NFL -> find the main-slate draftGroupId
     (Millionaire contest, Classic gameType, soonest upcoming start)
  2. api.draftkings.com/draftgroups/v1/draftgroups/{dg}/draftables

Salaries are a second market signal alongside Vegas-implied points:
DK salary cap $50,000; compare salary-vs-ECR disagreement the same way.

Dedupe on playerDkId (one row per eligible roster slot in the payload).
FanDuel has no public endpoint — DK only.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-football-signal/bin"))
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-mgmt/bin"))

import sbclient  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36",
      "Accept": "application/json",
      "Referer": "https://www.draftkings.com/",
      "Origin": "https://www.draftkings.com"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=60))


def find_main_slate():
    d = get("https://www.draftkings.com/lobby/getcontests?sport=NFL")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cands = []
    for c in d.get("Contests", []):
        name = c.get("n", "")
        if "millionaire" not in name.lower():
            continue
        if c.get("gameType") != "Classic":
            continue
        m = re.search(r"/Date\((\d+)\)/", c.get("sd", ""))
        if not m:
            continue
        start_ms = int(m.group(1))
        if start_ms < now_ms - 24 * 3600 * 1000:
            continue  # already started
        cands.append((start_ms, c.get("dg"), name))
    if not cands:
        raise RuntimeError("no upcoming Millionaire main slate found")
    cands.sort()
    return str(cands[0][1]), cands[0][2]


def main(season=2026, week=None):
    dg, name = find_main_slate()
    print(f"main slate: dg={dg} ({name})", flush=True)
    d = get(f"https://api.draftkings.com/draftgroups/v1/draftgroups/{dg}/draftables")
    draftables = d.get("draftables", [])

    # Canonical identity (2026-09-18): DraftKings names resolve through
    # the players table to a numeric player_key via engine/canonical_players,
    # using DK's own position for disambiguation. Ambiguous/unmatched names
    # return None (fail-closed) — the old first-candidate fallback is gone.
    from engine.canonical_players import load_registry, resolve
    _reg = load_registry()

    def match_player(disp, dk_pos):
        key = resolve(disp, position=(dk_pos or "").upper() or None,
                      registry=_reg)
        if key is None:
            return None, None
        entry = _reg.by_key.get(key)
        return entry.get("uuid"), key

    seen, rows = set(), []
    now = datetime.now(timezone.utc).isoformat()
    for p in draftables:
        dkid = str(p.get("playerDkId"))
        if dkid in seen:
            continue
        seen.add(dkid)
        disp = p.get("displayName") or ""
        team = (p.get("teamAbbreviation") or "").upper()
        _uuid, _key = match_player(disp, p.get("position"))
        rows.append({
            "player_id": _uuid, "player_key": _key, "player_name": disp,
            "position": p.get("position"), "team": team or None,
            "season": season, "week": week, "slate_id": dg,
            "salary": p.get("salary"), "dk_player_id": dkid,
            "status": p.get("status"), "fetched_at": now,
        })
    from sbclient import _request
    n = 0
    for i in range(0, len(rows), 200):
        chunk = rows[i:i + 200]
        _request("POST", "/rest/v1/dfs_salaries", body=chunk,
                 params="?on_conflict=season,week,slate_id,dk_player_id",
                 prefer="resolution=merge-duplicates")
        n += len(chunk)
    matched = sum(1 for r in rows if r["player_id"])
    print(f"dk salaries: {len(rows)} players ({matched} matched), "
          f"{n} upserted", flush=True)
    return {"players": len(rows), "matched": matched,
            "upserted": n, "slate": dg}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    if a.week is None:
        sys.path.insert(0, BASE)
        from engine.week import current_week
        a.week = current_week(a.season)
    main(season=a.season, week=a.week)
