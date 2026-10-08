"""Weekly CBS trade-chart ingestion: discover -> pull -> save -> verify.

Each write is an immutable bake (bake_id cbswk<week>_<date>_v<n>), like USA
Today: a same-week revision adds a version instead of overwriting the week.

Fails closed on: article not matching the requested week (never ingests a
stale fallback), fewer than 4 nonempty QB/RB/WR/TE tables, zero clean rows,
saver count mismatch, post-write grain mismatch, or prior-week clobbering.
Skips quietly when the week's article is not published yet or when the
content is unchanged since the last successful ingest (unless --force).

Usage:
    python3 ingest_cbs.py [--week N] [--url URL] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipelines"))

import ingest_common as ic  # noqa: E402
from _common import content_week  # noqa: E402


def _discover_fn(week: int) -> str:
    import pull_cbs

    return pull_cbs.discover_url(week)


def _pull_fn(url: str) -> list[dict[str, Any]]:
    import pull_cbs

    # JEG-85: pull() returns (tables, headline); ingest only needs tables.
    tables, _headline = pull_cbs.pull(url)
    return tables


def _build_fn(json_path: str, week: int, bake_id: str | None):
    from pathlib import Path

    from save_espn_cbs_references import build_cbs_rows

    return build_cbs_rows(Path(json_path), week, bake_id)


def _save_fn(json_path: str, dry_run: bool, week: int, bake_id: str | None):
    from pathlib import Path

    from save_espn_cbs_references import save_source

    return save_source("cbs", dry_run=dry_run, espn_csv=None, espn_meta=None,
                       cbs_json=Path(json_path), week=week, bake_id=bake_id)


def bake_id_fn(week: int, state: dict[str, Any]) -> str:
    """cbswk<week>_<exec-date>_v<seq> (GAP-CBS-WEEK-OVERWRITE): a same-week
    revision is a new immutable bake, never an in-place overwrite."""
    from save_espn_cbs_references import cbs_bake_id

    seq = 1
    if state.get("week") == week:
        seq = int(state.get("bake_seq", 0)) + 1
    return cbs_bake_id(week, seq)


def pre_write_guard(db: "ic.Db", week: int, per_scoring: dict[str, int],
                    clean: list[dict[str, Any]]) -> str | None:
    """Quiet skip when the DB already holds this exact week's content.

    Muse kept a local fingerprint state file between runs, so a daily cron
    saw "unchanged since last ingest" and never re-wrote. A CI runner starts
    with no state, so without this guard every daily run would re-upsert the
    same week and bump `pulled_at` on unchanged rows (making stale content
    look freshly pulled). Identical (player_key, scoring) -> native_value
    sets mean nothing to write. Any difference proceeds to a NEW versioned
    bake (GAP-CBS-WEEK-OVERWRITE, 2026-10-08): the week's earlier bake stays
    in the table, and readers select the latest one. The comparison is
    against the latest bake (Db.grain_native_values).
    """
    existing = db.grain_native_values(CFG["table"], CFG["source"],
                                      CFG["variant"], CFG["season"], week)
    if not existing:
        return None
    new: dict[tuple[int, str], float] = {}
    for r in clean:
        new[(int(r["player_key"]), str(r["scoring"]))] = float(r["native_value"])
    if set(new) == set(existing) and all(
            abs(existing[k] - new[k]) <= 1e-9 for k in new):
        print(f"[cbs] same-week content unchanged in DB ({len(new)} keys); "
              "skipping write", flush=True)
        return "unchanged"
    only_old, only_new = set(existing) - set(new), set(new) - set(existing)
    changed = sorted(k for k in set(new) & set(existing)
                     if abs(existing[k] - new[k]) > 1e-9)
    print(f"[cbs] same-week content changed vs DB: existing={len(existing)} "
          f"new={len(new)} removed={len(only_old)} added={len(only_new)} "
          f"changed={len(changed)} e.g. "
          f"{[(k, existing[k], new[k]) for k in changed[:3]]} "
          f"{sorted(only_old)[:3]} {sorted(only_new)[:3]}; writing", flush=True)
    return None


CFG: dict[str, Any] = {
    "name": "cbs",
    "source": "cbs",
    "variant": "as_published",
    "table": "cbs_trade_values",  # bare name: PostgREST path is /rest/v1/<table>
    "scorings": ("standard", "half_ppr", "ppr"),
    "season": 2026,
    "pull_prefix": "cbs",
    "week_fn": content_week,
    "discovery_failed_cls": None,  # CBS discovery raises RuntimeError; not-published is not a quiet path
    "discover_fn": _discover_fn,
    "pull_fn": _pull_fn,
    "build_fn": _build_fn,
    "save_fn": _save_fn,
    "pre_write_guard": pre_write_guard,
    "bake_id_fn": bake_id_fn,
    "verify_bake_id": True,
}


def run(week: int | None = None, url: str | None = None,
        dry_run: bool = False, force: bool = False,
        discover_fn: Callable | None = None,
        pull_fn: Callable | None = None,
        build_fn: Callable | None = None,
        save_fn: Callable | None = None,
        guard_build_fn: Callable | None = None,
        db: "ic.Db | None" = None,
        state_dir: str | None = None,
        pulls_dir: str | None = None) -> dict[str, Any]:
    cfg = dict(CFG)
    return ic.run_ingest(cfg, week=week, url=url, dry_run=dry_run, force=force,
                         discover_fn=discover_fn, pull_fn=pull_fn,
                         build_fn=build_fn, save_fn=save_fn,
                         guard_build_fn=guard_build_fn,
                         db=db, state_dir=state_dir, pulls_dir=pulls_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Weekly CBS trade-chart ingestion")
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--url", default=None,
                    help="explicit article URL (manual override; skips discovery)")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve identities, report, no writes")
    ap.add_argument("--force", action="store_true",
                    help="re-ingest even if content is unchanged")
    args = ap.parse_args(argv)
    try:
        run(week=args.week, url=args.url, dry_run=args.dry_run,
            force=args.force)
    except ic.IngestError as e:
        print(f"[cbs] INGEST FAILED: {e}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
