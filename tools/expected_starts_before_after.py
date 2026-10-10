#!/usr/bin/env python3
"""Before/after of JEG-536 on this week's data, for Jeremy's go (JEG-450 rule).

Before = the JEG-508 value pipeline (VP-2.6 slices, bench share fixed at 15%);
after = expected starts (ES-5 parts, bench share computed from the reader's
default settings). Both run in pipelines/value_reference.py on the committed
snapshot, which value_check holds to the engine at 0 disagreements.

Per setting: the blended DDF Value top movers (up and down), the bench tier's
share of each position's value (ES-14 readout; before measured the same way),
the number of players at DDF Value 0, where each position's curve starts (the
top blended DDF Value), within-source order inversions, and named examples.

    python3 tools/expected_starts_before_after.py [--settings ppr/12,half_ppr/10,standard/14]
        [--top 15] [--out output/expected-starts-engine-before-after.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
import value_reference as ref  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE")
SCORE_LABEL = {"ppr": "Full PPR", "half_ppr": "Half PPR", "standard": "Standard"}
EXAMPLES = ("Romeo Doubs", "Jaxon Smith-Njigba", "Jahmyr Gibbs", "Bijan Robinson")


def run(inp, hist, scoring, teams, expected_starts):
    s = ref.Setting(inp, scoring, teams, hist=hist, expected_starts=expected_starts)
    return s.result()


def inversions(res) -> int:
    """Pairs within one source and position where a higher native got a lower
    Adjusted value (the order guard, ES-5)."""
    bad = 0
    for d in res["sources"].values():
        for p in POSITIONS:
            pl = sorted((x for x in d["players"].values() if x["pos"] == p), key=lambda x: -x["native"])
            for a, b in zip(pl, pl[1:]):
                if a["native"] > b["native"] and b["adjusted"] > a["adjusted"] + 1e-9:
                    bad += 1
    return bad


def blended(res) -> dict:
    return {i: r["ddf"]["blended"]["value"] for i, r in res["rows"].items()}


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def setting_block(inp, hist, names, scoring, teams, top) -> tuple[list[str], dict]:
    before = run(inp, hist, scoring, teams, False)
    after = run(inp, hist, scoring, teams, True)
    b, a = blended(before), blended(after)
    rb, ra = before["bench_share_readout"], after["bench_share_readout"]
    label = f"{SCORE_LABEL[scoring]}, {teams} teams"
    movers = []
    for i in a:
        if a.get(i) is None or b.get(i) is None:
            continue
        movers.append((a[i] - b[i], i))
    movers.sort()
    tier = {i: r.get("ddf_tier") for i, r in after["rows"].items()}
    lines = [f"### {label}", ""]
    lines.append(f"Bench tier's share of each position's value (before: slices at 15%; after: computed). "
                 f"Pie paid on the bench groups: before {pct(before['bench_share_applied'])}, "
                 f"after {pct(after['bench_share_applied'])}.")
    lines.append("")
    lines.append("| | QB | RB | WR | TE | Overall |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append("| Before | " + " | ".join(pct(rb[p]) for p in POSITIONS) + f" | {pct(rb['overall'])} |")
    lines.append("| After | " + " | ".join(pct(ra[p]) for p in POSITIONS) + f" | {pct(ra['overall'])} |")
    lines.append("")
    zero_b = sum(1 for v in b.values() if v == 0)
    zero_a = sum(1 for v in a.values() if v == 0)
    lines.append(f"Players at DDF Value 0: before {zero_b}, after {zero_a} (of {len(a)} rows). "
                 f"Order inversions within a source: before {inversions(before)}, after {inversions(after)}.")
    lines.append("")
    start_b = {p: max((v for i, v in b.items() if v is not None and before['rows'][i]['pos'] == p), default=None)
               for p in POSITIONS}
    start_a = {p: max((v for i, v in a.items() if v is not None and after['rows'][i]['pos'] == p), default=None)
               for p in POSITIONS}
    lines.append("Where each position's curve starts (top DDF Value): "
                 + "; ".join(f"{p} {start_b[p]:.1f} -> {start_a[p]:.1f}" for p in POSITIONS) + ".")
    lines.append("")
    for title, rows in (("Up", list(reversed(movers[-top:]))), ("Down", movers[:top])):
        lines.append(f"Top {top} movers {title.lower()} (DDF Value, blended):")
        lines.append("")
        lines.append("| Player | Pos | Tier | Before | After | Change | Lineup share |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for d, i in rows:
            r = after["rows"][i]
            share = r.get("lineup_share")
            lines.append(f"| {names.get(i, i)} | {r['pos']} | {tier.get(i) or '-'} | {b[i]:.1f} | {a[i]:.1f} | "
                         f"{d:+.1f} | {pct(share)} |")
        lines.append("")
    ex = []
    by_name = {n: i for i, n in names.items()}
    for n in EXAMPLES:
        i = by_name.get(n)
        if i is None or i not in a:
            continue
        r = after["rows"][i]
        ex.append({"name": n, "pos": r["pos"], "tier": tier.get(i), "before": b.get(i), "after": a.get(i),
                   "lineup_share": r.get("lineup_share"), "start_worthy": r.get("start_worthy")})
    lines.append("Examples:")
    lines.append("")
    lines.append("| Player | Pos | Tier | Before | After | Change | Lineup share | Start-worthy |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for e in ex:
        lines.append(f"| {e['name']} | {e['pos']} | {e['tier']} | {e['before']:.1f} | {e['after']:.1f} | "
                     f"{e['after'] - e['before']:+.1f} | {pct(e['lineup_share'])} | {pct(e['start_worthy'])} |")
    lines.append("")
    summary = {"setting": label, "before_readout": rb, "after_readout": ra, "zero_before": zero_b,
               "zero_after": zero_a, "inversions_after": inversions(after), "examples": ex,
               "curve_start_before": start_b, "curve_start_after": start_a,
               "movers_up": [(names.get(i, i), d) for d, i in reversed(movers[-top:])],
               "movers_down": [(names.get(i, i), d) for d, i in movers[:top]]}
    return lines, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", default="ppr/12,half_ppr/10,standard/14")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--out", type=Path, default=REPO / "output" / "expected-starts-engine-before-after.md")
    args = ap.parse_args(argv)
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    hist = ref.History(ref.HISTORY)
    names = {k: p.get("name", str(k)) for k, p in inp.players.items()}
    week = json.loads((REPO / "config" / "lineup_parameters.json").read_text(encoding="utf-8"))["content_week"]
    lines = [f"# Expected starts (JEG-536): before and after, Week {week} data", "",
             "Before = the JEG-508 value pipeline (slices, bench share fixed at 15%). After = expected starts, "
             "bench share computed from the default reader settings (whole season, weeks 6-17, recent-seasons "
             "injury history, projection confidence as measured, no override). Same snapshot, same included "
             "sources; engine and Python reference agree at 0 disagreements.", ""]
    summaries = []
    for sid in args.settings.split(","):
        scoring, teams = sid.split("/")
        block, summary = setting_block(inp, hist, names, scoring, int(teams), args.top)
        lines += block
        summaries.append(summary)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.out.with_suffix(".json").write_text(json.dumps(summaries, indent=1, default=str), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
