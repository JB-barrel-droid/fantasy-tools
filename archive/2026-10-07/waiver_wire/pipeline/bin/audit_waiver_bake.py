#!/usr/bin/env python3
"""Pre-publish bake-consistency gate for the waiver dashboard artifact.

The waiver dashboard (ts-spaces/waiver-dashboard) is a static artifact:
its client code is written against the CURRENT builder schema, but the
baked `const board = {...}` data is injected by hand (builder subagent) -
nothing verifies the bake matches the pipeline output. The 2026-09-16/17
miss: the artifact baked pool.vegas / pool.frozen_vegas / value_weeks.vegas
while the client reads pool.monday / pool.frozen_blend / value_weeks.espn -
so every non-default settings vector rendered "—", the 0-70 scale fell back
to 1, and the ESPN week label read "Week unavailable".

This gate compares lottery/results/waiver_dashboard_data.json against the
baked board in the artifact. Run it before ANY waiver-dashboard publish;
exit 1 (CRITICAL) blocks publish.

Checks (CRITICAL unless noted):
  - baked board parses (fail-closed: an unparseable bake is not a pass)
  - baked as_of == pipeline as_of (stale bake)
  - baked board_week == pipeline board_week (WARN)
  - baked pool keys == pipeline pool keys (schema drift - the vegas/espn
    class: client reads pool[source] with source in {monday, ecr})
  - baked value_weeks keys == pipeline value_weeks keys (label drift -
    hydrateWeekLabels reads value_weeks[monday|ecr|espn])
  - baked board carries monday_leg_source (per-leg provenance; the client
    contract needs it to label Monday-imputed vs reassessed vs current legs)

Usage: python3 bin/audit_waiver_bake.py [--data PATH] [--artifact PATH]
"""
import argparse
import re
import json
import sys
from pathlib import Path

LOT = Path(__file__).resolve().parent.parent
DATA = LOT / "results" / "waiver_dashboard_data.json"
ARTIFACT = LOT.parent.parent / "waiver_wire" / "dashboard" / "index.html"


def extract_baked_board(html_path):
    """Return the baked board dict, or (None, reason).

    Brace-matches from 'const board = {' so key order doesn't matter;
    string literals (with escapes) are skipped so prose braces can't
    unbalance the scan. Fail-closed: anything unparseable is a gate
    failure, never a pass.
    """
    try:
        html = Path(html_path).read_text()
    except OSError as e:
        return None, "artifact unreadable: %s" % e
    marker = "const board = {"
    start = html.find(marker)
    if start < 0:
        return None, "no 'const board = {' in artifact"
    i = start + len("const board = ")
    depth, in_str, esc = 0, False, False
    for j in range(i, len(html)):
        ch = html[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = html[i:j + 1]
                try:
                    return json.loads(raw), ""
                except json.JSONDecodeError as e:
                    return None, "baked board is not valid JSON: %s" % e
    return None, "baked board braces never balanced"


def audit(data_path=DATA, artifact_path=ARTIFACT):
    crit, warn = [], []
    try:
        pipe = json.loads(Path(data_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        return ["waiver_dashboard_data.json unreadable: %s" % e], []
    baked, reason = extract_baked_board(artifact_path)
    if baked is None:
        return ["baked board: %s" % reason], []

    if baked.get("as_of") != pipe.get("as_of"):
        crit.append("STALE BAKE: artifact as_of %r != pipeline as_of %r - "
                    "re-bake before publish"
                    % (baked.get("as_of"), pipe.get("as_of")))
    if baked.get("board_week") != pipe.get("board_week"):
        warn.append("baked board_week %r != pipeline %r"
                    % (baked.get("board_week"), pipe.get("board_week")))

    bp, pp = set((baked.get("pool") or {}).keys()), set((pipe.get("pool") or {}).keys())
    if bp != pp:
        crit.append("SCHEMA DRIFT: baked pool keys %s != pipeline pool keys %s "
                    "- client reads pool[monday|ecr|frozen_blend]"
                    % (sorted(bp), sorted(pp)))
    bv, pv = set((baked.get("value_weeks") or {}).keys()), set((pipe.get("value_weeks") or {}).keys())
    if bv != pv:
        crit.append("LABEL DRIFT: baked value_weeks keys %s != pipeline %s - "
                    "week labels render 'Week unavailable'"
                    % (sorted(bv), sorted(pv)))
    if "monday_leg_source" not in baked and "monday_leg_source" in pipe:
        crit.append("PROVENANCE GAP: baked board lacks monday_leg_source - "
                    "per-leg as-of (Monday-imputed vs reassessed vs current) "
                    "cannot be labeled")

    # WEEK2 BLOCK (2026-09-18): the Week 2 source toggle (ECR/Vegas/ESPN)
    # reads board.week2. A bake without it renders every Week 2 cell as "—".
    bw, pw = baked.get("week2"), pipe.get("week2")
    if pw and not bw:
        crit.append("WEEK2 GAP: pipeline ships a week2 block but the baked "
                    "board lacks it - the Week 2 source toggle renders empty")
    elif bw and pw:
        if bw.get("week") != pw.get("week"):
            crit.append("WEEK2 DRIFT: baked week2.week %r != pipeline %r"
                        % (bw.get("week"), pw.get("week")))
        bs, ps = set((bw.get("scoring") or {}).keys()), set((pw.get("scoring") or {}).keys())
        if bs != ps:
            crit.append("WEEK2 DRIFT: baked week2 scorings %s != pipeline %s"
                        % (sorted(bs), sorted(ps)))

    # Row-count sanity: the bake should carry the same sections.
    b_secs = {s.get("id"): len(s.get("players", []))
              for s in baked.get("sections", [])}
    p_secs = {s.get("id"): len(s.get("players", []))
              for s in pipe.get("sections", [])}
    if b_secs != p_secs:
        crit.append("section row counts differ: baked %s vs pipeline %s"
                    % (b_secs, p_secs))

    # LEAKAGE (fail-closed, 2026-09-18): exact Sleeper add counts are
    # internal-only. They must never appear in public strings (what_changed,
    # verbal, notes) or as numeric fields in the baked data. Hot pickups stay
    # ranked by adds - rank carries the order publicly.
    leak_pat = re.compile(
        r"\d{1,3}(,\d{3})+\s*(adds|managers|teams)\b|\badded\s+\d{4,}\b",
        re.I)
    def _strings(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from _strings(v, path + "/" + str(k))
        elif isinstance(o, list):
            for n, v in enumerate(o):
                yield from _strings(v, "%s[%d]" % (path, n))
        elif isinstance(o, str):
            yield path, o
    for label, doc in (("pipeline", pipe), ("baked", baked)):
        for path, s in _strings(doc):
            if leak_pat.search(s):
                crit.append(
                    "SLEEPER LEAKAGE in %s %s: exact add count in public copy - "
                    "fix the builder, not the frontend" % (label, path))
                break
        # numeric sleeper_adds fields must not ship either
        for sec in doc.get("sections", []):
            for p in sec.get("players", []):
                if isinstance(p.get("sleeper_adds"), (int, float)):
                    crit.append(
                        "SLEEPER LEAKAGE in %s: numeric sleeper_adds on %s - "
                        "remove the field; rank carries the order"
                        % (label, p.get("name")))
                    break
    return crit, warn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--artifact", default=str(ARTIFACT))
    args = ap.parse_args()
    crit, warn = audit(args.data, args.artifact)
    print("waiver bake audit: %d CRITICAL, %d WARN" % (len(crit), len(warn)))
    for m in crit:
        print("CRITICAL:", m)
    for m in warn:
        print("WARN:", m)
    return 1 if crit else 0


if __name__ == "__main__":
    sys.exit(main())
