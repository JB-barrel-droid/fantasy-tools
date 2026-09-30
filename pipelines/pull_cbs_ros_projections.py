#!/usr/bin/env python3
"""Scrape CBS Sports rest-of-season fantasy projections (raw stat columns).

CBS publishes ROS projections per position at:
  https://www.cbssports.com/fantasy/football/stats/{POS}/2026/restofseason/projections/nonppr/
(POS = QB, RB, WR, TE). Only the `nonppr` slug exists; there is no half-PPR
variant. We scrape the RAW STAT columns (gp, attempts, yards, TDs, INTs,
targets, receptions, fumbles lost, ...) plus CBS's own nonppr fpts total,
then compute half-PPR / full-PPR ourselves by adding reception points --
exactly the repo's established rescoring pattern (reception points are the
only scoring difference; cf. build_ddf_two_tier_leg.load_espn_lists).

CBS's fpts column is taken as the ground-truth nonppr total. We do NOT
recompute nonppr from components with guessed coefficients (CBS's house
scoring differs slightly from textbook); we only add 0.5/1.0 per reception.

Output: data/raw/sources/cbsros/<YYYY-MM-DD>/snapshot.json
  rows: one per player per scoring (ppr / half_ppr / standard), each with
        player_name (normalized), pos, team, gp, per-game value, raw stats,
        and the CBS fpts total for audit.
  review_rows: unparseable rows or identity-unresolvable players (fail-closed:
        never guessed, never zero-filled).

Identity: names are resolved to numeric player_key downstream by the DDF leg
builder via the fixture's player_keys map (same as ESPN). This script records
the normalized name; resolution happens once, downstream.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain as norm_player_name  # noqa: E402
# NOTE: norm_plain (NO nickname expansion) is the fixture join convention:
# fixture player_keys and the ESPN leg's csv player_norm both use it
# ("josh allen", not "joshua allen"). norm_player_name() would falsely
# reject ~70 real players on identity join. Verified 2026-09-30.

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://www.cbssports.com/fantasy/football/stats/{pos}/2026/restofseason/projections/nonppr/"
POSITIONS = ["QB", "RB", "WR", "TE"]

# Data <td> columns per position, in order, after the player cell.
LAYOUTS = {
    "QB": ["gp", "pass_att", "pass_cmp", "pass_yds", "pass_yds_g", "pass_td",
           "int", "rate", "rush_att", "rush_yds", "rush_avg", "rush_td",
           "fl", "fpts", "fppg"],
    "RB": ["gp", "rush_att", "rush_yds", "rush_avg", "rush_td", "tgt", "rec",
           "rec_yds", "rec_yds_g", "rec_avg", "rec_td", "fl", "fpts", "fppg"],
    "WR": ["gp", "tgt", "rec", "rec_yds", "rec_yds_g", "rec_avg", "rec_td",
           "rush_att", "rush_yds", "rush_avg", "rush_td", "fl", "fpts", "fppg"],
    "TE": ["gp", "tgt", "rec", "rec_yds", "rec_yds_g", "rec_avg", "rec_td",
           "fl", "fpts", "fppg"],
}

ROW_RE = re.compile(r'<tr class="TableBase-bodyTr">(.*?)</tr>', re.S)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PLAYER_RE = re.compile(
    r"CellPlayerName--long.*?<a[^>]*>([^<]+)</a>"
    r".*?CellPlayerName-position[^>]*>\s*([A-Z]+)\s*"
    r".*?CellPlayerName-team[^>]*>\s*([A-Z]+)\s*",
    re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise SystemExit(f"Fail closed: HTTP {resp.status} for {url}")
        return resp.read().decode("utf-8", errors="replace")


def parse_num(raw: str) -> float | None:
    txt = TAG_RE.sub("", raw).replace(",", "").strip()
    if txt in ("", "--", "-", "—"):
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def parse_position(pos: str, html: str) -> tuple[list[dict], list[dict]]:
    """Return (rows, review_rows) for one position page."""
    layout = LAYOUTS[pos]
    rows, review = [], []
    for m in ROW_RE.finditer(html):
        body = m.group(1)
        pm = PLAYER_RE.search(body)
        if not pm:
            review.append({"reason": "unparseable_player_cell", "pos": pos})
            continue
        name, ppos, team = (pm.group(1).strip(), pm.group(2).strip(), pm.group(3).strip())
        tds = TD_RE.findall(body)
        if len(tds) - 1 != len(layout):
            review.append({"reason": "column_count_mismatch", "player": name,
                           "pos": pos, "tds": len(tds) - 1,
                           "expected": len(layout)})
            continue
        stats: dict[str, float | None] = {}
        bad = False
        for key, td in zip(layout, tds[1:]):
            val = parse_num(td)
            if val is None and key not in ("pass_yds_g", "rec_yds_g", "rush_avg",
                                           "rec_avg", "rate"):
                # Core counting stats must parse; per-game/avgs may be blank.
                review.append({"reason": "unparseable_stat", "player": name,
                               "pos": pos, "column": key})
                bad = True
                break
            stats[key] = val
        if bad:
            continue
        gp = stats.get("gp") or 0
        fpts = stats.get("fpts")
        rec = stats.get("rec") or 0.0
        if not gp or gp <= 0 or fpts is None:
            review.append({"reason": "missing_gp_or_fpts", "player": name, "pos": pos})
            continue
        # CBS fpts is the ground-truth nonppr total. Rescore by receptions only.
        ros = {
            "standard": fpts,
            "half_ppr": fpts + 0.5 * rec,
            "ppr": fpts + 1.0 * rec,
        }
        # Sanity: fpts/gp should match CBS's own fppg (catches column drift).
        fppg = stats.get("fppg")
        if fppg and abs(fpts / gp - fppg) > 0.15:
            review.append({"reason": "fppg_inconsistent", "player": name,
                           "pos": pos, "fpts": fpts, "gp": gp, "fppg": fppg})
            continue
        rows.append({
            "player_name": name,
            "player_norm": norm_player_name(name),
            "pos": ppos,
            "team": team,
            "gp": gp,
            "ros_standard": round(ros["standard"], 2),
            "ros_half_ppr": round(ros["half_ppr"], 2),
            "ros_ppr": round(ros["ppr"], 2),
            "per_game_standard": round(ros["standard"] / gp, 3),
            "per_game_half_ppr": round(ros["half_ppr"] / gp, 3),
            "per_game_ppr": round(ros["ppr"] / gp, 3),
            "cbs_fpts": fpts,
            "cbs_fppg": fppg,
            "receptions": rec,
            "raw_stats": {k: v for k, v in stats.items()
                          if k not in ("fpts", "fppg") and v is not None},
        })
    return rows, review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        help="Snapshot vintage date (default: today UTC)")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    out_dir = args.out_dir or (ROOT / "data" / "raw" / "sources" / "cbsros" / args.date)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    all_review: list[dict] = []
    page_urls = {}
    for pos in POSITIONS:
        url = BASE.format(pos=pos)
        page_urls[pos] = url
        print(f"  fetching {pos} ...", flush=True)
        html = fetch(url)
        rows, review = parse_position(pos, html)
        print(f"    {len(rows)} players, {len(review)} review rows")
        all_rows.extend(rows)
        all_review.extend(review)

    if not all_rows:
        raise SystemExit("Fail closed: no players parsed from any CBS page.")

    snapshot = {
        "schema": "trade-value-cbsros-snapshot-v1",
        "source": "cbssports_ros_projections",
        "vintage_date": args.date,
        "scraped_at": utc_now(),
        "page_urls": page_urls,
        "scoring_note": ("CBS publishes nonppr ROS totals only. half_ppr / ppr "
                         "are CBS fpts + 0.5/1.0 per reception (reception points "
                         "are the only scoring difference). per_game_* = ROS / gp."),
        "rows": all_rows,
        "review_rows": all_review,
        "summary": {
            "n_rows": len(all_rows),
            "n_review": len(all_review),
            "by_pos": {p: sum(1 for r in all_rows if r["pos"] == p) for p in POSITIONS},
        },
    }
    out_path = out_dir / "snapshot.json"
    out_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_rows)} players -> {out_path}")
    if all_review:
        print(f"  ({len(all_review)} review rows excluded fail-closed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
