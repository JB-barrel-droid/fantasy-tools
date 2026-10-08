"""Record names a saver could not resolve, per source, in public.player_name_aliases.

JEG-438: unmatched names must be visible and counted per source, not only
printed in a workflow log. A saver calls record_misses(source, review) after a
write; each identity miss (unmatched, ambiguous, position conflict) becomes
or refreshes one row at the table's grain (source, norm_name, position):

    status 'unmatched' (no candidate) or 'review' (several candidates),
    method 'saver-miss', last_seen_at = now, seen_count + 1.

Rows another process already settled (verified / rejected) are never
touched, and nothing here writes a player_key: the nightly job
(pipelines/reconcile_player_identity.py) resolves, proposes or keeps them
open, and the monitor alerts when a source has too many open names.

A queue failure never fails the save (the values are already written); it is
printed and the nightly count will miss it.
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable

_LIB = os.path.dirname(os.path.abspath(__file__))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
from canonical_players import norm_player_name  # noqa: E402 -- the single normalization rule

TABLE = "player_name_aliases"
OPEN_STATUSES = ("unmatched", "review", "provisional")
METHOD = "saver-miss"

# Monitoring (pipelines/monitor_alerts.py identity_unmatched_alerts): a source
# alerts when more than OPEN_NAMES_ALERT names seen in the last RECENT_DAYS are
# still open. Unmatched names should be extreme edge cases (JEG-438).
OPEN_NAMES_ALERT = 5
RECENT_DAYS = 8

# Review reasons that are identity misses (value problems are not).
IDENTITY_REASONS = {"no_match", "ambiguous", "unmatched", "unresolved_name", "position_conflict"}
IDENTITY_DETAIL = "no single canonical players-table identity"


def identity_misses(review: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The identity misses in a saver's review list, one per (norm, position)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in review or []:
        if not isinstance(r, dict):
            continue
        name = str(r.get("player_name") or r.get("player") or r.get("name") or "").strip()
        reason = str(r.get("reason") or "")
        if not name or not (reason in IDENTITY_REASONS or IDENTITY_DETAIL in str(r.get("detail") or "")):
            continue
        norm = norm_player_name(name)
        if not norm:
            continue
        pos = str(r.get("pos") or r.get("position") or "").strip().upper()
        out.setdefault((norm, pos), {"name": name, "norm": norm, "pos": pos,
                                     "status": "review" if reason == "ambiguous" else "unmatched",
                                     "reason": reason or "unresolved"})
    return list(out.values())


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def open_counts(rows: list[dict[str, Any]], now: datetime,
                days: int = RECENT_DAYS) -> dict[str, dict[str, Any]]:
    """Open names per source seen within `days`: {source: {status: n, open, names}}."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows or []:
        status = r.get("status")
        if status not in OPEN_STATUSES:
            continue
        seen = _parse_ts(r.get("last_seen_at"))
        if seen is None or (now - seen).total_seconds() > days * 86400:
            continue
        src = str(r.get("source") or "?")
        entry = out.setdefault(src, {"unmatched": 0, "review": 0, "provisional": 0, "open": 0, "names": []})
        entry[status] += 1
        entry["open"] += 1
        entry["names"].append(str(r.get("source_player_name") or r.get("norm_name") or "?"))
    for entry in out.values():
        entry["names"].sort()
    return dict(sorted(out.items()))


def _sb():
    try:
        import sbclient  # noqa: PLC0415 -- gh_sbclient copied onto PYTHONPATH in CI
    except ImportError:
        sys.path.insert(0, os.path.dirname(_LIB))
        import gh_sbclient as sbclient  # noqa: PLC0415
    return sbclient


def _default_get(params: str) -> list[dict[str, Any]]:
    rows = _sb().get(TABLE, params)
    return rows if isinstance(rows, list) else []


def _default_post(rows: list[dict[str, Any]]) -> None:
    _sb().post(TABLE, rows, prefer="return=minimal")


def _default_patch(row_id: int, body: dict[str, Any]) -> None:
    _sb().patch(TABLE, body, f"?id=eq.{row_id}")


get_rows: Callable[[str], list[dict[str, Any]]] = _default_get
post_rows: Callable[[list[dict[str, Any]]], None] = _default_post
patch_row: Callable[[int, dict[str, Any]], None] = _default_patch


def plan(source: str, misses: list[dict[str, Any]], existing: list[dict[str, Any]],
         now: str) -> tuple[list[dict[str, Any]], list[tuple[int, dict[str, Any]]]]:
    """(rows to insert, (id, patch) pairs) for one source's misses."""
    by_grain = {(e.get("norm_name"), e.get("position") or ""): e for e in existing}
    inserts, patches = [], []
    for m in misses:
        prior = by_grain.get((m["norm"], m["pos"]))
        if prior is None:
            inserts.append({
                "source": source, "source_player_name": m["name"], "norm_name": m["norm"],
                "position": m["pos"], "status": m["status"], "method": METHOD,
                "first_seen_at": now, "last_seen_at": now, "seen_count": 1,
                "notes": f"saver review reason: {m['reason']}",
            })
        elif prior.get("status") in OPEN_STATUSES:
            patches.append((prior["id"], {"last_seen_at": now,
                                          "seen_count": int(prior.get("seen_count") or 0) + 1}))
    return inserts, patches


def record_misses(source: str, review: list[dict[str, Any]], *, now: str | None = None,
                  log: Callable[[str], None] = print) -> dict[str, int]:
    """Queue a saver's identity misses. Never raises."""
    misses = identity_misses(review)
    summary = {"misses": len(misses), "inserted": 0, "refreshed": 0}
    if not misses:
        log(f"identity queue {source}: 0 unresolved names")
        return summary
    try:
        now = now or datetime.now(timezone.utc).isoformat()
        norms = ",".join(sorted({urllib.parse.quote(f'"{m["norm"]}"', safe="") for m in misses}))
        existing = get_rows(f"?select=id,norm_name,position,status,seen_count"
                            f"&source=eq.{urllib.parse.quote(source)}&norm_name=in.({norms})")
        inserts, patches = plan(source, misses, existing, now)
        if inserts:
            post_rows(inserts)
        for row_id, body in patches:
            patch_row(row_id, body)
        summary.update(inserted=len(inserts), refreshed=len(patches))
        log(f"identity queue {source}: {len(misses)} unresolved names "
            f"({len(inserts)} new, {len(patches)} seen again): "
            + ", ".join(sorted(m["name"] for m in misses))[:600])
    except Exception as exc:  # noqa: BLE001 -- the save already landed
        summary["error"] = 1
        log(f"identity queue {source}: WARNING could not record misses "
            f"({type(exc).__name__}: {str(exc)[:200]})")
    return summary
