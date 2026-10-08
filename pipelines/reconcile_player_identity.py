#!/usr/bin/env python3
"""Nightly player-identity reconciliation (JEG-438).

Reads every open row of public.player_name_aliases (status unmatched, review
or provisional: names a saver could not resolve, queued by
lib/identity_queue.py) and settles each one against public.players with the
one resolver rule the savers use:

  1. verified alias (lib/player_aliases: the curated list)       -> verified
  2. norm_player_name match, narrowed by position, then by the
     single active row (canonical_players.narrow_candidates)      -> verified
  3. several candidates left                                       -> review
  4. otherwise a fuzzy proposal (difflib on the normalized name,
     same position when known): best ratio >= FUZZY_FLOOR and
     ahead of the runner-up by FUZZY_MARGIN                       -> provisional
  5. nothing close                                                 -> unmatched

A provisional row is a proposal only. Savers never read this table to
resolve (identity-fuzzy-001: fuzzy matches are never written to values);
a provisional match becomes real only when someone checks it and adds it to
data/inputs/player_aliases.json (and the curated table rows).

Then it counts the names still open per source (seen in the last
identity_queue.RECENT_DAYS days), writes output/player-identity-reconcile.json,
and with --write records the monitored check `player_identity_reconcile`
(content_ok false when a source has more than OPEN_NAMES_ALERT open names).
monitor_alerts.py raises an ops alert on the same count.

It also reports drift between the curated table rows and the committed JSON.

    python3 pipelines/reconcile_player_identity.py            # dry run
    python3 pipelines/reconcile_player_identity.py --write    # nightly (pg_cron)
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import player_aliases  # noqa: E402 -- the one verified alias list
import identity_queue  # noqa: E402
from canonical_players import narrow_candidates, norm_player_name  # noqa: E402

DEFAULT_OUT = ROOT / "output" / "player-identity-reconcile.json"
CHECK_ID = "player_identity_reconcile"
RUNS_TABLE = "player_identity_reconcile_runs"  # existing stage-2 table, one row per source per run
FUZZY_FLOOR = 0.88
FUZZY_MARGIN = 0.05
WRITER = "reconcile_player_identity"


def build_index(players: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for p in players:
        key, name = p.get("player_key"), str(p.get("full_name") or "").strip()
        if not isinstance(key, int) or not name:
            continue
        index.setdefault(norm_player_name(name), []).append({
            "player_key": key, "full_name": name,
            "position": str(p.get("position") or "").upper() or None,
            "active": p.get("active")})
    return index


def fuzzy_candidates(norm: str, pos: str, index: dict[str, list[dict[str, Any]]],
                     limit: int = 3) -> list[tuple[float, int]]:
    """(ratio, player_key) best first, same position when one is known."""
    scored = []
    for form, recs in index.items():
        for rec in recs:
            if pos and rec["position"] and rec["position"] != pos:
                continue
            scored.append((round(difflib.SequenceMatcher(None, norm, form).ratio(), 3), rec["player_key"]))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[:limit]


def decide(row: dict[str, Any], index: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The new state for one open row (status, player_key, method, ...)."""
    name = str(row.get("source_player_name") or row.get("norm_name") or "")
    pos = str(row.get("position") or "").upper()
    hit = player_aliases.lookup(name)
    if hit is not None:
        return {"status": "verified", "player_key": hit["player_key"], "method": "reconcile:alias",
                "confidence": 1, "candidate_keys": None}
    cands = index.get(norm_player_name(name), [])
    rec, reason = narrow_candidates(cands, pos or None)
    if rec is not None:
        return {"status": "verified", "player_key": rec["player_key"], "method": "reconcile:exact",
                "confidence": 1, "candidate_keys": None}
    if reason == "ambiguous":
        return {"status": "review", "player_key": None, "method": "reconcile:ambiguous",
                "confidence": None, "candidate_keys": sorted(c["player_key"] for c in cands)}
    ranked = fuzzy_candidates(norm_player_name(name), pos, index)
    keys = [k for _r, k in ranked]
    best = ranked[0][0] if ranked else 0.0
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if best >= FUZZY_FLOOR and best - second >= FUZZY_MARGIN:
        return {"status": "provisional", "player_key": ranked[0][1], "method": "reconcile:fuzzy",
                "confidence": best, "candidate_keys": keys}
    return {"status": "unmatched", "player_key": None, "method": row.get("method") or identity_queue.METHOD,
            "confidence": round(best, 3) if ranked else None, "candidate_keys": keys or None}


def _changed(row: dict[str, Any], new: dict[str, Any]) -> bool:
    for k in ("status", "player_key", "candidate_keys"):
        if (row.get(k) or None) != (new.get(k) or None):
            return True
    return False


def curated_drift(table_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Aliases only in the table / only in the JSON (empty when in sync or no rows)."""
    if not table_rows:
        return {"only_in_table": [], "only_in_json": [], "table_rows": 0}
    table = {(norm_player_name(r.get("source_player_name") or ""), r.get("player_key")) for r in table_rows}
    committed = {(norm_player_name(e["alias"]), e["player_key"]) for e in player_aliases.json_entries()}
    return {"only_in_table": sorted(f"{a}->{k}" for a, k in table - committed),
            "only_in_json": sorted(f"{a}->{k}" for a, k in committed - table),
            "table_rows": len(table_rows)}


def reconcile(open_rows: list[dict[str, Any]], players: list[dict[str, Any]],
              now: datetime) -> tuple[list[tuple[int, dict[str, Any]]], dict[str, Any]]:
    """(id, patch) pairs and the report."""
    index = build_index(players)
    patches, settled = [], []
    after: list[dict[str, Any]] = []
    for row in open_rows:
        new = decide(row, index)
        if _changed(row, new):
            body = dict(new)
            if new["status"] == "verified":
                body.update(verified_at=now.isoformat(), verified_by=WRITER)
            patches.append((row["id"], body))
            settled.append({"source": row.get("source"), "name": row.get("source_player_name"),
                            "position": row.get("position"), "from": row.get("status"), **new})
        after.append({**row, **new})
    counts = identity_queue.open_counts(after, now)
    over = {s: c["open"] for s, c in counts.items() if c["open"] > identity_queue.OPEN_NAMES_ALERT}
    promoted: dict[str, int] = {}
    for c in settled:
        if c["status"] == "verified":
            promoted[str(c["source"])] = promoted.get(str(c["source"]), 0) + 1
    runs = []
    for src in sorted(set(counts) | set(promoted)):
        c = counts.get(src, {"unmatched": 0, "review": 0, "provisional": 0, "open": 0, "names": []})
        runs.append({"run_at": now.isoformat(), "run_label": WRITER, "source": src,
                     "total_aliases": c["open"] + promoted.get(src, 0), "verified": promoted.get(src, 0),
                     "promoted": promoted.get(src, 0), "unmatched": c["unmatched"], "review": c["review"],
                     "provisional": c["provisional"], "queued": c["open"],
                     "detail": {"open_names": c["names"], "window_days": identity_queue.RECENT_DAYS}})
    report = {
        "schema": "player-identity-reconcile-v1",
        "generated_at": now.isoformat(),
        "open_rows_read": len(open_rows),
        "changed": settled,
        "open_by_source": counts,
        "alert_threshold": identity_queue.OPEN_NAMES_ALERT,
        "window_days": identity_queue.RECENT_DAYS,
        "sources_over_threshold": over,
        "runs": runs,
        "fuzzy_floor": FUZZY_FLOOR,
        "fuzzy_margin": FUZZY_MARGIN,
    }
    return patches, report


# ----------------------------------------------------------------- Supabase

def _sb():
    return identity_queue._sb()


def _fetch_open() -> list[dict[str, Any]]:
    return _sb().get_all(identity_queue.TABLE,
                         "?select=id,source,source_player_name,norm_name,position,status,player_key,"
                         "confidence,candidate_keys,method,last_seen_at"
                         "&status=in.(unmatched,review,provisional)")


def _fetch_players() -> list[dict[str, Any]]:
    return _sb().get_all("players", "?select=player_key,full_name,position,active")


def _fetch_curated() -> list[dict[str, Any]]:
    return _sb().get_all(identity_queue.TABLE,
                         f"?select=id,source_player_name,player_key&source=eq.*&status=eq.verified"
                         f"&method=eq.{player_aliases.CURATED_METHOD}")


def _patch(row_id: int, body: dict[str, Any]) -> None:
    _sb().patch(identity_queue.TABLE, body, f"?id=eq.{row_id}")


def _post_runs(rows: list[dict[str, Any]]) -> None:
    if rows:
        _sb().post(RUNS_TABLE, rows, prefer="return=minimal")


def _record(ok: bool, content_ok: bool, error_code: str | None) -> None:
    _sb().rpc("monitoring_record_observation", {
        "p_check_id": CHECK_ID, "p_ok": ok, "p_content_ok": content_ok,
        "p_error_code": error_code, "p_scheduler_owner_id": "player-identity-reconcile.yml"})


fetch_open: Callable[[], list[dict[str, Any]]] = _fetch_open
fetch_players: Callable[[], list[dict[str, Any]]] = _fetch_players
fetch_curated: Callable[[], list[dict[str, Any]]] = _fetch_curated
patch_row: Callable[[int, dict[str, Any]], None] = _patch
post_runs: Callable[[list[dict[str, Any]]], None] = _post_runs
record_check: Callable[[bool, bool, str | None], None] = _record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="apply the changes and record the monitored check")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        players = fetch_players()
        if not players:
            raise RuntimeError("public.players read returned no rows")
        patches, report = reconcile(fetch_open(), players, now)
        report["curated_drift"] = curated_drift(fetch_curated())
        if args.write:
            for row_id, body in patches:
                patch_row(row_id, body)
            post_runs(report["runs"])  # history per source: public.player_identity_reconcile_runs
        report["mode"] = "write" if args.write else "dry-run"
    except Exception as exc:  # noqa: BLE001 -- recorded as a failed run
        print(f"IDENTITY RECONCILE FAILED: {type(exc).__name__}: {str(exc)[:300]}")
        if args.write:
            try:
                record_check(False, False, "RECONCILE_FAILED")
            except Exception as rec_exc:  # noqa: BLE001
                print(f"could not record the check: {rec_exc}")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    drift = report["curated_drift"]
    print(f"identity reconcile ({report['mode']}): {report['open_rows_read']} open rows read, "
          f"{len(patches)} changed")
    for c in report["changed"]:
        print(f"  {c['source']}: {c['name']} ({c['position'] or '-'}) {c['from']} -> {c['status']}"
              f" key={c['player_key']} conf={c['confidence']}")
    for src, c in report["open_by_source"].items():
        print(f"  open {src}: {c['open']} (unmatched {c['unmatched']}, review {c['review']}, "
              f"provisional {c['provisional']}): {', '.join(c['names'])[:400]}")
    if not report["open_by_source"]:
        print("  open: none")
    if drift["only_in_table"] or drift["only_in_json"]:
        print(f"  WARNING curated alias drift: table-only {drift['only_in_table']}, json-only {drift['only_in_json']}")
    content_ok = not report["sources_over_threshold"] and not drift["only_in_table"] and not drift["only_in_json"]
    if args.write:
        record_check(True, content_ok, None if content_ok else "IDENTITY_OPEN_NAMES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
