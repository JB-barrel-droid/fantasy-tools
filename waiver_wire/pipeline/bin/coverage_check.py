#!/usr/bin/env python3
"""Player-universe coverage check (fail-closed audit).

For every dashboard, verifies that every player in its source references is
covered. Run daily; exit 0 = all PASS (warnings allowed), exit 1 = any FAIL.
Writes lottery/results/coverage_<date>.json.

Checks
  C1 norm-fresh   fp_season_latest_norm MAX(snapshot_date) ==
                  fp_season_projections MAX(snapshot_date). Catches the
                  stale-derived-table class (the chart builds from the norm
                  table, not the raw snapshot table).
  C2 key-dedup    Every skill-position row of v_fp_season_latest survives the
                  builder's player_key dedup into fp_season_latest_norm
                  (canonical identity 2026-09-18).
                  Key collisions on the same human are OK (info).
  C3 chart-build  Every fp_season_latest_norm row is in trade-value/players.json.
  C4 legs-seed    Every players.json player is in the Monday leg universe
                  (legs are chart-seeded; leg-only extras are info).
                  K/DST missing from legs = WARN until first seeding (C8/C9
                  own the chain); after the legs have contained any K/DST, a
                  later absence = FAIL (seeding regression).
  C5 sources      Every FantasyCalc-cached + USA Today player is in the
                  sources dashboard display (source-driven; complete by
                  construction -- guards builder regressions).
  C6 waiver-trends Every Sleeper trending skill player with >=15000 adds is in
                  the waiver pool (waiver_boundary.canonical_pool -- the real
                  pool logic, not a reimplementation).
  C7 waiver-espn  Every ESPN roster%>=15 skill player is in the waiver pool.
  C8 kicker-chain Every kicker in v_fp_season_kdst_latest is in players.json
                  and in the Monday leg universe (legs seed K at the next
                  market step; missing legs = WARN until then).
  C9 dst-chain    Every defense in v_fp_season_kdst_latest is in players.json
                  and in the Monday leg universe (same WARN-then-PASS as C8).

Position filtering for C6/C7 uses the trends panel + pool + chart; names with
no resolvable skill position are reported as UNRESOLVED (warning), never FAIL.

FAIL verdicts are triaged per the miss protocol: fix the class, add a
deterministic rule/test, rerun affected players x scorings + downstream
outputs, report deltas beyond the trigger.
"""
import glob
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

BIN = Path(__file__).resolve().parent
LOT = BIN.parent
sys.path.insert(0, str(BIN))
from chart_paths import CHART_DIR  # noqa: E402
TRADE_VALUE = CHART_DIR
WTR = LOT.parent / "waiver-trends" / "results"

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "workspace", "skills", "supabase-mgmt", "bin"))
sys.path.insert(0, str(LOT / "engine"))

from mgmt import query  # noqa: E402  (Supabase management API)
# Canonical identity (2026-09-18): coverage checks join on numeric
# player_key, not normalized names.
import waiver_boundary as WB  # noqa: E402  (real waiver pool logic)
# Naming-table resolver (2026-09-19): engine/canonical_players resolves
# source spellings to the Supabase players player_key. Optional import:
# C5 falls back to string compare when it is unavailable.
try:
    from canonical_players import (  # noqa: E402
        load_registry as _cp_load, resolve as _cp_resolve)
    _CP_OK = True
except Exception as _cp_err:  # noqa: F841
    print("WARNING: canonical_players unavailable (%s) - C5 falls back to "
          "string compare" % _cp_err, file=sys.stderr)
    _cp_load = _cp_resolve = None
    _CP_OK = False

SKILL_POS = ("QB", "RB", "WR", "TE")
TREND_ADDS_FLOOR = 15000
ESPN_ROSTER_FLOOR = 15.0
SUFFIXES = ("jr", "sr", "ii", "iii", "iv", "v")


def canon(n):
    """Suffix-stripped lowercase norm for cross-source comparison."""
    t = re.sub(r"[^a-z ]", "", str(n or "").lower()).strip()
    p = t.split()
    while p and p[-1] in SUFFIXES:
        p.pop()
    return " ".join(p)


def latest(pattern):
    files = sorted(glob.glob(pattern))
    return Path(files[-1]) if files else None


def classify_source_row(name, pos, cp_reg, disp_keys, disp_c):
    """Classify one (source, name, pos) row against the sources display.

    Returns "covered" (resolves to a displayed player_key, or matches a
    display string when the resolver is unavailable), "outside" (resolves
    to a real player_key outside the chart universe -- the dashboard drops
    these by design), or "missing" (unresolvable and string-absent --
    fail-closed).
    """
    resolve = globals().get("_cp_resolve")
    key = resolve(name, position=pos, registry=cp_reg) if resolve and cp_reg else None
    if key is not None:
        return "covered" if int(key) in disp_keys else "outside"
    return "covered" if canon(name) in disp_c else "missing"


def dedupe_espn_lookup(lk):
    """Collapse ESPN's deliberate double-keying to one entry per human.

    build_lookup keys each human under both normalizations ("michael
    pittman" + "michael pittman jr") with the same pct by construction:
    same suffix-stripped base + same pct = same human, keep the base key.
    Different pcts = different humans, never merged.
    """
    seen, items = {}, []
    for name in sorted(lk):
        b, p = canon(name), lk[name]
        if b in seen and seen[b][1] == p:
            continue
        seen[b] = (name, p)
        items.append((name, p))
    return items


def espn_bridge(pool_keys, ident):
    """Registry-target -> pool pid, mirroring waiver_boundary._espn_roster.

    The identity registry snapshot's canonical targets can predate chart
    renames ("cam skattebo" -> "cameron skattebo"); the pipeline bridges
    those targets back to the pool pid so ESPN roster% still attaches.
    """
    bridge = {}
    for _pid in pool_keys:
        _c = ident.canon(_pid)
        if _c != _pid and _c not in pool_keys:
            bridge[_c] = _pid
    return bridge


def espn_pool_pid(name, pool, ident, bridge):
    """Resolve an ESPN lookup name to a pool pid, mirroring the pipeline.

    Returns the pool pid, or None when the name does not resolve.
    Mirrors waiver_boundary._espn_roster: the IdentityMap canon plus the
    registry-target bridge. No suffix guessing here -- ESPN's deliberate
    double-keying is deduped by the caller before resolution, so an
    unresolved suffix variant is a genuine miss, never silently merged
    into a different human.
    """
    ck = ident.canon(WB.norm_name(name))
    if ck in pool:
        return ck
    return bridge.get(ck)


class Check:
    def __init__(self):
        self.results = {}

    def record(self, cid, name, verdict, detail="", items=None):
        self.results[cid] = {
            "name": name, "verdict": verdict, "detail": detail,
            "items": items or [],
        }

    def fail(self, cid, name, detail="", items=None):
        self.record(cid, name, "FAIL", detail, items)

    def ok(self, cid, name, detail="", items=None):
        self.record(cid, name, "PASS", detail, items)

    def warn(self, cid, name, detail="", items=None):
        self.record(cid, name, "WARN", detail, items)


def pos_map(pool, trends):
    """name canon -> position from pool, trends panel, chart."""
    m = {}
    for k, v in pool.items():
        m.setdefault(canon(k), v.get("pos"))
    for k, v in trends.items():
        m.setdefault(canon(k), (v or {}).get("pos"))
    chart = json.loads((TRADE_VALUE / "players.json").read_text())["players"]
    for p in chart:
        m.setdefault(canon(p["name"]), p.get("pos"))
    return m


def main():
    c = Check()

    # ---- C1: norm table freshness ----
    r = query("SELECT MAX(snapshot_date) AS d FROM fp_season_projections")[0]["d"]
    r2 = query("SELECT MAX(snapshot_date) AS d FROM fp_season_latest_norm")[0]["d"]
    if str(r2) == str(r):
        c.ok("C1", "norm-fresh",
             f"fp_season_latest_norm is current (snapshot {r2})")
    else:
        c.fail("C1", "norm-fresh",
               f"STALE: norm table at {r2}, projections at {r}. "
               "Run football-signal/bin/build_blended_vorp_inputs.py before "
               "the chart build (wired as step 1b of the 08:00 chart cron).")

    # ---- C2: norm dedup keeps every real player ----
    latest_proj = query("SELECT MAX(snapshot_date) AS d FROM fp_season_projections")[0]["d"]
    rows = query(
        "SELECT v.player_id, p.player_key AS player_key, v.position, v.proj_half_ppr, p.full_name "
        "FROM v_fp_season_latest v JOIN players p ON p.id = v.player_id "
        f"WHERE v.snapshot_date = '{latest_proj}'")
    # Keyed by canonical player_key (2026-09-18): players.player_key (bigint)
    # is the canonical numeric key; p.id is the row UUID.
    expected, dupes = {}, []
    for r_ in rows:
        if not r_["full_name"] or r_["position"] not in SKILL_POS:
            continue
        kk = r_.get("player_key")
        if kk is None:
            continue
        prev = expected.get(kk)
        if prev is None:
            expected[kk] = r_
        else:
            # same key twice: keep the builder's winner (max proj_half_ppr)
            if float(r_["proj_half_ppr"] or 0) > float(prev["proj_half_ppr"] or 0):
                dupes.append((kk, prev["full_name"], r_["full_name"]))
                expected[kk] = r_
            else:
                dupes.append((kk, r_["full_name"], prev["full_name"]))
    latest_snap = query("SELECT MAX(snapshot_date) AS d FROM fp_season_latest_norm")[0]["d"]
    actual = {int(r_["player_key"]) for r_ in
              query("SELECT player_key FROM fp_season_latest_norm"
                    " WHERE player_key IS NOT NULL"
                    f" AND snapshot_date = '{latest_snap}'")}
    norm_humans = {canon(r_["full_name"]) for r_ in
                   query("SELECT p.full_name FROM fp_season_latest_norm n"
                         " JOIN players p ON p.player_key = n.player_key"
                         " WHERE n.player_key IS NOT NULL"
                         f" AND n.snapshot_date = '{latest_snap}'")}
    # Same-human duplicate registry keys are not real drops: the builder
    # keeps one key per human, so the loser's key is expected to be absent
    # while the human survives under another key.
    dropped = sorted(kk for kk in set(expected) - actual
                     if canon(expected[kk]["full_name"]) not in norm_humans)
    dupe_keys = sorted(kk for kk in set(expected) - actual
                       if canon(expected[kk]["full_name"]) in norm_humans)
    dupe_items = [f"{kk}: kept {w} over {l}" for kk, l, w in dupes[:10]]
    dupe_items += [f"{kk} ({expected[kk]['full_name']}): same-human dupe, "
                   f"survives under another key" for kk in dupe_keys[:10]]
    if not dropped:
        c.ok("C2", "key-dedup",
             f"all {len(expected)} skill keys survive "
             f"({len(dupes)} key collisions, {len(dupe_keys)} same-human dupes)",
             items=dupe_items)
    else:
        c.fail("C2", "key-dedup",
               f"{len(dropped)} players dropped by the key build",
               items=[f"{kk} ({expected[kk]['full_name']})" for kk in dropped]
               + dupe_items)

    # ---- C3: chart build covers the norm table ----
    chart = json.loads((TRADE_VALUE / "players.json").read_text())
    chart_keys = {p.get("player_key") for p in chart["players"]
                  if p.get("player_key") is not None}
    chart_humans = {canon(p["name"]) for p in chart["players"]}
    # Compare the norm table's keys directly (not the view-derived
    # expected set); same-human key variants are informational, only
    # humans entirely absent from the chart count as missing.
    key_names = {int(r_["player_key"]): r_["full_name"] for r_ in
                 query("SELECT p.player_key, p.full_name"
                       " FROM fp_season_latest_norm n"
                       " JOIN players p ON p.player_key = n.player_key"
                       " WHERE n.player_key IS NOT NULL"
                       f" AND n.snapshot_date = '{latest_snap}'")}
    missing_chart = sorted(kk for kk in set(actual) - chart_keys)
    missing_humans = sorted(kk for kk in missing_chart
                            if canon(key_names.get(kk, "")) not in chart_humans)
    dupe_chart = [kk for kk in missing_chart if kk not in missing_humans]
    if not missing_humans:
        c.ok("C3", "chart-build",
             f"players.json covers all {len(actual)} norm players "
             f"(n_players={chart['meta'].get('n_players')}"
             f", {len(dupe_chart)} same-human key variants)",
             items=[f"{kk} ({key_names.get(kk)}): in chart under another key"
                    for kk in dupe_chart[:10]])
    else:
        c.fail("C3", "chart-build",
               f"{len(missing_humans)} norm players missing from players.json",
               items=[f"{kk} ({key_names.get(kk)})" for kk in missing_humans]
               + [f"{kk} ({key_names.get(kk)}): in chart under another key"
                  for kk in dupe_chart[:10]])

    # ---- C4: Monday legs cover every chart player ----
    # Canonical identity (2026-09-18): the join is on numeric player_key
    # via the shared registry, not normalized names -- the legs pipeline's
    # naming-table renames ("cam skattebo" -> canonical "cameron skattebo")
    # must not read as missing players. Leg keys that do not resolve fall
    # back to name-canonical comparison (fail-safe: a genuine miss still
    # flags, never silently passes).
    leg_keys, leg_name_canons = set(), set()
    leg_label = None
    for pat in ("reassessed_values_*_half.json", "current_values_*_half.json",
                "imputed_proj_half.json"):
        f = latest(str(LOT / "results" / pat))
        if f:
            d = json.loads(f.read_text())
            recs = d.get("players") or d.get("records") or d
            for k, v in recs.items():
                cands = [k]
                if isinstance(v, dict):
                    cands += [v.get("display_name"), v.get("name"),
                              (v.get("debug") or {}).get("canonical_key")]
                resolved = None
                if _CP_OK:
                    for n in cands:
                        if not n:
                            continue
                        try:
                            resolved = _cp_resolve(n)
                        except Exception:
                            resolved = None
                        if resolved is not None:
                            break
                if resolved is not None:
                    leg_keys.add(int(resolved))
                else:
                    leg_name_canons |= {canon(n) for n in cands if n}
            leg_label = f.name
            break
    if not leg_keys and not leg_name_canons:
        c.fail("C4", "legs-seed", "no Monday leg file found")
    else:
        chart_info = {}
        for p in chart["players"]:
            kk = p.get("player_key")
            proj = max(abs(p["blend_ros"]["standard"] or 0),
                       abs(p["blend_ros"]["half_ppr"] or 0),
                       abs(p["blend_ros"]["ppr"] or 0))
            # Without the registry (import failure) the legs side can only
            # offer name canons, so key the chart side by name too -- the
            # old name-join behavior, strictly fail-safe.
            kk = kk if (isinstance(kk, int) and _CP_OK) else canon(p["name"])
            chart_info[kk] = (p["name"], p.get("pos"), proj)
        chart_keyed = {k for k in chart_info if isinstance(k, int)}
        chart_named = {k for k in chart_info if not isinstance(k, int)}
        chart_name_canons = {canon(v[0]) for v in chart_info.values()}
        missing = sorted(
            k for k in chart_keyed
            if k not in leg_keys
            and canon(chart_info[k][0]) not in leg_name_canons)
        missing += sorted(k for k in chart_named if k not in leg_name_canons)
        extras = (len(leg_keys - chart_keyed)
                  + len(leg_name_canons - chart_name_canons))
        # K/DST legs seed at the next market step (C8/C9 own that chain), so
        # a K/DST absence is expected-pending, never a C4 FAIL -- projection>0
        # is not a "should be in legs" test for K/DST (2026-09-16: 64 K/DST
        # with projections tripped this). Fail-closed: once the legs have
        # contained ANY K/DST, a later absence is a seeding regression -> FAIL.
        seeded_before = any(chart_info.get(k, (None, None, 0))[1]
                             in ("K", "DST") for k in leg_keys)
        kdst_missing = [m for m in missing
                        if chart_info[m][1] in ("K", "DST")]
        kdst_regressed = [m for m in kdst_missing if seeded_before]
        kdst_pending = [m for m in kdst_missing if not seeded_before]
        real = [m for m in missing
                if chart_info[m][2] > 0
                and chart_info[m][1] not in ("K", "DST")] + kdst_regressed
        pending = [m for m in missing if m not in real]
        disp = {m: chart_info[m][0] for m in missing}
        if not missing:
            c.ok("C4", "legs-seed",
                 f"{leg_label} covers all {len(chart_info)} chart players "
                 f"(+{extras} leg-only extras)")
        elif not real:
            c.warn("C4", "legs-seed",
                   f"{len(pending)} chart players not yet in {leg_label} "
                   f"({len(kdst_pending)} K/DST seed at the next market step; "
                   "no numeric impact)",
                   items=[disp[p] + (" (K/DST, seed-next-step)"
                                     if chart_info[p][1] in ("K", "DST")
                                     else " (0-proj, pending)")
                          for p in pending])
        else:
            c.fail("C4", "legs-seed",
                   f"{len(real)} chart players missing from {leg_label}",
                   items=[disp[p] for p in real]
                   + [disp[p] + (" (K/DST, seed-next-step)"
                                 if chart_info[p][1] in ("K", "DST")
                                 else " (0-proj, pending)")
                      for p in pending])

    # ---- C5: sources dashboard covers FC + USAT ----
    # Resolution rule (naming-table, 2026-09-19): the dashboard resolves
    # source rows through engine/canonical_players to numeric player_key
    # (resolve_source_rows in build_sources_dashboard); the check mirrors
    # that, joining on player_key via the display's player_keys map, never
    # on raw name strings. "Kenny Gainwell" (FC) vs "Kenneth Gainwell"
    # (display) is a nickname, not a miss. Names the resolver cannot place
    # fall back to the string compare (fail-closed: still flagged absent).
    sdata = json.loads((LOT / "results" / "sources_data.json").read_text())
    disp = sdata["display"]
    disp_c = {canon(k) for k in disp}
    disp_keys = set()
    try:
        disp_keys = {int(v) for v in sdata.get("player_keys", {}).values()}
    except (TypeError, ValueError):
        pass
    cp_reg = None
    if _CP_OK:
        try:
            cp_reg = _cp_load()
        except Exception as _e:
            print("WARNING: canonical registry load failed (%s) - C5 falls "
                  "back to string compare" % _e, file=sys.stderr)
    src_rows = []  # (source, name, pos)
    for f in glob.glob(str(LOT / "data" / "sources_cache" / "fantasycalc_*.json")):
        try:
            d = json.loads(Path(f).read_text())
            for row in d.get("rows", []):
                nm = row.get("name") or row.get("player")
                if nm:
                    src_rows.append(("fantasycalc", nm, row.get("pos")))
        except Exception:
            pass
    _USAT_POS = {"quarterback": "QB", "running back": "RB",
                 "wide receiver": "WR", "tight end": "TE"}
    uf = LOT / "data" / "sources_cache" / "usatoday.json"
    if uf.exists():
        d = json.loads(uf.read_text())
        tables = d.get("tables") or []
        if isinstance(tables, dict):
            tables = tables.values()
        for t in tables:
            title = (t.get("title") or "").lower() if isinstance(t, dict) else ""
            upos = next((p for k, p in _USAT_POS.items() if k in title), None)
            for row in (t.get("rows") if isinstance(t, dict) else t) or []:
                if isinstance(row, (list, tuple)):
                    nm = row[1] if len(row) > 1 else None
                elif isinstance(row, dict):
                    nm = row.get("name")
                else:
                    nm = None
                if nm:
                    src_rows.append(("usatoday", nm, upos))
    missing_src, _seen_src, _outside = [], set(), []
    for s, n, pos in src_rows:
        if (s, n) in _seen_src:
            continue
        _seen_src.add((s, n))
        verdict = classify_source_row(n, pos, cp_reg, disp_keys, disp_c)
        if verdict == "covered":
            continue
        if verdict == "outside":
            _outside.append(f"{s}:{n}")
            continue
        missing_src.append(f"{s}:{n}")
    missing_src = sorted(missing_src)
    src_names = {(s, n) for s, n, _ in src_rows}
    if not missing_src:
        det = (f"display covers all {len(src_names)} FantasyCalc/USAT players "
               f"({len(disp)} display rows)")
        if _outside:
            c.ok("C5", "sources",
                 det + f"; {len(_outside)} outside chart universe (by design)",
                 items=sorted(_outside)[:15])
        else:
            c.ok("C5", "sources", det)
    else:
        c.fail("C5", "sources",
               f"{len(missing_src)} source players missing from display",
               items=missing_src[:25])

    # ---- C6/C7: waiver pool covers trending + ESPN ----
    pool, _leg2chart = WB.canonical_pool()
    pool_pos = {canon(k): v.get("pos") for k, v in pool.items()}
    trends_panel = {}
    tf = latest(str(WTR / "trends_latest.json"))
    if tf:
        trends_panel = json.loads(tf.read_text())
    pmap = pos_map(pool, trends_panel)

    tfile = LOT / "data" / "sleeper_trending_2026-09-14.json"  # same file waiver_boundary reads
    if not tfile.exists():
        tfile = latest(str(LOT / "data" / "sleeper_trending_2026-*.json"))
    trending = {}
    if tfile and tfile.exists():
        d = json.loads(tfile.read_text())
        trending = d if isinstance(d, dict) else {}
    miss_t, unres_t = [], []
    for k, v in trending.items():
        adds = (v or [0])[0]
        if adds < TREND_ADDS_FLOOR:
            continue
        ck, pos = canon(k), pmap.get(canon(k))
        if ck in pool_pos or WB.norm_name(k) in pool:
            continue
        if pos in SKILL_POS:
            miss_t.append(f"{k} ({adds} adds)")
        elif pos is None:
            unres_t.append(k)
    if not miss_t:
        det = (f"all {sum(1 for k, v in trending.items() if (v or [0])[0] >= TREND_ADDS_FLOOR)} "
               f"players >= {TREND_ADDS_FLOOR} adds resolve to the pool")
        if unres_t:
            c.warn("C6", "waiver-trends", det + f"; {len(unres_t)} unresolvable names",
                   items=unres_t[:15])
        else:
            c.ok("C6", "waiver-trends", det)
    else:
        c.fail("C6", "waiver-trends",
               f"{len(miss_t)} trending skill players missing from the waiver pool",
               items=miss_t)

    espn_file = latest(str(LOT / "data" / "espn_roster_*.json"))
    miss_e, unres_e = [], []
    if espn_file:
        sys.path.insert(0, str(LOT / "engine"))
        import espn_roster as ER
        from identity import IdentityMap
        # Mirror waiver_boundary._espn_roster exactly: ESPN lookup keys are
        # ESPN-spelling norms; IdentityMap resolves them to chart keys via
        # the registry snapshot + nickname heuristic.
        # 2026-09-19: the registry snapshot's canonical targets predate the
        # naming-table renames ("cam skattebo" -> "cameron skattebo"), so
        # the pipeline's bridge (waiver_boundary._espn_roster) routes those
        # targets back to their pool pid -- mirrored here via espn_bridge.
        # ESPN's deliberate suffix-variant double-keying is collapsed by
        # same-pct dedupe below, never by suffix guessing.
        ident = IdentityMap(chart_keys=set(pool.keys()))
        bridge = espn_bridge(pool.keys(), ident)
        lk = ER.build_lookup(date_tag=ER.latest_tag())
        for name, pct in dedupe_espn_lookup(lk):
            if float(pct or 0) < ESPN_ROSTER_FLOOR:
                continue
            pid = espn_pool_pid(name, pool, ident, bridge)
            if pid is not None:
                continue
            ck = ident.canon(WB.norm_name(name))
            pos = pmap.get(ck) or pmap.get(canon(name))
            if pos in SKILL_POS:
                miss_e.append(f"{name} ({pct}%)")
            elif pos is None:
                unres_e.append(name)
    if not miss_e:
        det = f"all ESPN roster%>={ESPN_ROSTER_FLOOR:g} players resolve to the pool"
        if unres_e:
            c.warn("C7", "waiver-espn", det + f"; {len(unres_e)} unresolvable names",
                   items=unres_e[:15])
        else:
            c.ok("C7", "waiver-espn", det)
    else:
        c.fail("C7", "waiver-espn",
               f"{len(miss_e)} ESPN rostered skill players missing from the waiver pool",
               items=miss_e)

    # ---- C8/C9: K/DST chain (source -> chart -> legs) ----
    # K/DST live in fp_season_kdst_projections (not the norm table), so C2/C3
    # don't cover them. Legs seed K/DST at the next market step; until then a
    # chart->legs gap is WARN, not FAIL.
    kdst_rows = query(
        "SELECT position, player_key, display_name FROM v_fp_season_kdst_latest"
        " WHERE player_key IS NOT NULL")
    for cid, pos, label in (("C8", "K", "kicker"), ("C9", "DST", "defense")):
        src = {int(r["player_key"]): r["display_name"]
               for r in kdst_rows if r["position"] == pos}
        chart_pos = {p.get("player_key") for p in chart["players"]
                     if p.get("pos") == pos and p.get("player_key") is not None}
        missing_chart = sorted(set(src) - chart_pos)
        # legs join on player_key, same as C4 (name-canon fallback for
        # unresolvable leg keys)
        legs_present = bool(leg_keys or leg_name_canons)
        missing_legs = sorted(
            k for k in (set(src) & chart_pos)
            if k not in leg_keys
            and canon(chart_info[k][0]) not in leg_name_canons
        ) if legs_present else []
        det = (f"{len(src)} {label}s in source, "
               f"{len(chart_pos)} in players.json")
        if missing_chart:
            c.fail(cid, f"{label}-chain",
                   f"{det}; {len(missing_chart)} missing from the chart",
                   items=missing_chart)
        elif not legs_present:
            c.warn(cid, f"{label}-chain",
                   det + "; no leg file to check against yet")
        elif missing_legs:
            c.warn(cid, f"{label}-chain",
                   det + f"; {len(missing_legs)} not yet in "
                   f"{leg_label or 'the Monday legs'} "
                   "(seeds at the next market step)",
                   items=missing_legs[:15])
        else:
            c.ok(cid, f"{label}-chain",
                 det + f"; all in {leg_label or 'the Monday legs'}")

    # ---- C10: Monday-leg form coverage ----
    # Every chart player who logged a Week-1 stat row must carry a form
    # read (debug.form_pg) in the Monday legs. Catches the 2026-09-15 class:
    # the form feed (waiver-trends panel) covered only 332 players, so 232
    # chart players - including all Chiefs (pre-MNF panel) - carried
    # preseason baselines with Monday dates.
    try:
        # pyarrow, not polars: polars is not installable in the scheduled
        # runtime (PEP 668 externally-managed env), and this check only
        # needs a filtered column read. 2026-09-17.
        import pyarrow.parquet as pq
        import pyarrow.compute as pc
        _leg = json.loads((LOT / "results" / "imputed_proj_half.json").read_text())
        _tbl = pq.read_table(
            LOT / "data" / "player_stats_2026.parquet",
            columns=["player_display_name", "team", "season", "week"])
        _w1 = _tbl.filter((pc.field("season") == 2026) & (pc.field("week") == 1))
        _played = set()
        for _n, _t in zip(_w1.column("player_display_name").to_pylist(),
                          _w1.column("team").to_pylist()):
            _played.add((canon(_n), _t))
        _noform = []
        _team_nofrom = {}
        for _ck, _team in _played:
            # find the leg record by canon key
            _rec = None
            for _k, _v in _leg.items():
                if isinstance(_v, dict) and canon(_k) == _ck:
                    _rec = _v
                    break
            if _rec and _rec.get("pos") in SKILL_POS:
                if (_rec.get("debug") or {}).get("form_pg") is None:
                    _noform.append(_rec.get("name", _ck))
                    _team_nofrom[_team] = _team_nofrom.get(_team, 0) + 1
        _n_played_skill = sum(
            1 for _ck, _ in _played
            for _k, _v in _leg.items()
            if isinstance(_v, dict) and canon(_k) == _ck
            and _v.get("pos") in SKILL_POS)
        _cov = ((_n_played_skill - len(_noform)) / _n_played_skill
                if _n_played_skill else 1.0)
        _det = (f"{_n_played_skill - len(_noform)}/{_n_played_skill} played "
                f"skill players have a Week-1 form read "
                f"({_cov:.0%} coverage)")
        # Team-level: a completed team with zero form reads = feed gap.
        _zero_teams = sorted(
            _t for _t, _n in _team_nofrom.items()
            if _n >= 5)  # 5+ played players, none with form
        if _cov < 0.90 or _zero_teams:
            c.fail("C10", "form-coverage",
                   f"FAIL: {_det}. " +
                   (f"Teams with 5+ played players and no form: "
                    f"{', '.join(_zero_teams)}. " if _zero_teams else "") +
                   "The Monday form feed does not cover the chart universe.",
                   items=_noform[:20])
        elif _cov < 0.97:
            c.warn("C10", "form-coverage",
                   f"{_det}; {len(_noform)} played players without a read "
                   f"(fringe only - no team-level gap)",
                   items=_noform[:15])
        else:
            c.ok("C10", "form-coverage", _det)
    except Exception as _e:
        c.fail("C10", "form-coverage",
               f"check errored: {_e}")

    # ---- report ----
    today = date.today().isoformat()
    fails = [k for k, v in c.results.items() if v["verdict"] == "FAIL"]
    warns = [k for k, v in c.results.items() if v["verdict"] == "WARN"]
    report = {"date": today, "checks": c.results,
              "summary": {"fail": fails, "warn": warns}}
    out = LOT / "results" / f"coverage_{today}.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"coverage check {today}: "
          f"{len(c.results) - len(fails) - len(warns)}/{len(c.results)} PASS, "
          f"{len(warns)} WARN, {len(fails)} FAIL -> {out}")
    for cid, r_ in c.results.items():
        print(f"  [{r_['verdict']}] {cid} {r_['name']}: {r_['detail']}")
        for it in (r_["items"] or [])[:8]:
            print(f"      - {it}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
