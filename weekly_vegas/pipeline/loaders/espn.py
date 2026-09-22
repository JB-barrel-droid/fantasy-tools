"""ESPN public API loader (free, no auth).

NOTE (2026-09-11): site.api.espn.com returns 403 "Access Denied" from our
egress (Akamai edge block on the datacenter IP range) even with a browser
UA. A research pass from a different egress got 200s, so the block may be
IP-specific or transient. Keep this loader for retry/manual runs; the
Sleeper loader covers injuries (status/body part/recency) in the meantime.

  injuries  -> injuries table (status, body part, report timestamp,
               reporter comments). Covers the injuries + news-absorption
               foundation requirement. Poll Wed/Fri around practice reports.
  scoreboard -> games.status final updates + final scores into
               games.metadata (drives calibration finality; timely vs the
               weekly nflverse refresh).
  news      -> printed digest only (small wire); persisted to data/espn_news.json.

Usage: python3 loaders/espn.py [--skip-injuries] [--skip-scoreboard] [--skip-news]
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
DATA = os.path.join(BASE, "data")
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
import sbclient  # noqa: E402
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-mgmt/bin"))
import mgmt  # noqa: E402
from engine.snapshot import norm, load_players  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"}
API = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"


def get(path):
    req = urllib.request.Request(API + path, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def load_injuries():
    data = get("/injuries")
    by_name, _, _ = load_players()
    teams = {t["abbreviation"]: t["id"] for t in sbclient.get_all("teams")}
    n_upd = n_new = 0
    for team in data.get("teams", []):
        tabbr = team.get("abbreviation")
        for inj in team.get("injuries", []):
            ath = inj.get("athlete", {}) or {}
            name = ath.get("displayName", "")
            espn_id = None
            for lnk in (ath.get("links") or {}).get("web", {}).get("href", ""):
                pass
            # espn id from playercard href
            href = ((ath.get("links") or {}).get("web") or {}).get("href", "")
            if "/id/" in href:
                espn_id = href.rstrip("/").split("/id/")[-1].split("/")[0]
            pid = None
            key = norm(name)
            if key in by_name:
                pid = by_name[key]["id"]
            row = {
                "player_id": pid, "player_name": name, "team": tabbr,
                "position": inj.get("position", {}).get("abbreviation")
                            if isinstance(inj.get("position"), dict)
                            else inj.get("position"),
                "status": inj.get("status"), "body_part": inj.get("type"),
                "report_date": inj.get("date"),
                "short_comment": inj.get("shortComment"),
                "long_comment": inj.get("longComment"),
                "source": (inj.get("source") or {}).get("description")
                          if isinstance(inj.get("source"), dict)
                          else inj.get("source"),
                "espn_id": espn_id, "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            # upsert on (player_name, team)
            exists = sbclient.get(
                "injuries",
                f"?player_name=eq.{name.replace(' ', '%20')}&team=eq.{tabbr}&select=id")
            if exists:
                rid = exists[0]["id"]
                sbclient.patch("injuries", row, f"?id=eq.{rid}")
                n_upd += 1
            else:
                sbclient.post("injuries", [row])
                n_new += 1
    return {"updated": n_upd, "new": n_new}


def load_scoreboard(week=None):
    params = f"?week={week}" if week else ""
    data = get("/scoreboard" + params)
    n_final = 0
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        st = ((comp.get("status") or {}).get("type") or {}).get("name", "")
        if st != "STATUS_FINAL":
            continue
        scores = {}
        for c in comp.get("competitors", []):
            abbr = (c.get("team") or {}).get("abbreviation")
            scores[abbr] = c.get("score")
        # match to our games by team abbreviations + week
        wk = (ev.get("week") or {}).get("number")
        home = next((c.get("team", {}).get("abbreviation")
                     for c in comp.get("competitors", [])
                     if c.get("homeAway") == "home"), None)
        away = next((c.get("team", {}).get("abbreviation")
                     for c in comp.get("competitors", [])
                     if c.get("homeAway") == "away"), None)
        if not (home and away and wk):
            continue
        g = mgmt.query(f"""select g.id, g.status, g.metadata from games g
            join teams h on h.id=g.home_team_id
            join teams a on a.id=g.away_team_id
            where h.abbreviation='{home}' and a.abbreviation='{away}'
              and g.week={int(wk)} and g.season=2026 limit 1;""")
        if not g:
            continue
        g = g[0]
        md = g["metadata"] or {}
        md["espn_final"] = {"home": home, "away": away,
                            "home_score": scores.get(home),
                            "away_score": scores.get(away)}
        mgmt.query(f"""UPDATE games SET status='final',
            metadata='{json.dumps(md).replace("'", "''")}'::jsonb
            WHERE id='{g["id"]}';""")
        n_final += 1
    return {"games_marked_final": n_final}


def load_news():
    data = get("/news")
    arts = [{"headline": a.get("headline"), "published": a.get("published"),
             "byline": (a.get("byline") or ""),
             "description": (a.get("description") or "")[:300]}
            for a in data.get("articles", [])]
    open(os.path.join(DATA, "espn_news.json"), "w").write(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(),
                    "articles": arts}, indent=1))
    return {"articles": len(arts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-injuries", action="store_true")
    ap.add_argument("--skip-scoreboard", action="store_true")
    ap.add_argument("--skip-news", action="store_true")
    ap.add_argument("--week", type=int, default=None)
    a = ap.parse_args()
    if not a.skip_injuries:
        print("injuries:", load_injuries())
    if not a.skip_scoreboard:
        print("scoreboard:", load_scoreboard(a.week))
    if not a.skip_news:
        print("news:", load_news())


if __name__ == "__main__":
    main()
