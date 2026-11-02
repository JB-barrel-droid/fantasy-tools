"""JEG-1366 before/after: reference DDF Values at QB 2 / no superflex, rule off (before) vs on (after).
Usage: python3 tools/jeg1366_before_after.py <repo_root> <out.json>"""
import argparse, json, sys
from datetime import date
from pathlib import Path
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("repo_root", type=Path)
parser.add_argument("out", type=Path)
parser.add_argument("--fixture", type=Path)
parser.add_argument("--players", type=Path)
parser.add_argument("--seat-sigma", type=float)
args = parser.parse_args()
root = args.repo_root.resolve()
sys.path.insert(0, str(root / "pipelines")); sys.path.insert(0, str(root))
import value_reference as ref
from tests.test_week_history import _fixture_today
today = _fixture_today()
paths = {k: getattr(args, k) for k in ("fixture", "players") if getattr(args, k) is not None}
inp = ref.Inputs.load(today=date.fromisoformat(today), **paths)
pos = {k: p["pos"] for k, p in inp.players.items()}
name = {k: p.get("name") or p.get("player") or k for k, p in inp.players.items()}
real = ref.uses_two_qb_native_share
out = {"today": today, "fixture_built_at": inp.fixture.get("built_at"),
       "seat_sigma": args.seat_sigma if args.seat_sigma is not None else getattr(ref, "SEAT_SIGMA", 0),
       "data_label": "2026 week 8 charts and 2026 rest-of-season projections", "settings": {}}
for scoring in ref.SCORINGS:
    for teams in (10, 12, 14):
        rec = {}
        for label, rule in (("before", lambda s: False), ("after", real)):
            ref.uses_two_qb_native_share = rule
            st = ref.Setting(inp, scoring, teams, qb=2)
            if args.seat_sigma is not None:
                st.league.seat_sigma = args.seat_sigma
            res = st.result()
            w = res["ddf_weights"]
            vals = {k: v["ddf_value"] for k, v in st.rows("adj").items() if v["ddf_value"] is not None}
            tot = {}
            for k, v in vals.items():
                tot[pos.get(k)] = tot.get(pos.get(k), 0) + v
            rec[label] = {"qb_share": w["QB|starter"] + w["QB|bench"],
                          "totals": {p: round(tot.get(p, 0), 1) for p in ("QB", "RB", "WR", "TE")},
                          "values": {k: round(v, 1) for k, v in vals.items()}}
        ref.uses_two_qb_native_share = real
        out["settings"][f"{scoring}/{teams}"] = rec
out["names"] = {k: name[k] for k in pos}
out["pos"] = pos
args.out.write_text(json.dumps(out, indent=2) + "\n")
for s, r in out["settings"].items():
    print(s, f'{r["before"]["qb_share"]*100:.1f}% -> {r["after"]["qb_share"]*100:.1f}%',
          r["before"]["totals"], "->", r["after"]["totals"])
