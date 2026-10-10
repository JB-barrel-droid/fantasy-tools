"""ESPN / Sleeper player ids -> public.players (player_key, uuid), JEG-521 G4.

Ids first, names last, never a guess:

  1. Sleeper id -> players.metadata.sleeper_id (rows the JEG-502 refresh added).
  2. Sleeper id -> gsis id (Sleeper identity base) -> players.metadata.gsis_id
     (the nflverse-loaded rows; 4,613 of them carry it).
  3. ESPN id -> Sleeper id through the Sleeper identity base's espn_id, then 1-2.
  4. The canonical name resolver (canonical_players.resolve, position-checked),
     the rule every saver uses (JEG-438).

An id that maps to two players, or a resolved player at another position, is
reported and left out. public.external_id_map is NOT used for ESPN: on
2026-10-09 it maps two different ESPN ids to Josh Allen's player_key (the
quarterback and the linebacker).
"""
from __future__ import annotations

import canonical_players


class PlayerIndex:
    def __init__(self, players: list[dict], sleeper_base: dict | None = None,
                 registry=None):
        self.by_key = {}
        self.by_gsis: dict[str, list[dict]] = {}
        self.by_sleeper: dict[str, list[dict]] = {}
        for r in players:
            if r.get("player_key") is None:
                continue
            e = {"player_key": int(r["player_key"]), "id": r.get("id"),
                 "full_name": r.get("full_name") or "",
                 "position": (r.get("position") or "").upper(),
                 "active": bool(r.get("active", True))}
            self.by_key[e["player_key"]] = e
            md = r.get("metadata") or {}
            if md.get("gsis_id"):
                self.by_gsis.setdefault(str(md["gsis_id"]), []).append(e)
            if md.get("sleeper_id"):
                self.by_sleeper.setdefault(str(md["sleeper_id"]), []).append(e)
        base = (sleeper_base or {}).get("by_sleeper_id") or {}
        self.sleeper = base
        self.espn_to_sleeper: dict[str, list[str]] = {}
        for sid, rec in base.items():
            if rec.get("espn_id"):
                self.espn_to_sleeper.setdefault(str(rec["espn_id"]), []).append(str(sid))
        self.registry = registry if registry is not None else canonical_players.Registry(
            [{"player_key": e["player_key"], "id": e["id"], "full_name": e["full_name"],
              "position": e["position"], "active": e["active"]} for e in self.by_key.values()])

    @staticmethod
    def _one(cands, pos):
        uniq = {c["player_key"]: c for c in cands}
        if len(uniq) != 1:
            return None, ("ambiguous" if uniq else "none")
        c = next(iter(uniq.values()))
        if pos and c["position"] and c["position"] != pos:
            return None, f"position {c['position']}"
        return c, "ok"

    def resolve_sleeper(self, sleeper_id, name="", pos=""):
        """-> (entry, how) or (None, reason)."""
        sid = str(sleeper_id)
        if sid in self.by_sleeper:
            e, why = self._one(self.by_sleeper[sid], pos)
            if e:
                return e, "sleeper_id"
            if why != "none":
                return None, f"sleeper_id {why}"
        gsis = (self.sleeper.get(sid) or {}).get("gsis_id")
        if gsis and gsis in self.by_gsis:
            e, why = self._one(self.by_gsis[gsis], pos)
            if e:
                return e, "gsis_id"
            return None, f"gsis_id {why}"
        return self._by_name(name or (self.sleeper.get(sid) or {}).get("name", ""), pos)

    def resolve_espn(self, espn_id, name="", pos=""):
        sids = self.espn_to_sleeper.get(str(espn_id)) or []
        hits, reasons = {}, []
        for sid in sids:
            e, how = self.resolve_sleeper(sid, "", pos)
            if e:
                hits[e["player_key"]] = (e, "espn_id->" + how)
            else:
                reasons.append(how)
        if len(hits) == 1:
            return next(iter(hits.values()))
        if len(hits) > 1:
            return None, "espn_id ambiguous"
        return self._by_name(name, pos)

    def _by_name(self, name, pos):
        if not name:
            return None, "no id match, no name"
        key, why = canonical_players.resolve_with_reason(
            name, position=pos or None, registry=self.registry)
        if key is None:
            return None, f"name: {why}"
        return self.by_key.get(int(key)), "name"
