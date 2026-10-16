#!/usr/bin/env python3
"""JEG-684: pull FanDuel Research / NumberFire rest-of-season projections -> snapshot.json.

Source (public, anonymous, no key, no login; probed 2026-10-16, HTTP 200, 251 KB):
  page      https://www.fanduel.com/research/nfl/fantasy/rest-of-season-projections
  data call POST https://www.fanduel.com/research/api/graphql  (the page's own client call)
  query     GetProjections($input: ProjectionsInput!), NflSkill rows
  variables {"input": {"type": "REMAINING", "position": "NFL_SKILL", "sport": "NFL"}}
616 QB/RB/WR/TE rows, 439 with a non-zero projection (QB 57, RB 112, WR 169, TE 101);
the rest are zero-filled depth rows and are dropped (a zero projection is unpriced,
never a real 0). Per-stat fields: completionsAttempts ("274.2/398.92"), passing
yd/td/int, rush att/yd/td, receptions, targets, receiving yd/td, plus `fantasy`
(scoring unstated: Jahmyr Gibbs 282.2 vs 284.2 recomputed half-PPR, 310.4 PPR, so use
the per-stat columns and rescore). No fumbles or 2-point columns. The response has no
date: "remaining" means the rest of the season from the site's current week.

Output: <out-dir>/snapshot.json
  {"schema", "source", "source_url", "fetched_at", "vintage_date", "fingerprint",
   "rows": [{player_name, player_norm, pos, team, numberfire_id, pass_att, pass_cmp,
             pass_yd, pass_td, pass_int, rush_att, rush_yd, rush_td, rec, tgt, rec_yd,
             rec_td, fantasy, pos_rank, overall_rank}],
   "row_count", "dropped": {...}}
Identity (player_key) is resolved later by a saver via lib/canonical_players.

DATING: none in the payload, so the vintage is the run date; `fingerprint`
(sha256 of sorted (id, fantasy) pairs) decides whether the projections moved.

Fail closed (non-zero exit, no snapshot written), named on the
`NUMBERFIRE PULL FAILED [CODE]` line:
  SOURCE_BLOCKED    curl failure, non-200, or a tiny body
  SOURCE_LAYOUT     GraphQL errors, no getProjections list, or a required field is gone
  SOURCE_TRUNCATED  a position below its priced-row floor
  VALUE_RANGE       a negative stat or a fantasy total outside 0..600
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402

PAGE_URL = "https://www.fanduel.com/research/nfl/fantasy/rest-of-season-projections"
API_URL = "https://www.fanduel.com/research/api/graphql"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
QUERY = """query GetProjections($input: ProjectionsInput!) { getProjections(input: $input) {
 ... on NflSkill { player { numberFireId name position } team { abbreviation }
 completionsAttempts passingYards passingTouchdowns interceptionsThrown rushingAttempts rushingYards
 rushingTouchdowns receptions targets receivingYards receivingTouchdowns fantasy positionRank overallRank } } }"""
VARIABLES = {"input": {"type": "REMAINING", "position": "NFL_SKILL", "sport": "NFL"}}
MIN_BODY = 50_000  # live response is about 250 KB
POSITIONS = ("QB", "RB", "WR", "TE")
# priced-row floors, about 40% of the 2026-10-16 counts (QB 57, RB 112, WR 169, TE 101)
PRICED_FLOORS = {"QB": 22, "RB": 44, "WR": 67, "TE": 40}
FANTASY_MAX = 600
SCHEMA = "numberfire_ros_projections_v1"
STATS = {"pass_yd": "passingYards", "pass_td": "passingTouchdowns", "pass_int": "interceptionsThrown",
         "rush_att": "rushingAttempts", "rush_yd": "rushingYards", "rush_td": "rushingTouchdowns",
         "rec": "receptions", "tgt": "targets", "rec_yd": "receivingYards", "rec_td": "receivingTouchdowns"}


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def fetch() -> str:
    payload = json.dumps({"query": QUERY, "variables": VARIABLES})
    cmd = ["curl", "-sS", "-L", "--tlsv1.2", "--max-time", "60", "-A", UA,
           "-H", "Content-Type: application/json", "--data", "@-",
           "-w", "\n%{http_code}", API_URL]
    try:
        res = subprocess.run(cmd, input=payload.encode(), capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PullError(f"curl failed: {e}", "SOURCE_BLOCKED")
    if res.returncode != 0:
        raise PullError(f"curl exit {res.returncode}: {res.stderr.decode(errors='replace')[:200]}", "SOURCE_BLOCKED")
    body, _, status = res.stdout.decode("utf-8", errors="replace").rpartition("\n")
    if status != "200":
        raise PullError(f"HTTP {status} from {API_URL}", "SOURCE_BLOCKED")
    if len(body) < MIN_BODY:
        raise PullError(f"body is {len(body)} bytes (< {MIN_BODY})", "SOURCE_BLOCKED")
    return body


def extract_rows(body: str) -> list[dict]:
    try:
        doc = json.loads(body)
    except json.JSONDecodeError as e:
        raise PullError(f"response did not parse: {e}")
    if not isinstance(doc, dict) or doc.get("errors"):
        raise PullError(f"GraphQL errors: {str(doc.get('errors'))[:200] if isinstance(doc, dict) else 'not an object'}")
    rows = (doc.get("data") or {}).get("getProjections")
    if not isinstance(rows, list) or not rows:
        raise PullError("no data.getProjections list")
    return rows


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _split_att(value, name: str) -> tuple[float, float]:
    """'274.2/398.92' -> (completions, attempts)."""
    try:
        cmp_s, att_s = str(value).split("/")
        return float(cmp_s), float(att_s)
    except ValueError:
        raise PullError(f"{name} completionsAttempts unreadable: {value!r}")


def build_snapshot(rows_in: list[dict], now: datetime | None = None, floors: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    floors = PRICED_FLOORS if floors is None else floors
    sample = next((r for r in rows_in if isinstance(r.get("player"), dict)), None)
    if sample is None:
        raise PullError("no player rows")
    for key in ("completionsAttempts", "fantasy", "overallRank", "positionRank", *STATS.values()):
        if key not in sample:
            raise PullError(f"required field gone: {key}")
    rows, dropped, seen = [], {"non_skill_position": 0, "unpriced": 0}, set()
    for r in rows_in:
        player = r.get("player") or {}
        pos, name = player.get("position"), (player.get("name") or "").strip()
        if pos not in POSITIONS:
            dropped["non_skill_position"] += 1
            continue
        fantasy = _num(r.get("fantasy"))
        if fantasy is None:
            raise PullError(f"{name} fantasy is not a number")
        if not (0 <= fantasy <= FANTASY_MAX):
            raise PullError(f"{name} fantasy {fantasy} outside 0..{FANTASY_MAX}", "VALUE_RANGE")
        if fantasy == 0:
            dropped["unpriced"] += 1
            continue
        out = {"player_name": name, "player_norm": norm_plain(name), "pos": pos,
               "team": (r.get("team") or {}).get("abbreviation"), "numberfire_id": player.get("numberFireId")}
        cmp_, att = _split_att(r.get("completionsAttempts"), name)
        out["pass_cmp"], out["pass_att"] = cmp_, att
        for field, src in STATS.items():
            v = _num(r.get(src))
            if v is None:
                raise PullError(f"{name} {src} is not a number")
            if v < 0:
                raise PullError(f"{name} {src} {v} is negative", "VALUE_RANGE")
            out[field] = v
        out["fantasy"], out["pos_rank"], out["overall_rank"] = fantasy, _num(r.get("positionRank")), _num(r.get("overallRank"))
        if out["numberfire_id"] in seen:
            raise PullError(f"duplicate numberFireId {out['numberfire_id']} ({name})")
        seen.add(out["numberfire_id"])
        rows.append(out)
    for pos, floor in floors.items():
        n = sum(1 for r in rows if r["pos"] == pos)
        if n < floor:
            raise PullError(f"{pos} has {n} priced rows (floor {floor})", "SOURCE_TRUNCATED")
    pairs = sorted((r["numberfire_id"], r["fantasy"]) for r in rows)
    fingerprint = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]
    return {"schema": SCHEMA, "source": "numberfire_ros", "source_url": PAGE_URL,
            "fetched_at": now.isoformat(timespec="seconds"), "vintage_date": now.date().isoformat(),
            "fingerprint": fingerprint, "rows": rows, "row_count": len(rows), "dropped": dropped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--json", help="parse this saved GraphQL response instead of fetching (tests, replays)")
    a = ap.parse_args(argv)
    try:
        body = Path(a.json).read_text(encoding="utf-8") if a.json else fetch()
        snap = build_snapshot(extract_rows(body))
    except PullError as e:
        print(f"NUMBERFIRE PULL FAILED [{e.code}] {e}", file=sys.stderr)
        return 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f"numberfire_ros: {snap['row_count']} priced rows, fingerprint {snap['fingerprint']}, vintage {snap['vintage_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
