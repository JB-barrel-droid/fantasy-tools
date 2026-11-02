"""A full-CI label authorizes exactly one draft head, with no promotion bypass."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from pipelines.ci_pr_gate import decide, run
from tests.test_draft_ci_workflows import event, live

HEAD = 'a' * 40


def granted(sha=HEAD, grant=HEAD, **changes):
    return {**live(sha=sha), 'labels': [{'name': f'full-ci:{grant}'}], **changes}


class DraftFullCiTest(unittest.TestCase):
    def test_exact_head_grant_runs_existing_draft_pr_events(self):
        for action in ('opened', 'synchronize', 'reopened', 'converted_to_draft'):
            with self.subTest(action=action):
                self.assertTrue(decide('pull_request', event(action), granted())[0])

    def test_unbound_or_other_head_labels_do_not_authorize_full_ci(self):
        for labels in (None, [], [{'name': 'ready-for-full-ci'}],
                       [{'name': 'full-ci:' + 'b' * 40}], ['full-ci:' + HEAD],
                       [{'name': 'full-ci:' + HEAD + '-extra'}], {}, 'full-ci:' + HEAD):
            with self.subTest(labels=labels):
                self.assertFalse(decide('pull_request', event(), granted(labels=labels))[0])

    def test_new_head_needs_new_grant_even_when_old_label_remains(self):
        self.assertFalse(decide('pull_request', event(sha='b' * 40), granted(sha='b' * 40))[0])
        self.assertTrue(decide('pull_request', event(sha='b' * 40),
                               granted(sha='b' * 40, grant='b' * 40))[0])

    def test_grant_never_overrides_stale_events_closed_prs_or_draft_toggles(self):
        for current in (granted(sha='b' * 40, grant='b' * 40),
                        granted(state='closed'), granted(draft=False)):
            with self.subTest(current=current):
                self.assertFalse(decide('pull_request', event(), current)[0])
        self.assertFalse(decide('pull_request', event(draft=False), granted())[0])

    def test_missing_live_evidence_cannot_be_authorized_by_event_label(self):
        snapshot = event()
        snapshot['pull_request']['labels'] = [{'name': 'full-ci:' + HEAD}]
        with self.assertRaises(ValueError):
            decide('pull_request', snapshot, None)
        self.assertFalse(decide('pull_request', snapshot, live())[0])

    def test_each_gate_and_final_verification_rechecks_live_grant(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'event.json').write_text(json.dumps(event()))
            env = dict(GITHUB_EVENT_NAME='pull_request', GITHUB_REPOSITORY='owner/repo',
                       GITHUB_EVENT_PATH=str(root / 'event.json'),
                       GITHUB_OUTPUT=str(root / 'output'),
                       GITHUB_STEP_SUMMARY=str(root / 'summary'))
            fetch = Mock(return_value=granted())
            self.assertEqual(0, run('gate', env, fetch))
            self.assertIn('run_expensive=true', (root / 'output').read_text())
            self.assertEqual(0, run('verify', env, fetch))
            self.assertEqual(2, fetch.call_count)
            for current in (live(), granted(sha='b' * 40, grant='b' * 40), granted(state='closed')):
                with self.subTest(current=current), self.assertRaises(ValueError):
                    run('verify', env, Mock(return_value=current))
