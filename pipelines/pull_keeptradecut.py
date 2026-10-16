#!/usr/bin/env python3
"""JEG-669: pull the KeepTradeCut public dynasty rankings -> snapshot.json.

Source page (public, no login, no paywall; measured 2026-10-16, HTTP 200, 2.7 MB):
  https://keeptradecut.com/dynasty-rankings
The page embeds 500 rows as JSON in `<script type="application/json" id="ktc-players">`:
QB/RB/WR/TE plus rookie draft picks (position RDP). Each player has `oneQBValues` and
`superflexValues`; each of those carries the base value (`value`, `rank`,
`positionalRank`, `overallTier`) and three TE-premium blocks (`tep`, `tepp`, `teppp`,
the same fields). Values are on KTC's 1-9999 scale; they are DYNASTY-framed
(a methods decision is needed before any DDF use). A missing or 0 value is null,
never 0. Draft picks are dropped. Only QB/RB/WR/TE rows are kept.

Python urllib fails TLS against this host (TLSv1 alert), so the fetch shells out to
curl (`--tlsv1.2`).

Output: <out-dir>/snapshot.json
  {"schema", "source", "source_url", "fetched_at", "vintage_date", "fingerprint",
   "rows": [{player_name, player_norm, pos, team, ktc_id,
             values: {<format>: {value, rank, pos_rank, tier}}}],
   "row_count", "dropped": {...}}
`<format>` is `1qb`, `1qb_tep`, `1qb_tepp`, `1qb_teppp`, `sf`, `sf_tep`, ...
Identity (player_key) is resolved later by the saver against public.players via
lib/canonical_players; this puller only normalizes the name.

DATING: the page has no chart timestamp, so the vintage is the run date and
`fingerprint` (sha256 of sorted (id, 1QB value) pairs) decides whether it moved.

Fail closed (non-zero exit, no snapshot written), named on the
`KEEPTRADECUT PULL FAILED [CODE]` line:
  SOURCE_BLOCKED    curl failure, non-200, login/bot wall, or a tiny body
  SOURCE_LAYOUT     no ktc-players script, bad JSON, or a required field is gone
  SOURCE_TRUNCATED  a position below its priced-row floor
  VALUE_RANGE       a value outside 1..9999 (scale changed)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402

URL = "https://keeptradecut.com/dynasty-rankings"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MIN_BODY = 500_000
POSITIONS = ("QB", "RB", "WR", "TE")
# priced-row floors, about 40% of the 2026-10-16 counts (QB 71, RB 126, WR 186, TE 81)
PRICED_FLOORS = {"QB": 28, "RB": 50, "WR": 74, "TE": 32}
VALUE_MIN, VALUE_MAX = 1, 9999
LEAGUES = {"oneQBValues": "1qb", "superflexValues": "sf"}
TE_BLOCKS = {"tep": "_tep", "tepp": "_tepp", "teppp": "_teppp"}
SCHEMA = "keeptradecut_trade_value_v1"
_SCRIPT = re.compile(r'<script[^>]*id="ktc-players"[^>]*>(.*?)</script>', re.S)


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def format_keys() -> list[str]:
    return [lg + suf for lg in LEAGUES.values() for suf in ("", *TE_BLOCKS.values())]


def fetch(url: str = URL) -> str:
    cmd = ["curl", "-sS", "-L", "--tlsv1.2", "--max-time", "60", "-A", UA,
           "-w", "\n%{http_code} %{url_effective}", url]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PullError(f"curl failed: {e}", "SOURCE_BLOCKED")
    if res.returncode != 0:
        raise PullError(f"curl exit {res.returncode}: {res.stderr.decode(errors='replace')[:200]}", "SOURCE_BLOCKED")
    out = res.stdout.decode("utf-8", errors="replace")
    body, _, tail = out.rpartition("\n")
    status, _, final = tail.partition(" ")
    if status != "200":
        raise PullError(f"HTTP {status} from {url}", "SOURCE_BLOCKED")
    if re.search(r"/(login|sign-?in|subscribe)\b", final):
        raise PullError(f"redirected to a login/paywall page: {final}", "SOURCE_BLOCKED")
    return body


def extract_players(body: str) -> list[dict]:
    if len(body) < MIN_BODY:
        raise PullError(f"body is {len(body)} bytes (< {MIN_BODY})", "SOURCE_BLOCKED")
    m = _SCRIPT.search(body)
    if not m:
        raise PullError("no ktc-players script on the page")
    try:
        players = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise PullError(f"ktc-players did not parse: {e}")
    if not isinstance(players, list) or not players:
        raise PullError("ktc-players is empty")
    return players


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _cell(block, name: str) -> dict | None:
    """One format's {value, rank, pos_rank, tier}; None when unpriced (0 or missing)."""
    if not isinstance(block, dict):
        return None
    v = _num(block.get("value"))
    if not v:
        return None
    if not (VALUE_MIN <= v <= VALUE_MAX):
        raise PullError(f"{name} value {v} outside {VALUE_MIN}..{VALUE_MAX}", "VALUE_RANGE")
    return {"value": v, "rank": _num(block.get("rank")),
            "pos_rank": _num(block.get("positionalRank")), "tier": _num(block.get("overallTier"))}


def build_snapshot(players: list[dict], now: datetime | None = None, floors: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    floors = PRICED_FLOORS if floors is None else floors
    sample = next((p for p in players if p.get("position") in POSITIONS), None)
    if sample is None:
        raise PullError("no QB/RB/WR/TE rows", "SOURCE_TRUNCATED")
    for key in ("playerName", "playerID", "oneQBValues", "superflexValues"):
        if key not in sample:
            raise PullError(f"required field gone: {key}")
    if _num(sample["oneQBValues"].get("value")) is None:
        raise PullError("required field gone: oneQBValues.value")
    rows, dropped = [], {"non_skill_position": 0, "unpriced": 0}
    for p in players:
        pos = p.get("position")
        if pos not in POSITIONS:
            dropped["non_skill_position"] += 1
            continue
        name = (p.get("playerName") or "").strip()
        values = {}
        for lg_key, lg in LEAGUES.items():
            block = p.get(lg_key) or {}
            values[lg] = _cell(block, f"{name} {lg}")
            for te_key, suf in TE_BLOCKS.items():
                values[lg + suf] = _cell(block.get(te_key), f"{name} {lg}{suf}")
        if all(v is None for v in values.values()):
            dropped["unpriced"] += 1
            continue
        rows.append({"player_name": name, "player_norm": norm_plain(name), "pos": pos,
                     "team": p.get("team") or None, "ktc_id": p.get("playerID"), "values": values})
    for pos, floor in floors.items():
        n = sum(1 for r in rows if r["pos"] == pos and r["values"]["1qb"])
        if n < floor:
            raise PullError(f"{pos} has {n} priced 1QB rows (floor {floor})", "SOURCE_TRUNCATED")
    pairs = sorted((r["ktc_id"], r["values"]["1qb"]["value"]) for r in rows if r["values"]["1qb"])
    fingerprint = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]
    return {"schema": SCHEMA, "source": "keeptradecut", "source_url": URL,
            "fetched_at": now.isoformat(timespec="seconds"), "vintage_date": now.date().isoformat(),
            "fingerprint": fingerprint, "rows": rows, "row_count": len(rows), "dropped": dropped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--html", help="parse this saved page instead of fetching (tests, replays)")
    a = ap.parse_args(argv)
    try:
        body = Path(a.html).read_text(encoding="utf-8") if a.html else fetch()
        snap = build_snapshot(extract_players(body))
    except PullError as e:
        print(f"KEEPTRADECUT PULL FAILED [{e.code}] {e}", file=sys.stderr)
        return 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f"keeptradecut: {snap['row_count']} priced rows, fingerprint {snap['fingerprint']}, vintage {snap['vintage_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
