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
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
sys.path.insert(0, str(REPO))

from build_ddf_two_tier_leg import (
    REF_SLOTS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    POSITIONS,
)
from pipelines.vorp_translation.vorp_via_roster import (
    apportion,
    bench_for_teams,
    rostered_for_teams,
)
# Canonical identity: all name resolution goes through the naming table via
# player_key (standing rule 2026-10-02; JEG-75). Never match on raw strings.
from canonical_players import Registry, norm_player_name, resolve as _resolve_key

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

# JEG332-DERIVED-PEAKS (2026-10-07): OUR_MAX is the calibration at the saved
# setup (12 teams, QB1 RB2 WR3 TE1 FLEX1 BENCH6). At any other league setting
# the positional maxes follow OUR model's scarcity there: each position's max
# is OUR_MAX scaled by how much the top player's value above waivers (ESPN
# per-game projections, the anchor's input, through the SAME roster/waiver
# math as the translation) grows or shrinks against the saved setup; then all
# four are rescaled so the top position sits at TOP_OF_SCALE (70), the chart's
# convention that the top player is 70 (the ESPN anchor's RB peak is ~70 at
# every setting). At the saved setup every ratio is exactly 1 and k = 1, so
# the maxes are OUR_MAX exactly. Browser port: value-model.js
# positionalMaxForSetup (parity: tests/test_vorp_translation_js_parity.py).
POSITIONAL_MAX_VERSION = "espn-vaw-ratio/1"
TOP_OF_SCALE = max(OUR_MAX.values())
SAVED_SETUP_TEAMS = 12


def flex_for_teams(teams: int, flex_count: Optional[int] = None) -> dict[str, int]:
    """Slot-proportional fallback when publisher values are unavailable."""
    if flex_count is None:
        flex_count = REF_FLEX_COUNT
    total_flex = teams * flex_count
    return apportion({pos: REF_SLOTS[pos] for pos in REF_FLEX_ELIGIBLE}, total_flex)


def resolve_combo_key(sdata: dict, scoring: str, teams: int) -> str:
    """Resolve the fixture combo key for (scoring, teams).

    Most sources price a single combo per scoring/teams (e.g. half_12);
    FantasyCalc splits by QB config (half_12_qb1 / half_12_qb2). Prefer the
    exact key; otherwise take the first combo extending it, sorted
    (deterministic: qb1 before qb2). Data-driven, no per-source branching.
    Fail-closed when nothing matches — a silent empty translation would
    write zero rows and look like success.
    """
    prefix = {"half_ppr": "half", "ppr": "full"}.get(scoring, scoring)
    exact = f"{prefix}_{teams}"
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
                       fixture_path: Optional[Path] = None,
                       superflex: bool = False,
                       ) -> tuple[dict[str, list[tuple[str, float]]], dict[str, str]]:
    """Load publisher native values as ranked lists per position.

    In production, this reads from Supabase source_trade_values.
    For now, reads from the local fixture.

    Returns (by_pos, key_by_name): by_pos maps position -> [(name, value)]
    sorted descending; key_by_name maps lowercase name -> canonical player_key
    from the naming table (players.json). Every name in by_pos is guaranteed
    to have a key (unmatched names are excluded, fail-closed upstream).

    superflex=True mirrors the browser with a superflex slot on the roster
    (curve-widget.js savedPublishedNative, GAP-SUPERFLEX-PUBLISHER-VALUES):
    the publisher's own superflex values (`native_superflex`) replace its
    1-QB natives where it publishes them. Default False: the 1-QB natives.
    """
    if fixture_path is None:
        fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    players_path = REPO / "data" / "fixtures" / "current" / "players.json"

    fixture = json.loads(fixture_path.read_text())
    # Canonical registry built from the naming table (players.json). Identity
    # resolves through norm_player_name + player_key -- never raw strings, so
    # 'jaxon smithnjigba' (fixture slug) matches 'Jaxon Smith-Njigba'.
    reg = naming_registry(players_path)

    sdata = fixture["sources"].get(source, {})
    combo_key = resolve_combo_key(sdata, scoring, teams)
    combo = sdata.get("combos", {}).get(combo_key, {})
    native = combo.get("native", {})
    if superflex and native and combo.get("native_superflex"):
        native = {**native, **combo["native_superflex"]}
    return rank_natives(native, reg)


def naming_registry(players_path: Optional[Path] = None) -> Registry:
    """Canonical registry from the naming table (players.json)."""
    if players_path is None:
        players_path = REPO / "data" / "fixtures" / "current" / "players.json"
    players = json.loads(players_path.read_text())
    return Registry([
        {"player_key": p["player_key"], "full_name": p["name"],
         "position": p.get("pos"), "active": True}
        for p in players["players"] if p.get("player_key") is not None
    ])


def rank_natives(native: dict, reg: Optional[Registry] = None
                 ) -> tuple[dict[str, list[tuple[str, float]]], dict[str, str]]:
    """Rank one combo's native values per position (load_native_values core).

    native: {fixture slug: publisher native value}. Returns (by_pos,
    key_by_name) exactly as load_native_values does; names whose identity does
    not resolve through the naming table are excluded.
    """
    if reg is None:
        reg = naming_registry()
    by_pos: dict[str, list[tuple[str, float]]] = {p: [] for p in POSITIONS}
    key_by_name: dict[str, str] = {}
    for name, val in native.items():
        if val is None:
            continue
        key = _resolve_key(name, registry=reg)
        if key is None:
            # Unresolvable identity -> excluded (fail-closed upstream).
            continue
        pos = reg.by_key[key]["position"]
        if pos in POSITIONS:
            by_pos[pos].append((name, float(val)))
            key_by_name[norm_player_name(name)] = str(key)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x[1])
    return by_pos, key_by_name


def keyed_ranked(native: dict, reg: Optional[Registry] = None) -> dict:
    """{pos: [(player_key, slug, value)]} sorted descending (rank_natives, keyed)."""
    by_pos, key_by_name = rank_natives(native, reg)
    return {pos: [(key_by_name[norm_player_name(n)], n, v) for n, v in rows]
            for pos, rows in by_pos.items() if rows}


AS_PUBLISHED = ("cbs", "fantasycalc", "fantasypros", "usatoday")


def peer_natives(fixture: dict, source: str, scoring: str) -> dict:
    """The OTHER published charts' saved 12-team natives at this scoring.

    {peer_source: {slug: native}}; a peer with no saved combo for the scoring
    is left out (it borrows nothing). The browser reads the same combos
    (product-data view=native, teams=12, qb1).
    """
    out = {}
    for peer in AS_PUBLISHED:
        if peer == source:
            continue
        sdata = (fixture.get("sources") or {}).get(peer) or {}
        try:
            combo_key = resolve_combo_key(sdata, scoring, SAVED_SETUP_TEAMS)
        except SystemExit:
            continue
        native = (sdata["combos"][combo_key] or {}).get("native") or {}
        if native:
            out[peer] = native
    return out


def peers_ranked(peer_native_docs: Optional[dict], reg: Optional[Registry] = None) -> dict:
    """{peer: {slug: native}} -> {peer: {pos: [(key, slug, value)]}}."""
    return {peer: keyed_ranked(native, reg) for peer, native in (peer_native_docs or {}).items()}


def waiver_summary(positions: dict) -> dict:
    """Per-position waiver provenance for a translation (the denotation)."""
    return {pos: {"method": p["waiver_method"], "n_listed": p["n_listed"],
                  "n_rostered": p["n_rostered"], "n_imputed": p["n_imputed"]}
            for pos, p in positions.items()}


def translate_natives(native: dict, teams: int, reg: Optional[Registry] = None,
                      peers: Optional[dict] = None) -> dict:
    """Translate ONE combo's own native values at the default roster.

    JEG332-STORED-DRIFT (2026-10-07): the comparison chain's translate stage
    used to read the Supabase grain written by the PREVIOUS run's natives, so
    every native refresh promoted a stale translation. This is the same math
    as translate_source (rank_natives + translate_ranked, default roster), run
    on the values being promoted.

    Returns {'slug_keys': {slug: player_key}, 'evaluated': {player_key},
    'translated': {player_key: translated_value}, 'positions': {...}}.
    'evaluated' holds every player the translation priced (above or at/below
    the waiver line); a key in evaluated but not in translated is at or below
    the waiver line.
    """
    by_pos, key_by_name = rank_natives(native, reg)
    ranked_keyed = {pos: [(key_by_name[norm_player_name(n)], n, v) for n, v in rows]
                    for pos, rows in by_pos.items() if rows}
    core = translate_ranked(ranked_keyed, teams, peers=peers_ranked(peers, reg))
    slug_keys = {n: key_by_name[norm_player_name(n)]
                 for rows in by_pos.values() for n, _v in rows}
    return {
        "slug_keys": slug_keys,
        "evaluated": set(slug_keys.values()),
        "translated": {k: t["translated"] for k, t in core["translated"].items()},
        "positions": core["positions"],
        "peers": sorted(peers or {}),
    }


def translate_source(source: str, scoring: str = "half_ppr", teams: int = 12,
                     week: int = 4, bench_per_team: float = 6.0,
                     write_supabase: bool = False,
                     flex_count: Optional[int] = None,
                     impute: bool = True) -> dict:
    """Unified VORP translation for any as-published source.
    
    Args:
        source: usatoday, fantasypros, fantasycalc, cbs
        scoring: standard, half_ppr, ppr
        teams: 10, 12, 14
        week: NFL week
        bench_per_team: bench spots per team (ESPN default 6.0)
        write_supabase: if True, write intermediates to Supabase
        flex_count: flex slots per team (default REF_FLEX_COUNT)
    
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
    # The current storage grain does not distinguish custom roster settings.
    # Keep them read-only until that contract can represent them separately.
    if write_supabase and (bench_per_team != 6.0 or
                           flex_count not in (None, REF_FLEX_COUNT)):
        raise SystemExit("custom roster settings cannot overwrite default-grain VORP rows")
    ranked, key_by_name = load_native_values(source, scoring, teams)
    # V2-WAIVER-COVERAGE: the other published charts' saved natives, so a
    # short position's waiver line is extrapolated exactly as the chain and
    # the browser do it.
    fixture = json.loads((REPO / "data" / "fixtures" / "current"
                          / "comparison-sources-data.json").read_text())
    peers = peers_ranked(peer_natives(fixture, source, scoring)) if impute else None

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
            pkey = key_by_name.get(norm_player_name(name))
            if not pkey:
                raise SystemExit(
                    f"JEG-62 fail-closed: '{name}' ({pos}) has no player_key "
                    "in the naming table; refusing to write keyless rows."
                )
            ranked_keyed.append((pkey, name, val))
        result['ranked'][pos] = ranked_keyed

    core = translate_ranked(result['ranked'], teams, bench_per_team, flex_count, peers=peers)
    result['positions'] = core['positions']
    result['translated'] = core['translated']

    if write_supabase:
        _write_to_supabase(result)

    return result


# V2-WAIVER-COVERAGE (Jeremy 2026-10-07: "If needed for computations, cover
# them by extrapolating from the average of other charts. Denote them. Where
# it's not needed, hide those values.")
#
# When a chart lists fewer players at a position than the league rosters, its
# waiver line used to fall back to its LAST listed value, so the bottom of a
# short chart was 0 only because the list ended. Now the chart is extended past
# its own list with IMPUTED native values for players it does not list, taken
# from the other published charts (impute_extension), and the waiver line is
# the value at the rostered count of that extended list. Imputed players exist
# only for this computation: they never receive a translated value.
#
# Mapping (per position, per other chart O): k_O = sum(this chart's natives) /
# sum(O's natives) over the players both list among the BOTTOM HALF of this
# chart's list (value <= its median listed value, ties included, so input
# order never matters; at least IMPUTE_MIN_FIT of them, else O is not used). An
# unlisted player's imputed native is the mean over the usable charts that
# list him of k_O x O's native, capped at this chart's last listed value (a
# chart that leaves a player out values him at most at its last listed
# value). Proportional, so monotone in every other chart's value. The
# extension is ordered by that imputed value (ties: player key), appended
# after the chart's own list. Browser port: value-model.js imputeExtension.
IMPUTATION_VERSION = "other-charts-tail-ratio/1"
IMPUTE_MIN_FIT = 3
WAIVER_IMPUTED = "imputed_from_other_charts"


def _pairs(rows) -> list:
    """(key, value) pairs from (key, value) or (key, name, value) rows."""
    return [(str(row[0]), float(row[-1])) for row in rows or []]


def impute_extension(ranked: dict, peers: Optional[dict]) -> dict:
    """Imputed natives for the players this chart does not list, per position.

    ranked: {pos: [(key, value)]} this chart, sorted descending.
    peers: {source: {pos: [(key, value)]}} the OTHER published charts (same
    scoring, saved 12-team natives); rows may also be (key, name, value).
    Returns {pos: [(key, imputed_value)]} sorted by value desc, key asc; a
    position with nothing to impute is absent. Arithmetic order is fixed
    (peers by sorted source name, players by sorted key string) so the
    browser port reproduces every float bit for bit.
    """
    out: dict[str, list] = {}
    if not peers:
        return out
    for pos in POSITIONS:
        listed = _pairs(ranked.get(pos))
        if not listed:
            continue
        mine = dict(listed)
        last = listed[-1][1]
        median = listed[len(listed) // 2][1]
        tail = sorted(k for k, v in listed if v <= median)
        acc: dict[str, list] = {}
        for source in sorted(peers):
            theirs = dict(_pairs((peers[source] or {}).get(pos)))
            shared = [k for k in tail if k in theirs]
            if len(shared) < IMPUTE_MIN_FIT:
                continue
            num = 0.0
            den = 0.0
            for k in shared:
                num += mine[k]
                den += theirs[k]
            if not den > 0:
                continue
            ratio = num / den
            for k in sorted(theirs):
                if k in mine:
                    continue
                slot = acc.setdefault(k, [0.0, 0])
                slot[0] += ratio * theirs[k]
                slot[1] += 1
        ext = [(k, min(last, total / count)) for k, (total, count) in acc.items()]
        if ext:
            ext.sort(key=lambda row: (-row[1], row[0]))
            out[pos] = ext
    return out


def translate_ranked(ranked_keyed: dict, teams: int, bench_per_team: float = 6.0,
                     flex_count: Optional[int] = None,
                     slots: Optional[dict] = None,
                     flex_eligible: Optional[list] = None,
                     our_max: Optional[dict] = None,
                     peers: Optional[dict] = None,
                     superflex_count: int = 0) -> dict:
    """Pure core of translate_source: no fixture, no naming table, no I/O.

    our_max: positional maxes to translate onto (default OUR_MAX, today's
    fixed anchors). positional_max_for_setup supplies league-following maxes.

    superflex_count: dedicated superflex slots per team (JEG332-SUPERFLEX-FLEX
    option A; vorp_via_roster.allocate_superflex). Default 0 = unchanged
    output; when > 0 each position also reports n_superflex.

    peers: the other published charts' natives ({source: {pos: [(key,
    value)]}}). When given, a position where this chart lists no more players
    than the league rosters is extended with impute_extension's values and
    its waiver line is read from the extended list (waiver_method
    'imputed_from_other_charts'). Extension is applied only to such short
    positions (re-checked after the roster allocation moves, at most once per
    position), so a chart that is never short translates exactly as before.
    If the extended list is still too short, the old fallback applies (last
    LISTED value, 'insufficient_coverage').

    ranked_keyed: {pos: [(player_key, name, native), ...]} sorted descending.
    Returns {'positions': {...}, 'translated': {...}} exactly as
    translate_source reports them.

    JEG-332: this is the reference the browser port
    (app/trade-value-chart/assets/value-model.js translatePublishedVorp) is
    held to by tests/test_vorp_translation_js_parity.py. slots/flex_eligible
    default to the server's standard roster, so translate_source output is
    unchanged; the browser passes the chart's roster steppers.
    """
    if our_max is None:
        our_max = OUR_MAX
    ranked = {pos: [(pkey, val) for pkey, _name, val in rows]
              for pos, rows in ranked_keyed.items()}
    extension = impute_extension(ranked, peers) if peers else {}
    extended: set = set()
    while True:
        work = {pos: rows + (extension[pos] if pos in extended else [])
                for pos, rows in ranked.items()}
        roster = rostered_for_teams(teams, bench_per_team, flex_count, ranked=work,
                                    slots=slots, flex_eligible=flex_eligible,
                                    superflex_count=superflex_count)
        short = [pos for pos in POSITIONS
                 if pos not in extended and pos in extension and ranked.get(pos)
                 and len(ranked[pos]) <= roster[pos]['rostered']]
        if not short:
            break
        extended.update(short)
    result = {'positions': {}, 'translated': {}}

    for pos in POSITIONS:
        ranked_rows = ranked_keyed.get(pos, [])
        if not ranked_rows:
            continue
        players = [(name, val) for _pkey, name, val in ranked_rows]
        line = work[pos]
        r = roster[pos]
        n_rostered = r['rostered']
        n_imputed = 0

        # Waiver line = first non-rostered (of the extended list when the
        # chart is short and other charts cover it).
        if len(line) > n_rostered:
            waiver_val = line[n_rostered][1]
            if n_rostered < len(players):
                method = 'roster_determined'
            else:
                method = WAIVER_IMPUTED
                n_imputed = n_rostered - len(players) + 1
        elif players:
            waiver_val = players[-1][1]
            method = 'insufficient_coverage'
        else:
            waiver_val = 0.0
            method = 'no_players'

        # VORP per player
        vorp_list = [(pkey, name, val, max(0.0, val - waiver_val))
                     for pkey, name, val in ranked_rows]
        max_vorp = max((v for _, _, _, v in vorp_list), default=0.0)
        total_vorp = sum(v for _, _, _, v in vorp_list)

        # Translate via our positional max
        scale = our_max[pos] / max_vorp if max_vorp > 0 else 0.0
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
            'n_listed': len(players),
            'n_imputed': n_imputed,
            'waiver_line_value': round(waiver_val, 2),
            'waiver_method': method,
            'max_vorp': round(max_vorp, 1),
            'total_vorp': round(total_vorp, 1),
            'scale_factor': round(scale, 3),
        }
        if superflex_count:
            result['positions'][pos]['n_superflex'] = r['superflex']
    
    # Implied weights
    total = sum(p['total_vorp'] for p in result['positions'].values())
    for pos in result['positions']:
        w = result['positions'][pos]['total_vorp'] / total if total > 0 else 0
        result['positions'][pos]['implied_weight'] = round(w, 4)

    return result


def projection_max_vorp(projection_ranked: dict, teams: int, bench_per_team: float = 6.0,
                        flex_count: Optional[int] = None, slots: Optional[dict] = None,
                        flex_eligible: Optional[list] = None,
                        superflex_count: int = 0) -> dict[str, float]:
    """Top player's value above waivers per position, unrounded.

    projection_ranked: {pos: [(player_key, name, per_game_points), ...]}
    sorted descending. Rostered counts and the waiver line use exactly the
    translation's rules (rostered_for_teams; waiver = first unrostered, or
    the last player when coverage runs out).
    """
    ranked = {pos: [(pkey, float(val)) for pkey, _name, val in rows]
              for pos, rows in projection_ranked.items()}
    roster = rostered_for_teams(teams, bench_per_team, flex_count, ranked=ranked,
                                slots=slots, flex_eligible=flex_eligible,
                                superflex_count=superflex_count)
    out = {}
    for pos in POSITIONS:
        rows = ranked.get(pos) or []
        if not rows:
            continue
        n = roster[pos]['rostered']
        waiver = rows[n][1] if len(rows) > n else rows[-1][1]
        out[pos] = max(0.0, rows[0][1] - waiver)
    return out


def positional_max_for_setup(projection_ranked: dict, teams: int, bench_per_team: float = 6.0,
                             flex_count: Optional[int] = None, slots: Optional[dict] = None,
                             flex_eligible: Optional[list] = None,
                             superflex_count: int = 0) -> dict[str, float]:
    """League-following positional maxes (JEG332-DERIVED-PEAKS rule).

    raw[pos] = OUR_MAX[pos] * M_pos(setting) / M_pos(saved setup), where M is
    projection_max_vorp; then every raw max is multiplied by
    TOP_OF_SCALE / max(raw) so the top position sits at 70. A position with no
    reference surplus keeps OUR_MAX. At the saved setup this returns OUR_MAX
    exactly.
    """
    ref = projection_max_vorp(projection_ranked, SAVED_SETUP_TEAMS)
    at = projection_max_vorp(projection_ranked, teams, bench_per_team, flex_count,
                             slots=slots, flex_eligible=flex_eligible,
                             superflex_count=superflex_count)
    raw = {}
    for pos in POSITIONS:
        r = ref.get(pos, 0.0)
        raw[pos] = OUR_MAX[pos] * (at.get(pos, 0.0) / r) if r > 0 else OUR_MAX[pos]
    top = max(raw.values())
    if not top > 0:
        return dict(OUR_MAX)
    k = TOP_OF_SCALE / top
    return {pos: raw[pos] * k for pos in POSITIONS}


def load_projection_ranked(scoring: str, players_path: Optional[Path] = None) -> dict:
    """ESPN per-game projections from the naming table, ranked per position.

    Returns {pos: [(player_key, name, espn_ppg), ...]} sorted descending --
    the same numbers the browser reads from player.espn_ppg[scoring].
    """
    if players_path is None:
        players_path = REPO / "data" / "fixtures" / "current" / "players.json"
    players = json.loads(players_path.read_text())["players"]
    out: dict[str, list] = {pos: [] for pos in POSITIONS}
    for p in players:
        pos = p.get("pos")
        val = (p.get("espn_ppg") or {}).get(scoring)
        if pos in out and p.get("player_key") is not None and isinstance(val, (int, float)):
            out[pos].append((str(p["player_key"]), p.get("name"), float(val)))
    for pos in out:
        out[pos].sort(key=lambda row: -row[2])
    return out


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
    parser.add_argument("--bench-per-team", type=float, default=6.0)
    parser.add_argument("--flex-count", type=int, default=REF_FLEX_COUNT)
    parser.add_argument("--write-supabase", action="store_true",
                        help="Write intermediates to Supabase (requires the "
                             "JEG-62 migration to have run)")
    args = parser.parse_args()

    result = translate_source(args.source, args.scoring, args.teams, args.week,
                              bench_per_team=args.bench_per_team,
                              write_supabase=args.write_supabase,
                              flex_count=args.flex_count)
    
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
