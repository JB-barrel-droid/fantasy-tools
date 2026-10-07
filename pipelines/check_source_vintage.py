#!/usr/bin/env python3
"""Check if source data has changed since the last fixture build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_PATH = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
# JEG-205: persisted code-version stamp for the hourly check. The workflow
# records the pipelines/ hash here each time it dispatches on a code change;
# the hash is the loop guard (exactly one dispatch per code change).
CODE_STATE_PATH = ROOT / ".github" / "source-vintage-state.json"
STATE_FIELD_LAST_CODE_HASH = "last_code_hash"
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
    """Derive vintage from DB rows. Matches canonical logic from import_supabase_references.py."""
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
    """Get the current vintage for a source from the database."""
    table = SOURCE_TABLES[source]
    # Base params - will be modified based on source-specific scoping
    base_params = "?select=*"

    if source in ("fantasycalc", "usatoday", "fantasypros"):
        # These use source_trade_values with source + variant filters, plus week + bake scoping
        params = f"{base_params}&source=eq.{source}&variant=eq.as_published"
        rows = _get_supabase_rows(table, params)
        if not rows:
            raise SystemExit(f"Fail closed: source {source} returned zero rows")
        rows, _ = _select_latest_week(rows)
        rows, _ = _select_latest_bake(rows)
    elif source == "espn":
        # ESPN uses espn_snapshot_date for scoping
        params = base_params
        rows = _get_supabase_rows(table, params)
        if not rows:
            raise SystemExit(f"Fail closed: source {source} returned zero rows")
        rows, _ = _select_latest_snapshot_date(rows, date_key="espn_snapshot_date")
    elif source == "cbs":
        # CBS: source=eq.cbs&variant=eq.as_published plus latest-week + latest-bake scoping
        # Matches canonical logic from import_supabase_references.py lines 628-648
        params = f"{base_params}&source=eq.cbs&variant=eq.as_published"
        rows = _get_supabase_rows(table, params)
        if not rows:
            raise SystemExit(f"Fail closed: source {source} returned zero rows")
        rows, _ = _select_latest_week(rows)
        rows, _ = _select_latest_bake(rows)
    elif source == "cbsros":
        # CBSROS: scopes to latest cbs_snapshot_date
        # Matches canonical logic from import_supabase_references.py lines 723-736
        params = base_params
        rows = _get_supabase_rows(table, params)
        if not rows:
            raise SystemExit(f"Fail closed: source {source} returned zero rows")
        rows, _ = _select_latest_snapshot_date(rows, date_key="cbs_snapshot_date")
    elif source == "razzball":
        # Razzball: scopes to latest razzball_snapshot_date
        # Matches canonical logic from import_supabase_references.py lines 883-893
        params = base_params
        rows = _get_supabase_rows(table, params)
        if not rows:
            raise SystemExit(f"Fail closed: source {source} returned zero rows")
        rows, _ = _select_latest_snapshot_date(rows, date_key="razzball_snapshot_date")
    else:
        raise SystemExit(f"Unknown source: {source}")

    if not rows:
        raise SystemExit(f"Fail closed: source {source} returned zero rows after scoping")

    return _derive_db_vintage(rows, source)


# Mapping of sources to their vintage key in the fixture
# Based on analysis of data/fixtures/current/comparison-sources-data.json
FIXTURE_VINTAGE_KEYS = {
    "fantasycalc": "content_vintage",
    "usatoday": "content_vintage",
    "fantasypros": "content_vintage",
    "espn": "espn_snapshot",
    "cbs": "content_vintage",
    "cbsros": "vintage",  # cbsros uses "vintage" key
    "razzball": "vintage",  # razzball uses "vintage" key
}


def get_fixture_vintage(source, fixture_data):
    """Get the fixture vintage for a source, using the correct key."""
    sources_data = fixture_data.get("sources", {})
    source_data = sources_data.get(source, {})

    # Get the correct vintage key for this source
    vintage_key = FIXTURE_VINTAGE_KEYS.get(source, "vintage")

    # Try the correct key first
    if vintage_key in source_data:
        return source_data.get(vintage_key)

    # Fallback to legacy "vintage" key for backward compatibility
    return source_data.get("vintage")


def compute_pipelines_code_hash(repo_root=ROOT):
    """Deterministic SHA-256 over the pipelines/ tree (JEG-205).

    Walks pipelines/ in sorted relative-path order, hashing each relative
    path and its bytes. Excludes __pycache__ and *.pyc so bytecode churn
    never counts as a code change. Raises on any failure -- callers apply
    the fail-safe policy (trigger on uncertainty).
    """
    pipelines_dir = Path(repo_root) / "pipelines"
    if not pipelines_dir.is_dir():
        raise FileNotFoundError(f"pipelines/ not found under {repo_root}")
    files = []
    for p in pipelines_dir.rglob("*"):
        if p.is_dir():
            continue
        if "__pycache__" in p.parts:
            continue
        if p.suffix == ".pyc":
            continue
        files.append(p)
    if not files:
        raise FileNotFoundError(f"no files under {pipelines_dir}")
    h = hashlib.sha256()
    for p in sorted(files, key=lambda q: q.relative_to(pipelines_dir).as_posix()):
        rel = p.relative_to(pipelines_dir).as_posix().encode("utf-8")
        h.update(rel + b"\x00" + p.read_bytes() + b"\x00")
    return h.hexdigest()


def check_code_change(state_path=CODE_STATE_PATH, repo_root=ROOT):
    """Compare the current pipelines/ hash vs the persisted stamp (JEG-205).

    Reads from Supabase when SUPABASE_URL + SUPABASE_SERVICE_KEY are set (CI);
    falls back to the local state file otherwise (local dev / tests).

    Never raises: any failure to compute the hash or read the state is
    fail-safe (code_changed=True -- a code change earns its chain run,
    and uncertainty triggers rather than skips).
    """
    try:
        current = compute_pipelines_code_hash(repo_root)
    except BaseException as e:
        return {"code_changed": True, "code_hash": None,
                "reason": f"fail-safe: cannot hash pipelines/: {e}"}

    # Try Supabase first when credentials are available (CI path).
    recorded = None
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
        try:
            recorded = _read_code_hash_supabase()
        except Exception as e:
            return {"code_changed": True, "code_hash": current,
                    "reason": f"fail-safe: cannot read code hash from Supabase: {e}"}
    else:
        # Local dev: fall back to the file.
        try:
            state = json.loads(Path(state_path).read_text(encoding="utf-8"))
            recorded = state.get(STATE_FIELD_LAST_CODE_HASH) if isinstance(state, dict) else None
        except BaseException as e:
            return {"code_changed": True, "code_hash": current,
                    "reason": f"fail-safe: cannot read state file: {e}"}

    if not recorded:
        return {"code_changed": True, "code_hash": current,
                "reason": "fail-safe: no recorded hash (first run)"}
    if recorded != current:
        return {"code_changed": True, "code_hash": current,
                "reason": "pipelines/ hash differs from recorded stamp"}
    return {"code_changed": False, "code_hash": current,
            "reason": "pipelines/ hash matches recorded stamp"}


def record_code_hash(state_path, code_hash):
    """Persist the dispatched code hash (JEG-205). Preserves other state fields.

    Legacy file-based path used for local dev and fallback. In CI, use
    record_code_hash_supabase() instead (JEG-414 follow-up).
    """
    path = Path(state_path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except BaseException:
        state = {}
    state[STATE_FIELD_LAST_CODE_HASH] = code_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def record_code_hash_supabase(code_hash: str) -> None:
    """Store the dispatched code hash in Supabase public.ops_artifacts (JEG-414 follow-up).

    Replaces the git-commit path (record_code_hash + git push to main).
    Raises OpsArtifactError on Supabase failure so the caller can surface it.
    """
    import ops_artifact_store as store  # noqa: PLC0415
    store.upsert(store.CODE_HASH, {"last_code_hash": code_hash})


def _read_code_hash_supabase() -> str | None:
    """Read the last recorded code hash from Supabase (JEG-414 follow-up).

    Returns None on any failure (fail-safe: treats missing as code_changed=True).
    """
    try:
        import ops_artifact_store as store  # noqa: PLC0415
        payload = store.fetch(store.CODE_HASH, use_service_key=True)
        if payload and isinstance(payload.get("last_code_hash"), str):
            return payload["last_code_hash"]
    except Exception:
        pass
    return None


def check_all_sources():
    """Check all sources and return results."""
    results = {"sources": {}, "changed": False}
    # JEG-205: pipeline-code changes also earn a chain run. This check never
    # raises: any failure to compute or read state is fail-safe (trigger).
    code = check_code_change()
    results["code_changed"] = code["code_changed"]
    results["code_hash"] = code["code_hash"]
    results["code_change_reason"] = code["reason"]
    if code["code_changed"]:
        results["changed"] = True
    if not DEFAULT_FIXTURE_PATH.exists():
        raise SystemExit(f"Fixture not found: {DEFAULT_FIXTURE_PATH}")
    fixture_data = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    for source in CHAIN_SOURCES:
        sr = {}
        try:
            sr["current_vintage"] = get_current_vintage(source)
        except BaseException as e:
            # Catch SystemExit and other exceptions
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
    except BaseException as e:
        # Catch SystemExit so --json still emits a report on fail-closed paths.
        # JEG-205: the code-change fields are always reported, even here.
        result = {"error": str(e), "changed": True, "sources": {}}
        code = check_code_change()
        result["code_changed"] = code["code_changed"]
        result["code_hash"] = code["code_hash"]
        result["code_change_reason"] = code["reason"]
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f'Changed: {result["changed"]}')
        if "code_changed" in result:
            print(f'  code: {"CHANGED" if result["code_changed"] else "same"} '
                  f'({result.get("code_change_reason")})')
        for source, sr in result.get("sources", {}).items():
            print(f'  {source}: {sr.get("current_vintage")} vs {sr.get("fixture_vintage")} ({"CHANGED" if sr.get("changed") else "same"})')
    sys.exit(0 if not result["changed"] else 1)


if __name__ == "__main__":
    main()
