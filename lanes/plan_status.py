#!/usr/bin/env python3
"""Plan status command (JEG-96).

Prints the current operating-model state derived from lanes/plan.json and
lanes/linear_fixture.json:

  - which phase is active
  - what's blocking it (which tickets are not yet Done/Verified)
  - what's next (the unblocked phase with the most preparation)

Run: `python3 lanes/plan_status.py` or `make plan-status` (added by JEG-96).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

PLAN_DIR = Path(__file__).parent
PLAN_JSON = PLAN_DIR / "plan.json"
FIXTURE_JSON = PLAN_DIR / "linear_fixture.json"

# Ticket states that count as "complete enough" to allow a phase to exit.
# 'Done' is the Linear terminal state; 'Verified' is reserved for tickets
# that go through a second-stage review.
COMPLETE_STATUSES = {"done", "verified", "cancelled"}


def _load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _ticket_status(fixture: dict, ticket_id: str) -> str:
    """Look up a ticket's status. Unknown tickets are 'missing' (NOT todo)."""
    t = fixture.get("tickets", {}).get(ticket_id)
    if not t:
        return "missing"
    return t.get("status", "missing").lower()


def _phase_progress(phase: dict, fixture: dict) -> Tuple[int, int, List[str]]:
    """Return (done_count, total_count, blocking_ticket_ids) for a phase."""
    total = len(phase["ticket_ids"])
    blocking: List[str] = []
    done = 0
    for tid in phase["ticket_ids"]:
        status = _ticket_status(fixture, tid)
        if status in COMPLETE_STATUSES:
            done += 1
        else:
            blocking.append(f"{tid}={status}")
    return done, total, blocking


def _is_unblocked(phase: dict, fixture: dict) -> bool:
    for dep in phase.get("blocked_by", []):
        dep_done, dep_total, _ = _phase_progress(
            next(p for p in _load_json(PLAN_JSON)["phases"] if p["id"] == dep),
            fixture,
        )
        if dep_done < dep_total:
            return False
    return True


def compute_state() -> dict:
    plan = _load_json(PLAN_JSON)
    fixture = _load_json(FIXTURE_JSON)

    phases_out = []
    for phase in plan["phases"]:
        done, total, blocking = _phase_progress(phase, fixture)
        unblocked = _is_unblocked(phase, fixture)
        # Active = unblocked AND not yet at 100% complete.
        if unblocked and done < total:
            state = "active"
        elif unblocked and done == total:
            state = "done"
        else:
            state = "blocked"
        phases_out.append({
            "id": phase["id"],
            "name": phase["name"],
            "ticket_ids": phase["ticket_ids"],
            "done": done,
            "total": total,
            "blocking_tickets": blocking,
            "state": state,
            "blocked_by": phase.get("blocked_by", []),
            "parallel_with": phase.get("parallel_with", []),
        })

    active = [p for p in phases_out if p["state"] == "active"]
    blocked = [p for p in phases_out if p["state"] == "blocked"]
    done = [p for p in phases_out if p["state"] == "done"]

    return {
        "source_issue": plan.get("source_issue", "JEG-96"),
        "fixture_last_refreshed": fixture.get("_last_refreshed", "unknown"),
        "phases": phases_out,
        "active": active,
        "blocked": blocked,
        "done": done,
    }


def render(state: dict) -> str:
    lines: List[str] = []
    lines.append(f"# Operating-model status ({state['source_issue']})")
    lines.append(
        f"_Linear fixture last refreshed {state['fixture_last_refreshed']}._"
    )
    lines.append("")

    if state["done"]:
        lines.append("## Completed phases")
        for p in state["done"]:
            lines.append(f"- **{p['name']}** ({p['id']}): {p['done']}/{p['total']} tickets")
        lines.append("")

    if state["active"]:
        lines.append("## Active phase(s)")
        for p in state["active"]:
            lines.append(f"### {p['name']} ({p['id']})")
            lines.append(f"Tickets: {', '.join(p['ticket_ids'])}")
            lines.append(
                f"Progress: {p['done']}/{p['total']}"
                + (f" — blocking: {', '.join(p['blocking_tickets'])}" if p['blocking_tickets'] else "")
            )
            if p["parallel_with"]:
                lines.append(f"Parallel with: {', '.join(p['parallel_with'])}")
            lines.append("")

    if state["blocked"]:
        lines.append("## Blocked phase(s) — waiting on prerequisites")
        for p in state["blocked"]:
            lines.append(f"### {p['name']} ({p['id']})")
            lines.append(
                f"Waiting on: {', '.join(p['blocked_by'])}"
                + (f" — current blockers in this phase: {', '.join(p['blocking_tickets'])}" if p['blocking_tickets'] else "")
            )
            lines.append("")

    if not state["active"]:
        if state["blocked"]:
            lines.append("**No active phase right now.** The remaining phases wait on prerequisites above.")
        elif state["done"] and not state["blocked"]:
            lines.append("**Plan complete.** All phases Done.")

    return "\n".join(lines)


def main() -> int:
    state = compute_state()
    print(render(state))
    # Also print a JSON summary to stdout for scripts.
    # (Send it to stderr so piping render() to a file still works.)
    print(json.dumps(state, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())