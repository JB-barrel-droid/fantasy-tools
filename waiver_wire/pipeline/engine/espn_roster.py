"""ESPN-global fantasy ownership % (public, no-auth source of roster%).

Replaces the FantasyPros ROST% scrape as the pipeline's roster% source
(user-approved 2026-09-15: public, nameable, broader coverage). Covers
QB/RB/WR/TE plus K and team D/ST (K/DST added 2026-09-16).

Endpoint (no auth):
  https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/
      segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info
  + X-Fantasy-Filter header with a players filter, X-Fantasy-Source: kona.

player.ownership.percentOwned = % of ESPN leagues rostering the player
(ESPN-global, per ESPN's own %ROST definition - verified 2026-09-15).

Notes:
  - The fantasy.espn.com host 302-redirects API paths to the homepage;
    the lm-api-reads.fantasy.espn.com host is required.
  - Python urllib gets 403'd by ESPN's TLS fingerprinting: curl via
    subprocess (same pattern as the rest of the ESPN pulls here).
  - The players filter uses LINEUP slot ids, NOT defaultPositionId.
    Kicker is defaultPositionId 5 but lineup slot 17 (slot 5 is a WR
    lineup slot - filtering on 5 returns wide receivers). D/ST is 16
    in both. Verified live 2026-09-16.
  - ESPN rate-limits: ~2s spacing between page requests, paginate <=1000.
  - Dated cache: data/espn_roster_{YYYY-MM-DD}.json (ESPN display name ->
    percentOwned). D/ST rows are keyed under the ESPN display name
    ("Bills D/ST"); build_lookup() additionally keys them under the
    canonical entity key "dst:<abbr>" (lowercase, e.g. "dst:buf") so
    downstream K/DST matching never has to re-parse names. Pulls on
    cache miss; fail-closed on failure.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

LOT = str(Path(__file__).resolve().parent.parent)  # waiver_wire/pipeline
DATA = os.path.join(LOT, "data")

API = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/"
       "segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info")

POS_IDS = {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "K": 17, "DST": 16}
PAGE = 1000
SLEEP = 2.0

SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.IGNORECASE)

# ESPN display-name variants that don't normalize to our tracked names
ALIASES = {
    "cameron skattebo": "cam skattebo",
    "kenneth gainwell": "kenny gainwell",
    "marquise brown": "hollywood brown",
    "cameron ward": "cam ward",
}


# D/ST display names are "<Mascot> D/ST" (verified live 2026-09-16, all 32
# teams; the mascot may contain digits: "49ers D/ST"). Maps to the team
# abbreviations used by the FP K/DST pipeline (same set as the Supabase
# teams table and the Yahoo loader).
DST_RE = re.compile(r"^(?P<mascot>[A-Za-z0-9 ]+)\s+D/ST$", re.IGNORECASE)

MASCOT_ABBR = {
    "49ers": "SF", "bears": "CHI", "bengals": "CIN", "bills": "BUF",
    "broncos": "DEN", "browns": "CLE", "buccaneers": "TB", "cardinals": "ARI",
    "chargers": "LAC", "chiefs": "KC", "colts": "IND", "commanders": "WAS",
    "cowboys": "DAL", "dolphins": "MIA", "eagles": "PHI", "falcons": "ATL",
    "giants": "NYG", "jaguars": "JAX", "jets": "NYJ", "lions": "DET",
    "packers": "GB", "panthers": "CAR", "patriots": "NE", "raiders": "LV",
    "rams": "LA", "ravens": "BAL", "saints": "NO", "seahawks": "SEA",
    "steelers": "PIT", "texans": "HOU", "titans": "TEN", "vikings": "MIN",
}


def dst_entity_key(name):
    """Canonical D/ST lookup key "dst:<abbr>" (lowercase) for an ESPN
    display name like "Bills D/ST". Returns None for non-D/ST names.
    Raises on an unmapped mascot (fail-closed: a renamed D/ST must not
    silently drop out of the lookup)."""
    m = DST_RE.match((name or "").strip())
    if not m:
        return None
    abbr = MASCOT_ABBR.get(m.group("mascot").lower())
    if abbr is None:
        raise KeyError(f"unmapped D/ST mascot in ESPN name {name!r}")
    return "dst:" + abbr.lower()


def norm_name(name):
    """Aggressive normalization for roster matching: lowercase, strip
    periods/hyphens/apostrophes and generational suffixes, apply aliases."""
    n = (name or "").lower().replace(".", "").replace("-", "").replace("'", "").strip()
    n = SUFFIX_RE.sub("", n)
    n = re.sub(r"\s+", " ", n).strip()
    return ALIASES.get(n, n)


def score_norm(name):
    """score_v0-style normalization (keeps hyphens/apostrophes)."""
    s = (name or "").lower().strip()
    s = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", s)
    s = re.sub(r"[^a-z '\-]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_page(offset, limit=PAGE):
    filt = json.dumps({
        "players": {
            "filterSlotIds": {"value": list(POS_IDS.values())},
            "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
            "limit": limit,
            "offset": offset,
        }
    })
    cmd = [
        "curl", "-s", "--max-time", "60",
        "-H", "Accept: application/json",
        "-H", "X-Fantasy-Source: kona",
        "-H", "X-Fantasy-Filter: " + filt,
        "-H", "User-Agent: Mozilla/5.0",
        API,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"curl failed rc={out.returncode}: {out.stderr[:200]}")
    try:
        payload = json.loads(out.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"non-JSON response ({len(out.stdout)} bytes): {out.stdout[:200]}")
    players = payload.get("players", [])
    if not players and "messages" in payload:
        raise RuntimeError(f"API error payload: {json.dumps(payload)[:300]}")
    return players


def pull_all():
    all_players, offset = [], 0
    while True:
        page = fetch_page(offset)
        print(f"offset {offset}: got {len(page)} players", flush=True)
        if not page:
            break
        all_players.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
        time.sleep(SLEEP)
    return all_players


def latest_tag():
    """Newest dated ESPN roster cache available (fail-closed if none)."""
    cands = sorted(f for f in os.listdir(DATA)
                   if f.startswith("espn_roster_") and f.endswith(".json"))
    if not cands:
        raise RuntimeError("no ESPN roster cache in data/ - run bin/espn_roster.py")
    return cands[-1][len("espn_roster_"):-len(".json")]


def cache_path(date_tag):
    return os.path.join(DATA, f"espn_roster_{date_tag}.json")


def load(date_tag=None, force=False):
    """name (ESPN display) -> percentOwned. Pulls on cache miss unless the
    pull fails, in which case it raises (fail-closed: never silently fall
    back to a stale or FP source)."""
    date_tag = date_tag or date.today().isoformat()
    path = cache_path(date_tag)
    if os.path.exists(path) and not force:
        print(f"reusing cached {path}", flush=True)
        return {k: float(v) for k, v in json.loads(open(path).read()).items()}
    print("Pulling ESPN ownership data ...", flush=True)
    players = pull_all()
    print(f"total players pulled: {len(players)}", flush=True)
    espn = {}
    for entry in players:
        p = entry.get("player", {})
        name = p.get("fullName")
        own = (p.get("ownership") or {}).get("percentOwned")
        if name is None or own is None:
            continue
        espn[name] = round(float(own), 2)
    if not espn:
        raise RuntimeError("ESPN pull returned zero players - refusing to write an empty cache")
    n_dst = sum(1 for n in espn if DST_RE.match(n))
    if n_dst < 32:
        raise RuntimeError(f"ESPN pull returned only {n_dst} D/ST rows - refusing to write a partial cache")
    with open(path, "w") as f:
        json.dump(espn, f, indent=1, sort_keys=True)
    print(f"wrote {path} ({len(espn)} names)", flush=True)
    return espn


def build_lookup(date_tag=None, force=False):
    """Normalized lookup: keys each player under BOTH normalizations so
    callers using either convention (score_v0 norm or aggressive norm) hit.
    D/ST rows get a third key, the canonical entity key "dst:<abbr>"
    (lowercase, e.g. "dst:buf"), so K/DST consumers can resolve by team
    abbreviation (FP entity keys are "dst:BUF" - lowercase before lookup)."""
    espn = load(date_tag=date_tag, force=force)
    lookup = {}
    for name, pct in espn.items():
        lookup[norm_name(name)] = pct
        lookup.setdefault(score_norm(name), pct)
        key = dst_entity_key(name)
        if key is not None:
            lookup.setdefault(key, pct)
    return lookup


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    force = "--force" in sys.argv
    d = load(date_tag=tag, force=force)
    print(f"{len(d)} players")
