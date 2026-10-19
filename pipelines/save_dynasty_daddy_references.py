#!/usr/bin/env python3
"""Save Dynasty Daddy snapshots into public.dynasty_daddy_trade_values (JEG-674).

DRAFT: the table does not exist yet. Migration sql/migrations/013_dynasty_daddy_trade_values.sql is NOT applied;
the lead applies it after Jeremy confirms the table name and columns. Dry run is the default;
nothing is written without --write.

Loads data/raw/sources/dynasty_daddy/<date>/snapshot.json (from pipelines/pull_dynasty_daddy.py).
Mirrors pipelines/save_draftsharks_references.py and the KeepTradeCut saver: the canonical resolver
(lib/canonical_players via base.resolve_name), fail-closed identity (unmatched/ambiguous/position-conflict
names go to the review list, never guessed, never zero-filled) and save verification.

Credentials come from the environment only: SUPABASE_URL and SUPABASE_SERVICE_KEY. Nothing is read
from a file or a vault, and a missing one fails closed (dry run also needs them: it reads public.players).
Grain (upsert key): (player_key, dynasty_daddy_snapshot_date). Vintage is the newest `most_recent_data_point` date in the pull.
COMPARISON AND ID BRIDGE ONLY: Dynasty Daddy's value aggregates FantasyCalc and KTC, so it must never be weighted beside them.
Values are its 0-9999 dynasty scale (1QB and superflex); 0, missing or non-numeric is null, out of 0..9999 fails closed.
FantasyPros-derived ROS ranks are excluded repo-wide and are not in the snapshot.
A snapshot whose fingerprint does not match its rows fails closed.
Nothing here feeds any chart, consolidation, DDF Value input list or schedule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import identity_queue  # noqa: E402
import save_razzball_references as base  # noqa: E402 -- shared resolver glue

SOURCE = "dynasty_daddy"
LABEL = "Dynasty Daddy"
TABLE = "dynasty_daddy_trade_values"
SNAPSHOT_COLUMN = "dynasty_daddy_snapshot_date"
CONFLICT = f"player_key,{SNAPSHOT_COLUMN}"
SCHEMA = "dynasty_daddy_values_v1"
WRITER = "save_dynasty_daddy_references.py"
VALUE_MIN, VALUE_MAX = 0, 9999
TYPED_FORMATS = ("1qb", "sf")  # typed columns: dd_<format>_{value,rank,pos_rank}

def _env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(f"Fail closed: {name} is not set in the environment.")
    return val


def _request(method: str, path: str, body: Any = None, prefer: str | None = None) -> Any:
    url = _env("SUPABASE_URL").rstrip("/") + "/rest/v1/" + path
    key = _env("SUPABASE_SERVICE_KEY")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 -- https Supabase host from env
        raw = resp.read()
    return json.loads(raw) if raw else None


def _get_all(table: str, params: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sep = "&" if "?" in params else "?"
    while True:
        page = _request("GET", f"{table}{params}{sep}limit=1000&offset={len(out)}")
        if not isinstance(page, list):
            raise SystemExit(f"Fail closed: unexpected Supabase response for {table}.")
        out.extend(r for r in page if isinstance(r, dict))
        if len(page) < 1000:
            return out


def _default_fetch_players() -> list[dict[str, Any]]:
    return _get_all("players", "?select=player_key,full_name,position,active")


def _default_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    for start in range(0, len(rows), 500):
        _request("POST", f"{table}?on_conflict={on_conflict}", rows[start:start + 500],
                 prefer="resolution=merge-duplicates,return=minimal")


def _default_count(table: str, params: str) -> int:
    return len(_get_all(table, params))


fetch_players: Callable[[], list[dict[str, Any]]] = _default_fetch_players
upsert_rows: Callable[[str, list[dict[str, Any]], str], None] = _default_upsert
count_rows: Callable[[str, str], int] = _default_count


def latest_snapshot() -> Path:
    root = ROOT / "data" / "raw" / "sources" / SOURCE
    found = sorted(p for p in root.iterdir() if p.is_dir() and (p / "snapshot.json").is_file()) if root.is_dir() else []
    if not found:
        raise SystemExit(f"Fail closed: no {SOURCE} snapshot found under data/raw/sources/{SOURCE}/.")
    return found[-1] / "snapshot.json"


def clean_number(raw: Any, lo: float, hi: float, what: str) -> float | None:
    """A source number, or None. 0, missing, non-numeric are None; a priced value outside lo..hi fails closed."""
    v = base.parse_float(raw)
    if not v:
        return None
    if not (lo <= v <= hi):
        raise SystemExit(f"Fail closed: {LABEL} {what} {v} outside {lo}..{hi} (scale changed).")
    return v


def clean_int(raw: Any) -> int | None:
    v = base.parse_float(raw)
    return int(v) if v and v > 0 else None


def fingerprint_of(rows: list[dict[str, Any]]) -> str:
    """Same recipe as pull_dynasty_daddy.build_snapshot: sha256 of sorted (name_id, 1QB value) pairs."""
    pairs = sorted((r["name_id"], r["values"]["1qb"]["value"])
                   for r in rows if isinstance(r.get("values"), dict) and isinstance(r["values"].get("1qb"), dict)
                   and r["values"]["1qb"].get("value"))
    return hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]


def snapshot_level_fields(snap: dict[str, Any], vintage_date: date) -> dict[str, Any]:
    return {"season": base.season_for_vintage(vintage_date)}


def clean_cell(cell: Any) -> dict[str, Any] | None:
    if not isinstance(cell, dict):
        return None
    value = clean_number(cell.get("value"), VALUE_MIN, VALUE_MAX, "value")
    if value is None:
        return None  # an unpriced format carries no rank either
    return {"value": value, "rank": clean_int(cell.get("rank")), "pos_rank": clean_int(cell.get("pos_rank"))}


def typed_fields(row: dict[str, Any]) -> dict[str, Any]:
    cells = {fmt: clean_cell(cell) for fmt, cell in (row.get("values") or {}).items()}
    out: dict[str, Any] = {"name_id": row.get("name_id"), "ids": row.get("ids") or {}}
    for fmt in TYPED_FORMATS:
        cell = cells.get(fmt)
        for field in ("value", "rank", "pos_rank"):
            out[f"dd_{fmt}_{field}"] = cell[field] if cell else None
    for field in ("espn_ros", "fanduel_ros", "fantasyguys_ros"):
        out[field] = clean_int(row.get(field))
    return out


def build_rows(snapshot_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if snap.get("source") != SOURCE or snap.get("schema") != SCHEMA:
        raise SystemExit(f"Fail closed: not a {SOURCE} {SCHEMA} snapshot.")
    vintage = snap.get("vintage_date")
    if not vintage:
        raise SystemExit(f"Fail closed: {LABEL} snapshot has no vintage_date.")
    try:
        vintage_date = date.fromisoformat(vintage)
    except (TypeError, ValueError):
        raise SystemExit(f"Fail closed: {LABEL} snapshot vintage_date is not an ISO date: {vintage!r}.")
    rows = snap.get("rows") or []
    if not rows:
        raise SystemExit(f"Fail closed: {LABEL} snapshot has no rows.")
    fingerprint = snap.get("fingerprint")
    if not fingerprint:
        raise SystemExit(f"Fail closed: {LABEL} snapshot has no fingerprint.")
    if fingerprint != fingerprint_of(rows):
        raise SystemExit(f"Fail closed: {LABEL} snapshot fingerprint does not match its rows.")
    snapshot_fields = snapshot_level_fields(snap, vintage_date)
    registry = base.build_registry(fetch_players())
    pulled_at = base.utc_now()
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    seen: dict[int, str] = {}
    for row in rows:
        name = str(row.get("player_name") or "").strip()
        pos = str(row.get("pos") or "").strip().upper() or None
        if not name:
            review.append({"reason": "missing_player_name", "pos": pos, "team": row.get("team")})
            continue
        key, reason = base.resolve_name(name, pos, registry, row.get("player_norm"))
        if key is None:
            if reason in base.canonical_players.SILENT_REASONS:
                continue
            review.append({"reason": reason, "player_name": name, "player_norm": row.get("player_norm"), "pos": pos})
            continue
        if key in seen:  # two source rows for one player: never guess which is right
            review.append({"reason": "duplicate_player_key", "player_name": name, "player_norm": row.get("player_norm"),
                           "pos": pos, "first_seen": seen[key]})
            continue
        seen[key] = name
        out: dict[str, Any] = {
            "player_key": key, "player_norm": row.get("player_norm"), "pos": pos,
            "team": str(row.get("team") or "").strip() or None,
        }
        out.update(typed_fields(row))
        out.update(snapshot_fields)
        out.update({
            SNAPSHOT_COLUMN: vintage, "fingerprint": fingerprint,
            "snapshot_ref": f"data/raw/sources/{SOURCE}/{vintage}/snapshot.json",
            "pulled_at": pulled_at, "_written_at": pulled_at, "source_content_date": vintage,
            "_run_id": f"{SOURCE}-save-{vintage}-{fingerprint}", "_writer_identity": WRITER,
        })
        clean.append(out)
    return clean, review, vintage


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=f"Save the {LABEL} snapshot to Supabase (dry run unless --write).")
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--write", action="store_true", help="Actually upsert. Default is a dry run.")
    args = parser.parse_args(argv)
    clean, review, vintage = build_rows(args.snapshot or latest_snapshot())
    print(f"{SOURCE} {vintage}: {len(clean)} clean rows, {len(review)} review rows")
    for r in review[:10]:
        print(f"  review: {r.get('reason')}: {r.get('player_name')}")
    if not args.write:
        print(f"[dry-run] would upsert {len(clean)} rows into {TABLE}; pass --write to save")
        return
    if not clean:
        raise SystemExit("Fail closed: zero clean rows, not writing.")
    upsert_rows(TABLE, clean, CONFLICT)
    pulled_at = quote(clean[0]["pulled_at"], safe="")
    live = count_rows(TABLE, f"?select=id&{SNAPSHOT_COLUMN}=eq.{vintage}&pulled_at=eq.{pulled_at}")
    print(f"Verified: {TABLE} holds {live} rows from this save for vintage {vintage}")
    if live != len(clean):
        raise SystemExit(f"Fail closed: {TABLE} holds {live} rows from this save for vintage {vintage} "
                         f"after upsert, expected {len(clean)}.")
    identity_queue.record_misses(SOURCE, review)
    print("Dynasty Daddy save complete.")


if __name__ == "__main__":
    main()
