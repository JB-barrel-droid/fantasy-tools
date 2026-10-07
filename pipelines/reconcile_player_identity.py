#!/usr/bin/env python3
"""JEG-438: nightly player-identity reconcile.

Runs every night (pg_cron `player-identity-reconcile-nightly` dispatches
.github/workflows/player-identity-reconcile.yml). It turns temporary matches
into true ones:

  1. Universe sync. Pull Sleeper /players/nfl. Every rostered fantasy-position
     Sleeper player that public.players already holds (matched by an existing
     cross-id, or by an exact canonical name at the same position -- never
     fuzzy) gets its missing sleeper/espn/gsis cross-ids added to
     public.external_id_map. Nothing is inserted from this step alone, so
     Sleeper's stale "active" ghosts never enter the table.
  2. Re-resolve every non-verified alias (provisional / unmatched / review) in
     public.player_name_aliases with independent evidence only (exact names,
     verified aliases, cross-ids; fuzzy is switched off):
        found              -> verified (a provisional that disagrees is replaced
                              and its old key noted)
        Sleeper has exactly one active player of that name at that position
                           -> verified to that player's key; a player the
                              table does not hold yet is inserted (the only way
                              the universe grows, and only for names a source
                              actually uses)
        nothing, older than QUEUE_AFTER_DAYS -> review (the human queue)
  3. Record per-source counts in public.player_identity_reconcile_runs and
     return non-zero content status when open names exceed the alert limits.

Dry run (default) computes and prints everything and writes nothing.

    python3 pipelines/reconcile_player_identity.py --mode dry --summary-out /tmp/r.json
    python3 pipelines/reconcile_player_identity.py --mode write
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

from export_player_registry import ID_TYPE_BY_SOURCE, build_registry  # noqa: E402
from lib.player_resolver import (  # noqa: E402
    PlayerResolver, nickname_key, norm_key, registry_from_snapshot, team_abbr,
)

SLEEPER_URL = "https://api.sleeper.app/v1/players/nfl"
FANTASY_POSITIONS = ("QB", "RB", "WR", "TE", "K")
MIN_SLEEPER_PLAYERS = 2500
QUEUE_AFTER_DAYS = 3
OPEN_WINDOW_DAYS = 14
# "These should be extreme edge cases": alert above these open counts.
ALERT_PER_SOURCE = 5
ALERT_TOTAL = 15
OPEN_STATUSES = ("provisional", "unmatched", "review")


def _client():
    try:
        import sbclient  # noqa: PLC0415
    except ImportError:
        import gh_sbclient as sbclient  # noqa: PLC0415
    return sbclient


def pull_sleeper() -> dict:
    req = urllib.request.Request(SLEEPER_URL, headers={"User-Agent": "fantasy-tools/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def sleeper_rows(raw: dict) -> list[dict]:
    """Fantasy-position Sleeper players as flat dicts (cross-ids stripped of whitespace)."""
    out = []
    for sid, p in raw.items():
        pos = p.get("position") or (p.get("fantasy_positions") or [None])[0]
        name = (p.get("full_name") or f"{p.get('first_name') or ''} {p.get('last_name') or ''}").strip()
        if pos not in FANTASY_POSITIONS or not name:
            continue
        row = {"sleeper_id": str(sid), "name": name, "pos": pos, "team": team_abbr(p.get("team")),
               "active": bool(p.get("active")), "status": p.get("status")}
        for k, t in (("espn_id", "espn"), ("gsis_id", "gsis"), ("yahoo_id", "yahoo")):
            v = str(p.get(k) or "").strip()
            if v:
                row[t] = v
        out.append(row)
    return out


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def sleeper_key(resolver: PlayerResolver, s: dict) -> tuple[int | None, str]:
    """Existing player_key for a Sleeper player: cross-ids first, then an exact
    canonical name at the same position. Never fuzzy."""
    for t in ("sleeper", "gsis", "espn", "yahoo"):
        sid = s["sleeper_id"] if t == "sleeper" else s.get(t)
        if sid and sid in resolver.xrefs.get(t, {}):
            k = resolver.xrefs[t][sid]
            p = resolver.by_key.get(k)
            if p and p.position == s["pos"]:
                return k, f"xref:{t}"
    res = resolver.resolve(s["name"], source="sleeper", pos=s["pos"], team=s.get("team"),
                           allow_provisional=False, record=False)
    if res.status in ("verified", "exact"):
        return res.player_key, res.method
    return None, res.status


def plan_universe_sync(resolver: PlayerResolver, sleeper: list[dict]) -> list[dict]:
    """Cross-ids to add for rostered Sleeper players the table already holds."""
    adds = []
    for s in sleeper:
        if not s.get("team") or s.get("status") != "Active":
            continue
        key, how = sleeper_key(resolver, s)
        if key is None:
            continue
        for t in ("sleeper", "espn", "gsis", "yahoo"):
            ext = s["sleeper_id"] if t == "sleeper" else s.get(t)
            if not ext:
                continue
            known = resolver.xrefs.get(t, {})
            if ext in known:
                continue  # already mapped (to this or another key: never re-pointed here)
            if key in set(known.values()):
                continue  # this player already has an id of this type
            adds.append({"id_type": t, "external_id": ext, "player_key": key,
                         "matched_by": how, "name": s["name"]})
    # one id per (type, external_id); drop ids two players would claim
    claims = Counter((a["id_type"], a["external_id"]) for a in adds)
    return [a for a in adds if claims[(a["id_type"], a["external_id"])] == 1]


def sleeper_name_index(sleeper: list[dict]) -> dict[tuple[str, str], list[dict]]:
    idx: dict[tuple[str, str], list[dict]] = {}
    for s in sleeper:
        if not s["active"]:
            continue
        k = norm_key(s["name"])
        for key in dict.fromkeys((k, nickname_key(k))):
            idx.setdefault((key, s["pos"]), []).append(s)
    return idx


def plan_alias_reconcile(resolver: PlayerResolver, aliases: list[dict], sleeper: list[dict],
                         now: datetime) -> list[dict]:
    """One action per non-verified alias row: promote | insert_player | queue | keep."""
    sidx = sleeper_name_index(sleeper)
    actions = []
    for a in aliases:
        if a.get("status") not in OPEN_STATUSES:
            continue
        name, pos, source = a["source_player_name"], (a.get("position") or None), a["source"]
        old_key = a.get("player_key")
        res = resolver.resolve(name, source=source, pos=pos, team=a.get("team"),
                               source_id=a.get("source_player_id"),
                               allow_provisional=False, record=False)
        act = {"id": a.get("id"), "source": source, "name": name, "position": a.get("position") or "",
               "old_status": a["status"], "old_key": old_key}
        if res.status in ("verified", "exact"):
            act.update(action="promote", player_key=res.player_key,
                       method=f"nightly:{res.method}",
                       note=(None if old_key in (None, res.player_key)
                             else f"provisional key {old_key} replaced by {res.method}"))
            actions.append(act)
            continue
        k = norm_key(name)
        cands = []
        if pos:
            for key in dict.fromkeys((k, nickname_key(k))):
                cands.extend(sidx.get((key, pos), []))
        uniq = list({c["sleeper_id"]: c for c in cands}.values())
        if len(uniq) == 1:
            s = uniq[0]
            key, how = sleeper_key(resolver, s)
            if key is not None:
                act.update(action="promote", player_key=key, method=f"nightly:sleeper+{how}",
                           note=(None if old_key in (None, key)
                                 else f"provisional key {old_key} replaced by sleeper {s['sleeper_id']}"))
            else:
                act.update(action="insert_player", sleeper=s, method="nightly:sleeper-new-player")
            actions.append(act)
            continue
        first = _parse_ts(a.get("first_seen_at")) or now
        if a["status"] != "review" and now - first >= timedelta(days=QUEUE_AFTER_DAYS):
            act.update(action="queue", note=f"no independent match after {QUEUE_AFTER_DAYS} days"
                       + (f"; {len(uniq)} Sleeper namesakes" if len(uniq) > 1 else ""))
        else:
            act.update(action="keep")
        actions.append(act)
    return actions


def open_counts(aliases: list[dict], actions: list[dict], now: datetime) -> dict[str, dict[str, int]]:
    """Per-source counts of open names (seen in the last OPEN_WINDOW_DAYS) after the actions."""
    after = {a.get("id"): a for a in aliases}
    status = {i: a.get("status") for i, a in after.items()}
    for act in actions:
        if act["action"] in ("promote", "insert_player"):
            status[act["id"]] = "verified"
        elif act["action"] == "queue":
            status[act["id"]] = "review"
    out: dict[str, dict[str, int]] = {}
    for i, a in after.items():
        seen = _parse_ts(a.get("last_seen_at")) or now
        st = status[i]
        c = out.setdefault(a["source"], {s: 0 for s in ("verified",) + OPEN_STATUSES})
        if st == "verified":
            c["verified"] += 1
        elif st in OPEN_STATUSES and now - seen <= timedelta(days=OPEN_WINDOW_DAYS):
            c[st] += 1
    return out


def alert_state(counts: dict[str, dict[str, int]]) -> tuple[bool, list[str]]:
    msgs = []
    total = 0
    for src, c in sorted(counts.items()):
        n = sum(c.get(s, 0) for s in OPEN_STATUSES)
        total += n
        if n > ALERT_PER_SOURCE:
            msgs.append(f"{src}: {n} open names (> {ALERT_PER_SOURCE})")
    if total > ALERT_TOTAL:
        msgs.append(f"all sources: {total} open names (> {ALERT_TOTAL})")
    return (not msgs), msgs


# ---------------------------------------------------------------------------
# Writes (mode=write only)
# ---------------------------------------------------------------------------

def apply_actions(sb, live: dict, universe_adds: list[dict], actions: list[dict], now_iso: str) -> dict:
    src_id = {s["name"]: s["id"] for s in live["sources"]}
    type_to_source = {v: k for k, v in ID_TYPE_BY_SOURCE.items()}
    uuid_by_key = {int(p["player_key"]): p["id"] for p in live["players"]}
    team_id_by_abbr = {team_abbr(t.get("abbreviation")): t["id"] for t in live["teams"]}
    league_id = next((p.get("league_id") for p in live["players"] if p.get("league_id")), None)
    stats = Counter()

    def add_xref(t, ext, key):
        src = src_id.get(type_to_source.get(t))
        if not src or key not in uuid_by_key:
            return
        sb.post("external_id_map", [{"source_id": src, "entity_type": "player",
                                      "entity_id": uuid_by_key[key], "external_id": ext}],
                params="?on_conflict=source_id,entity_type,external_id",
                prefer="resolution=ignore-duplicates,return=minimal")
        stats["xrefs_added"] += 1

    for a in universe_adds:
        add_xref(a["id_type"], a["external_id"], a["player_key"])

    next_key = max(uuid_by_key) + 1
    for act in actions:
        if act["action"] == "insert_player":
            s = act["sleeper"]
            row = {"player_key": next_key, "full_name": s["name"], "position": s["pos"],
                   "active": True, "team_id": team_id_by_abbr.get(s.get("team")),
                   "league_id": league_id,
                   "metadata": {"team": s.get("team"), "added": f"jeg438 nightly {now_iso[:10]}: "
                                f"named by {act['source']}, Sleeper {s['sleeper_id']}"}}
            created = sb.post("players", [row], prefer="return=representation")
            if created:
                uuid_by_key[next_key] = created[0]["id"]
                for t in ("sleeper", "espn", "gsis", "yahoo"):
                    ext = s["sleeper_id"] if t == "sleeper" else s.get(t)
                    if ext:
                        add_xref(t, ext, next_key)
                act["player_key"] = next_key
                stats["players_added"] += 1
                next_key += 1
            else:
                continue
        if act["action"] in ("promote", "insert_player"):
            body = {"player_key": act["player_key"], "status": "verified", "method": act["method"],
                    "verified_at": now_iso, "verified_by": "player-identity-reconcile"}
            if act.get("note"):
                body["notes"] = act["note"]
            sb.patch("player_name_aliases", body, params=f"?id=eq.{act['id']}")
            stats["promoted"] += 1
        elif act["action"] == "queue":
            sb.patch("player_name_aliases", {"status": "review", "notes": act.get("note")},
                     params=f"?id=eq.{act['id']}")
            stats["queued"] += 1
    return dict(stats)


def load_live(sb) -> dict:
    return {
        "players": sb.get_all("players", "?select=id,player_key,full_name,position,active,team_id,league_id,metadata"),
        "teams": sb.get_all("teams", "?select=id,abbreviation"),
        "sources": sb.get_all("data_sources", "?select=id,name"),
        "xrefs": sb.get_all("external_id_map", "?select=id,source_id,entity_id,external_id&entity_type=eq.player"),
        "aliases": sb.get_all("player_name_aliases", "?select=*"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("dry", "write"), default="dry")
    ap.add_argument("--summary-out", type=Path)
    ap.add_argument("--sleeper-file", type=Path, help="saved /players/nfl response instead of the API")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    sb = _client()
    live = load_live(sb)
    resolver = registry_from_snapshot(build_registry(
        live["players"], live["teams"], live["xrefs"], live["sources"], live["aliases"]))
    raw = json.loads(args.sleeper_file.read_text()) if args.sleeper_file else pull_sleeper()
    sleeper = sleeper_rows(raw)
    if len(sleeper) < MIN_SLEEPER_PLAYERS:
        print(f"FAIL-CLOSED: Sleeper returned {len(sleeper)} fantasy players (< {MIN_SLEEPER_PLAYERS})",
              file=sys.stderr)
        return 1

    universe_adds = plan_universe_sync(resolver, sleeper)
    actions = plan_alias_reconcile(resolver, live["aliases"], sleeper, now)
    stats = {}
    if args.mode == "write":
        stats = apply_actions(sb, live, universe_adds, actions, now_iso)
        live["aliases"] = sb.get_all("player_name_aliases", "?select=*")
        counts = open_counts(live["aliases"], [], now)
    else:
        counts = open_counts(live["aliases"], actions, now)
    ok, msgs = alert_state(counts)

    by_src = Counter((a["source"], a["action"]) for a in actions)
    if args.mode == "write":
        rows = [{
            "run_label": now_iso, "source": src,
            "total_aliases": sum(c.values()), "verified": c["verified"],
            "provisional": c["provisional"], "unmatched": c["unmatched"], "review": c["review"],
            "promoted": by_src[(src, "promote")] + by_src[(src, "insert_player")],
            "queued": by_src[(src, "queue")],
            "players_added": by_src[(src, "insert_player")],
            "xrefs_added": stats.get("xrefs_added", 0) if src == "*" else 0,
            "detail": {"alert": msgs, "universe_xref_candidates": len(universe_adds)},
        } for src, c in sorted(counts.items())]
        if rows:
            sb.post("player_identity_reconcile_runs", rows, prefer="return=minimal")

    summary = {
        "generated_at": now_iso, "mode": args.mode, "ok": ok, "alerts": msgs,
        "sleeper_players": len(sleeper), "universe_xref_adds": len(universe_adds),
        "actions": Counter(a["action"] for a in actions), "applied": stats,
        "open_counts": counts,
        "action_rows": [{k: v for k, v in a.items() if k != "sleeper"} for a in actions
                        if a["action"] != "keep"],
        "universe_xref_sample": universe_adds[:50],
    }
    text = json.dumps(summary, indent=2, default=str)
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("mode", "ok", "alerts", "sleeper_players",
                                              "universe_xref_adds", "actions", "applied")},
                     default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
