#!/usr/bin/env python3
"""Verify import health for the five active dashboard trade-value sources.

Fail-checking gate (Jeremy directive): every active source's snapshot must
VERIFY it landed with fresh content vintage before any fixture update
(match/reference/section/promote). A missing, stale, or failed import fails
closed (no fixture update, loud signal).

For each source (espn, usatoday, fantasycalc, fantasypros, cbs -- never
ecr/vegas/razzball; unknown names are a hard error), the gate checks:
  - a snapshot exists under data/raw/sources/<source>/ with a manifest;
  - the snapshot bytes match the manifest sha256
    (defect guarded: unverified bytes promoted);
  - DB-backed sources (all five): the Supabase table's LATEST vintage still
    matches the manifest, re-queried through the same skill path the
    importer used (sbclient.get_all). Tables keep every historical vintage
    (rows are never deleted); only the newest vintage verifies, older rows
    are ignored in every check
    (defect guarded: partial/stale table treated as complete);
  - FRESHNESS on content vintage, never pull time. Week-designated trade
    charts (fantasycalc, usatoday, fantasypros, cbs) are fresh iff their NFL
    week == --nfl-week. ESPN projections are a daily live reference: fresh
    iff the content vintage is within 2 days of the check date.
    (defect guarded: a vintage-less import backing fixture updates.)

Writes output/source-import-health.json in the consumer-contract shape
("trade-value-import-health-v1", see docs/import-health-schema.md) consumed
by the pull watchdog. Exit 0 only if every source is ok; any missing/stale/
failed source -> non-zero exit with a loud human-readable summary on
stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Source-specific publication windows for yellow/red status
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.publication_windows import get_publication_status  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES_ROOT = ROOT / "data" / "raw" / "sources"
DEFAULT_OUTPUT = ROOT / "output" / "source-import-health.json"
HEALTH_SCHEMA = "trade-value-import-health-v1"

DB_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "espn", "cbs")
DASHBOARD_SOURCES = DB_SOURCES
WEEK_DESIGNATED_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "cbs")

# Per-source table verification config. The big three import FROM
# public.source_trade_values, so the table holds every row the importer saw
# (clean + review + ECR-backstop drops). ESPN/CBS tables are written BY the
# save step (stage 1b closed 2026-09-22) and hold exactly the clean rows the
# manifest's row_count counts -- review rows never touched the table.
SOURCE_CONFIGS = {
    "fantasycalc": {
        "api_table": "source_trade_values",
        "params": "?select=player_key,source_content_date,week,created_at&source=eq.fantasycalc&variant=eq.as_published",
        "vintage_date_col": "source_content_date",
        "table_holds_review_rows": True,
    },
    "usatoday": {
        "api_table": "source_trade_values",
        "params": "?select=player_key,source_content_date,week,created_at&source=eq.usatoday&variant=eq.as_published",
        "vintage_date_col": "source_content_date",
        "table_holds_review_rows": True,
    },
    "fantasypros": {
        "api_table": "source_trade_values",
        "params": "?select=player_key,source_content_date,week,created_at&source=eq.fantasypros&variant=eq.as_published",
        "vintage_date_col": "source_content_date",
        "table_holds_review_rows": True,
    },
    "espn": {
        "api_table": "espn_season_projections",
        "params": "?select=player_key,espn_snapshot_date,week,created_at",
        "vintage_date_col": "espn_snapshot_date",
        "table_holds_review_rows": False,
    },
    "cbs": {
        "api_table": "cbs_trade_values",
        "params": "?select=player_key,source_content_date,week,created_at&source=eq.cbs&variant=eq.as_published",
        "vintage_date_col": "source_content_date",
        "table_holds_review_rows": False,
    },
}

# Sources that must never be health-checked here, even if someone names them.
HARD_EXCLUSIONS = ("ecr", "vegas", "razzball", "prediction_markets", "prediction-markets")

FAILURE_CODES = (
    "MISSING_SNAPSHOT",
    "STALE_VINTAGE",
    "BYTE_MISMATCH",
    "TABLE_DRIFT",
    "NO_VINTAGE",
    "IMPORT_FAILED",
)

# ---------------------------------------------------------------------------
# 2026 NFL week calendar (editorial weeks, Tuesday -> Monday, the trade-chart
# cadence). VERIFIED 2026-09-21 against the published 2026 schedule
# (sportsnet.ca/nfl/article/nfl-announces-2026-regular-season-schedule,
# nbc.com/nbc-insider/the-full-2026-2027-nfl-schedule,
# paramountplus.com/nfl-on-cbs-schedule, si.com/nfl/schedule):
#   Week 1 games: Wed Sep 9 (NE@SEA kickoff) .. Mon Sep 14
#   Week 2 games: Thu Sep 17 (DET@BUF) .. Mon Sep 21
#   Week 3 games: Thu Sep 24 .. Mon Sep 28
#   Week 4 games: Thu Oct 1 .. Mon Oct 5
# Editorial week boundaries run Tuesday..Monday (charts publish midweek), so:
#   Week 1: 2026-09-08 .. 2026-09-14
#   Week 2: 2026-09-15 .. 2026-09-21
#   Week 3: 2026-09-22 .. 2026-09-28
#   Week 4: 2026-09-29 .. 2026-10-05
# The 7-day cadence is fixed for the 18-week season, so weeks are computed as
# offsets from the Week 1 start rather than an authored per-week table.
# ---------------------------------------------------------------------------
WEEK1_START = date(2026, 9, 8)


def nfl_week_for_date(d: date) -> int | None:
    """Map a calendar date to its 2026 NFL editorial week, or None pre-season."""
    if d < WEEK1_START:
        return None
    return 1 + (d - WEEK1_START).days // 7


def is_ecr_flavored(source_name: Any) -> bool:
    return "ecr" in str(source_name or "").lower()


def check_source(source: str) -> str:
    name = str(source or "").strip().lower()
    if name in HARD_EXCLUSIONS or is_ecr_flavored(name):
        raise SystemExit(
            f"Refusing to health-check '{source}': not a dashboard trade-value source "
            f"(hard exclusions: ECR, Vegas, Razzball, prediction markets)."
        )
    if name not in DASHBOARD_SOURCES:
        raise SystemExit(
            f"Unknown source '{source}'. Health-checkable dashboard sources: "
            f"{', '.join(DASHBOARD_SOURCES)}."
        )
    return name


# ---------------------------------------------------------------------------
# Supabase access (read-only, minimal columns). Module-level callable so tests
# can inject recorded fixtures without touching the network.
# ---------------------------------------------------------------------------

def _default_table_summary(table: str, params: str) -> list[dict[str, Any]]:
    sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
    from sbclient import get_all  # noqa: E402

    rows = get_all(table, params=params)
    if not isinstance(rows, list):
        raise SystemExit(f"Unexpected Supabase response for {table}: {type(rows)}")
    return [row for row in rows if isinstance(row, dict)]


fetch_table_summary: Callable[[str, str], list[dict[str, Any]]] = _default_table_summary


def utc_today() -> date:
    """Check date for the ESPN daily-freshness rule. Module-level for tests."""
    return datetime.now(timezone.utc).date()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Vintage derivation (content vintage, never pull time)
# ---------------------------------------------------------------------------

WEEK_RE = re.compile(r"^\s*week\s+(\d+)\s*$", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ECR_DROPPED_RE = re.compile(r"dropped\s+(\d+)\s+ECR-flavored")


def derive_vintage(manifest: dict[str, Any], source: str) -> tuple[str, str, int | None]:
    """Return (vintage_display, vintage_kind, nfl_week_or_none).

    Raises _NoVintage when no vintage is derivable from the manifest --
    a vintage-less snapshot may never back a fixture update.
    """
    content_vintage = manifest.get("content_vintage")
    week_designated = manifest.get("week_designated")

    if isinstance(week_designated, int) and not isinstance(week_designated, bool):
        return str(content_vintage), "week_designated", week_designated

    if isinstance(content_vintage, str):
        m = WEEK_RE.match(content_vintage)
        if m:
            return content_vintage, "week_designated", int(m.group(1))
        if ISO_DATE_RE.match(content_vintage.strip()):
            vintage_date = date.fromisoformat(content_vintage.strip())
            week = nfl_week_for_date(vintage_date)
            if week is None:
                raise _NoVintage(
                    f"content_vintage {content_vintage} predates the 2026 season; "
                    "no NFL week derivable"
                )
            kind = "file_meta" if source == "espn" else "source_content_date"
            return content_vintage, kind, week

    raise _NoVintage(
        f"content vintage not derivable from manifest "
        f"(content_vintage={content_vintage!r}, week_designated={week_designated!r})"
    )


class _NoVintage(Exception):
    pass


class _MissingSnapshot(Exception):
    pass


def find_latest_manifest(sources_root: Path, source: str) -> tuple[Path, dict[str, Any]]:
    """Return (manifest_dir, manifest) for the most recently pulled snapshot."""
    source_dir = sources_root / source
    candidates: list[tuple[str, Path]] = []
    if source_dir.is_dir():
        for child in source_dir.iterdir():
            manifest_path = child / "snapshot-manifest.json"
            if child.is_dir() and manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                pulled = str(manifest.get("pulled_at") or "")
                candidates.append((pulled, child))
    if not candidates:
        raise _MissingSnapshot(
            f"no snapshot-manifest.json under {source_dir} (expected "
            f"data/raw/sources/{source}/<content-vintage>/snapshot-manifest.json)"
        )
    candidates.sort(key=lambda item: item[0])
    manifest_dir = candidates[-1][1]
    manifest = json.loads((manifest_dir / "snapshot-manifest.json").read_text(encoding="utf-8"))
    return manifest_dir, manifest


def snapshot_path_from_manifest(manifest: dict[str, Any], manifest_dir: Path) -> Path | None:
    recorded = manifest.get("snapshot_path")
    if isinstance(recorded, str) and recorded:
        candidate = Path(recorded)
        if not candidate.is_absolute():
            candidate = ROOT / recorded
        if candidate.is_file():
            return candidate
    fallback = manifest_dir / "snapshot.json"
    return fallback if fallback.is_file() else None


def expected_table_rows(manifest: dict[str, Any], source: str) -> int:
    """Rows the table must hold for the manifest to verify.

    Big-three rule (unchanged): the importer read FROM the table, so it saw
    clean + review + ECR-backstop drops. ESPN/CBS rule: the save step wrote
    exactly the clean rows (review rows never touched the table), so the
    table must hold row_count and nothing else.
    """
    row_count = manifest.get("row_count")
    expected = row_count if isinstance(row_count, int) and not isinstance(row_count, bool) else 0
    if SOURCE_CONFIGS[source]["table_holds_review_rows"]:
        review = manifest.get("review_count")
        if isinstance(review, int) and not isinstance(review, bool):
            expected += review
        filter_note = str(manifest.get("filter") or "")
        m = ECR_DROPPED_RE.search(filter_note)
        if m:
            expected += int(m.group(1))
    return expected


def _week_sort_key(week: Any) -> tuple[int, Any]:
    """Order weeks numerically when possible (2 < 3), lexically otherwise."""
    try:
        return (0, int(str(week).strip()))
    except (TypeError, ValueError):
        return (1, str(week))


def latest_vintage_rows(
    rows: list[dict[str, Any]], *, date_col: str = "source_content_date"
) -> tuple[str, list[dict[str, Any]]]:
    """Return (latest_vintage, rows_at_latest_vintage).

    Latest-vintage wins: tables keep every historical vintage (rows are NEVER
    deleted), but verification and display only ever see the newest one --
    older rows are ignored, never removed. Multiple dates -> newest date;
    no dates -> newest week.
    """
    dates = sorted({str(r.get(date_col)) for r in rows if r.get(date_col)})
    weeks = sorted(
        {r.get("week") for r in rows if r.get("week") not in (None, "")},
        key=_week_sort_key,
    )
    if dates:
        latest = dates[-1]
        return latest, [r for r in rows if str(r.get(date_col)) == latest]
    if weeks:
        latest_week = weeks[-1]
        return f"Week {latest_week}", [
            r for r in rows if _week_sort_key(r.get("week")) == _week_sort_key(latest_week)
        ]
    raise _NoVintage("table has no source_content_date and no week on any row")


def table_vintage(rows: list[dict[str, Any]], *, date_col: str = "source_content_date") -> str:
    """Latest table vintage, never the earliest (older rows stay, ignored)."""
    vintage, _ = latest_vintage_rows(rows, date_col=date_col)
    return vintage


# ---------------------------------------------------------------------------
# Per-source verification
# ---------------------------------------------------------------------------

def verify_source(
    source: str,
    *,
    sources_root: Path,
    nfl_week: int,
    check_date: date,
    prev_entry: dict[str, Any] | None,
    checked_at: str,
) -> tuple[dict[str, Any], list[str]]:
    """Return (health_entry, loud_lines). Never raises for a named source."""
    entry: dict[str, Any] = {
        "status": "failed",
        "last_successful_import": None,
        "content_vintage": None,
        "vintage_kind": "unknown",
        "row_count": None,
        "supabase_table": None,
        "supabase_landing": source in DB_SOURCES,
        "snapshot_path": None,
        "failure_reason": None,
        # Older table vintages are never deleted but ignored everywhere;
        # counted here so the monitor can show the latest version is what
        # verifies and displays.
        "ignored_older_rows": None,
        # Checkpoint visibility: the dashboard shows the pipeline stages
        # separately so a mismatch between what's in the DB and what's
        # snapshotted is visually obvious (not buried in failure_reason).
        # db_latest_* = newest vintage actually sitting in Supabase.
        # content_vintage/row_count/snapshot_path = what the manifest points to.
        "db_latest_vintage": None,
        "db_latest_rows": None,
        "db_latest_arrived_at": None,
    }
    loud: list[str] = []

    def fail(code: str, detail: str) -> tuple[dict[str, Any], list[str]]:
        assert code in FAILURE_CODES, code
        entry["failure_reason"] = f"{code}: {detail}"
        entry["status"] = "missing" if code == "MISSING_SNAPSHOT" else "failed"
        # Stateful carry-forward: a failed check keeps the previous known-good
        # import time; null if the source never verified.
        if prev_entry:
            entry["last_successful_import"] = prev_entry.get("last_successful_import")
        return entry, loud

    # 1. snapshot + manifest exist ------------------------------------------
    try:
        manifest_dir, manifest = find_latest_manifest(sources_root, source)
    except _MissingSnapshot as exc:
        return fail("MISSING_SNAPSHOT", str(exc))
    entry["row_count"] = manifest.get("row_count")
    entry["supabase_table"] = manifest.get("supabase_table")
    entry["supabase_landing"] = manifest.get("supabase_table") is not None

    snapshot_path = snapshot_path_from_manifest(manifest, manifest_dir)
    if snapshot_path is None:
        return fail("MISSING_SNAPSHOT", f"snapshot.json not found for manifest at {manifest_dir}")
    try:
        rel = snapshot_path.relative_to(ROOT)
        entry["snapshot_path"] = rel.as_posix()
    except ValueError:
        entry["snapshot_path"] = str(snapshot_path)

    # 2. bytes match the manifest sha ----------------------------------------
    try:
        snapshot_bytes = snapshot_path.read_bytes()
    except OSError as exc:
        return fail("IMPORT_FAILED", f"cannot read snapshot bytes at {snapshot_path}: {exc}")
    actual_sha = sha256_bytes(snapshot_bytes)
    expected_sha = manifest.get("snapshot_sha256")
    if not expected_sha or actual_sha != expected_sha:
        return fail(
            "BYTE_MISMATCH",
            f"snapshot bytes do not match manifest sha256 "
            f"(manifest {str(expected_sha)[:16]}..., actual {actual_sha[:16]}...); "
            "unverified bytes must never be promoted",
        )

    # 3. vintage derivable (content vintage, never pull time) -----------------
    try:
        vintage_display, vintage_kind, vintage_week = derive_vintage(manifest, source)
    except _NoVintage as exc:
        return fail("NO_VINTAGE", str(exc))
    entry["content_vintage"] = vintage_display
    entry["vintage_kind"] = vintage_kind

    # 4. DB sources: table row count / vintage still matches the manifest -----
    config = SOURCE_CONFIGS[source]
    table_label = f"public.{config['api_table']}"
    try:
        # sbclient builds /rest/v1/<table> with PostgREST's default schema,
        # so it takes the bare table name; the manifest keeps the
        # schema-qualified name for the health JSON contract.
        rows = fetch_table_summary(config["api_table"], config["params"])
    except Exception as exc:  # noqa: BLE001 -- any query failure fails closed
        return fail("IMPORT_FAILED", f"Supabase re-query of {table_label} failed: {exc}")
    expected = expected_table_rows(manifest, source)
    # Latest-vintage wins: the table keeps every historical vintage (rows are
    # NEVER deleted), but only the newest vintage verifies against the
    # manifest -- older rows are ignored here and in every process.
    try:
        live_vintage, latest_rows = latest_vintage_rows(rows, date_col=config["vintage_date_col"])
    except _NoVintage as exc:
        return fail("TABLE_DRIFT", f"table vintage undeterminable: {exc}")
    entry["ignored_older_rows"] = len(rows) - len(latest_rows)
    # Checkpoint fields: expose what's actually in the DB so the dashboard
    # can show it separately from the snapshot vintage.
    entry["db_latest_vintage"] = live_vintage
    entry["db_latest_rows"] = len(latest_rows)
    # When did the newest DB rows arrive? (for lag detection - best practice:
    # show how long data has been waiting between pipeline stages)
    arrived = [r.get("created_at") for r in latest_rows if r.get("created_at")]
    entry["db_latest_arrived_at"] = max(arrived) if arrived else None
    drift_bits: list[str] = []
    if len(latest_rows) != expected:
        drift_bits.append(
            f"table has {len(latest_rows)} rows at latest vintage {live_vintage}, "
            f"manifest expects {expected}"
        )
    if live_vintage != str(manifest.get("content_vintage")):
        drift_bits.append(
            f"table latest vintage {live_vintage} != manifest vintage "
            f"{manifest.get('content_vintage')} -- run stage-1 import to stamp it"
        )
    if drift_bits:
        return fail("TABLE_DRIFT", "; ".join(drift_bits) + " -- partial/stale table, not complete")

    # 5. freshness ------------------------------------------------------------
    # Uses source-specific publication windows (pipelines/lib/publication_windows.py)
    # to determine yellow (within window) vs red (missed window) vs stale (no verified schedule).
    verified_at = checked_at  # the snapshot landed and verified; record it
    if source in WEEK_DESIGNATED_SOURCES:
        # Use publication window logic for week-designated sources
        pub_status, pub_reason = get_publication_status(
            source=source,
            vintage_week=vintage_week,
            current_week=nfl_week,
            check_date=check_date,
        )
        if pub_status != "ok":
            entry["last_successful_import"] = verified_at
            entry["failure_reason"] = pub_reason
            entry["status"] = pub_status
            return entry, loud
    else:  # espn: daily live reference
        if vintage_kind in ("file_meta", "source_content_date"):
            vintage_date = date.fromisoformat(str(vintage_display).strip()[:10])
            age_days = abs((check_date - vintage_date).days)
            if age_days > 2:
                entry["last_successful_import"] = verified_at
                entry["failure_reason"] = (
                    f"STALE_VINTAGE: ESPN content vintage {vintage_display} is "
                    f"{age_days} days from check date {check_date} (> 2d daily limit)"
                )
                entry["status"] = "stale"
                return entry, loud
        else:
            return fail(
                "NO_VINTAGE",
                f"ESPN vintage {vintage_display!r} is not a content date; "
                "daily freshness needs a date",
            )

    entry["status"] = "ok"
    entry["last_successful_import"] = verified_at
    return entry, loud


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------

def load_previous_health(output_path: Path) -> dict[str, Any]:
    if output_path.is_file():
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("sources"), dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def run_health(
    *,
    nfl_week: int,
    sources_root: Path = DEFAULT_SOURCES_ROOT,
    output_path: Path = DEFAULT_OUTPUT,
    check_date: date | None = None,
) -> int:
    """Verify all five sources, write the health JSON, return the exit code."""
    checked_at = utc_now_iso()
    today = check_date or utc_today()
    prev = load_previous_health(output_path)
    prev_sources = prev.get("sources", {}) if isinstance(prev, dict) else {}

    sources: dict[str, dict[str, Any]] = {}
    loud: list[str] = []
    for source in DASHBOARD_SOURCES:
        entry, lines = verify_source(
            source,
            sources_root=sources_root,
            nfl_week=nfl_week,
            check_date=today,
            prev_entry=prev_sources.get(source),
            checked_at=checked_at,
        )
        sources[source] = entry
        loud.extend(lines)

    health = {
        "schema": HEALTH_SCHEMA,
        "checked_at": checked_at,
        "nfl_week": nfl_week,
        "sources": sources,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(health, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    counts = {"ok": 0, "stale": 0, "missing": 0, "failed": 0}
    for entry in sources.values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1

    err: list[str] = []
    err.append(
        f"IMPORT HEALTH [{checked_at} | NFL week {nfl_week}]: "
        f"{counts['ok']} ok / {counts['stale']} stale / "
        f"{counts['missing']} missing / {counts['failed']} failed"
    )
    for source in DASHBOARD_SOURCES:
        entry = sources[source]
        if entry["status"] != "ok":
            err.append(
                f"  {entry['status'].upper():7} {source:12} "
                f"vintage={entry['content_vintage']} kind={entry['vintage_kind']} "
                f"rows={entry['row_count']} :: {entry['failure_reason']}"
            )
    err.extend(loud)
    green = counts["stale"] == 0 and counts["missing"] == 0 and counts["failed"] == 0
    if green:
        err.append("GATE: GREEN -- all five import sources verified fresh")
    else:
        err.append(
            "GATE: RED -- no fixture update (match/reference/section/promote) may run "
            "on this health check"
        )
    print("\n".join(err), file=sys.stderr)

    return 0 if green else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nfl-week",
        type=int,
        required=True,
        help="Current NFL week (passed by the watchdog/cron; e.g. --nfl-week 3).",
    )
    parser.add_argument(
        "--sources-root",
        type=Path,
        default=DEFAULT_SOURCES_ROOT,
        help="Root of data/raw/sources (default: repo data/raw/sources).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the health JSON (default: output/source-import-health.json).",
    )
    args = parser.parse_args()
    for source in DASHBOARD_SOURCES:
        check_source(source)  # hard error on unknown/excluded names
    return run_health(
        nfl_week=args.nfl_week,
        sources_root=args.sources_root,
        output_path=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
