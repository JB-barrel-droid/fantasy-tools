#!/usr/bin/env python3
"""A fidelity pulse red holds that source (JEG-520).

Jeremy, 2026-10-09: a red in the fidelity pulse should hold that source,
"though with some tolerance". The tolerance lives in the pulse
(pipelines/fidelity_pulse.py RULES["tolerance"], docs/fidelity-tolerances.md):
only a red that survives it reaches `holds` in dist/modules/fidelity-pulse.json.

    python3 pipelines/fidelity_hold.py apply [--pulse P] [--week N]

Runs in the rebuild chain after the JEG-479 value-check hold, before
`make validate`. For every source the latest published pulse holds, the
source and every series derived from it (value_check.SOURCE_DERIVED) are
marked `validationHold: {reason: "fidelity: <stage>", ...}`, the same field
the page reads for JEG-479 holds: labelled, and kept out of DDF Value.

Gray out (Jeremy, 2026-10-12, JEG-569 part 2): a held source is grayed
out with no values shown, but its combos are KEPT in the fixture so the
engine can include the source in the pipeline (weights, pie, universe).
Removing a source from the pipeline would renormalize every other
source's values. The page hides a held source's curves via the
validationHold flag.

A held build must pass `make validate` (JEG-569): checks that need an
unheld baseline read tests/_holds.without_held_sources, and
tests/test_seeded_hold_build.py seeds holds and runs those checks.

A hold lasts while the pulse reports it: a section whose fidelity hold the
latest pulse no longer lists is released (its validationHold removed).
JEG-479 holds (no "fidelity: " reason) are never touched here, and
value_check.release_holds leaves fidelity holds alone.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date, datetime, timezone
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
# `lib` lives in pipelines/; make it importable whatever the CWD, checkout path or
# import order (tests import this module as pipelines.X without pipelines/ on sys.path).
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from lib.timestamps import parse_iso_timestamp  # noqa: E402
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

import value_check as vc  # noqa: E402

PULSE = REPO / "dist" / "modules" / "fidelity-pulse.json"
HOLD_PREFIX = "fidelity: "
STALE_PULSE_HOURS = 24
# JEG-1194: the pulse stamps this scope on a red that judges only a stored
# save newer than the live chart (fidelity_pulse.red_scope).
SCOPE_STORED_NEWER = "stored_newer_than_site"
# A chart section's identity is the save's pulled_at; the pulse names the save
# by its bake's saved_at, written seconds later. Saves are hours apart.
SAME_SAVE_SECONDS = 300


def is_fidelity_hold(hold) -> bool:
    return isinstance(hold, dict) and str(hold.get("reason") or "").startswith(HOLD_PREFIX)


def pulse_holds(pulse: dict | None) -> dict:
    """{root: hold} for the sources the pulse holds (roots the chain knows only)."""
    return {root: h for root, h in ((pulse or {}).get("holds") or {}).items()
            if root in vc.SOURCE_DERIVED and isinstance(h, dict) and h.get("stage")}


def _held_sections(root: str) -> list[str]:
    """The fixture sections to strip when holding a source: its own sections
    plus any derivative sections (e.g. *_adjusted for published charts)."""
    base = list(vc.SOURCE_DERIVED[root]["sections"])
    # _adjusted sections are derivatives of published charts that live in the
    # fixture but aren't tracked in SOURCE_DERIVED (retired by JEG-508).
    for sec in list(base):
        adj = f"{sec}_adjusted"
        if adj not in base:
            base.append(adj)
    return base


def section_identity(section: dict) -> str | None:
    """The build identity of a fixture section, for hold matching (JEG-799 B2).

    The pulse stamps a hold with measured_site = this value read off the live
    page; apply_fidelity_holds compares it with the candidate's. Both sides
    use this one function so they cannot drift.

    Charts: source_provenance.snapshot_fetched_at (the save the section was
    built from). Projections (JEG-807, 2026-10-22): the snapshot date, espn's
    `espn_snapshot` or cbsros/razzball's `vintage`. Before this the projection
    sections had no identity on either side (`fetched_at` is the ESPN build
    time, absent on cbsros/razzball), so a razzball hold measured on the
    10-19 chart was applied to the 10-21 candidate. `fetched_at` is the last
    resort for a chart without provenance."""
    if not isinstance(section, dict):
        return None
    prov = section.get("source_provenance") or {}
    for value in (prov.get("snapshot_fetched_at"), section.get("espn_snapshot"),
                  section.get("vintage"), section.get("fetched_at")):
        if value:
            return str(value)
    return None


_candidate_identity = section_identity


def same_save(candidate_id: str, judged: str) -> bool:
    """True when a section identity and a hold's judged_save name one save:
    equal strings (projection snapshot dates), or timestamps within
    SAME_SAVE_SECONDS (a chart's pulled_at vs its bake's saved_at)."""
    if candidate_id == judged:
        return True
    if "T" not in candidate_id or "T" not in judged:
        return False
    try:
        gap = parse_iso_timestamp(candidate_id) - parse_iso_timestamp(judged)
    except (TypeError, ValueError):
        return False
    return abs(gap.total_seconds()) <= SAME_SAVE_SECONDS


def apply_fidelity_holds(fixture: dict, holds: dict, week: int | None) -> tuple[dict, dict]:
    """Return (fixture with holds applied, {root: {sections}}).

    JEG-569 part 2 (Jeremy, 2026-10-12): a held source is grayed out on the
    page.  Its combos are KEPT so the engine can still include the source in
    the pipeline (weights, pie, universe) -- otherwise removing a source
    renormalizes every other source's values.  The page hides a held source's
    curves and values; the validationHold flag is the signal.

    JEG-799 (B2): a hold applies only to the build the pulse measured.  If the
    hold's measured_site differs from the candidate section's
    source_provenance.snapshot_fetched_at, the candidate has newer data and the
    hold is skipped.

    JEG-1194: a hold scoped SCOPE_STORED_NEWER is about a stored save newer
    than the live chart, so the match is reversed: it holds a candidate built
    from that save (its judged_save) and skips the live chart's own section
    and a build from any other save, such as a later fixed one."""
    out = copy.deepcopy(fixture)
    sources = out.setdefault("sources", {})
    report = {}
    for root, hold in holds.items():
        sections = _held_sections(root)
        hold_level = hold.get("hold_level", "red")
        measured = hold.get("measured_site")
        applied_sections = []
        skipped_sections = []
        for sec in sections:
            target = sources.get(sec)
            if isinstance(target, dict):
                # JEG-799: skip this hold when the candidate section has a
                # different identity than the build the pulse measured.
                if measured is not None:
                    candidate_id = _candidate_identity(target)
                    # JEG-1194: a red about a stored save newer than the live
                    # chart is the reverse case: it holds a build made from
                    # the save it judged and leaves the live chart (same
                    # identity) and a build from a later save unheld.
                    other_build = candidate_id is not None and candidate_id != measured
                    if hold.get("scope") == SCOPE_STORED_NEWER:
                        judged = hold.get("judged_save")
                        skip = candidate_id == measured or bool(
                            judged and other_build and not same_save(candidate_id, str(judged)))
                    else:
                        skip = other_build
                    if skip:
                        # JEG-807 (2026-10-22): the skip must not leave an
                        # older fidelity hold on the candidate. The 04:08Z
                        # chain skipped fantasycalc's and espn's holds this
                        # way and shipped their week-6 red holds on Week 7
                        # sections. A hold this pulse measured on another
                        # build says nothing about this one.
                        if is_fidelity_hold(target.get("validationHold")):
                            del target["validationHold"]
                        skipped_sections.append(sec)
                        continue
                # Keep combos intact so the engine can compute with them.
                target.pop("validationHold", None)
                target["validationHold"] = {
                    "reason": hold.get("reason") or HOLD_PREFIX + hold["stage"], "week": week, "root": root,
                    "stage": hold["stage"], "identity": hold.get("identity"),
                    "since": hold.get("since"),
                    "hold_level": hold_level}
                applied_sections.append(sec)
        if measured is not None and not applied_sections:
            # Nothing on this build carries the hold: it is not held.
            continue
        report[root] = {"sections": applied_sections if measured is not None else sections,
                        "skipped": skipped_sections,
                        "hold_level": hold_level,
                        "reason": hold.get("reason"), "summary": hold.get("summary")}
    return out, report


def release_fidelity_holds(fixture: dict, holds: dict) -> list[str]:
    """Remove (in place) fidelity holds whose root the pulse no longer holds."""
    released = []
    for sec, section in (fixture.get("sources") or {}).items():
        if not isinstance(section, dict) or not is_fidelity_hold(section.get("validationHold")):
            continue
        root = section["validationHold"].get("root") or vc.ROOT_OF.get(sec)
        if root not in holds:
            del section["validationHold"]
            released.append(sec)
    return sorted(released)


def update_chain_status(status: dict, report: dict, week: int | None) -> dict:
    status = copy.deepcopy(status or {})
    held = set(status.get("held") or [])
    detail = dict(status.get("held_detail") or {})
    for root, r in report.items():
        held.add(root)
        # JEG-807 (2026-10-22): the severity is the pulse's hold_level. This
        # used to say "amber" for every fidelity hold while the fixture carried
        # hold_level "red" (hidden from DDF Value), so the status page said
        # "labelled only" about sources the engine had dropped.
        detail[root] = {"reason": r["reason"], "held_series": vc.derived_series(root), "sections": r["sections"],
                        "detail": r["summary"], "hold_severity": r.get("hold_level") or "red", "week": week}
    status["held"] = sorted(held)
    status["held_detail"] = detail
    status["fidelity_holds"] = {root: r["reason"] for root, r in report.items()}
    severities = [d.get("hold_severity") for d in detail.values() if d.get("hold_severity")]
    status["hold_severity"] = ("red" if "red" in severities else "amber") if severities else "none"
    for key in ("status", "outcome"):
        if held and status.get(key) == "green":
            status[key] = "published_with_holds"
    return status


def pulse_age_hours(pulse: dict, now: datetime) -> float | None:
    try:
        checked = parse_iso_timestamp(str(pulse.get("checked_at")))
    except ValueError:
        return None
    return (now - checked).total_seconds() / 3600


def cmd_apply(args) -> int:
    try:
        pulse = json.loads(Path(args.pulse).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"::warning title=fidelity hold::no pulse read ({type(e).__name__}); nothing held or released")
        return 0
    age = pulse_age_hours(pulse, datetime.now(timezone.utc))
    if age is None or age > STALE_PULSE_HOURS:
        print(f"::warning title=fidelity hold::the pulse is {age if age is None else round(age)} h old; "
              "its holds still apply until a newer pulse")
    holds = pulse_holds(pulse)
    fixture_path = REPO / vc.FIXTURE_REL
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    released = release_fidelity_holds(fixture, holds)
    for sec in released:
        print(f"fidelity hold: released {sec} (the pulse no longer holds it)")
    from nfl_week import current_nfl_week, today_ny  # noqa: PLC0415
    week = args.week or current_nfl_week(today_ny())
    held, report = apply_fidelity_holds(fixture, holds, week)
    if released or report:
        fixture_path.write_text(json.dumps(held, indent=2) + "\n", encoding="utf-8")
    if report:
        try:
            status = json.loads(vc.STATUS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            status = {}
        vc.STATUS.parent.mkdir(parents=True, exist_ok=True)
        vc.STATUS.write_text(json.dumps(update_chain_status(status, report, week), indent=2) + "\n", encoding="utf-8")
    for root, r in report.items():
        print(f"::warning title=Fidelity hold ({root})::{r['reason']}: {', '.join(r['sections'])} held, "
              f"values stripped (no computation on old data); {(r['summary'] or '')[:200]}")
    if not report:
        print("fidelity hold: the pulse holds no source")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply")
    a.add_argument("--pulse", default=str(PULSE))
    a.add_argument("--week", type=int, default=None)
    a.set_defaults(func=cmd_apply)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
