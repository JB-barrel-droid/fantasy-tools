#!/usr/bin/env python3
"""Import scraped trade-value references from Supabase into versioned snapshots.

Stage 1 of the repo import chain: Supabase -> data/raw/sources/.

All five dashboard sources (fantasycalc, usatoday, fantasypros, espn, cbs)
are DB-backed. The big three read public.source_trade_values
(variant='as_published' only -- that is the source's own scraped value;
'bias_adjusted' is our fitted calibration and is never imported here).
ESPN reads public.espn_season_projections and CBS reads
public.cbs_trade_values (their tables were DDL'd 2026-09-22 and loaded by
pipelines/save_espn_cbs_references.py -- stage 1b closed).

Snapshots use schema "trade-value-source-snapshot-v1" -- the SAME record shape
as pipelines/import_source_snapshot.py, so the downstream
match -> reference -> section chain works unchanged. Normalization helpers
(parse_float, parse_int, normalize_scoring, first_value, slug) are imported
from that module rather than duplicated.

Every snapshot is content-vintage-stamped and written to
data/raw/sources/<source>/<content-vintage>/snapshot.json with a
snapshot-manifest.json sidecar. Pull time is recorded as pull time and is
never presented as vintage.

Provenance migration: the espn/cbs snapshots that were stamped from FILE
caches (save_gap='no-supabase-table-stage1b') are superseded by the DB-backed
imports. When a stamped snapshot exists for the same (source, vintage) but
the new import's provenance (supabase_table / from_file / save_gap) differs,
the old pair is archived under <vintage-dir>/_superseded/<timestamp>/ and the
new pair is stamped with manifest["supersedes"] recording the old sha. Same
provenance with different bytes still fails closed -- a stamped snapshot is
never silently replaced.

Fail-closed guards (each negative-tested in tests/test_supabase_import.py):
  - unknown source name (ECR/Vegas/Razzball can never sneak in)
  - source resolves to zero rows (never writes an empty snapshot)
  - content vintage undeterminable (NULL source_content_date AND no week/file vintage)
  - stamped snapshot exists with different bytes under the SAME provenance
    (no silent overwrite)
  - non-numeric player_key or non-numeric/non-null value -> review_rows, never guessed/zero-filled
  - fantasypros: ECR-flavored rows excluded even if the table filter is widened
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "raw" / "sources"
MANIFEST_SCHEMA = "trade-value-source-manifest-v1"
SUPABASE_TABLE = "public.source_trade_values"

sys.path.insert(0, str(ROOT / "pipelines"))
from import_source_snapshot import (  # noqa: E402
    SCHEMA,
    first_value,
    normalize_scoring,
    parse_float,
    parse_int,
    slug,
    utc_now,
)

DB_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "espn", "cbs")
DASHBOARD_SOURCES = DB_SOURCES

# Supabase table per source. The big three share public.source_trade_values;
# ESPN and CBS have their own reference tables (stage 1b closed 2026-09-22).
SOURCE_TABLES = {
    "fantasycalc": "public.source_trade_values",
    "usatoday": "public.source_trade_values",
    "fantasypros": "public.source_trade_values",
    "espn": "public.espn_season_projections",
    "cbs": "public.cbs_trade_values",
}

# Sources that must never be importable here, even if someone names them.
HARD_EXCLUSIONS = ("ecr", "vegas", "razzball", "prediction_markets", "prediction-markets")

# Repo reference-level scoring vocabulary: ppr/half_ppr/standard (the fixture
# maps these onto full/half/standard at the comparison stage).
REPO_SCORING_OVERRIDES = {"full": "ppr"}


def repo_scoring(raw: Any) -> str | None:
    """Map a source scoring label onto the repo reference vocabulary."""
    normalized = normalize_scoring(raw)
    if normalized is None:
        return None
    return REPO_SCORING_OVERRIDES.get(normalized, normalized)


def is_ecr_flavored(source_name: Any) -> bool:
    """Backstop: any source string smelling of ECR is excluded, always."""
    return "ecr" in str(source_name or "").lower()


def check_source(source: str) -> str:
    name = str(source or "").strip().lower()
    if name in HARD_EXCLUSIONS or is_ecr_flavored(name):
        raise SystemExit(
            f"Refusing to import '{source}': not a dashboard trade-value source "
            f"(hard exclusions: ECR, Vegas, Razzball, prediction markets)."
        )
    if name not in DASHBOARD_SOURCES:
        raise SystemExit(
            f"Unknown source '{source}'. Importable dashboard sources: "
            f"{', '.join(DASHBOARD_SOURCES)}."
        )
    return name


# ---------------------------------------------------------------------------
# Supabase access (read-only). Module-level callables so tests can inject
# recorded fixtures without touching the network.
# ---------------------------------------------------------------------------

def _default_supabase_rows(table: str, params: str) -> list[dict[str, Any]]:
    sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
    from sbclient import get_all  # noqa: E402

    rows = get_all(table, params=params)
    if not isinstance(rows, list):
        raise SystemExit(f"Unexpected Supabase response for {table}: {type(rows)}")
    return [row for row in rows if isinstance(row, dict)]


def _default_player_names(keys: list[int]) -> dict[int, str]:
    """Resolve canonical full_name for numeric player_keys via the players table."""
    sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
    from sbclient import get_all  # noqa: E402

    names: dict[int, str] = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start : start + 500]
        in_list = ",".join(str(key) for key in chunk)
        rows = get_all("players", params=f"?select=player_key,full_name&player_key=in.({in_list})")
        for row in rows:
            key = row.get("player_key")
            name = row.get("full_name")
            if isinstance(key, int) and name:
                names[key] = str(name)
    return names


def _default_player_positions(keys: list[int]) -> dict[int, str]:
    """Resolve canonical position for numeric player_keys via the players table.

    The players table carries position but no team column, so pos comes from
    here (canonical) while team comes from the repo fixture players.json map
    (see fixture_pos_team). Documented choice: canonical position from the
    naming-authority table; team from the fixture map.
    """
    sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
    from sbclient import get_all  # noqa: E402

    positions: dict[int, str] = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start : start + 500]
        in_list = ",".join(str(key) for key in chunk)
        rows = get_all("players", params=f"?select=player_key,position&player_key=in.({in_list})")
        for row in rows:
            key = row.get("player_key")
            pos = str(row.get("position") or "").strip().upper() or None
            if isinstance(key, int) and pos:
                positions[key] = pos
    return positions


def fixture_pos_team() -> dict[int, tuple[str | None, str | None]]:
    """player_key -> (pos, team) from the repo fixture players.json.

    Fallback for fields the Supabase players table does not carry (team).
    Pos is taken from the players table (canonical) when available.
    """
    payload = json.loads((ROOT / "data" / "fixtures" / "current" / "players.json").read_text(encoding="utf-8"))
    out: dict[int, tuple[str | None, str | None]] = {}
    for row in payload.get("players", []):
        key = row.get("player_key")
        if isinstance(key, int) and not isinstance(key, bool):
            out[key] = (
                str(row.get("pos") or "").strip().upper() or None,
                str(row.get("team") or "").strip().upper() or None,
            )
    return out


fetch_supabase_rows: Callable[[str, str], list[dict[str, Any]]] = _default_supabase_rows
fetch_player_names: Callable[[list[int]], dict[int, str]] = _default_player_names
fetch_player_positions: Callable[[list[int]], dict[int, str]] = _default_player_positions


def _rel_to_root(path: Path) -> str:
    """Repo-relative path when under the repo tree, absolute otherwise."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Row normalization -> v1 snapshot record shape
# ---------------------------------------------------------------------------

def canonical_player_key(raw: Any) -> int | None:
    """Numeric player_key only. Anything else is unresolved, never guessed."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw or "").strip()
    if text.isdigit():
        return int(text)
    return None


def normalize_db_row(row: dict[str, Any], names: dict[int, str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (clean_row, review_row); exactly one is not None."""
    key = canonical_player_key(row.get("player_key"))
    if key is None:
        return None, {
            "reason": "non_numeric_player_key",
            "player_key_raw": row.get("player_key"),
            "player_norm": row.get("player_norm"),
            "value_raw": row.get("value"),
        }
    name = names.get(key)
    if not name:
        return None, {
            "reason": "unresolved_player_key",
            "player_key": key,
            "player_norm": row.get("player_norm"),
            "value_raw": row.get("value"),
        }
    value = parse_float(row.get("value"))
    if value is None:
        return None, {
            "reason": "missing_or_non_numeric_value",
            "player_key": key,
            "player_name": name,
            "value_raw": row.get("value"),
        }
    teams = parse_int(row.get("league_teams"))
    clean = {
        "player_name": name,
        "value": value,
        "pos": str(row.get("position") or "").strip() or None,
        "team": str(row.get("team") or "").strip() or None,
        "scoring": repo_scoring(row.get("scoring")),
        "teams": teams,
        "source_player_id": key,
        # Carried alongside value: the source's scraped native before any
        # reindexing. Downstream stages ignore unknown keys; this one is for
        # review/copy and for the manifest's provenance note.
        "native_value": parse_float(row.get("native_value")),
    }
    return clean, None


def derive_db_vintage(rows: list[dict[str, Any]], *, date_column: str = "source_content_date") -> tuple[str, str, int | None]:
    """Return (content_vintage, derivation_note, week_or_none).

    The date column (source_content_date, or espn_snapshot_date for ESPN) is
    the honest vintage when the source publishes one. FantasyCalc and CBS
    carry no date by design -- their week column IS the vintage. Multiple
    distinct dates or weeks fail closed: one stamp, one vintage.
    """
    dates = sorted({str(r.get(date_column)) for r in rows if r.get(date_column)})
    weeks = sorted({r.get("week") for r in rows if r.get("week") not in (None, "")})
    if len(dates) > 1:
        raise SystemExit(f"Fail closed: mixed source_content_date values {dates}; cannot stamp one vintage.")
    if len(weeks) > 1:
        raise SystemExit(f"Fail closed: mixed week values {weeks}; cannot stamp one vintage.")
    if dates:
        return dates[0], f"{date_column} (unanimous across {len(rows)} rows)", None
    if weeks:
        week = weeks[0]
        return f"Week {week}", (
            f"week column ({date_column} is NULL by design for this source; "
            "a weekly snapshot, not a dated publication)"
        ), (int(week) if str(week).isdigit() else None)
    raise SystemExit(
        "Fail closed: content vintage undeterminable "
        "(source_content_date is NULL and no week/file vintage available). "
        "A vintage-less snapshot would reset freshness; refusing to write one."
    )


def vintage_dir_slug(content_vintage: str) -> str:
    return slug(content_vintage)


def build_db_snapshot(source: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pull a DB-backed source and return (snapshot, manifest_fields)."""
    if source in ("fantasycalc", "usatoday", "fantasypros"):
        return build_source_trade_values_snapshot(source)
    if source == "espn":
        return build_espn_snapshot()
    if source == "cbs":
        return build_cbs_snapshot()
    raise SystemExit(f"No DB importer defined for source '{source}'")  # unreachable


def build_source_trade_values_snapshot(source: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The big three: public.source_trade_values, variant='as_published' only."""
    params = f"?select=*&source=eq.{source}&variant=eq.as_published"
    raw_rows = fetch_supabase_rows("source_trade_values", params)

    # ECR backstop: the SQL filter names the source, but even if it is widened
    # later, anything ECR-flavored is dropped here and can never be imported.
    ecr_dropped = [r for r in raw_rows if is_ecr_flavored(r.get("source"))]
    rows = [r for r in raw_rows if not is_ecr_flavored(r.get("source"))]
    if not rows:
        raise SystemExit(
            f"Fail closed: source '{source}' resolved to zero usable rows "
            f"({len(ecr_dropped)} ECR-flavored rows dropped). Never writing an empty snapshot."
        )

    content_vintage, vintage_note, week = derive_db_vintage(rows)

    keys = sorted({k for k in (canonical_player_key(r.get("player_key")) for r in rows) if k is not None})
    names = fetch_player_names(keys)

    clean_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for row in rows:
        clean, review = normalize_db_row(row, names)
        if clean is not None:
            clean_rows.append(clean)
        else:
            review_rows.append(review)
    if not clean_rows:
        raise SystemExit(
            f"Fail closed: source '{source}' resolved to zero clean rows "
            f"({len(review_rows)} in review). Never writing an empty snapshot."
        )

    pulled_values = sorted({str(r.get("pulled_at")) for r in rows if r.get("pulled_at")})
    fetched_at = pulled_values[-1] if pulled_values else utc_now()
    teams_values = {r.get("teams") for r in clean_rows}
    default_teams = next(iter(teams_values)) if len(teams_values) == 1 else None

    snapshot = {
        "schema": SCHEMA,
        "source": source,
        "fetched_at": fetched_at,
        "source_url": None,
        "default_scoring": None,  # mixed scorings carried per row
        "default_teams": default_teams,
        "row_count": len(clean_rows),
        "rows": clean_rows,
        # Additive extension to the v1 schema: rows that failed import
        # validation, inspectable in place. The matcher only reads rows[].
        "review_rows": review_rows,
        "review_count": len(review_rows),
    }
    manifest_fields = {
        "supabase_table": SUPABASE_TABLE,
        "from_file": None,
        "filter": (
            f"select=*&source=eq.{source}&variant=eq.as_published "
            f"(as_published only: the source's own scraped value); "
            f"python backstop dropped {len(ecr_dropped)} ECR-flavored row(s)"
        ),
        "content_vintage": content_vintage,
        "content_vintage_derived_from": vintage_note,
        "week_designated": week,
        "save_gap": None,
        "fetched_at_note": "snapshot.fetched_at is the table's pulled_at (pull time), not content vintage",
    }
    return snapshot, manifest_fields


def build_espn_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
    """ESPN: public.espn_season_projections.

    The table stores per-player ROS stat projections verbatim; the snapshot
    carries ros_half_ppr as the row value with scoring='half_ppr' throughout
    (the same shape the old file-backed import produced).
    pos comes from the canonical players table; team from the repo fixture
    players.json map (public.players carries no team column) -- documented
    in fixture_pos_team.
    """
    rows = fetch_supabase_rows("espn_season_projections", "?select=*")
    if not rows:
        raise SystemExit(
            "Fail closed: source 'espn' resolved to zero rows in "
            "public.espn_season_projections. Never writing an empty snapshot."
        )

    content_vintage, vintage_note, table_week = derive_db_vintage(rows, date_column="espn_snapshot_date")

    keys = sorted({k for k in (canonical_player_key(r.get("player_key")) for r in rows) if k is not None})
    names = fetch_player_names(keys)
    positions = fetch_player_positions(keys)
    fixture_map = fixture_pos_team()

    clean_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for row in rows:
        key = canonical_player_key(row.get("player_key"))
        name = names.get(key) if key is not None else None
        value = parse_float(row.get("ros_half_ppr"))
        if key is None:
            review_rows.append(
                {
                    "reason": "non_numeric_player_key",
                    "player_key_raw": row.get("player_key"),
                    "player_norm": row.get("player_norm"),
                }
            )
            continue
        if not name:
            review_rows.append(
                {
                    "reason": "unresolved_player_key",
                    "player_key": key,
                    "player_norm": row.get("player_norm"),
                }
            )
            continue
        if value is None:
            review_rows.append(
                {
                    "reason": "missing_or_non_numeric_value",
                    "player_key": key,
                    "player_name": name,
                    "value_raw": row.get("ros_half_ppr"),
                }
            )
            continue
        fixture_pos, fixture_team = fixture_map.get(key, (None, None))
        clean_rows.append(
            {
                "player_name": name,
                "value": value,
                "pos": positions.get(key) or fixture_pos,
                "team": fixture_team,
                "scoring": "half_ppr",
                "teams": 12,
                "source_player_id": key,
                "native_value": value,
            }
        )
    if not clean_rows:
        raise SystemExit(
            f"Fail closed: source 'espn' resolved to zero clean rows "
            f"({len(review_rows)} in review). Never writing an empty snapshot."
        )

    pulled_values = sorted({str(r.get("pulled_at")) for r in rows if r.get("pulled_at")})
    fetched_at = pulled_values[-1] if pulled_values else utc_now()

    snapshot = {
        "schema": SCHEMA,
        "source": "espn",
        "fetched_at": fetched_at,
        "source_url": None,
        "default_scoring": "half_ppr",
        "default_teams": 12,
        "row_count": len(clean_rows),
        "rows": clean_rows,
        "review_rows": review_rows,
        "review_count": len(review_rows),
    }
    manifest_fields = {
        "supabase_table": SOURCE_TABLES["espn"],
        "from_file": None,
        "filter": (
            "public.espn_season_projections (all rows); value=ros_half_ppr "
            "(Mike Clay ROS half-PPR points); pos from public.players.position, "
            "team from the repo fixture players.json map (players carries no team)"
        ),
        "content_vintage": content_vintage,
        "content_vintage_derived_from": vintage_note,
        # week_designated stays None for ESPN: the health gate must judge the
        # DATED vintage (daily rule), not the designated week. The table week
        # is recorded as table_week for transparency.
        "week_designated": None,
        "table_week": table_week,
        "save_gap": None,
        "fetched_at_note": "snapshot.fetched_at is the table's pulled_at (pull time), not content vintage",
    }
    return snapshot, manifest_fields


def build_cbs_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
    """CBS: public.cbs_trade_values (source='cbs', variant='as_published').

    Same grain as public.source_trade_values, so the generic row path is
    reused. QB rows were saved one-per-scoring with the published 1QB-4 value
    (IMPLIED: CBS publishes no per-scoring QB split -- see
    save_espn_cbs_references.py); they flow into the standard/half_ppr/ppr
    combos exactly like the live fixture's cbs section.
    """
    params = "?select=*&source=eq.cbs&variant=eq.as_published"
    rows = fetch_supabase_rows("cbs_trade_values", params)
    ecr_dropped = [r for r in rows if is_ecr_flavored(r.get("source"))]
    rows = [r for r in rows if not is_ecr_flavored(r.get("source"))]
    if not rows:
        raise SystemExit(
            f"Fail closed: source 'cbs' resolved to zero usable rows "
            f"({len(ecr_dropped)} ECR-flavored rows dropped). Never writing an empty snapshot."
        )

    content_vintage, vintage_note, week = derive_db_vintage(rows)

    keys = sorted({k for k in (canonical_player_key(r.get("player_key")) for r in rows) if k is not None})
    names = fetch_player_names(keys)

    clean_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for row in rows:
        clean, review = normalize_db_row(row, names)
        if clean is not None:
            clean_rows.append(clean)
        else:
            review_rows.append(review)
    if not clean_rows:
        raise SystemExit(
            f"Fail closed: source 'cbs' resolved to zero clean rows "
            f"({len(review_rows)} in review). Never writing an empty snapshot."
        )

    pulled_values = sorted({str(r.get("pulled_at")) for r in rows if r.get("pulled_at")})
    fetched_at = pulled_values[-1] if pulled_values else utc_now()
    teams_values = {r.get("teams") for r in clean_rows}
    default_teams = next(iter(teams_values)) if len(teams_values) == 1 else None

    snapshot = {
        "schema": SCHEMA,
        "source": "cbs",
        "fetched_at": fetched_at,
        "source_url": None,
        "default_scoring": None,  # mixed scorings carried per row
        "default_teams": default_teams,
        "row_count": len(clean_rows),
        "rows": clean_rows,
        "review_rows": review_rows,
        "review_count": len(review_rows),
    }
    manifest_fields = {
        "supabase_table": SOURCE_TABLES["cbs"],
        "from_file": None,
        "filter": (
            "select=*&source=eq.cbs&variant=eq.as_published "
            "(as_published only: the chart's own scraped numbers); "
            "QB rows IMPLIED: CBS publishes one 1QB-4 column with no per-scoring "
            "split, so the 1QB-4 value is stored once per scoring "
            "(standard/half_ppr/ppr) -- the live fixture's cbs convention; "
            f"python backstop dropped {len(ecr_dropped)} ECR-flavored row(s)"
        ),
        "content_vintage": content_vintage,
        "content_vintage_derived_from": vintage_note,
        "week_designated": week,
        "save_gap": None,
        "fetched_at_note": "snapshot.fetched_at is the table's pulled_at (pull time), not content vintage",
    }
    return snapshot, manifest_fields

# ---------------------------------------------------------------------------
# Stamping
# ---------------------------------------------------------------------------

def build_manifest(
    source: str,
    snapshot: dict[str, Any],
    fields: dict[str, Any],
    snapshot_path: Path,
    snapshot_sha: str,
) -> dict[str, Any]:
    try:
        rel_path = _rel_to_root(snapshot_path)
    except ValueError:
        rel_path = str(snapshot_path)
    return {
        "schema": MANIFEST_SCHEMA,
        "source": source,
        "snapshot_path": rel_path,
        "snapshot_sha256": snapshot_sha,
        "snapshot_schema": snapshot.get("schema"),
        "supabase_table": fields.get("supabase_table"),
        "from_file": fields.get("from_file"),
        "filter": fields.get("filter"),
        "content_vintage": fields.get("content_vintage"),
        "content_vintage_derived_from": fields.get("content_vintage_derived_from"),
        "week_designated": fields.get("week_designated"),
        # Informational only (ESPN): the table's designated week. Freshness
        # for ESPN judges the DATED content_vintage, never this week.
        "table_week": fields.get("table_week"),
        "save_gap": fields.get("save_gap"),
        # Pull time. Labeled as such. It is NEVER the content vintage.
        "pulled_at": utc_now(),
        "pulled_at_note": "PULL TIME, not content vintage. Freshness gates must use content_vintage.",
        "row_count": snapshot.get("row_count"),
        "review_count": snapshot.get("review_count"),
    }


def _provenance_key(fields: dict[str, Any]) -> tuple:
    return (fields.get("supabase_table"), fields.get("from_file"), fields.get("save_gap"))


def import_source(
    source: str,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """Run the import. Returns a result dict; raises SystemExit fail-closed."""
    name = check_source(source)
    snapshot, fields = build_db_snapshot(name)

    if not snapshot["rows"]:
        raise SystemExit(f"Fail closed: source '{name}' resolved to zero rows. Never writing an empty snapshot.")

    vintage_slug = vintage_dir_slug(str(fields["content_vintage"]))
    target_dir = output_dir / name / vintage_slug
    snapshot_path = target_dir / "snapshot.json"
    manifest_path = target_dir / "snapshot-manifest.json"

    snapshot_bytes = (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
    snapshot_sha = sha256_bytes(snapshot_bytes)

    superseded = None
    if snapshot_path.exists():
        existing_sha = sha256_bytes(snapshot_path.read_bytes())
        if existing_sha != snapshot_sha:
            if manifest_path.exists():
                old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            else:
                old_manifest = {}
            if _provenance_key(old_manifest) != _provenance_key(fields):
                # Provenance migration (e.g. file cache -> Supabase table):
                # the old stamped pair is archived, never silently replaced.
                stamp = utc_now().replace("-", "").replace(":", "")
                archive_dir = target_dir / "_superseded" / stamp
                archive_dir.mkdir(parents=True, exist_ok=True)
                snapshot_path.rename(archive_dir / "snapshot.json")
                manifest_path.rename(archive_dir / "snapshot-manifest.json")
                superseded = {
                    "sha256": existing_sha,
                    "archived_to": _rel_to_root(archive_dir),
                    "reason": (
                        "provenance migration: "
                        f"{_provenance_key(old_manifest)} -> {_provenance_key(fields)}"
                    ),
                }
                stamped = False
            else:
                raise SystemExit(
                    f"Fail closed: stamped snapshot already exists for ({name}, {fields['content_vintage']}) "
                    f"with DIFFERENT bytes (existing sha256 {existing_sha[:16]}..., new {snapshot_sha[:16]}...). "
                    "Refusing to silently overwrite a vintage-stamped snapshot."
                )
        else:
            stamped = True
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        stamped = False

    if not stamped:
        snapshot_path.write_bytes(snapshot_bytes)

    manifest = build_manifest(name, snapshot, fields, snapshot_path, snapshot_sha)
    if superseded:
        manifest["supersedes"] = superseded
    elif manifest_path.exists():
        # Idempotent re-run: keep the audit trail of any earlier migration.
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(prior, dict) and prior.get("supersedes"):
            manifest["supersedes"] = prior["supersedes"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "source": name,
        "snapshot_path": snapshot_path,
        "manifest_path": manifest_path,
        "snapshot_sha256": snapshot_sha,
        "already_stamped": stamped,
        "superseded": superseded,
        "row_count": snapshot["row_count"],
        "review_count": snapshot["review_count"],
        "content_vintage": fields["content_vintage"],
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="fantasycalc | usatoday | fantasypros | espn | cbs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    result = import_source(args.source, output_dir=args.output_dir)
    status = "already stamped" if result["already_stamped"] else "stamped"
    print(
        f"{status}: {result['row_count']} {result['source']} rows "
        f"(vintage {result['content_vintage']}, {result['review_count']} review) -> {result['snapshot_path']}"
    )
    if result.get("superseded"):
        print(f"superseded archived snapshot: {result['superseded']['archived_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
