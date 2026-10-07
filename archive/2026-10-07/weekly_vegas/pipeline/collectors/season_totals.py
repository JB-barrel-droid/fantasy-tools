"""Season-long NFL player totals collector: DraftKings Player Futures +
FanDuel Regular Season markets -> raw JSON snapshots + Supabase
``vegas_season_totals``.

Feeds the Vegas-based full-season VORP engine. Free sources only: both
books expose keyless unofficial JSON endpoints. No credentials, no sign-in.

DraftKings:
  base  https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1
  NFL league 88808, category 1759 ("Player Futures"). Sub-category IDs are
  RE-KEYED BY DRAFTKINGS EVERY SEASON, so they are discovered at runtime
  from the category response and matched by name -- never hardcoded.
FanDuel:
  https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page
  ?page=CUSTOM&customPageId=nfl&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx
  (FD's own public web-app key, embedded in their site JS). One request
  returns every posted "Regular Season YYYY-YY" market.

Akamai TLS fingerprinting blocks plain ``requests`` on both hosts, so all
HTTP goes through ``curl_cffi`` (impersonate chrome110).

Requests per snapshot: 1 DK category + ~8 DK subcategories + 1 FD ~= 10.

Raw snapshots: data/season_totals/{draftkings|fanduel}/{YYYY-MM-DD}/
Supabase load (--load): rows are idempotent per (snapshot_date, book) --
existing rows for that date+book are deleted first, then re-inserted.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))

from engine.canonical_players import (  # noqa: E402
    load_registry, norm_plain, resolve_skill)

DK_API_BASE = ("https://sportsbook-nash.draftkings.com"
               "/api/sportscontent/dkusoh/v1")
DK_LEAGUE_ID = 88808
DK_CATEGORY_ID = 1759  # "Player Futures" (stable category; sub-IDs re-key yearly)

FD_URL = ("https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
          "?page=CUSTOM&customPageId=nfl&pbHorizontal=false"
          "&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York")

# DK subcategory display name -> canonical market key (matched at runtime).
DK_SUBCAT_TO_MARKET = {
    "Passing Yards": "season_pass_yds",
    "Passing TDs": "season_pass_tds",
    "Rushing Yards": "season_rush_yds",
    "Rushing TDs": "season_rush_tds",
    "Receiving Yards": "season_rec_yds",
    "Receiving TDs": "season_rec_tds",
    "Receptions": "season_receptions",
    "Sacks": "season_sacks",  # defensive; kept in raw, excluded from DB load
}
# Markets loaded into vegas_season_totals (fantasy-relevant only).
DB_MARKETS = {m for m in DK_SUBCAT_TO_MARKET.values() if m != "season_sacks"}

FD_STAT_TO_MARKET = {
    "Passing Yards": "season_pass_yds",
    "Passing TDs": "season_pass_tds",
    "Rushing Yards": "season_rush_yds",
    "Rushing TDs": "season_rush_tds",
    "Receiving Yards": "season_rec_yds",
    "Receiving TDs": "season_rec_tds",
    "Receptions": "season_receptions",
}

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "season_totals")
REQUEST_DELAY_S = 1.0

_EVENT_NAME_RE = re.compile(r"^NFL\s+(\d{4})/\d{2}\s*-\s*(.+)$")
_LABEL_LINE_RE = re.compile(r"^(Over|Under)\s+([\d,]+(?:\.\d+)?)$")
_FD_MARKET_RE = re.compile(
    r"^(?P<player>.+?)\s+Regular Season\s+(?P<stat>Passing Yards|Passing TDs|"
    r"Rushing Yards|Rushing TDs|Receiving Yards|Receiving TDs|Receptions)"
    r"\s+(?P<season>\d{4})-\d{2}$")
_FD_RUNNER_RE = re.compile(r"\b(Over|Under)\s+([\d,]+(?:\.\d+)?)$")

# NOTE (2026-09-18): the private ALIASES table that lived here
# (hollywood->marquise, kenny->kenneth, scotty->scott, cam->cameron) is deleted.
# Nickname expansion now lives in the shared NICKNAMES table
# (lottery/bin/identity.py), applied by engine.canonical_players at identity
# time. Labels below use norm_plain (no nickname expansion) — the legacy
# player_norm label convention that name-keyed consumers already join on.


def _now():
    return datetime.now(timezone.utc)


def _session():
    from curl_cffi import requests as cr
    return cr.Session(impersonate="chrome110")


def _get(session, url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_american_odds(display):
    """DK renders negative odds with U+2212; FD gives ints already."""
    if display is None:
        return None
    if isinstance(display, (int, float)):
        return int(display)
    cleaned = str(display).replace("\u2212", "-").replace("+", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return None


# ------------------------------------------------------------ DraftKings
def dk_discover_subcategories(session):
    """Return {canonical_market: subcat_id} discovered live from the
    category response. Raises if an expected subcategory name is missing
    (fail-visible: DK re-keys or renames these)."""
    url = (f"{DK_API_BASE}/leagues/{DK_LEAGUE_ID}"
           f"/categories/{DK_CATEGORY_ID}")
    data = _get(session, url)
    found = {}
    for s in data.get("subcategories", []):
        if s.get("categoryId") != DK_CATEGORY_ID:
            continue
        key = DK_SUBCAT_TO_MARKET.get(s.get("name"))
        if key:
            found[key] = s["id"]
    missing = [m for m in DK_SUBCAT_TO_MARKET.values() if m not in found]
    if missing:
        raise RuntimeError(
            f"DK Player Futures missing expected subcategories: {missing}. "
            "DK likely re-keyed/renamed them; inspect the category response.")
    return found


def dk_parse_subcategory(data, market_key, snapshot_ts):
    events = {e.get("id"): e for e in data.get("events", [])}
    by_market = {}
    for sel in data.get("selections", []):
        if sel.get("outcomeType") not in ("Over", "Under"):
            continue
        by_market.setdefault(sel.get("marketId"), {})[sel["outcomeType"]] = sel
    rows = []
    for market in data.get("markets", []):
        sides = by_market.get(market.get("id"))
        if not sides:
            continue
        event = events.get(market.get("eventId"), {})
        m = _EVENT_NAME_RE.match(event.get("name", "") or "")
        if not m:
            print(f"  warn: unparseable DK event name {event.get('name')!r}; skipping")
            continue
        season, player = int(m.group(1)), m.group(2).strip()
        over, under = sides.get("Over", {}), sides.get("Under", {})
        line = None
        for lbl in (over.get("label", ""), under.get("label", "")):
            lm = _LABEL_LINE_RE.match((lbl or "").strip())
            if lm:
                line = float(lm.group(2).replace(",", ""))
                break
        if line is None:
            print(f"  warn: no line for DK market {market.get('name')!r}; skipping")
            continue
        team = None
        for p in event.get("participants", []) or []:
            short = (p.get("metadata") or {}).get("shortName")
            if short:
                team = short
                break
        rows.append({
            "snapshot_ts": snapshot_ts,
            "book": "draftkings",
            "market": market_key,
            "market_name": market.get("name", ""),
            "player_name": player,
            "player_norm": norm_plain(player),
            "team": team,
            "line": line,
            "over_odds": parse_american_odds(
                (over.get("displayOdds") or {}).get("american")),
            "under_odds": parse_american_odds(
                (under.get("displayOdds") or {}).get("american")),
            "season": season,
        })
    return rows


def dk_snapshot(session, date_str):
    out_dir = os.path.join(BASE_DIR, "draftkings", date_str)
    os.makedirs(out_dir, exist_ok=True)
    snapshot_ts = _now().isoformat()
    subcats = dk_discover_subcategories(session)
    print(f"DK Player Futures subcategories discovered: "
          f"{ {k: v for k, v in sorted(subcats.items())} }")
    all_rows = []
    for market_key, sub_id in sorted(subcats.items(), key=lambda kv: kv[1]):
        url = (f"{DK_API_BASE}/leagues/{DK_LEAGUE_ID}"
               f"/categories/{DK_CATEGORY_ID}/subcategories/{sub_id}")
        data = _get(session, url)
        raw_path = os.path.join(out_dir, f"subcategory_{sub_id}_{market_key}.json")
        json.dump(data, open(raw_path, "w"))
        rows = dk_parse_subcategory(data, market_key, snapshot_ts)
        print(f"  {market_key}: {len(data.get('markets', []))} markets -> "
              f"{len(rows)} rows (raw: {os.path.basename(raw_path)})")
        all_rows.extend(rows)
        time.sleep(REQUEST_DELAY_S)
    return all_rows


# ------------------------------------------------------------- FanDuel
def fd_parse_page(data, snapshot_ts):
    markets = (data.get("attachments") or {}).get("markets") or {}
    rows = []
    for market in markets.values():
        m = _FD_MARKET_RE.match(market.get("marketName", "") or "")
        if not m:
            continue
        market_key = FD_STAT_TO_MARKET[m.group("stat")]
        sides, line = {}, None
        for runner in market.get("runners", []) or []:
            rm = _FD_RUNNER_RE.search(runner.get("runnerName", "") or "")
            if not rm:
                continue
            sides[rm.group(1)] = runner
            if line is None:
                line = float(rm.group(2).replace(",", ""))
        if line is None:
            continue

        def _price(runner):
            if not runner:
                return None
            odds = ((runner.get("winRunnerOdds") or {})
                    .get("americanDisplayOdds", {}).get("americanOdds"))
            return parse_american_odds(odds)

        player = m.group("player").strip()
        rows.append({
            "snapshot_ts": snapshot_ts,
            "book": "fanduel",
            "market": market_key,
            "market_name": market.get("marketName", ""),
            "player_name": player,
            "player_norm": norm_plain(player),
            "team": None,
            "line": line,
            "over_odds": _price(sides.get("Over")),
            "under_odds": _price(sides.get("Under")),
            "season": int(m.group("season")),
        })
    return rows


def fd_snapshot(session, date_str):
    out_dir = os.path.join(BASE_DIR, "fanduel", date_str)
    os.makedirs(out_dir, exist_ok=True)
    snapshot_ts = _now().isoformat()
    data = _get(session, FD_URL)
    raw_path = os.path.join(out_dir, "content_managed_page.json")
    json.dump(data, open(raw_path, "w"))
    rows = fd_parse_page(data, snapshot_ts)
    print(f"FD regular-season markets: {len(rows)} rows "
          f"(raw: {os.path.basename(raw_path)})")
    return rows


# ------------------------------------------------------------- Supabase
def load_to_supabase(rows, date_str):
    import sbclient
    # Canonical identity: resolve each book name once against the players
    # table -> numeric player_key (uuid kept as transitional player_id).
    # Books carry no position, so the position-blind skill sweep is used;
    # ambiguous/unmatched names resolve to NULL, never a guess.
    reg = load_registry()
    db_rows = []
    for r in rows:
        if r["market"] not in DB_MARKETS:
            continue
        key = resolve_skill(r["player_name"], registry=reg)
        db_rows.append({
            "snapshot_date": date_str,
            "snapshot_ts": r["snapshot_ts"],
            "book": r["book"],
            "market": r["market"],
            "market_name": r["market_name"],
            "player_name": r["player_name"],
            "player_norm": r["player_norm"],
            "player_id": reg.by_key[key]["uuid"] if key else None,
            "player_key": key,
            "team": r["team"],
            "line": r["line"],
            "over_odds": r["over_odds"],
            "under_odds": r["under_odds"],
            "season": r["season"],
        })
    unmatched = sum(1 for r in db_rows if not r["player_id"])
    if unmatched:
        print(f"  note: {unmatched}/{len(db_rows)} rows did not match a players row "
              f"(player_id NULL)")
    for book in sorted({r["book"] for r in db_rows}):
        sbclient.delete("vegas_season_totals",
                        f"?snapshot_date=eq.{date_str}&book=eq.{book}")
    for i in range(0, len(db_rows), 200):
        sbclient.post("vegas_season_totals", db_rows[i:i + 200])
    return len(db_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=_now().strftime("%Y-%m-%d"),
                    help="snapshot date (default: today UTC)")
    ap.add_argument("--books", default="draftkings,fanduel")
    ap.add_argument("--load", action="store_true",
                    help="upsert parsed rows into vegas_season_totals")
    ap.add_argument("--raw-only", action="store_true",
                    help="fetch + write raw snapshots, skip parsing summary")
    args = ap.parse_args()

    session = _session()
    all_rows = []
    for book in [b.strip() for b in args.books.split(",") if b.strip()]:
        if book == "draftkings":
            all_rows.extend(dk_snapshot(session, args.date))
        elif book == "fanduel":
            all_rows.extend(fd_snapshot(session, args.date))
        else:
            raise SystemExit(f"unknown book: {book}")

    parsed_path = os.path.join(
        BASE_DIR, f"parsed_{args.date}_{'+'.join(sorted(set(r['book'] for r in all_rows)))}.json")
    json.dump(all_rows, open(parsed_path, "w"), indent=1)
    print(f"parsed {len(all_rows)} rows -> {parsed_path}")

    if args.load:
        n = load_to_supabase(all_rows, args.date)
        print(f"loaded {n} rows into vegas_season_totals for {args.date}")


if __name__ == "__main__":
    main()
