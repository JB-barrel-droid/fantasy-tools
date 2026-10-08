"""Canonical player identity resolution (shared) — legacy shim.

Migrated from waiver_wire/pipeline/bin/identity.py when that product was
archived (2026-10-07). API is unchanged so pull_espn_projections.py keeps
working without modification to its call sites.

New identity work should use pipelines/lib/layered_identity.py instead.

The Supabase player_identities registry is the single source of truth;
this module canonicalizes names through its snapshot before any pricing
math.

Resolution order for a normed key:
  0. a verified alias (data/inputs/player_aliases.json, the one shared list)
     is rewritten to its public.players spelling first
  1. snapshot alias_to_canonical (mechanical spelling variants)
  2. the key itself when it is a known canonical chart key
  3. built-in heuristic (suffix strip/add, nickname table) against chart
     keys - deterministic, single-candidate only, logged to stderr
  4. the key itself (leg-only / unknown player)

New variants belong in the registry, never as another hardcoded table
in a script. The heuristic is a backstop, not the authority.
"""
import json
import re
import sys
from pathlib import Path

# Snapshot lives in data/inputs/ in the repo; the old waiver_wire path
# is gone (archived 2026-10-07). pull_espn_projections.py already carries
# a Path(ident.SNAP).exists() guard with a fallback to data/inputs/, so
# pointing SNAP at the canonical repo location removes the fallback branch.
_LIB = Path(__file__).resolve().parent      # pipelines/lib/
_PIPELINES = _LIB.parent                    # pipelines/
_REPO = _PIPELINES.parent                   # repo root
SNAP = _REPO / "data" / "inputs" / "player_identity_map.json"

SUFFIXES = ("jr", "sr", "ii", "iii", "iv", "v")
# One nickname table (lib/nicknames.py) and one verified alias list
# (lib/player_aliases.py) for every resolver; this module kept private copies
# before 2026-10-08.
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
from nicknames import NICKNAMES  # noqa: E402
import player_aliases  # noqa: E402


def shared_alias_spelling(name):
    """The public.players spelling when `name` is a verified alias, else `name`."""
    return player_aliases.canonical_spelling(name)


def norm_name(n):
    return re.sub(r"[^a-z ]", "", str(n).lower()).strip()


def _strip_suffix(k):
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", k).strip()


class IdentityMap:
    def __init__(self, chart_keys=(), snapshot_path=SNAP):
        self.chart_keys = set(chart_keys)
        self.alias_to_canonical = {}
        self.canonical = {}
        try:
            snap = json.loads(Path(snapshot_path).read_text())
            self.alias_to_canonical = snap.get("alias_to_canonical", {})
            self.canonical = snap.get("canonical", {})
        except (OSError, ValueError) as e:
            print("  identity snapshot unavailable (%s) - heuristic only"
                  % e, file=sys.stderr)

    def heuristic(self, key):
        """Mechanical variants against chart keys. Single candidate only."""
        cands = set()
        bases = {key, _strip_suffix(key)}
        parts = key.split(" ")
        if parts and parts[0] in NICKNAMES:
            b2 = norm_name(NICKNAMES[parts[0]] + " " + " ".join(parts[1:]))
            bases.add(b2)
            bases.add(_strip_suffix(b2))
        for b in bases:
            if b in self.chart_keys:
                cands.add(b)
            for s in SUFFIXES:
                if b + " " + s in self.chart_keys:
                    cands.add(b + " " + s)
        if len(cands) == 1:
            ck = next(iter(cands))
            print("  identity heuristic: %r -> %r (add to registry)"
                  % (key, ck), file=sys.stderr)
            return ck
        return None

    def canon(self, key):
        """Normed key -> canonical (chart-key) identity."""
        key = norm_name(shared_alias_spelling(key))
        hit = self.alias_to_canonical.get(key)
        if hit:
            return hit
        if key in self.chart_keys:
            return key
        h = self.heuristic(key)
        if h:
            return h
        return key

    def display(self, key):
        """Canonical display name for a key (chart spelling)."""
        ck = self.canon(key)
        c = self.canonical.get(ck)
        if c:
            return c["name"]
        return " ".join(w.capitalize() for w in ck.split(" "))
