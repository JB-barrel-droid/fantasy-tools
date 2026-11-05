"""Executable release preflight regressions; no GitHub mutations or merges."""
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile
from pipelines import release_batch as gate

A, B, C, D = (c * 40 for c in 'abcd')


def sample():
    return {'version': 1, 'batches': [{'id': 'train-1', 'state': 'active', 'owner': 'integrator',
        'integration_pr': 20, 'members': [{'pr': 10, 'head': B, 'risk': 'review-standard', 'owner': 'author-10'}]}]}


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.doc = sample()
        self.manifest = {'batch_id': 'train-1', 'main_sha': A, 'members': copy.deepcopy(self.doc['batches'][0]['members'])}
        self.ci = patch.object(gate, 'check_ci'); self.review = patch.object(gate, 'review')
        risk = patch.object(gate, 'risk_floor'); risk.start(); self.addCleanup(risk.stop)
        self.mock_ci = self.ci.start(); self.mock_review = self.review.start()
        self.addCleanup(self.ci.stop); self.addCleanup(self.review.stop)
        self.prs = {'pulls/10': {'state': 'open', 'merged': False, 'head': {'sha': B}, 'base': {'ref': 'main'}},
                    'pulls/20': {'state': 'open', 'draft': False, 'head': {'sha': C}, 'base': {'ref': 'main'}, 'mergeable': True}}

    def run_gate(self, **kwargs):
        gate.preflight(self.doc, self.manifest, kwargs.get('main', A), kwargs.get('head', C),
                       get=self.prs.__getitem__, run_git=kwargs.get('git', lambda *a: ''))

    def test_valid_batch_checks_members_and_combined_head(self):
        self.run_gate()
        self.assertEqual([c.args[:2] for c in self.mock_ci.call_args_list], [(10, B), (20, C)])
        self.assertEqual(self.mock_review.call_args_list[-1].args[2], {'integrator', 'author-10'})

    def test_stale_main_member_integration_and_missing_combination_block(self):
        for target, field, value in (('pulls/10', 'head', {'sha': D}), ('pulls/10', 'merged', True),
                                     ('pulls/20', 'head', {'sha': D}), ('pulls/20', 'draft', True),
                                     ('pulls/20', 'mergeable', None)):
            with self.subTest(target=target, field=field):
                old = copy.deepcopy(self.prs[target]); self.prs[target][field] = value
                with self.assertRaises(ValueError): self.run_gate()
                self.prs[target] = old
        with self.assertRaises(ValueError): self.run_gate(main=D)
        def no_ancestor(*args): raise ValueError('not combined')
        with self.assertRaises(ValueError): self.run_gate(git=no_ancestor)

    def test_missing_or_failed_gate_and_review_block(self):
        for mocked in (self.mock_ci, self.mock_review):
            mocked.side_effect = ValueError('missing evidence')
            with self.assertRaises(ValueError): self.run_gate()
            mocked.side_effect = None

    def test_duplicate_member_in_one_or_multiple_batches_blocks(self):
        member = self.doc['batches'][0]['members'][0]
        self.doc['batches'][0]['members'].append(copy.deepcopy(member))
        with self.assertRaisesRegex(ValueError, 'membership'): gate.registry(self.doc)
        self.doc = sample(); duplicate = copy.deepcopy(self.doc['batches'][0]); duplicate['id'] = 'train-2'; duplicate['integration_pr'] = 21
        self.doc['batches'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'membership'): gate.registry(self.doc)

    def test_member_cannot_be_integration_and_registry_must_be_well_formed(self):
        for mutation in (lambda d: d.update(version=2), lambda d: d['batches'][0].update(state='published'),
                         lambda d: d['batches'][0].update(integration_pr=10),
                         lambda d: d['batches'][0]['members'][0].update(head='main'),
                         lambda d: d['batches'][0]['members'][0].update(owner='')):
            d = sample(); mutation(d)
            with self.assertRaises(ValueError): gate.registry(d)

    def test_highrisk_and_mixedrisk_stay_isolated(self):
        for risk in ('review-light', 'review-high-risk'):
            d = sample(); m = copy.deepcopy(d['batches'][0]['members'][0]); m.update(pr=11, risk=risk)
            d['batches'][0]['members'].append(m)
            with self.assertRaises(ValueError): gate.registry(d)
        d['batches'][0]['members'][0]['risk'] = 'review-high-risk'
        with self.assertRaisesRegex(ValueError, 'isolated'): gate.registry(d)

    def test_active_batch_blocks_every_ordinary_merge_and_repeat_member(self):
        for pr in (10, 20, 99):
            with self.assertRaisesRegex(ValueError, 'active batch'): gate.ordinary(self.doc, pr)
        self.doc['batches'][0].update(state='accepted', acceptance={'published_sha': D, 'publication_run': 1, 'live_run': 2})
        with self.assertRaisesRegex(ValueError, 'integration record'): gate.ordinary(self.doc, 10)
        gate.ordinary(self.doc, 99)

    def test_next_batch_requires_acceptance_and_preserves_history(self):
        previous = copy.deepcopy(self.doc['batches'][0])
        previous.update(id='previous', integration_pr=19)
        previous['members'][0]['pr'] = 9
        self.doc['batches'].insert(0, previous)
        with self.assertRaisesRegex(ValueError, 'previous batch'): gate.registry(self.doc)
        previous.update(state='accepted')
        with self.assertRaises(KeyError): gate.registry(self.doc)
        previous['acceptance'] = {'published_sha': D, 'publication_run': 1, 'live_run': 2}
        with patch.object(gate, 'acceptance', side_effect=ValueError('missing live artifact')) as accept:
            with self.assertRaisesRegex(ValueError, 'live artifact'): self.run_gate()
            accept.assert_called_once()

    def test_registry_transitions_require_verified_receipts(self):
        gate.transition({'version': 1, 'batches': []}, sample())
        accepted = copy.deepcopy(self.doc)
        accepted['batches'][0].update(state='accepted', acceptance={'published_sha': D, 'publication_run': 1, 'live_run': 2})
        with patch.object(gate, 'acceptance', side_effect=ValueError('no publication')):
            with self.assertRaises(ValueError): gate.transition(self.doc, accepted)
        with patch.object(gate, 'acceptance') as accept:
            gate.transition(self.doc, accepted); accept.assert_called_once()
            changed = copy.deepcopy(accepted); changed['batches'][0]['members'][0]['head'] = D
            with self.assertRaisesRegex(ValueError, 'ownership changed'): gate.transition(self.doc, changed)
        with self.assertRaises(ValueError): gate.transition(self.doc, {'version': 1, 'batches': []})

    def test_stale_head_recovery_requires_green_reviewed_current_heads(self):
        corrected = copy.deepcopy(self.doc); corrected['batches'][0]['members'][0]['head'] = D
        self.prs['pulls/10']['head']['sha'] = D
        gate.transition(self.doc, corrected, self.prs.__getitem__)
        self.mock_ci.assert_called_with(10, D, self.prs.__getitem__)
        self.mock_review.assert_called_with(10, D, {'author-10'}, 'review-standard', self.prs.__getitem__)
        for evidence in (self.mock_ci, self.mock_review):
            evidence.side_effect = ValueError('failed gate')
            with self.assertRaises(ValueError): gate.transition(self.doc, corrected, self.prs.__getitem__)
            evidence.side_effect = None
        self.prs['pulls/10']['head']['sha'] = B
        with self.assertRaisesRegex(ValueError, 'stale recovery'): gate.transition(self.doc, corrected, self.prs.__getitem__)
        self.doc = corrected
        with self.assertRaisesRegex(ValueError, 'membership'): self.run_gate()

    def test_withdrawal_preserves_history_and_never_bypasses_a_merged_batch_receipt(self):
        withdrawn = copy.deepcopy(self.doc)
        withdrawn['batches'][0].update(state='withdrawn', recovery={'reason': 'member needs more work; branches and PRs retained'})
        self.prs['pulls/20']['merged'] = False
        gate.transition(self.doc, withdrawn, self.prs.__getitem__)
        gate.ordinary(withdrawn, 10)
        following = copy.deepcopy(withdrawn); next_batch = copy.deepcopy(sample()['batches'][0])
        next_batch.update(id='train-2', integration_pr=21); following['batches'].append(next_batch)
        gate.transition(withdrawn, following, self.prs.__getitem__)
        self.assertEqual(following['batches'][0], withdrawn['batches'][0])
        self.prs['pulls/20']['merged'] = True
        with self.assertRaisesRegex(ValueError, 'publication/live acceptance'): gate.transition(self.doc, withdrawn, self.prs.__getitem__)
        withdrawn['batches'][0]['recovery']['reason'] = ''
        with self.assertRaisesRegex(ValueError, 'reason'): gate.registry(withdrawn)

    def test_synchronized_reserved_member_keeps_ci_usable_while_ordinary_merge_blocks(self):
        import contextlib
        import sys
        def run_git(*args):
            if args[0] == 'show': return json.dumps(self.doc)
            return A
        def api(path):
            if path.startswith('pulls/10/files'): return []
            if path == 'git/ref/heads/main': return {'object': {'sha': A}}
            raise AssertionError(path)
        output = io.StringIO()
        with patch.object(sys, 'argv', ['release_batch.py', '--check-ownership', '10', '--main', A]), \
             patch.object(gate, 'git', side_effect=run_git), patch.object(gate, 'api', side_effect=api), \
             patch.object(gate, 'items', return_value=[]), contextlib.redirect_stdout(output):
            self.assertEqual(gate.main(), 0)
        self.assertIn('individual merge preflight remains blocked', output.getvalue())
        with self.assertRaises(ValueError): gate.ordinary(self.doc, 10)

    def ownership_cli(self, fetched=A, latest=A, initial_blob=B, fetched_blob=B, latest_blob=B, merge_mode=False):
        import contextlib
        import sys
        def run_git(*args):
            if args == ('rev-parse', 'FETCH_HEAD'): return fetched
            if args[0] == 'show': return json.dumps({'version': 1, 'batches': []})
            if args[0] == 'rev-parse':
                return initial_blob if args[1] == f'{A}:{gate.REGISTRY}' else fetched_blob
            return ''
        def api(path):
            if path == 'git/ref/heads/main': return {'object': {'sha': latest}}
            if path == f'contents/{gate.REGISTRY}?ref={latest}': return {'sha': latest_blob}
            raise AssertionError(path)
        argv = ['release_batch.py', '--pr' if merge_mode else '--check-ownership', '99', '--main', A]
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', argv), patch.object(gate, 'git', side_effect=run_git), \
             patch.object(gate, 'api', side_effect=api), patch.object(gate, 'items', return_value=[]), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = gate.main()
        return result, output.getvalue(), errors.getvalue()

    def test_ownership_pins_registry_while_unrelated_main_advances(self):
        for fetched, latest in ((D, D), (A, D), (D, C)):
            with self.subTest(fetched=fetched, latest=latest):
                result, output, errors = self.ownership_cli(fetched=fetched, latest=latest)
                self.assertEqual(result, 0, errors)
                receipt = json.loads(output.splitlines()[-1])
                self.assertTrue(receipt['ownership_only'])
                self.assertEqual(receipt['registry_blob'], B)

    def test_ownership_still_blocks_registry_changes_and_missing_evidence(self):
        for fields in ({'fetched': D, 'fetched_blob': C}, {'latest': D, 'latest_blob': C},
                       {'fetched': D, 'fetched_blob': ''}, {'latest': D, 'latest_blob': None}):
            with self.subTest(fields=fields):
                result, _, errors = self.ownership_cli(**fields)
                self.assertEqual(result, 1)
                self.assertIn('registry', errors)

    def test_ordinary_release_preflight_still_requires_exact_main_at_both_reads(self):
        for fields in ({'fetched': D}, {'latest': D}):
            with self.subTest(fields=fields):
                result, _, errors = self.ownership_cli(merge_mode=True, **fields)
                self.assertEqual(result, 1)
                self.assertIn('main advanced', errors)


class EvidenceTest(unittest.TestCase):
    def ci_api(self, path):
        if path.startswith('actions/runs?'):
            return {'total_count': 2, 'workflow_runs': [
                {'id': i, 'run_number': i, 'run_attempt': 1, 'head_sha': C, 'path': f'.github/workflows/{name}',
                 'status': 'completed', 'conclusion': 'success', 'pull_requests': [{'number': 20}]}
                for i, name in ((1, 'preview.yml'), (2, 'v2-render-test.yml'))]}
        if '/artifacts?' in path:
            return {'total_count': 1, 'artifacts': [{'name': 'preview-dist-' + C, 'expired': False, 'size_in_bytes': 1}]}
        if '/jobs?' in path:
            names = (['preview', 'preview-build'] + [f'preview-shard ({i})' for i in range(1, 6)]
                     if '/1/' in path else ['v2-render'] + [f'render-tests ({lane})' for lane in ('contract', 'league', 'journey')])
            return {'total_count': len(names), 'jobs': [{'name': n, 'conclusion': 'success'} for n in names]}
        if '/check-runs?' in path:
            return {'total_count': 1, 'check_runs': [{'status': 'completed', 'conclusion': 'success'}]}
        raise AssertionError(path)

    def test_ci_missing_failed_skipped_old_or_expired_artifacts_block(self):
        gate.check_ci(20, C, self.ci_api)
        for kind in ('no-runs', 'wrong-head', 'pending', 'failed', 'skipped-shard', 'no-artifact', 'expired', 'partial', 'other-red'):
            def api(path):
                doc = self.ci_api(path)
                if 'workflow_runs' in doc:
                    if kind == 'no-runs': doc['workflow_runs'] = []
                    if kind == 'wrong-head': doc['workflow_runs'][0]['head_sha'] = B
                    if kind == 'pending': doc['workflow_runs'][0]['status'] = 'in_progress'
                    if kind == 'failed': doc['workflow_runs'][0]['conclusion'] = 'failure'
                if 'jobs' in doc and kind == 'skipped-shard': doc['jobs'][-1]['conclusion'] = 'skipped'
                if 'artifacts' in doc:
                    if kind == 'no-artifact': doc['artifacts'] = []; doc['total_count'] = 0
                    if kind == 'expired': doc['artifacts'][0]['expired'] = True
                    if kind == 'partial': doc['total_count'] = 2
                if 'check_runs' in doc and kind == 'other-red': doc['check_runs'][0]['conclusion'] = 'failure'
                return doc
            with self.subTest(kind=kind), self.assertRaises(ValueError): gate.check_ci(20, C, api)

    def test_reviews_are_exact_independent_receipts_with_highrisk_capability(self):
        att = {'head': C, 'result': 'pass', 'reviewer_session': 'reviewer', 'provider': 'claude', 'model': 'opus', 'capability': 'high-risk'}
        receipt = {'commit_id': C, 'state': 'COMMENTED', 'body': '<!-- release-review ' + json.dumps(att) + ' -->', 'submitted_at': '2026-11-03T20:00:00Z'}
        gate.review(20, C, {'author'}, 'review-high-risk', lambda _: [receipt])
        for field, value in (('head', B), ('result', 'fail'), ('reviewer_session', 'author'), ('capability', 'standard'), ('model', '')):
            wrong = dict(att); wrong[field] = value
            mutated = dict(receipt, body='<!-- release-review ' + json.dumps(wrong) + ' -->')
            with self.subTest(field=field), self.assertRaises(ValueError): gate.review(20, C, {'author'}, 'review-high-risk', lambda _: [mutated])
        for change in ({'commit_id': B}, {'state': 'DISMISSED'}, {'body': 'PASS'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate.review(20, C, {'author'}, 'review-standard', lambda _: [dict(receipt, **change)])
        finding = dict(receipt, state='CHANGES_REQUESTED', submitted_at='2026-11-03T21:00:00Z')
        with self.assertRaises(ValueError): gate.review(20, C, {'author'}, 'review-standard', lambda _: [receipt, finding])

    def publication_api(self, path, raw=False):
        if path == 'actions/runs/1':
            return {'id': 1, 'path': '.github/workflows/pages.yml', 'head_branch': 'main', 'head_sha': D, 'conclusion': 'success', 'updated_at': '2026-11-03T19:00:00Z'}
        if path == 'actions/runs/2':
            return {'id': 2, 'path': '.github/workflows/live-page-synthetic.yml', 'head_branch': 'main', 'conclusion': 'success', 'run_started_at': '2026-11-03T20:00:00Z'}
        if path == 'pulls/20': return {'merged': True, 'merge_commit_sha': D}
        if '/jobs?' in path:
            names = ['build', 'deploy'] + [f'validate-shard ({i})' for i in range(1, 6)]
            return {'total_count': 7, 'jobs': [{'name': n, 'conclusion': 'success'} for n in names]}
        if '/artifacts?' in path:
            return {'total_count': 1, 'artifacts': [{'id': 3, 'name': 'live-page-synthetic-results', 'expired': False, 'size_in_bytes': 1}]}
        if path == 'actions/artifacts/3/zip':
            result = {'passed': True, 'problems': [], 'pageErrors': [], 'httpStatus': 200,
                      'liveTag': 'tv-20261103-1900-' + D[:7], 'pages': [{'passed': True}]}
            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as z: z.writestr('live-page-synthetic.json', json.dumps(result))
            return out.getvalue()
        raise AssertionError(path)

    def test_publication_and_live_artifacts_must_accept_exact_merge(self):
        batch = sample()['batches'][0]
        batch.update(state='accepted', acceptance={'published_sha': D, 'publication_run': 1, 'live_run': 2})
        gate.acceptance(batch, self.publication_api)
        for kind in ('publication-red', 'publication-branch', 'wrong-sha', 'not-merged', 'noop', 'live-red', 'live-branch', 'live-before', 'expired', 'wrong-live', 'missing-passed'):
            def api(path, raw=False):
                doc = self.publication_api(path, raw)
                if path == 'actions/runs/1':
                    if kind == 'publication-red': doc['conclusion'] = 'failure'
                    if kind == 'publication-branch': doc['head_branch'] = 'untrusted-branch'
                    if kind == 'wrong-sha': doc['head_sha'] = C
                if path == 'pulls/20' and kind == 'not-merged': doc['merged'] = False
                if '/jobs?' in path and kind == 'noop': doc['jobs'][1]['conclusion'] = 'skipped'
                if path == 'actions/runs/2':
                    if kind == 'live-red': doc['conclusion'] = 'failure'
                    if kind == 'live-branch': doc['head_branch'] = 'untrusted-branch'
                    if kind == 'live-before': doc['run_started_at'] = '2026-11-03T18:00:00Z'
                if '/artifacts?' in path and kind == 'expired': doc['artifacts'][0]['expired'] = True
                if raw:
                    with zipfile.ZipFile(io.BytesIO(doc)) as z: result = json.loads(z.read('live-page-synthetic.json'))
                    if kind == 'wrong-live': result['liveTag'] = 'tv-20261103-1900-' + C[:7]
                    if kind == 'missing-passed': del result['passed']
                    out = io.BytesIO()
                    with zipfile.ZipFile(out, 'w') as z: z.writestr('live-page-synthetic.json', json.dumps(result))
                    doc = out.getvalue()
                return doc
            with self.subTest(kind=kind), self.assertRaises(ValueError): gate.acceptance(batch, api)

    def test_deterministic_highrisk_cannot_hide_in_a_standard_batch(self):
        pr = {'number': 10, 'changed_files': 1, 'labels': [{'name': 'review-standard'}]}
        for path, patch_text in (('config/roster.json', ''), ('pipelines/value_reference.py', ''),
                                  ('tests/test_any.py', '- self.assertTrue(result)'), ('tests/test_any.py', '+ @unittest.skip("x")'),
                                  ('tests/test_any.py', None)):
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.risk_floor(pr, 'review-standard', lambda _: [{'filename': path, 'patch': patch_text}])
        gate.risk_floor(pr, 'review-standard', lambda _: [{'filename': 'app/v2/copy.js', 'patch': '+copy'}])
        with self.assertRaises(ValueError): gate.risk_floor(pr, 'review-standard', lambda _: [])
        pr['labels'] = [{'name': 'review-high-risk'}]
        with self.assertRaises(ValueError): gate.risk_floor(pr, 'review-standard', lambda _: [])

    def test_registry_and_ownership_workflow_are_wired(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIsNone(gate.registry(json.loads((root / gate.REGISTRY).read_text())))
        workflow = (root / '.github/workflows/release-batch.yml').read_text()
        self.assertIn('ref: ${{ github.event.pull_request.base.sha }}', workflow)
        self.assertIn('--check-ownership "$PR_NUMBER" --main "$main_sha"', workflow)
        self.assertNotIn('continue-on-error', workflow)


if __name__ == '__main__': unittest.main()
