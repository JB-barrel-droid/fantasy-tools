"""Canonical player resolution: the ONE name -> player_key path for the pipeline.

The Supabase `players` table (Sleeper-sourced, full NFL pool, 4641 rows) is the
canonical roster. Every pipeline stage that receives a player NAME from any
source resolves it here, once, to the numeric `player_key` -- and carries that
key downstream. Joins happen on player_key, never on re-derived name strings.

This module replaces the scattered per-script matching (norm_name copies in
fit_source_variants, build_values, build_compare_dashboard_data, the lottery
IdentityMap snapshot, engine/snapshot.match_player, ...). New code MUST resolve
through here; do not add another name table.

Rules (fail-closed):
  - Normalization is the single shared rule: lowercase, strip punctuation and
    generational suffixes, collapse whitespace, expand first-token nicknames
    via the shared NICKNAMES table in lottery/bin/identity.py (imported, never
    copied -- the two tables WILL drift).
  - The curated identity snapshot (lottery/data/player_identity_map.json,
    alias_to_canonical) is applied as an override layer before lookup.
  - Active players beat inactive ones with the same normalized name.
  - An optional position filter disambiguates same-name players
    (Lamar Jackson QB vs DB; Justin Jefferson WR vs LB).
  - Anything still ambiguous -> None, never a guess. Unmatched -> None.
    Missing is null, never zero.

Usage:
    from engine.canonical_players import resolve, load_registry
    reg = load_registry()                       # once per run
    key = resolve("Kenny Gainwell", position="RB", registry=reg)  # -> 785
"""

import json
import os
import re
import sys

WS = os.environ.get("HATCH_WORKSPACE", os.path.expanduser("~/workspace"))
LOTTERY_BIN = os.path.join(WS, "goals", "football-signal-database-and-app", "lottery", "bin")
if LOTTERY_BIN not in sys.path:
    sys.path.insert(0, LOTTERY_BIN)
SKILL_BIN = os.path.join(WS, "skills", "supabase-football-signal", "bin")
if SKILL_BIN not in sys.path:
    sys.path.insert(0, SKILL_BIN)

from identity import NICKNAMES  # noqa: E402  -- shared table, imported not copied

IDENTITY_SNAPSHOT = os.path.join(
    WS, "goals", "football-signal-database-and-app", "lottery", "data",
    "player_identity_map.json",
)

_SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")


def norm_plain(name):
    """Normalization WITHOUT nickname expansion.

    This is the legacy ``player_norm`` label convention — what name-keyed
    consumers (kicker/DST actuals joins) already join on. Identity matching
    must use norm_player_name(); this is label-only, never for matching.
    """
    s = (name or "").lower()
    for ch in ("’", "'", ".", "-"):
        s = s.replace(ch, "")
    s = _SUFFIX_RE.sub("", s)
    return " ".join(s.split())


def norm_player_name(s):
    """The single normalization rule. Import this; do not reimplement it."""
    s = str(s).lower()
    for ch in ("\u2019", "'", ".", "-"):
        s = s.replace(ch, "")
    s = _SUFFIX_RE.sub("", s)
    s = " ".join(s.split())
    toks = s.split(" ")
    if toks and toks[0] in NICKNAMES:
        toks[0] = NICKNAMES[toks[0]]
        s = " ".join(toks)
    return s


def _load_alias_overrides():
    """alias_to_canonical from the curated identity snapshot, normalized."""
    try:
        snap = json.load(open(IDENTITY_SNAPSHOT))
    except (OSError, ValueError):
        return {}
    out = {}
    for alias, canon in snap.get("alias_to_canonical", {}).items():
        a, c = norm_player_name(alias), norm_player_name(canon)
        if a != c:
            out[a] = c
    return out


class Registry:
    """In-memory index of the canonical players table."""

    def __init__(self, rows):
        # rows: iterable of dicts with player_key, full_name, position, active
        # (+ optional id, carried as uuid for transitional consumers)
        self.by_key = {}
        self.by_norm = {}
        self.dst_by_token = {}
        for r in rows:
            key = int(r["player_key"])
            norm = norm_player_name(r["full_name"])
            entry = {
                "player_key": key,
                "uuid": r.get("id"),
                "full_name": r["full_name"],
                "position": (r.get("position") or "").upper(),
                "active": bool(r.get("active")),
                "team_id": r.get("team_id"),
            }
            self.by_key[key] = entry
            self.by_norm.setdefault(norm, []).append(entry)
            if entry["position"] == "DST":
                # "Seattle Seahawks" -> city/nickname/full-name tokens
                toks = norm.split(" ")
                self.dst_by_token[norm] = key
                if len(toks) >= 2:
                    self.dst_by_token[toks[-1]] = key          # seahawks
                    self.dst_by_token[" ".join(toks[:-1])] = key  # seattle
        self.alias_overrides = _load_alias_overrides()

    def lookup_dst(self, raw):
        """Team-defense forms: 'Seahawks DST', 'Seattle', 'SEA'..."""
        s = norm_player_name(raw)
        s = re.sub(r"\s+(dst|defense|def)$", "", s).strip()
        return self.dst_by_token.get(s)


_REGISTRY = None


def load_registry(rows=None):
    """Load (and cache) the registry. Pass rows to build from in-memory data
    (tests); otherwise reads the live players table."""
    global _REGISTRY
    if rows is None:
        if _REGISTRY is not None:
            return _REGISTRY
        import sbclient
        rows = sbclient.get_all(
            "players", "?select=player_key,id,full_name,position,active,team_id")
        _REGISTRY = Registry(rows)
        # Team-defense abbreviations ("HOU", "LA", ...) -> DST keys, via the
        # teams table. The teams table carries stale duplicate rows
        # (STL/SD/OAK alongside LA/LAC/LV); map those to current first.
        _STALE_ABBR = {"LAR": "LA", "JAC": "JAX", "STL": "LA",
                       "OAK": "LV", "SD": "LAC"}
        try:
            teams = sbclient.get_all(
                "teams", "?select=id,abbreviation&limit=100")
        except Exception:
            teams = []
        seen_team = {}
        for t in teams:
            abbr = (t.get("abbreviation") or "").strip().upper()
            abbr = _STALE_ABBR.get(abbr, abbr)
            if t.get("id") and abbr and t["id"] not in seen_team:
                seen_team[t["id"]] = abbr
        for e in _REGISTRY.by_key.values():
            if e["position"] == "DST" and e.get("team_id"):
                abbr = seen_team.get(e["team_id"])
                if abbr:
                    _REGISTRY.dst_by_token[abbr.lower()] = e["player_key"]
        return _REGISTRY
    return Registry(rows)


def resolve_with_reason(name, position=None, registry=None, allow_inactive=True):
    """Resolve a raw source name to a canonical player_key.

    Returns (player_key | None, reason) where reason is one of:
      ok | dst | unmatched | ambiguous | position_conflict
    """
    reg = registry or load_registry()
    pos = (position or "").upper() or None

    # Team defenses take the DST token path.
    if pos == "DST" or re.search(r"\b(dst|defense|def)\b", str(name).lower()):
        key = reg.lookup_dst(name)
        return (key, "dst") if key else (None, "unmatched")

    norm = norm_player_name(name)
    norm = reg.alias_overrides.get(norm, norm)
    cands = reg.by_norm.get(norm, [])
    if not cands:
        return None, "unmatched"

    if pos:
        pc = [c for c in cands if c["position"] == pos]
        if not pc:
            return None, "position_conflict"
        cands = pc

    active = [c for c in cands if c["active"]]
    pool = active or (cands if allow_inactive else [])
    if not pool:
        return None, "unmatched"
    if len(pool) == 1:
        return pool[0]["player_key"], "ok"
    # Same norm name, same position, multiple actives -> fail closed.
    # (Only known case in the full pool: Jordan Phillips DL x2, an IDP player.)
    return None, "ambiguous"


def resolve(name, position=None, registry=None, allow_inactive=True):
    """Resolve a raw source name to player_key, or None (fail-closed)."""
    key, _reason = resolve_with_reason(
        name, position=position, registry=registry,
        allow_inactive=allow_inactive)
    return key


SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def resolve_skill(name, registry=None):
    """Resolve a chart-universe name (QB/RB/WR/TE) without a known position.

    Tries each skill position; returns the key iff exactly one position
    yields a unique hit, else None (fail-closed). Used when classifying
    source names that have no target-side position (e.g. no-fit reasons).
    """
    reg = registry or load_registry()
    hits = set()
    for pos in SKILL_POSITIONS:
        key = resolve(name, position=pos, registry=reg)
        if key is not None:
            hits.add(key)
    return hits.pop() if len(hits) == 1 else None


def key_for_uuid(player_uuid, registry=None):
    """Bridge: UUID-keyed rows -> player_key via the registry (no matching)."""
    import sbclient
    rows = sbclient.get("players",
                        "?select=player_key&id=eq.%s" % player_uuid)
    return int(rows[0]["player_key"]) if rows else None


def display_name(player_key, registry=None):
    reg = registry or load_registry()
    e = reg.by_key.get(int(player_key))
    return e["full_name"] if e else None


def canonical_name(player_key, registry=None):
    """The ONE display-name source: the Supabase `players` table's
    `full_name`, looked up by numeric player_key.

    Returns the canonical name, or None when the key has no row. Callers
    must fail closed on None -- a source's spelling is never substituted.
    """
    return display_name(player_key, registry=registry)


def require_canonical_name(player_key, registry=None):
    """canonical_name() that aborts the build instead of returning None.

    Use at every bake site that emits a player-facing name: a chart player
    with no canonical players-table name is a data bug, not a gap to fill
    with a source's spelling.
    """
    name = canonical_name(player_key, registry=registry)
    if not name:
        raise SystemExit(
            "FAIL-CLOSED: no canonical players-table name for "
            f"player_key {player_key} -- refusing to substitute a "
            "source spelling.")
    return name


def assert_canonical_names(pairs, registry=None, context=""):
    """Fail-closed gate: every (player_key, display_name) pair must equal
    the players-table canonical full_name for its key.

    Raises SystemExit listing every mismatch and every key with no
    canonical name. Call at the end of each bake, before writing output.
    """
    reg = registry or load_registry()
    bad, missing = [], []
    for key, name in pairs:
        want = canonical_name(key, registry=reg)
        if want is None:
            missing.append((key, name))
        elif want != name:
            bad.append((key, name, want))
    if not bad and not missing:
        return
    where = f" in {context}" if context else ""
    lines = [f"FAIL-CLOSED: {len(bad)} non-canonical display name(s), "
             f"{len(missing)} key(s) with no canonical name{where}"]
    for key, name, want in bad[:25]:
        lines.append(f"  key={key}: baked {name!r} != canonical {want!r}")
    for key, name in missing[:25]:
        lines.append(f"  key={key}: baked {name!r} has no canonical name")
    raise SystemExit("\n".join(lines))
