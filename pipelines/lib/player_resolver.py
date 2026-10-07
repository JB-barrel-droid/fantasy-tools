"""JEG-438: the ONE player-name resolver.

Every pipeline that receives a player NAME (or a source's own player id) turns
it into the canonical numeric ``player_key`` here, and nowhere else. A guard
test (tests/test_single_player_resolver.py) fails the build if a pipeline
normalizes or matches player names any other way.

Data (docs/identity-model.md):
  canonical table   public.players            -> player_key, full_name, position, active, team
  cross-ids         public.external_id_map    -> sleeper / espn / yahoo / gsis ids
  name mappings     public.player_name_aliases -> how each source spells a player
All three are exported to data/inputs/player_registry.json by
pipelines/export_player_registry.py (nightly, player-identity-reconcile.yml),
which is what this module reads. Callers holding live rows may build a
resolver from them directly (PlayerResolver(players, aliases, xrefs)).

Resolution order, stopping at the first step that yields exactly one player:
  1. source id   -- (source, source_player_id) alias row, or a cross-id
                    (sleeper/espn/yahoo/gsis) in external_id_map.       -> verified
  2. alias       -- a verified alias for this source, then for '*'.      -> verified
                    (a provisional alias row resolves as provisional)
  3. canonical   -- the players table's own names, three spellings in
                    order: exact key, nickname-expanded, space-free.
                    Position filter, then active-over-inactive, then team.
                    Two players left at any spelling -> ambiguous, stop. -> exact
  4. fuzzy       -- ONLY when nothing above found any candidate. Same last
                    name, compatible first name, unique by a margin, above a
                    confidence floor. Returned as status 'provisional',
                    flagged, recorded for the nightly reconcile, and never
                    written back as verified by this module.            -> provisional
Unknown or ambiguous -> player_key None. Missing is null, never a guess.

Usage:
    from lib.player_resolver import get_resolver
    r = get_resolver()
    res = r.resolve("Kenny Gainwell", source="fantasycalc", pos="RB")
    res.player_key, res.status        # 785, 'verified'
    r.write_pending("output/identity/pending-fantasycalc.json")
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

_LIB = os.path.dirname(os.path.abspath(__file__))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
from nicknames import NICKNAMES  # noqa: E402  -- vendored, drift-tested

REPO = Path(_LIB).parent.parent
REGISTRY_PATH = REPO / "data" / "inputs" / "player_registry.json"
REGISTRY_SCHEMA = "player-registry-v1"
ID_TYPES = ("sleeper", "espn", "yahoo", "gsis")

# Fuzzy (provisional) policy. These should be extreme edge cases.
PROVISIONAL_FLOOR = 0.90
PROVISIONAL_MARGIN = 0.05

MATCHED = ("verified", "exact")

_SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")
_DELETE_RE = re.compile(r"[’‘'`.]")
_NONALNUM_RE = re.compile(r"[^a-z0-9]+")
_DST_RE = re.compile(r"\s+(dst|d st|defense|def)$")
# Stale/alternate team abbreviations -> current canonical abbreviations.
TEAM_ABBR_FIX = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX", "STL": "LA",
                 "OAK": "LV", "SD": "LAC"}


# ---------------------------------------------------------------------------
# Normalization: the single rule. Do not reimplement it anywhere else.
# ---------------------------------------------------------------------------

def norm_key(name: Any) -> str:
    """Name -> lookup key: ASCII-fold, lowercase, drop apostrophes and periods,
    other punctuation (hyphens) to spaces, drop a generational suffix.

    "Ja'Marr Chase" -> "jamarr chase"; "Amon-Ra St. Brown" -> "amon ra st brown";
    "Kenneth Walker III" -> "kenneth walker"; "A.J. Brown" -> "aj brown".
    """
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii")
    s = _DELETE_RE.sub("", s.lower())
    s = _NONALNUM_RE.sub(" ", s)
    s = " ".join(s.split())
    return _SUFFIX_RE.sub("", s)


def nickname_key(key: str) -> str:
    """norm_key with the first token's nickname expanded ("kenny" -> "kenneth")."""
    toks = key.split(" ")
    if toks and toks[0] in NICKNAMES:
        toks[0] = NICKNAMES[toks[0]]
    return " ".join(toks)


def compact_key(key: str) -> str:
    """norm_key without spaces ("smith njigba" == "smithnjigba")."""
    return key.replace(" ", "")


def name_label(name: Any) -> str:
    """The stored ``player_norm`` label for a source row (= norm_key).

    A LABEL only, written next to the resolved player_key for readability.
    Never join on it: join on player_key.
    """
    return norm_key(name)


# Stored-label conventions. Before JEG-438 each writer of a ``player_norm``
# column had its own normalizer, and the stored strings differ by writer
# ("Ja'Marr Chase" is "ja marr chase" in the source-reference tables and
# "jamarr chase" in the DDF legs). Several downstream steps still join on those
# stored strings, so a migrated writer must keep writing byte-identical labels.
# The rules live here, once; they are LABELS, never identity (identity is
# PlayerResolver.resolve -> player_key). Unifying them is a separate, value-
# checked change (docs/identity-model.md, "Stored labels").
_LABEL_SUFFIX_ANYWHERE_RE = re.compile(r"\b(jr|sr|ii|iii|iv)\.?\b")
_PLAIN_SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")
LABEL_CONVENTIONS = ("key", "source", "plain", "lower")


def legacy_label(name: Any, convention: str) -> str:
    """The stored ``player_norm`` label for a row, in the given convention.

    key    -- norm_key (the resolver's own lookup key)
    source -- source-reference tables (save_*_references, match files):
              ASCII-fold, lowercase, drop jr/sr/ii/iii/iv anywhere, every
              non-alphanumeric run to one space.
    plain  -- DDF legs and projection pulls: lowercase, delete apostrophes,
              periods and hyphens, drop a trailing generational suffix.
    lower  -- refresh_fantasycalc_supabase: lowercase and strip only.
    """
    if convention == "key":
        return norm_key(name)
    if convention == "source":
        text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii")
        text = _LABEL_SUFFIX_ANYWHERE_RE.sub(" ", text.lower())
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()
    if convention == "plain":
        s = (name or "").lower()
        for ch in ("’", "'", ".", "-"):
            s = s.replace(ch, "")
        s = _PLAIN_SUFFIX_RE.sub("", s)
        return " ".join(s.split())
    if convention == "lower":
        return str(name or "").lower().strip()
    raise ValueError(f"unknown label convention {convention!r}; one of {LABEL_CONVENTIONS}")


def team_abbr(value: Any) -> str | None:
    t = str(value or "").strip().upper()
    return TEAM_ABBR_FIX.get(t, t) or None


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Resolution:
    player_key: int | None
    status: str          # verified | exact | provisional | unmatched | ambiguous | position_conflict
    method: str          # source_id | xref:<type> | alias:<source> | canonical:<tier> | fuzzy | dst | none
    confidence: float | None = None
    candidates: tuple = ()

    @property
    def ok(self) -> bool:
        """True when the key is safe to use (verified/exact, or an accepted provisional)."""
        return self.player_key is not None

    @property
    def provisional(self) -> bool:
        return self.status == "provisional"

    @property
    def reason(self) -> str:
        """Legacy reason vocabulary: ok | dst | unmatched | ambiguous | position_conflict."""
        if self.player_key is not None:
            return "dst" if self.method == "dst" else "ok"
        return self.status


@dataclass
class _Player:
    player_key: int
    full_name: str
    position: str
    active: bool
    team: str | None
    keys: tuple = field(default=())


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class PlayerResolver:
    """In-memory index of the canonical players table + alias map + cross-ids."""

    def __init__(self, players: Iterable[dict], aliases: Iterable[dict] = (),
                 xrefs: dict[str, dict[str, int]] | None = None, *,
                 provisional_floor: float = PROVISIONAL_FLOOR,
                 provisional_margin: float = PROVISIONAL_MARGIN,
                 meta: dict | None = None):
        self.meta = dict(meta or {})
        self.floor = provisional_floor
        self.margin = provisional_margin
        self.by_key: dict[int, _Player] = {}
        self._tiers: tuple[dict[str, list[_Player]], ...] = ({}, {}, {})
        self.dst_by_token: dict[str, int] = {}
        self.by_last: dict[str, list[_Player]] = {}
        for row in players:
            key = int(row["player_key"])
            name = str(row.get("full_name") or row.get("name") or "").strip()
            if not name:
                continue
            k1 = norm_key(name)
            p = _Player(key, name, str(row.get("position") or "").upper(),
                        bool(row.get("active")), team_abbr(row.get("team")),
                        (k1, nickname_key(k1), compact_key(k1)))
            self.by_key[key] = p
            for tier, k in zip(self._tiers, p.keys):
                tier.setdefault(k, []).append(p)
            toks = k1.split(" ")
            if toks:
                self.by_last.setdefault(toks[-1], []).append(p)
            if p.position == "DST":
                self._index_dst(p)
        self.xrefs = {t: {str(k): int(v) for k, v in (xrefs or {}).get(t, {}).items()}
                      for t in ID_TYPES}
        # aliases: (source, norm_key) -> list of alias dicts; (source, source_id) -> alias
        self._alias: dict[tuple[str, str], list[dict]] = {}
        self._alias_by_id: dict[tuple[str, str], dict] = {}
        self._rejected: dict[tuple[str, str], set[int]] = {}
        for a in aliases:
            self.add_alias(a)
        self.pending: dict[tuple[str, str, str], dict] = {}

    # -- construction helpers -------------------------------------------------

    def _index_dst(self, p: _Player) -> None:
        k = p.keys[0]
        toks = k.split(" ")
        self.dst_by_token[k] = p.player_key
        if len(toks) >= 2:
            self.dst_by_token[toks[-1]] = p.player_key            # seahawks
            self.dst_by_token[" ".join(toks[:-1])] = p.player_key  # seattle
        if p.team:
            self.dst_by_token[p.team.lower()] = p.player_key       # sea

    def add_alias(self, a: dict) -> None:
        status = str(a.get("status") or "verified")
        source = str(a.get("source") or "*").lower()
        name = a.get("source_player_name") or a.get("name") or ""
        key = a.get("player_key")
        entry = {
            "source": source, "name": name, "key": norm_key(name),
            "position": str(a.get("position") or "").upper(),
            "player_key": int(key) if key is not None else None,
            "status": status, "method": a.get("method"),
            "confidence": a.get("confidence"),
            "source_player_id": a.get("source_player_id"),
        }
        if status == "rejected" and entry["player_key"] is not None:
            self._rejected.setdefault((source, entry["key"]), set()).add(entry["player_key"])
            return
        if status not in ("verified", "provisional") or entry["player_key"] is None:
            return
        if entry["player_key"] not in self.by_key:
            return  # alias to a key the snapshot does not know: never trusted
        self._alias.setdefault((source, entry["key"]), []).append(entry)
        if entry["source_player_id"]:
            self._alias_by_id[(source, str(entry["source_player_id"]))] = entry

    # -- lookups ---------------------------------------------------------------

    def player(self, player_key: int) -> dict | None:
        p = self.by_key.get(int(player_key))
        if p is None:
            return None
        return {"player_key": p.player_key, "full_name": p.full_name,
                "position": p.position, "active": p.active, "team": p.team}

    def canonical_name(self, player_key: int) -> str | None:
        p = self.by_key.get(int(player_key))
        return p.full_name if p else None

    def resolve_dst(self, raw: Any) -> int | None:
        """Team-defense forms: 'Seahawks DST', 'Seattle', 'SEA', 'Seattle Seahawks'."""
        s = _DST_RE.sub("", norm_key(raw)).strip()
        s = TEAM_ABBR_FIX.get(s.upper(), s.upper()).lower() if len(s) <= 3 else s
        return self.dst_by_token.get(s)

    def resolve(self, name: Any, *, source: str, pos: str | None = None,
                team: str | None = None, source_id: Any = None,
                id_type: str | None = None, allow_provisional: bool = True,
                record: bool = True) -> Resolution:
        source = str(source or "*").lower()
        pos = str(pos or "").strip().upper() or None
        team = team_abbr(team)
        raw = str(name or "").strip()

        # Team defenses take the DST token path.
        if pos in ("DST", "DEF", "D/ST") or re.search(r"\b(dst|d/st|defense)\b", raw.lower()):
            k = self.resolve_dst(raw)
            res = Resolution(k, "verified" if k else "unmatched", "dst" if k else "none",
                             1.0 if k else None)
            if k is None and record:
                self._remember(source, raw, pos, team, res, source_id)
            return res

        # 1. source id
        if source_id not in (None, ""):
            sid = str(source_id).strip()
            hit = self._alias_by_id.get((source, sid))
            if hit and self._pos_ok(hit["player_key"], pos):
                return self._from_alias(hit, "source_id", allow_provisional, source, raw, pos, team, sid, record)
            t = (id_type or source).lower()
            if t in self.xrefs and sid in self.xrefs[t]:
                k = self.xrefs[t][sid]
                if k in self.by_key and self._pos_ok(k, pos):
                    return Resolution(k, "verified", f"xref:{t}", 1.0)

        if not raw:
            return Resolution(None, "unmatched", "none")
        k1 = norm_key(raw)

        # 2. alias: this source first, then any source
        for src in dict.fromkeys((source, "*")):
            rows = [a for a in self._alias.get((src, k1), [])
                    if (not a["position"] or not pos or a["position"] == pos)
                    and self._pos_ok(a["player_key"], pos)]
            keys = {a["player_key"] for a in rows}
            if len(keys) == 1:
                best = sorted(rows, key=lambda a: a["status"] != "verified")[0]
                return self._from_alias(best, f"alias:{src}", allow_provisional, source, raw, pos, team, source_id, record)
            if len(keys) > 1:
                res = Resolution(None, "ambiguous", f"alias:{src}", None, tuple(sorted(keys)))
                if record:
                    self._remember(source, raw, pos, team, res, source_id)
                return res

        # 3. canonical exact (three spellings)
        probe = (k1, nickname_key(k1), compact_key(k1))
        saw_name = False
        for tier_name, tier, k in zip(("exact", "nickname", "compact"), self._tiers, probe):
            cands = tier.get(k, [])
            if not cands:
                continue
            saw_name = True
            pick, status = self._choose(cands, pos, team)
            if status == "ok":
                return Resolution(pick.player_key, "exact", f"canonical:{tier_name}", 1.0)
            if status == "ambiguous":
                res = Resolution(None, "ambiguous", f"canonical:{tier_name}", None,
                                 tuple(sorted(c.player_key for c in pick)))
                if record:
                    self._remember(source, raw, pos, team, res, source_id)
                return res
            # position_conflict at this spelling: a looser spelling may still fit
        if saw_name:
            res = Resolution(None, "position_conflict", "canonical", None)
            if record:
                self._remember(source, raw, pos, team, res, source_id)
            return res

        # 4. fuzzy -> provisional (flagged; nightly job verifies or rejects)
        res = self._fuzzy(source, k1, pos, team)
        if record:
            self._remember(source, raw, pos, team, res, source_id)
        if res.status == "provisional" and not allow_provisional:
            return Resolution(None, "unmatched", "fuzzy-declined", res.confidence, res.candidates)
        return res

    def name_candidates(self, name: Any) -> list[int]:
        """Every player_key whose canonical name matches at any spelling tier,
        any position (no filtering, no choice). For audits and the nightly job."""
        k1 = norm_key(name)
        keys = set()
        for tier, k in zip(self._tiers, (k1, nickname_key(k1), compact_key(k1))):
            keys.update(p.player_key for p in tier.get(k, []))
        return sorted(keys)

    def key(self, name: Any, **kw) -> int | None:
        return self.resolve(name, **kw).player_key

    # -- internals -------------------------------------------------------------

    def _pos_ok(self, player_key: int, pos: str | None) -> bool:
        if not pos:
            return True
        p = self.by_key.get(player_key)
        return p is not None and p.position == pos

    def _from_alias(self, a: dict, method: str, allow_provisional: bool, source: str,
                    raw: str, pos, team, source_id, record: bool) -> Resolution:
        if a["status"] == "verified":
            return Resolution(a["player_key"], "verified", method, 1.0)
        res = Resolution(a["player_key"], "provisional", method,
                         float(a["confidence"]) if a.get("confidence") is not None else None)
        if record:
            self._remember(source, raw, pos, team, res, source_id)
        if not allow_provisional:
            return Resolution(None, "unmatched", method + ":provisional-declined", res.confidence)
        return res

    @staticmethod
    def _choose(cands: list[_Player], pos: str | None, team: str | None):
        uniq = list({c.player_key: c for c in cands}.values())
        if pos:
            uniq = [c for c in uniq if c.position == pos]
            if not uniq:
                return None, "position_conflict"
        if len(uniq) > 1:
            active = [c for c in uniq if c.active]
            uniq = active or uniq
        if len(uniq) > 1 and team:
            same = [c for c in uniq if c.team == team]
            if len(same) == 1:
                uniq = same
        if len(uniq) == 1:
            return uniq[0], "ok"
        return uniq, "ambiguous"

    def _fuzzy(self, source: str, k1: str, pos: str | None, team: str | None) -> Resolution:
        toks = k1.split(" ")
        if len(toks) < 2:
            return Resolution(None, "unmatched", "none")
        first, last = toks[0], toks[-1]
        rejected = self._rejected.get((source, k1), set()) | self._rejected.get(("*", k1), set())
        scored: list[tuple[float, _Player]] = []
        pool = list(self.by_last.get(last, []))
        # hyphenated / compound surnames: "jalen cropper" vs "jalen moreno cropper"
        for p in pool:
            if pos and p.position != pos:
                continue
            if p.player_key in rejected:
                continue
            ptoks = p.keys[0].split(" ")
            pf = ptoks[0]
            ef, pf_exp = nickname_key(first), nickname_key(pf)
            if first == pf or ef == pf_exp:
                score = 0.95
            elif len(first) >= 3 and len(pf) >= 3 and (pf.startswith(first) or first.startswith(pf)):
                score = 0.92
            elif first[0] == pf[0]:
                score = 0.80 + 0.1 * SequenceMatcher(None, first, pf).ratio()
            else:
                score = 0.5 * SequenceMatcher(None, k1, p.keys[0]).ratio()
            score -= 0.01 * abs(len(ptoks) - len(toks))
            if team and p.team and p.team != team:
                score -= 0.03
            if not p.active:
                score -= 0.02
            scored.append((round(score, 3), p))
        if not scored:
            return Resolution(None, "unmatched", "none")
        scored.sort(key=lambda t: (-t[0], t[1].player_key))
        best_score, best = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        cands = tuple(p.player_key for _, p in scored[:5])
        if best_score >= self.floor and best_score - second >= self.margin:
            return Resolution(best.player_key, "provisional", "fuzzy", best_score, cands)
        return Resolution(None, "unmatched", "fuzzy-below-floor", best_score, cands)

    def _remember(self, source, raw, pos, team, res: Resolution, source_id) -> None:
        k = (source, norm_key(raw), pos or "")
        entry = self.pending.get(k)
        if entry:
            entry["seen_count"] += 1
            return
        self.pending[k] = {
            "source": source, "source_player_name": raw, "norm_name": norm_key(raw),
            "position": pos or "", "team": team,
            "source_player_id": None if source_id in (None, "") else str(source_id),
            "player_key": res.player_key,
            "status": "provisional" if res.status == "provisional" else (
                "review" if res.status in ("ambiguous", "position_conflict") else "unmatched"),
            "resolver_status": res.status, "method": res.method,
            "confidence": res.confidence, "candidate_keys": list(res.candidates),
            "seen_count": 1,
        }

    # -- pending (provisional / unmatched) -------------------------------------

    def pending_rows(self) -> list[dict]:
        return sorted(self.pending.values(), key=lambda r: (r["source"], r["norm_name"], r["position"]))

    def pending_summary(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for r in self.pending.values():
            out.setdefault(r["source"], {}).setdefault(r["status"], 0)
            out[r["source"]][r["status"]] += 1
        return out

    def write_pending(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": "player-identity-pending-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "registry": self.meta,
            "summary": self.pending_summary(),
            "rows": self.pending_rows(),
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def flush_pending(self, sbclient) -> int:
        """Record provisional/unmatched names in public.player_name_aliases for the
        nightly reconcile. Never overwrites an existing row (verified rows win).
        Returns rows sent; never raises (identity logging must not fail a save)."""
        rows = [{
            "source": r["source"], "source_player_name": r["source_player_name"],
            "norm_name": r["norm_name"], "position": r["position"],
            "source_player_id": r["source_player_id"], "player_key": r["player_key"],
            "status": r["status"], "method": f"resolver:{r['method']}",
            "confidence": r["confidence"], "team": r["team"],
            "candidate_keys": r["candidate_keys"] or None,
        } for r in self.pending_rows()]
        if not rows:
            return 0
        try:
            sbclient.post("player_name_aliases", rows,
                          params="?on_conflict=source,norm_name,position",
                          prefer="resolution=ignore-duplicates,return=minimal")
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=player-identity::could not record {len(rows)} pending names: {exc}",
                  file=sys.stderr)
            return 0
        return len(rows)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def registry_from_snapshot(payload: dict) -> PlayerResolver:
    if payload.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"FAIL-CLOSED: player registry schema {payload.get('schema')!r} "
                         f"!= {REGISTRY_SCHEMA!r}")
    cols = payload["columns"]
    players = [dict(zip(cols, row)) for row in payload["players"]]
    return PlayerResolver(players, payload.get("aliases", []), payload.get("xrefs", {}),
                          meta=payload.get("meta", {}))


_CACHE: dict[str, PlayerResolver] = {}
_PAYLOADS: dict[str, dict] = {}


def _registry_path(path: Path | str | None) -> Path:
    return Path(path or os.environ.get("PLAYER_REGISTRY_PATH") or REGISTRY_PATH)


def load_registry_payload(path: Path | str | None = None) -> dict:
    """The committed registry snapshot as parsed JSON (cached, schema-checked)."""
    p = _registry_path(path)
    k = str(p.resolve())
    if k not in _PAYLOADS:
        if not p.exists():
            raise SystemExit(f"FAIL-CLOSED: player registry {p} missing; run "
                             "pipelines/export_player_registry.py")
        payload = json.loads(p.read_text(encoding="utf-8"))
        if payload.get("schema") != REGISTRY_SCHEMA:
            raise SystemExit(f"FAIL-CLOSED: player registry schema {payload.get('schema')!r} "
                             f"!= {REGISTRY_SCHEMA!r}")
        _PAYLOADS[k] = payload
    return _PAYLOADS[k]


def get_resolver(path: Path | str | None = None) -> PlayerResolver:
    """The cached resolver for the committed registry snapshot (or PLAYER_REGISTRY_PATH)."""
    k = str(_registry_path(path).resolve())
    if k not in _CACHE:
        _CACHE[k] = registry_from_snapshot(load_registry_payload(path))
    return _CACHE[k]


def resolver_for_players(players: Iterable[dict], path: Path | str | None = None) -> PlayerResolver:
    """A resolver over caller-supplied canonical rows (e.g. a saver's live
    ``public.players`` read) plus the committed snapshot's alias map and
    cross-ids. Aliases pointing at keys absent from ``players`` are ignored."""
    payload = load_registry_payload(path)
    return PlayerResolver(players, payload.get("aliases", []), payload.get("xrefs", {}),
                          meta={**payload.get("meta", {}), "players": "caller-supplied"})


# Saver reason vocabulary (review rows): unmatched -> no_match.
_SAVER_REASON = {"unmatched": "no_match", "ambiguous": "ambiguous",
                 "position_conflict": "position_conflict"}


def lookup_for_saver(resolver: PlayerResolver, name: Any, *, source: str,
                     pos: str | None = None, team: str | None = None,
                     source_id: Any = None, id_type: str | None = None
                     ) -> tuple[int | None, str | None]:
    """(player_key, None) or (None, reason) for a row a saver will WRITE.

    Fuzzy (provisional) matches are not written: the name is recorded in
    ``resolver.pending`` as provisional for the nightly reconcile, and the row
    goes to review until the match is verified ("never display unvalidated
    values"). Reasons: no_match | ambiguous | position_conflict.
    """
    res = resolver.resolve(name, source=source, pos=pos, team=team, source_id=source_id,
                           id_type=id_type, allow_provisional=False)
    if res.player_key is not None:
        return res.player_key, None
    return None, _SAVER_REASON.get(res.status, "no_match")


def clear_cache() -> None:
    _CACHE.clear()
    _PAYLOADS.clear()
