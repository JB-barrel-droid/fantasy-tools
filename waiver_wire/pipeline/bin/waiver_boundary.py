"""Finite-capacity waiver boundary (shared by builder and audit).

The boundary mirrors the trade value chart's own spot-filling math
(starter_model.build_model): for every active settings vector, the chart fills
an EXACT set of roster spots by ranking the complete pool on continuous
per-game projections (positional: dedicated starters -> FLEX -> bench).
The Monday repricing fills the same structure of spots. The boundary is the
comparison of the two rostered sets -- no value-thresholding, no zero-tail
padding, no pid tiebreaks. (2026-09-15: the user corrected an earlier
implementation that ranked by integer value and padded with pid-sorted
zero-value players, which manufactured fake 0->0 drops. Under the chart's
real spot-filling, every rostered player has value >= 1, so a drop can never
show 0->0 -- every drop genuinely held a roster spot and lost it.)

For every active settings vector:
  capacity = teams x (QB + RB + WR + TE + FLEX starters + bench)

  1. Complete pool: the Monday legs are keyed by canonical identity (one
     record per human - the impute merges feed variants upstream via the
     Supabase player_identities registry, so the old duplicate-leg-entry
     class is gone; the boundary keeps a registry-based alias safety net).
     Players with no Monday projection are unpriced: skipped (never mapped
     to 0), reported in `unpriced`.
  2. Old rosterable set O = build_model(chart projections)["rostered"].
     New rosterable set M = build_model(Monday projections)["rostered"].
     Both are exact (capacity pids); |M - O| == |O - M| BY CONSTRUCTION.
  3. Display values (old/new) are upside-ON (chart base + lottery edge, news
     mult), never bare trade_value. The boundary sets use pure projections;
     the display adds the upside layer.
  4. Sections (user's taxonomy, 2026-09-15, refined 2026-09-16):
       Hot   = the most-added players since Sunday (>=15k Sleeper adds,
               available, priced, not holds/drops), ranked by add count.
               Each card carries a verdict: ADD (entrant or real value
               new>=4 - the value layer agrees) or PASS (fringe/zero value).
       Add   = "Other pickups we like": available entrants NOT on the hot
               list - the data's under-the-radar finds.
       Drop  = displaced incumbents (O - M) whose display Monday value is 0
               ("moved to 0").
       Hold  = (O & M) declined but still positive ("high to low, non-0"),
               plus displaced incumbents with positive upside value
               ("hold your nerve": lost the median spot, upside case remains),
               plus the surface-says-drop class.
       In-both and increased WITHOUT community momentum -> hold-steady
       ("didn't move, but should be rostered": already on the board - check
       whether they're free in your league).
       Hold-steady = in-both, still positive, not a hold: "didn't move,
       but should be rostered". Available (wire-check) or a big value jump
       (delta >= 5) under 90% rostered.
     Every section ranked by highest updated (Monday) value.
  5. Add/Drop counts reconcile at the BOUNDARY level (|entrants| ==
     |displaced|); the visible Drop section is the moved-to-0 subset, so
     visible adds and drops need not be equal. The audit enforces
     boundary parity and section-definition compliance, not add==drop.
"""

import json
import re
import sys
from pathlib import Path

LOT = Path(__file__).resolve().parent.parent
# 2026-09-22: chart data moved to the fantasy-tools repo fixtures; resolve via
# the shared chart_paths module (same as coverage_check.py), never a
# hardcoded legacy path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chart_paths import CHART_DIR  # noqa: E402
TRADE_VALUE_DIR = CHART_DIR
from identity import IdentityMap  # noqa: E402
from board_week import board_stem  # noqa: E402

# The naming table: Supabase `players` (full_name by player_key) via the one
# shared resolver. Every displayed name in the pipe sequence comes from here.
sys.path.insert(0, str(Path.home() / "workspace" / "football-signal" / "engine"))
from canonical_players import (  # noqa: E402
    load_registry as _load_naming_registry,
    require_canonical_name,
    resolve_with_reason,
    resolve_skill,
    canonical_name,
)


def _naming_registry():
    """The naming table as a canonical_players Registry.

    Module-level seam so tests can stub the registry without network.
    The Registry itself is cached by canonical_players.load_registry.
    """
    return _load_naming_registry()


def _resolve_leg_identity(name, pos, reg):
    """Leg-only display name -> (player_key, canonical full_name).

    Resolves through the naming table, position-aware. Falls back to the
    exactly-one-skill-hit rule only when the name is cleanly unmatched at
    the leg's position (a stale leg/trends position must not mask a real
    conflict). Returns None on ambiguous / position-conflict / unmatched:
    the caller fails closed instead of manufacturing a name.
    """
    key, reason = resolve_with_reason(name, position=pos, registry=reg)
    if key is None and reason == "unmatched":
        key = resolve_skill(name, registry=reg)
    if key is None:
        return None
    return key, canonical_name(key, registry=reg)

DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1}


def norm_name(n):
    return re.sub(r"[^a-z ]", "", str(n).lower()).strip()


def _load_chart():
    data = json.loads((TRADE_VALUE_DIR / "players.json").read_text())
    return data["players"]


def _load_leg_raw(scoring="half"):
    """Monday per-game projections leg, raw keys: ({norm_name: record}, label).

    Leg preference (2026-09-16, enforced 2026-09-19): newest valid
    reassessed -> newest dated current -> Monday market step, via
    leg_files.load_leg. Reading imputed_proj_<scoring>.json directly had
    frozen the boundary on the 9/17 Monday leg while the dashboard label
    claimed reassessed 9/18 (Montgomery, Shakir, Collins, Stevenson,
    Etienne, Flowers priced a day stale).
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from leg_files import load_leg
    recs, label = load_leg(LOT / "results", scoring)
    return {norm_name(k): v for k, v in recs.items()}, label


def _normalize_leg_keys(leg):
    """Rename leg keys onto chart pids via the alias map.

    One record per human, keyed the way the chart (and the dashboard)
    spells the name. When two leg keys resolve to one chart key the
    fresh-then-exact preference mirrors _monday_proj.
    """
    _, leg2chart = canonical_pool()
    out = {}
    for k, r in leg.items():
        ck = leg2chart.get(k, k)
        note = (r or {}).get("note") or ""
        fresh = ("carries the preseason baseline" not in note
                 and "no expected-points read" not in note)
        cand = (fresh, k == ck, r)
        prev = out.get(ck)
        if prev is None or (cand[0], cand[1]) > (prev[0], prev[1]):
            out[ck] = cand
    return {ck: c[2] for ck, c in out.items()}


def _load_leg(scoring="half"):
    """Monday per-game projections leg keyed by chart pid: {pid: record}."""
    raw, _label = _load_leg_raw(scoring)
    return _normalize_leg_keys(raw)


def _load_leg_with_label(scoring="half"):
    """_load_leg plus the leg_files label ('reassessed:<date>' | ...)."""
    raw, label = _load_leg_raw(scoring)
    return _normalize_leg_keys(raw), label


def _resolve_alias(key, chart_pos, ident, chart_canon=None):
    """Map a Monday-leg key onto a chart key via the canonical identity map.

    The Supabase player_identities registry (via bin/identity.py) is the
    authority - no hardcoded nickname tables here. Falls back to None when
    the key is genuinely leg-only.

    Two spellings of one human can straddle the registry's canonical form
    and the chart's canonical display name (leg 'cameron ward' vs chart
    'cam ward', both canon to 'cameron ward'). The second branch matches by
    canonical equivalence; it fails closed (None) when zero or several
    chart keys share the form - never a guess.
    """
    ck = ident.canon(key)
    if ck != key and ck in chart_pos:
        return ck
    if chart_canon is None:
        chart_canon = {c: ident.canon(c) for c in chart_pos}
    cands = [c for c in chart_pos if c != key and chart_canon.get(c) == ck]
    if len(cands) == 1:
        return cands[0]
    return None


def canonical_pool():
    """Return {pid: {name, pos, team, player_key}} for the complete pool.

    pid is the chart-normalized name (leg-only players keep their leg key).

    Naming-table rule (2026-09-19): every displayed name ties to the naming
    table (Supabase players.full_name by player_key) via
    engine/canonical_players - fail-closed. Chart players resolve through
    their chart player_key; leg-only players resolve through the canonical
    registry, position-aware. A leg-only human with no resolvable identity
    is excluded from the pool: a title-cased leg key is never manufactured
    as a display name, and a source spelling is never substituted.
    """
    reg = _naming_registry()
    chart = _load_chart()
    pool = {}
    for p in chart:
        if p.get("pos") not in ("QB", "RB", "WR", "TE"):
            continue
        k = norm_name(p["name"])
        key = p.get("player_key")
        if key is None:
            raise SystemExit(
                "FAIL-CLOSED: chart player %r has no player_key - the "
                "waiver pool cannot tie its name to the naming table."
                % (p.get("name"),))
        name = require_canonical_name(key, registry=reg)
        if name != p["name"]:
            print(f"WARNING: chart name {p['name']!r} != naming-table "
                  f"{name!r} (player_key {key}); displaying the canonical "
                  f"name.", file=sys.stderr, flush=True)
        pool[k] = {"name": name, "pos": p["pos"],
                   "team": p.get("team") or "", "player_key": int(key)}
    chart_pos = {k: v["pos"] for k, v in pool.items()}
    ident = IdentityMap(chart_keys=set(chart_pos))
    chart_canon = {c: ident.canon(c) for c in chart_pos}
    leg, _ = _load_leg_raw("half")
    trends = json.loads(
        (LOT.parent / "waiver-trends" / "results" / "trends_latest.json").read_text())
    leg2chart = {}
    for k in leg:
        if k in pool:
            continue
        a = _resolve_alias(k, chart_pos, ident, chart_canon)
        if a:
            leg2chart[k] = a
    for k in leg:
        if k in pool or k in leg2chart:
            continue
        rec = leg.get(k) or {}
        t = trends.get(k) or {}
        pos = rec.get("pos") or t.get("pos")
        if pos not in ("QB", "RB", "WR", "TE"):
            # Kickers, defenses, and players with no known skill position
            # stay out of the waiver pool. A position is never invented:
            # the old `or "WR"` fallback priced QBs (Cam Ward) and RBs
            # (Etienne, Skattebo) as wide receivers.
            continue
        resolved = _resolve_leg_identity(rec.get("name") or k, pos, reg)
        if resolved is None:
            print(f"WARNING: leg-only player {k!r} has no resolvable "
                  f"naming-table identity - excluded from the pool "
                  f"(fail-closed).", file=sys.stderr, flush=True)
            continue
        key, name = resolved
        pool[k] = {"name": name, "pos": pos,
                   "team": rec.get("team") or t.get("team") or "",
                   "player_key": key}
    return pool, leg2chart


def _edge_map():
    """Lottery edge (upside layer) by canonical pid, from the weekly board."""
    board = json.loads((LOT / ("results/" + board_stem() + ".json")).read_text())
    edge = {}
    for sec in ("lottery_tickets", "upside_stashes", "on_the_radar"):
        for p in board.get(sec, []):
            edge.setdefault(norm_name(p["player"]), p.get("lottery_edge_tv") or 0)
    return edge


def _mult_map(leg2chart):
    """News multiplier by canonical pid (alias-deduplicated like _monday_proj)."""
    mult = {}
    for scoring in ("half", "std", "full"):
        try:
            leg = _load_leg(scoring)
        except FileNotFoundError:
            continue
        for k, r in leg.items():
            ck = leg2chart.get(k, k)
            m = (r or {}).get("mult") or 1.0
            if abs(m - 1.0) > 1e-9:
                # Exact chart-key matches win over alias variants.
                prev = mult.setdefault(ck, {})
                if k == ck or scoring not in prev:
                    prev[scoring] = m
    # half leg is the canonical multiplier source; fall back across scorings
    out = {}
    for ck, m in mult.items():
        out[ck] = m.get("half") or m.get("std") or m.get("full") or 1.0
    return out


def _monday_proj(leg2chart, scoring="half"):
    """Monday per-game projections by canonical pid.

    The legs are keyed by canonical identity upstream (one record per human),
    so this is now a straight read with a registry-based alias safety net
    for any stray variant key.

    Returns (proj, stale): proj maps pid -> per-game projection; stale is the
    set of pids whose leg record carries NO new Week-N evidence (form_pg is
    None and no news adjustment) -- their projection is just the preseason
    baseline carried forward. Callers must not manufacture a value move from
    repricing a stale baseline through a different model; change-not-level
    means no surprise -> no delta.
    """
    import sys
    leg = _load_leg(scoring)
    by_canon = {}
    for k, r in leg.items():
        ck = leg2chart.get(k, k)
        pg = (r or {}).get("proj_pg")
        if pg is None:
            continue
        note = (r or {}).get("note") or ""
        fresh = ("carries the preseason baseline" not in note
                 and "no expected-points read" not in note)
        exact = (k == ck)
        cand = (float(pg), fresh, exact, k)
        prev = by_canon.get(ck)
        # Prefer fresh (Week 1-informed), then exact chart-key match.
        if prev is None or (cand[1], cand[2]) > (prev[1], prev[2]):
            by_canon[ck] = cand
    for ck, cand in sorted(by_canon.items()):
        if cand[3] != ck:
            print(f"  alias-resolve {ck}: picked '{cand[3]}' "
                  f"(proj={cand[0]}, fresh={cand[1]})", file=sys.stderr)
    proj = {ck: cand[0] for ck, cand in by_canon.items()}
    stale = set()
    for k, r in leg.items():
        ck = leg2chart.get(k, k)
        if ck not in proj:
            continue
        dbg = (r or {}).get("debug") or {}
        if dbg.get("form_pg") is None and not dbg.get("news_id"):
            stale.add(ck)
    # A pid is only stale if EVERY leg record for it lacks new evidence --
    # a fresh record for the same human wins over a stale variant.
    fresh_pids = set()
    for k, r in leg.items():
        ck = leg2chart.get(k, k)
        dbg = (r or {}).get("debug") or {}
        if not (dbg.get("form_pg") is None and not dbg.get("news_id")):
            fresh_pids.add(ck)
    stale -= fresh_pids
    return proj, stale


def _frozen_chart():
    chart = _load_chart()
    frozen = {}
    for p in chart:
        if p.get("pos") not in ("QB", "RB", "WR", "TE"):
            continue
        k = norm_name(p["name"])
        b = (p.get("blend_ppg") or {}).get("half_ppr")
        frozen[(k, p["pos"])] = float(b) if b is not None else None
    return frozen


def _state_for(teams, slots, bench):
    # Bench mix mirrors the chart's two-tier calibration pools
    # (starter_model.DEFAULT_STATE, workbook-aligned 2026-09-22): the waiver
    # boundary must fill the SAME rostered sets the chart prices, or adds /
    # drops desync from chart values. QB/TE are 10-deep (not 6): the 15/85
    # calibration requires it.
    from starter_model import DEFAULT_STATE as _DS
    _base = _DS["bench_mix"]
    _base_total = sum(_base.values())
    total = teams * bench
    bm = {p: max(1, round(total * _base[p] / _base_total)) for p in _base}
    return {"teams": teams, "slots": slots, "bench": bench,
            "bench_mix": bm,
            "flex_types": [{"count": slots.get("FLEX", 0),
                            "eligible": ["RB", "WR", "TE"]}]}


# Waiver scoring keys -> ESPN pie scoring keys.
_PIE_SKEY = {"half": "half_ppr", "std": "standard", "full": "ppr"}


def price_vector(scoring="half", teams=12, slots=None, bench=6):
    """Return {pid: {"old": int, "new": int}} for the vector.

    old = frozen chart-side value, upside ON (chart base + lottery edge).
    new = Monday value under the vector (base x news-mult + edge), floored at 0.
    Unpriced players (no Monday projection) are omitted, never mapped to 0.
    """
    from starter_model import trade_values_pinned, trade_values, load_pies
    slots = slots or dict(DEFAULT_SLOTS)
    pool, leg2chart = canonical_pool()
    edge = _edge_map()
    mult = _mult_map(leg2chart)
    mproj, stale = _monday_proj(leg2chart, scoring)
    frozen = _frozen_chart()
    st = _state_for(teams, slots, bench)
    pies = load_pies(_PIE_SKEY[scoring], teams)
    monday_proj = {(k, v["pos"]): mproj.get(k) for k, v in pool.items()}
    new_base, _ = trade_values_pinned(monday_proj, frozen, st, pies=pies)
    old_base, _ = trade_values(frozen, st, pies=pies)
    chart_keys = {norm_name(p["name"]) for p in _load_chart()}
    out = {}
    for k, v in pool.items():
        key = (k, v["pos"])
        pg = mproj.get(k)
        if pg is None:
            continue  # unpriced: skipped, never mapped to 0
        if k in chart_keys:
            old = old_base.get(key, 0) + edge.get(k, 0)
            if k in stale:
                # No new Week-N evidence: change-not-level. Carrying the
                # chart value unchanged -- repricing the same preseason
                # baseline through the Monday model manufactures fake moves
                # (e.g. Stribling 1->7 with no Week 1 line).
                new = old
            else:
                new = max(0, round(new_base.get(key, 0) * mult.get(k, 1.0))) + edge.get(k, 0)
        else:
            # Leg-only players were not on the chart last week: effectively 0.
            new = max(0, round(new_base.get(key, 0) * mult.get(k, 1.0))) + edge.get(k, 0)
            old = 0
        out[k] = {"old": old, "new": new}
    return out, pool


def _espn_roster(chart_keys):
    """ESPN roster% keyed by canonical pid. ESPN's own suffix variants
    ("Aaron Jones Sr.") resolve through the identity registry, so no
    suffix-strip fallback is needed at lookup time."""
    sys.path.insert(0, str(LOT / "engine"))
    import espn_roster
    ident = IdentityMap(chart_keys=set(chart_keys))
    lk = espn_roster.build_lookup(date_tag=espn_roster.latest_tag())
    out = {}
    for k, v in lk.items():
        ck = ident.canon(norm_name(k))
        out[ck] = round(float(v), 1)
    # Pool pids are chart-canonical keys ('cam ward'); the registry may
    # canonicalize to another spelling ('cameron ward'). Bridge the gap so
    # roster% still attaches to the merged human (2026-09-19: without this,
    # the alias fix orphaned ESPN roster% and availability failed open).
    for pid in chart_keys:
        if pid not in out:
            c = ident.canon(pid)
            if c in out:
                out[pid] = out[c]
    return out


def boundary(teams=12, slots=None, bench=6, scoring="half",
             add_to_wire=(), remove_from_wire=()):
    """Compute the finite-capacity boundary for a settings vector.

    O/M are the chart's own exact rostered sets (starter_model.build_model),
    ranked on continuous projections -- no integer-value ties, no padding.
    Returns dict with: capacity, available, O, M, entrants, displaced, adds,
    drops, displaced_upside, holds, hold_steady, excluded_risers, gated_out,
    unpriced, trending_pickups, trending {pid: adds}, values {pid: {old, new}},
    roster {pid: pct}.
    adds/drops/holds are pid lists ranked by new desc (pid tiebreak).
    """
    from starter_model import build_model, load_pies
    slots = slots or dict(DEFAULT_SLOTS)
    values, pool = price_vector(scoring, teams, slots, bench)
    _pool2, leg2chart = canonical_pool()
    mproj, _stale = _monday_proj(leg2chart, scoring)
    frozen = _frozen_chart()
    st = _state_for(teams, slots, bench)
    pies = load_pies(_PIE_SKEY[scoring], teams)
    cap = teams * (sum(slots.values()) + bench)

    # Complete-pool projections for the rostered sets. Unpriced players
    # (no Monday projection) are excluded from both sets and reported.
    old_proj, new_proj, unpriced = {}, {}, []
    for k, v in pool.items():
        mp = mproj.get(k)
        if mp is None:
            unpriced.append(k)
            continue
        key = (k, v["pos"])
        new_proj[key] = mp
        fp = frozen.get(key)  # None for leg-only players: not on the chart
        if fp is not None:
            old_proj[key] = fp
    Oset = {pid[0] for pid in build_model(old_proj, st, pies=pies)["rostered"]}
    Mset = {pid[0] for pid in build_model(new_proj, st, pies=pies)["rostered"]}
    assert len(Oset) == cap, f"O size {len(Oset)} != capacity {cap}"
    assert len(Mset) == cap, f"M size {len(Mset)} != capacity {cap}"

    entrants = sorted(Mset - Oset, key=lambda p: (-values[p]["new"], p))
    displaced = sorted(Oset - Mset, key=lambda p: (-values[p]["old"], p))
    if len(entrants) != len(displaced):
        raise AssertionError(
            f"boundary parity broken: {len(entrants)} entrants vs "
            f"{len(displaced)} displaced (teams={teams} bench={bench})")

    roster = _espn_roster(pool.keys())
    # Sleeper trending adds since Sunday: the community's pickup signal.
    # (Same file the dashboard's hype section reads.) Newest dated file
    # wins — never a hardcoded date (stale-file class, fixed 2026-09-18).
    trending = {}
    try:
        _trend_files = sorted(
            p for p in (LOT / "data").glob("sleeper_trending_*.json")
            if re.search(r"sleeper_trending_\d{4}-\d{2}-\d{2}\.json$", p.name))
        _hp = json.loads(_trend_files[-1].read_text())
        for _k, _vv in _hp.items():
            _pid = norm_name(_k)
            if _pid in pool:
                trending[_pid] = (_vv or [0])[0]
    except FileNotFoundError:
        pass
    add_set = {norm_name(n) for n in add_to_wire}
    rem_set = {norm_name(n) for n in remove_from_wire}

    def available(pid):
        if pid in rem_set:
            return False
        if pid in add_set:
            return True
        r = roster.get(pid)
        if r is None:
            return True  # no signal: fail open on availability, value decides
        new = values[pid]["new"]
        gate = 50.0 if new >= 10 else 70.0
        return r < gate

    avail = [pid for pid in values if available(pid)]
    availset = set(avail)

    # Sections per the user's taxonomy (2026-09-15, refined 2026-09-16).
    # - Hot pickups: the most-added players since Sunday (>=15k Sleeper adds,
    #   available, priced, not holds/drops), ranked by add count. Each gets
    #   a verdict: ADD (entrant or real value new>=4 - the value layer agrees)
    #   or PASS (fringe/zero value - don't chase the hype).
    # - Adds ("Other pickups we like"): available entrants NOT already on the
    #   hot list - the data's under-the-radar finds. Ranked by highest updated
    #   value. Never a 0->0.
    # - Drops: genuinely displaced AND moved to 0 (old>0). Never a 0->0.
    # - Holds: fell from >=10 to 1-9 (zero is reserved for Drops); plus
    #   displaced players who kept positive value. No roster% filter: a hold
    #   is advice about your own roster, and even a 95%-rostered player in
    #   decline deserves the explicit "don't panic". Ranked by highest
    #   updated value.
    inboth = Oset & Mset
    riser_pids = {p for p in inboth
                  if values[p]["old"] <= 2 and values[p]["new"] >= 5}
    risers = sorted([p for p in riser_pids if p in availset],
                    key=lambda p: (-values[p]["new"], p))
    # "Other pickups we like": available entrants; narrowed below to exclude
    # anyone already on the hot-pickups list (no duplication).
    adds = sorted({p for p in entrants
                   if p in availset and values[p]["new"] > 0},
                  key=lambda p: (-values[p]["new"], p))
    drops = sorted([p for p in displaced
                    if values[p]["new"] == 0 and values[p]["old"] > 0],
                   key=lambda p: (-values[p]["old"], p))
    displaced_upside = [p for p in displaced if values[p]["new"] > 0]
    holds = sorted(
        [p for p in inboth
         if values[p]["old"] >= 10 and 0 < values[p]["new"] < 10]
        + displaced_upside,
        key=lambda p: (-values[p]["new"], p))
    # Hot pickups (2026-09-16): the community's most-added players since
    # Sunday. Available, priced, not holds/drops. Ranked by add count.
    # Verdicts (builder): ADD = entrant or new>=4; PASS = fringe/zero.
    # Adds is narrowed to entrants off the hot list (no duplication).
    HOT_PICKUP_FLOOR = 15000
    HOT_PICKUP_N = 15
    hot_pickups = sorted(
        [p for p in values
         if trending.get(p, 0) >= HOT_PICKUP_FLOOR and p in availset
         and p not in holds and p not in drops],
        key=lambda p: (-trending[p], p))[:HOT_PICKUP_N]
    hot_set = set(hot_pickups)
    adds = sorted(set(adds) - hot_set,
                  key=lambda p: (-values[p]["new"], p))
    # In-both risers that didn't make Adds (gated out by roster%): kept for
    # the audit/dashboard, never rendered as adds.
    excluded_risers = sorted(riser_pids - set(adds),
                             key=lambda p: (-values[p]["new"], p))
    # Hold-steady: in-both, still positive, not a hold and not a mover
    # section. "Didn't move, but should be rostered": already on the board -
    # check whether they're free in your league. Available players, plus big
    # value jumps (delta >= 5) under 90% rostered (awareness, not
    # wire-checks). Ranked by highest updated value.
    hold_steady = sorted(
        [p for p in inboth
         if values[p]["new"] > 0 and p not in holds and p not in adds
         and p not in hot_set
         and (p in availset
              or (values[p]["new"] - values[p]["old"] >= 5
                  and (roster.get(p) or 0) < 90))],
        key=lambda p: (-values[p]["new"], p))
    gated_out = sorted([p for p in values
                        if p not in availset and p not in rem_set],
                       key=lambda p: (-values[p]["new"], p))
    return {"capacity": cap, "teams": teams, "bench": bench, "slots": dict(slots),
            "scoring": scoring, "available": avail, "O": sorted(Oset),
            "M": sorted(Mset), "entrants": entrants, "displaced": displaced,
            "adds": adds, "risers": risers, "drops": drops,
            "displaced_upside": displaced_upside, "holds": holds,
            "excluded_risers": excluded_risers, "gated_out": gated_out,
            "hold_steady": hold_steady, "hot_pickups": hot_pickups,
            "trending": trending,
            "unpriced": sorted(unpriced), "values": values, "pool": pool,
            "roster": roster}


def visible_sections(bnd):
    """Visible add/drop pids under the true rostered-set boundary (2026-09-15).

    Hot pickups = most-added since Sunday (available, priced, not holds/drops).
    Adds = available entrants NOT on the hot list ("other pickups we like").
    Drops = displaced incumbents whose Monday value moved to 0
    (the user's taxonomy). Boundary parity (|entrants| == |displaced|) and
    the taxonomy invariants are enforced by boundary(); this function
    re-checks them at render time so a data-shape change can never silently
    emit a dishonest board. Visible adds and drops need not be equal.
    Fail-closed: any deviation raises.
    """
    v = bnd["values"]
    if len(bnd["entrants"]) != len(bnd["displaced"]):
        raise AssertionError(
            f"boundary parity broken: {len(bnd['entrants'])} entrants vs "
            f"{len(bnd['displaced'])} displaced "
            f"(teams={bnd['teams']} bench={bnd['bench']})")
    for p in bnd["drops"]:
        if v[p]["new"] != 0:
            raise AssertionError(f"drop {p} did not move to 0")
        if v[p]["old"] <= 0:
            raise AssertionError(f"drop {p} never held a roster spot")
        if p not in bnd["displaced"]:
            raise AssertionError(f"drop {p} was not genuinely displaced")
    for p in bnd["adds"]:
        if v[p]["new"] <= 0:
            raise AssertionError(f"add {p} has no positive Monday value")
    for p in bnd["holds"]:
        if not isinstance(v[p]["new"], int) or v[p]["new"] <= 0:
            raise AssertionError(f"hold {p} has no positive Monday value")
    for p in bnd["hold_steady"]:
        if v[p]["new"] <= 0:
            raise AssertionError(f"hold_steady {p} has no positive Monday value")
        if p in bnd["holds"] or p in bnd["adds"] or p in bnd["drops"]:
            raise AssertionError(f"hold_steady {p} is also in a mover section")
    return list(bnd["adds"]), list(bnd["drops"])


if __name__ == "__main__":
    import sys
    teams = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    bench = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    b = boundary(teams=teams, bench=bench)
    v = b["values"]
    print(f"pool={len(b['pool'])} priced={len(v)} avail={len(b['available'])} "
          f"cap={b['capacity']} |O|={len(b['O'])} |M|={len(b['M'])} "
          f"unpriced={len(b['unpriced'])}")
    print(f"entrants={len(b['entrants'])} displaced={len(b['displaced'])} "
          f"adds={len(b['adds'])} drops={len(b['drops'])} "
          f"displaced_upside={len(b['displaced_upside'])} holds={len(b['holds'])} "
          f"hold_steady={len(b['hold_steady'])} "
          f"excluded_risers={len(b['excluded_risers'])} gated={len(b['gated_out'])}")
    for pid in b["adds"]:
        tag = "RISR" if pid in b["risers"] else "ADD "
        print(f"  {tag} {b['pool'][pid]['name']} ({b['pool'][pid]['pos']}) "
              f"{v[pid]['old']}->{v[pid]['new']} roster={b['roster'].get(pid)}")
    for pid in b["drops"]:
        print(f"  DROP {b['pool'][pid]['name']} ({b['pool'][pid]['pos']}) "
              f"{v[pid]['old']}->{v[pid]['new']} roster={b['roster'].get(pid)}")
    for pid in b["holds"]:
        print(f"  HOLD {b['pool'][pid]['name']} ({b['pool'][pid]['pos']}) "
              f"{v[pid]['old']}->{v[pid]['new']} roster={b['roster'].get(pid)}")
    for pid in b["excluded_risers"]:
        print(f"  XRSR {b['pool'][pid]['name']} ({b['pool'][pid]['pos']}) "
              f"{v[pid]['old']}->{v[pid]['new']} roster={b['roster'].get(pid)}")
