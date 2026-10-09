#!/usr/bin/env python3
"""Store the chain's engine vs Python reference values in Supabase (JEG-479).

Reads the published build's comparison (output/value-check.json and the two
dumps beside it, written by `pipelines/value_check.py compare`) and upserts:

  public.value_check_runs    one row: verdict, tolerance, counts, held sections,
                             the report itself
  public.value_check_values  one row per (scoring, teams, roster, view, series,
                             player) for the current content week: the engine's
                             value, the reference's, agrees (within the report's
                             tolerance, presence exact) and held. Series are the
                             page's 14 plus the three DDF versions and their prior weeks (the
                             DDF Value's prior-week side, keyed by this week).

api.player_values and api.value_check_diff read them
(supabase/migrations/jeg479_value_check.sql). Non-blocking for Pages, like
the consolidation write (JEG-380): the workflow step continues on error and
records the monitored check value_check_write.

Usage:
  python pipelines/load_value_check.py [--report output/value-check.json] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

import value_check as vc  # noqa: E402
import value_reference as ref  # noqa: E402

SCORING = {"ppr": "full", "half_ppr": "half", "standard": "standard"}
CHUNK = 1000


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _agrees(e, r, tol):
    if e is None or r is None:
        return e is None and r is None
    return abs(e - r) <= tol


def player_names(fixture: dict, players: dict) -> dict:
    """player_key -> the fixture's own name key (the `player` column of
    consolidated_values), preferring the one equal to the lowercased name."""
    by_key = {}
    for slug, key in (fixture.get("player_keys") or {}).items():
        if isinstance(key, int):
            by_key.setdefault(key, []).append(slug)
    out = {}
    for key, p in players.items():
        slugs = by_key.get(key) or []
        name = p["name"].strip().lower()
        out[key] = name if name in slugs else (sorted(slugs)[0] if slugs else name)
    return out


def build_rows(report: dict, engine: dict, reference: dict, season: int, week: int,
               names: dict, held_series: set) -> list[dict]:
    tol = float(report.get("tolerance") or vc.TOL)
    rows = []
    for sid, r in reference.items():
        spec = r["setting"]
        e = (engine.get(sid) or {})
        base = {"season": season, "week": week, "scoring": SCORING[spec["scoring"]],
                "teams": int(spec["teams"]), "roster": "superflex" if spec.get("superflex") else "standard"}
        for view in ref.VIEWS:
            series = list(ref.SERIES_KEYS) if view == "indexed" else list(ref.PUBLISHED)
            series.extend(ref.DDF_VERSIONS)
            ev = {int(k): v for k, v in ((e.get("views") or {}).get(view) or {}).items()}
            rv = {int(k): v for k, v in (r["views"].get(view) or {}).items()}
            cells = {}
            for key in series:
                for pk in set(ev) | set(rv):
                    a = _num((ev.get(pk) or {}).get(key))
                    b = _num((rv.get(pk) or {}).get(key))
                    if a is not None or b is not None:
                        cells[(key, pk)] = (a, b)
            for version in ref.DDF_VERSIONS:
                ep = (((e.get("prior") or {}).get(view) or {}).get(version) or {}).get("values") or {}
                rp = (((r.get("prior") or {}).get(view) or {}).get(version) or {}).get("values") or {}
                for pk in {int(k) for k in ep} | {int(k) for k in rp}:
                    a, b = _num(ep.get(str(pk), ep.get(pk))), _num(rp.get(str(pk), rp.get(pk)))
                    if a is not None or b is not None:
                        cells[(f"{version}_prior", pk)] = (a, b)
            for (key, pk), (a, b) in cells.items():
                if pk not in names:
                    continue
                rows.append({**base, "view": view, "series": key, "player_key": pk, "player": names[pk],
                             "engine_value": a, "reference_value": b, "agrees": _agrees(a, b, tol),
                             "held": key in held_series})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", default=str(vc.REPORT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    report_path = Path(args.report)
    _summary, engine_path, reference_path = vc.dumps_for(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    engine = json.loads(engine_path.read_text(encoding="utf-8"))["settings"]
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    inp = ref.Inputs.load()
    from nfl_week import current_nfl_week
    today = datetime.fromisoformat(report.get("today") or datetime.now(timezone.utc).date().isoformat()).date()
    week, season = current_nfl_week(today), today.year
    held_roots = {(h or {}).get("root") for h in (report.get("held_sections") or {}).values()}
    held_series = {s for root in held_roots if root in vc.SOURCE_DERIVED for s in vc.derived_series(root)}
    rows = build_rows(report, engine, reference, season, week, player_names(inp.fixture, inp.players),
                      held_series)
    run = {"generated_at": report["generated_at"], "season": season, "week": week,
           "verdict": report["verdict"], "tolerance": report["tolerance"],
           "values_compared": report["values_compared"],
           "disagreeing_sources": report.get("disagreeing_sources") or [],
           "composite_disagreements": report.get("composite_disagreements") or [],
           "held_sections": report.get("held_sections") or {},
           "fixture_built_at": inp.fixture.get("built_at"),
           "github_run_id": os.environ.get("GITHUB_RUN_ID"),
           "report": {k: v for k, v in report.items() if k != "series"} | {
               "series": {k: {kk: vv for kk, vv in a.items() if kk != "examples"} | {"examples": a["examples"][:3]}
                          for k, a in report["series"].items()}}}
    n_disagree = sum(1 for r in rows if not r["agrees"])
    print(f"value check store: season {season} week {week}, {len(rows)} values "
          f"({n_disagree} disagree), verdict {report['verdict']}")
    if args.dry_run:
        return 0
    import gh_sbclient as sb  # noqa: PLC0415 - env-based client (GitHub Actions secrets)
    created = sb.post("value_check_runs", [run], prefer="return=representation")
    run_id = created[0]["run_id"]
    for row in rows:
        row["run_id"] = run_id
        row["updated_at"] = run["generated_at"]
    for start in range(0, len(rows), CHUNK):
        sb.post("value_check_values", rows[start:start + CHUNK],
                params="?on_conflict=season,week,scoring,teams,roster,view,series,player_key",
                prefer="resolution=merge-duplicates,return=minimal")
    # Values an earlier run stored for this week that this run no longer has.
    sb.delete("value_check_values", f"?season=eq.{season}&week=eq.{week}&run_id=neq.{run_id}")
    print(f"stored run {run_id}: {len(rows)} values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
