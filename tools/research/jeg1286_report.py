"""JEG-1286: turn jeg1286_flex_flips_<tag>.json into the figures page.

  python3 tools/research/jeg1286_report.py docs/research/data/jeg1286_flex_flips_main.json \
      [docs/research/data/jeg1286_flex_flips_band.json] > docs/research/data/jeg1286_flex_flips.md
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

OPT_LABEL = {
    "A": "A today (step at the cutoff)",
    "B50": "B flex only, sigma 0.5",
    "B75": "B flex only, sigma 0.75",
    "B100": "B flex only, sigma 1.0",
    "B50b": "B flex and bench, sigma 0.5",
    "B75b": "B flex and bench, sigma 0.75",
    "B100b": "B flex and bench, sigma 1.0",
    "C": "C fixed flex split (real-league shares)",
    "D": "D bench discount from a fixed flex share",
}


# Short column labels for the examples table.
OPT_KEY = {"A": "A today", "B50": "B flex, σ 0.5", "B75": "B flex, σ 0.75", "B100": "B flex, σ 1.0",
           "B50b": "B flex+bench, σ 0.5", "B75b": "B flex+bench, σ 0.75", "B100b": "B flex+bench, σ 1.0",
           "C": "C fixed split", "D": "D bench decoupled"}


def f(x, n=2):
    return "n/a" if x is None else f"{x:.{n}f}"


def split_str(d):
    return "/".join(str(d.get(p, 0)) for p in ("RB", "WR", "TE"))


def pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def margins_table(r):
    out = ["| Setting | Flex split RB/WR/TE | Closest flex swap | Gap (mean PPG) | One source needs | Closest bench swap | Gap (mean PPG) |",
           "|---|---|---|---|---|---|---|"]
    for m in r["margins"]:
        fp = m["flex_pairs"][0] if m["flex_pairs"] else None
        bp = m["bench_pairs"][0] if m["bench_pairs"] else None
        out.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            m["cell"], split_str(m["flex"]),
            f"{fp['winner']} ({fp['from']}) vs {fp['loser']} ({fp['to']})" if fp else "none",
            f(fp["gap"]) if fp else "", f(fp["one_source_ppg"]) if fp else "",
            f"{bp['winner']} ({bp['from']}) vs {bp['loser']} ({bp['to']})" if bp else "none",
            f(bp["gap"]) if bp else ""))
    near = sum(1 for m in r["margins"] if m["flex_pairs"] and m["flex_pairs"][0]["one_source_ppg"] < 1.0)
    out.append("")
    out.append(f"Flex cutoffs a 1 PPG change in one source can cross: {near} of {len(r['margins'])} settings.")
    return "\n".join(out)


def soft_table(r):
    out = ["| Setting | Flex today RB/WR/TE | B σ 0.5 | B σ 0.75 | B σ 1.0 | Allocations B σ 0.75 blends | Projection disagreement near the cutoff (median SE of the mean, PPG) |",
           "|---|---|---|---|---|---|---|"]
    noise = {n["cell"]: n for n in r.get("noise", [])}
    for m in r["margins"]:
        soft = m.get("soft") or {}
        cell = lambda k: "/".join(f"{soft[k]['flex'].get(p, 0):.1f}" for p in ("RB", "WR", "TE")) if k in soft else ""
        n = noise.get(m["cell"])
        out.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            m["cell"], split_str(m["flex"]), cell("0.5"), cell("0.75"), cell("1.0"),
            soft.get("0.75", {}).get("vertices", ""), f(n["median_se"]) if n else ""))
    return "\n".join(out)


def sweep_table(r):
    out = ["| Setting | Cases | Flex flips | Bench-only flips | Worst DDF move, any cause | Worst DDF move from the flip | Who | Cases over 1.0 | of which flips |",
           "|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    for s in r["sweep"]:
        cs = s["cases"]
        flips = Counter(c["flip"] for c in cs)
        worst = max(cs, key=lambda c: c["move"]["ddf"], default=None)
        fpw = max((c for c in cs if c["flip"] != "none"), key=lambda c: c["flip_part"]["ddf"], default=None)
        over = [c for c in cs if c["move"]["ddf"] > 1.0]
        tot.update(cases=len(cs), flex=flips["flex"], bench=flips["bench"], over=len(over),
                   over_flip=sum(1 for c in over if c["flip"] != "none"))
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            s["cell"], len(cs), flips["flex"], flips["bench"],
            f(worst["move"]["ddf"]) if worst else "", f(fpw["flip_part"]["ddf"]) if fpw else "0.00",
            (fpw["flip_part"]["ddf_who"] or "") if fpw else "", len(over),
            sum(1 for c in over if c["flip"] != "none")))
    out.append("| All | {cases} | {flex} | {bench} | | | | {over} | {over_flip} |".format(**tot))
    return "\n".join(out)


def options_table(r):
    opts = [o for o in OPT_LABEL if o == "A" or any(o in c.get("options", {}) for s in r["sweep"] for c in s["cases"])]
    out = ["| Option | Worst DDF move | 99th pct | Cases over 1.0 | Cases over 0.5 | Worst projections DDF move | Largest change to today's values (no perturbation) |",
           "|---|---|---|---|---|---|---|"]
    for o in opts:
        mv, pj = [], []
        for s in r["sweep"]:
            for c in s["cases"]:
                v = c["move"] if o == "A" else c["options"].get(o)
                if v is None:
                    continue
                mv.append(v["ddf"])
                pj.append(v["proj"] or 0.0)
        if o == "A":
            dep = "0.00"
        else:
            worst_dep = max(((s["departure"][o]["ddf"], s["cell"], s["departure"][o]["top"][0])
                             for s in r["sweep"] if o in s["departure"]), key=lambda t: t[0])
            t = worst_dep[2]
            dep = f"{f(worst_dep[0])} ({t['who']} {f(t['today'],1)} to {f(t['option'],1)}, {worst_dep[1]})"
        out.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            OPT_LABEL[o], f(max(mv, default=None)), f(pct(mv, 0.99)), sum(1 for x in mv if x > 1.0),
            sum(1 for x in mv if x > 0.5), f(max(pj, default=None)), dep))
    return "\n".join(out)


def _day(when):
    return datetime.fromisoformat(when).astimezone(timezone(timedelta(hours=-5))).date()


def history_table(r):
    out = ["| Setting | Bakes compared | Flex flips | Bench-only flips | Days with a flex flip | Flex splits seen RB/WR/TE | Median DDF move from a flip | Worst | Who |",
           "|---|---|---|---|---|---|---|---|---|"]
    allp = []
    n_days = 0
    for h in r["history"]:
        # From the first bake with all three projections (2026-10-01); the
        # September bakes had one projection source.
        bs = [b for b in h["bakes"] if "flip" in b and b.get("n_src", 0) >= 3]
        days = {_day(b["when"]) for b in bs}
        n_days = max(n_days, len(days))
        flex_days = {_day(b["when"]) for b in bs if b["flip"] == "flex"}
        fl = Counter(b["flip"] for b in bs)
        parts = [b["flip_part"]["ddf"] for b in bs if "flip_part" in b]
        allp += parts
        worst = max((b for b in bs if "flip_part" in b), key=lambda b: b["flip_part"]["ddf"], default=None)
        splits = sorted({split_str(b["flex"]) for b in h["bakes"] if "flex" in b and b.get("n_src", 0) >= 3})
        out.append("| {} | {} | {} | {} | {} of {} | {} | {} | {} | {} |".format(
            h["cell"], len(bs), fl["flex"], fl["bench"], len(flex_days), len(days), ", ".join(splits),
            f(statistics.median(parts)) if parts else "", f(worst["flip_part"]["ddf"]) if worst else "",
            (worst["flip_part"]["ddf_who"] or "") if worst else ""))
    errs = Counter(b["error"].split(":")[0] for h in r["history"] for b in h["bakes"] if "error" in b)
    out.append("")
    if allp:
        out.append(f"Across all settings, {len(allp)} flips in {sum(1 for h in r['history'] for b in h['bakes'] if 'flip' in b and b.get('n_src', 0) >= 3)} "
                   f"consecutive-bake comparisons over {n_days} days with a bake; median DDF move from the flip "
                   f"{f(statistics.median(allp))}, 90th percentile {f(pct(allp, 0.9))}, worst {f(max(allp))}.")
    if errs:
        out.append(f"Bakes today's code could not read: {dict(errs)}.")
    return "\n".join(out)


def examples_block(r):
    out = []
    for e in r.get("examples", []):
        opts = sorted(e["worst"], key=lambda o: list(OPT_KEY).index(o) if o in OPT_KEY else 99)
        out.append(f"#### {e['cell']}: {e['who']} {e['src']} {e['delta']:+} PPG")
        out.append("")
        out.append(f"Flex split RB/WR/TE {split_str(e['flex_before'])} to {split_str(e['flex_after'])}; "
                   f"bench RB/WR/TE {split_str(e['bench_before'])} to {split_str(e['bench_after'])}.")
        out.append("")
        out.append("| Player | " + " | ".join(OPT_KEY.get(o, o) for o in opts) + " |")
        out.append("|---|" + "---|" * len(opts))
        for p in e["players"]:
            cells = []
            for o in opts:
                v = p.get(o)
                cells.append(f"{f(v['before'],1)} to {f(v['after'],1)} ({v['after'] - v['before']:+.2f})" if v else "")
            out.append(f"| {p['name']} ({p['pos']}) | " + " | ".join(cells) + " |")
        out.append("| Worst move, any other player | " + " | ".join(f(e["worst"][o]) for o in opts) + " |")
        out.append("")
    return "\n".join(out)


def main(argv):
    main_r = json.loads(open(argv[1]).read())
    band = json.loads(open(argv[2]).read()) if len(argv) > 2 else None
    print("# JEG-1286 figures: flex and bench slot flips")
    print()
    print(f"Generated by `tools/research/jeg1286_report.py` from `tools/research/jeg1286_flex_flips.py` "
          f"(Python reference at `{main_r['repo_head'][:8]}`, `data/fixtures/current`). DDF Value points throughout. "
          f"{main_r['alloc_check']}. Write-up: [../jeg1286-flex-flips.md](../jeg1286-flex-flips.md). The run JSON (about 12 MB) is not committed; rerun the script to regenerate it.")
    print()
    print("## 1. How close each cutoff is today")
    print()
    print(margins_table(main_r))
    print()
    print("Expected flex seats under option B (fractional seats) and the projection noise its σ is set from:")
    print()
    print(soft_table(main_r))
    print()
    if main_r.get("examples"):
        print("## 2. Named examples, before and after, under each option")
        print()
        print(examples_block(main_r))
    print("## 3. One-player sweep (1 and 0.5 PPG, one source, players within 3 of a cutoff)")
    print()
    print("Today's rule (A):")
    print()
    print(sweep_table(main_r))
    print()
    print("Every option on the same cases. A move is the largest change to any other player's DDF Value, "
          "measured against that option's own unperturbed values:")
    print()
    print(options_table(main_r))
    print()
    if band:
        print(f"With PR #1077's 7-player waiver band (`{band['repo_head'][:8]}`):")
        print()
        print(sweep_table(band))
        print()
        print(options_table(band))
        print()
    if main_r.get("history"):
        print("## 4. Real data updates: every players.json bake on main, replayed with today's code")
        print()
        print("A flip is a change in the allocation between two consecutive bakes. The move from the flip is the "
              "largest gap, at the later bake, between DDF Value with the allocation free and with the earlier "
              "bake's allocation held; everything else that changed between the bakes is in both runs.")
        print()
        print(history_table(main_r))
        print()


if __name__ == "__main__":
    main(sys.argv)
