#!/usr/bin/env python3
"""Unified VORP translation for as-published trade value sources (JEG-62).

Single module handling all as-published sources (USA Today, FantasyPros,
FantasyCalc, CBS). No per-source branching — the logic is identical.

Pipeline:
1. Load publisher native values
2. Compute rostered per position (flexible math, scales with teams)
3. Waiver line = first non-rostered player's value
4. VORP = native - waiver_line
5. Translate: vorp × (our_max / their_max_vorp)
6. Write all intermediates to Supabase

Usage:
    from vorp_translation.unified import translate_source
    result = translate_source('usatoday', scoring='half_ppr', teams=12, week=4)
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_ddf_two_tier_leg import (
    REF_SLOTS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    POSITIONS,
    BENCH_MIX_12,
)

# NFL season year for the JEG-62 Supabase grain (part of every unique key).
SEASON = 2026

# Supabase tables (migration: supabase/migrations/jeg62_vorp_translation.sql).
# Grain: (source, scoring, league_teams, week, season, position|player_key).
TBL_ASSUMPTIONS = "publisher_roster_assumptions"
TBL_VORP = "publisher_vorp"
TBL_TRANSLATED = "publisher_translated_values"
CONFLICT_ASSUMPTIONS = "source,scoring,league_teams,week,season,position"
CONFLICT_PLAYER = "source,scoring,league_teams,week,season,player_key"

# Our positional maxes (embody our starter/bench/positional economics)
# These are the anchors for translation — our 0-70 scale per position
OUR_MAX = {
    'QB': 25.0,
    'RB': 70.0,
    'WR': 55.0,
    'TE': 30.0,
}


def bench_for_teams(teams: int, bench_per_team: float = 6.0) -> dict[str, int]:
    """Scale bench by teams and bench size."""
    base_per_team = sum(BENCH_MIX_12.values()) / 12
    return {
        pos: int(BENCH_MIX_12[pos] * (teams / 12) * (bench_per_team / base_per_team) + 0.5)
        for pos in POSITIONS
    }


def flex_for_teams(teams: int, flex_count: Optional[int] = None) -> dict[str, int]:
    """Allocate flex proportionally to slots (JEG-61 will make scoring-aware)."""
    if flex_count is None:
        flex_count = REF_FLEX_COUNT
    total_flex = teams * flex_count
    flex_slots = sum(REF_SLOTS.get(pos, 0) for pos in REF_FLEX_ELIGIBLE)
    result = {}
    for pos in POSITIONS:
        if pos not in REF_FLEX_ELIGIBLE:
            result[pos] = 0
        else:
            result[pos] = int(total_flex * REF_SLOTS.get(pos, 0) / flex_slots + 0.5)
    # Fix rounding
    diff = total_flex - sum(result.values())
    if diff:
        largest = max(REF_FLEX_ELIGIBLE, key=lambda p: REF_SLOTS.get(p, 0))
        result[largest] += diff
    return result


def rostered_for_teams(teams: int, bench_per_team: float = 6.0,
                       flex_count: Optional[int] = None) -> dict[str, dict]:
    """Compute rostered counts per position."""
    flex_alloc = flex_for_teams(teams, flex_count)
    bench_alloc = bench_for_teams(teams, bench_per_team)
    return {
        pos: {
            'dedicated': teams * REF_SLOTS.get(pos, 0),
            'flex': flex_alloc[pos],
            'bench': bench_alloc[pos],
            'rostered': teams * REF_SLOTS.get(pos, 0) + flex_alloc[pos] + bench_alloc[pos],
        }
        for pos in POSITIONS
    }


def resolve_combo_key(sdata: dict, scoring: str, teams: int) -> str:
    """Resolve the fixture combo key for (scoring, teams).

    Most sources price a single combo per scoring/teams (e.g. half_12);
    FantasyCalc splits by QB config (half_12_qb1 / half_12_qb2). Prefer the
    exact key; otherwise take the first combo extending it, sorted
    (deterministic: qb1 before qb2). Data-driven, no per-source branching.
    Fail-closed when nothing matches — a silent empty translation would
    write zero rows and look like success.
    """
    exact = f"half_{teams}" if scoring == "half_ppr" else f"{scoring}_{teams}"
    combos = sdata.get("combos", {})
    if exact in combos:
        return exact
    prefixed = sorted(k for k in combos if k.startswith(exact + "_"))
    if prefixed:
        return prefixed[0]
    raise SystemExit(
        f"JEG-62 fail-closed: no fixture combo for scoring={scoring} "
        f"teams={teams} (tried '{exact}' and '{exact}_*')"
    )


def load_native_values(source: str, scoring: str, teams: int,
                       fixture_path: Optional[Path] = None
                       ) -> tuple[dict[str, list[tuple[str, float]]], dict[str, str]]:
    """Load publisher native values as ranked lists per position.

    In production, this reads from Supabase source_trade_values.
    For now, reads from the local fixture.

    Returns (by_pos, key_by_name): by_pos maps position -> [(name, value)]
    sorted descending; key_by_name maps lowercase name -> canonical player_key
    from the naming table (players.json). Every name in by_pos is guaranteed
    to have a key (unmatched names are excluded, fail-closed upstream).
    """
    if fixture_path is None:
        fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    players_path = REPO / "data" / "fixtures" / "current" / "players.json"

    fixture = json.loads(fixture_path.read_text())
    players = json.loads(players_path.read_text())
    pos_by_name = {p["name"].lower(): p["pos"] for p in players["players"]}
    key_by_name = {p["name"].lower(): p["player_key"] for p in players["players"]}

    sdata = fixture["sources"].get(source, {})
    combo_key = resolve_combo_key(sdata, scoring, teams)
    native = sdata.get("combos", {}).get(combo_key, {}).get("native", {})

    by_pos: dict[str, list[tuple[str, float]]] = {p: [] for p in POSITIONS}
    for name, val in native.items():
        pos = pos_by_name.get(name.lower())
        if pos in POSITIONS and val is not None:
            by_pos[pos].append((name, float(val)))
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x[1])
    return by_pos, key_by_name


def translate_source(source: str, scoring: str = "half_ppr", teams: int = 12,
                     week: int = 4, bench_per_team: float = 6.0,
                     write_supabase: bool = False) -> dict:
    """Unified VORP translation for any as-published source.
    
    Args:
        source: usatoday, fantasypros, fantasycalc, cbs
        scoring: standard, half_ppr, ppr
        teams: 10, 12, 14
        week: NFL week
        bench_per_team: bench spots per team (ESPN default 6.0)
        write_supabase: if True, write intermediates to Supabase
    
    Returns:
        {
            'source': str,
            'scoring': str,
            'teams': int,
            'week': int,
            'positions': {pos: {...roster, waiver, vorp stats...}},
            'ranked': {pos: [(player_key, name, native), ...] sorted desc},
            'translated': {player_key: {'name':, 'pos':, 'native':, 'vorp':, 'translated':}},
        }

    translated is keyed by canonical player_key (naming-table identity), not
    display name.
    """
    ranked, key_by_name = load_native_values(source, scoring, teams)
    roster = rostered_for_teams(teams, bench_per_team)

    result = {
        'source': source,
        'scoring': scoring,
        'teams': teams,
        'week': week,
        'positions': {},
        'ranked': {},
        'translated': {},
    }

    for pos in POSITIONS:
        players = ranked.get(pos, [])
        if not players:
            continue

        # Fail closed: every translated name must resolve to a canonical key.
        ranked_keyed = []
        for name, val in players:
            pkey = key_by_name.get(name.lower())
            if not pkey:
                raise SystemExit(
                    f"JEG-62 fail-closed: '{name}' ({pos}) has no player_key "
                    "in the naming table; refusing to write keyless rows."
                )
            ranked_keyed.append((pkey, name, val))
        result['ranked'][pos] = ranked_keyed

        r = roster[pos]
        n_rostered = r['rostered']

        # Waiver line = first non-rostered
        if len(players) > n_rostered:
            waiver_val = players[n_rostered][1]
            method = 'roster_determined'
        elif players:
            waiver_val = players[-1][1]
            method = 'insufficient_coverage'
        else:
            waiver_val = 0.0
            method = 'no_players'

        # VORP per player
        vorp_list = [(pkey, name, val, max(0.0, val - waiver_val))
                     for pkey, name, val in ranked_keyed]
        max_vorp = max((v for _, _, _, v in vorp_list), default=0.0)
        total_vorp = sum(v for _, _, _, v in vorp_list)

        # Translate via our positional max
        scale = OUR_MAX[pos] / max_vorp if max_vorp > 0 else 0.0
        for pkey, name, val, vorp in vorp_list:
            if vorp > 0:
                result['translated'][pkey] = {
                    'name': name,
                    'pos': pos,
                    'native': round(val, 1),
                    'vorp': round(vorp, 1),
                    'translated': round(vorp * scale, 1),
                }

        result['positions'][pos] = {
            'n_dedicated': r['dedicated'],
            'n_flex': r['flex'],
            'n_bench': r['bench'],
            'n_rostered': n_rostered,
            'waiver_line_value': round(waiver_val, 2),
            'waiver_method': method,
            'max_vorp': round(max_vorp, 1),
            'total_vorp': round(total_vorp, 1),
            'scale_factor': round(scale, 3),
        }
    
    # Implied weights
    total = sum(p['total_vorp'] for p in result['positions'].values())
    for pos in result['positions']:
        w = result['positions'][pos]['total_vorp'] / total if total > 0 else 0
        result['positions'][pos]['implied_weight'] = round(w, 4)
    
    if write_supabase:
        _write_to_supabase(result)
    
    return result


def _sb():
    """Supabase REST client via the stored credential (surrogate flow)."""
    bin_dir = Path.home() / "workspace" / "skills" / "supabase-football-signal" / "bin"
    if str(bin_dir) not in sys.path:
        sys.path.insert(0, str(bin_dir))
    import sbclient  # noqa: E402
    return sbclient


def _upsert(sbclient, table: str, rows: list[dict], on_conflict: str) -> int:
    """Idempotent upsert in 500-row chunks; returns rows written."""
    n = 0
    for start in range(0, len(rows), 500):
        sbclient.post(
            table,
            rows[start:start + 500],
            params=f"?on_conflict={on_conflict}",
            prefer="resolution=merge-duplicates",
        )
        n += len(rows[start:start + 500])
    return n


def build_write_rows(result: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Build the three Supabase row sets from a translate_source result.

    Pure function (no I/O) so the write grain is unit-testable without a DB.
    """
    source = result['source']
    scoring = result['scoring']
    teams = result['teams']
    week = result['week']
    bench_per_team = 6.0  # carried on assumption rows; matches translate default

    assumptions: list[dict] = []
    vorps: list[dict] = []
    translated: list[dict] = []

    for pos, p in result['positions'].items():
        assumptions.append({
            'source': source,
            'scoring': scoring,
            'league_teams': teams,
            'week': week,
            'season': SEASON,
            'position': pos,
            'n_dedicated': p['n_dedicated'],
            'n_flex': p['n_flex'],
            'n_bench': p['n_bench'],
            'n_rostered': p['n_rostered'],
            'waiver_line_value': p['waiver_line_value'],
            'waiver_method': p['waiver_method'],
            'bench_per_team': bench_per_team,
        })
        for rank, (pkey, name, native) in enumerate(result['ranked'][pos], 1):
            vorp = max(0.0, native - p['waiver_line_value'])
            vorps.append({
                'source': source,
                'scoring': scoring,
                'league_teams': teams,
                'week': week,
                'season': SEASON,
                'player_key': pkey,
                'position': pos,
                'native_value': round(native, 1),
                'vorp_value': round(vorp, 1),
                'pos_rank': rank,
            })

    for pkey, t in result['translated'].items():
        scale = result['positions'][t['pos']]['scale_factor']
        translated.append({
            'source': source,
            'scoring': scoring,
            'league_teams': teams,
            'week': week,
            'season': SEASON,
            'player_key': pkey,
            'position': t['pos'],
            'translated_value': t['translated'],
            'scale_factor': scale,
        })

    return assumptions, vorps, translated


def _write_to_supabase(result: dict) -> dict[str, int]:
    """Write all intermediates to the JEG-62 Supabase tables (idempotent).

    Fail-closed: a missing table (migration not run) raises loudly instead of
    silently dropping the write. Returns {table: rows_written}.
    """
    sbclient = _sb()
    assumptions, vorps, translated = build_write_rows(result)
    counts = {
        TBL_ASSUMPTIONS: _upsert(sbclient, TBL_ASSUMPTIONS, assumptions, CONFLICT_ASSUMPTIONS),
        TBL_VORP: _upsert(sbclient, TBL_VORP, vorps, CONFLICT_PLAYER),
        TBL_TRANSLATED: _upsert(sbclient, TBL_TRANSLATED, translated, CONFLICT_PLAYER),
    }
    return counts


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unified VORP translation")
    parser.add_argument("--source", required=True,
                        choices=["usatoday", "fantasypros", "fantasycalc", "cbs"])
    parser.add_argument("--scoring", default="half_ppr",
                        choices=["standard", "half_ppr", "ppr"])
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--week", type=int, default=4)
    parser.add_argument("--write-supabase", action="store_true",
                        help="Write intermediates to Supabase (requires the "
                             "JEG-62 migration to have run)")
    args = parser.parse_args()

    result = translate_source(args.source, args.scoring, args.teams, args.week,
                              write_supabase=args.write_supabase)
    
    print(f"\nVORP Translation: {args.source} ({args.scoring}, {args.teams}t, W{args.week})")
    print("=" * 70)
    for pos in ['QB', 'RB', 'WR', 'TE']:
        p = result['positions'].get(pos)
        if not p:
            continue
        print(f"\n{pos}: rostered={p['n_rostered']} waiver={p['waiver_line_value']} "
              f"max_vorp={p['max_vorp']} weight={p['implied_weight']:.1%}")
    
    print(f"\nTranslated {len(result['translated'])} players")


if __name__ == "__main__":
    main()
