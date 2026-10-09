#!/usr/bin/env python3
"""Weekly refresh of the VORP translation tables (JEG-70).

Runs the unified VORP translation module (JEG-62) for all 12-team as-published
grains and writes the results to Supabase, then runs a freshness checkpoint.

Grains (12):
  usatoday, fantasypros, cbs, fantasycalc : 12-team x {standard, half_ppr, ppr}

FantasyCalc 8/10/14-team grains were retired from the fixture by
league-settings-001; translate_source raises SystemExit for them (not caught
by the per-grain `except Exception`), so they must not be listed here.
FantasyCalc qb2 combos are intentionally NOT written: the JEG-62 grain
has no qb dimension and qb2 natives diverge materially, so those combos stay
pinned to reindex-fallback. Do not serve the qb1 grain to qb2 combos.
Since JEG-482 the grains are a record only: no saved chart value is read
from publisher_translated_values (Indexed is a one-factor rescale).

Grain week = the SOURCE's content week (GAP-VORP-GRAIN-WEEK-LABEL,
2026-10-08): each source's grain is labelled with the week of the natives it
was computed from (the fixture section's week, nfl_week.
section_content_week), never the chain week. A CBS section still on Week 4
while the chain runs in Week 5 is stored as week 4. --week is the chain week;
it is printed for the log only.

Fail-closed: any grain whose Supabase write raises aborts the run (nonzero
exit) -- a partial refresh must never look complete. The freshness checkpoint
queries publisher_translated_values for the max grain week per source and
fails loudly when any expected grain is missing or below that source's
content week, so the JEG-64 reindex fallback can never become the silent
steady state. A source whose content week cannot be read fails closed.

Usage:
    python3 pipelines/refresh_vorp_translation.py [--week N] [--no-checkpoint]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "vorp_translation"))

import json

from nfl_week import current_nfl_week
from nfl_week import section_content_week
from unified import translate_source, TBL_TRANSLATED

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"

GRAINS: list[tuple[str, int]] = (
    [("usatoday", 12), ("fantasypros", 12), ("cbs", 12), ("fantasycalc", 12)]
)
SCORINGS = ("standard", "half_ppr", "ppr")
SEASON = 2026


def source_content_weeks(fixture: dict | None = None) -> dict[str, int | None]:
    """{source: content week of its natives in the fixture} for every grain source."""
    fixture = fixture if fixture is not None else json.loads(FIXTURE.read_text())
    sections = fixture.get("sources") or {}
    return {source: section_content_week(sections.get(source)) for source, _ in GRAINS}


def refresh_grain(source: str, scoring: str, teams: int, week: int) -> int:
    """Translate one grain and write to Supabase. Returns translated count."""
    result = translate_source(
        source, scoring, teams, week,
        bench_per_team=6.0,
        write_supabase=True,
    )
    n = len(result["translated"])
    print(f"  {source:12} {scoring:9} {teams:2}t  week {week}: {n} translated", flush=True)
    return n


def _sb():
    bin_dir = Path.home() / "workspace" / "skills" / "supabase-football-signal" / "bin"
    if str(bin_dir) not in sys.path:
        sys.path.insert(0, str(bin_dir))
    import sbclient  # noqa: E402
    return sbclient


def freshness_checkpoint(weeks: dict[str, int | None]) -> None:
    """Fail closed when any expected grain is missing or below its source's
    content week in Supabase (weeks: source_content_weeks())."""
    sbclient = _sb()
    rows = sbclient.get_all(
        TBL_TRANSLATED,
        params=f"select=source,scoring,league_teams,week,season&season=eq.{SEASON}",
    )
    seen: dict[tuple[str, str, int], int] = {}
    for r in rows:
        key = (r["source"], r["scoring"], r["league_teams"])
        seen[key] = max(seen.get(key, 0), r["week"])

    problems: list[str] = []
    for source, teams in GRAINS:
        week = weeks.get(source)
        if week is None:
            problems.append(f"{source}: content week unreadable from the fixture section")
            continue
        for scoring in SCORINGS:
            key = (source, scoring, teams)
            grain_week = seen.get(key, 0)
            if grain_week < week:
                problems.append(
                    f"{source}/{scoring}/{teams}t: grain week {grain_week} < content week {week}"
                )
    if problems:
        raise SystemExit(
            "VORP translation freshness checkpoint FAILED:\n  "
            + "\n  ".join(problems)
        )
    print(f"Freshness checkpoint OK: all {len(GRAINS) * len(SCORINGS)} grains at their "
          f"content weeks {weeks}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", type=int, default=None,
                        help="chain week, for the log (default: content week, nfl_week.py); "
                             "each grain is labelled with its source's content week")
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Skip the Supabase freshness checkpoint")
    parser.add_argument("--check-only", action="store_true",
                        help="Exit 0 if all grains are fresh, 1 if any stale; "
                             "writes nothing (for staleness-gated callers)")
    args = parser.parse_args()

    chain_week = args.week or current_nfl_week()
    weeks = source_content_weeks()

    if args.check_only:
        try:
            freshness_checkpoint(weeks)
        except SystemExit as e:
            print(f"VORP grains stale (chain week {chain_week}); refresh needed.")
            print(e)
            return 1
        return 0

    print(f"VORP translation refresh: season {SEASON}, chain week {chain_week}, "
          f"grain weeks {weeks} ({len(GRAINS) * len(SCORINGS)} grains)")

    failures: list[str] = []
    for source, teams in GRAINS:
        for scoring in SCORINGS:
            label = f"{source}/{scoring}/{teams}t"
            if weeks.get(source) is None:
                failures.append(f"{label}: content week unreadable from the fixture section")
                continue
            try:
                refresh_grain(source, scoring, teams, weeks[source])
            except Exception as e:  # noqa: BLE001 -- fail-closed per grain
                failures.append(f"{label}: {e}")
                print(f"  {label}: FAILED: {e}", flush=True)
    if failures:
        raise SystemExit(
            "VORP translation refresh FAILED for "
            f"{len(failures)} grain(s):\n  " + "\n  ".join(failures)
        )

    if not args.no_checkpoint:
        freshness_checkpoint(weeks)

    print("VORP translation refresh complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
