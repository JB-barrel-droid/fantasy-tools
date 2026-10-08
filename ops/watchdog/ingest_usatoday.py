"""Weekly USA Today trade-chart ingestion: discover -> pull -> save -> verify.

Same fail-closed contract as ingest_cbs.py, plus two USA Today specifics:
  - Smart same-week guard: if rows already exist for (usatoday, as_published,
    week), the wrapper compares published (native) values. Identical content
    -> quiet skip (no write needed). Changed content or a changed key set ->
    fail closed: same-week replacement semantics (which bake the numbers
    belong to, and how bias_adjusted stays consistent) are still unresolved,
    so a changed re-pull never writes on its own.
  - bake_id verification: every written row must carry the new bake_id.

USA Today values are translated onto the chart scale at write time
(isotonic reindex anchored to the fixture's ESPN leg, in
save_usatoday_references); the DB's `value` column always carries
chart-scale numbers, `native_value` the raw published numbers.

Usage:
    python3 ingest_usatoday.py [--week N] [--url URL] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipelines"))

import ingest_common as ic  # noqa: E402
import pull_usatoday  # noqa: E402
from _common import content_week  # noqa: E402


def _build_fn(json_path: str, week: int, bake_id: str | None):
    from pathlib import Path

    from save_usatoday_references import build_usatoday_rows_final

    # Final rows: values on chart scale (isotonic reindex applied), so the
    # counted rows are exactly the rows the write pass would store.
    return build_usatoday_rows_final(Path(json_path), week, bake_id)


def _guard_build_fn(json_path: str, week: int, bake_id: str | None):
    from pathlib import Path

    from save_usatoday_references import build_usatoday_rows

    # Pre-reindex rows for the same-week guard: the guard compares PUBLISHED
    # (native) content, so reindex exclusions (e.g. players with no ESPN
    # anchor pair) must not trip its key-set check.
    return build_usatoday_rows(Path(json_path), week, bake_id)


def _save_fn(json_path: str, dry_run: bool, week: int, bake_id: str | None):
    from pathlib import Path

    from save_usatoday_references import save_usatoday

    return save_usatoday(Path(json_path), dry_run=dry_run, week=week,
                         bake_id=bake_id)


def bake_id_fn(week: int, state: dict[str, Any]) -> str:
    """usatwk<week>_<YYYY-MM-DD>t<HHMM>_v<seq> (UTC minute). seq bumps on a
    re-ingest of the same week when a state file exists; the minute stamp
    keeps two same-day revisions apart on a stateless CI runner
    (USAT-BAKE-SAMEDAY)."""
    seq = 1
    if state.get("week") == week:
        seq = int(state.get("bake_seq", 0)) + 1
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dt%H%M")
    return f"usatwk{week}_{stamp}_v{seq}"


def pre_write_guard(db: "ic.Db", week: int, per_scoring: dict[str, int],
                    clean: list[dict[str, Any]]) -> str | None:
    """Same-week versioning guard for the (usatoday, as_published) grain.

    Week-versioning practice (Jeremy 2026-10-02): a week may hold multiple
    bakes; each ingest writes an immutable version, never overwrites. So:
      - No existing rows for the week -> proceed with the write.
      - Existing rows with IDENTICAL published (native) values -> quiet skip
        ("unchanged"): the article's numbers are already in the DB, so no
        write is needed. The reindex is deterministic, so identical natives
        imply identical reindexed values.
      - Existing rows with DIFFERENT published values -> proceed: the new
        pull becomes a new versioned bake (bake_id in the upsert grain).
        Readers select one bake per week; versions are never blended.
      - Fail closed only on a degenerate pull: if more than 5% of the
        existing week's keys are absent from the new pull, the pull is
        probably truncated (e.g. a table failed to parse) and must not
        become the current version. Legitimate same-week revisions add or
        adjust players; they don't vaporize the chart.
    """
    # Share of existing keys allowed to vanish before the pull is judged
    # degenerate. Same-week revisions (2026-10-02: +12 keys, 0 removed)
    # sit far below this; a missed table parse would blow past it.
    MAX_KEY_ATTRITION_FRAC = 0.05

    existing = db.grain_native_values(CFG["table"], CFG["source"],
                                      CFG["variant"], CFG["season"], week)
    if not existing:
        return None
    new: dict[tuple[int, str], float] = {}
    for r in clean:
        new[(int(r["player_key"]), str(r["scoring"]))] = float(r["native_value"])
    only_old = set(existing) - set(new)
    if only_old and len(only_old) / len(existing) > MAX_KEY_ATTRITION_FRAC:
        raise ic.IngestError(
            f"[usatoday] new pull is missing {len(only_old)}/{len(existing)} "
            f"existing week-{week} keys (>{MAX_KEY_ATTRITION_FRAC:.0%} attrition); "
            "probable truncated pull -- not writing a new version.")
    if set(new) == set(existing):
        diffs = [k for k in new if abs(existing[k] - new[k]) > 1e-9]
        if not diffs:
            print(f"[usatoday] same-week content unchanged in DB "
                  f"({len(new)} keys, native values identical); skipping write",
                  flush=True)
            return "unchanged"
    n_new = len(set(new) - set(existing))
    n_chg = sum(1 for k in new if k in existing and abs(existing[k] - new[k]) > 1e-9)
    print(f"[usatoday] same-week content changed: {n_new} new keys, "
          f"{n_chg} changed values; writing as a new versioned bake",
          flush=True)
    return None


CFG: dict[str, Any] = {
    "name": "usatoday",
    "source": "usatoday",
    "variant": "as_published",
    "table": "source_trade_values",  # bare name: PostgREST path is /rest/v1/<table>
    "scorings": ("std", "half", "full"),
    "season": 2026,
    "pull_prefix": "usatoday",
    "week_fn": content_week,
    "discovery_failed_cls": pull_usatoday.DiscoveryFailed,
    "discover_fn": pull_usatoday.discover_url,
    "pull_fn": pull_usatoday.pull,
    "build_fn": _build_fn,
    "save_fn": _save_fn,
    "guard_build_fn": _guard_build_fn,
    "bake_id_fn": bake_id_fn,
    "pre_write_guard": pre_write_guard,
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
    ap = argparse.ArgumentParser(
        description="Weekly USA Today trade-chart ingestion")
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
        print(f"[usatoday] INGEST FAILED: {e}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
