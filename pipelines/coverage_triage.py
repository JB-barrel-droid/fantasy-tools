#!/usr/bin/env python3
"""Decision brief for a source the comparison chain held on coverage (JEG-667).

The chain's review holds a candidate that prices fewer players than the fixture
(`coverage:<combo>/<POS>:fail`) and never overrides the hold. This turns the
failing check into one page Jeremy can decide from:

  - per combo and position: candidate priced vs fixture floor;
  - the exact players that dropped out vs the last accepted (fixture) section:
    name, team, last value, rank in that combo/position;
  - for each, whether leaving the list is plausibly a genuine rotation
    (injured reserve, PUP, practice squad, free agent, inactive/retired, no
    team) or looks like a scrape loss (an active, depth-chart player);
  - the two options, a recommendation, and the exact command for each.

Where the drops come from, in order: `--review` artifacts (output/reviewed/
<source>-*-review.json, written by the chain run; CI does not upload them), else
the failing-check text in the chain status file. `--rev GIT_REV` reads the
status AND the fixture as of that commit, to triage a hold that a later run has
since moved past.

Subcommands:
  report SOURCE           print the brief (read-only; the default)
  accept SOURCE           record Jeremy's decision in data/triage/
                          coverage-accepted.json; the next chain run's review
                          then passes exactly that decision for that content
                          week. Needs --approve "<name> <date> <reason>" and
                          --names (option A) or --floor (option B).
Nothing here releases a hold by itself, and no other check is touched.

Usage:
  python3 pipelines/coverage_triage.py report fantasycalc
  python3 pipelines/coverage_triage.py report cbs --rev 958b8018
  python3 pipelines/coverage_triage.py accept cbs --names \\
      --approve "Jeremy 2026-10-16 genuine roster rotation"
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE_REL = "data/fixtures/current/comparison-sources-data.json"
PLAYERS_REL = "data/fixtures/current/players.json"
SLEEPER_REL = "data/inputs/sleeper_identity_base.json"
STATUS_RELS = ("dist/modules/comparison-chain-status.json",
               "output/comparison-chain-status.json")
ACCEPTED_REL = "data/triage/coverage-accepted.json"
POSITIONS = ("QB", "RB", "WR", "TE")

ROTATION_ROSTER = {
    "injured_reserve": "on injured reserve",
    "pup": "on PUP",
    "practice_squad": "on the practice squad",
    "free_agent": "a free agent (cut or unsigned)",
}
SLEEPER_OUT = {"Inactive": "Sleeper status Inactive", "Retired": "retired"}
TAIL_FRAC = 0.10  # reviewer's tail rule: native within 10% of the position floor-to-top span
STARTER_DEPTH = 3  # depth_chart_order at or below this is a player the list should price

CHECK_RE = re.compile(
    r"coverage:(?P<combo>\w+)/(?P<pos>QB|RB|WR|TE):fail -- candidate priced "
    r"(?P<c>\d+) < fixture (?P<f>\d+) \(dropped: (?P<dropped>.*?); added: (?P<added>.*?)\)"
    r"(?: -- (?P<verify>.*?))?(?=; (?:coverage|native_drift|zero_)|\. A hold|$)")


def _git_show(rev, rel):
    out = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=REPO,
                         capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"git show {rev}:{rel} failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def _load(rel, rev=None):
    return _git_show(rev, rel) if rev else json.loads((REPO / rel).read_text())


def load_status(rev=None, path=None):
    if path:
        return json.loads(Path(path).read_text())
    for rel in STATUS_RELS:
        try:
            return _load(rel, rev)
        except (OSError, SystemExit):
            continue
    raise SystemExit("no chain status file found (pass --status-file)")


def _names(text):
    text = text.strip()
    return [] if text in ("", "none", "none named") else [n.strip() for n in text.split(",") if n.strip()]


def drops_from_reviews(source, review_glob=None):
    """[(combo, pos, cand_n, fix_n, dropped, added)] from review artifacts that failed coverage."""
    pattern = review_glob or str(REPO / "output" / "reviewed" / f"{source}-*-review.json")
    rows, used = [], []
    for path in sorted(glob.glob(pattern)):
        rev = json.loads(Path(path).read_text())
        if rev.get("source_key") != source:
            continue
        failed = {c["name"] for c in rev.get("checks", []) if c.get("status") == "fail"}
        for combo, detail in (rev.get("combos") or {}).items():
            for pos, cov in (detail.get("coverage") or {}).items():
                if f"coverage:{combo}/{pos}" in failed:
                    rows.append((combo, pos, cov["candidate"], cov["fixture"],
                                 list(cov.get("dropped") or []), list(cov.get("added") or []), False))
                    used.append(path)
    return rows, sorted(set(used))


def drops_from_status(source, status):
    # held_detail may carry a different hold's text (a fidelity hold); scan both
    text = " ".join([((status.get("held_detail") or {}).get(source) or {}).get("detail") or "",
                     str((status.get("sources") or {}).get(source) or "")])
    rows = []
    for m in CHECK_RE.finditer(text):
        dropped = _names(m["dropped"])
        # the reviewer prints at most 8 names; a count gap larger than the list means truncated
        truncated = int(m["f"]) - int(m["c"]) > len(dropped) and len(dropped) >= 8
        rows.append((m["combo"], m["pos"], int(m["c"]), int(m["f"]),
                     dropped, _names(m["added"]), truncated))
        VERIFY[(m["combo"], m["pos"])] = (m["verify"] or "").strip()
    return rows


VERIFY = {}  # (combo, pos) -> the reviewer's live-verification / churn text


class Directory:
    """Fixture section + players + Sleeper base, for last value, rank, team, status."""

    def __init__(self, source, rev=None):
        fixture = _load(FIXTURE_REL, rev)
        self.keys = fixture.get("player_keys", {})
        self.section = fixture["sources"][source]
        self.players = {p["player_key"]: p for p in _load(PLAYERS_REL, rev)["players"]}
        try:
            self.sleeper = _load(SLEEPER_REL, rev).get("by_sleeper_id", {})
        except (OSError, SystemExit):
            self.sleeper = {}

    def pos_of(self, slug):
        return (self.players.get(self.keys.get(slug)) or {}).get("pos")

    def describe(self, combo, pos, slug):
        c = self.section["combos"][combo]
        reidx = c.get("reindexed") or c.get("values") or {}
        native = c.get("native") or {}
        in_fixture = slug in reidx
        ranked = sorted((s for s in reidx if self.pos_of(s) == pos),
                        key=lambda s: -float(reidx[s] or 0))
        rank = ranked.index(slug) + 1 if slug in ranked else None
        pl = self.players.get(self.keys.get(slug)) or {}
        sl = self.sleeper.get(str(pl.get("sleeper_id"))) or {}
        nats = [float(native.get(s) or 0) for s in ranked]
        floor, top = (min(nats), max(nats)) if nats else (0.0, 0.0)
        tail = top > floor and float(native.get(slug) or 0) - floor < TAIL_FRAC * (top - floor)
        return {
            "tail": tail, "slug": slug, "name": pl.get("name") or slug, "team": pl.get("team") or sl.get("team") or "-",
            "value": reidx.get(slug), "native": native.get(slug), "rank": rank, "of": len(ranked),
            "roster_status": pl.get("roster_status"), "depth": pl.get("depth_chart_order"),
            "sleeper_status": sl.get("status"), "in_fixture": in_fixture, "known": bool(pl),
        }


def classify(d):
    """('rotation'|'scrape'|'unclear', why)."""
    if not d["known"]:
        return "unclear", "not in players.json (no status to check)"
    why = []
    rs = d["roster_status"]
    if rs in ROTATION_ROSTER:
        return "rotation", ROTATION_ROSTER[rs]
    if d["sleeper_status"] in SLEEPER_OUT:
        return "rotation", SLEEPER_OUT[d["sleeper_status"]]
    if d["team"] in ("-", None):
        return "rotation", "no NFL team"
    if rs == "active_roster":
        depth = d["depth"]
        if depth is not None and depth <= STARTER_DEPTH:
            if d["tail"]:
                return "tail", (f"active roster, depth {depth} ({d['team']}), but at the tail of the list: "
                                "publisher list trimming is possible")
            return "scrape", (f"active roster, depth {depth} ({d['team']}), mid-list value -- "
                              "still plays, so a list loss is not a rotation")
        return "unclear", f"active roster, depth {depth if depth is not None else 'n/a'} -- deep bench; could be list churn"
    return "unclear", f"roster status {rs or 'unknown'}"


def fmt_val(v):
    return "-" if v is None else f"{float(v):.1f}"


def build_brief(source, rows, directory, status, origin):
    lines = [f"# {source} coverage triage (week {status.get('nfl_week')}, chain run {status.get('run_at')})",
             f"drops from: {origin}", ""]
    verdicts = []
    lines.append("## Coverage vs floor")
    lines.append("combo / pos | candidate | fixture floor | net")
    for combo, pos, c, f, dropped, added, truncated in rows:
        lines.append(f"{combo} / {pos} | {c} | {f} | -{f - c}")
    lines.append("")
    lines.append("## Players that dropped out (last accepted section = fixture)")
    for combo, pos, c, f, dropped, added, truncated in rows:
        lines.append(f"{combo} / {pos}: {len(dropped)} named dropped, added: {', '.join(added) or 'none'}"
                     + ("  (name list truncated by the reviewer; use --review for all)" if truncated else ""))
        if VERIFY.get((combo, pos)):
            lines.append(f"  reviewer: {VERIFY[(combo, pos)]}")
        for slug in dropped:
            d = directory.describe(combo, pos, slug)
            kind, why = classify(d)
            verdicts.append(kind)
            where = "" if d["in_fixture"] else " [not in fixture section: already refreshed since]"
            rank = f"#{d['rank']} of {d['of']}" if d["rank"] else "unranked"
            lines.append(f"  - {d['name']} ({d['team']}) value {fmt_val(d['value'])} native {fmt_val(d['native'])} "
                         f"{rank} {pos} -> {kind.upper()}: {why}{where}")
        if not dropped:
            verdicts.append("unclear")
            lines.append("  - no player named: counts disagree with the priced sets")
    lines.append("")
    n = {k: verdicts.count(k) for k in ("rotation", "scrape", "tail", "unclear")}
    lines.append(f"Summary: {n['rotation']} plausible rotation, {n['scrape']} likely scrape loss, "
                 f"{n['tail']} active but tail-of-list, {n['unclear']} unclear.")
    lines.append("")
    live = [k for k, v in VERIFY.items() if "still priced live" in v]
    if live:
        rec = "C"
        why = ("the reviewer found a dropped player still priced on the live source (a pipeline loss); the review "
               "will not accept a drop the source contradicts, so A and B would stay held. Fix the match/producer.")
    elif n["scrape"]:
        rec = "C"
        why = (f"{n['scrape']} dropped player(s) are active, depth-chart players; accepting would price the chart "
               "without them. Fix the producer/match and re-run.")
    elif n["unclear"] == 0 and n["tail"] == 0 and n["rotation"]:
        rec, why = "A", "every dropped player is out of the league or off the active roster."
    else:
        rec = "B"
        why = "no mid-list starter lost; the drops are tail-of-list or not attributable to status, so reset the floor."
    lines.append("## Options")
    lines.append("A. Accept the genuine rotation: pass exactly the named drops for this content week. The fixture floor "
                 "follows when the next chain run promotes the candidate.")
    lines.append(f"   python3 pipelines/coverage_triage.py accept {source} --names --approve \"Jeremy <date> <reason>\"")
    lines.append("B. Refresh the floor from the reviewed candidate: pass any drop down to the candidate's count, named or not "
                 "(the publisher resized its list). Use when names do not tell the story.")
    lines.append(f"   python3 pipelines/coverage_triage.py accept {source} --floor --approve \"Jeremy <date> <reason>\"")
    lines.append("C. Neither (scrape loss): leave the hold; fix the producer or match, then re-run the producer and chain.")
    lines.append("   gh workflow run rebuild-chain.yml")
    lines.append("After A or B: commit data/triage/coverage-accepted.json to main, then dispatch the chain "
                 "(`gh workflow run rebuild-chain.yml`); its review passes only that decision and promotes.")
    lines.append(f"Recommendation: {rec} -- {why}")
    return "\n".join(lines), rec


def accept(source, rows, week, approve, kind, accepted_path):
    if not re.match(r"^\S+ \d{4}-\d{2}-\d{2} \S", approve or ""):
        raise SystemExit('--approve must be "<name> <YYYY-MM-DD> <reason>"')
    name, day, reason = approve.split(" ", 2)
    path = Path(accepted_path)
    doc = json.loads(path.read_text()) if path.is_file() else {
        "_note": "Recorded coverage decisions (JEG-667). review_comparison_candidate passes a coverage drop only "
                 "when an entry matches source, combo, position and content week.", "entries": []}
    for combo, pos, c, f, dropped, added, truncated in rows:
        if kind == "names" and (truncated or not dropped):
            raise SystemExit(f"{combo}/{pos}: dropped names are incomplete; pass --review or use --floor")
        entry = {"source": source, "combo": combo, "pos": pos, "week": week,
                 "approved_by": name, "approved_on": day, "reason": reason}
        entry.update({"names": sorted(dropped)} if kind == "names" else {"floor": c})
        doc["entries"] = [e for e in doc["entries"]
                          if (e["source"], e["combo"], e["pos"], e["week"]) != (source, combo, pos, week)]
        doc["entries"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1) + "\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("report", "accept"))
    ap.add_argument("source")
    ap.add_argument("--rev", help="git revision to read the status file and fixture from")
    ap.add_argument("--status-file")
    ap.add_argument("--review", help="glob of review artifacts (default output/reviewed/<source>-*-review.json)")
    ap.add_argument("--approve")
    ap.add_argument("--names", action="store_true")
    ap.add_argument("--floor", action="store_true")
    ap.add_argument("--accepted-file", default=str(REPO / ACCEPTED_REL))
    args = ap.parse_args(argv)

    status = load_status(args.rev, args.status_file)
    rows, used = drops_from_reviews(args.source, args.review)
    origin = ", ".join(used) if rows else None
    if not rows:
        rows = drops_from_status(args.source, status)
        origin = f"chain status file (run {status.get('run_at')}), failing-check text"
    if not rows:
        print(f"{args.source}: no coverage failure in the review artifacts or the chain status; nothing to triage.")
        return 0
    directory = Directory(args.source, args.rev)
    if args.cmd == "report":
        text, _ = build_brief(args.source, rows, directory, status, origin)
        print(text)
        return 0
    if args.names == args.floor:
        raise SystemExit("accept needs exactly one of --names (option A) or --floor (option B)")
    week = status.get("nfl_week")
    path = accept(args.source, rows, week, args.approve, "names" if args.names else "floor", args.accepted_file)
    print(f"recorded {'named drops' if args.names else 'floor'} for {args.source} week {week} -> {path}")
    print("commit it to main and dispatch the chain; the review passes exactly this decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
