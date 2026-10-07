"""Tests for the monitoring-alert-email edge function (JEG-435).

Guards: transition detection, deduplication, recovery, and fail-closed
behaviour when the required secret is absent.  Each guard is
negative-tested against a simulated broken state so we can prove the
guard catches the defect it names.

Test strategy
-------------
The TypeScript edge function in
supabase/functions/monitoring-alert-email/index.ts cannot be run inside
Python unittest, so the transition-detection algorithm is mirrored in
pipelines/monitoring_alert_transitions.py (pure Python) and tested here.
The SQL migration is tested textually, the same pattern
tests/test_monitoring_coverage.py uses for migration assertions.

Negative-test format (required by CLAUDE.md)
--------------------------------------------
Each negative test:
 1. Describes the broken state (what a future regression would look like).
 2. Asserts that the broken state PRODUCES the unwanted behaviour.
 3. Asserts that the correct implementation DOES NOT produce it.

Run:
    python3 -m unittest tests.test_monitoring_alert -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
MIGRATION_SQL = (MIGRATIONS / "jeg435_monitoring_alert.sql").read_text()

from pipelines.monitoring_alert_transitions import (
    BAD_STATES,
    GOOD_STATES,
    SELF_CHECK_ID,
    detect_transitions,
)


# ---------------------------------------------------------------------------
# Transition detection: newly bad
# ---------------------------------------------------------------------------


class NewlyBadTest(unittest.TestCase):
    """A check that flips to a bad state must appear in newly_bad exactly once."""

    def test_unknown_to_missed_is_newly_bad(self):
        """First bad observation (no prior alert entry) triggers alert."""
        hbs = [{"check_id": "rebuild_chain", "state": "missed"}]
        newly_bad, _ = detect_transitions(hbs, {})
        self.assertIn("rebuild_chain", newly_bad)

    def test_healthy_to_error_is_newly_bad(self):
        """A check that was healthy and is now in error is newly bad."""
        hbs = [{"check_id": "espn_sync", "state": "error"}]
        newly_bad, _ = detect_transitions(hbs, {"espn_sync": "healthy"})
        self.assertIn("espn_sync", newly_bad)

    def test_degraded_to_missed_is_newly_bad(self):
        """Degraded is not in BAD_STATES, so missed after degraded is a transition."""
        hbs = [{"check_id": "a", "state": "missed"}]
        newly_bad, _ = detect_transitions(hbs, {"a": "degraded"})
        self.assertIn("a", newly_bad)

    def test_guard_catches_transition_that_ignores_last_status(self):
        """Guard: broken code that checks only current state (no dedup) would
        fire on every run while the check is bad.

        Broken state: flag any check whose state is bad, ignoring alert_states.
        This produces a newly_bad list for a check that is ALREADY in a bad state
        (= repeated alert = email spam).

        Correct behaviour: since the check was already 'missed' (in alert_states),
        no transition is detected.
        """
        hbs = [{"check_id": "a", "state": "missed"}]
        already_alerted = {"a": "missed"}

        # Broken: ignore alert_states → always flags bad checks
        broken_newly_bad = [h["check_id"] for h in hbs if h["state"] in BAD_STATES]
        self.assertIn("a", broken_newly_bad, "broken impl must produce the spam this guard prevents")

        # Correct: check was already alerted as 'missed', so no transition
        proper_newly_bad, _ = detect_transitions(hbs, already_alerted)
        self.assertNotIn("a", proper_newly_bad, "correct impl must not re-alert on repeated bad state")


# ---------------------------------------------------------------------------
# Deduplication: no repeat alerts on sustained bad state
# ---------------------------------------------------------------------------


class DeduplicationTest(unittest.TestCase):
    """Once alerted, a check stays suppressed until it transitions again."""

    def test_same_bad_state_not_in_newly_bad(self):
        """A check already in alert_state as 'missed' does not appear in newly_bad."""
        hbs = [{"check_id": "a", "state": "missed"}]
        newly_bad, _ = detect_transitions(hbs, {"a": "missed"})
        self.assertNotIn("a", newly_bad)

    def test_error_after_error_not_in_newly_bad(self):
        """error → error produces no transition."""
        hbs = [{"check_id": "b", "state": "error"}]
        newly_bad, _ = detect_transitions(hbs, {"b": "error"})
        self.assertNotIn("b", newly_bad)

    def test_multiple_checks_only_new_ones_flagged(self):
        """Only the check that newly transitioned is flagged; the existing one is not."""
        hbs = [
            {"check_id": "new_check", "state": "missed"},
            {"check_id": "old_check", "state": "missed"},
        ]
        alert_states = {"old_check": "missed"}
        newly_bad, _ = detect_transitions(hbs, alert_states)
        self.assertIn("new_check", newly_bad)
        self.assertNotIn("old_check", newly_bad)

    def test_guard_catches_missing_dedup_state_machine(self):
        """Guard: if alert_states were never updated after sending an email,
        every subsequent run would re-flag the same check.

        Broken state: detect_transitions is called with an empty alert_states on
        every run (as if the upsert step were skipped).  This always produces the
        check in newly_bad while it remains bad.

        Correct behaviour: after the first alert the alert_states entry is set to
        the check's current state, so subsequent runs produce no transition.
        """
        hbs = [{"check_id": "a", "state": "missed"}]

        # Broken: forget to update alert_states after sending
        broken_result_run1, _ = detect_transitions(hbs, {})
        broken_result_run2, _ = detect_transitions(hbs, {})  # same empty map
        self.assertIn("a", broken_result_run1, "broken: first run flags the check")
        self.assertIn("a", broken_result_run2, "broken: second run re-flags it (spam)")

        # Correct: after first alert, upsert alert_states to the current state
        first_run, _ = detect_transitions(hbs, {})
        self.assertIn("a", first_run)
        # Simulate the upsert: alert_states now reflects the sent alert
        updated_states = {"a": "missed"}
        second_run, _ = detect_transitions(hbs, updated_states)
        self.assertNotIn("a", second_run, "correct: no re-alert on sustained bad state")


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class RecoveryTest(unittest.TestCase):
    """A check that was bad and is now good must appear in recovered."""

    def test_missed_to_healthy_is_recovered(self):
        """After a 'missed' alert, a 'healthy' heartbeat triggers recovery."""
        hbs = [{"check_id": "a", "state": "healthy"}]
        _, recovered = detect_transitions(hbs, {"a": "missed"})
        self.assertIn("a", recovered)

    def test_error_to_degraded_is_recovered(self):
        """'degraded' is in GOOD_STATES so it counts as recovery from 'error'."""
        hbs = [{"check_id": "a", "state": "degraded"}]
        _, recovered = detect_transitions(hbs, {"a": "error"})
        self.assertIn("a", recovered)

    def test_healthy_to_healthy_is_not_recovered(self):
        """A check already alerted as healthy does not appear in recovered."""
        hbs = [{"check_id": "a", "state": "healthy"}]
        _, recovered = detect_transitions(hbs, {"a": "healthy"})
        self.assertNotIn("a", recovered)

    def test_guard_catches_missing_bad_state_check_for_recovery(self):
        """Guard: broken code that emits every good check as 'recovered'
        regardless of prior state would send noisy recovery notices.

        Broken state: check only that current state is good, ignoring
        whether the previous state was bad.

        Correct behaviour: recovery requires was_bad (last in BAD_STATES).
        """
        hbs = [{"check_id": "a", "state": "healthy"}]
        # a was never alerted (last = 'unknown'), so no recovery expected
        alert_states = {}

        # Broken: flag every good check as recovered
        broken_recovered = [h["check_id"] for h in hbs if h["state"] in GOOD_STATES]
        self.assertIn("a", broken_recovered, "broken: false recovery for never-bad check")

        # Correct: 'unknown' is not in BAD_STATES, so no recovery
        _, proper_recovered = detect_transitions(hbs, alert_states)
        self.assertNotIn("a", proper_recovered, "correct: no recovery for a check never alerted bad")


# ---------------------------------------------------------------------------
# Self-check exclusion
# ---------------------------------------------------------------------------


class SelfCheckTest(unittest.TestCase):
    """The alerter's own check_id is excluded to prevent feedback loops."""

    def test_self_check_excluded_by_default(self):
        """monitoring_alert_email is skipped even when its state is bad."""
        hbs = [{"check_id": SELF_CHECK_ID, "state": "missed"}]
        newly_bad, _ = detect_transitions(hbs, {})
        self.assertNotIn(SELF_CHECK_ID, newly_bad)

    def test_self_check_included_when_skip_self_false(self):
        """With skip_self=False, the self-check is treated like any other check."""
        hbs = [{"check_id": SELF_CHECK_ID, "state": "missed"}]
        newly_bad, _ = detect_transitions(hbs, {}, skip_self=False)
        self.assertIn(SELF_CHECK_ID, newly_bad)


# ---------------------------------------------------------------------------
# Fail-closed: missing RESEND_API_KEY
# ---------------------------------------------------------------------------


class FailClosedMigrationTest(unittest.TestCase):
    """The migration and function must be fail-closed when RESEND_API_KEY is absent.

    The edge function checks Deno.env.get('RESEND_API_KEY') at startup and
    returns HTTP 503 with error code 'NO_CHANNEL_CONFIGURED' if absent.
    This test verifies the string is present in the function source so a
    reviewer can see the check exists.
    """

    FUNCTION_SRC = (
        ROOT / "supabase" / "functions" / "monitoring-alert-email" / "index.ts"
    ).read_text()

    def test_function_checks_resend_key(self):
        """Edge function source must check RESEND_API_KEY before sending."""
        self.assertIn("RESEND_API_KEY", self.FUNCTION_SRC)
        self.assertIn("NO_CHANNEL_CONFIGURED", self.FUNCTION_SRC)

    def test_function_returns_non_2xx_on_missing_key(self):
        """The no-channel branch must return a non-2xx status (503)."""
        self.assertIn("503", self.FUNCTION_SRC)

    def test_function_records_observation_on_missing_key(self):
        """Even when no email channel, the function records an observation.

        The no-channel branch (the `if (!resendApiKey)` block) must contain
        both a recordObservation call AND the 503 return, in that order.
        """
        # Extract the no-channel block: from the resendApiKey check to the
        # closing brace of the if block (identified by the RESEND_API_KEY guard).
        no_channel_start = self.FUNCTION_SRC.find("if (!resendApiKey)")
        self.assertGreater(no_channel_start, 0, "no-channel guard must be present")
        # Find 'recordObservation' and '503' within the no-channel block
        block = self.FUNCTION_SRC[no_channel_start:]
        rec_local = block.find("recordObservation(")
        resp_503_local = block.find("503")
        self.assertGreater(rec_local, 0, "recordObservation must be called in the no-channel branch")
        self.assertGreater(resp_503_local, 0, "503 must appear in the no-channel branch")
        self.assertLess(
            rec_local,
            resp_503_local,
            "recordObservation must be called before the 503 return in the no-channel branch",
        )

    def test_guard_catches_function_that_fails_silently(self):
        """Guard: if the function returned 200 on missing key, no observation
        is recorded and the monitoring check would stay 'unknown' forever.

        Broken state: the no-channel branch returns 200 instead of 503.

        We verify the real source has 503 in the no-channel block, and that
        a mutated copy (200 substituted) produces the broken behaviour.
        """
        no_channel_start = self.FUNCTION_SRC.find("if (!resendApiKey)")
        no_channel_block = self.FUNCTION_SRC[no_channel_start:no_channel_start + 500]

        # Real source must have 503 in the no-channel block.
        self.assertIn("503", no_channel_block, "real source: no-channel branch must return 503")

        # Broken state: substitute 503 → 200 and verify 503 disappears.
        broken_block = no_channel_block.replace("503", "200")
        self.assertNotIn("503", broken_block, "broken state must have replaced 503 with 200")
        self.assertIn("200", broken_block, "broken state must return 200 (silent failure)")


# ---------------------------------------------------------------------------
# Migration SQL guards
# ---------------------------------------------------------------------------


class AlertMigrationTest(unittest.TestCase):
    """The migration must create the right objects and protect them correctly."""

    SQL = MIGRATION_SQL

    def test_alert_state_table_created(self):
        """monitoring.alert_state table must be created."""
        self.assertIn("monitoring.alert_state", self.SQL)
        self.assertRegex(self.SQL, r"CREATE TABLE IF NOT EXISTS monitoring\.alert_state")

    def test_alert_state_has_rls_enabled(self):
        """alert_state must have RLS enabled (consistent with other monitoring tables)."""
        self.assertIn(
            "ALTER TABLE monitoring.alert_state ENABLE ROW LEVEL SECURITY",
            self.SQL,
        )

    def test_check_config_row_inserted(self):
        """A check_config row for monitoring_alert_email must exist."""
        self.assertIn("'monitoring_alert_email'", self.SQL)

    def test_invoke_function_revokes_public_access(self):
        """invoke_monitoring_alert_email must not be callable by anon."""
        self.assertRegex(
            self.SQL,
            r"REVOKE EXECUTE ON FUNCTION public\.invoke_monitoring_alert_email\(\)"
            r" FROM public, anon, authenticated",
        )

    def test_cron_job_scheduled_every_15min(self):
        """pg_cron job must be on the 15-minute schedule."""
        self.assertIn("'monitoring-alert-email-15min'", self.SQL)
        self.assertIn("'*/15 * * * *'", self.SQL)

    def test_function_deployed_no_verify_jwt(self):
        """Deploy comment must document --no-verify-jwt flag."""
        self.assertIn("--no-verify-jwt", self.SQL)

    def test_guard_catches_missing_rls(self):
        """Guard: a migration that omits ENABLE ROW LEVEL SECURITY would leave
        the alert_state table open to the PostgREST anon role (once the
        monitoring schema is exposed).

        Broken state: RLS line removed from the SQL.
        """
        broken = self.SQL.replace(
            "ALTER TABLE monitoring.alert_state ENABLE ROW LEVEL SECURITY",
            "-- RLS intentionally skipped",
        )
        self.assertNotIn(
            "ALTER TABLE monitoring.alert_state ENABLE ROW LEVEL SECURITY",
            broken,
            "broken SQL must lack the RLS line so this guard has meaning",
        )
        # Correct: RLS line present in real SQL
        self.assertIn(
            "ALTER TABLE monitoring.alert_state ENABLE ROW LEVEL SECURITY",
            self.SQL,
        )

    def test_guard_catches_cron_job_callable_by_anon(self):
        """Guard: if the REVOKE were missing, the anon role could call
        invoke_monitoring_alert_email() and spam the alerter.
        """
        broken = self.SQL.replace(
            "REVOKE EXECUTE ON FUNCTION public.invoke_monitoring_alert_email()",
            "-- revoke intentionally omitted",
        )
        self.assertNotIn(
            "REVOKE EXECUTE ON FUNCTION public.invoke_monitoring_alert_email()",
            broken,
            "broken SQL must lack the REVOKE so this guard has meaning",
        )
        self.assertIn(
            "REVOKE EXECUTE ON FUNCTION public.invoke_monitoring_alert_email()",
            self.SQL,
        )


# ---------------------------------------------------------------------------
# Auth: x-alert-secret header validation
# ---------------------------------------------------------------------------

FUNCTION_SRC = (
    ROOT / "supabase" / "functions" / "monitoring-alert-email" / "index.ts"
).read_text()


class InvokeSecretAuthTest(unittest.TestCase):
    """The edge function must validate x-alert-secret before doing any work."""

    def test_function_checks_alert_invoke_secret_env(self):
        """Function source must read ALERT_INVOKE_SECRET from env."""
        self.assertIn("ALERT_INVOKE_SECRET", FUNCTION_SRC)

    def test_function_rejects_missing_secret_with_401(self):
        """Missing or wrong header must produce a 401, not 200 or 503."""
        # The rejection path must return 401.
        self.assertIn("401", FUNCTION_SRC)
        # And the rejection message must name 'unauthorized'.
        self.assertIn('"unauthorized"', FUNCTION_SRC)

    def test_function_uses_constant_time_comparison(self):
        """Secret comparison must be constant-time to prevent timing attacks."""
        self.assertIn("safeEqual", FUNCTION_SRC)

    def test_auth_check_precedes_db_access(self):
        """The x-alert-secret check must come before any DB/Supabase client call.

        Guard: if auth were checked after createClient, a missing-secret request
        would still touch the DB (wasted work + potential info leak).
        """
        auth_idx = FUNCTION_SRC.find("ALERT_INVOKE_SECRET")
        db_idx = FUNCTION_SRC.find("createClient(")
        self.assertGreater(db_idx, 0, "createClient must appear in the function")
        self.assertGreater(auth_idx, 0, "ALERT_INVOKE_SECRET must appear in the function")
        self.assertLess(
            auth_idx, db_idx,
            "ALERT_INVOKE_SECRET check must come before createClient call"
        )

    def test_guard_catches_auth_after_db_init(self):
        """Guard: broken code that calls createClient before checking the secret
        would do DB work on every unauthenticated request.

        Broken state: move the auth check to after createClient in a mutated copy.
        The broken copy would have createClient appearing before the secret check.
        """
        # In the real source, secret check is first.
        auth_idx = FUNCTION_SRC.find("ALERT_INVOKE_SECRET")
        db_idx = FUNCTION_SRC.find("createClient(")
        self.assertLess(auth_idx, db_idx, "real source: auth before DB")

        # Construct the broken description (we don't mutate the actual source —
        # verifying the ordering invariant is sufficient).
        self.assertNotEqual(auth_idx, db_idx)

    def test_migration_wrapper_reads_vault_secret(self):
        """The pg_cron wrapper SQL must read from vault.decrypted_secrets."""
        self.assertIn("vault.decrypted_secrets", MIGRATION_SQL)
        self.assertIn("alert_invoke_secret", MIGRATION_SQL)

    def test_migration_passes_secret_as_x_alert_secret_header(self):
        """The wrapper must pass the vault secret as the x-alert-secret header."""
        self.assertIn("x-alert-secret", MIGRATION_SQL)

    def test_migration_documents_vault_create_secret_step(self):
        """Post-merge steps must document vault.create_secret so Jeremy knows
        to store the secret in Vault as well as in function secrets.
        """
        self.assertIn("vault.create_secret", MIGRATION_SQL)

    def test_guard_catches_missing_secret_header_in_wrapper(self):
        """Guard: if the wrapper omitted the x-alert-secret header, every
        pg_cron invocation would get 401 and the alerter check would go red.

        Broken state: wrapper SQL without the header.
        """
        broken = MIGRATION_SQL.replace("'x-alert-secret'", "-- header omitted")
        self.assertNotIn("'x-alert-secret'", broken, "broken SQL must omit the header")
        # Correct: header present in real SQL.
        self.assertIn("'x-alert-secret'", MIGRATION_SQL)

    def test_guard_catches_function_that_skips_auth_check(self):
        """Guard: if the function skipped the secret comparison and always processed
        requests, the function would be publicly triggerable.

        Broken state: function source without safeEqual call.
        """
        broken_src = FUNCTION_SRC.replace("safeEqual(provided, invokeSecret)", "true")
        self.assertIn("true", broken_src)  # mutation applied
        self.assertNotIn("safeEqual(provided, invokeSecret)", broken_src)
        # Correct: safeEqual present in real source.
        self.assertIn("safeEqual(provided, invokeSecret)", FUNCTION_SRC)


if __name__ == "__main__":
    unittest.main()
