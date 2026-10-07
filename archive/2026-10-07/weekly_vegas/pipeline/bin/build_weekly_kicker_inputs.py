#!/usr/bin/env python3
"""Weekly kicker-model input builder.

Assembles everything project_kicker() needs for every team in a given week:
  team implied points (caller-supplied: Odds API spreads/totals or manual
  lines), spread, dome/outdoor, Open-Meteo kickoff-hour weather for outdoor
  venues, season-to-date red-zone TD rates (offense + opponent defense), and
  the team's primary kicker with prior band accuracy for shrinkage.

Free-only: nflverse (schedules + pbp), Open-Meteo (keyless). Implied totals
are NOT fetched here -- pass them in (see --implied-json) so quota-guarded
Odds API pulls stay in their own collector.

Usage:
  build_weekly_kicker_inputs.py --week 3 --implied-json implied_w3.json
      [--no-weather] [--out inputs_w3.json]
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/hatch/workspace/football-signal")
sys.path.insert(0, "/home/hatch/workspace/football-signal/engine")
sys.path.insert(0, "/home/hatch/workspace/football-signal/.venv/lib/python3.12/site-packages")

DATA_DIR = Path("/home/hatch/workspace/goals/football-signal-database-and-app/lottery/data")
ET = ZoneInfo("America/New_York")

# Primary venue per team: (lat, lon, dome). Dome = nflverse roof in
# {dome, closed} across 2024-2025 (retractable-roof stadiums counted as domes:
# weather is only fetched when the roof is open, which we cannot know pregame).
VENUES = {
    "ARI": (33.5276, -112.2626, True), "ATL": (33.7554, -84.4008, True),
    "BAL": (39.2780, -76.6227, False), "BUF": (42.7743, -78.7870, False),
    "CAR": (35.2258, -80.8529, False), "CHI": (41.8623, -87.6167, False),
    "CIN": (39.0955, -84.5161, False), "CLE": (41.5061, -81.6995, False),
    "DAL": (32.7473, -97.0945, True), "DEN": (39.7439, -105.0201, False),
    "DET": (42.3400, -83.0456, True), "GB": (44.5013, -88.0622, False),
    "HOU": (29.6847, -95.4107, True), "IND": (39.7601, -86.1639, True),
    "JAX": (30.3239, -81.6373, False), "KC": (39.0489, -94.4839, False),
    "LA": (33.9535, -118.3392, True), "LAC": (33.9535, -118.3392, True),
    "LV": (36.0908, -115.1839, True), "MIA": (25.9580, -80.2389, False),
    "MIN": (44.9739, -93.2581, True), "NE": (42.0909, -71.2643, False),
    "NO": (29.9509, -90.0811, True), "NYG": (40.8135, -74.0745, False),
    "NYJ": (40.8135, -74.0745, False), "PHI": (39.9008, -75.1675, False),
    "PIT": (40.4468, -80.0158, False), "SEA": (47.5952, -122.3316, False),
    "SF": (37.4030, -121.9698, False), "TB": (27.9759, -82.5033, False),
    "TEN": (36.1665, -86.7713, False), "WAS": (38.9076, -76.8645, False),
}
# International/neutral 2026 venues (all treated as outdoor unless nflverse
# says otherwise on the schedule row).
NEUTRAL_VENUES = {
    "Bernabeu": (40.4531, -3.6883), "Maracana Stadium": (-22.9122, -43.2302),
    "Wembley Stadium": (51.5560, -0.2795),
    "Tottenham Hotspur Stadium": (51.6043, -0.0664),
    "Stade de France": (48.9245, 2.3602),
    "Melbourne Cricket Ground": (-37.8200, 144.9834),
    "FC Bayern Munich Stadium": (48.2188, 11.6247),
    "Estadio Banorte": (19.3029, -99.1505),
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}


def get_week_games(week, season=2026):
    """Games for the week from the local schedules file. Returns list of
    dicts with home/away teams, kickoff (ET), stadium, dome."""
    import polars as pl
    sched = pl.read_parquet(DATA_DIR / "schedules.parquet").filter(
        (pl.col("season") == season) & (pl.col("week") == week)
        & (pl.col("game_type") == "REG"))
    games = []
    for r in sched.iter_rows(named=True):
        kickoff = datetime.strptime(
            f"{r['gameday']} {r['gametime']}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        games.append({
            "home": r["home_team"], "away": r["away_team"],
            "kickoff_et": kickoff.isoformat(), "stadium": r["stadium"],
            "roof": r["roof"],
        })
    return games


def venue_for(team, stadium, roof):
    """(lat, lon, dome) for a game: neutral-stadium coords when the game is
    at a neutral venue, else the home team's primary venue."""
    if stadium in NEUTRAL_VENUES:
        lat, lon = NEUTRAL_VENUES[stadium]
        return lat, lon, roof in ("dome", "closed")
    lat, lon, dome = VENUES[team]
    if roof in ("dome", "closed", "outdoors"):
        dome = roof in ("dome", "closed")
    return lat, lon, dome


def fetch_weather(points):
    """Open-Meteo batch fetch. points: list of (lat, lon, kickoff_iso).
    Returns list of {temp_f, wind_mph, precip_prob} at the kickoff hour."""
    lats = ",".join(str(p[0]) for p in points)
    lons = ",".join(str(p[1]) for p in points)
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lats}&longitude={lons}"
           "&hourly=temperature_2m,precipitation_probability,wind_speed_10m"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph"
           "&forecast_days=16&timezone=America%2FNew_York")
    req = urllib.request.Request(url, headers=UA)
    data = json.load(urllib.request.urlopen(req, timeout=60))
    results = data if isinstance(data, list) else [data]
    out = []
    for (lat, lon, kickoff_iso), fc in zip(points, results):
        kickoff = datetime.fromisoformat(kickoff_iso)
        times = fc["hourly"]["time"]
        best = min(range(len(times)),
                   key=lambda i: abs((datetime.fromisoformat(times[i]).replace(tzinfo=ET)
                                      - kickoff).total_seconds()))
        h = fc["hourly"]
        out.append({
            "temp_f": round(h["temperature_2m"][best], 1),
            "wind_mph": round(h["wind_speed_10m"][best], 1),
            "precip_prob": round(h["precipitation_probability"][best] / 100, 2),
        })
    return out


def red_zone_rates(season=2026, through_week=None):
    """Season-to-date red-zone TD rate per team (offense) and allowed rate
    per team (defense), from pbp. Returns (off_rate, def_allowed)."""
    import polars as pl
    pbp = pl.read_parquet(DATA_DIR / f"pbp_{season}.parquet")
    if through_week:
        pbp = pbp.filter(pl.col("week") < through_week)
    drives = (
        pbp.filter(pl.col("posteam").is_not_null()
                   & pl.col("fixed_drive").is_not_null())
        .group_by(["fixed_drive", "posteam", "defteam"])
        .agg([
            pl.col("yardline_100").min().alias("min_yl"),
            ((pl.col("touchdown") == 1)
             & (pl.col("td_team") == pl.col("posteam"))).any().alias("off_td"),
        ])
        .filter(pl.col("min_yl") <= 20))
    off = drives.group_by("posteam").agg(
        (pl.col("off_td").sum() / pl.len()).alias("rz_td_rate"))
    deff = drives.group_by("defteam").agg(
        (pl.col("off_td").sum() / pl.len()).alias("rz_td_allowed"))
    return (dict(zip(off["posteam"], off["rz_td_rate"])),
            dict(zip(deff["defteam"], deff["rz_td_allowed"])))


def kicker_prior_accuracy(season=2026, through_week=None):
    """Each team's primary kicker (most FG attempts to date) with per-band
    makes/atts for shrunk_accuracy(). Returns {team: (name, makes, atts)}."""
    import polars as pl
    from kicker_model import band_of, BANDS
    pbp = pl.read_parquet(DATA_DIR / f"pbp_{season}.parquet")
    if through_week:
        pbp = pbp.filter(pl.col("week") < through_week)
    fg = (pbp.filter(pl.col("field_goal_attempt") == 1)
          .with_columns(pl.col("kick_distance").map_elements(
              band_of, return_dtype=pl.String).alias("band")))
    prim = (fg.group_by(["posteam", "kicker_player_name"])
            .agg(pl.len().alias("n")).sort("n", descending=True)
            .group_by("posteam").first())
    out = {}
    for r in prim.iter_rows(named=True):
        sub = fg.filter((pl.col("posteam") == r["posteam"])
                        & (pl.col("kicker_player_name") == r["kicker_player_name"]))
        makes = {b: sub.filter((pl.col("band") == b)
                               & (pl.col("field_goal_result") == "made")).height
                 for b in BANDS}
        atts = {b: sub.filter(pl.col("band") == b).height for b in BANDS}
        out[r["posteam"]] = (r["kicker_player_name"], makes, atts)
    return out


def build_inputs(week, implied_totals, spreads=None, season=2026,
                 fetch_weather_flag=True):
    """Assemble project_kicker() inputs for all 32 teams.

    implied_totals: {team: implied points}. spreads: {team: spread from the
    team's perspective (negative = underdog)}. Returns {team: kwargs dict}.
    """
    games = get_week_games(week, season)
    off_rz, def_rz = red_zone_rates(season, through_week=week)
    kickers = kicker_prior_accuracy(season, through_week=week)

    wx_points, wx_idx = [], {}
    meta = {}
    for g in games:
        for team, is_home in ((g["home"], True), (g["away"], False)):
            lat, lon, dome = venue_for(g["home"], g["stadium"], g["roof"])
            meta[team] = {"dome": dome, "lat": lat, "lon": lon,
                          "kickoff": g["kickoff_et"], "opp": g["away"] if is_home else g["home"]}
            if not dome and fetch_weather_flag:
                wx_idx[team] = len(wx_points)
                wx_points.append((lat, lon, g["kickoff_et"]))
    wx = fetch_weather(wx_points) if wx_points else []
    inputs = {}
    for team, m in meta.items():
        w = wx[wx_idx[team]] if team in wx_idx else {"temp_f": None,
                                                    "wind_mph": None,
                                                    "precip_prob": None}
        km = kickers.get(team, (None, {}, {}))
        inputs[team] = {
            "team_implied": implied_totals[team],
            "spread": (spreads or {}).get(team),
            "rz_td_rate": off_rz.get(team),
            "opp_rz_td_allowed": def_rz.get(m["opp"]),
            "kicker_makes": km[1], "kicker_atts": km[2],
            "kicker_name": km[0], "opp": m["opp"],
            "temp_f": w["temp_f"], "wind_mph": w["wind_mph"],
            "precip_prob": w["precip_prob"], "dome": m["dome"],
            "week": week,
        }
    return inputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--implied-json", required=True,
                    help="JSON {team: implied points}; optional 'spreads' key")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-weather", action="store_true")
    args = ap.parse_args()
    raw = json.load(open(args.implied_json))
    implied = raw["implied"] if "implied" in raw else raw
    spreads = raw.get("spreads")
    try:
        inputs = build_inputs(args.week, implied, spreads,
                              fetch_weather_flag=not args.no_weather)
    except Exception as e:
        print(f"input build failed: {e}", file=sys.stderr)
        sys.exit(1)
    out = args.out or f"engine/data/kicker_inputs_w{args.week}.json"
    json.dump(inputs, open(out, "w"), indent=1)
    wx_n = sum(1 for v in inputs.values() if v["temp_f"] is not None)
    print(f"wrote {len(inputs)} team inputs -> {out} (weather: {wx_n})")


if __name__ == "__main__":
    main()
