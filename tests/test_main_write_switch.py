"""JEG-1472: scoped release-window pause and its switch workflow.

A scoped control names the frequent writers it covers and lasts at most two
hours. Daily and weekly snapshot writers are never covered. The guard names are
read as attributes inside each test so these tests run, and fail, against a
guard that predates JEG-1472.
"""
import importlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipelines import main_write_guard as guard
from tests.test_main_write_guard import WRITERS
from tests.test_rebuild_chain_workflow import git, script_of, step_blocks

ROOT = Path(__file__).resolve().parents[1]
SWITCH = ROOT / '.github/workflows/main-write-pause-switch.yml'
CONTROL = '.github/main-write-pause.json'
NOW = datetime(2026, 11, 1, 16, tzinfo=timezone.utc)
FREQUENT = ['fidelity-pulse', 'rebuild-chain', 'health-artifacts', 'source-vintage-check']
DAILY = ['espn-weekly-store', 'player-trace-rebuild', 'player-status-history',
         'espn-supabase-sync', 'sleeper-identity-refresh', 'espn-history-probe']


def writer_ids(base):
    return [f'{base}-{n}' for n in range(1, WRITERS[base] + 1)]


def scoped(scope=None, start=None, end=None, **extra):
    start = start or NOW - timedelta(minutes=30)
    end = end or start + timedelta(minutes=90)
    doc = {'paused': True, 'started_at': start.isoformat(), 'expires_at': end.isoformat(),
           'reason': 'release window', 'scope': FREQUENT if scope is None else scope}
    return json.dumps({**doc, **extra})


def switch_module():
    return importlib.import_module('pipelines.main_write_switch')


class ScopeDecisionTest(unittest.TestCase):
    def test_allowlist_matches_the_pinned_writer_inventory(self):
        self.assertEqual(list(guard.FREQUENT_WRITERS), FREQUENT)
        self.assertEqual(list(guard.DAILY_WRITERS), DAILY)
        self.assertFalse(set(guard.FREQUENT_WRITERS) & set(guard.DAILY_WRITERS))
        self.assertEqual(set(guard.FREQUENT_WRITERS) | set(guard.DAILY_WRITERS), set(WRITERS))

    def test_a_daily_writer_is_never_paused_by_a_scoped_pause(self):
        for base in DAILY:
            for writer in writer_ids(base):
                with self.subTest(writer=writer):
                    paused, reason = guard.decision(scoped(), NOW, writer)
                    self.assertFalse(paused, reason)

    def test_every_frequent_writer_block_is_paused(self):
        for base in FREQUENT:
            for writer in writer_ids(base):
                with self.subTest(writer=writer):
                    paused, reason = guard.decision(scoped(), NOW, writer)
                    self.assertTrue(paused, reason)
                    self.assertIn('scope', reason)

    def test_a_writer_outside_the_scope_publishes_while_the_pause_is_on(self):
        control = scoped(['fidelity-pulse'])
        self.assertTrue(guard.decision(control, NOW, 'fidelity-pulse-1')[0])
        for writer in ('health-artifacts-3', 'rebuild-chain-1', 'source-vintage-check-1',
                       'espn-weekly-store-1'):
            with self.subTest(writer=writer):
                paused, reason = guard.decision(control, NOW, writer)
                self.assertFalse(paused, reason)
                self.assertIn('does not cover', reason)

    def test_an_expired_scoped_pause_restores_publication(self):
        control = scoped()
        for writer in ('fidelity-pulse-1', 'rebuild-chain-1', 'health-artifacts-2'):
            with self.subTest(writer=writer):
                self.assertTrue(guard.decision(control, NOW, writer)[0])
                paused, reason = guard.decision(control, NOW + timedelta(minutes=61), writer)
                self.assertFalse(paused)
                self.assertIn('expired', reason)

    def test_a_control_without_a_scope_still_pauses_everything(self):
        raw = json.dumps({'paused': True, 'started_at': (NOW - timedelta(hours=1)).isoformat(),
                          'expires_at': (NOW + timedelta(hours=3)).isoformat(), 'reason': 'release'})
        for writer in ('espn-weekly-store-1', 'fidelity-pulse-1', 'health-artifacts-3'):
            self.assertTrue(guard.decision(raw, NOW, writer)[0])

    def test_invalid_scopes_fail_closed(self):
        for change in ({'scope': []}, {'scope': 'fidelity-pulse'}, {'scope': [1]},
                       {'scope': ['fidelity-pulse', 'fidelity-pulse']},
                       {'scope': ['espn-weekly-store']}, {'scope': ['fidelity-pulse-1']},
                       {'scope': ['not-a-writer']}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                guard.decision(scoped(**change), NOW, 'fidelity-pulse-1')

    def test_a_null_scope_is_invalid_not_a_pause_of_everything(self):
        raw = json.loads(scoped())
        raw['scope'] = None
        with self.assertRaises(ValueError):
            guard.decision(json.dumps(raw), NOW, 'fidelity-pulse-1')

    def test_a_scoped_pause_longer_than_two_hours_is_invalid(self):
        start = NOW - timedelta(minutes=30)
        guard.decision(scoped(start=start, end=start + timedelta(minutes=120)), NOW)
        with self.assertRaises(ValueError):
            guard.decision(scoped(start=start, end=start + timedelta(minutes=121)), NOW)


class ScopedGuardCliTest(unittest.TestCase):
    """The real guard script against a local bare remote."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote, self.work = self.root / 'remote', self.root / 'work'
        git(self.root, 'init', '-q', '--bare', '-b', 'main', str(self.remote))
        git(self.root, 'clone', '-q', str(self.remote), str(self.work))
        git(self.work, 'config', 'user.name', 'test')
        git(self.work, 'config', 'user.email', 'test@test')
        (self.work / '.github').mkdir()
        (self.work / CONTROL).write_text('{"paused":false}')
        (self.work / 'candidate').write_text('old')
        git(self.work, 'add', '.')
        git(self.work, 'commit', '-qm', 'base')
        git(self.work, 'push', '-qu', 'origin', 'main')
        (self.work / 'candidate').write_text('new')
        git(self.work, 'add', 'candidate')

    def set_remote_control(self, value):
        other = self.root / 'other'
        git(self.root, 'clone', '-q', str(self.remote), str(other))
        (other / CONTROL).write_text(value)
        git(other, 'add', '.')
        git(other, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'control')
        git(other, 'push', '-q', 'origin', 'main')

    def run_guard(self, writer, phase='stage'):
        return subprocess.run(
            ['python3', str(ROOT / 'pipelines/main_write_guard.py'), '--writer', writer,
             '--phase', phase, '--target', 'main'], cwd=self.work,
            env={**os.environ, 'GITHUB_OUTPUT': str(self.root / 'outputs'),
                 'GITHUB_STEP_SUMMARY': str(self.root / 'summary')},
            capture_output=True, text=True)

    def live_control(self, **kwargs):
        now = datetime.now(timezone.utc)
        return scoped(start=now - timedelta(minutes=5), end=now + timedelta(minutes=85), **kwargs)

    def test_daily_writer_publishes_and_frequent_writer_is_held(self):
        self.set_remote_control(self.live_control())
        daily = self.run_guard('espn-weekly-store-1')
        self.assertEqual(daily.returncode, 0, daily.stderr)
        self.assertEqual(git(self.work, 'diff', '--cached', '--name-only'), 'candidate')
        self.assertFalse((self.root / 'outputs').exists())
        frequent = self.run_guard('fidelity-pulse-1')
        self.assertEqual(frequent.returncode, 75, frequent.stderr)
        self.assertEqual(git(self.work, 'diff', '--cached', '--name-only'), '')
        self.assertIn('publication_deferred=true', (self.root / 'outputs').read_text())

    def test_writer_outside_the_scope_publishes_on_both_phases(self):
        self.set_remote_control(self.live_control(scope=['fidelity-pulse']))
        for phase in ('stage', 'push'):
            result = self.run_guard('health-artifacts-3', phase)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_guard('fidelity-pulse-1').returncode, 75)

    def test_expired_scoped_pause_restores_a_frequent_writer(self):
        now = datetime.now(timezone.utc)
        self.set_remote_control(scoped(start=now - timedelta(minutes=110),
                                       end=now - timedelta(minutes=20)))
        result = self.run_guard('fidelity-pulse-1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('expired', result.stdout)
        self.assertEqual(git(self.work, 'diff', '--cached', '--name-only'), 'candidate')


class SwitchBuildTest(unittest.TestCase):
    def test_on_builds_a_scoped_control_the_guard_reads_as_paused(self):
        switch = switch_module()
        doc = switch.build('on', 90, ' release window ', NOW)
        self.assertEqual(doc['scope'], sorted(FREQUENT))
        self.assertEqual(doc['reason'], 'release window')
        self.assertEqual(doc['started_at'], '2026-11-01T16:00:00Z')
        self.assertEqual(doc['expires_at'], '2026-11-01T17:30:00Z')
        for writer in ('fidelity-pulse-1', 'source-vintage-check-1'):
            self.assertTrue(guard.decision(json.dumps(doc), NOW, writer)[0])
        self.assertFalse(guard.decision(json.dumps(doc), NOW, 'player-trace-rebuild-1')[0])

    def test_the_limit_is_120_minutes_and_longer_is_refused(self):
        switch = switch_module()
        doc = switch.build('on', 120, 'release', NOW)
        self.assertEqual(datetime.fromisoformat(doc['expires_at'].replace('Z', '+00:00')) - NOW,
                         timedelta(minutes=120))
        for minutes in (121, 360, 0, -5, 90.5, '90', True, None):
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                switch.build('on', minutes, 'release', NOW)

    def test_an_empty_or_multiline_reason_is_refused(self):
        switch = switch_module()
        for reason in ('', '   ', '\n', None, 'one\ntwo', 'x' * 201):
            for action in ('on', 'off'):
                with self.subTest(reason=reason, action=action), self.assertRaises(ValueError):
                    switch.build(action, 90, reason, NOW)

    def test_a_daily_writer_or_unknown_writer_in_the_scope_is_refused(self):
        switch = switch_module()
        for writer in DAILY + ['not-a-writer']:
            with self.subTest(writer=writer), self.assertRaises(ValueError):
                switch.build('on', 90, 'release', NOW, scope=FREQUENT + [writer])
        with self.assertRaises(ValueError):
            switch.build('on', 90, 'release', NOW, scope=[])

    def test_off_writes_the_default_unpaused_control(self):
        switch = switch_module()
        doc = switch.build('off', 90, 'release done', NOW)
        self.assertEqual(doc, {'paused': False, 'started_at': None, 'expires_at': None, 'reason': ''})
        with self.assertRaises(ValueError):
            switch.build('toggle', 90, 'release', NOW)

    def test_the_cli_refuses_before_writing_and_writes_only_the_control(self):
        switch = switch_module()
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / '.github').mkdir()
            self.assertEqual(switch.write_control({'paused': False}, td), Path(td) / CONTROL)
            self.assertEqual([p.relative_to(td).as_posix() for p in Path(td).rglob('*') if p.is_file()],
                             [CONTROL])
        before = (ROOT / CONTROL).read_text()
        for args in (['--action', 'on', '--minutes', '121', '--reason', 'release'],
                     ['--action', 'on', '--minutes', '90', '--reason', ''],
                     ['--action', 'on', '--minutes', 'abc', '--reason', 'release']):
            with self.subTest(args=args):
                result = subprocess.run(['python3', str(ROOT / 'pipelines/main_write_switch.py'), *args],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('nothing written', result.stdout)
        self.assertEqual((ROOT / CONTROL).read_text(), before)


class SwitchWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = SWITCH.read_text()
        self.doc = None
        try:
            import yaml
        except ImportError:
            return
        self.doc = yaml.safe_load(self.text)

    def steps(self):
        return step_blocks(self.text)

    def test_text_contract(self):
        """Plain-text checks that run without PyYAML."""
        scripts = [script_of(block) or '' for block in self.steps()]
        adds = [line.strip() for script in scripts for line in script.splitlines()
                if re.match(r'\s*git add\b', line)]
        self.assertEqual(adds, ['git add "$control"'])
        self.assertIn('control=.github/main-write-pause.json', '\n'.join(scripts))
        joined = '\n'.join(scripts)
        for forbidden in ('git add -A', 'git add .', 'git commit -a', 'git push --force',
                          'git push -f', '--force-with-lease', 'git rebase main', 'reset --hard',
                          'main_write_guard.py', 'release_guard'):
            self.assertNotIn(forbidden, joined)
        self.assertEqual(len(re.findall(r'\bgit push\b', joined)), 1)
        self.assertIn('git push origin "HEAD:${GITHUB_REF:?}"', joined)
        self.assertIn('[ "$(git diff --name-only origin/main HEAD)" = "$control" ]', joined)
        # Never echo or write the token; inputs reach scripts only as env vars.
        self.assertNotIn('MAIN_WRITER_TOKEN', joined)
        self.assertNotIn('${{', joined)
        self.assertEqual(sorted(set(re.findall(r'secrets\.([A-Z0-9_]+)', self.text))),
                         ['MAIN_WRITER_APP_ID', 'MAIN_WRITER_APP_PRIVATE_KEY'])
        self.assertEqual(self.text.count('${{ steps.main-writer.outputs.token }}'), 1)

    def test_validation_precedes_the_token_and_the_push(self):
        names = [re.search(r'name:\s*(.+)', block).group(1).strip() for block in self.steps()
                 if re.search(r'^\s*(- )?name:', block, re.M)]
        self.assertEqual(names, ['Build and validate the control', 'Mint main writer token',
                                 'Commit and push the control'])
        build = script_of(self.steps()[2])
        self.assertIn('pipelines/main_write_switch.py', build)
        for forbidden in ('--out', '--path', '--scope'):
            self.assertNotIn(forbidden, build)

    def test_workflow_structure_and_only_the_control_path_is_written(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('PyYAML not installed; test_text_contract covers the same boundary')
        doc = self.doc
        triggers = doc.get('on', doc.get(True))
        self.assertEqual(list(triggers), ['workflow_dispatch'])
        inputs = triggers['workflow_dispatch']['inputs']
        self.assertEqual(list(inputs), ['action', 'minutes', 'reason'])
        self.assertEqual(inputs['action']['options'], ['on', 'off'])
        self.assertTrue(inputs['action']['required'] and inputs['reason']['required'])
        self.assertEqual(str(inputs['minutes']['default']), '90')
        self.assertEqual(doc['concurrency'], {'group': 'main-write-pause-switch',
                                              'cancel-in-progress': False})
        self.assertEqual(doc['permissions'], {'contents': 'read'})
        job = doc['jobs']['switch']
        self.assertEqual(list(doc['jobs']), ['switch'])
        self.assertEqual(job['environment'], 'main-writer')
        self.assertEqual(job['if'], "github.ref == 'refs/heads/main'")
        writes = []
        for step in job['steps']:
            run = step.get('run', '')
            for line in run.splitlines():
                if re.match(r'\s*git add\b', line):
                    writes.append(line.strip().split(None, 2)[2])
                self.assertNotRegex(line, r'(?:>|>>|tee)\s*\S*\.github/(?!main-write-pause\.json)')
            if 'git push' in run:
                self.assertEqual(step['env']['MAIN_WRITER_TOKEN'], '${{ steps.main-writer.outputs.token }}')
        self.assertEqual(writes, ['"$control"'])
        app = [s for s in job['steps'] if 'create-github-app-token' in s.get('uses', '')][0]
        self.assertRegex(app['uses'], r'@[0-9a-f]{40}$')
        self.assertEqual(app['with']['permission-contents'], 'write')
        self.assertEqual(app['with']['repositories'], '${{ github.event.repository.name }}')
        self.assertNotIn('skip-token-revoke', app['with'])
        for step in job['steps']:
            if step.get('uses', '').startswith('actions/checkout'):
                self.assertIs(step['with']['persist-credentials'], False)


if __name__ == '__main__':
    unittest.main()
