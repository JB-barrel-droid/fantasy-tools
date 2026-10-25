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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "pipelines"))
from nfl_week import content_week  # noqa: E402
from canonical_players import norm_plain as norm_player_name  # noqa: E402
# NOTE: norm_plain (NO nickname expansion) is the fixture join convention:
# fixture player_keys and the ESPN leg's csv player_norm both use it
# ("josh allen", not "joshua allen"). norm_player_name() would falsely
# reject ~70 real players on identity join. Verified 2026-09-30.

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://www.cbssports.com/fantasy/football/stats/{pos}/2026/restofseason/projections/nonppr/"
POSITIONS = ["QB", "RB", "WR", "TE"]
# JEG-944: CBS also publishes per-week projections. Checked 2026-10-23: only the
# current week and the next week are real; a later week's URL answers 200 with
# the CURRENT week's page, titled "Week <current> Proj". So a page counts only
# when its own title names the week asked for.
WEEK_BASE = "https://www.cbssports.com/fantasy/football/stats/{pos}/2026/{week}/projections/nonppr/"
WEEK_TITLE_RE = re.compile(r"<title>\s*Week\s+(\d+)\s+Proj", re.I)
WEEKS_TO_TRY = 3  # content week, +1, +2 (the last is how the fallback is seen)

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


FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SECONDS = 5.0
# Transient statuses worth a retry. Anything else (403 block, 404 moved page)
# fails on the first attempt: retrying would only delay the loud failure.
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _fetch_once(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise SystemExit(f"Fail closed: HTTP {resp.status} for {url}")
        return resp.read().decode("utf-8", errors="replace")


def fetch(url: str, *, attempts: int = FETCH_ATTEMPTS,
          backoff: float = FETCH_BACKOFF_SECONDS, sleep=time.sleep) -> str:
    """GET a CBS page, retrying transient network / 429 / 5xx errors.

    Fails closed (SystemExit) once attempts are exhausted or on a
    non-retryable HTTP status.
    """
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _fetch_once(url)
        except urllib.error.HTTPError as err:
            if err.code not in RETRYABLE_HTTP:
                raise SystemExit(f"Fail closed: HTTP {err.code} for {url}") from err
            last_err = err
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last_err = err
        if attempt < attempts:
            print(f"    attempt {attempt}/{attempts} failed ({last_err}); retrying",
                  flush=True)
            sleep(backoff * attempt)
    raise SystemExit(f"Fail closed: {url} failed after {attempts} attempts: {last_err}")


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
        # JEG-807 (2026-10-22): the position is the table's, not the cell's.
        # CBS lists fullbacks in the RB table with "(FB)" in the cell (Kyle
        # Juszczyk, Andrew Beck, Michael Burton; Connor Heyward under TE).
        # Saving the cell's FB made save_cbsros_references.py's resolver
        # answer position_conflict (public.players has them at RB) and drop
        # them to review, while the pulse reader (fidelity_sources/cbsros.py)
        # keeps the table position, resolves them, and held CBS ROS red for
        # "3 publisher players not stored" with every value equal. The
        # cell's position is kept beside it for the record.
        rows.append({
            "player_name": name,
            "player_norm": norm_player_name(name),
            "pos": pos,
            "cell_pos": ppos,
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


def served_week(html: str) -> int | None:
    m = WEEK_TITLE_RE.search(html)
    return int(m.group(1)) if m else None


def pull_weekly(source_week: int, scraped_at: str) -> dict:
    """Per-week CBS projections for source_week .. source_week+WEEKS_TO_TRY-1.

    Never raises: a fault is recorded in `errors`, and the ROS leg (the only part
    that feeds a published value) is untouched either way. Rows carry the week
    TOTAL (gp is 1) in points_*; half/PPR add receptions as in the ROS rows.
    """
    weeks: dict[str, list[dict]] = {}
    not_offered: list[int] = []
    errors: list[str] = []
    for wk in range(source_week, source_week + WEEKS_TO_TRY):
        rows_wk: list[dict] = []
        offered = True
        for pos in POSITIONS:
            try:
                html = fetch(WEEK_BASE.format(pos=pos, week=wk))
            except (SystemExit, Exception) as exc:  # noqa: BLE001
                errors.append(f"week {wk} {pos}: {exc}")
                offered = False
                break
            if served_week(html) != wk:
                offered = False
                break
            rows, _review = parse_position(pos, html)
            for r in rows:
                rows_wk.append({"player_name": r["player_name"], "player_norm": r["player_norm"],
                                "pos": r["pos"], "team": r["team"], "gp": r["gp"],
                                "points_standard": r["ros_standard"],
                                "points_half_ppr": r["ros_half_ppr"],
                                "points_ppr": r["ros_ppr"]})
        if offered and rows_wk:
            weeks[str(wk)] = rows_wk
        elif not any(e.startswith(f"week {wk} ") for e in errors):
            not_offered.append(wk)
    return {"schema": "cbs-weekly-projections-v1", "scraped_at": scraped_at,
            "source_week": source_week, "weeks": weeks,
            "not_offered_weeks": not_offered, "errors": errors}


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
    page_counts: dict[str, int] = {}
    for pos in POSITIONS:
        url = BASE.format(pos=pos)
        page_urls[pos] = url
        print(f"  fetching {pos} ...", flush=True)
        html = fetch(url)
        rows, review = parse_position(pos, html)
        print(f"    {len(rows)} players, {len(review)} review rows")
        page_counts[pos] = len(rows)
        all_rows.extend(rows)
        all_review.extend(review)

    if not all_rows:
        raise SystemExit("Fail closed: no players parsed from any CBS page.")
    # A position page that parses to nothing is a page change or a block, not
    # an empty position: publishing the other three would silently drop it.
    empty = [p for p in POSITIONS if not page_counts.get(p)]
    if empty:
        raise SystemExit(f"Fail closed: no players parsed for {', '.join(empty)}.")

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
    try:
        weekly = pull_weekly(content_week(datetime.strptime(args.date, "%Y-%m-%d").date()),
                             utc_now())
    except Exception as exc:  # noqa: BLE001 -- the ROS snapshot above is already safe
        weekly = {"schema": "cbs-weekly-projections-v1", "weeks": {}, "not_offered_weeks": [],
                  "errors": [f"pull_weekly: {exc}"]}
    (out_dir / "weekly_snapshot.json").write_text(json.dumps(weekly, indent=1) + "\n",
                                                  encoding="utf-8")
    print(f"CBS weekly pages: weeks {sorted(map(int, weekly['weeks']))}, "
          f"not offered {weekly['not_offered_weeks']}, errors {len(weekly['errors'])}")
    if all_review:
        print(f"  ({len(all_review)} review rows excluded fail-closed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
