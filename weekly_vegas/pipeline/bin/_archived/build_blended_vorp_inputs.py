"""Build chart input tables from the canonical FP season snapshot (idempotent).

1. blended_player_map: every skill-position player in v_fp_season_latest,
   keyed by canonical player_key (numeric). player_norm is a transitional
   label only; has_vegas is always false (the season Vegas blend was retired
   2026-09-16).
2. fp_season_latest_norm: latest FP snapshot per player_key, 7 granular stats.

Identity: player_key comes from fp_season_projections (written at ingest by
bin/load_fp_season.py via engine/canonical_players). No name matching here.

Retired 2026-09-18: the Vegas-blend machinery (blended_source_confidence,
blended_calibration, v_blended_season_vorp, blended_season_vorp.csv) wrote to
tables nothing consumes. Pre-retirement copy:
goals/football-signal-database-and-app/hidden_files/
  build_blended_vorp_inputs.pre_canonical_20260918.py

Usage: python3 bin/build_blended_vorp_inputs.py
"""
import sys

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-mgmt/bin")
from mgmt import query  # noqa: E402  (full results; CLI print truncates)

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
import sbclient  # noqa: E402

sys.path.insert(0, "/home/hatch/workspace/football-signal")
from engine.canonical_players import (  # noqa: E402
    load_registry, norm_plain,
)

SKILL_POS = ("QB", "RB", "WR", "TE")
STAT_COLS = ["passing_yards", "passing_tds", "rushing_yards",
             "rushing_tds", "receptions", "receiving_yards",
             "receiving_tds"]


def esc(v):
    return v.replace("'", "''")


def chunked_insert(table, cols, rows, chunk=500):
    for i in range(0, len(rows), chunk):
        vals = ", ".join(
            "(" + ",".join(
                "NULL" if v is None else f"'{esc(str(v))}'" for v in r
            ) + ")" for r in rows[i:i + chunk])
        query(f"INSERT INTO {table} ({','.join(cols)}) VALUES {vals};")


def main():
    # ---- 1. schema (player_key added 2026-09-18) ----
    query("""
    CREATE TABLE IF NOT EXISTS blended_player_map (
      player_norm text PRIMARY KEY,
      display_name text,
      position text,
      team text,
      has_vegas boolean NOT NULL DEFAULT false);
    CREATE TABLE IF NOT EXISTS fp_season_latest_norm (
      player_norm text PRIMARY KEY,
      snapshot_date date,
      position text,
      team text,
      passing_yards double precision,
      passing_tds double precision,
      rushing_yards double precision,
      rushing_tds double precision,
      receptions double precision,
      receiving_yards double precision,
      receiving_tds double precision);
    """)
    print("schema ok", flush=True)

    # ---- 2. latest FP snapshot, deduped by canonical key ----
    fp_rows = sbclient.get_all(
        "v_fp_season_latest",
        "?select=player_key,position,team,passing_yards,passing_tds,"
        "rushing_yards,rushing_tds,receptions,receiving_yards,receiving_tds,"
        "proj_half_ppr,snapshot_date")
    print(f"fp rows: {len(fp_rows)}", flush=True)
    print("fp positions: " + str(sorted({r["position"] for r in fp_rows})),
          flush=True)

    reg = load_registry()

    def _better(r, prev):
        rp, pp = float(r["proj_half_ppr"] or 0), float(prev["proj_half_ppr"] or 0)
        if rp != pp:
            return rp > pp
        return str(r["snapshot_date"] or "") > str(prev["snapshot_date"] or "")

    by_key = {}
    for r in fp_rows:
        key = r["player_key"]
        if not key or r["position"] not in SKILL_POS:
            continue
        key = int(key)
        prev = by_key.get(key)
        if prev is None or _better(r, prev):
            by_key[key] = r
    print(f"fp players (skill positions, by key): {len(by_key)}", flush=True)

    # Transitional: the two tables are still PK'd on player_norm, so collapse
    # to one row per norm (winner = max proj_half_ppr, tie -> newest snapshot).
    # The winner's player_key is written; losers are audit-logged, never guessed.
    by_norm = {}
    for key, r in by_key.items():
        e = reg.by_key.get(key)
        if not e:
            print(f"  WARN: key {key} not in registry; skipped", flush=True)
            continue
        nn = norm_plain(e["full_name"])
        prev = by_norm.get(nn)
        if prev is None or _better(r, prev[0]):
            if prev is not None:
                print(f"  norm-dedup: '{nn}' key {prev[1]} -> {key} "
                      f"(proj {prev[0]['proj_half_ppr']}/{prev[0]['snapshot_date']} "
                      f"vs {r['proj_half_ppr']}/{r['snapshot_date']})", flush=True)
            by_norm[nn] = (r, key, e["full_name"])
    print(f"norm rows: {len(by_norm)}", flush=True)

    # ---- 3. blended_player_map (key-first; norm is transitional) ----
    query("DELETE FROM blended_player_map;")
    map_rows = [(nn, name, r["position"], r["team"], "false", key)
                for nn, (r, key, name) in by_norm.items()]
    chunked_insert("blended_player_map",
                   ["player_norm", "display_name", "position", "team",
                    "has_vegas", "player_key"], map_rows)
    print(f"blended_player_map: {len(map_rows)} rows", flush=True)

    # ---- 4. fp_season_latest_norm (key-first; norm is transitional) ----
    query("DELETE FROM fp_season_latest_norm;")
    norm_rows = [
        (nn, r["snapshot_date"], r["position"], r["team"]) + tuple(
            None if r[c] is None else float(r[c]) for c in STAT_COLS
        ) + (key,)
        for nn, (r, key, name) in by_norm.items()]
    chunked_insert("fp_season_latest_norm",
                   ["player_norm", "snapshot_date", "position", "team"]
                   + STAT_COLS + ["player_key"], norm_rows)
    print(f"fp_season_latest_norm: {len(norm_rows)} rows", flush=True)

    # ---- 5. audit: no NULL keys ----
    n_null = query("SELECT count(*) AS n FROM fp_season_latest_norm "
                   "WHERE player_key IS NULL;")[0]["n"]
    n_map_null = query("SELECT count(*) AS n FROM blended_player_map "
                       "WHERE player_key IS NULL;")[0]["n"]
    print(f"NULL keys: fp_season_latest_norm={n_null}, "
          f"blended_player_map={n_map_null}", flush=True)
    assert n_null == 0 and n_map_null == 0, "NULL player_key written"
    print("done", flush=True)


if __name__ == "__main__":
    main()
