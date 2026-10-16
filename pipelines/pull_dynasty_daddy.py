#!/usr/bin/env python3
"""JEG-674: pull the Dynasty Daddy public player JSON -> snapshot.json (comparison / id bridge).

Source (public JSON, no key, no login; probed 2026-10-16, HTTP 200, 930 KB):
  https://dynasty-daddy.com/api/v1/player/all/today
A JSON list of 765 rows: 621 QB/RB/WR/TE plus 144 draft picks (position PI, dropped).
Per player: `trade_value` (1QB) and `sf_trade_value` (superflex) on a 0-9999 scale,
overall and position ranks for both, and the ids sleeper_id, mfl_id, espn_id, yahoo_id,
ff_id, ffpc_id, fantrax_id. A trade value of 0 is unpriced and is written as null
(153 skill rows were 0 on 2026-10-16), never 0.

USE: comparison and id cross-check only. Dynasty Daddy's value aggregates other
markets (FantasyCalc, KTC), so weighting it beside them double counts, and the values
are dynasty-framed. Rank columns that derive from FantasyPros expert consensus
(`fantasypros_ros`, `avg_ros`) are deliberately NOT kept, because ECR is excluded
repo-wide. The other ROS ranks (espn_ros, fanduel_ros, fantasyguys_ros) are kept.

Output: <out-dir>/snapshot.json
  {"schema", "source", "source_url", "fetched_at", "vintage_date", "fingerprint",
   "rows": [{player_name, player_norm, pos, team, ids: {...},
             values: {"1qb": {value, rank, pos_rank}, "sf": {value, rank, pos_rank}},
             espn_ros, fanduel_ros, fantasyguys_ros}],
   "row_count", "dropped": {...}}
Identity (player_key) is resolved later by a saver via lib/canonical_players.

DATING: each row carries `most_recent_data_point`; the vintage is the newest such date.
`fingerprint` is sha256 of sorted (name_id, 1QB value) pairs.

Fail closed (non-zero exit, no snapshot written), named on the
`DYNASTYDADDY PULL FAILED [CODE]` line:
  SOURCE_BLOCKED    curl failure, non-200, or a tiny body
  SOURCE_LAYOUT     not a list, or a required field is gone
  SOURCE_STALE      newest data point is more than 3 days old
  SOURCE_TRUNCATED  a position below its priced-row floor
  VALUE_RANGE       a value outside 0..9999 (scale changed)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402

URL = "https://dynasty-daddy.com/api/v1/player/all/today"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MIN_BODY = 200_000  # live response is about 930 KB
POSITIONS = ("QB", "RB", "WR", "TE")
# priced-row floors, about 40% of the 2026-10-16 counts (QB 73, RB 127, WR 187, TE 81)
PRICED_FLOORS = {"QB": 29, "RB": 50, "WR": 75, "TE": 32}
VALUE_MIN, VALUE_MAX = 0, 9999
MAX_AGE_DAYS = 3
SCHEMA = "dynasty_daddy_values_v1"
ID_FIELDS = ("sleeper_id", "mfl_id", "espn_id", "yahoo_id", "ff_id", "ffpc_id", "fantrax_id")
LEAGUES = {"1qb": ("trade_value", "overall_rank", "position_rank"),
           "sf": ("sf_trade_value", "sf_overall_rank", "sf_position_rank")}


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def fetch() -> str:
    cmd = ["curl", "-sS", "-L", "--tlsv1.2", "--max-time", "60", "-A", UA, "-w", "\n%{http_code}", URL]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PullError(f"curl failed: {e}", "SOURCE_BLOCKED")
    if res.returncode != 0:
        raise PullError(f"curl exit {res.returncode}: {res.stderr.decode(errors='replace')[:200]}", "SOURCE_BLOCKED")
    body, _, status = res.stdout.decode("utf-8", errors="replace").rpartition("\n")
    if status != "200":
        raise PullError(f"HTTP {status} from {URL}", "SOURCE_BLOCKED")
    if len(body) < MIN_BODY:
        raise PullError(f"body is {len(body)} bytes (< {MIN_BODY})", "SOURCE_BLOCKED")
    return body


def extract_rows(body: str) -> list[dict]:
    try:
        rows = json.loads(body)
    except json.JSONDecodeError as e:
        raise PullError(f"response did not parse: {e}")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise PullError("response is not a non-empty list of objects")
    return rows


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _value(r: dict, key: str, name: str):
    v = _num(r.get(key))
    if v is None:
        return None
    if not (VALUE_MIN <= v <= VALUE_MAX):
        raise PullError(f"{name} {key} {v} outside {VALUE_MIN}..{VALUE_MAX}", "VALUE_RANGE")
    return v or None  # 0 is unpriced


def _stamp_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def build_snapshot(rows_in: list[dict], now: datetime | None = None, floors: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    floors = PRICED_FLOORS if floors is None else floors
    sample = next((r for r in rows_in if r.get("position") in POSITIONS), None)
    if sample is None:
        raise PullError("no QB/RB/WR/TE rows", "SOURCE_TRUNCATED")
    for key in ("name_id", "full_name", "trade_value", "sf_trade_value", "overall_rank", "sf_overall_rank",
                "most_recent_data_point"):
        if key not in sample:
            raise PullError(f"required field gone: {key}")
    rows, dropped, seen, newest = [], {"non_skill_position": 0, "unpriced": 0}, set(), None
    for r in rows_in:
        pos = r.get("position")
        if pos not in POSITIONS:
            dropped["non_skill_position"] += 1
            continue
        name = (r.get("full_name") or "").strip()
        values = {}
        for lg, (vkey, rkey, pkey) in LEAGUES.items():
            v = _value(r, vkey, name)
            values[lg] = {"value": v, "rank": _num(r.get(rkey)), "pos_rank": _num(r.get(pkey))} if v else None
        if all(v is None for v in values.values()):
            dropped["unpriced"] += 1
            continue
        if r["name_id"] in seen:
            raise PullError(f"duplicate name_id {r['name_id']}")
        seen.add(r["name_id"])
        stamp = _stamp_date(r.get("most_recent_data_point"))
        if stamp and (newest is None or stamp > newest):
            newest = stamp
        rows.append({"player_name": name, "player_norm": norm_plain(name), "pos": pos, "team": r.get("team") or None,
                     "name_id": r["name_id"], "ids": {k: r.get(k) for k in ID_FIELDS if r.get(k)},
                     "values": values, "espn_ros": _num(r.get("espn_ros")), "fanduel_ros": _num(r.get("fanduel_ros")),
                     "fantasyguys_ros": _num(r.get("fantasyguys_ros"))})
    if newest is None:
        raise PullError("no row carries a most_recent_data_point date")
    age = (now.date() - newest).days
    if age > MAX_AGE_DAYS:
        raise PullError(f"newest data point is {newest} ({age} days old, limit {MAX_AGE_DAYS})", "SOURCE_STALE")
    for pos, floor in floors.items():
        n = sum(1 for r in rows if r["pos"] == pos and r["values"]["1qb"])
        if n < floor:
            raise PullError(f"{pos} has {n} priced 1QB rows (floor {floor})", "SOURCE_TRUNCATED")
    pairs = sorted((r["name_id"], r["values"]["1qb"]["value"]) for r in rows if r["values"]["1qb"])
    fingerprint = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]
    return {"schema": SCHEMA, "source": "dynasty_daddy", "source_url": URL,
            "fetched_at": now.isoformat(timespec="seconds"), "vintage_date": newest.isoformat(),
            "fingerprint": fingerprint, "rows": rows, "row_count": len(rows), "dropped": dropped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--json", help="parse this saved response instead of fetching (tests, replays)")
    a = ap.parse_args(argv)
    try:
        body = Path(a.json).read_text(encoding="utf-8") if a.json else fetch()
        snap = build_snapshot(extract_rows(body))
    except PullError as e:
        print(f"DYNASTYDADDY PULL FAILED [{e.code}] {e}", file=sys.stderr)
        return 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f"dynasty_daddy: {snap['row_count']} priced rows, fingerprint {snap['fingerprint']}, vintage {snap['vintage_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
