#!/usr/bin/env python3
"""Check if source data has changed since the last fixture build."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_PATH = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
SUPABASE_SKILL_BIN = os.environ.get(
    "SUPABASE_FOOTBALL_SIGNAL_BIN",
    os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"),
)

CHAIN_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "espn", "cbs", "cbsros", "razzball")

SOURCE_TABLES = {
    "fantasycalc": "public.source_trade_values",
    "usatoday": "public.source_trade_values",
    "fantasypros": "public.source_trade_values",
    "espn": "public.espn_season_projections",
    "cbs": "public.cbs_trade_values",
    "cbsros": "public.cbs_ros_projections",
    "razzball": "public.razzball_projections",
}
def _get_supabase_rows(table: str, params: str) -> list[dict[str, Any]]:
    if SUPABASE_SKILL_BIN not in sys.path:
        sys.path.insert(0, SUPABASE_SKILL_BIN)
    from sbclient import get_all
    rows = get_all(table, params=params)
    if not isinstance(rows, list):
        raise SystemExit(f"Unexpected Supabase response for {table}: {type(rows)}")
    return [row for row in rows if isinstance(row, dict)]

def _select_latest_week(rows):
    weeks = sorted({r.get("week") for r in rows if r.get("week") is not None})
    if not weeks:
        return rows, None
    return [r for r in rows if r.get("week") == weeks[-1]], weeks[-1]

def _select_latest_bake(rows):
    bakes = {}
    for r in rows:
        bakes.setdefault(r.get("bake_id"), []).append(r)
    if len(bakes) == 1:
        return rows, next(iter(bakes))
    stamps = {b: [r.get("created_at") for r in rs if r.get("created_at")] for b, rs in bakes.items()}
    if not any(stamps.values()):
        return rows, next(iter(bakes))
    best = max(bakes, key=lambda b: (max(stamps[b]) if stamps[b] else "", str(b or "")))
    return bakes[best], best

def _select_latest_snapshot_date(rows, *, date_key):
    dates = sorted({r.get(date_key) for r in rows if r.get(date_key)})
    if not dates:
        return rows, None
    return [r for r in rows if r.get(date_key) == dates[-1]], dates[-1]

def _derive_db_vintage(rows, source):
    date_column = "espn_snapshot_date" if source == "espn" else "source_content_date"
    dates = sorted({str(r.get(date_column)) for r in rows if r.get(date_column)})
    weeks = sorted({r.get("week") for r in rows if r.get("week") not in (None, "")})
    if len(dates) > 1:
        raise SystemExit(f"Fail closed: mixed {date_column} values {dates}")
    if len(weeks) > 1:
        raise SystemExit(f"Fail closed: mixed week values {weeks}")
    if dates:
        return dates[0]
    if weeks:
        return f"Week {weeks[0]}"
    raise SystemExit(f"Fail closed: vintage undeterminable for {source}")

def get_current_vintage(source):
    table = SOURCE_TABLES[source]
    params_map = {
        "fantasycalc": f"?select=*&source=eq.{source}&variant=eq.as_published",
        "usatoday": f"?select=*&source=eq.{source}&variant=eq.as_published",
        "fantasypros": f"?select=*&source=eq.{source}&variant=eq.as_published",
        "espn": "?select=*", "cbs": "?select=*", "cbsros": "?select=*", "razzball": "?select=*",
    }
    rows = _get_supabase_rows(table, params_map.get(source, "?select=*"))
    if not rows:
        raise SystemExit(f"Fail closed: source {source} returned zero rows")
    if source in ("fantasycalc", "usatoday", "fantasypros"):
        rows, _ = _select_latest_week(rows)
        rows, _ = _select_latest_bake(rows)
    elif source == "espn":
        rows, _ = _select_latest_snapshot_date(rows, date_key="espn_snapshot_date")
    if not rows:
        raise SystemExit(f"Fail closed: source {source} returned zero rows after scoping")
    return _derive_db_vintage(rows, source)

def get_fixture_vintage(source, fixture_data):
    return fixture_data.get("sources", {}).get(source, {}).get("vintage")

def check_all_sources():
    if not DEFAULT_FIXTURE_PATH.exists():
        raise SystemExit(f"Fixture not found: {DEFAULT_FIXTURE_PATH}")
    fixture_data = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    results = {"sources": {}, "changed": False}
    for source in CHAIN_SOURCES:
        sr = {}
        try:
            sr["current_vintage"] = get_current_vintage(source)
        except Exception as e:
            sr["error"] = str(e)
            sr["current_vintage"] = None
            sr["fixture_vintage"] = None
            sr["changed"] = True
            results["sources"][source] = sr
            results["changed"] = True
            continue
        sr["fixture_vintage"] = get_fixture_vintage(source, fixture_data)
        sr["changed"] = sr["current_vintage"] != sr["fixture_vintage"]
        if sr["changed"]:
            results["changed"] = True
        results["sources"][source] = sr
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = check_all_sources()
    except Exception as e:
        result = {"error": str(e), "changed": True, "sources": {}}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Changed: {result[""changed""]}")
        for source, sr in result.get("sources", {}).items():
            print(f"  {source}: {sr.get(""current_vintage"")} vs {sr.get(""fixture_vintage"")} ({""CHANGED"" if sr.get(""changed"") else ""same""})")
    sys.exit(0 if not result[""changed""] else 1)

if __name__ == "__main__":
    main()
