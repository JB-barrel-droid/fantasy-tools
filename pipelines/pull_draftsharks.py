#!/usr/bin/env python3
"""JEG-620: pull the Draft Sharks public trade value chart -> snapshot.json.

Source page (public, no login, no paywall; measured 2026-10-12, HTTP 200, 12 MB):
  https://www.draftsharks.com/trade-value-chart
The page server-renders its whole chart as one JSON object, `"players":[{...}]`,
with one row per player (QB/RB/WR/TE plus IDP, K, DEF, coaches). Each row carries,
for every format, `dsValue<Redraft|Dynasty><NoPpr|HalfPpr|OnePpr|TePremium>[Superflex]`
(Draft Sharks' own 0-100 trade value) and `marketValue...` (the market's value on
the same scale), plus `...Delta` and `...OverallTier`. Unpriced players carry 0
in every column; 0 therefore means unpriced and is written as null. Negative
values (down to about -135) are real below-replacement depth values and are kept.
Only QB/RB/WR/TE rows priced in at least one format are kept.

Output: <out-dir>/snapshot.json
  {"schema", "source", "source_url", "fetched_at", "vintage_date", "fingerprint",
   "rows": [{player_name, player_norm, pos, team, draftsharks_id,
             ds: {<format>: value}, market: {<format>: value}}],
   "row_count", "dropped": {...}}
`<format>` is e.g. `redraft_half_ppr`, `redraft_one_ppr_superflex`,
`dynasty_te_premium`. A format with value 0 is null, never 0.
Identity (player_key) is resolved later by the saver against public.players via
lib/canonical_players; this puller only normalizes the name (fail closed there).

DATING: the page carries no player-chart timestamp (only pick rows have one), so
the vintage is the run date and `fingerprint` (sha256 of the sorted
(id, redraft half-PPR ds value) pairs) is what decides whether the chart moved.

Fail closed (non-zero exit, no snapshot written), named on the
`DRAFTSHARKS PULL FAILED [CODE]` line:
  SOURCE_BLOCKED    non-200, bot wall / login redirect, or a tiny body
  SOURCE_LAYOUT     no players array, or a required value column is gone
  SOURCE_TRUNCATED  a position below its priced-row floor
  VALUE_RANGE       a skill-position value outside -200..100 (scale changed; observed
                    -135..100, negatives are below-replacement depth, real values)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402

URL = "https://www.draftsharks.com/trade-value-chart"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MIN_BODY = 1_000_000
POSITIONS = ("QB", "RB", "WR", "TE")
# priced-row floors, about 40% of the 2026-10-12 counts (QB 24, RB 67, WR 60, TE 17)
PRICED_FLOORS = {"QB": 10, "RB": 25, "WR": 24, "TE": 7}
SCORINGS = {"NoPpr": "no_ppr", "HalfPpr": "half_ppr", "OnePpr": "one_ppr", "TePremium": "te_premium"}
LEAGUES = {"Redraft": "redraft", "Dynasty": "dynasty"}
REQUIRED_COLUMNS = ("dsValueRedraftHalfPpr", "marketValueRedraftHalfPpr", "dsValueDynastyHalfPpr")
SCHEMA = "draftsharks_trade_value_v1"
_PLAYERS_ANCHOR = re.compile(r'"players"\s*:\s*\[')


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def format_columns() -> dict[str, tuple[str, str]]:
    """format key -> (ds column, market column)."""
    out = {}
    for lg_col, lg in LEAGUES.items():
        for sc_col, sc in SCORINGS.items():
            for sf_col, sf in (("", ""), ("Superflex", "_superflex")):
                out[f"{lg}_{sc}{sf}"] = (f"dsValue{lg_col}{sc_col}{sf_col}",
                                        f"marketValue{lg_col}{sc_col}{sf_col}")
    return out


def fetch(url: str = URL) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            final = r.geturl()
            body = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise PullError(f"HTTP {e.code} from {url}", "SOURCE_BLOCKED")
    except (urllib.error.URLError, TimeoutError) as e:
        raise PullError(f"fetch failed: {e}", "SOURCE_BLOCKED")
    if re.search(r"/(login|sign-?in|subscribe)\b", final):
        raise PullError(f"redirected to a login/paywall page: {final}", "SOURCE_BLOCKED")
    return body


def extract_players(body: str) -> list[dict]:
    if len(body) < MIN_BODY:
        raise PullError(f"body is {len(body)} bytes (< {MIN_BODY})", "SOURCE_BLOCKED")
    match = _PLAYERS_ANCHOR.search(body)
    if match is None:
        raise PullError("no embedded players array on the page")
    try:
        players, _ = json.JSONDecoder().raw_decode(body[match.end() - 1:])
    except json.JSONDecodeError as e:
        raise PullError(f"players array did not parse: {e}")
    if not isinstance(players, list) or not players:
        raise PullError("players array is empty")
    return players


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def build_snapshot(players: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cols = format_columns()
    rows, dropped = [], {"non_skill_position": 0, "unpriced": 0}
    seen_ids = set()
    for p in players:
        if not isinstance(p, dict):
            raise PullError("players array contains a non-object row")
        pos = p.get("fantasy_position")
        if pos not in POSITIONS:
            dropped["non_skill_position"] += 1
            continue
        missing = [c for c in REQUIRED_COLUMNS if c not in p]
        if missing:
            raise PullError(f"required columns gone for player {p.get('id')}: {missing}")
        name = f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip()
        pid = p.get("id")
        if not name or not isinstance(pid, int) or isinstance(pid, bool) or pid in seen_ids:
            raise PullError(f"missing name/id or duplicate id for player {pid!r}")
        seen_ids.add(pid)
        ds, market = {}, {}
        for fmt, (dc, mc) in cols.items():
            dv, mv = _num(p.get(dc)), _num(p.get(mc))
            for col, v in ((dc, dv), (mc, mv)):
                if v is not None and not (-200 <= v <= 100):
                    raise PullError(f"{name} {col}={v} outside -200..100", "VALUE_RANGE")
            ds[fmt] = dv if dv else None
            market[fmt] = mv if mv else None
        if all(v is None for v in ds.values()):
            dropped["unpriced"] += 1
            continue
        rows.append({
            "player_name": name, "player_norm": norm_plain(name), "pos": pos,
            "team": p.get("abbr") or None, "draftsharks_id": p.get("id"),
            "ds": ds, "market": market,
        })
    for pos in POSITIONS:
        n = sum(1 for r in rows if r["pos"] == pos and (r["ds"]["redraft_half_ppr"] or 0) > 0)
        if n < PRICED_FLOORS[pos]:
            raise PullError(f"{pos} has {n} positive redraft half-PPR rows (floor {PRICED_FLOORS[pos]})", "SOURCE_TRUNCATED")
    pairs = sorted((r["draftsharks_id"], r["ds"]["redraft_half_ppr"]) for r in rows
                   if r["ds"]["redraft_half_ppr"] is not None)
    fingerprint = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]
    return {
        "schema": SCHEMA, "source": "draftsharks", "source_url": URL,
        "fetched_at": now.isoformat(timespec="seconds"),
        "vintage_date": now.date().isoformat(), "fingerprint": fingerprint,
        "rows": rows, "row_count": len(rows), "dropped": dropped,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--html", help="parse this saved page instead of fetching (tests, replays)")
    a = ap.parse_args(argv)
    try:
        body = Path(a.html).read_text(encoding="utf-8") if a.html else fetch()
        snap = build_snapshot(extract_players(body))
    except PullError as e:
        print(f"DRAFTSHARKS PULL FAILED [{e.code}] {e}", file=sys.stderr)
        return 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f"draftsharks: {snap['row_count']} priced rows, fingerprint {snap['fingerprint']}, vintage {snap['vintage_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
