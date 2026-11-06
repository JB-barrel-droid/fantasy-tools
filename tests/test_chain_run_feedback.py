"""JEG-1522: terminal reports survive absent jobs and partial step timings."""
import unittest
from pathlib import Path
from pipelines.chain_run_feedback import report, markdown

ROOT = Path(__file__).resolve().parents[1]


class FeedbackTest(unittest.TestCase):
    def run_data(self, conclusion='success'):
        return dict(id=42, run_attempt=2, head_sha='exact-head', status='completed',
                    conclusion=conclusion, created_at='2026-11-05T00:00:00Z')

    def test_pending_cancellation_is_terminal_without_claiming_replacement(self):
        data = report(self.run_data('cancelled'), [])
        self.assertEqual(data['conclusion'], 'cancelled')
        self.assertEqual(data['jobs'], [])
        self.assertIn('unknown', data['replacement'])
        self.assertIn('completed / cancelled', markdown(data))
        self.assertIn('exact-head', markdown(data))

    def test_timeout_and_queue_are_separate_from_execution(self):
        jobs = [dict(name='rebuild', conclusion='timed_out',
                     started_at='2026-11-05T00:30:00Z', completed_at='2026-11-05T02:30:00Z',
                     steps=[dict(name='validate', conclusion='cancelled',
                                 started_at='2026-11-05T01:00:00Z')])]
        data = report(self.run_data('timed_out'), jobs)
        self.assertEqual(data['jobs'][0]['queue_seconds'], 1800)
        self.assertEqual(data['jobs'][0]['execution_seconds'], 7200)
        self.assertIsNone(data['jobs'][0]['steps'][0]['seconds'])
        self.assertIn('timed_out', markdown(data))

    def test_step_duration(self):
        data = report(self.run_data(), [dict(name='rebuild', steps=[dict(
            name='import', started_at='2026-11-05T00:00:00Z', completed_at='2026-11-05T00:02:00Z')])])
        self.assertEqual(data['jobs'][0]['steps'][0]['seconds'], 120)

    def test_workflow_bounds_and_separates_proofs(self):
        workflow = (ROOT / '.github/workflows/rebuild-chain.yml').read_text()
        self.assertIn('group: rebuild-chain-${{ github.ref }}', workflow)
        self.assertEqual(workflow.count('timeout-minutes: 120'), 2)
        self.assertIn('cancel-in-progress: false', workflow)
        self.assertIn('JOB_STATUS_FOR_RECORD: ${{ job.status }}', workflow)
        self.assertIn('STATUS="$JOB_STATUS_FOR_RECORD"', workflow)
        self.assertIn('pending runs may be replaced', workflow)
        for marker in ('initial_validate_start', 'initial_validate_end', 'isolation_start',
                       'isolation_end_retry_validate_start', 'retry_validate_end'):
            self.assertIn(marker, workflow)

    def test_observer_runs_outside_publication_slot_on_trusted_code(self):
        workflow = (ROOT / '.github/workflows/chain-run-feedback.yml').read_text()
        self.assertIn('types: [completed]', workflow)
        self.assertNotIn('concurrency:', workflow)
        self.assertIn('github.event.repository.default_branch', workflow)
        self.assertIn('/attempts/$RUN_ATTEMPT/jobs?per_page=100', workflow)
        self.assertNotIn('secrets.', workflow)
