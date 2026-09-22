"""Shared primitives for the weekly CBS / USA Today ingestion wrappers.

Pipeline order per source (see ingest_cbs.py / ingest_usatoday.py):
  discover -> pull -> write pull JSON -> validate tables -> dedupe ->
  build rows (identity resolution) -> dry-run save -> live save -> verify.

Verification is intentionally independent of the savers: the wrapper recounts
the weekly grain from the database itself and fails closed on any mismatch.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from typing import Any, Callable

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PULLS_DIR = os.path.join(REPO, "ops", "watchdog", "pulls")


class IngestError(Exception):
    """A wrapper-level failure. Nonzero exit; cron surfaces it."""


# ---------------------------------------------------------------------------
# URL week gate: discovery tries the requested week and preceding weeks, so
# the wrapper must reject any selected article that is not exactly the
# requested week. Never ingest a stale fallback.
# ---------------------------------------------------------------------------

_URL_WEEK_RE = re.compile(r"week-(\d+)", re.IGNORECASE)


def url_week(url: str) -> int | None:
    """Extract the week number from a trade-chart article URL slug, or None."""
    m = _URL_WEEK_RE.search(url or "")
    return int(m.group(1)) if m else None


def assert_url_week(url: str, week: int) -> int:
    """Fail closed when the selected article is not exactly the requested week."""
    found = url_week(url)
    if found is None:
        raise IngestError(
            f"could not determine week from URL {url!r}; refusing to ingest"
        )
    if found != week:
        raise IngestError(
            f"stale article rejected: URL is week {found}, requested week {week}: {url}"
        )
    return found


# ---------------------------------------------------------------------------
# Table validation: nonempty QB/RB/WR/TE data is required before any write.
# Position is inferred from table-title keywords, not table order.
# ---------------------------------------------------------------------------

_POS_PATTERNS: dict[str, tuple[str, ...]] = {
    "QB": (r"\bquarterbacks?\b", r"\bqbs?\b"),
    "RB": (r"\brunning backs?\b", r"\brbs?\b"),
    "WR": (r"\bwide receivers?\b", r"\bwrs?\b"),
    "TE": (r"\btight ends?\b", r"\btes?\b"),
}


def table_position(title: str) -> str | None:
    title = (title or "").lower()
    for pos, patterns in _POS_PATTERNS.items():
        if any(re.search(p, title) for p in patterns):
            return pos
    return None


def validate_tables(tables: list[dict[str, Any]]) -> dict[str, int]:
    """Require nonempty QB/RB/WR/TE tables. Returns {pos: row_count}."""
    found: dict[str, int] = {}
    for t in tables:
        pos = table_position(t.get("title", ""))
        if pos is None:
            continue
        n = len(t.get("rows") or [])
        found[pos] = max(found.get(pos, 0), n)
    missing = [p for p in ("QB", "RB", "WR", "TE") if p not in found]
    empty = [p for p, n in found.items() if n == 0]
    if missing or empty:
        raise IngestError(
            "table validation failed: missing=%s empty=%s (need nonempty QB/RB/WR/TE)"
            % (missing, empty)
        )
    return found


# ---------------------------------------------------------------------------
# Fingerprint + dedupe state: skip the write when the same article content
# was already ingested (unless --force).
# ---------------------------------------------------------------------------

def fingerprint(tables: list[dict[str, Any]]) -> str:
    canon = json.dumps(tables, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def state_path(source: str, state_dir: str | None = None) -> str:
    return os.path.join(state_dir or PULLS_DIR,
                        f"last_ingest_{source}.json")


def load_state(source: str, state_dir: str | None = None) -> dict[str, Any]:
    path = state_path(source, state_dir)
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(source: str, state: dict[str, Any],
               state_dir: str | None = None) -> str:
    path = state_path(source, state_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    return path


# ---------------------------------------------------------------------------
# DB adapter. The default count callable resolves the module attribute at
# call time so tests can monkeypatch the saver's injectable count_rows.
# ---------------------------------------------------------------------------

def _default_count_rows(table: str, params: str) -> int:
    import save_espn_cbs_references

    return int(save_espn_cbs_references.count_rows(table, params))


def _default_fetch_rows(table: str, params: str) -> list[dict[str, Any]]:
    import save_espn_cbs_references

    return save_espn_cbs_references.fetch_rows(table, params)


class Db:
    def __init__(self, count_fn: Callable[[str, str], int] | None = None,
                 rows_fn: Callable[[str, str], list[dict[str, Any]]] | None = None):
        self.count_fn = count_fn or _default_count_rows
        self.rows_fn = rows_fn or _default_fetch_rows

    def grain_count(self, table: str, source: str, variant: str,
                    scoring: str, season: int, week: int,
                    bake_id: str | None = None) -> int:
        params = ("?select=player_key"
                  f"&source=eq.{source}&variant=eq.{variant}"
                  f"&scoring=eq.{scoring}&season=eq.{season}&week=eq.{week}")
        if bake_id is not None:
            params += f"&bake_id=eq.{bake_id}"
        return int(self.count_fn(table, params))

    def grain_native_values(self, table: str, source: str, variant: str,
                            season: int, week: int) -> dict[tuple[int, str], float]:
        """{(player_key, scoring): native_value} for the weekly grain.

        Used by the USA Today same-week guard to compare published content
        without trusting bake ids. Rows with missing/unparseable fields are
        skipped (fail-closed comparison treats them as a key-set difference
        at the guard, never as equal).
        """
        params = ("?select=player_key,scoring,native_value"
                  f"&source=eq.{source}&variant=eq.{variant}"
                  f"&season=eq.{season}&week=eq.{week}")
        out: dict[tuple[int, str], float] = {}
        for r in self.rows_fn(table, params):
            try:
                out[(int(r["player_key"]), str(r["scoring"]))] = float(
                    r["native_value"])
            except (KeyError, TypeError, ValueError):
                continue
        return out


# ---------------------------------------------------------------------------
# The engine. Source modules provide a config dict + thin run()/main().
# ---------------------------------------------------------------------------

def make_pull_path(prefix: str, pulls_dir: str | None = None) -> str:
    d = pulls_dir or PULLS_DIR
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{prefix}-{date.today().isoformat()}.json")


def run_ingest(cfg: dict[str, Any], *,
               week: int | None = None,
               url: str | None = None,
               dry_run: bool = False,
               force: bool = False,
               discover_fn: Callable | None = None,
               pull_fn: Callable | None = None,
               build_fn: Callable | None = None,
               save_fn: Callable | None = None,
               guard_build_fn: Callable | None = None,
               db: Db | None = None,
               state_dir: str | None = None,
               pulls_dir: str | None = None) -> dict[str, Any]:
    """Run the full discover -> pull -> save -> verify pipeline for one source.

    Returns a result dict. Raises IngestError on any wrapper-level failure;
    lets the saver's SystemExit propagate (fail closed).
    """
    name = cfg["name"]
    week_fn = cfg["week_fn"]
    week = week or week_fn()
    season = cfg["season"]

    discover_fn = discover_fn or cfg["discover_fn"]
    pull_fn = pull_fn or cfg["pull_fn"]
    build_fn = build_fn or cfg["build_fn"]
    save_fn = save_fn or cfg["save_fn"]
    guard_build_fn = guard_build_fn or cfg.get("guard_build_fn")
    db = db or Db()

    # 1. Discover. DiscoveryFailed (not published yet) is a quiet cron skip
    # for sources whose discovery defines one (USA Today). CBS discovery
    # has no quiet path: a discovery failure there is a genuine failure.
    disc_exc = cfg.get("discovery_failed_cls")
    try:
        url = url or discover_fn(week)
    except Exception as e:
        if disc_exc is not None and isinstance(e, disc_exc):
            print(f"[{name}] week {week} article not published yet; skipping ({e})",
                  flush=True)
            return {"status": "not_published", "week": week}
        raise
    print(f"[{name}] url: {url}", flush=True)

    # 2. Exact-week gate: never ingest a stale fallback article.
    assert_url_week(url, week)

    # 3. Pull + persist pull JSON.
    tables = pull_fn(url)
    pos_counts = validate_tables(tables)
    total_rows = sum(pos_counts.values())
    print(f"[{name}] tables ok: " +
          ", ".join(f"{p}={n}" for p, n in sorted(pos_counts.items())),
          flush=True)
    pull_payload = {"url": url, "fetched_at": date.today().isoformat(),
                    "tables": tables}
    pull_path = make_pull_path(cfg["pull_prefix"], pulls_dir)
    with open(pull_path, "w") as f:
        json.dump(pull_payload, f)
    print(f"[{name}] wrote {pull_path}", flush=True)

    # 4. Dedupe against the last successful ingest.
    fp = fingerprint(tables)
    state = load_state(name, state_dir)
    if (not force and state.get("url") == url
            and state.get("week") == week
            and state.get("fingerprint") == fp):
        print(f"[{name}] unchanged since last ingest; skipping (use --force)",
              flush=True)
        return {"status": "unchanged", "week": week, "url": url}

    # 5. Build rows (identity resolution happens inside the saver builders).
    bake_id = None
    if cfg.get("bake_id_fn"):
        bake_id = cfg["bake_id_fn"](week, state)
    clean, review, pulled_at, _purl = build_fn(pull_path, week, bake_id)
    if not clean:
        raise IngestError(f"[{name}] zero clean rows after identity resolution")
    per_scoring: dict[str, int] = {}
    for row in clean:
        per_scoring[row["scoring"]] = per_scoring.get(row["scoring"], 0) + 1
    missing_scorings = [s for s in cfg["scorings"] if s not in per_scoring]
    if missing_scorings:
        raise IngestError(
            f"[{name}] clean rows missing scorings {missing_scorings}; "
            f"have {sorted(per_scoring)}")
    print(f"[{name}] clean={len(clean)} review={len(review)} "
          f"per_scoring={per_scoring}", flush=True)

    # 6. Snapshot prior-week counts (prior weeks must be preserved by writes).
    prior_snapshot: dict[str, int] = {}
    if week > 1:
        for s in cfg["scorings"]:
            prior_snapshot[s] = db.grain_count(
                cfg["table"], cfg["source"], cfg["variant"], s, season, week - 1)

    # 7. Dry-run: saver dry-run resolves identities with no writes. The
    #    same-week guard does not apply here (nothing is written).
    if dry_run:
        res = save_fn(pull_path, True, week, bake_id)
        print(f"[{name}] dry-run ok: would write "
              f"{res.get('written', len(clean))} rows "
              f"({res.get('review_count', len(review))} review), no writes made",
              flush=True)
        return {"status": "dry_run", "week": week, "url": url,
                "clean": len(clean), "review": len(review),
                "per_scoring": per_scoring}

    # 8. Source-specific pre-write guard (e.g. USA Today same-week fork).
    #    Applies to the live write path only. A guard may return the string
    #    "unchanged" to request a quiet skip (no write, state recorded) when
    #    the DB already holds identical content for the week. The guard
    #    compares PUBLISHED (native) content, so it sees the pre-reindex rows
    #    when guard_build_fn is set: reindex exclusions must never trip the
    #    key-set check.
    if cfg.get("pre_write_guard"):
        guard_clean = clean
        if guard_build_fn is not None:
            guard_clean, _g_review, _g_pa, _g_pu = guard_build_fn(
                pull_path, week, bake_id)
        skip = cfg["pre_write_guard"](db, week, per_scoring, guard_clean)
        if skip == "unchanged":
            new_state = {"url": url, "week": week, "fingerprint": fp,
                         "pull_path": pull_path, "written": 0,
                         "review_count": len(review), "bake_id": None,
                         "note": "same-week content unchanged in DB; no write",
                         "at": date.today().isoformat()}
            save_state(name, new_state, state_dir)
            return {"status": "same_week_unchanged", "week": week, "url": url,
                    "clean": len(clean), "review": len(review)}

    # 9. Live save. The saver fails closed itself (SystemExit) on zero rows
    #    or count mismatch; that propagates and is a cron-visible failure.
    res = save_fn(pull_path, False, week, bake_id)
    written = int(res.get("written", 0))
    review_count = int(res.get("review_count", len(review)))
    if written != len(clean):
        raise IngestError(
            f"[{name}] saver reported written={written} but clean rows="
            f"{len(clean)}")

    # 10. Independent post-write verification (the wrapper recounts itself).
    verify_counts(cfg, db, week, season, per_scoring, prior_snapshot, bake_id)

    new_state = {"url": url, "week": week, "fingerprint": fp,
                 "pull_path": pull_path, "written": written,
                 "review_count": review_count, "bake_id": bake_id,
                 "at": date.today().isoformat()}
    if bake_id and cfg.get("bake_id_fn"):
        new_state["bake_seq"] = state.get("bake_seq", 0) + 1
    save_state(name, new_state, state_dir)

    print(f"[{name}] INGEST OK week={week} written={written} "
          f"review={review_count} bake_id={bake_id}", flush=True)
    return {"status": "ok", "week": week, "url": url, "written": written,
            "review_count": review_count, "per_scoring": per_scoring,
            "bake_id": bake_id}


def verify_counts(cfg: dict[str, Any], db: Db, week: int, season: int,
                  per_scoring: dict[str, int],
                  prior_snapshot: dict[str, int],
                  bake_id: str | None) -> None:
    """Independent post-write verification. Raises IngestError on mismatch.

    Named defects this catches: short/over write, cross-scoring bleed,
    prior-week clobbering, wrong bake id.
    """
    name = cfg["name"]
    total = 0
    for s, expected in sorted(per_scoring.items()):
        got = db.grain_count(cfg["table"], cfg["source"], cfg["variant"],
                             s, season, week)
        total += got
        if got != expected:
            raise IngestError(
                f"[{name}] post-write count mismatch scoring={s}: "
                f"db={got} expected={expected}")
    if total != sum(per_scoring.values()):
        raise IngestError(
            f"[{name}] post-write total mismatch: db={total} "
            f"expected={sum(per_scoring.values())}")
    for s, before in sorted(prior_snapshot.items()):
        after = db.grain_count(cfg["table"], cfg["source"], cfg["variant"],
                               s, season, week - 1)
        if after != before:
            raise IngestError(
                f"[{name}] prior week {week - 1} scoring={s} changed by write: "
                f"before={before} after={after}")
    if cfg.get("verify_bake_id") and bake_id:
        # bake id is shared across scorings: sum all scorings with the filter.
        got = sum(db.grain_count(cfg["table"], cfg["source"], cfg["variant"],
                                 s, season, week, bake_id=bake_id)
                  for s in cfg["scorings"])
        if got != sum(per_scoring.values()):
            raise IngestError(
                f"[{name}] bake_id={bake_id} count mismatch: db={got} "
                f"expected={sum(per_scoring.values())}")
