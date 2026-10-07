"""Open-Meteo game-day weather loader (free, keyless, no signup).

Fetches hourly forecasts for upcoming scheduled games at open-air or
retractable-roof venues (domes don't need weather), and stores the
kickoff-hour conditions in game_weather.

One API call covers all stadiums (comma-separated lat/lon batching).
16-day horizon; 10,000 calls/day free tier.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-football-signal/bin"))
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-mgmt/bin"))

import sbclient  # noqa: E402
import mgmt  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}


def main(days_ahead=10):
    games = mgmt.query(f"""
        select g.id, g.starts_at, g.venue, v.lat, v.lon, v.roof
        from games g join venues v on v.venue = g.venue
        where g.status='scheduled' and g.season=2026
          and g.starts_at > now()
          and g.starts_at < now() + interval '{days_ahead} days'
          and v.lat is not null
          and v.roof in ('open', 'retractable');
    """)
    if not games:
        print("no outdoor/retractable games in horizon")
        return {"games": 0}
    lats = ",".join(str(g["lat"]) for g in games)
    lons = ",".join(str(g["lon"]) for g in games)
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lats}&longitude={lons}"
           "&hourly=temperature_2m,precipitation,wind_speed_10m,snowfall"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph"
           "&precipitation_unit=inch&forecast_days=16&timezone=UTC")
    req = urllib.request.Request(url, headers=UA)
    data = json.load(urllib.request.urlopen(req, timeout=60))
    results = data if isinstance(data, list) else [data]
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for g, fc in zip(games, results):
        kickoff = datetime.fromisoformat(str(g["starts_at"]).replace("Z", "+00:00"))
        times = fc.get("hourly", {}).get("time", [])

        def _t(s):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        best = min(range(len(times)),
                   key=lambda i: abs((_t(times[i]) - kickoff).total_seconds()))
        h = fc["hourly"]
        fhour = _t(times[best]).isoformat()
        row = {
            "game_id": g["id"], "fetched_at": now,
            "temp_f": h["temperature_2m"][best],
            "wind_mph": h["wind_speed_10m"][best],
            "precip_in": h["precipitation"][best],
            "snowfall_in": h.get("snowfall", [0] * len(times))[best],
            "forecast_hour": fhour, "source": "open-meteo",
        }
        exists = sbclient.get(
            "game_weather",
            f"?game_id=eq.{g['id']}&forecast_hour=eq."
            f"{urllib.parse.quote(fhour, safe='')}&select=id")
        if exists:
            sbclient.patch("game_weather", row, f"?id=eq.{exists[0]['id']}")
        else:
            sbclient.post("game_weather", [row])
        n += 1
    print(f"weather: {n} games updated")
    return {"games": n}


if __name__ == "__main__":
    main()
