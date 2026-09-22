"""Sleeper loader: player DB cache, ID crosswalk, injury/news metadata.

Endpoints (all free, no auth):
  /state/nfl                    -> current season/week pointer
  /players/nfl                  -> 12k players, ID crosswalk (espn/yahoo/gsis/
                                   sportradar), injury_status, news_updated,
                                   depth_chart_position. 14MB: cached to disk,
                                   refreshed at most daily.
  /players/nfl/trending/add|drop -> waiver-wire interest counts (news proxy)

What it does:
  1. Refresh the local players cache if older than 20h.
  2. Crosswalk: match Sleeper players to our players table by gsis_id
     (via external_id_map, nflverse source), falling back to
     normalized name+team. Upsert sleeper/espn/yahoo/gsis/sportradar IDs
     into external_id_map.
  3. Merge injury_status, injury_body_part, news_updated,
     depth_chart_position into players.metadata.
  4. Load trending add/drop snapshots into trending table.

Usage: python3 loaders/sleeper.py [--skip-players] [--skip-trending]
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import uuid

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
DATA = os.path.join(BASE, "data")
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
import sbclient  # noqa: E402
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-mgmt/bin"))
import mgmt  # noqa: E402
from engine.snapshot import norm, load_players  # noqa: E402

UA = {"User-Agent": "football-signal/1.0"}
PLAYERS_CACHE = os.path.join(DATA, "sleeper_players.json")
CACHE_TTL = 20 * 3600


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def current_state():
    return get("https://api.sleeper.app/v1/state/nfl")


def players_cache(max_age=CACHE_TTL):
    if (os.path.exists(PLAYERS_CACHE)
            and time.time() - os.path.getmtime(PLAYERS_CACHE) < max_age):
        return json.load(open(PLAYERS_CACHE))
    data = get("https://api.sleeper.app/v1/players/nfl")
    open(PLAYERS_CACHE, "w").write(json.dumps(data))
    return data


def source_id(name):
    r = mgmt.query(f"select id from data_sources where name='{name}';")
    return r[0]["id"] if r else None


def load_crosswalk(sleeper_players):
    """Match Sleeper players to our players; upsert external IDs.

    Batched: preloads existing mappings, POSTs new ones in chunks, and
    merges metadata with one UPDATE per chunk (no per-player GET/PATCH).
    """
    import json as _json
    by_name, _, _ = load_players()
    # gsis -> player_id from existing nflverse mappings
    nflv = source_id("nflverse")
    rows = mgmt.query(
        f"select entity_id, external_id from external_id_map "
        f"where source_id='{nflv}' and entity_type='player';")
    gsis_map = {r["external_id"]: r["entity_id"] for r in rows}
    teams = {t["abbreviation"]: t["id"] for t in sbclient.get_all("teams")}

    sl_src = source_id("sleeper")
    espn_src = source_id("espn")
    yahoo_src = source_id("yahoo")

    # preload existing crosswalk rows to avoid per-player checks
    existing = set()
    for src in (sl_src, espn_src, yahoo_src):
        if not src:
            continue
        for r in mgmt.query(
                f"select external_id from external_id_map "
                f"where source_id='{src}' and entity_type='player';"):
            existing.add((src, r["external_id"]))

    id_rows, md_rows = [], []
    matched = 0
    for sid, sp in sleeper_players.items():
        pid = None
        gsis = sp.get("gsis_id")
        if gsis and gsis in gsis_map:
            pid = gsis_map[gsis]
        else:
            name = sp.get("full_name") or ""
            key = norm(name)
            if key in by_name:
                cand = by_name[key]
                st = (sp.get("team") or "").upper()
                pt = None
                if cand.get("team_id"):
                    pt = next((a for a, i in teams.items()
                               if i == cand["team_id"]), None)
                if not st or not pt or st == pt:
                    pid = cand["id"]
        if not pid:
            continue
        matched += 1
        for src, ext in ((sl_src, sid),
                         (espn_src, str(sp.get("espn_id")) if sp.get("espn_id") else None),
                         (yahoo_src, str(sp.get("yahoo_id")) if sp.get("yahoo_id") else None)):
            if not src or not ext or (src, ext) in existing:
                continue
            existing.add((src, ext))
            id_rows.append({"id": str(uuid.uuid4()), "source_id": src,
                            "entity_type": "player", "entity_id": pid,
                            "external_id": ext})
        md = {"sleeper": {
            "injury_status": sp.get("injury_status"),
            "injury_body_part": sp.get("injury_body_part"),
            "news_updated": sp.get("news_updated"),
            "depth_chart_position": sp.get("depth_chart_position")}}
        md_rows.append((pid, _json.dumps(md).replace("'", "''")))
    for i in range(0, len(id_rows), 200):
        sbclient.post("external_id_map", id_rows[i:i + 200])
    for i in range(0, len(md_rows), 200):
        vals = ",".join(
            f"('{pid}','{md}'::jsonb)" for pid, md in md_rows[i:i + 200])
        mgmt.query(
            f"UPDATE players AS p SET metadata = "
            f"COALESCE(p.metadata,'{{}}'::jsonb) || v.md "
            f"FROM (VALUES {vals}) AS v(id, md) WHERE p.id = v.id::uuid;")
    return {"matched": matched, "crosswalk_upserts": len(id_rows),
            "metadata_merges": len(md_rows)}


def load_injuries(sleeper_players):
    """Populate the injuries table from Sleeper injury flags.

    ESPN's public injuries endpoint is richer (reporter comments) but is
    Akamai-blocked from our egress; Sleeper gives status + body part +
    news_updated recency for 700+ flagged players, which covers the
    foundation requirement.
    """
    from datetime import datetime, timezone
    by_name, _, _ = load_players()
    existing = {(r["player_name"], r["team"], r["source"]): r["id"] for r in
                mgmt.query("select id, player_name, team, source from injuries;")}
    n_upd = n_new = 0
    now = datetime.now(timezone.utc).isoformat()
    upd_batch, new_batch = [], []
    for sid, sp in sleeper_players.items():
        status = sp.get("injury_status")
        if not status:
            continue
        name = (sp.get("full_name") or sid or "").strip()
        team = (sp.get("team") or "").upper() or None
        pid = None
        key = norm(name)
        if key in by_name:
            pid = by_name[key]["id"]
        nu = sp.get("news_updated")
        report_date = None
        if nu:
            try:
                report_date = datetime.fromtimestamp(
                    int(nu) / 1000, tz=timezone.utc).isoformat()
            except (ValueError, TypeError):
                pass
        row = {
            "player_id": pid, "player_name": name, "team": team,
            "position": sp.get("position"), "status": status,
            "body_part": sp.get("injury_body_part"),
            "report_date": report_date, "source": "sleeper",
            "fetched_at": now,
        }
        key = (name, team, "sleeper")
        if key in existing:
            upd_batch.append((existing[key], row))
        else:
            new_batch.append(row)
    # Write phase: chunked upsert on the table's real unique key
    # (player_name, team, source), covering updates and inserts in one path.
    # The old per-row PATCH loop issued 700+ sequential requests through the
    # egress proxy; a single stalled request wedged the whole run (one PATCH
    # landed, then zero table progress for 8+ minutes).
    #
    # NULL-team replace (2026-09-19): rows with NULL team can't match the
    # unique key (NULLs never conflict in Postgres), so the upsert always
    # INSERTs. The old PATCH-by-id path for NULL-team rows missed at least
    # one row (Drake Jackson's 2026-09-11 row was never patched while a
    # duplicate was inserted — root cause unknown), and duplicates
    # accumulate behind the dict key collision. Replace semantics instead:
    # delete every existing NULL-team Sleeper row for a name the feed
    # designates now, then insert the fresh row. Exactly one NULL-team row
    # per name survives.
    write_rows = [row for _rid, row in upd_batch] + new_batch
    null_names = {r["player_name"] for r in write_rows
                  if r.get("team") is None}
    if null_names:
        # Query fresh: `existing` holds only one id per dup key, and dupes
        # are exactly what we're removing.
        null_rows = mgmt.query(
            "SELECT id, player_name FROM injuries "
            "WHERE source='sleeper' AND team IS NULL;")
        replace_ids = [r["id"] for r in null_rows
                       if r["player_name"] in null_names]
        if replace_ids:
            id_list = ",".join(f"'{rid}'" for rid in replace_ids)
            mgmt.query(f"DELETE FROM injuries WHERE id IN ({id_list});")
    # Dedupe the whole batch up front: the Sleeper feed occasionally carries
    # two entries for the same (player_name, team, source), and copies that
    # land in different 200-row chunks would each post -> 409 against the
    # injuries_player_team_source_key unique index. Last row wins.
    seen = {}
    for row in write_rows:
        seen[(row["player_name"], row["team"], row["source"])] = row
    upsert_rows = list(seen.values())
    # Reported counts reflect the UNIQUE rows actually written (dedupe: last
    # row wins) -- the 2026-09-14 409-fix invariant. A dupe pair where both
    # copies are new counts once; a key already in the table counts as an
    # update.
    n_new = sum(1 for r in upsert_rows
                if (r["player_name"], r["team"], r["source"]) not in existing)
    n_upd = len(upsert_rows) - n_new
    for i in range(0, len(upsert_rows), 200):
        sbclient.post("injuries", upsert_rows[i:i + 200],
                      params="?on_conflict=player_name,team,source",
                      prefer="resolution=merge-duplicates")
    # Clear stale designations (2026-09-19, refined): the Sleeper feed is
    # the full player universe, so a player present with NO injury_status
    # has no current designation. An existing Sleeper row still carrying
    # one is stale — left alone it keeps gating signals (218 stale rows
    # cleared on 2026-09-19, e.g. Maliek Collins still Questionable after
    # the feed cleared him; his team also changed SF->CLE, so the match is
    # by normalized name, not (name, team)).
    #
    # Refinement (2026-09-19, second pass): the feed carries duplicate
    # player entries (same name, 2+ Sleeper ids — e.g. one with the team,
    # one teamless). The first version's "any ambiguity -> leave" rule let
    # stale designations survive behind a duplicate: Justin Jefferson sat
    # "Out" on CLE — he's on MIN and healthy — because two UNDESIGNATED
    # feed identities made the name "ambiguous". Per normalized name:
    #   - absent from the feed -> leave (feed hiccup, fail closed);
    #   - NO feed entry carries a designation -> the name has no live
    #     designation: delete every existing Sleeper row for the name.
    #     Ambiguity is irrelevant — there is no live designation to
    #     confuse (this catches the Justin Jefferson case);
    #   - exactly one feed identity, and it IS designated -> the upsert
    #     wrote (name, feed_team): delete existing rows for the name whose
    #     team differs (old-team rows, e.g. Jermar Jefferson's stale
    #     MIN/IR when the feed says teamless/Questionable);
    #   - multiple identities with at least one designation -> genuinely
    #     ambiguous which designation applies: leave (fail closed).
    from collections import defaultdict
    feed_by_name = defaultdict(list)
    for sid, sp in sleeper_players.items():
        fname = (sp.get("full_name") or sid or "").strip()
        team = (sp.get("team") or "").upper() or None
        feed_by_name[norm(fname)].append(
            (sid, bool(sp.get("injury_status")), team))
    exist_by_name = defaultdict(list)
    for (name, team, src), rid in existing.items():
        if src == "sleeper":
            exist_by_name[norm(name or "")].append((rid, team))
    clear_ids = set()
    for nname, rows in exist_by_name.items():
        entries = feed_by_name.get(nname)
        if not entries:
            continue
        designated = [(sid, team) for sid, hs, team in entries if hs]
        if not designated:
            clear_ids.update(rid for rid, _ in rows)
        elif len({sid for sid, _, _ in entries}) == 1:
            feed_team = designated[0][1]
            clear_ids.update(rid for rid, team in rows
                             if team != feed_team)
        # else: ambiguous — fail closed.
    n_cleared = 0
    if clear_ids:
        id_list = ",".join(f"'{rid}'" for rid in clear_ids)
        stale_rows = mgmt.query(
            f"SELECT id FROM injuries WHERE id IN ({id_list}) "
            f"AND status IS NOT NULL;")
        if stale_rows:
            # DELETE, not SET status=NULL: the injuries table has a NOT NULL
            # constraint on status, and a player with no live designation
            # should carry no designation row at all (2026-09-19: the NULL
            # write failed closed on the constraint mid-run).
            del_ids = ",".join(f"'{r['id']}'" for r in stale_rows)
            mgmt.query(f"DELETE FROM injuries WHERE id IN ({del_ids});")
            n_cleared = len(stale_rows)
    return {"updated": n_upd, "new": n_new,
            "upserted": len(upsert_rows), "cleared": n_cleared}


def load_trending(lookback_hours=24, limit=50):
    out = {"add": 0, "drop": 0}
    for direction in ("add", "drop"):
        items = get(f"https://api.sleeper.app/v1/players/nfl/trending/"
                    f"{direction}?lookback_hours={lookback_hours}&limit={limit}")
        if not items:
            continue
        by_name, _, _ = load_players()
        cache = json.load(open(PLAYERS_CACHE)) if os.path.exists(PLAYERS_CACHE) else {}
        batch = []
        for it in items:
            sid = str(it.get("player_id"))
            sp = cache.get(sid, {})
            name = sp.get("full_name") or sid
            pid = None
            if name in by_name or norm(name) in by_name:
                pid = (by_name.get(name) or by_name.get(norm(name)))["id"]
            batch.append({
                "id": str(uuid.uuid4()),
                "player_id": pid, "sleeper_id": sid,
                "player_name": name, "direction": direction,
                "count": it.get("count", 0),
                "lookback_hours": lookback_hours})
        for i in range(0, len(batch), 200):
            sbclient.post("trending", batch[i:i + 200])
        out[direction] = len(batch)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-players", action="store_true")
    ap.add_argument("--skip-trending", action="store_true")
    ap.add_argument("--skip-injuries", action="store_true")
    a = ap.parse_args()
    st = current_state()
    print(f"sleeper state: season {st['season']} week {st['week']} "
          f"({st['season_type']})")
    pl = players_cache()
    print(f"players cache: {len(pl)} players")
    if not a.skip_players:
        r = load_crosswalk(pl)
        print(f"crosswalk: {r}")
    if not a.skip_injuries:
        print(f"injuries: {load_injuries(pl)}")
    if not a.skip_trending:
        r = load_trending()
        print(f"trending: {r}")


if __name__ == "__main__":
    main()
