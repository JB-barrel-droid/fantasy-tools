"""The single verified player-name alias list, for every resolver.

Data: data/inputs/player_aliases.json. Each entry maps a source spelling to
one public.players row (player_key + full_name). A raw source name matches an
entry when canonical_players.norm_player_name gives both the same form, so a
resolver may pass the raw name or its own normalized label.

Every resolver (reference savers, DDF legs, the players.json bake, the
comparison-snapshot matcher, the ESPN pull, the layered/Sleeper identity)
applies these through this module. Keeping a second, private alias map is
what let GAP-CBSROS-BAKE-IDENTITY happen; tests/test_player_aliases.py fails
if a resolver does.

Rewriting a name to the entry's full_name (the public.players spelling) is
how resolvers keyed on names use it; resolvers keyed on player_key use
alias_key(). No fuzzy matching: a name that is not an exact (normalized)
alias spelling is returned unchanged.

Where the list lives (JEG-438): the target home is Supabase
public.player_name_aliases, rows with source '*', method 'curated' and status
'verified' (seeded from the JSON by
supabase/migrations/jeg438_alias_table_curated.sql). When Supabase credentials
are in the environment and that table holds curated rows, load() reads them;
otherwise (no credentials, no curated rows yet, any read error, or
PLAYER_ALIASES_SOURCE=json) it reads the committed JSON. The two hold the same
entries (tests/test_player_alias_table.py pins the seed to the JSON, and
reconcile_player_identity.py reports drift), so which one a run reads never
changes a number. Other rows of that table (backfills, saver misses, nightly
proposals) are never read here.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

_LIB = os.path.dirname(os.path.abspath(__file__))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
from canonical_players import norm_player_name  # noqa: E402 -- the single normalization rule

_REPO = os.path.dirname(os.path.dirname(_LIB))
ALIAS_FILE = os.path.join(_REPO, "data", "inputs", "player_aliases.json")
SCHEMA = "player-aliases-v1"

TABLE = "player_name_aliases"
CURATED_METHOD = "curated"
_cache: dict | None = None
_loaded_from: str | None = None


def _index(entries: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in entries:
        key = e.get("player_key")
        full = str(e.get("full_name") or "").strip()
        alias = str(e.get("alias") or "").strip()
        if not isinstance(key, int) or not full or not alias:
            raise ValueError(f"player_aliases: incomplete entry {e!r}")
        form = norm_player_name(alias)
        prior = out.get(form)
        if prior is not None and prior["player_key"] != key:
            raise ValueError(
                f"player_aliases: {alias!r} and {prior['alias']!r} normalize to "
                f"{form!r} but name different players ({key} vs {prior['player_key']})")
        out[form] = {"alias": alias, "player_key": key, "full_name": full,
                     "pos": (e.get("pos") or "").upper() or None}
    return out


def json_entries(path: str | None = None) -> list[dict]:
    """The committed list's raw entries."""
    with open(path or ALIAS_FILE, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"player_aliases: unexpected schema {doc.get('schema')!r}")
    return doc.get("aliases") or []


def table_rows_to_entries(rows: list[dict]) -> list[dict]:
    """Curated public.player_name_aliases rows (players(full_name) embedded)
    -> alias entries."""
    out = []
    for r in rows:
        player = r.get("players") or {}
        out.append({"alias": r.get("source_player_name"), "player_key": r.get("player_key"),
                    "full_name": player.get("full_name") if isinstance(player, dict) else None,
                    "pos": r.get("position") or None})
    return out


def _fetch_curated_rows(timeout: float = 10.0) -> list[dict] | None:
    """Curated verified rows from Supabase, or None when not configured."""
    if os.environ.get("PLAYER_ALIASES_SOURCE", "").strip().lower() == "json":
        return None
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    params = urllib.parse.urlencode({
        "select": "source_player_name,player_key,position,players(full_name)",
        "source": "eq.*", "status": "eq.verified", "method": f"eq.{CURATED_METHOD}",
        "order": "id"})
    req = urllib.request.Request(f"{url}/rest/v1/{TABLE}?{params}")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        rows = json.loads(resp.read().decode() or "[]")
    if not isinstance(rows, list):
        raise ValueError("player_aliases: unexpected Supabase response")
    return rows


fetch_curated_rows = _fetch_curated_rows  # replaced in tests


def load(path: str | None = None) -> dict[str, dict]:
    """norm_player_name(alias) -> entry. Cached for the default source:
    the Supabase curated rows when present, else the committed JSON."""
    global _cache, _loaded_from
    if path is not None:
        return _index(json_entries(path))
    if _cache is not None:
        return _cache
    idx, origin = None, "json"
    try:
        rows = fetch_curated_rows()
        if rows:
            idx, origin = _index(table_rows_to_entries(rows)), "supabase"
            print(f"player_aliases: {len(idx)} curated aliases from public.{TABLE}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 -- the JSON holds the same list
        print(f"player_aliases: Supabase read failed ({type(exc).__name__}: {str(exc)[:120]}); "
              "using data/inputs/player_aliases.json", file=sys.stderr)
    if idx is None:
        idx = _index(json_entries())
    _cache, _loaded_from = idx, origin
    return idx


def loaded_from() -> str | None:
    """'supabase' or 'json' once load() ran, else None."""
    return _loaded_from


def entries() -> list[dict]:
    return list(load().values())


def lookup(name) -> dict | None:
    """The alias entry a raw (or normalized) name matches, else None."""
    if name is None:
        return None
    return load().get(norm_player_name(name))


def canonical_spelling(name):
    """public.players full_name when `name` is a verified alias, else `name`."""
    hit = lookup(name)
    return hit["full_name"] if hit else name


def alias_key(name) -> int | None:
    """player_key when `name` is a verified alias, else None."""
    hit = lookup(name)
    return hit["player_key"] if hit else None


def spellings(name) -> list:
    """`name` plus every verified spelling of the same player.

    For resolvers whose own table may carry either spelling (the Sleeper base
    says "Kenny Gainwell" and "Joshua Palmer"; public.players says "Kenneth
    Gainwell" and "Josh Palmer"). Matches the alias or the full_name form.
    """
    if name is None:
        return [name]
    form = norm_player_name(name)
    keys = {e["player_key"] for f, e in load().items()
            if f == form or norm_player_name(e["full_name"]) == form}
    out = [name]
    for e in load().values():
        if e["player_key"] in keys:
            out += [e["full_name"], e["alias"]]
    return list(dict.fromkeys(out))


def _reset_for_tests(idx: dict[str, dict] | None = None) -> None:
    """Replace (or clear) the cached list. Tests only."""
    global _cache, _loaded_from
    _cache = idx
    _loaded_from = None
