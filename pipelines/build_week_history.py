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
    (ValueModel.derivePublishedSetup). Origin: Supabase api.source_inputs_weekly
    (the latest pull of that week, one per source/week/scoring).
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
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from nfl_week import current_nfl_week  # noqa: E402

sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from games_remaining import PPG_DECIMALS  # noqa: E402  (bake_players' per-game precision)

HISTORY_DIR = ROOT / "data" / "history"
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"

SCHEMA = "week-history/1"
INDEX_SCHEMA = "week-history-index/1"
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

def published_entries_from_rows(rows: list[dict]) -> list[dict]:
    """api.source_inputs_weekly rows -> one entry per (source, week)."""
    groups: dict = {}
    for row in rows:
        source = row["source"]
        if source not in PUBLISHED or int(row.get("season") or SEASON) != SEASON:
            continue
        scoring = SB_SCORING.get(row["scoring"])
        if scoring is None or row.get("player_key") is None or row.get("native_value") is None:
            continue
        g = groups.setdefault((source, int(row["week"])), {"natives": {}, "pulls": set(),
                                                            "content": set(), "bakes": set()})
        g["natives"].setdefault(scoring, {})[str(int(row["player_key"]))] = float(row["native_value"])
        g["pulls"].add(str(row["pulled_at"]))
        if row.get("source_content_date"):
            g["content"].add(str(row["source_content_date"])[:10])
        if row.get("bake_id"):
            g["bakes"].add(row["bake_id"])
    out = []
    for (source, week_col), g in sorted(groups.items()):
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
                 "origin": "supabase:api.source_inputs_weekly (12 teams, 1 QB, as published; latest pull of the week)",
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

    published = paged("source_inputs_weekly",
                      "source,season,week,scoring,player_key,native_value,source_content_date,pulled_at,bake_id",
                      "source,week,scoring,player_key", schema="api")
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


def merge(docs: dict[int, dict], candidates: list[dict], content_week: int, log=print) -> dict[int, dict]:
    """Fold candidate entries into the week documents (append-only)."""
    for cand in candidates:
        week = cand["week"]
        sort_key = cand.pop("sort_key")
        cand["fingerprint"] = fingerprint(cand)
        if week > content_week:
            log(f"skip {cand['source']} week {week}: later than the content calendar ({content_week})")
            continue
        doc = docs.setdefault(week, {"schema": SCHEMA, "season": SEASON, "week": week,
                                     "frozen": False, "sources": {}})
        have = doc["sources"].get(cand["source"])
        if have is None:
            cand["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            cand["_sort"] = sort_key
            doc["sources"][cand["source"]] = cand
            log(f"add {cand['source']} week {week}{' (late, frozen week)' if doc['frozen'] else ''}")
            continue
        if have["fingerprint"] == cand["fingerprint"]:
            continue
        if doc["frozen"] and same_content_finer(have, cand):
            cand["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            cand["_sort"] = sort_key
            cand["rebased_from"] = have["fingerprint"]
            doc["sources"][cand["source"]] = cand
            log(f"rebase frozen {cand['source']} week {week}: same content, finer precision")
            continue
        if doc["frozen"]:
            log(f"KEEP frozen {cand['source']} week {week}: a different candidate "
                f"({cand['origin']}) was not applied (append-only)")
            continue
        if sort_key >= (have.get("_sort") or [have.get("pulled_at") or have.get("snapshot_date") or "", 0]):
            cand["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            cand["_sort"] = sort_key
            doc["sources"][cand["source"]] = cand
            log(f"update open week {week} {cand['source']} -> {cand['origin']}")
    for week, doc in docs.items():
        if week < content_week and not doc["frozen"]:
            doc["frozen"] = True
            log(f"freeze week {week}")
    return docs


def write_weeks(docs: dict[int, dict], directory: Path = HISTORY_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for week, doc in sorted(docs.items()):
        validate_week_doc(doc, week)
        week_path(week, directory).write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------- index

def served_fingerprints(fixture: dict, players: dict) -> dict:
    """Fingerprint of the inputs the page serves now, per source."""
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
            out[source] = fingerprint({"kind": "published_chart", "natives": natives})
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


def build_index(docs: dict[int, dict], fixture: dict, players: dict, content_week: int) -> dict:
    served = {}
    fps = served_fingerprints(fixture, players)
    for source in (*PUBLISHED, *PROJECTION_FIELDS):
        fp = fps.get(source)
        matches = [w for w, d in sorted(docs.items())
                   if (d["sources"].get(source) or {}).get("fingerprint") == fp]
        label = label_week(fixture, source)
        rec = {"label_week": label, "fingerprint": fp}
        if not fp:
            rec.update(week=None, reason="the page serves no inputs for this source")
        elif not matches:
            rec.update(week=None, reason="the served inputs match no saved week")
        else:
            rec["week"] = matches[-1]
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


def write_index(index: dict, directory: Path = HISTORY_DIR) -> None:
    (directory / "index.json").write_text(json.dumps(index, sort_keys=True, indent=1) + "\n")


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
    players = json.loads(PLAYERS.read_text())
    if args.index_only:
        write_index(build_index(docs, json.loads(FIXTURE.read_text()), players, content_week), args.dir)
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
    docs = merge(docs, candidates, content_week)
    write_weeks(docs, args.dir)
    index = build_index(docs, json.loads(FIXTURE.read_text()), players, content_week)
    write_index(index, args.dir)
    for source, rec in index["served"].items():
        note = rec.get("label_mismatch") or rec.get("reason") or ""
        print(f"served {source}: week {rec['week']} {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
