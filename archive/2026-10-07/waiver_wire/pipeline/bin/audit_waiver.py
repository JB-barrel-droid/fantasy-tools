#!/usr/bin/env python3
"""Fail-closed audit for the finite-capacity waiver dashboard.

Two modes:
  python3 bin/audit_waiver.py                 # audit the built default-vector JSON
  python3 bin/audit_waiver.py --teams 14 --bench 10   # validate a non-default
                                              # settings vector's boundary math
                                              # (no JSON written)

Contract checks (CRITICAL unless noted) -- user taxonomy 2026-09-16:
- Sections: hot_pickups, add, hold, hold_steady, drop (+ top-level browse).
  dont_add is gone (absorbed into hot_pickups PASS verdicts).
- Hot pickups: top 15 most-added since Sunday (available, priced, not
  holds/drops), ranked by adds. Verdict per row: ADD = entrant or new>=4,
  PASS = fringe/zero. Verdict id/label must agree.
- Adds ("Other pickups we like"): available entrants NOT on the hot list,
  new>0. Never a 0->0 card. Ranked by highest updated value.
- Drops: genuinely displaced AND moved to 0 (old>0). Never a 0->0 card.
- Visible Add and Drop counts NEED NOT match.
- Holds: in-both old>=10 -> 0<new<10 (zero is reserved for Drops),
  plus displaced-but-positive. No roster% filter. Every hold keeps
  positive value and carries why_hold.
- Hold-steady ("Didn't change, but should be rostered"): in-both, still
  positive, not a hold and not a mover section. Every row keeps positive
  Monday value.
- Section membership AND order must equal the recomputed boundary exactly
  (the audit re-derives boundary() from the JSON's own settings - the
  recompute is verified deterministic).
- No player in multiple sections.
- No 0->0 Add or Drop card, anywhere.
- Unchanged players are never described as declining.
- Old displayed value is trade_value_upside (chart base + edge).
- Allgeier 5->5 + no stale copy; Kupp never "established veteran";
  "longtime veteran" only.
- run_weekly.sh runs this for the default vector AND at least one
  non-default vector.

Card-coherence checks (Golden/Coker rules) over EVERY renderable row
(sections + gated_out + drop_pool + corrections): see check_row.

Exit 1 on any CRITICAL.
"""
import argparse
import json
import re
import sys
from pathlib import Path

LOT = Path(__file__).resolve().parent.parent
BIN = LOT / "bin"
sys.path.insert(0, str(BIN))
import build_waiver_dashboard_data as B  # noqa: E402  (norm_name, TRENDS,
# _CURATED_NORMS, _evidence_verdict, AGGR_NOTES, CONV_NOTES - the builder is
# the single source of truth)
from chart_paths import CHART_PLAYERS_JSON  # noqa: E402

DATA = LOT / "results" / "waiver_dashboard_data.json"
PLAYERS_JSON = CHART_PLAYERS_JSON

NOTHING_RE = re.compile(r"nothing,? really|essentially nothing", re.I)
PRICED_IN_RE = re.compile(r"(upside|value) was priced in", re.I)
MOVE_RES = [
    re.compile(r"moved (?:him |her |them )?from (\d+) to (\d+)"),
    re.compile(r"that's the (\d+) to (\d+)"),
    re.compile(r"hence (\d+) to (\d+)"),
]
MONDAY_CLAIM_RE = re.compile(r"\(Monday value (\d+)\)")
XFP_RE = re.compile(r"(\d+\.\d+) expected points")
PMM_MENTION_RE = re.compile(r"([A-Z][A-Za-z'\-]+(?: [A-Z][A-Za-z'\-]+)+) \(([A-Z]{2,3})\)")

EXPECTED_SECTIONS = {"hot_pickups", "add", "hold", "hold_steady", "drop"}


def _taxonomy_crit(bnd):
    """Boundary-level taxonomy invariants for any settings vector."""
    from waiver_boundary import visible_sections
    crit = []
    v = bnd["values"]
    adds, drops = visible_sections(bnd)  # raises on parity break
    O, M = set(bnd["O"]), set(bnd["M"])
    inboth = O & M
    avail = set(bnd["available"])

    # Boundary parity + capacity (also asserted inside boundary()).
    if len(bnd["entrants"]) != len(bnd["displaced"]):
        crit.append(f"entrant/displaced parity broken: {len(bnd['entrants'])} "
                    f"vs {len(bnd['displaced'])}")
    if len(O) != bnd["capacity"] or len(M) != bnd["capacity"]:
        crit.append(f"O/M != capacity: |O|={len(O)} |M|={len(M)} "
                    f"cap={bnd['capacity']}")

    # Adds: available entrants with new>0, not on the hot list. In-both
    # risers are NOT adds (they "didn't move") - user taxonomy 2026-09-16.
    for p in adds:
        old, new = v[p]["old"], v[p]["new"]
        is_entrant = p in bnd["entrants"] and p in avail and new > 0
        if not is_entrant:
            crit.append(f"ADD {p}: not an available entrant ({old}->{new})")
        if old == 0 and new == 0:
            crit.append(f"ADD {p}: manufactured 0->0 card")

    # Drops: genuinely displaced, moved to 0, held value before.
    for p in drops:
        old, new = v[p]["old"], v[p]["new"]
        if p not in bnd["displaced"]:
            crit.append(f"DROP {p}: not genuinely displaced")
        if new != 0:
            crit.append(f"DROP {p}: monday_value must be 0, got {new!r}")
        if old <= 0:
            crit.append(f"DROP {p}: never held a roster spot ({old}->{new})")
        if old == 0 and new == 0:
            crit.append(f"DROP {p}: manufactured 0->0 card")

    # Holds: old>=10 -> 0<new<10 (zero is reserved for Drops), or
    # displaced-but-positive. No roster% filter by user rule.
    disp_up = set(bnd["displaced_upside"])
    for p in bnd["holds"]:
        old, new = v[p]["old"], v[p]["new"]
        inboth_hold = (p in inboth and old >= 10 and 0 < new < 10)
        if not (inboth_hold or p in disp_up):
            crit.append(f"HOLD {p}: matches neither hold rule ({old}->{new})")
        if not (isinstance(new, int) and new > 0):
            crit.append(f"HOLD {p}: monday_value must be int > 0, got {new!r}")

    # Visible Add and Drop counts NEED NOT match - no check here by design.
    exp_cap = bnd["teams"] * (sum(bnd["slots"].values()) + bnd["bench"])
    if bnd["capacity"] != exp_cap:
        crit.append(f"capacity math wrong: {bnd['capacity']} != {exp_cap}")
    return crit


def check_vector(teams, bench):
    """Validate a settings vector's boundary math without writing JSON."""
    from waiver_boundary import boundary, DEFAULT_SLOTS
    bnd = boundary(teams=teams, slots=dict(DEFAULT_SLOTS), bench=bench,
                   scoring="half")
    crit = _taxonomy_crit(bnd)
    v = bnd["values"]
    for p in bnd["adds"]:
        mv = v[p]["new"]
        if not isinstance(mv, int) or mv < 0:
            crit.append(f"ADD {p}: monday_value must be int >= 0, got {mv!r}")
    print(f"vector half/{teams}t/bench{bench}: adds={len(bnd['adds'])} "
          f"drops={len(bnd['drops'])} holds={len(bnd['holds'])} "
          f"cap={bnd['capacity']}: {len(crit)} CRITICAL")
    for m in crit:
        print("CRITICAL:", m)
    return 1 if crit else 0


def check_row(name, p, origin, crit, warn):
    norm = B.norm_name(name)
    chart = p.get("chart_value")
    monday = p.get("monday_value")
    copy = " ".join(str(p.get(k) or "") for k in ("what_changed", "verbal"))
    note = str(p.get("imputed_tv_note") or "")
    tag = f"{name} [{origin}]"
    move = (abs(monday - chart)
            if isinstance(monday, int) and isinstance(chart, int) else 0)

    if NOTHING_RE.search(copy) and move >= 5:
        crit.append(f"{tag}: 'nothing changed' copy next to a "
                    f"{chart}->{monday} move")
    if PRICED_IN_RE.search(copy) and isinstance(chart, int) and chart <= 2:
        crit.append(f"{tag}: 'priced in' copy with chart value {chart}")
    for rx in MOVE_RES:
        for m in rx.finditer(copy):
            if (int(m.group(1)), int(m.group(2))) != (chart, monday):
                crit.append(f"{tag}: claims move {m.group(1)}->{m.group(2)} "
                            f"but card shows {chart}->{monday}")
    if re.search(r"(?<!projection )nudged (up|down)", note):
        crit.append(f"{tag}: note claims a nudge without saying 'projection'")
    for m in MONDAY_CLAIM_RE.finditer(copy):
        if int(m.group(1)) != monday:
            crit.append(f"{tag}: claims Monday value {m.group(1)} "
                        f"but row shows {monday}")
    ag = p.get("aggression")
    if ag is not None:
        if not (isinstance(ag, dict) and ag.get("level") in B.AGGR_NOTES):
            crit.append(f"{tag}: aggression is not a level/note dict: {ag!r}")
        elif ag["note"] != B.AGGR_NOTES[ag["level"]]:
            crit.append(f"{tag}: aggression {ag['level']} carries a mismatched note")
    cv = p.get("conviction")
    if cv is not None:
        if not (isinstance(cv, dict) and cv.get("level") in B.CONV_NOTES):
            crit.append(f"{tag}: conviction is not a level/note dict: {cv!r}")
        elif cv["note"] != B.CONV_NOTES[cv["level"]]:
            crit.append(f"{tag}: conviction {cv['level']} carries a mismatched note")
    if (not p.get("established")) and re.search(r"established role", copy, re.I):
        crit.append(f"{tag}: 'established role' copy but established flag is False")

    # A row with trend evidence in the pipeline must carry its trend card.
    if B.TRENDS.get(norm) is not None and p.get("trend") is None:
        crit.append(f"{tag}: trend evidence exists but row carries no trend card")

    # Add-section schema parity: the card renderer expects the full shape.
    if origin == "add":
        for field in ("verbal", "aggression", "what_changed", "trend",
                      "imputed_tv", "imputed_tv_note", "case"):
            if p.get(field) is None:
                crit.append(f"{tag}: add row missing '{field}'")

    # Hot-pickup rows carry a verdict instead of a case.
    # (2026-09-18: sleeper_adds removed - exact add counts are internal-only;
    # rank carries the most-added order publicly.)
    if origin == "hot_pickups":
        for field in ("verbal", "aggression", "what_changed", "trend",
                      "imputed_tv", "imputed_tv_note", "verdict",
                      "rank"):
            if p.get(field) is None:
                crit.append(f"{tag}: hot_pickups row missing '{field}'")

    # The evidence override must fire for non-curated decisive evidence.
    t = B.TRENDS.get(norm)
    if (t and t.get("verdict") == 0 and norm not in B._CURATED_NORMS
            and B._evidence_verdict(t) != 0):
        tv = (p.get("trend") or {}).get("verdict")
        if tv == "No signal":
            crit.append(f"{tag}: decisive usage evidence rendered as 'No signal'")

    if re.search(r"barely valued", copy, re.I) and isinstance(monday, int) and monday >= 5:
        warn.append(f"{tag}: 'barely valued' copy next to Monday value {monday}")
    if ((not p.get("established")) and "kupp" not in name.lower()
            and re.search(r"established veteran", copy, re.I)):
        warn.append(f"{tag}: 'established veteran' copy but established flag is False")
    ev = (p.get("trend") or {}).get("evidence") or ""
    xfps = [float(x) for x in XFP_RE.findall(note)] + [float(x) for x in XFP_RE.findall(ev)]
    if xfps and max(xfps) - min(xfps) > 2.0:
        warn.append(f"{tag}: expected-points figures disagree across boxes "
                    f"({min(xfps):.1f} vs {max(xfps):.1f})")


def check_json():
    crit, warn = [], []
    d = json.loads(DATA.read_text())
    secs = {s["id"]: s for s in d.get("sections", [])}
    b = d.get("boundary", {})

    # ---- 1. Sections present, no unknown sections, no subgroups ----
    for sid in EXPECTED_SECTIONS:
        if sid not in secs:
            crit.append(f"expected section missing: {sid}")
    for sid in secs:
        if sid not in EXPECTED_SECTIONS:
            crit.append(f"unexpected section: {sid} (audit taxonomy is "
                        f"{sorted(EXPECTED_SECTIONS)})")
    for sid, s in secs.items():
        for g in s.get("groups", []) or []:
            crit.append(f"section {sid} still carries a subgroup: "
                        f"{g.get('id') or g.get('label') or '?'}")

    # ---- 1b. Membership/order/verdicts vs the recomputed boundary ----
    # The builder's sections must equal boundary() re-derived from the JSON's
    # own settings (verified deterministic). Verdict rule: ADD = entrant or
    # new>=4, PASS = fringe/zero.
    _bnd = None
    try:
        from waiver_boundary import boundary as _boundary
        from waiver_boundary import visible_sections as _visible_sections
        _bnd = _boundary(teams=b.get("teams"), slots=dict(b.get("slots")),
                         bench=b.get("bench"),
                         scoring=(b.get("scoring") or "half"))
    except Exception as e:
        crit.append(f"boundary recompute failed: {e}")
    if _bnd is not None:
        try:
            _adds, _drops = _visible_sections(_bnd)
        except Exception as e:
            crit.append(f"visible_sections failed on recompute: {e}")
            _adds, _drops = [], []
        _exp = {"hot_pickups": _bnd["hot_pickups"], "add": _adds,
                "hold": _bnd["holds"], "hold_steady": _bnd["hold_steady"],
                "drop": _drops}
        _entrants = set(_bnd.get("entrants", []))
        for sid, want in _exp.items():
            got = [B.norm_name(p["name"])
                   for p in secs.get(sid, {}).get("players", [])]
            if got != list(want):
                crit.append(f"{sid}: membership/order differs from boundary "
                            f"(got {len(got)}, want {len(want)})")
        for p in secs.get("hot_pickups", {}).get("players", []):
            pid = B.norm_name(p["name"])
            new = p.get("monday_value")
            vd = p.get("verdict") or {}
            if vd.get("id") not in ("add", "pass") or \
                    vd.get("label") not in ("ADD", "PASS"):
                crit.append(f"HOT {p['name']}: verdict must be add/ADD or "
                            f"pass/PASS, got {vd!r}")
                continue
            if (vd["id"] == "add") != (vd["label"] == "ADD"):
                crit.append(f"HOT {p['name']}: verdict id/label mismatch: "
                            f"{vd!r}")
            should_add = (pid in _entrants) or \
                (isinstance(new, int) and new >= 4)
            if should_add and vd["id"] != "add":
                crit.append(f"HOT {p['name']}: entrant-or-value>=4 must be "
                            f"ADD, got {vd['label']}")
            if not should_add and vd["id"] != "pass":
                crit.append(f"HOT {p['name']}: fringe/zero must be PASS, got "
                            f"{vd['label']}")

    # ---- 2. Boundary metadata: capacity math; counts reconcile ----
    for k in ("capacity", "teams", "bench", "adds", "drops", "holds",
              "hold_steady", "entrants", "displaced"):
        if k not in b:
            crit.append(f"boundary metadata missing: {k}")
    # Boundary parity lives here too (belt and suspenders with boundary()).
    if b.get("entrants") != b.get("displaced"):
        crit.append(f"entrant/displaced parity violated: "
                    f"{b.get('entrants')} vs {b.get('displaced')}")
    n_add = len(secs.get("add", {}).get("players", []))
    n_drop = len(secs.get("drop", {}).get("players", []))
    n_hold = len(secs.get("hold", {}).get("players", []))
    n_steady = len(secs.get("hold_steady", {}).get("players", []))
    if b.get("adds") != n_add:
        crit.append(f"boundary.adds={b.get('adds')} != add section size {n_add}")
    if b.get("drops") != n_drop:
        crit.append(f"boundary.drops={b.get('drops')} != drop section size {n_drop}")
    if b.get("holds") != n_hold:
        crit.append(f"boundary.holds={b.get('holds')} != hold section size {n_hold}")
    if b.get("hold_steady") != n_steady:
        crit.append(f"boundary.hold_steady={b.get('hold_steady')} != hold_steady "
                    f"section size {n_steady}")
    # Visible Add and Drop counts NEED NOT match - no parity check by design.
    slots = b.get("slots", {})
    if slots and b.get("capacity") is not None:
        expect = b["teams"] * (sum(slots.values()) + b["bench"])
        if expect != b["capacity"]:
            crit.append(f"capacity math wrong: teams*slots+bench={expect} "
                        f"!= {b['capacity']}")

    # ---- 3. No duplicates across sections ----
    seen = {}
    for sid, s in secs.items():
        for p in s.get("players", []):
            if p["name"] in seen:
                crit.append(f"duplicate player: {p['name']} in {seen[p['name']]} and {sid}")
            seen[p["name"]] = sid

    # ---- 4. Value invariants (user taxonomy) ----
    for p in secs.get("add", {}).get("players", []):
        mv, cv = p.get("monday_value"), p.get("chart_value")
        if not isinstance(mv, int) or mv <= 0:
            crit.append(f"ADD {p['name']}: monday_value must be int > 0, got {mv!r}")
        if cv == 0 and mv == 0:
            crit.append(f"ADD {p['name']}: manufactured 0->0 card")
    for p in secs.get("drop", {}).get("players", []):
        cv, mv = p.get("chart_value"), p.get("monday_value")
        if not isinstance(cv, int) or cv <= 0:
            crit.append(f"DROP {p['name']}: chart_value must be int > 0, got {cv!r}")
        if mv != 0:
            crit.append(f"DROP {p['name']}: monday_value must be 0, got {mv!r}")
        if cv == 0 and mv == 0:
            crit.append(f"DROP {p['name']}: manufactured 0->0 card")
    for p in secs.get("hold", {}).get("players", []):
        mv = p.get("monday_value")
        if not isinstance(mv, int) or mv <= 0:
            crit.append(f"HOLD {p['name']}: monday_value must be int > 0, got {mv!r}")
        if not p.get("why_hold"):
            crit.append(f"HOLD {p['name']}: missing why_hold explanation")
    for p in secs.get("hold_steady", {}).get("players", []):
        mv = p.get("monday_value")
        if not isinstance(mv, int) or mv <= 0:
            crit.append(f"HOLD_STEADY {p['name']}: monday_value must be int > 0, "
                        f"got {mv!r}")

    # ---- 5. Ranking: add/hold/hold_steady/drop sorted by monday_value
    # desc (WARN); hot_pickups order is pinned by the boundary check in 1b ----
    for sid in ("add", "hold", "hold_steady", "drop"):
        ps = secs.get(sid, {}).get("players", [])
        vals = [p.get("monday_value") for p in ps]
        if vals != sorted(vals, reverse=True):
            warn.append(f"{sid} not ranked by monday_value desc: {vals}")

    # ---- 6. Copy repairs + unchanged-player guard ----
    def _text(p):
        return " ".join(str(p.get(k) or "") for k in
                        ("verbal", "what_changed", "aggression_note", "conviction_note"))

    for sid, s in secs.items():
        for p in s.get("players", []):
            t = _text(p).lower()
            nm = p["name"].lower()
            cv, mv = p.get("chart_value"), p.get("monday_value")
            if "allgeier" in nm:
                for bad in ("slipped from starter to bench", "usage data disagrees",
                            "a downgrade", "the cut if you need the spot",
                            "downgrade, not a collapse"):
                    if bad in t:
                        crit.append(f"Allgeier stale copy: '{bad}'")
                if cv != 5 or mv != 5:
                    crit.append(f"Allgeier must be 5->5, got {cv}->{mv}")
            if "kupp" in nm and "established veteran" in t:
                crit.append("Kupp: 'established veteran' is false (chart < 8); "
                            "use 'longtime veteran'")
            # Unchanged players are never described as declining.
            if cv == mv and isinstance(cv, int):
                if re.search(r"\b(declined|dropped|slipped|downgrade)\b", t):
                    if "allgeier" not in nm:
                        crit.append(f"{p['name']} [{sid}]: unchanged {cv}->{mv} "
                                    f"but copy says decline/drop")

    # ---- 7. Card coherence over EVERY renderable row ----
    rows = []  # (origin, row)
    for s in d.get("sections", []):
        for p in s.get("players", []):
            rows.append((s.get("id"), p))
    for p in d.get("gated_out", []):
        rows.append(("gated_out", p))
    for p in d.get("drop_pool", []):
        rows.append(("drop_pool", p))
    for c in d.get("corrections", []):
        rows.append(("corrections", c))
    for p in d.get("browse", []):
        rows.append(("browse", p))
    if not rows:
        crit.append("zero player rows audited - data shape changed?")
    for origin, p in rows:
        check_row(p.get("name") or "?", p, origin, crit, warn)

    # ---- 8. week_read.pmm_take: "Name (TEAM)" mentions must be real ----
    take = str((d.get("week_read") or {}).get("pmm_take") or "")
    if take:
        teams = {}
        for pl in json.loads(PLAYERS_JSON.read_text())["players"]:
            teams.setdefault(pl["name"].lower(), set()).add(pl["team"])
        for m in PMM_MENTION_RE.finditer(take):
            nm, tm = m.group(1), m.group(2)
            if tm not in teams.get(nm.lower(), set()):
                warn.append(f"pmm_take: '{nm} ({tm})' matches no known player/team")

    n_rows = sum(len(s.get("players", [])) for s in secs.values())
    print(f"audited {n_rows} section rows + {len(rows) - n_rows} gated/drop_pool/"
          f"corrections rows (+pmm_take): {len(crit)} CRITICAL, "
          f"{len(warn)} WARN")
    for m in crit:
        print("CRITICAL:", m)
    for m in warn:
        print("WARN:", m)
    return 1 if crit else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", type=int, default=None)
    ap.add_argument("--bench", type=int, default=None)
    args = ap.parse_args()
    if args.teams is not None or args.bench is not None:
        sys.exit(check_vector(args.teams or 12, args.bench or 6))
    sys.exit(check_json())


if __name__ == "__main__":
    main()
