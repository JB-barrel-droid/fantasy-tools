#!/usr/bin/env python3
"""JEG-427: pull FantasyCalc for the one saved league setup (12 teams, 1 QB),
plus FantasyCalc's own superflex / 2-QB lists (12 teams, numQbs=2).

Decision league-settings-001 (docs/decisions.md): the backend saves one league
setup, 12 teams, for each scoring format; every other team count and roster is
derived in the browser. So this pulls exactly three FantasyCalc lists
(standard / half / full PPR at numTeams=12, numQbs=1) and writes them in the
cache shape save_fantasycalc_references.py reads:

    <cache-dir>/fantasycalc_<scoring>_12_qb1.json
      {"fetched_at", "week", "week_evidence", "url", "rows": [{"name","pos","team","value","fantasycalc_id"}]}
    <cache-dir>/fantasycalc_<scoring>_12_qb2.json   (same shape, numQbs=2)

The numQbs=2 lists are FantasyCalc's superflex values (GAP-SUPERFLEX-PUBLISHER-
VALUES), saved as qb_slots = 2 rows and used only when the chart's roster has
a superflex slot. They never hold the 1-QB save: a 2-QB list that fails the
same checks is reported and not written, and the 1-QB lists save as before.

Week (JEG-87 rule): FantasyCalc's /values/current carries no week, so the week
is asserted from the CONTENT week (pipelines/nfl_week.py, flips Tuesday -- the
calendar the import-health gate and rebuild chain judge freshness by; the
watchdog's _common.nfl_week flips Thursday and would label a Tuesday save one
week stale) and recorded as week_evidence with week_url=None,
week_titles=[] -- consumers can see the evidence is request-asserted.

Fail closed: if any of the three lists has fewer than MIN_ROWS players, or the
three disagree wildly in size, nothing is written (a 2026-10-05 outage returned
a partial pull that then flowed into a table write two mornings running).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from nfl_week import content_week  # noqa: E402

API = "https://api.fantasycalc.com/values/current?isDynasty=false&numQbs={qbs}&numTeams=12&ppr={ppr}"
QB_SLOTS = (1, 2)  # 1 = the saved 1-QB setup; 2 = FantasyCalc's superflex lists
SCORINGS = {"standard": 0, "half": 0.5, "full": 1}
MIN_ROWS = 150          # the live 12-team list holds ~200 players
MAX_SIZE_SPREAD = 0.2   # the three scoring lists price nearly the same pool


def fantasycalc_url(scoring: str, qb_slots: int = 1) -> str:
    return API.format(qbs=qb_slots, ppr=SCORINGS[scoring])


def fetch(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def to_rows(payload: list[dict]) -> list[dict]:
    rows = []
    for p in payload:
        pl = p.get("player") or {}
        name, value = pl.get("name"), p.get("value")
        if not name or value is None:
            continue
        rows.append({"name": name, "pos": pl.get("position"), "team": pl.get("maybeTeam") or pl.get("team"),
                     "value": float(value), "fantasycalc_id": pl.get("id")})
    return rows


def check_pull(lists: dict[str, list[dict]]) -> list[str]:
    problems = [f"{s}: {len(r)} players (< {MIN_ROWS})" for s, r in lists.items() if len(r) < MIN_ROWS]
    sizes = [len(r) for r in lists.values()]
    if sizes and max(sizes) and (max(sizes) - min(sizes)) / max(sizes) > MAX_SIZE_SPREAD:
        problems.append(f"list sizes disagree: {dict((s, len(r)) for s, r in lists.items())}")
    return problems


def main(argv: list[str] | None = None, fetch_fn=fetch) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", type=Path, required=True)
    ap.add_argument("--week", type=int, default=None, help="default: content week (pipelines/nfl_week.py)")
    args = ap.parse_args(argv)
    week = args.week or content_week()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    lists = {s: to_rows(fetch_fn(fantasycalc_url(s))) for s in SCORINGS}
    problems = check_pull(lists)
    if problems:
        for p in problems:
            print(f"FAIL-CLOSED: {p}; nothing written", file=sys.stderr)
        return 2

    # Superflex lists: the same checks, but a failure only skips them.
    try:
        superflex = {s: to_rows(fetch_fn(fantasycalc_url(s, 2))) for s in SCORINGS}
        sf_problems = check_pull(superflex)
    except Exception as exc:  # noqa: BLE001 -- a 2-QB outage must not stop the 1-QB save
        superflex, sf_problems = {}, [f"fetch failed: {exc}"]
    if sf_problems:
        for p in sf_problems:
            print(f"WARNING: superflex (numQbs=2) {p}; superflex lists not written", file=sys.stderr)
        superflex = {}

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    for qb_slots, by_scoring in ((1, lists), (2, superflex)):
        for scoring, rows in by_scoring.items():
            payload = {
                "fetched_at": fetched_at,
                "week": week,
                "week_evidence": {"requested_week": week, "asserted_from": "pipelines/nfl_week.py (content week)",
                                  "week_url": None, "week_titles": []},
                "url": fantasycalc_url(scoring, qb_slots),
                "rows": rows,
            }
            out = args.cache_dir / f"fantasycalc_{scoring}_12_qb{qb_slots}.json"
            out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
            print(f"wrote {out} ({len(rows)} players, week {week})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
