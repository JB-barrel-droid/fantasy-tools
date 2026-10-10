#!/usr/bin/env python3
"""Refresh the repo copies of the weekly store from Supabase (JEG-521 G4).

  data/inputs/weekly_actuals_2024_2026.csv
      season, week, player_key, pos, team, std, half_ppr, ppr: one row per
      QB/RB/WR/TE player-game in public.player_game_stats, scored exactly as
      public.v_player_game_actuals (decimal arithmetic, rounded half away from
      zero to 2 places, like Postgres round(numeric, 2)). Same columns, order
      and rounding as the 2026-10-09 export in docs/methodology.md ES-A, so a
      refresh only adds weeks (tests/test_espn_weekly_store.py pins the format).

  data/inputs/espn_weekly_projections_2026.csv
      season, week, player_key, pos, team, std, half_ppr, ppr, snapshot_at,
      pre_kickoff, basis: ESPN's weekly projection for each player-week as it
      stood before his team's kickoff (the latest public.projection_snapshots
      row with snapshot_at < games.starts_at). When no snapshot predates
      kickoff (the 2026-10 backfill of played weeks), the earliest snapshot is
      used and pre_kickoff is false, so a reader can drop those rows.
      basis = team_week (MR-20): per scheduled team week, 0 when ESPN
      projected him out.

Run weekly by espn-weekly-store.yml (pg_cron), after save_espn_weekly.py.
"""
from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTUALS = ROOT / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
PROJECTIONS = ROOT / "data" / "inputs" / "espn_weekly_projections_2026.csv"
POSITIONS = ("QB", "RB", "WR", "TE")
ACTUAL_COLS = ["season", "week", "player_key", "pos", "team", "std", "half_ppr", "ppr"]
PROJ_COLS = ACTUAL_COLS + ["snapshot_at", "pre_kickoff", "basis"]
D = Decimal


def _d(stats, k):
    v = (stats or {}).get(k)
    return D(str(v)) if v not in (None, "") else D(0)


def view_points(stats: dict) -> tuple[Decimal, Decimal, Decimal]:
    """(std, half, ppr), the public.v_player_game_actuals formula, exact."""
    base = (_d(stats, "passing_yards") / 25 + _d(stats, "passing_tds") * 4
            - _d(stats, "interceptions") * 2
            + _d(stats, "rushing_yards") / 10 + _d(stats, "rushing_tds") * 6
            + _d(stats, "receiving_yards") / 10 + _d(stats, "receiving_tds") * 6)
    rec = _d(stats, "receptions")
    return base, base + rec * D("0.5"), base + rec


def fmt(x: Decimal) -> str:
    """round(numeric, 2) then the float text the ES-A export carries (4.0, 8.58)."""
    return str(float(x.quantize(D("0.01"), rounding=ROUND_HALF_UP)))


def actual_rows(pgs: list[dict]) -> list[list]:
    out = []
    for r in pgs:
        g, p, t = r.get("game") or {}, r.get("player") or {}, r.get("team") or {}
        if p.get("position") not in POSITIONS or g.get("season") is None:
            continue
        std, half, ppr = view_points(r.get("stats") or {})
        out.append([int(g["season"]), int(g["week"]), int(p["player_key"]),
                    p["position"], t.get("abbreviation") or "", fmt(std), fmt(half), fmt(ppr)])
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    return out


def projection_rows(snaps: list[dict], kickoff: dict, meta: dict) -> list[list]:
    """snaps: projection_snapshots rows (player_key, week, scoring_format,
    projected_points, snapshot_at, game_id); kickoff: {game_id: starts_at};
    meta: {player_key: (pos, team)}."""
    by = {}
    for s in snaps:
        by.setdefault((s["player_key"], s["week"]), []).append(s)
    out = []
    for (pk, wk), rows in by.items():
        ko = kickoff.get(rows[0].get("game_id"))
        pre = [r for r in rows if ko and _ts(r["snapshot_at"]) < _ts(ko)]
        if pre:
            at = max((r["snapshot_at"] for r in pre), key=_ts)
            pool, is_pre = pre, True
        else:
            at = min((r["snapshot_at"] for r in rows), key=_ts)
            pool, is_pre = rows, False
        val = {}
        for fmt_ in ("standard", "half_ppr", "full_ppr"):
            cands = [r for r in pool if r["scoring_format"] == fmt_ and
                     (_ts(r["snapshot_at"]) <= _ts(at) if is_pre else True)]
            if not cands:
                continue
            pick = (max if is_pre else min)(cands, key=lambda r: _ts(r["snapshot_at"]))
            val[fmt_] = pick["projected_points"]
        if len(val) < 3:
            continue
        pos, team = meta.get(pk, ("", ""))
        out.append([2026, int(wk), int(pk), pos, team,
                    _num(val["standard"]), _num(val["half_ppr"]), _num(val["full_ppr"]),
                    at, "true" if is_pre else "false", "team_week"])
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    return out


def _ts(s):
    from datetime import datetime  # noqa: PLC0415
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def _num(v):
    return str(float(v))


def write_csv(path: Path, cols, rows) -> bool:
    """Write atomically; True when the content changed."""
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    w.writerows(rows)
    new = buf.getvalue()
    if path.exists() and path.read_text() == new:
        return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new)
    tmp.replace(path)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--season-from", type=int, default=2024)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "pipelines"))
    try:
        import sbclient as sb  # noqa: PLC0415
    except ImportError:
        import gh_sbclient as sb  # noqa: PLC0415

    pgs = sb.get_all(
        "player_game_stats",
        "?select=id,stats,game:games!inner(season,week),"
        "player:players!inner(player_key,position),team:teams(abbreviation)"
        f"&game.season=gte.{a.season_from}&player.position=in.(QB,RB,WR,TE)")
    rows = actual_rows(pgs)
    if len(rows) < 13000:
        print(f"FAILED: only {len(rows)} actual rows (the 2026-10-09 export had 13,531)",
              file=sys.stderr)
        return 1
    changed = write_csv(ACTUALS, ACTUAL_COLS, rows)
    print(f"{ACTUALS.name}: {len(rows)} rows ({'changed' if changed else 'unchanged'})")

    snaps = sb.get_all(
        "projection_snapshots",
        "?select=id,player_key,week,scoring_format,projected_points,snapshot_at,game_id"
        "&source=eq.espn&season=eq.2026&vintage_note=like.*basis=team_week*")
    games = sb.get_all("games", "?select=id,starts_at&season=eq.2026")
    kickoff = {g["id"]: g["starts_at"] for g in games}
    keys = sorted({s["player_key"] for s in snaps if s.get("player_key") is not None})
    meta = {}
    for i in range(0, len(keys), 150):
        for p in sb.get_all("players", "?select=id,player_key,position,metadata&player_key=in.("
                            + ",".join(map(str, keys[i:i + 150])) + ")"):
            meta[p["player_key"]] = (p.get("position") or "",
                                     (p.get("metadata") or {}).get("team") or "")
    prow = projection_rows([s for s in snaps if s.get("player_key") is not None], kickoff, meta)
    changed = write_csv(PROJECTIONS, PROJ_COLS, prow)
    print(f"{PROJECTIONS.name}: {len(prow)} rows ({'changed' if changed else 'unchanged'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
