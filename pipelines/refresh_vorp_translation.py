#!/usr/bin/env python3
"""Weekly refresh of the VORP translation tables (JEG-70).

Runs the unified VORP translation module (JEG-62) for all 21 as-published
grains and writes the results to Supabase, then runs a freshness checkpoint.

Grains (21):
  usatoday, fantasypros, cbs : 12-team x {standard, half_ppr, ppr}      (9)
  fantasycalc                : {8,10,12,14}-team x {standard, half_ppr, ppr} (12)

FantasyCalc qb2 8/10/14 combos are intentionally NOT written: the JEG-62 grain
has no qb dimension and qb2 natives diverge materially, so those combos stay
pinned to reindex-fallback by the data-driven guard in translate_via_vorp.py.
Do not serve the qb1 grain to qb2 combos.

Fail-closed: any grain whose Supabase write raises aborts the run (nonzero
exit) -- a partial refresh must never look complete. The freshness checkpoint
queries publisher_translated_values for the max grain week per source and
fails loudly when any expected grain is missing or below the target week, so
the JEG-64 reindex fallback can never become the silent steady state.

Usage:
    python3 pipelines/refresh_vorp_translation.py [--week N] [--no-checkpoint]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "vorp_translation"))

from nfl_week import current_nfl_week
from unified import translate_source, TBL_TRANSLATED

GRAINS: list[tuple[str, int]] = (
    [("usatoday", 12), ("fantasypros", 12), ("cbs", 12)]
    + [("fantasycalc", t) for t in (8, 10, 12, 14)]
)
SCORINGS = ("standard", "half_ppr", "ppr")
SEASON = 2026


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


def freshness_checkpoint(week: int) -> None:
    """Fail closed when any expected grain is missing or stale in Supabase."""
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
        for scoring in SCORINGS:
            key = (source, scoring, teams)
            grain_week = seen.get(key, 0)
            if grain_week < week:
                problems.append(
                    f"{source}/{scoring}/{teams}t: grain week {grain_week} < {week}"
                )
    if problems:
        raise SystemExit(
            "VORP translation freshness checkpoint FAILED:\n  "
            + "\n  ".join(problems)
        )
    print(f"Freshness checkpoint OK: all 21 grains at week {week}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", type=int, default=None,
                        help="NFL week (default: current from nfl_week.py)")
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Skip the Supabase freshness checkpoint")
    args = parser.parse_args()

    week = args.week or current_nfl_week()
    print(f"VORP translation refresh: season {SEASON}, week {week} "
          f"({len(GRAINS) * len(SCORINGS)} grains)")

    failures: list[str] = []
    for source, teams in GRAINS:
        for scoring in SCORINGS:
            label = f"{source}/{scoring}/{teams}t"
            try:
                refresh_grain(source, scoring, teams, week)
            except Exception as e:  # noqa: BLE001 -- fail-closed per grain
                failures.append(f"{label}: {e}")
                print(f"  {label}: FAILED: {e}", flush=True)
    if failures:
        raise SystemExit(
            "VORP translation refresh FAILED for "
            f"{len(failures)} grain(s):\n  " + "\n  ".join(failures)
        )

    if not args.no_checkpoint:
        freshness_checkpoint(week)

    print("VORP translation refresh complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
