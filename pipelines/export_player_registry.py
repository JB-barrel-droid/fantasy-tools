#!/usr/bin/env python3
"""JEG-438: export the canonical player registry snapshot the resolver reads.

Reads public.players, public.teams, public.external_id_map (+ data_sources) and
public.player_name_aliases, and writes data/inputs/player_registry.json
(schema player-registry-v1). Deterministic: rows are sorted, so a run that
changes nothing changes nothing in the file but meta.exported_at.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python3 pipelines/export_player_registry.py

Fail-closed: fewer than MIN_PLAYERS players, a duplicate player_key, or an alias
pointing at an unknown key exits non-zero and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

from lib.player_resolver import REGISTRY_PATH, REGISTRY_SCHEMA, team_abbr  # noqa: E402

MIN_PLAYERS = 4000          # 4,646 rows on 2026-10-07
COLUMNS = ["player_key", "full_name", "position", "active", "team"]
ID_TYPE_BY_SOURCE = {"sleeper": "sleeper", "espn": "espn", "yahoo": "yahoo", "nflverse": "gsis"}
ALIAS_FIELDS = ("source", "source_player_name", "position", "source_player_id",
                "player_key", "status", "method", "confidence")


def _client():
    try:
        import sbclient  # noqa: PLC0415 - gh_sbclient shim in CI
    except ImportError:
        import gh_sbclient as sbclient  # noqa: PLC0415
    return sbclient


def build_registry(players, teams, xref_rows, sources, aliases, exported_at=None) -> dict:
    team_by_id = {t["id"]: team_abbr(t.get("abbreviation")) for t in teams}
    key_by_uuid = {}
    out_players = []
    seen = set()
    for p in players:
        key = p.get("player_key")
        if key is None:
            continue
        key = int(key)
        if key in seen:
            raise SystemExit(f"FAIL-CLOSED: duplicate player_key {key}")
        seen.add(key)
        key_by_uuid[p["id"]] = key
        meta = p.get("metadata") or {}
        team = team_abbr(meta.get("team")) or team_by_id.get(p.get("team_id"))
        out_players.append([key, (p.get("full_name") or "").strip(),
                            (p.get("position") or "").upper(), bool(p.get("active")), team])
    out_players.sort(key=lambda r: r[0])

    src_name = {s["id"]: s["name"] for s in sources}
    xrefs: dict[str, dict[str, int]] = {t: {} for t in ID_TYPE_BY_SOURCE.values()}
    for x in xref_rows:
        t = ID_TYPE_BY_SOURCE.get(src_name.get(x.get("source_id")))
        k = key_by_uuid.get(x.get("entity_id"))
        if t and k is not None and x.get("external_id") not in (None, ""):
            xrefs[t][str(x["external_id"]).strip()] = k
    xrefs = {t: dict(sorted(m.items())) for t, m in xrefs.items()}

    out_aliases = []
    for a in aliases:
        if a.get("player_key") is not None and int(a["player_key"]) not in seen:
            raise SystemExit(f"FAIL-CLOSED: alias {a.get('source_player_name')!r} -> unknown "
                             f"player_key {a['player_key']}")
        row = {f: a.get(f) for f in ALIAS_FIELDS}
        if row["confidence"] is not None:
            row["confidence"] = float(row["confidence"])
        out_aliases.append(row)
    out_aliases.sort(key=lambda r: (r["source"], r["source_player_name"].lower(), r["position"] or ""))

    status_counts: dict[str, int] = {}
    for a in out_aliases:
        status_counts[a["status"]] = status_counts.get(a["status"], 0) + 1
    return {
        "schema": REGISTRY_SCHEMA,
        "meta": {
            "exported_at": exported_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "supabase public.players + external_id_map + player_name_aliases",
            "n_players": len(out_players),
            "n_active": sum(1 for r in out_players if r[3]),
            "n_xrefs": {t: len(m) for t, m in xrefs.items()},
            "n_aliases": len(out_aliases),
            "alias_status": dict(sorted(status_counts.items())),
        },
        "columns": COLUMNS,
        "players": out_players,
        "xrefs": xrefs,
        "aliases": out_aliases,
    }


def content(payload: dict) -> dict:
    body = dict(payload)
    body["meta"] = {k: v for k, v in payload.get("meta", {}).items() if k != "exported_at"}
    return body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REGISTRY_PATH)
    args = ap.parse_args(argv)
    sb = _client()
    players = sb.get_all("players", "?select=id,player_key,full_name,position,active,team_id,metadata")
    teams = sb.get_all("teams", "?select=id,abbreviation")
    sources = sb.get_all("data_sources", "?select=id,name")
    xref_rows = sb.get_all("external_id_map",
                           "?select=id,source_id,entity_id,external_id&entity_type=eq.player")
    aliases = sb.get_all("player_name_aliases", "?select=id," + ",".join(ALIAS_FIELDS))
    payload = build_registry(players, teams, xref_rows, sources, aliases)
    if payload["meta"]["n_players"] < MIN_PLAYERS:
        print(f"FAIL-CLOSED: only {payload['meta']['n_players']} players (< {MIN_PLAYERS})", file=sys.stderr)
        return 1
    if args.out.exists():
        try:
            old = json.loads(args.out.read_text(encoding="utf-8"))
            if content(old) == content(payload):
                print(f"{args.out}: unchanged ({payload['meta']['n_players']} players)")
                return 0
        except ValueError:
            pass
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    # one player / alias per line keeps diffs reviewable
    text = (text.replace("],[", "],\n[").replace("},{", "},\n{"))
    args.out.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {args.out}: {json.dumps(payload['meta'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
