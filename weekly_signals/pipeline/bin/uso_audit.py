#!/usr/bin/env python3
"""USO league audit: join Yahoo rosters with Supabase projections/signals/injuries,
compute per-team positional strength vs league average, flag needs/surplus."""
import json, re, sys
from collections import defaultdict

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
from sbclient import get_all  # noqa: E402

def norm(name):
    n = name.lower()
    n = re.sub(r"\b(sr|jr|iii|ii|iv|v)\.?$", "", n).strip()
    n = re.sub(r"[.'\-]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

snap = json.load(open("/home/hatch/workspace/football-signal/data/yahoo_uso/snapshot_2026-09-11.json"))
rosters = snap["rosters"]

print("pulling projections...", file=sys.stderr)
proj = get_all("fp_season_projections",
               "?select=position,team,proj_half_ppr,players(full_name)&snapshot_date=eq.2026-09-11&proj_half_ppr=not.is.null")
print(f"  {len(proj)} rows", file=sys.stderr)
print("pulling signals...", file=sys.stderr)
sigs = get_all("v_latest_signals",
               "?select=player_name,position,player_team,vegas_half,expert_half,pts_delta_half,lean,post_worthy&week=eq.1")
print(f"  {len(sigs)} rows", file=sys.stderr)
print("pulling injuries...", file=sys.stderr)
inj = get_all("injuries", "?select=player_name,status,report_date&order=report_date.desc")
print(f"  {len(inj)} rows", file=sys.stderr)

proj_map = {}
for r in proj:
    nm = (r.get("players") or {}).get("full_name")
    if not nm or r.get("proj_half_ppr") is None:
        continue
    proj_map[(norm(nm), r["position"])] = float(r["proj_half_ppr"])
sig_map = {}
for r in sigs:
    sig_map[(norm(r["player_name"]), r["position"])] = r
inj_map = {}
for r in inj:
    k = norm(r["player_name"])
    if k not in inj_map:
        inj_map[k] = r["status"]

def lookup(d, name, pos):
    v = d.get((norm(name), pos))
    if v is not None:
        return v
    for (nm, _ps), val in d.items():
        if nm == norm(name):
            return val
    return None

teams = {}
for team, players in rosters.items():
    enriched = []
    for pl in players:
        ros = lookup(proj_map, pl["player"], pl["pos"])
        sg = lookup(sig_map, pl["player"], pl["pos"])
        enriched.append({**pl, "ros_half": ros, "sig": sg,
                         "inj_status": inj_map.get(norm(pl["player"]))})
    teams[team] = enriched

pos_counts = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
audit = {}
for team, players in teams.items():
    by_pos = defaultdict(list)
    for pl in players:
        if pl["pos"] in ("QB", "RB", "WR", "TE"):
            by_pos[pl["pos"]].append(pl["ros_half"] or 0)
    row = {}
    for pos, n in pos_counts.items():
        vals = sorted(by_pos.get(pos, []), reverse=True)
        row[pos] = round(sum(vals[:n]), 1)
    flex_pool = [pl["ros_half"] or 0 for pl in players if pl["pos"] in ("RB", "WR", "TE")]
    for pos, n in pos_counts.items():
        for v in sorted(by_pos.get(pos, []), reverse=True)[:n]:
            if v in flex_pool:
                flex_pool.remove(v)
    row["FLEX"] = round(max(flex_pool) if flex_pool else 0, 1)
    row["QBdepth"] = round(sum(sorted(by_pos.get("QB", []), reverse=True)[1:2]), 1)
    row["total_start"] = round(row["QB"] + row["RB"] + row["WR"] + row["TE"] + row["FLEX"], 1)
    audit[team] = row

avg = {k: round(sum(audit[t][k] for t in audit) / len(audit), 1)
       for k in ["QB", "RB", "WR", "TE", "FLEX", "total_start"]}

print("\n=== LEAGUE AUDIT: starter-group ROS value (half-PPR) vs league avg ===")
print(f"{'team':24s} {'QB':>7s} {'RB':>7s} {'WR':>7s} {'TE':>7s} {'FLEX':>7s} {'TOTAL':>8s}")
for t in sorted(audit, key=lambda t: -audit[t]["total_start"]):
    a = audit[t]
    mark = " <== YOU" if t == "Tiny Hands" else ""
    print(f"{t:24s} {a['QB']:7.1f} {a['RB']:7.1f} {a['WR']:7.1f} {a['TE']:7.1f} {a['FLEX']:7.1f} {a['total_start']:8.1f}{mark}")
print(f"{'LEAGUE AVG':24s} {avg['QB']:7.1f} {avg['RB']:7.1f} {avg['WR']:7.1f} {avg['TE']:7.1f} {avg['FLEX']:7.1f} {avg['total_start']:8.1f}")

print("\n=== NEEDS (<90% of avg) / SURPLUS (>110% of avg) + injury flags ===")
for t in sorted(audit):
    a = audit[t]
    needs = [p for p in ["QB", "RB", "WR", "TE", "FLEX"] if a[p] < avg[p] * 0.90]
    surp = [p for p in ["QB", "RB", "WR", "TE", "FLEX"] if a[p] > avg[p] * 1.10]
    flags = [f"{pl['player']}({pl['status']})" for pl in teams[t] if pl["status"] in ("O", "IR", "Q", "PUP-R", "NA", "CEL")]
    print(f"{t:24s} needs={str(needs or '-'):32s} surplus={str(surp or '-')}{'  FLAGS: '+', '.join(flags) if flags else ''}")

print("\n=== NO ROS PROJECTION (unmatched) ===", file=sys.stderr)
missing = [f"{t}: {pl['player']} ({pl['pos']})" for t, ps in teams.items() for pl in ps
             if pl["ros_half"] is None and pl["pos"] not in ("K", "DEF")]
print("\n".join(missing) if missing else "none", file=sys.stderr)

json.dump({t: teams[t] for t in teams},
          open("/home/hatch/workspace/football-signal/data/yahoo_uso/rosters_enriched_2026-09-11.json", "w"),
          indent=1, default=str)
json.dump({"audit": audit, "avg": avg},
          open("/home/hatch/workspace/football-signal/data/yahoo_uso/audit_2026-09-11.json", "w"),
          indent=1)
print("saved enriched rosters + audit", file=sys.stderr)
