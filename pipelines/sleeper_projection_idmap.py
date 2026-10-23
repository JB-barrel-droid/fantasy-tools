#!/usr/bin/env python3
"""Map Sleeper weekly-projection players (RotoWire) to our player_key (JEG-949).

Read-only measurement plumbing. Changes no shown value and writes nothing to
Supabase. Join chain, exact ids only, never fuzzy:

    sleeper_id -> gsis_id -> public.players.metadata->>'gsis_id' -> player_key

gsis_id is not carried by Sleeper for most current players (3,893 of 12,229 on
2026-10-23; Justin Herbert, Jalen Hurts, Jahmyr Gibbs have none), so the gsis
is taken, in this order, from:
  1. the pulled projection row (Sleeper's own gsis_id)
  2. the DynastyProcess id table, by sleeper_id (public CSV)
  3. the DynastyProcess table, by Sleeper's sportradar_id
  4. the DynastyProcess table, by Sleeper's espn_id
Every layer that answers must agree; a disagreement is status `conflict` and
the player is left unmapped. A mapped player whose last name differs from the
players-table name is status `name_review` and also left unmapped. Nothing is
chosen by name similarity; an unmatched player with an exact name+position
candidate is listed as a suggestion only (`suggested_player_key`), never used.

Inputs (all local files; fetch with --fetch, which writes under data/raw/):
    data/inputs/weekly_projections_sleeper.csv.gz   projections (pull_sleeper_projections.py)
    data/raw/sleeper_players_nfl.json               https://api.sleeper.app/v1/players/nfl
    data/raw/dynastyprocess_db_playerids.csv        github.com/dynastyprocess/data db_playerids.csv
    data/inputs/players_identity_snapshot.json      SELECT of public.players (player_key, name, position, gsis_id)

Outputs:
    data/inputs/sleeper_projection_idmap.csv        one row per sleeper_id with status
    data/inputs/sleeper_projection_idmap_report.json  match rates and the unmatched list summary
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJ = ROOT / "data/inputs/weekly_projections_sleeper.csv.gz"
SLEEPER_PLAYERS = ROOT / "data/raw/sleeper_players_nfl.json"
DP_IDS = ROOT / "data/raw/dynastyprocess_db_playerids.csv"
SNAPSHOT = ROOT / "data/inputs/players_identity_snapshot.json"
OUT_MAP = ROOT / "data/inputs/sleeper_projection_idmap.csv"
OUT_REPORT = ROOT / "data/inputs/sleeper_projection_idmap_report.json"
URLS = {
    SLEEPER_PLAYERS: "https://api.sleeper.app/v1/players/nfl",
    DP_IDS: "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv",
}
FIELDS = ("sleeper_id", "name", "pos", "gsis_id", "gsis_source", "player_key", "status",
          "suggested_player_key", "rows", "seasons", "ppr_points")
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def last_name_key(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    parts = [p for p in re.sub(r"[^a-z ]", " ", text).split() if p not in SUFFIXES]
    return parts[-1] if parts else ""


def full_name_key(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return " ".join(p for p in re.sub(r"[^a-z ]", " ", text).split() if p not in SUFFIXES)


def load_projection_players(path: Path) -> dict:
    """sleeper_id -> {name, pos, gsis (from the row), rows, seasons, ppr_points}."""
    out: dict = {}
    with gzip.open(path, "rt", newline="") as fh:
        for r in csv.DictReader(fh):
            p = out.setdefault(r["sleeper_id"], {"name": r["name"], "pos": r["pos"], "gsis": set(),
                                                 "rows": 0, "seasons": set(), "ppr": 0.0})
            if r["gsis_id"]:
                p["gsis"].add(r["gsis_id"])
            p["rows"] += 1
            p["seasons"].add(r["season"])
            p["ppr"] += float(r["pts_ppr"] or 0)
    return out


def load_dp_indexes(path: Path) -> dict:
    """DynastyProcess id table -> {sleeper_id|sportradar_id|espn_id: gsis_id}, ambiguous keys dropped."""
    idx: dict = {"sleeper": defaultdict(set), "sportradar": defaultdict(set), "espn": defaultdict(set)}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            gsis = (r.get("gsis_id") or "").strip()
            if not gsis or gsis == "NA":
                continue
            for key, col in (("sleeper", "sleeper_id"), ("sportradar", "sportradar_id"), ("espn", "espn_id")):
                v = (r.get(col) or "").strip()
                if v and v != "NA":
                    idx[key][v].add(gsis)
    return idx


def resolve_gsis(sleeper_id: str, proj_gsis: set, sleeper_rec: dict, dp: dict):
    """Return (gsis, source, status). Every answering layer must agree."""
    answers: list = []
    for g in sorted(proj_gsis):
        answers.append(("sleeper", g))
    for src, key in (("dp_sleeper", sleeper_id),
                     ("dp_sportradar", str(sleeper_rec.get("sportradar_id") or "")),
                     ("dp_espn", str(sleeper_rec.get("espn_id") or ""))):
        if not key:
            continue
        table = dp[src.split("_", 1)[1]]
        got = table.get(key, set())
        if len(got) > 1:
            return "", src, "conflict"
        if got:
            answers.append((src, next(iter(got))))
    values = {g for _, g in answers}
    if not values:
        return "", "", "unmapped"
    if len(values) > 1:
        return "", "+".join(s for s, _ in answers), "conflict"
    return values.pop(), "+".join(dict.fromkeys(s for s, _ in answers)), "gsis"


def build_idmap(proj_players: dict, sleeper_players: dict, dp: dict, snapshot: list) -> list:
    by_gsis = {r["gsis_id"]: r for r in snapshot if r.get("gsis_id")}
    by_name_pos: dict = defaultdict(list)
    for r in snapshot:
        by_name_pos[(full_name_key(r["full_name"]), r["position"])].append(r["player_key"])
    rows = []
    for sid, p in sorted(proj_players.items(), key=lambda kv: -kv[1]["ppr"]):
        gsis, source, status = resolve_gsis(sid, p["gsis"], sleeper_players.get(sid, {}), dp)
        key = ""
        if status == "gsis":
            rec = by_gsis.get(gsis)
            if rec is None:
                status = "gsis_not_in_players"
            elif last_name_key(rec["full_name"]) != last_name_key(p["name"]):
                status = "name_review"
            else:
                status, key = "matched", rec["player_key"]
        suggestion = ""
        if status != "matched":
            cands = by_name_pos.get((full_name_key(p["name"]), p["pos"]), [])
            if len(cands) == 1:
                suggestion = cands[0]
        rows.append({"sleeper_id": sid, "name": p["name"], "pos": p["pos"], "gsis_id": gsis,
                     "gsis_source": source, "player_key": key, "status": status,
                     "suggested_player_key": suggestion, "rows": p["rows"],
                     "seasons": f"{min(p['seasons'])}-{max(p['seasons'])}", "ppr_points": round(p["ppr"], 1)})
    return rows


def match_report(rows: list) -> dict:
    """Match rates by player and by player-week rows, for all and for fantasy-relevant players."""
    def rate(sel):
        tot = sum(r["rows"] for r in sel)
        ok = sum(r["rows"] for r in sel if r["status"] == "matched")
        return {"players": len(sel), "players_matched": sum(r["status"] == "matched" for r in sel),
                "rows": tot, "rows_matched": ok, "row_rate": round(ok / tot, 4) if tot else None}
    skill = [r for r in rows if r["pos"] in ("QB", "RB", "WR", "TE")]
    # relevant = averaged at least 4 projected PPR points over the weeks they were projected
    relevant = [r for r in skill if r["rows"] and r["ppr_points"] / r["rows"] >= 4.0]
    def gsis_rate(sel):
        tot = sum(r["rows"] for r in sel)
        ok = sum(r["rows"] for r in sel if r["gsis_id"] and r["status"] in ("matched", "gsis_not_in_players"))
        return round(ok / tot, 4) if tot else None
    recent_missing = [r for r in rows if r["status"] == "gsis_not_in_players"
                      and r["pos"] in ("QB", "RB", "WR", "TE") and r["seasons"].endswith(("2025", "2026"))]
    return {"status_counts": dict(Counter(r["status"] for r in rows)),
            "gsis_resolved_row_rate": {"all": gsis_rate(rows), "qb_rb_wr_te": gsis_rate(skill),
                                       "qb_rb_wr_te_avg_ppr_ge_4": gsis_rate(relevant)},
            "gsis_known_but_not_in_players_projected_2025_or_2026": len(recent_missing),
            "all": rate(rows), "qb_rb_wr_te": rate(skill), "qb_rb_wr_te_avg_ppr_ge_4": rate(relevant),
            "suggestions_unused": sum(1 for r in rows if r["suggested_player_key"] and r["status"] != "matched")}


def fetch_raw() -> None:
    for dest, url in URLS.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "data-driven-football-measurement/1.0"})
        dest.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        print(f"fetched {dest.name}: {dest.stat().st_size} bytes")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="download the two public raw inputs first")
    args = ap.parse_args(argv)
    if args.fetch:
        fetch_raw()
    for need in (PROJ, SLEEPER_PLAYERS, DP_IDS, SNAPSHOT):
        if not need.exists():
            print(f"missing input {need} (run with --fetch; snapshot is a SELECT of public.players)", file=sys.stderr)
            return 2
    rows = build_idmap(load_projection_players(PROJ), json.loads(SLEEPER_PLAYERS.read_text()),
                       load_dp_indexes(DP_IDS), json.loads(SNAPSHOT.read_text()))
    with open(OUT_MAP, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    report = match_report(rows)
    report["top_unmatched_by_ppr_points"] = [
        {k: r[k] for k in ("sleeper_id", "name", "pos", "status", "rows", "seasons", "ppr_points")}
        for r in rows if r["status"] != "matched" and r["pos"] in ("QB", "RB", "WR", "TE")][:25]
    OUT_REPORT.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("status_counts", "all", "qb_rb_wr_te", "qb_rb_wr_te_avg_ppr_ge_4")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
