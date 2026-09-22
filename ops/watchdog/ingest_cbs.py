"""Weekly CBS trade-chart ingestion: discover -> pull -> save -> verify.

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
from _common import nfl_week  # noqa: E402


def _discover_fn(week: int) -> str:
    import pull_cbs

    return pull_cbs.discover_url(week)


def _pull_fn(url: str) -> list[dict[str, Any]]:
    import pull_cbs

    return pull_cbs.pull(url)


def _build_fn(json_path: str, week: int, _bake_id: str | None):
    from pathlib import Path

    from save_espn_cbs_references import build_cbs_rows

    return build_cbs_rows(Path(json_path), week)


def _save_fn(json_path: str, dry_run: bool, week: int, _bake_id: str | None):
    from pathlib import Path

    from save_espn_cbs_references import save_source

    return save_source("cbs", dry_run=dry_run, espn_csv=None, espn_meta=None,
                       cbs_json=Path(json_path), week=week)


CFG: dict[str, Any] = {
    "name": "cbs",
    "source": "cbs",
    "variant": "as_published",
    "table": "cbs_trade_values",  # bare name: PostgREST path is /rest/v1/<table>
    "scorings": ("standard", "half_ppr", "ppr"),
    "season": 2026,
    "pull_prefix": "cbs",
    "week_fn": nfl_week,
    "discovery_failed_cls": None,  # CBS discovery raises RuntimeError; not-published is not a quiet path
    "discover_fn": _discover_fn,
    "pull_fn": _pull_fn,
    "build_fn": _build_fn,
    "save_fn": _save_fn,
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
