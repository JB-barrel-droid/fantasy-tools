"""Pure-Python transition-detection logic for monitoring-alert-email (JEG-435).

This module mirrors the TypeScript logic in
supabase/functions/monitoring-alert-email/index.ts so the transition
algorithm can be unit-tested without running a Deno process.  Keep both
in sync: the canonical spec is this file (tested) and the edge function
is the production implementation.

Terminology
-----------
heartbeats  : list of dicts with at minimum 'check_id' and 'state'
alert_states: dict mapping check_id -> last_alert_status string
              (absent key = never alerted = treat as 'unknown')

A 'transition' is:
  - newly bad:  state is in BAD_STATES  AND  last status was NOT in BAD_STATES
  - recovered:  state is in GOOD_STATES AND  last status WAS in BAD_STATES

No email is sent on a repeated bad state (deduplication).
"""

from __future__ import annotations

# States that constitute a bad outcome and warrant an alert email.
BAD_STATES: frozenset[str] = frozenset({"missed", "error"})

# States that constitute recovery from a previously alerted bad state.
GOOD_STATES: frozenset[str] = frozenset({"healthy", "degraded"})

SELF_CHECK_ID = "monitoring_alert_email"


def detect_transitions(
    heartbeats: list[dict],
    alert_states: dict[str, str],
    *,
    skip_self: bool = True,
) -> tuple[list[str], list[str]]:
    """Return (newly_bad_check_ids, recovered_check_ids).

    Parameters
    ----------
    heartbeats:
        List of dicts with 'check_id' and 'state'.
    alert_states:
        Map of check_id -> last_alert_status (the state that was current
        when we last sent an alert for that check, or last upserted).
        Missing keys are treated as 'unknown' (not previously bad).
    skip_self:
        If True (default), exclude SELF_CHECK_ID to avoid feedback loops.
    """
    newly_bad: list[str] = []
    recovered: list[str] = []

    for hb in heartbeats:
        check_id: str = hb["check_id"]
        current: str = hb["state"]

        if skip_self and check_id == SELF_CHECK_ID:
            continue

        last = alert_states.get(check_id, "unknown")

        now_bad = current in BAD_STATES
        was_good = last not in BAD_STATES  # unknown, healthy, degraded, disabled
        now_good = current in GOOD_STATES
        was_bad = last in BAD_STATES

        if now_bad and was_good:
            newly_bad.append(check_id)
        if now_good and was_bad:
            recovered.append(check_id)

    return newly_bad, recovered
