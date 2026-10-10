#!/usr/bin/env python3
"""Per-week source history: the saved inputs the chart engine needs to
recompute a PRIOR week at the reader's league settings (v2 "Risers & fallers"
and the Δ prior-week filter; frame 22, docs/v2-design-notes.md "Back-end
contract: history").

Store: data/history/week-<N>.json, one file per content week, committed.
Served: copied to assets/history/ by `make sync` (pipelines/sync_dashboard_artifacts.py).

What an entry holds (one source, one content week):
  * published charts (usatoday, fantasycalc, fantasypros, cbs): the source's
    own as-published native values for the saved 12-team, 1-QB setup, per
    scoring -- exactly the `native` cells the engine derives a chart from
    (ValueModel.derivePublishedSetup). Origin: Supabase public.source_trade_values
    / public.cbs_trade_values, one entry per bake (its latest pull).
  * projection sources (espn, cbsros, razzball): per-game projections per
    scoring, the same field the engine reads from players.json (espn_ppg,
    cbsros_ppg, rz_ppg), rounded to PPG_DECIMALS as pipelines/bake_players.py
    does.
    Origin: players.json (what the page served) or the Supabase projection
    tables.

Week coding (docs/week-coding-rules.md): an entry's week comes from its
CONTENT, never from the request or a label:
  * content date (source_content_date / snapshot date) -> content week on the
    Tuesday-flip calendar (pipelines/nfl_week.py);
  * CBS (no content date) -> the pull's week column (the puller reads it from
    the article), and the pull cannot predate that week;
  * FantasyCalc (a live crowd value, no article) -> the pull's week column,
    which must equal the content week the pull happened in.
An entry whose evidence does not give the file's week is refused
(validate_week_doc), so a Week 4 file can never carry Week 3 content.

Which version is a week's snapshot (Jeremy 2026-10-08, "the snapshot we
compare to week over week"; prefer()): articles = the latest revision saved
before the week froze; FantasyCalc = the first pull at or after Tuesday
12:00 UTC of the week; projections = the newest snapshot dated in the week.
Every other distinct version is kept in data/history/superseded/week-<N>.json
(not served), so a mid-week replacement keeps both (HISTORY-WEEK-CAPTURE).
Published-chart versions are read from the base tables, where every ingest
writes an immutable bake, so a revision saved and replaced between two chain
runs is still captured.

Append-only: a week is frozen once the content calendar has moved past it.
A frozen entry is never replaced (a differing candidate is reported and
dropped); a source missing from a frozen week may still be added when its
genuine content for that week turns up. The open (current) week keeps the
newest content seen for each source until it freezes.

index.json also records which saved week each source's CURRENTLY SERVED
inputs are (matched by content fingerprint against the fixture /
players.json, not by the section's label), so the engine pairs "current"
with exactly the week before it.

Usage:
  python3 pipelines/build_week_history.py                 # local: index only
  python3 pipelines/build_week_history.py --supabase      # CI: fetch + append
  python3 pipelines/build_week_history.py --supabase-dump rows.json
  python3 pipelines/build_week_history.py --players-from-git <rev> --provenance "..."
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from nfl_week import content_week_start, current_nfl_week  # noqa: E402

sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from games_remaining import PPG_DECIMALS  # noqa: E402  (bake_players' per-game precision)

HISTORY_DIR = ROOT / "data" / "history"
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"

SCHEMA = "week-history/1"
INDEX_SCHEMA = "week-history-index/1"
SUPERSEDED_SCHEMA = "week-history-superseded/1"
SUPERSEDED_DIR_NAME = "superseded"   # data/history/superseded/ (never served)
MAX_SUPERSEDED_PER_SOURCE = 12        # newest kept per source and week
# FantasyCalc is a continuous crowd value: its week-N snapshot is the first
# pull at or after this cut in content week N (the Tuesday turnover, after the
# Monday-night reaction, when the Week-N articles are out).
FANTASYCALC_CUT_HOUR_UTC = 12
SEASON = 2026
SCORINGS = ("standard", "half_ppr", "ppr")
PUBLISHED = ("usatoday", "fantasycalc", "fantasypros", "cbs")
PROJECTION_FIELDS = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
PLAYERS_META_DATE = {"espn": "espn_snapshot", "cbsros": "cbsros_snapshot", "razzball": "rz_snapshot"}
SB_SCORING = {"standard": "standard", "std": "standard", "half": "half_ppr",
              "half_ppr": "half_ppr", "full": "ppr", "ppr": "ppr"}
FIXTURE_COMBO = {"standard": "standard_12", "half_ppr": "half_12", "ppr": "full_12"}
# Origin preference inside one week when two captures carry the same
# snapshot date: what the page served beats a table read.
ORIGIN_RANK = {"players.json": 2, "supabase": 1}


class HistoryError(Exception):
    pass


# ---------------------------------------------------------------- week rules

def week_of_day(value) -> int | None:
    """Content week of an ISO date/timestamp (Tuesday flip), or None."""
    if not value:
        return None
    try:
        day = date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return current_nfl_week(day)


def evidence_week(entry: dict) -> int:
    """The content week an entry's own evidence proves. Raises when the
    evidence is missing or contradicts itself (fail closed, never relabel)."""
    ev = entry.get("week_evidence") or {}
    rule = ev.get("rule")
    if rule == "content_date":
        week = week_of_day(ev.get("content_date"))
        if week is None:
            raise HistoryError(f"{entry.get('source')}: content_date rule without a date")
        if ev.get("week_column") is not None and int(ev["week_column"]) != week:
            raise HistoryError(f"{entry.get('source')}: week column {ev['week_column']} "
                               f"disagrees with content date {ev['content_date']} (week {week})")
        return week
    if rule == "week_column_article":  # CBS: week read from the article
        week = int(ev.get("week_column") or 0)
        pulled = week_of_day(ev.get("pulled_at"))
        if week < 1 or pulled is None or pulled < week:
            raise HistoryError(f"{entry.get('source')}: week column {week} pulled in week {pulled}")
        return week
    if rule == "week_column_pull":  # FantasyCalc: live value, the pull IS the content
        week = int(ev.get("week_column") or 0)
        pulled = week_of_day(ev.get("pulled_at"))
        if week < 1 or pulled != week:
            raise HistoryError(f"{entry.get('source')}: week column {week} but pulled in week {pulled}")
        return week
    raise HistoryError(f"{entry.get('source')}: unknown week evidence rule {rule!r}")


# --------------------------------------------------------------- fingerprints

def _num(value) -> float:
    return float(round(float(value), 6))


def canonical_values(entry: dict) -> dict:
    if entry["kind"] == "published_chart":
        return {s: {str(k): _num(v) for k, v in sorted(entry["natives"][s].items(), key=lambda kv: int(kv[0]))}
                for s in SCORINGS if s in entry["natives"]}
    return {str(k): [_num(x) for x in v] for k, v in sorted(entry["ppg"].items(), key=lambda kv: int(kv[0]))}


def fingerprint(entry_or_values: dict) -> str:
    values = canonical_values(entry_or_values) if "kind" in entry_or_values else entry_or_values
    blob = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


# ------------------------------------------------------------------ validate

def validate_week_doc(doc: dict, expected_week: int | None = None) -> None:
    """The no-relabel guard. Raises HistoryError on any entry whose content
    evidence does not prove the document's week."""
    if doc.get("schema") != SCHEMA:
        raise HistoryError(f"schema {doc.get('schema')!r} != {SCHEMA}")
    week = doc.get("week")
    if not isinstance(week, int) or week < 1:
        raise HistoryError(f"bad week {week!r}")
    if expected_week is not None and week != expected_week:
        raise HistoryError(f"file is week-{expected_week} but its document says week {week}")
    if not isinstance(doc.get("frozen"), bool):
        raise HistoryError("frozen must be true/false")
    for source, entry in (doc.get("sources") or {}).items():
        if entry.get("source") != source:
            raise HistoryError(f"entry under {source!r} names {entry.get('source')!r}")
        if entry.get("week") != week:
            raise HistoryError(f"{source}: entry week {entry.get('week')} in the week-{week} file")
        proven = evidence_week(entry)
        if proven != week:
            raise HistoryError(f"{source}: content evidence says week {proven}, file is week {week}")
        if entry.get("kind") == "published_chart":
            if source not in PUBLISHED:
                raise HistoryError(f"{source}: not a published chart")
            natives = entry.get("natives") or {}
            if not natives or any(s not in SCORINGS for s in natives):
                raise HistoryError(f"{source}: natives must be keyed by {SCORINGS}")
            for s, cells in natives.items():
                if not cells:
                    raise HistoryError(f"{source}: empty {s} natives")
                for k, v in cells.items():
                    int(k)
                    if not isinstance(v, (int, float)) or v != v:
                        raise HistoryError(f"{source}: non-numeric native {k}={v!r}")
        elif entry.get("kind") == "projection":
            if PROJECTION_FIELDS.get(source) != entry.get("field"):
                raise HistoryError(f"{source}: field {entry.get('field')!r}")
            if not entry.get("ppg"):
                raise HistoryError(f"{source}: empty ppg")
            for k, v in entry["ppg"].items():
                int(k)
                if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)):
                    raise HistoryError(f"{source}: ppg {k} must be [standard, half_ppr, ppr]")
        else:
            raise HistoryError(f"{source}: unknown kind {entry.get('kind')!r}")
        if entry.get("fingerprint") != fingerprint(entry):
            raise HistoryError(f"{source}: fingerprint does not match its values")


# ------------------------------------------------------------------ captures

def _latest_pull_per_bake(rows: list[dict]) -> list[dict]:
    """Within one bake keep only its latest pull. A bake overwritten in place
    (an upsert re-pulled into the same bake_id, or the pre-versioning CBS
    week grain) leaves rows of players the newer pull dropped behind with an
    older pulled_at; they are leftovers, not a version, and never part of the
    newer one (same rule as api.source_inputs_weekly)."""
    latest: dict = {}
    for row in rows:
        k = (row["source"], int(row["week"]), row.get("bake_id"))
        latest[k] = max(latest.get(k, ""), str(row.get("pulled_at") or ""))
    return [r for r in rows
            if str(r.get("pulled_at") or "") == latest[(r["source"], int(r["week"]), r.get("bake_id"))]]


def published_entries_from_rows(rows: list[dict]) -> list[dict]:
    """Saved chart rows -> one entry per (source, week, version). A version
    is one bake's latest pull (every immutable revision the ingests saved);
    which one is the week's snapshot is merge()'s job (select rule)."""
    groups: dict = {}
    # 12 teams, 1 QB only: superflex / 2-QB rows share a bake (FantasyCalc
    # saves both since feat/superflex-publisher-values) and must never mix
    # into the 1-QB natives the engine derives the chart from.
    rows = [r for r in rows if r.get("source") in PUBLISHED and r.get("week") is not None
            and int(r.get("qb_slots") or 1) == 1 and int(r.get("league_teams") or 12) == 12
            and (r.get("variant") or "as_published") == "as_published"]
    for row in _latest_pull_per_bake(rows):
        source = row["source"]
        if int(row.get("season") or SEASON) != SEASON:
            continue
        scoring = SB_SCORING.get(row["scoring"])
        if scoring is None or row.get("player_key") is None or row.get("native_value") is None:
            continue
        version = (row.get("bake_id"), str(row.get("pulled_at")))
        g = groups.setdefault((source, int(row["week"]), version),
                              {"natives": {}, "pulls": set(), "content": set(), "bakes": set()})
        g["natives"].setdefault(scoring, {})[str(int(row["player_key"]))] = float(row["native_value"])
        g["pulls"].add(str(row["pulled_at"]))
        if row.get("source_content_date"):
            g["content"].add(str(row["source_content_date"])[:10])
        if row.get("bake_id"):
            g["bakes"].add(row["bake_id"])
    out = []
    for (source, week_col, _version), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2][1])):
        if len(g["content"]) > 1:
            raise HistoryError(f"{source} week {week_col}: mixed content dates {sorted(g['content'])}")
        pulled = max(g["pulls"])
        content_date = next(iter(g["content"]), None)
        if content_date:
            ev = {"rule": "content_date", "content_date": content_date, "week_column": week_col,
                  "pulled_at": pulled}
        elif source == "cbs":
            ev = {"rule": "week_column_article", "week_column": week_col, "pulled_at": pulled}
        elif source == "fantasycalc":
            ev = {"rule": "week_column_pull", "week_column": week_col, "pulled_at": pulled}
        else:
            raise HistoryError(f"{source} week {week_col}: no content date")
        entry = {"source": source, "kind": "published_chart", "week": None, "week_evidence": ev,
                 "origin": (f"supabase:{'public.cbs_trade_values' if source == 'cbs' else 'public.source_trade_values'}"
                            f" bake {next(iter(g['bakes']), 'none')} (12 teams, 1 QB, as published)"),
                 "pulled_at": pulled, "bake_ids": sorted(g["bakes"]),
                 "complete": all(s in g["natives"] for s in SCORINGS),
                 "natives": g["natives"], "sort_key": [pulled, ORIGIN_RANK["supabase"]]}
        entry["week"] = evidence_week(entry)
        if entry["week"] != week_col:
            raise HistoryError(f"{source}: week column {week_col} but content week {entry['week']}")
        out.append(entry)
    return out


def projection_entry(source: str, ppg: dict, snapshot_date: str, origin: str, origin_kind: str,
                     pulled_at: str | None = None) -> dict:
    entry = {"source": source, "kind": "projection", "field": PROJECTION_FIELDS[source],
             "week": week_of_day(snapshot_date),
             "week_evidence": {"rule": "content_date", "content_date": snapshot_date[:10],
                               **({"pulled_at": pulled_at} if pulled_at else {})},
             "origin": origin, "snapshot_date": snapshot_date[:10], "complete": True,
             "ppg": ppg, "sort_key": [snapshot_date[:10], ORIGIN_RANK[origin_kind]]}
    if entry["week"] is None:
        raise HistoryError(f"{source}: undated snapshot {snapshot_date!r}")
    return entry


def projection_entries_from_players(players: dict, origin: str) -> list[dict]:
    meta = players.get("meta") or {}
    out = []
    for source, field in PROJECTION_FIELDS.items():
        snap = meta.get(PLAYERS_META_DATE[source])
        if not snap or snap == "?":
            continue
        ppg = {}
        for p in players.get("players") or []:
            v = p.get(field)
            if source == "espn" and not isinstance(v, dict) and p.get("espn_status") == "ineligible":
                # ESPN lists the player and projects 0 (injured/out): part of
                # the snapshot, priced 0 by the leg and shown 0.0, so a prior
                # week can show it too (product-data.js espnProjectsZero).
                ppg[str(int(p["player_key"]))] = [0.0, 0.0, 0.0]
                continue
            if not isinstance(v, dict):
                continue
            vals = [v.get(s) for s in SCORINGS]
            if all(isinstance(x, (int, float)) and x == x for x in vals):
                ppg[str(int(p["player_key"]))] = [float(x) for x in vals]
        if ppg:
            out.append(projection_entry(source, ppg, str(snap), origin, "players.json"))
    return out


def projection_entries_from_tables(snapshots: list[dict]) -> list[dict]:
    """[{src, snap, cd, pulled_at, ppg: {key: [std, half, ppr]}}] from the
    Supabase projection tables -> entries, rounded like bake_players."""
    out = []
    for snap in snapshots:
        source = snap["src"]
        ppg = {}
        for key, vals in (snap.get("ppg") or {}).items():
            if not str(key).lstrip("-").isdigit():
                continue
            if vals is None or len(vals) != 3 or any(x is None for x in vals):
                continue
            ppg[str(int(key))] = [round(float(x), PPG_DECIMALS) for x in vals]
        if not ppg:
            continue
        date_ = snap.get("cd") or snap["snap"]
        table = {"razzball": "razzball_projections", "cbsros": "cbs_ros_projections"}[source]
        out.append(projection_entry(source, ppg, str(date_),
                                    f"supabase:public.{table} snapshot {snap['snap']} (per_game_*, rounded to {PPG_DECIMALS} dp as bake_players)",
                                    "supabase", pulled_at=str(snap.get("pulled_at") or "") or None))
    return out


# ------------------------------------------------------------------ supabase

def fetch_supabase() -> tuple[list[dict], list[dict]]:
    import sbclient  # the CI shim (pipelines/gh_sbclient.py) or Muse's client

    def paged(table, select, order, schema=None):
        rows, offset = [], 0
        while True:
            page = sbclient.get(table, f"?select={select}&order={order}&limit=1000&offset={offset}",
                                schema=schema) if schema else \
                sbclient.get(table, f"?select={select}&order={order}&limit=1000&offset={offset}")
            rows.extend(page)
            if len(page) < 1000:
                return rows
            offset += 1000

    # Every saved version (HISTORY-WEEK-CAPTURE): the ingests write each
    # revision as an immutable bake, so reading the base tables (not the
    # latest-pull view) recovers a version replaced between two chain runs.
    cols = "source,season,week,scoring,player_key,native_value,source_content_date,pulled_at,bake_id,qb_slots,league_teams,variant"
    grain = f"&season=eq.{SEASON}&league_teams=eq.12&qb_slots=eq.1&variant=eq.as_published"

    def published_rows(table, source_filter):
        rows, offset = [], 0
        while True:
            page = sbclient.get(table, f"?select={cols}&{source_filter}{grain}"
                                       f"&order=id&limit=1000&offset={offset}")
            rows.extend(page)
            if len(page) < 1000:
                return rows
            offset += 1000

    published = (published_rows("source_trade_values", "source=in.(fantasycalc,fantasypros,usatoday)")
                 + published_rows("cbs_trade_values", "source=eq.cbs"))
    snaps: dict = {}
    for src, table, date_col in (("razzball", "razzball_projections", "razzball_snapshot_date"),
                                 ("cbsros", "cbs_ros_projections", "cbs_snapshot_date")):
        for r in paged(table, f"player_key,{date_col},source_content_date,pulled_at,"
                              "per_game_standard,per_game_half_ppr,per_game_ppr", "id"):
            s = snaps.setdefault((src, r[date_col]), {"src": src, "snap": r[date_col], "cd": None,
                                                      "pulled_at": None, "ppg": {}})
            s["cd"] = max(filter(None, [s["cd"], r.get("source_content_date")]), default=None)
            s["pulled_at"] = max(filter(None, [s["pulled_at"], r.get("pulled_at")]), default=None)
            if r.get("player_key") is not None:
                s["ppg"][str(r["player_key"])] = [r["per_game_standard"], r["per_game_half_ppr"], r["per_game_ppr"]]
    return published, list(snaps.values())


def rows_from_dump(path: Path) -> tuple[list[dict], list[dict]]:
    """A dump: {"published_rows": [...view rows...], "projection_snapshots": [...]}.
    Published rows may also be grouped as {source, week, scoring, pulled_at,
    bake_id, content_date, natives: {key: value}} (an execute_sql export)."""
    doc = json.loads(path.read_text())
    rows = []
    for r in doc.get("published_rows") or []:
        if "natives" in r:
            for key, value in r["natives"].items():
                if not key.isdigit():
                    continue
                rows.append({"source": r["source"], "season": SEASON, "week": r["week"],
                             "scoring": r["scoring"], "player_key": int(key), "native_value": value,
                             "source_content_date": r.get("content_date"),
                             "pulled_at": r.get("pulled_at"), "bake_id": r.get("bake_id")})
        else:
            rows.append(r)
    return rows, doc.get("projection_snapshots") or []


# ------------------------------------------------------------------- merging

def week_path(week: int, directory: Path = HISTORY_DIR) -> Path:
    return directory / f"week-{week}.json"


def load_weeks(directory: Path = HISTORY_DIR) -> dict[int, dict]:
    docs = {}
    for path in sorted(directory.glob("week-*.json")):
        week = int(path.stem.split("-")[1])
        doc = json.loads(path.read_text())
        validate_week_doc(doc, week)
        docs[week] = doc
    return docs


def _decimals(x: float) -> int:
    text = repr(float(x))
    return 0 if "e" in text or "." not in text else len(text.split(".")[1].rstrip("0"))


def same_content_finer(have: dict, cand: dict) -> bool:
    """True when a candidate is the SAME saved content as a frozen entry, only
    stored at a finer precision (e.g. bake_players moving per-game rates from
    2 dp to PPG_DECIMALS): same source, kind, week and content date / pull,
    the same players, and every saved value equals the candidate's value
    rounded to the saved value's own precision. Anything else is a different
    candidate, and a frozen entry keeps it out (append-only)."""
    if (have.get("source"), have.get("kind"), have.get("week")) != (cand.get("source"), cand.get("kind"), cand.get("week")):
        return False
    ev_have, ev_cand = have.get("week_evidence") or {}, cand.get("week_evidence") or {}
    if have.get("kind") == "projection":
        if have.get("snapshot_date") != cand.get("snapshot_date"):
            return False
        old, new = have["ppg"], cand["ppg"]
        if set(old) != set(new):
            return False
        pairs = [(o, n) for k in old for o, n in zip(old[k], new[k])]
    else:
        if (ev_have.get("content_date"), ev_have.get("week_column"), ev_have.get("pulled_at")) != \
                (ev_cand.get("content_date"), ev_cand.get("week_column"), ev_cand.get("pulled_at")):
            return False
        old, new = have["natives"], cand["natives"]
        if set(old) != set(new) or any(set(old[s]) != set(new[s]) for s in old):
            return False
        pairs = [(old[s][k], new[s][k]) for s in old for k in old[s]]
    finer = False
    for o, n in pairs:
        d = _decimals(o)
        if _decimals(n) < d or abs(float(n) - float(o)) > 0.5 * 10 ** -d + 1e-12:
            return False
        finer = finer or _decimals(n) > d
    return finer


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pulled(entry: dict) -> str:
    return str(entry.get("pulled_at") or (entry.get("week_evidence") or {}).get("pulled_at") or "")


def fantasycalc_cut(week: int) -> str:
    """Tuesday 12:00 UTC of content week `week`, as a comparable timestamp."""
    return f"{content_week_start(week).isoformat()} {FANTASYCALC_CUT_HOUR_UTC:02d}:00:00+00"


def _ts(value: str) -> str:
    """Normalise '2026-10-06T14:20:24+00:00' / '2026-10-06 14:20:24+00' for
    string comparison (date, space, time)."""
    return str(value).replace("T", " ")[:19]


def prefer(cand: dict, have: dict) -> bool:
    """True when `cand` is the better week-N snapshot than `have` (the
    week-over-week rule, docs/v2-design-notes.md "Which snapshot is a
    source's week"):
      * FantasyCalc: the first pull at or after Tuesday 12:00 UTC of the
        week; with no pull after the cut, the week's latest pull;
      * articles and projections: the newest version (latest revision /
        newest snapshot dated in the week).
    """
    if cand["source"] == "fantasycalc" and cand.get("kind") == "published_chart":
        cut = _ts(fantasycalc_cut(cand["week"]))
        c, h = _ts(_pulled(cand)), _ts(_pulled(have))
        if (c >= cut) != (h >= cut):
            return c >= cut
        return c < h if c >= cut else c > h
    have_sort = have.get("_sort") or [have.get("pulled_at") or have.get("snapshot_date") or "", 0]
    # Timestamps arrive as '2026-10-07 00:00:00+00' (view, dumps) and
    # '2026-10-07T00:00:00+00:00' (PostgREST on the base tables): compare
    # them normalised, never as raw strings.
    return [_ts(cand["_sort"][0]), cand["_sort"][1]] >= [_ts(have_sort[0]), have_sort[1]]


def _supersede(superseded: dict, entry: dict, log) -> None:
    """Keep a version that is not (or no longer) the week's snapshot."""
    doc = superseded.setdefault(entry["week"], {"schema": SUPERSEDED_SCHEMA, "season": SEASON,
                                                "week": entry["week"], "versions": {}})
    versions = doc["versions"].setdefault(entry["source"], [])
    if any(v["fingerprint"] == entry["fingerprint"] for v in versions):
        return
    versions.append(entry)
    versions.sort(key=lambda v: (_pulled(v) or v.get("snapshot_date") or ""))
    if len(versions) > MAX_SUPERSEDED_PER_SOURCE:
        dropped = versions.pop(0)
        log(f"superseded cap: drop oldest {entry['source']} week {entry['week']} version {dropped['origin']}")
    log(f"keep superseded {entry['source']} week {entry['week']}: {entry['origin']}")


def merge(docs: dict[int, dict], candidates: list[dict], content_week: int, log=print,
          superseded: dict[int, dict] | None = None) -> dict[int, dict]:
    """Fold candidate entries into the week documents (append-only).

    Each (source, week) gets ONE snapshot by the week-over-week rule
    (prefer); every other distinct version goes to `superseded` (when given),
    so a version replaced mid-week is kept, not lost (HISTORY-WEEK-CAPTURE).
    A frozen week's snapshot never changes (late versions are superseded)."""
    superseded = {} if superseded is None else superseded
    for cand in candidates:
        week = cand["week"]
        sort_key = cand.pop("sort_key")
        cand["fingerprint"] = fingerprint(cand)
        if week > content_week:
            log(f"skip {cand['source']} week {week}: later than the content calendar ({content_week})")
            continue
        doc = docs.setdefault(week, {"schema": SCHEMA, "season": SEASON, "week": week,
                                     "frozen": False, "sources": {}})
        cand["_sort"] = sort_key
        if cand["source"] == "fantasycalc" and cand.get("kind") == "published_chart":
            cand["cut"] = "after" if _ts(_pulled(cand)) >= _ts(fantasycalc_cut(week)) else "missed"
        have = doc["sources"].get(cand["source"])
        if have is None:
            cand["captured_at"] = _stamp()
            doc["sources"][cand["source"]] = cand
            log(f"add {cand['source']} week {week}{' (late, frozen week)' if doc['frozen'] else ''}")
            continue
        if have["fingerprint"] == cand["fingerprint"]:
            continue
        if doc["frozen"] and same_content_finer(have, cand):
            cand["captured_at"] = _stamp()
            cand["rebased_from"] = have["fingerprint"]
            doc["sources"][cand["source"]] = cand
            log(f"rebase frozen {cand['source']} week {week}: same content, finer precision")
            continue
        cand["captured_at"] = _stamp()
        if doc["frozen"]:
            log(f"KEEP frozen {cand['source']} week {week}: a different candidate "
                f"({cand['origin']}) is kept as a superseded version (append-only)")
            _supersede(superseded, cand, log)
            continue
        if prefer(cand, have):
            doc["sources"][cand["source"]] = cand
            log(f"update open week {week} {cand['source']} -> {cand['origin']}")
            _supersede(superseded, have, log)
        else:
            _supersede(superseded, cand, log)
    for week, doc in docs.items():
        if week < content_week and not doc["frozen"]:
            doc["frozen"] = True
            log(f"freeze week {week}")
    for week, sdoc in superseded.items():
        selected = docs.get(week, {}).get("sources", {})
        for source in list(sdoc["versions"]):
            fp = (selected.get(source) or {}).get("fingerprint")
            sdoc["versions"][source] = [v for v in sdoc["versions"][source] if v["fingerprint"] != fp]
            if not sdoc["versions"][source]:
                del sdoc["versions"][source]
    return docs


def superseded_dir(directory: Path = HISTORY_DIR) -> Path:
    return directory / SUPERSEDED_DIR_NAME


def load_superseded(directory: Path = HISTORY_DIR) -> dict[int, dict]:
    out = {}
    for path in sorted(superseded_dir(directory).glob("week-*.json")):
        week = int(path.stem.split("-")[1])
        doc = json.loads(path.read_text())
        validate_superseded_doc(doc, week)
        out[week] = doc
    return out


def validate_superseded_doc(doc: dict, expected_week: int) -> None:
    """Same no-relabel guard as a week file, for every kept version."""
    if doc.get("schema") != SUPERSEDED_SCHEMA or doc.get("week") != expected_week:
        raise HistoryError(f"superseded week-{expected_week}: bad schema/week")
    for source, versions in (doc.get("versions") or {}).items():
        probe = {"schema": SCHEMA, "season": doc.get("season"), "week": expected_week, "frozen": True,
                 "sources": {}}
        for v in versions:
            probe["sources"] = {source: v}
            validate_week_doc(probe, expected_week)


def write_superseded(superseded: dict[int, dict], directory: Path = HISTORY_DIR) -> None:
    target = superseded_dir(directory)
    for week, doc in sorted(superseded.items()):
        if not doc["versions"]:
            continue
        validate_superseded_doc(doc, week)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"week-{week}.json").write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")


def write_weeks(docs: dict[int, dict], directory: Path = HISTORY_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for week, doc in sorted(docs.items()):
        validate_week_doc(doc, week)
        week_path(week, directory).write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------- index

def served_published_natives(fixture: dict) -> dict:
    """The as-published natives the page serves now, per source and scoring,
    keyed by player_key (the fixture's sections mapped through player_keys)."""
    out = {}
    keys = fixture.get("player_keys") or {}
    for source in PUBLISHED:
        combos = ((fixture.get("sources") or {}).get(source) or {}).get("combos") or {}
        natives = {}
        for scoring, combo in FIXTURE_COMBO.items():
            cell = combos.get(combo) or combos.get(combo + "_qb1") or {}
            native = cell.get("native") or {}
            mapped = {}
            for slug, value in native.items():
                key = keys.get(slug)
                if key is not None and isinstance(value, (int, float)):
                    mapped[str(int(key))] = float(value)
            if mapped:
                natives[scoring] = mapped
        if natives:
            out[source] = natives
    return out


def served_fingerprints(fixture: dict, players: dict) -> dict:
    """Fingerprint of the inputs the page serves now, per source."""
    out = {source: fingerprint({"kind": "published_chart", "natives": natives})
           for source, natives in served_published_natives(fixture).items()}
    for entry in projection_entries_from_players(players, "players.json"):
        out[entry["source"]] = fingerprint(entry)
    return out


def label_week(fixture: dict, source: str) -> int | None:
    section = (fixture.get("sources") or {}).get(source) or {}
    for field in ("week_designated", "content_vintage", "vintage"):
        value = str(section.get(field) or "")
        if value.lower().startswith("week "):
            try:
                return int(value.split()[1])
            except (IndexError, ValueError):
                continue
        week = week_of_day(value) if len(value) >= 10 else None
        if week:
            return week
    return None


def without_players(entry: dict, dropped) -> dict:
    """A saved published-chart entry without the given players (every
    scoring), re-fingerprinted: the version of that week a kept section
    serves (build_index, kept-section match)."""
    dropped = {str(k) for k in dropped}
    out = copy.deepcopy(entry)
    out["natives"] = {sc: {k: v for k, v in cells.items() if k not in dropped}
                      for sc, cells in (entry.get("natives") or {}).items()}
    out["origin"] = (f"{entry['origin']} as served: without player(s) {', '.join(sorted(dropped, key=int))}, "
                     f"whom the served section does not carry")
    out["fingerprint"] = fingerprint(out)
    return out


def kept_section_drops(entry: dict | None, served_natives: dict, universe: set[str]) -> list[str] | None:
    """When the page serves an older build of a section (a held source keeps
    its last promoted section, JEG-479), that section can lack a player the
    saved week prices who has since joined the universe (player_keys): run
    37877126939 kept CBS Week 5, built before Tyreek Hill was keyed, in the
    same run that keyed him. Returns the universe players the saved entry
    prices and the served section lacks when the served natives are exactly
    the saved entry without them (same scorings, every served value equal);
    None otherwise (including an exact match, which needs no drop)."""
    saved = (entry or {}).get("natives") or {}
    if not saved or not served_natives or set(saved) != set(served_natives):
        return None
    dropped = set()
    for sc, cells in served_natives.items():
        have = saved[sc]
        if any(k not in have or _num(have[k]) != _num(v) for k, v in cells.items()):
            return None
        dropped |= {k for k in have if k in universe and k not in cells}
    if not dropped:
        return None
    # Every scoring must lose the same players (one served version per week).
    if any(k in cells for cells in served_natives.values() for k in dropped):
        return None
    return sorted(dropped, key=int)


def build_index(docs: dict[int, dict], fixture: dict, players: dict, content_week: int,
                superseded: dict[int, dict] | None = None) -> dict:
    served = {}
    fps = served_fingerprints(fixture, players)
    served_natives = served_published_natives(fixture)
    superseded = superseded or {}
    # A saved chart can price a player the page's universe does not have (CBS
    # Week 5 lists Tyreek Hill, who is not in players.json / player_keys, so
    # the section drops him). Match the served inputs against each saved
    # version restricted to the players the page can show, as the engine
    # does when it reads a saved week (curve-widget historyNatives).
    universe = {str(int(k)) for k in (fixture.get("player_keys") or {}).values()}

    def entry_fp(entry, source):
        if not entry:
            return None
        if source in PUBLISHED and universe:
            natives = {sc: {k: v for k, v in cells.items() if k in universe}
                       for sc, cells in (entry.get("natives") or {}).items()}
            return fingerprint({"kind": "published_chart", "natives": {sc: c for sc, c in natives.items() if c}})
        return entry.get("fingerprint")

    for source in (*PUBLISHED, *PROJECTION_FIELDS):
        fp = fps.get(source)
        matches = [w for w, d in sorted(docs.items())
                   if entry_fp(d["sources"].get(source), source) == fp]
        # The page may serve a version that is not its week's snapshot (an
        # older revision still in the fixture, or a FantasyCalc pull other
        # than the cut): it is still that week's content, so Δ pairs it with
        # the week before (version: "superseded").
        other = [w for w, d in sorted(superseded.items())
                 if any(entry_fp(v, source) == fp for v in (d.get("versions") or {}).get(source, []))]
        label = label_week(fixture, source)
        rec = {"label_week": label, "fingerprint": fp}
        kept = None
        if fp and not matches and not other and source in served_natives:
            # A kept (e.g. held) section built on a smaller universe: the
            # saved week less the players it does not carry. Newest week
            # first; the snapshot before the other kept versions.
            for week in sorted(set(docs) | set(superseded), reverse=True):
                candidates = [("snapshot", (docs.get(week) or {}).get("sources", {}).get(source))]
                candidates += [("superseded", v) for v in
                               ((superseded.get(week) or {}).get("versions") or {}).get(source, [])]
                for of, entry in candidates:
                    dropped = kept_section_drops(entry, served_natives[source], universe)
                    if dropped:
                        kept = (week, of, entry, dropped)
                        break
                if kept:
                    break
        if not fp:
            rec.update(week=None, reason="the page serves no inputs for this source")
        elif kept:
            week, of, entry, dropped = kept
            # Served as another version of that week (served.json, derived
            # at `make sync`), so "this week" is exactly what the chart shows.
            rec.update(week=week, version="superseded",
                       entry_fingerprint=without_players(entry, dropped)["fingerprint"],
                       served_from={"version": of, "fingerprint": entry["fingerprint"],
                                    "dropped_players": dropped},
                       note=(f"the page serves a kept section (e.g. a held source): the saved Week {week} "
                             f"content without {len(dropped)} player(s) the section does not carry "
                             f"({', '.join(dropped)})"))
            if label is not None and label != week:
                rec["label_mismatch"] = (f"section label says Week {label}; the served inputs are "
                                         f"the saved Week {week} content")
        elif not matches and not other:
            rec.update(week=None, reason="the served inputs match no saved week")
        else:
            rec["week"] = matches[-1] if matches else other[-1]
            rec["version"] = "snapshot" if matches else "superseded"
            if not matches:
                # The page serves another kept version of that week (e.g. a
                # FantasyCalc pull newer than the week's Tuesday cut). Name it
                # so `make sync` can serve it (assets/history/served.json) and
                # "this week" is exactly what the chart shows.
                rec["entry_fingerprint"] = next(
                    v["fingerprint"] for v in superseded[rec["week"]]["versions"][source]
                    if entry_fp(v, source) == fp)
            if label is not None and label != rec["week"]:
                rec["label_mismatch"] = (f"section label says Week {label}; the served inputs are "
                                         f"the saved Week {rec['week']} content")
        served[source] = rec
    weeks = {}
    for week, doc in sorted(docs.items()):
        weeks[str(week)] = {
            "file": f"assets/history/week-{week}.json", "frozen": doc["frozen"],
            "sources": {s: {"origin": e["origin"], "complete": e["complete"], "fingerprint": e["fingerprint"],
                            **({"content_date": e["week_evidence"].get("content_date")}
                               if e["week_evidence"].get("content_date") else {}),
                            **({"pulled_at": e.get("pulled_at")} if e.get("pulled_at") else {})}
                        for s, e in sorted(doc["sources"].items())}}
    return {"schema": INDEX_SCHEMA, "season": SEASON, "content_week": content_week,
            "fixture_built_at": fixture.get("built_at"), "weeks": weeks, "served": served}


SERVED_SCHEMA = "week-history-served/1"


def write_served_versions(index: dict, superseded: dict[int, dict], target: Path,
                          docs: dict[int, dict] | None = None) -> dict:
    """assets/history/served.json: {source: entry} for every source whose
    served inputs are a superseded version of their week (index
    served.version == "superseded"), including a kept section's version
    (served_from: a saved version without the players that section does not
    carry). Derived at `make sync`, not stored."""
    out = {}
    for source, rec in (index.get("served") or {}).items():
        if rec.get("version") != "superseded":
            continue
        versions = ((superseded.get(rec["week"]) or {}).get("versions") or {}).get(source, [])
        origin = rec.get("served_from")
        if origin:
            base = ((docs or {}).get(rec["week"]) or {}).get("sources", {}).get(source) \
                if origin.get("version") == "snapshot" else \
                next((v for v in versions if v.get("fingerprint") == origin.get("fingerprint")), None)
            versions = [without_players(base, origin.get("dropped_players") or [])] \
                if base and base.get("fingerprint") == origin.get("fingerprint") else []
        entry = next((v for v in versions if v.get("fingerprint") == rec.get("entry_fingerprint")), None)
        if entry is not None:
            out[source] = entry
    doc = {"schema": SERVED_SCHEMA, "season": SEASON, "sources": out}
    target.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")
    return doc


def write_index(index: dict, directory: Path = HISTORY_DIR) -> None:
    (directory / "index.json").write_text(json.dumps(index, sort_keys=True, indent=1) + "\n")


# ------------------------------------------------------- prior ESPN legs

ESPN_LEGS_SCHEMA = "week-history-espn-legs/1"


def espn_legs_for_week(entry: dict, players: dict) -> dict:
    """The ESPN two-tier leg of a saved week, per scoring, built by the
    pipeline's own leg code (build_ddf_two_tier_leg: tier pool at 12 teams,
    calibrate_tiers at the 0.15 reference share with the feasible-share
    fallback, one 70/max scale) from that week's saved espn_ppg, rounded to
    1 dp as build_espn_section_from_ddf_leg writes the fixture's ESPN combos
    (HISTORY-ESPN-PRIOR). Positions are today's canonical ones; a player no
    longer in players.json is left out. Returns {"legs": {scoring: {key:
    value}}} or {"reason": ...}."""
    import build_ddf_two_tier_leg as L

    pos_of = {str(p["player_key"]): p.get("pos") for p in players.get("players") or []
              if p.get("player_key") is not None}
    legs = {}
    for idx, scoring in enumerate(SCORINGS):
        lists = {pos: [] for pos in L.POSITIONS}
        for key, triple in (entry.get("ppg") or {}).items():
            pos = pos_of.get(str(key))
            if pos in lists and isinstance(triple, list) and len(triple) == 3:
                lists[pos].append({"id": int(key), "x": float(triple[idx])})
        try:
            pool = L.build_position_tiers(lists, 12, dict(L.REF_SLOTS), L.REF_FLEX_COUNT,
                                          list(L.REF_FLEX_ELIGIBLE), L.bench_mix_for_teams(12))
            calibration, _notes = L.calibrate_tiers(pool, L.DEFAULT_BENCH_SHARE)
        except (ValueError, KeyError, TypeError) as exc:
            return {"reason": f"the Week {entry.get('week')} ESPN leg cannot be calibrated: {exc}"}
        raw = {d["id"]: L.price_for_projection(d["x"], calibration[pos])
               for pos in L.POSITIONS for d in lists[pos]}
        mx = max(raw.values(), default=0.0)
        if not mx > 0:
            return {"reason": f"the Week {entry.get('week')} ESPN leg has no positive value"}
        legs[scoring] = {str(k): round(v * 70.0 / mx, 1) for k, v in sorted(raw.items())}
    return {"legs": legs}


def write_espn_legs(docs: dict[int, dict], players: dict, target: Path) -> dict:
    """assets/history/espn-legs.json for every saved ESPN week (derived at
    `make sync` with the current pipeline; not part of the committed store)."""
    weeks = {}
    for week, doc in sorted(docs.items()):
        entry = doc["sources"].get("espn")
        if entry:
            weeks[str(week)] = {"fingerprint": entry["fingerprint"], **espn_legs_for_week(entry, players)}
    out = {"schema": ESPN_LEGS_SCHEMA, "season": SEASON,
           "built_by": "pipelines/build_week_history.espn_legs_for_week (build_ddf_two_tier_leg, 12 teams, "
                       "bench share 0.15, 1 dp as build_espn_section_from_ddf_leg)",
           "weeks": weeks}
    target.write_text(json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n")
    return out


# ---------------------------------------------------------------------- main

def git_json(rev: str, path: str) -> dict:
    return json.loads(subprocess.check_output(["git", "show", f"{rev}:{path}"], cwd=ROOT))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--supabase", action="store_true", help="fetch saved inputs from Supabase (CI)")
    ap.add_argument("--supabase-dump", type=Path, help="read a saved Supabase dump instead")
    ap.add_argument("--players-from-git", action="append", default=[], metavar="REV",
                    help="capture projection inputs from players.json at a git revision (backfill)")
    ap.add_argument("--players-file", action="append", default=[], type=Path,
                    help="capture projection inputs from a players.json-shaped file (backfill)")
    ap.add_argument("--only", action="append", default=[],
                    help="with --players-*, keep only these sources")
    ap.add_argument("--index-only", action="store_true",
                    help="only rebuild index.json from the saved weeks")
    ap.add_argument("--served-only", action="store_true",
                    help="capture only the served players.json projections, then rebuild the "
                         "index (make sync: no Supabase; keeps the served week saved)")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    ap.add_argument("--dir", type=Path, default=HISTORY_DIR)
    args = ap.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else date.today()
    content_week = current_nfl_week(today)
    docs = load_weeks(args.dir)
    superseded = load_superseded(args.dir)
    players = json.loads(PLAYERS.read_text())
    if args.index_only:
        write_index(build_index(docs, json.loads(FIXTURE.read_text()), players, content_week, superseded),
                    args.dir)
        return 0
    candidates: list[dict] = []
    if args.served_only:
        pass
    elif args.supabase or args.supabase_dump:
        published, snaps = fetch_supabase() if args.supabase else rows_from_dump(args.supabase_dump)
        candidates += published_entries_from_rows(published)
        candidates += projection_entries_from_tables(snaps)
    backfill = [(rev, git_json(rev, "data/fixtures/current/players.json"), f"git {rev}") for rev in args.players_from_git]
    backfill += [(str(p), json.loads(p.read_text()), str(p.relative_to(ROOT) if p.is_absolute() and ROOT in p.parents else p))
                 for p in args.players_file]
    for _, players_doc, where in backfill:
        for entry in projection_entries_from_players(players_doc, f"players.json ({where})"):
            if not args.only or entry["source"] in args.only:
                candidates.append(entry)
    # Always: the projection inputs the page serves right now.
    candidates += projection_entries_from_players(players, "players.json (served)")
    docs = merge(docs, candidates, content_week, superseded=superseded)
    write_weeks(docs, args.dir)
    write_superseded(superseded, args.dir)
    index = build_index(docs, json.loads(FIXTURE.read_text()), players, content_week, superseded)
    write_index(index, args.dir)
    for source, rec in index["served"].items():
        note = rec.get("label_mismatch") or rec.get("note") or rec.get("reason") or ""
        print(f"served {source}: week {rec['week']} {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
