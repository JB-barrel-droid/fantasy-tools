#!/usr/bin/env python3
"""Build the DDF two-tier value-above-waivers leg from ESPN projections.

Stage 2 of the repo pipeline: ESPN projections -> DDF two-tier leg ->
versioned adjustment inputs (pipelines/build_adjustment_inputs.py).

This is a pure-Python port of the browser's TwoTier calibration in
app/trade-value-chart/assets/curve-widget.js (itself a port of
lottery/bin/starter_model.py, the reference implementation). The port is
verified bit-exact against the JS harness in tests/test_ddf_two_tier_leg.py
(pinned vectors + the real ESPN inputs, 1e-9 tolerance).

Locked decisions (Jeremy, 2026-09-21/22):
  - ESPN-purity: every number labeled ESPN comes from ESPN projections only.
    Per-game projections are the CSV's ROS components rescored per scoring
    (arithmetic on ESPN components only -- never expert blending), divided
    by the games the player's team plays inside ESPN's ROS window
    (weeks_covered, minus the bye when it falls inside;
    pipelines/lib/games_remaining.py, shared with bake_players.py so the
    browser's espn_ppg and this leg use the same count). Until 2026-10-08
    this was a flat 16 (weeks 3-18), stale from week 5 on.
  - Positional pies: ESPN-measured pools (lottery/bin/espn_pies.json),
    vintage-recorded. Never guessed.
  - bench_share: 0.15 default (the UI parameter; the leg is built at the
    recommended share).
  - Glide width tau = 25% of (starter line - waiver line) per position.
  - normalize-then-round: full precision through calibration; ONE 70/max
    multiplier applied before any rounding; rounding is display-only and
    never enters this artifact. The 85/15 pie identity is verified
    pre-rounding (bench_raw == 0.15*pie, starter_raw == 0.85*pie).
  - Fail closed: an infeasible calibration at the active share, a
    non-positive pie, a position with no surplus, or an unresolvable
    identity publishes NO leg. Missing values stay absent (review rows),
    never zero-filled or guessed.

Identity: numeric player_key via the fixture's player_keys map
(source-id -> canonical key). Four CSV spellings are verified aliases of
canonical chart names (2026-09-19 waiver investigation, confirmed against
Supabase players.full_name 2026-09-22): c Cameron Ward (697),
'cameron skattebo' -> 'cam skattebo' (3664), 'travis etienne jr' ->
'travis etienne' (810), 'michael pittman jr' -> 'michael pittman' (561).
Generational suffixes, punctuation and first-name nicknames are matched
through the repo's single normalization rule (lib/canonical_players.
norm_player_name) by FixtureIdentity below: 'kenneth walker' (CBS ROS,
Razzball) and 'kenneth walker iii' (fixture slug) are the same player_key.
A normalized form that maps to more than one player_key (after the
position filter) is ambiguous and excluded, never guessed.
Anything else unresolvable is excluded to review_rows, never guessed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "inputs" / "espn_projections.csv"
DEFAULT_PIES = ROOT / "data" / "inputs" / "espn_pies.json"
DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ddf-two-tier"

SCHEMA = "trade-value-ddf-leg-v1"

# Roster config from shared config/roster.json — never hardcode.
def _load_roster_config():
    import json
    cfg = Path(__file__).resolve().parent.parent / "config" / "roster.json"
    try:
        return json.load(open(cfg))
    except (OSError, json.JSONDecodeError):
        return {"positions": ["QB", "RB", "WR", "TE"], "bench_share": 0.15}
_ROSTER_CFG = _load_roster_config()
POSITIONS = _ROSTER_CFG["positions"]
DEFAULT_BENCH_SHARE = _ROSTER_CFG["bench_share"]
GLIDE_WIDTH_FRAC = 0.25
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from games_remaining import (  # noqa: E402
    load_byes, window_from_rows, games_in_window, BYES_PATH,
)
from canonical_players import norm_player_name  # noqa: E402 -- the single normalization rule

# Reference league shape (mirrors the widget's TwoTier constants exactly).
REF_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
REF_FLEX_COUNT = 1
REF_FLEX_ELIGIBLE = ["RB", "WR", "TE"]
BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}

# Backward-compatible alias for the pre-rename constant name.
REF_BENCH_SLOTS = BENCH_MIX_12

# Verified spelling aliases: csv player_norm -> fixture player_keys id.
# (Same humans; verified 2026-09-19, re-confirmed vs players.full_name.)
ALIASES = {
    "cameron ward": "cam ward",
    "cameron skattebo": "cam skattebo",
    "travis etienne jr": "travis etienne",
    "michael pittman jr": "michael pittman",
    # FantasyPros Week 5 chart spells him "Kenny Gainwell"; players table has a
    # single "Kenneth Gainwell" (player_key 785, RB), verified 2026-10-07.
    "kenny gainwell": "kenneth gainwell",
    # Razzball ROS spellings (2026-10-06 save review rows). Each target is the
    # only public.players row of that surname at that position (exact
    # full_name check, read-only, 2026-10-08) and is the fixture slug:
    # Josh Palmer 822 WR, Andrew Ogletree 920 TE, Chig Okonkwo 4247 TE,
    # Mitchell Trubisky 4214 QB. No Joshua Palmer / Drew Ogletree /
    # Chigoziem Okonkwo / Mitch Trubisky row exists.
    "joshua palmer": "josh palmer",
    "drew ogletree": "andrew ogletree",
    "chigoziem okonkwo": "chig okonkwo",
    "mitch trubisky": "mitchell trubisky",
}


# A trailing generational suffix on a source spelling: the spelling itself
# names the suffixed player, so it may break a tie between same-name keys.
_GENERATIONAL_SUFFIX = re.compile(r"\s(jr|sr|ii|iii|iv|v)\.?$")


class FixtureIdentity:
    """Resolve a source's normalized name to the fixture's numeric player_key.

    The fixture's player_keys slugs do not follow one suffix convention
    ('kenneth walker iii' keeps it, 'travis etienne' drops it), and sources
    differ too (CBS ROS and Razzball strip suffixes, ESPN keeps them). An
    exact slug lookup therefore dropped every suffixed player whose source
    and slug disagreed (GAP-CBSROS-LIVE-POOL), while bake_players.py, which
    feeds the browser, resolves through norm_player_name and priced them.

    Order: verified ALIASES, then the exact slug, then the slug's
    norm_player_name form (suffixes, punctuation and nicknames removed).
    Fail-closed: when the normalized form maps to more than one player_key
    in the row's position (or in any position when the fixture has no
    position for a key), the row is ambiguous and excluded -- unless the
    source spelling itself carries the suffix and hits a slug exactly.
    resolve() returns (player_key | None, how, alias) with how one of
    exact | alias | normalized | ambiguous | unresolved.
    """

    def __init__(self, player_keys: dict[str, Any], key_pos: dict[int, str] | None = None):
        self.player_keys = {slug: key for slug, key in player_keys.items() if isinstance(key, int)}
        self.key_pos = dict(key_pos or {})
        self.by_norm: dict[str, set[int]] = {}
        self.slug_by_key: dict[int, str] = {}
        for slug, key in self.player_keys.items():
            self.by_norm.setdefault(norm_player_name(slug), set()).add(key)
            self.slug_by_key.setdefault(key, slug)

    @classmethod
    def from_fixture(cls, fixture_path: Path) -> "FixtureIdentity":
        fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        key_pos: dict[int, str] = {}
        players_path = Path(fixture_path).with_name("players.json")
        if players_path.exists():
            for p in json.loads(players_path.read_text(encoding="utf-8")).get("players", []):
                if isinstance(p.get("player_key"), int) and p.get("pos"):
                    key_pos[p["player_key"]] = str(p["pos"]).upper()
        return cls(fixture.get("player_keys") or {}, key_pos)

    def slug_for(self, key: int) -> str:
        """The fixture slug for a resolved key: what sections and leg checks join on."""
        return self.slug_by_key[key]

    def candidates(self, name: str, pos: str | None = None) -> set[int]:
        keys = self.by_norm.get(norm_player_name(name), set())
        if pos:
            keys = {k for k in keys if self.key_pos.get(k) in (None, pos.upper())}
        return keys

    def ambiguous_forms(self) -> dict[str, list[int]]:
        """Normalized forms shared by more than one player_key in one position."""
        out: dict[str, list[int]] = {}
        for form, keys in self.by_norm.items():
            by_pos: dict[str | None, list[int]] = {}
            for k in keys:
                by_pos.setdefault(self.key_pos.get(k), []).append(k)
            clash = [k for p, ks in by_pos.items() for k in ks
                     if len(ks) > 1 or (p is None and len(keys) > 1)]
            if clash:
                out[form] = sorted(clash)
        return out

    def resolve(self, norm: str, pos: str | None = None) -> tuple[int | None, str, str | None]:
        alias = ALIASES.get(norm)
        target = alias or norm
        exact = self.player_keys.get(target)
        cands = self.candidates(target, pos)
        if len(cands) > 1:
            if exact in cands and _GENERATIONAL_SUFFIX.search(target):
                return exact, ("alias" if alias else "exact"), alias
            return None, "ambiguous", alias
        if exact is not None and (not cands or exact in cands):
            return exact, ("alias" if alias else "exact"), alias
        if len(cands) == 1:
            return next(iter(cands)), ("alias" if alias else "normalized"), alias
        return None, "unresolved", alias


def drop_duplicate_keys(resolved: dict[str, list[dict[str, Any]]],
                        review: list[dict[str, Any]], name_field: str) -> None:
    """Fail closed when two source rows resolve to one player_key.

    Normalization can map two spellings ('x jr', 'x') onto one key; which
    row's projection is right is unknown, so neither is priced.
    """
    counts: dict[int, int] = {}
    for rows in resolved.values():
        for d in rows:
            counts[d["player_key"]] = counts.get(d["player_key"], 0) + 1
    dupes = {k for k, n in counts.items() if n > 1}
    if not dupes:
        return
    for pos, rows in resolved.items():
        keep = []
        for d in rows:
            if d["player_key"] in dupes:
                review.append({"reason": "duplicate_identity", "player": d.get(name_field),
                               "player_key": d["player_key"], "pos": pos})
            else:
                keep.append(d)
        resolved[pos] = keep


def identity_review_row(how: str, player: Any, norm: str, pos: str) -> dict[str, Any]:
    reason = "ambiguous_identity" if how == "ambiguous" else "unresolved_identity"
    return {"reason": reason, "player": player, "player_norm": norm, "pos": pos}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Two-tier math: exact port of the widget's TwoTier helpers.
# ---------------------------------------------------------------------------

def softplus(z: float) -> float:
    return math.log1p(math.exp(-abs(z))) + (z if z > 0 else 0.0)


def slice_exposures(x: float, rw: float, rs: float, tau: float) -> tuple[float, float]:
    if not (x > rw):
        return (0.0, 0.0)
    glide = tau * (softplus((x - rs) / tau) - softplus((rw - rs) / tau))
    return ((x - rw) - glide, glide)


def check_share(share: Any, pos: str = "?") -> float:
    s = float(share)
    if not math.isfinite(s) or not (s > 0 and s < 1):
        raise ValueError(f"cannot calibrate {pos}: bench share {share!r} is not between 0 and 1 (exclusive)")
    return s


def solve_tier_prices(a_bench: float, b_bench: float, a_start: float, b_start: float,
                      pie: float, pos: str = "?", bench_share: float = DEFAULT_BENCH_SHARE) -> tuple[float, float]:
    share = check_share(bench_share, pos)
    starter_share = 1.0 - share
    if not (pie > 0):
        raise ValueError(f"cannot calibrate {pos}: non-positive pie {pie!r}")
    det = a_bench * b_start - a_start * b_bench
    if det == 0:
        raise ValueError(f"cannot calibrate {pos}: degenerate slice exposures")
    pb = (share * pie * b_start - b_bench * starter_share * pie) / det
    ps = (a_bench * starter_share * pie - share * pie * a_start) / det
    if not (pb > 0):
        raise ValueError(f"cannot calibrate {pos} at bench share {share}: bench rate {pb} not positive")
    if not (ps > pb):
        raise ValueError(
            f"cannot calibrate {pos} at bench share {share}: starter rate {ps} does not exceed "
            f"bench rate {pb} -- the economics break (bench slices would pay more than starter slices)")
    tol = 1e-9 * pie
    if abs(pb * a_bench + ps * b_bench - share * pie) > tol or \
       abs(pb * a_start + ps * b_start - starter_share * pie) > tol:
        raise ValueError(f"cannot calibrate {pos} at bench share {share}: solved rates miss the split")
    return pb, ps


def bench_mix_for_teams(teams: int) -> dict[str, int]:
    # Round-half-up (matches the widget; Python round() would banker's-round).
    return {pos: int(math.floor(BENCH_MIX_12[pos] * teams / 12 + 0.5)) for pos in POSITIONS}


# NOTE: bench_mix_for (6-arg) was removed; use bench_mix_for_teams(teams).


def build_position_tiers(lists: dict[str, list[dict[str, Any]]], teams: int,
                         slots: dict[str, int], flex_count: int,
                         flex_eligible: list[str], bench_mix: dict[str, int],
                         positions: list[str] | None = None) -> dict[str, Any]:
    # positions defaults to the module POSITIONS (skill slots). Callers for
    # other position sets (e.g. the K/DST leg, JEG-211) pass their own list;
    # the tier economics are identical, only the iterated positions change.
    # Existing callers see byte-identical behavior (default None -> POSITIONS).
    _positions = POSITIONS if positions is None else positions
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for pos in _positions:
        rows = [{"id": d["id"], "x": d["x"]} for d in lists.get(pos, [])
                if isinstance(d.get("x"), float) and math.isfinite(d["x"])]
        rows.sort(key=lambda d: (-d["x"], d["id"]))
        by_pos[pos] = rows
    dedicated: set[str] = set()
    starters: set[str] = set()
    for pos in _positions:
        for d in by_pos[pos][: teams * slots.get(pos, 0)]:
            dedicated.add(d["id"])
            starters.add(d["id"])
    flex_pool: list[dict[str, Any]] = []
    for pos in _positions:
        if pos not in flex_eligible:
            continue
        for d in by_pos[pos]:
            if d["id"] not in dedicated:
                flex_pool.append(d)
    flex_pool.sort(key=lambda d: (-d["x"], d["id"]))
    for d in flex_pool[: teams * flex_count]:
        starters.add(d["id"])
    rostered = set(starters)
    bench: set[str] = set()
    for pos in _positions:
        for d in [d for d in by_pos[pos] if d["id"] not in rostered][: bench_mix.get(pos, 0)]:
            rostered.add(d["id"])
            bench.add(d["id"])
    tiers: dict[str, Any] = {}
    for pos in _positions:
        lst = by_pos[pos]
        if not lst:
            tiers[pos] = None
            continue
        nxt = next((d for d in lst if d["id"] not in rostered), None)
        rw = nxt["x"] if nxt else 0.0
        s_projs = [d["x"] for d in lst if d["id"] in starters]
        b_projs = [d["x"] for d in lst if d["id"] not in starters]
        if not s_projs:
            rs = lst[0]["x"] + 1
        elif not b_projs:
            rs = lst[-1]["x"] - 1
        else:
            rs = (min(s_projs) + max(b_projs)) / 2
        if not (rs > rw):
            raise ValueError(f"buildPositionTiers: starter line {rs} must exceed waiver line {rw} at {pos}")
        tau = GLIDE_WIDTH_FRAC * (rs - rw)
        a_bench = b_bench = a_start = b_start = surplus = 0.0
        for d in lst:
            if not (d["x"] > rw):
                continue
            surplus += d["x"] - rw
            a, b = slice_exposures(d["x"], rw, rs, tau)
            if d["id"] in starters:
                a_start += a
                b_start += b
            else:
                a_bench += a
                b_bench += b
        tiers[pos] = {"rw": rw, "rs": rs, "tau": tau, "a_bench": a_bench,
                      "b_bench": b_bench, "a_start": a_start, "b_start": b_start,
                      "surplus": surplus}
    return {"tiers": tiers, "starters": starters, "bench": bench, "rostered": rostered}


def calibrate_position(tier: dict[str, Any] | None, pie: float,
                       bench_share: float = DEFAULT_BENCH_SHARE) -> dict[str, Any]:
    if tier is None:
        raise ValueError("cannot calibrate: missing tier (no players at this position)")
    if not (tier["surplus"] > 0):
        raise ValueError("cannot calibrate: position has no above-waiver surplus")
    if not (pie > 0):
        raise ValueError(f"cannot calibrate: non-positive pie {pie!r}")
    pb, ps = solve_tier_prices(tier["a_bench"], tier["b_bench"], tier["a_start"],
                               tier["b_start"], pie, "?", bench_share)
    return {**tier, "pb": pb, "ps": ps, "pie_used": pie, "bench_share_used": bench_share,
            "bench_raw": pb * tier["a_bench"] + ps * tier["b_bench"],
            "starter_raw": pb * tier["a_start"] + ps * tier["b_start"]}


def price_for_projection(x: float, cal: dict[str, Any]) -> float:
    if not (x > cal["rw"]):
        return 0.0
    a, b = slice_exposures(x, cal["rw"], cal["rs"], cal["tau"])
    return cal["pb"] * a + cal["ps"] * b


# ---------------------------------------------------------------------------
# ESPN input: ROS components -> per-game, rescored per scoring.
# ---------------------------------------------------------------------------

def parse_float(raw: Any) -> float | None:
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def load_espn_lists(csv_path: Path, scoring: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], list[dict[str, Any]]]:
    """Return (lists, input_meta, review_rows).

    lists: {pos: [{id: player_norm, name, team, x: per-game}]}.
    Per-game = ROS components rescored per scoring / the team's games in
    ESPN's ROS window (pipelines/lib/games_remaining.py). A row with no team
    (free agent) divides by the window length: ESPN projects every week.
    Rescoring is arithmetic on ESPN components only (reception points are
    the only scoring difference): ppr = half_ppr + 0.5*receptions,
    standard = half_ppr - 0.5*receptions. ESPN-pure by construction.
    """
    if scoring not in ("standard", "half_ppr", "ppr"):
        raise SystemExit(f"Unknown scoring '{scoring}'")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    dates = {r.get("espn_snapshot_date") for r in raw_rows if r.get("espn_snapshot_date")}
    if len(dates) != 1:
        raise SystemExit(
            f"Fail closed: ESPN content vintage undeterminable "
            f"(espn_snapshot_date values: {sorted(dates)[:5]}).")
    vintage = next(iter(dates))
    window = window_from_rows(raw_rows)
    byes, _ = load_byes()
    window_len = window[1] - window[0] + 1
    lists: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
    review_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        name = str(row.get("player") or "").strip()
        norm = str(row.get("player_norm") or "").strip()
        pos = str(row.get("pos") or "").strip()
        projected = str(row.get("has_espn_projection") or "").strip().lower() in ("true", "1", "yes")
        if not name or not projected:
            review_rows.append({"reason": "no_espn_projection", "player": name or None})
            continue
        # NOTE: the row's "eligible" flag intentionally does NOT gate pricing.
        # Ineligible (out/IR) players with a real ESPN row carry an explicit
        # zero, not missing data -- same rule as save_espn_cbs_references.py.
        # Their zeroed components flow through and price at 0.0; sending them
        # to review would silently drop a legitimate zero (e.g. De'Von Achane).
        if pos not in POSITIONS:
            review_rows.append({"reason": "non_skill_position", "player": name, "pos": pos})
            continue
        ros_half = parse_float(row.get("ros_half_ppr"))
        receptions = parse_float(row.get("r_receptions"))
        if ros_half is None or receptions is None:
            review_rows.append({"reason": "missing_components", "player": name})
            continue
        if scoring == "ppr":
            ros = ros_half + 0.5 * receptions
        elif scoring == "standard":
            ros = ros_half - 0.5 * receptions
        else:
            ros = ros_half
        team = str(row.get("team") or "").strip() or None
        games = games_in_window(team, window, byes) if team else window_len
        if not games:
            review_rows.append({"reason": "unknown_team", "player": name, "team": team})
            continue
        lists[pos].append({
            "id": norm,
            "name": name,
            "team": team,
            "games": games,
            "x": ros / games,
        })
    meta = {"espn_snapshot_date": vintage, "csv_rows": len(raw_rows),
            "ros_weeks": f"{window[0]}-{window[1]}"}
    return lists, meta, review_rows


def load_pies(pies_path: Path, scoring: str, teams: int) -> tuple[dict[str, float], dict[str, Any]]:
    data = json.loads(pies_path.read_text(encoding="utf-8"))
    try:
        pies_raw = data["pies"][scoring][str(teams)]
    except KeyError:
        raise SystemExit(
            f"Fail closed: no ESPN-measured pies for scoring={scoring} teams={teams} "
            f"in {pies_path}. A guessed pie would silently re-weight every position.")
    pies = {pos: float(pies_raw[pos]) for pos in POSITIONS if pos in pies_raw}
    missing = [pos for pos in POSITIONS if pos not in pies]
    if missing:
        raise SystemExit(f"Fail closed: pies missing positions {missing} in {pies_path}")
    if any(not (v > 0) for v in pies.values()):
        raise SystemExit(f"Fail closed: non-positive pie in {pies_path}: {pies}")
    meta = {
        "pies_file": str(pies_path),
        "pies_sha256": sha256_file(pies_path),
        "pies_vintage": (data.get("meta") or {}).get("vintage", {}).get("skill", {}).get("espn_snapshot_date"),
        "pies_method": (data.get("meta") or {}).get("method"),
    }
    return pies, meta


def resolve_identities(lists: dict[str, list[dict[str, Any]]],
                       fixture_path: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach canonical player_key to every leg row.

    Join: csv player_norm -> fixture player_keys (with the verified alias
    map). Unresolvable norms are excluded to review_rows, never guessed.
    """
    ident = FixtureIdentity.from_fixture(fixture_path)
    resolved: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
    review: list[dict[str, Any]] = []
    aliases_used: list[dict[str, Any]] = []
    for pos in POSITIONS:
        for d in lists[pos]:
            norm = d["id"]
            key, how, alias = ident.resolve(norm, pos)
            if key is None:
                review.append(identity_review_row(how, d["name"], norm, pos))
                continue
            if alias:
                aliases_used.append({"csv_norm": norm, "canonical_id": alias, "player_key": key})
            resolved[pos].append({**d, "player_key": key})
    drop_duplicate_keys(resolved, review, "name")
    return resolved, review, aliases_used


def calibrate_tiers(pool: dict[str, Any], bench_share: float) -> tuple[dict[str, Any], list[str]]:
    """Calibrate every position of a tier pool at the requested bench share,
    with the pipeline's feasible-share fallback (factored out of build_leg
    2026-10-08 so a saved week's projections are priced by the same code:
    pipelines/build_week_history.espn_legs_for_week)."""
    calibration: dict[str, Any] = {}
    calibration_notes = []  # Jeremy 2026-09-29: track per-position share adjustments
    for pos in POSITIONS:
        tier = pool["tiers"][pos]
        # Jeremy 2026-09-29: Use the surplus measured from current data, not a
        # stale pie file. The surplus IS the ESPN-measured pie for this dataset.
        # A static pie file goes stale when the player pool changes (e.g., 492
        # players -> 351 after IR moves), breaking calibration with "economics
        # break" errors. Measuring from current data keeps pies in sync.
        # The old pies[pos] file is kept for vintage reference only.
        pie = tier["surplus"] if tier else 0
        # Jeremy 2026-09-29: Use the feasible bench share per position. The
        # requested share (default 0.15) may be infeasible for thin positions
        # (e.g., TE after IR removals). Like the UI's bounded slider, we use
        # the highest feasible share <= requested. This is not a manual patch —
        # it's the same feasibility logic the UI applies.
        feasible_share = bench_share
        try:
            calibration[pos] = calibrate_position(tier, pie, feasible_share)
        except ValueError as e:
            msg = str(e)
            if "not positive" in msg:
                # JEG-74: requested bench share is BELOW this tier's feasible
                # window (bench rate went negative). Scan UPWARD for the
                # minimum feasible share >= requested, then refine.
                # (cbsros 2026-10-02 QB 8-team standard: feasible window sits
                # just above 0.15; 0.20 calibrates cleanly.)
                best = None
                lo = bench_share  # last infeasible
                hi = None  # first feasible
                s = bench_share
                while s < 0.99:
                    s = min(0.99, s + 0.01)
                    try:
                        test_cal = calibrate_position(tier, pie, s)
                        hi = s
                        best = (s, test_cal)
                        break
                    except ValueError:
                        lo = s
                if best is not None:
                    for _ in range(15):  # refine to ~0.0003 precision
                        mid = (lo + hi) / 2
                        try:
                            test_cal = calibrate_position(tier, pie, mid)
                            best = (mid, test_cal)
                            hi = mid
                        except ValueError:
                            lo = mid
                    feasible_share, calibration[pos] = best
                    calibration_notes.append(f"{pos}: bench share {bench_share} infeasible, using {feasible_share:.3f}")
                else:
                    raise
            elif "economics break" in msg or "does not exceed" in msg:
                # Binary search for max feasible share
                lo, hi = 0.01, bench_share
                best = None
                for _ in range(20):  # 20 iterations = high precision
                    mid = (lo + hi) / 2
                    try:
                        test_cal = calibrate_position(tier, pie, mid)
                        best = (mid, test_cal)
                        lo = mid  # try higher
                    except ValueError:
                        hi = mid  # try lower
                if best:
                    feasible_share, calibration[pos] = best
                    # Record the adjustment in notes
                    calibration_notes.append(f"{pos}: bench share {bench_share} infeasible, using {feasible_share:.3f}")
                else:
                    raise
            else:
                raise

    return calibration, calibration_notes


def build_leg(csv_path: Path, pies_path: Path, fixture_path: Path,
              scoring: str, teams: int, bench_share: float) -> dict[str, Any]:
    lists, csv_meta, csv_review = load_espn_lists(csv_path, scoring)
    pies, pies_meta = load_pies(pies_path, scoring, teams)
    resolved, id_review, aliases_used = resolve_identities(lists, fixture_path)
    review_rows = csv_review + id_review

    # JEG-67 (reverts JEG-52/JEG-60 pool cap): the cap was a value no-op.
    # Discrimination test (2026-10-02) proved it on real snapshots: capping
    # the pool at 3x starters changed ZERO of 252 shared Razzball values and
    # left calibration (rw/rs/pie/pb/ps) byte-identical in all 4 positions,
    # while dropping 217 players from leg outputs (469 -> 252). Mechanism:
    # the surplus sums only players above the waiver line, and the waiver
    # line is set by the fixed roster shape (starters + bench_mix), never by
    # pool depth -- deep tails below the line were never inflating anything.
    # The cap only destroyed coverage, so it is removed; every resolved
    # player is priced (tails below the waiver line price to exactly 0.0).

    # Tier pool keyed by canonical player_key (stable total order by key).
    pool_lists = {pos: [{"id": d["player_key"], "x": d["x"]} for d in resolved[pos]] for pos in POSITIONS}

    pool = build_position_tiers(pool_lists, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
                                list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(teams))
    calibration, calibration_notes = calibrate_tiers(pool, bench_share)

    # Full-precision raw values; the single 70/max multiplier applies BEFORE
    # any rounding (rounding is display-only and never enters this artifact).
    raw: dict[int, float] = {}
    for pos in POSITIONS:
        cal = calibration[pos]
        for d in resolved[pos]:
            raw[d["player_key"]] = price_for_projection(d["x"], cal)
    mx = max(raw.values()) if raw else 0.0
    if not (mx > 0):
        raise SystemExit("Fail closed: leg has no positive raw value; nothing to normalize.")
    scale = 70.0 / mx

    # 85/15 pie identity, verified pre-rounding (the locked guarantee).
    for pos in POSITIONS:
        cal = calibration[pos]
        # Use the actual pie and share from calibration, not the stale file
        pie = cal.get("pie_used", pies[pos])
        share_used = cal.get("bench_share_used", bench_share)
        if abs(cal["bench_raw"] - share_used * pie) > 1e-9 * pie or \
           abs(cal["starter_raw"] - (1 - share_used) * pie) > 1e-9 * pie:
            raise SystemExit(f"Fail closed: {pos} pie identity broken pre-rounding.")

    values = []
    for pos in POSITIONS:
        for d in resolved[pos]:
            key = d["player_key"]
            tier = "starter" if key in pool["starters"] else ("bench" if key in pool["bench"] else "waiver")
            values.append({
                "player_key": key,
                "player_norm": d["id"],
                "player": d["name"],
                "pos": pos,
                "team": d["team"],
                "ppg": d["x"],
                "tier": tier,
                "raw_value": raw[key],
                "value": raw[key] * scale,
            })
    values.sort(key=lambda v: (-v["value"], v["player_key"]))

    bake_id = (f"ddf-{csv_meta['espn_snapshot_date'].replace('-', '')}-espn-"
               f"{scoring}-{teams}t-{str(bench_share).replace('.', 'p')}")
    return {
        "schema": SCHEMA,
        "bake_id": bake_id,
        "generated_at": utc_now(),
        "inputs": {
            "espn_csv": str(csv_path),
            "espn_csv_sha256": sha256_file(csv_path),
            "espn_snapshot_date": csv_meta["espn_snapshot_date"],
            "espn_csv_rows": csv_meta["csv_rows"],
            "ros_weeks": csv_meta.get("ros_weeks"),
            "games_divisor": "per team: games inside ros_weeks (bye excluded)",
            "byes_sha256": sha256_file(BYES_PATH),
            "rescoring_note": ("per-game = ROS components rescored per scoring / the "
                               "team's games inside ESPN's ROS window (bye excluded). "
                               "Reception points are the only scoring "
                               "difference: ppr = half_ppr + 0.5*receptions, "
                               "standard = half_ppr - 0.5*receptions. Arithmetic on "
                               "ESPN components only; no expert blending."),
            **pies_meta,
            "scoring": scoring,
            "teams": teams,
            "bench_share": bench_share,
        },
        "reference_shape": {
            "slots": REF_SLOTS, "flex_count": REF_FLEX_COUNT,
            "flex_eligible": REF_FLEX_ELIGIBLE,
            "bench_mix": bench_mix_for_teams(teams),
        },
        "calibration": {
            pos: {
                "rw": c["rw"], "rs": c["rs"], "tau": c["tau"], "pie": c.get("pie_used", pies[pos]),
                "pb": c["pb"], "ps": c["ps"],
                "bench_share_used": c.get("bench_share_used", bench_share),
                "n_starters": sum(1 for d in resolved[pos] if d["player_key"] in pool["starters"]),
                "n_bench": sum(1 for d in resolved[pos] if d["player_key"] in pool["bench"]),
                "n_pool": len(resolved[pos]),
                "bench_raw": c["bench_raw"], "starter_raw": c["starter_raw"],
            } for pos, c in calibration.items()
        },
        "scale_70_over_max": scale,
        "max_raw_value": mx,
        "identity": {
            "aliases_used": aliases_used,
            "alias_note": ("Four CSV spellings verified as the same humans as "
                           "canonical chart names (2026-09-19 investigation, "
                           "re-confirmed vs Supabase players.full_name)."),
        },
        "values": values,
        "review_rows": review_rows,
        "summary": {
            "n_values": len(values),
            "n_review": len(review_rows),
            "n_starters": sum(1 for v in values if v["tier"] == "starter"),
            "n_bench": sum(1 for v in values if v["tier"] == "bench"),
            "n_waiver": sum(1 for v in values if v["tier"] == "waiver"),
            "calibration_notes": calibration_notes,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--pies", type=Path, default=DEFAULT_PIES)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--scoring", default="ppr", help="standard | half_ppr | ppr")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--bench-share", type=float, default=DEFAULT_BENCH_SHARE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    for path in (args.csv, args.pies, args.fixture):
        if not path.is_file():
            raise SystemExit(f"Input not found: {path}")

    leg = build_leg(args.csv, args.pies, args.fixture, args.scoring, args.teams, args.bench_share)
    out_dir = args.output_dir / leg["bake_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ddf_leg.json"
    out_path.write_text(json.dumps(leg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = leg["summary"]
    print(f"Built DDF leg {leg['bake_id']}: {summary['n_values']} values "
          f"({summary['n_starters']} starters / {summary['n_bench']} bench / "
          f"{summary['n_waiver']} waiver), {summary['n_review']} review -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
