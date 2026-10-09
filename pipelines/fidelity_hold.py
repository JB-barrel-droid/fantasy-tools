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

Last good section. A held published chart (USA Today, FantasyCalc,
FantasyPros, CBS) is served from the section of the last chart file the pulse
did not hold it on: the pulse carries that file's `built_at` forward
(`last_good`), and the fixture commit with that built_at supplies the
sections. If no such commit is found the current sections stay, still held.
A held projection (ESPN, CBS rest of season, Razzball) keeps its current
section, held: its values are baked into players.json together with the ESPN
anchor (tests/test_static_export.py checks the triple), so restoring the
section alone would fail validate and stop every source from publishing.
Never the whole site: one source at a time.

A hold lasts while the pulse reports it: a section whose fidelity hold the
latest pulse no longer lists is released (its validationHold removed).
JEG-479 holds (no "fidelity: " reason) are never touched here, and
value_check.release_holds leaves fidelity holds alone.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

import value_check as vc  # noqa: E402

PULSE = REPO / "dist" / "modules" / "fidelity-pulse.json"
HOLD_PREFIX = "fidelity: "
RESTORABLE = ("usatoday", "fantasycalc", "fantasypros", "cbs")
MAX_COMMITS = 400
STALE_PULSE_HOURS = 24


def is_fidelity_hold(hold) -> bool:
    return isinstance(hold, dict) and str(hold.get("reason") or "").startswith(HOLD_PREFIX)


def pulse_holds(pulse: dict | None) -> dict:
    """{root: hold} for the sources the pulse holds (roots the chain knows only)."""
    return {root: h for root, h in ((pulse or {}).get("holds") or {}).items()
            if root in vc.SOURCE_DERIVED and isinstance(h, dict) and h.get("stage")}


def fixture_with_built_at(built_at: str | None, repo: Path = REPO, rel: str = vc.FIXTURE_REL,
                          max_commits: int = MAX_COMMITS) -> dict | None:
    """The committed fixture whose built_at is `built_at` (newest first, at most max_commits back)."""
    if not built_at:
        return None
    revs = subprocess.run(["git", "log", "--format=%H", "-n", str(max_commits), "--", rel], cwd=str(repo),
                          capture_output=True, text=True)
    needle = f'"built_at": "{built_at}"'
    for sha in revs.stdout.split():
        proc = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=str(repo), capture_output=True, text=True,
                              encoding="utf-8")
        if proc.returncode != 0:
            continue
        head = proc.stdout[:20000]
        if needle in head or f'"built_at":"{built_at}"' in head:
            try:
                return json.loads(proc.stdout)
            except ValueError:
                return None
    return None


def apply_fidelity_holds(fixture: dict, holds: dict, last_good_of, week: int | None,
                         today: date | None = None) -> tuple[dict, dict]:
    """Return (fixture with holds applied, {root: {sections, restored_from}}).

    last_good_of(root) -> the last good fixture for a restorable root, or None."""
    out = copy.deepcopy(fixture)
    sources = out.setdefault("sources", {})
    today = today or datetime.now(timezone.utc).date()
    report = {}
    for root, hold in holds.items():
        good = last_good_of(root) if root in RESTORABLE else None
        prior = (good or {}).get("sources") or {}
        sections = vc.SOURCE_DERIVED[root]["sections"]
        restored = []
        for sec in sections:
            kept_week = None
            if sec in prior:
                sources[sec] = copy.deepcopy(prior[sec])
                kept_week = vc.ref.section_week(prior[sec], today)[0]
                restored.append(sec)
            target = sources.get(sec)
            if isinstance(target, dict):
                target.pop("validationHold", None)
                target["validationHold"] = {
                    "reason": hold.get("reason") or HOLD_PREFIX + hold["stage"], "week": week, "root": root,
                    "kept_week": kept_week, "stage": hold["stage"], "identity": hold.get("identity"),
                    "since": hold.get("since"), "restored_from": (good or {}).get("built_at") if restored else None}
        report[root] = {"sections": sections, "restored": restored,
                        "restored_from": (good or {}).get("built_at") if restored else None,
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
        detail[root] = {"reason": r["reason"], "held_series": vc.derived_series(root), "sections": r["sections"],
                        "restored_from": r["restored_from"], "detail": r["summary"],
                        "hold_severity": "amber", "week": week}
    status["held"] = sorted(held)
    status["held_detail"] = detail
    status["fidelity_holds"] = {root: r["reason"] for root, r in report.items()}
    if held and status.get("status") == "green":
        status["status"] = "published_with_holds"
    return status


def pulse_age_hours(pulse: dict, now: datetime) -> float | None:
    try:
        checked = datetime.fromisoformat(str(pulse.get("checked_at")).replace("Z", "+00:00"))
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
    last_good = pulse.get("last_good") or {}
    from nfl_week import current_nfl_week  # noqa: PLC0415
    week = args.week or current_nfl_week(datetime.now(timezone.utc).date())
    held, report = apply_fidelity_holds(fixture, holds, lambda root: fixture_with_built_at(last_good.get(root)), week)
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
        where = (f"restored from the chart built {r['restored_from']}" if r["restored"]
                 else "current section kept (labelled)")
        print(f"::warning title=Fidelity hold ({root})::{r['reason']}: {', '.join(r['sections'])} held, {where}; "
              f"{(r['summary'] or '')[:200]}")
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
