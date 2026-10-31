"""Publication-only release window guards, using local bare remotes."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pipelines.main_write_guard import decision
from tests.test_rebuild_chain_workflow import git, script_of, step_blocks

ROOT = Path(__file__).resolve().parents[1]
WRITERS = {'rebuild-chain': 1, 'health-artifacts': 3, 'fidelity-pulse': 1,
           'source-vintage-check': 1, 'espn-supabase-sync': 1,
           'espn-weekly-store': 1, 'player-status-history': 1,
           'player-trace-rebuild': 1, 'espn-history-probe': 1,
           'sleeper-identity-refresh': 1}
NOW = datetime(2026, 10, 28, 16, tzinfo=timezone.utc)


def control():
    return json.dumps(dict(paused=True, started_at='2026-10-28T15:00:00Z',
                           expires_at='2026-10-28T18:00:00Z', reason='release'))


class DecisionTest(unittest.TestCase):
    def test_off_and_expiry(self):
        self.assertFalse(decision('{"paused":false}', NOW)[0])
        self.assertTrue(decision(control(), NOW)[0])
        self.assertFalse(decision(control(), NOW.replace(hour=18))[0])

    def test_invalid_controls(self):
        base=json.loads(control())
        for change in [{'paused':'true'}, {'expires_at':None}, {'reason':''},
                       {'expires_at':'2026-10-29T18:00:00Z'},
                       {'started_at':'2026-10-28T17:00:00Z'},
                       {'started_at':'2026-10-28T15:00:00'}]:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError, AttributeError)):
                decision(json.dumps({**base, **change}), NOW)


class WorkflowTest(unittest.TestCase):
    def test_every_writer_and_no_other_work_is_guarded(self):
        found={}
        for path in (ROOT/'.github/workflows').glob('*.yml'):
            text=path.read_text()
            guarded=0
            for block in step_blocks(text):
                script=script_of(block)
                if not script: continue
                if 'git commit' in script and path.stem not in {'bake-players', 'sleeper-projections-backfill'}:
                    self.assertIn('release_guard stage', script, path.name)
                if 'release_guard stage' not in script: continue
                guarded+=1
                subprocess.run(['bash','-n'], input=script, text=True, check=True)
                self.assertLess(script.index('git add'),script.index('release_guard stage'))
                self.assertLess(script.index('release_guard stage'),script.index('git commit'))
                self.assertEqual(len(re.findall(r'\bgit(?:\s+-C\s+(?:"[^"]*"|\S+))?\s+push\b', script)), 1, path.name)
                self.assertIn('release_guard push\n',script)
                self.assertIn('if [ "$rc" = 75 ]; then exit 0; fi',script)
            if guarded: found[path.stem]=guarded
            if path.stem in WRITERS:
                self.assertEqual(text.count('name: Retain deferred publication ('),WRITERS[path.stem])
        self.assertEqual(found, WRITERS)

    def test_pause_exits_only_publication_step(self):
        # Real workflow functions must exit successfully before commit/dispatch,
        # allowing a following ingestion/validation/deployment step to execute.
        for name, count in WRITERS.items():
            for block in step_blocks((ROOT/f'.github/workflows/{name}.yml').read_text()):
                script=script_of(block)
                if not script or 'release_guard stage' not in script: continue
                # Extract only the guard functions; prelude work differs by writer.
                end=script.index('\n}',script.index('release_push()'))+2
                with tempfile.TemporaryDirectory() as td:
                    p=Path(td); (p/'pipelines').mkdir()
                    (p/'pipelines/main_write_guard.py').write_text('raise SystemExit(75)\n')
                    for call in ['release_guard stage', 'release_push origin HEAD:main']:
                        # The publication-pause scenarios run on main; branch refusal
                        # is exercised separately against a real temporary remote.
                        result=subprocess.run(['bash','-e','-c',script[:end]+'\n'+call+'\ntouch committed\n'],
                                              cwd=p,env={**os.environ,'GITHUB_REF':'refs/heads/main'})
                        self.assertEqual(result.returncode,0)
                        self.assertFalse((p/'committed').exists())


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.remote=self.root/'remote'; self.work=self.root/'work'
        git(self.root,'init','-q','--bare','-b','main',str(self.remote))
        git(self.root,'clone','-q',str(self.remote),str(self.work))
        git(self.work,'config','user.name','test');git(self.work,'config','user.email','test@test')
        (self.work/'.github').mkdir()
        (self.work/'.github/main-write-pause.json').write_text('{"paused":false}')
        (self.work/'candidate').write_text('old')
        git(self.work,'add','.');git(self.work,'commit','-qm','base');git(self.work,'push','-qu','origin','main')
        self.base=git(self.work,'rev-parse','HEAD')
        (self.work/'candidate').write_text('new');git(self.work,'add','candidate')
        (self.work/'unstaged').write_text('partial must not publish')

    def run_guard(self, phase='stage', target='main'):
        return subprocess.run(['python3',str(ROOT/'pipelines/main_write_guard.py'),
            '--writer','test','--phase',phase,'--target',target],cwd=self.work,
            env={**os.environ,'GITHUB_OUTPUT':str(self.root/'outputs'),
                 'GITHUB_STEP_SUMMARY':str(self.root/'summary')},capture_output=True,text=True)

    def remote_control(self, value):
        other=self.root/'other';git(self.root,'clone','-q',str(self.remote),str(other))
        (other/'.github/main-write-pause.json').write_text(value)
        git(other,'add','.');git(other,'-c','user.name=t','-c','user.email=t@t','commit','-qm','control')
        git(other,'push','-q','origin','main')

    def test_remote_control_and_retained_patch(self):
        from datetime import timedelta
        now=datetime.now(timezone.utc)
        self.remote_control(json.dumps({'paused':True,'started_at':now.isoformat(),
            'expires_at':(now+timedelta(hours=1)).isoformat(),'reason':'release'}))
        r=self.run_guard();self.assertEqual(r.returncode,75,r.stderr)
        patch=self.work/'output/release-publications/test/stage.patch'
        self.assertIn('+new',patch.read_text());self.assertNotIn('unstaged',patch.read_text())
        self.assertEqual((self.work/'candidate').read_text(),'new')
        self.assertEqual(git(self.work,'diff','--cached','--name-only'),'')
        verify=self.root/'verify';git(self.root,'clone','-q',str(self.remote),str(verify))
        git(verify,'apply',str(patch));self.assertEqual((verify/'candidate').read_text(),'new')
        self.assertIn('publication_deferred=true',(self.root/'outputs').read_text())

    def test_invalid_and_unreachable_control_defer(self):
        self.remote_control('malformed')
        self.assertEqual(self.run_guard().returncode,75)
        git(self.work,'remote','set-url','origin',str(self.root/'unavailable'))
        self.assertEqual(self.run_guard().returncode,75)

    def test_expired_remote_control_restores_publication(self):
        from datetime import timedelta
        now=datetime.now(timezone.utc)
        self.remote_control(json.dumps({'paused':True,
            'started_at':(now-timedelta(hours=2)).isoformat(),
            'expires_at':(now-timedelta(hours=1)).isoformat(),'reason':'release'}))
        result=self.run_guard()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('expired',result.stdout)
        self.assertEqual(git(self.work,'diff','--cached','--name-only'),'candidate')

    def test_retention_failure_is_not_reported_as_success(self):
        self.remote_control('malformed')
        (self.work/'output').write_text('cannot create artifact directory')
        result=self.run_guard()
        self.assertNotIn(result.returncode, (0,75))
        self.assertFalse((self.root/'outputs').exists())

    def test_off_and_other_branch_continue(self):
        self.assertEqual(self.run_guard().returncode,0)
        self.remote_control('malformed')
        self.assertEqual(self.run_guard(target='feature').returncode,0)

    def test_accepted_push_can_confirm_during_pause(self):
        git(self.work,'commit','-qm','candidate')
        git(self.work,'push','-q','origin','main')
        self.remote_control('malformed')
        result=self.run_guard('push')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('no-op push confirmation',result.stdout)

    def test_unpublished_empty_commit_is_still_deferred(self):
        git(self.work,'restore','--staged','candidate')
        git(self.work,'commit','--allow-empty','-qm','empty candidate')
        self.remote_control('malformed')
        result=self.run_guard('push')
        self.assertEqual(result.returncode,75,result.stderr)
        self.assertTrue((self.work/'output/release-publications/test/push.json').exists())

    def test_pause_after_commit_retains_commit_patch(self):
        git(self.work,'commit','-qm','candidate')
        self.remote_control('malformed')
        r=self.run_guard('push');self.assertEqual(r.returncode,75,r.stderr)
        patch=self.work/'output/release-publications/test/push.patch'
        self.assertIn('+new',patch.read_text());self.assertNotIn('main-write-pause',patch.read_text())
        self.assertEqual(git(self.remote,'show','main:candidate'),'old')



# JEG-1364: main's JEG-1206 publish path builds the publication in a scratch
# worktree and pushes it by refspec. The guard must stage before the candidate
# commit, and the scratch push must go through release_push and retain the
# commit it would have published.
PAUSE_ON_WORKTREE_SHIM = """#!/bin/bash
if [ "$1" = "worktree" ] && [ "$2" = "add" ] && [ ! -e "$SHIM_STATE/fired" ]; then
  touch "$SHIM_STATE/fired"
  ( cd "$SHIM_OTHER" && {real} pull -q origin main && printf '%s' "$SHIM_CONTROL" > .github/main-write-pause.json \\
    && {real} add -A && {real} -c user.name=t -c user.email=t@t commit -qm 'release pause' \\
    && {real} push -q origin HEAD:main ) >/dev/null 2>&1
fi
exec {real} "$@"
"""


def active_control():
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    return json.dumps({'paused': True, 'started_at': (now - timedelta(minutes=1)).isoformat(),
                       'expires_at': (now + timedelta(hours=1)).isoformat(), 'reason': 'release'})


class RebuildChainPublishTest(unittest.TestCase):
    def commit_step(self):
        from tests.test_rebuild_chain_workflow import COMMIT, WORKFLOW, find_step
        return script_of(find_step(WORKFLOW, COMMIT))

    def test_every_main_push_is_guarded_and_stage_precedes_the_commit(self):
        script = self.commit_step()
        define = script.index('release_push() {')
        body = script[define:script.index('\n}', define)]
        pushes = [m.start() for m in re.finditer(r'\bgit(?:\s+-C\s+(?:"[^"]*"|\S+))?\s+push\b', script)]
        self.assertEqual(len(pushes), 1, 'only release_push itself may run git push')
        self.assertIn(script[pushes[0]:pushes[0] + 8], body)
        self.assertIn('release_push origin "$publication:refs/heads/main"', script)
        self.assertIn('--head "${publication:-HEAD}"', script)
        stage = script.index('release_guard stage')
        self.assertLess(stage, script.index('git commit -m "$MESSAGE"'))
        self.assertLess(stage, script.index('git worktree add'))
        self.assertLess(stage, script.index('git -C "$pub/tree" commit'))

    def scenario(self, control_at):
        import shutil
        import sys
        from tests.test_rebuild_chain_workflow import (
            BASELINE, COMMIT, FIXTURE, HEALTH, SYNC_OK, WORKFLOW, run_script, write)
        real = shutil.which('git')
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            remote, work, other = td / 'remote.git', td / 'work', td / 'other'
            git(td, 'init', '-q', '--bare', '-b', 'main', str(remote))
            git(td, 'clone', '-q', str(remote), str(work))
            git(work, 'checkout', '-q', '-b', 'main')
            for rel, content in {**BASELINE, '.github/main-write-pause.json': '{"paused":false}'}.items():
                write(work, rel, content)
            git(work, 'add', '-A')
            git(work, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'baseline')
            git(work, 'push', '-q', '-u', 'origin', 'main')
            base = git(work, 'rev-parse', 'HEAD')
            git(td, 'clone', '-q', str(remote), str(other))
            # health-artifacts moves main meanwhile: the publication keeps main's
            # report, so it differs from this run's candidate commit.
            moves = {HEALTH: 'MAIN-HEALTH'}
            if control_at == 'stage':
                moves['.github/main-write-pause.json'] = active_control()
            for rel, content in moves.items():
                write(other, rel, content)
            git(other, 'add', '-A')
            git(other, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'main moved')
            git(other, 'push', '-q', 'origin', 'main')
            moved = git(other, 'rev-parse', 'HEAD')
            for rel, content in {FIXTURE: 'NEW', 'output/comparison-chain-status.json': 'GREEN',
                                 HEALTH: 'RUN-HEALTH'}.items():
                write(work, rel, content)
            shim, state = td / 'shim', td / 'state'
            shim.mkdir(); state.mkdir()
            (shim / 'git').write_text(PAUSE_ON_WORKTREE_SHIM.format(real=real))
            (shim / 'git').chmod(0o755)
            out = td / 'gh_out.txt'
            env = {'PATH': f'{shim}:{os.path.dirname(sys.executable)}:/usr/bin:/bin:/usr/local/bin',
                   'GITHUB_OUTPUT': str(out), 'GITHUB_STEP_SUMMARY': str(td / 'summary.md'),
                   'CHAIN_OUTCOME': 'success', 'CHAIN_ATTEMPT': '1', 'MAX_CHAIN_ATTEMPTS': '3',
                   'BAKE_PLAYERS': 'false', 'SHIM_STATE': str(state), 'SHIM_OTHER': str(other),
                   'SHIM_CONTROL': active_control() if control_at == 'push' else ''}
            if control_at == 'stage':
                (state / 'fired').touch()
            sync = run_script(WORKFLOW, SYNC_OK, work, env)
            self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
            r = run_script(WORKFLOW, COMMIT, work, env)
            retained = work / 'output/release-publications/rebuild-chain-1'
            files = {p.name: p.read_text() for p in retained.glob('*')} if retained.exists() else {}
            return {'rc': r.returncode, 'log': r.stdout + r.stderr, 'base': base, 'moved': moved,
                    'main_fixture': git(remote, 'show', f'main:{FIXTURE}'),
                    'main_log': git(remote, 'log', '--format=%s', f'{base}..main').splitlines(),
                    'outputs': out.read_text() if out.exists() else '', 'retained': files,
                    'worktrees': git(work, 'worktree', 'list').splitlines()}

    def assertDeferred(self, r):
        self.assertEqual(0, r['rc'], r['log'])
        self.assertEqual('OLD', r['main_fixture'], 'nothing may publish during a pause')
        self.assertNotIn('Automated comparison rebuild (GitHub Actions)', r['main_log'])
        self.assertIn('pushed=false', r['outputs'])
        self.assertIn('publication_deferred=true', r['outputs'])
        self.assertNotIn('pushed=true', r['outputs'])
        self.assertEqual(1, len(r['worktrees']), 'the scratch worktree is cleaned up')

    def test_pause_at_stage_defers_before_the_candidate_commit(self):
        r = self.scenario('stage')
        self.assertDeferred(r)
        self.assertIn('stage.patch', r['retained'])
        self.assertIn('+NEW', r['retained']['stage.patch'])
        self.assertNotIn('push.patch', r['retained'])

    def test_pause_at_push_retains_the_scratch_publication(self):
        r = self.scenario('push')
        self.assertDeferred(r)
        patch, meta = r['retained']['push.patch'], json.loads(r['retained']['push.json'])
        self.assertIn('+NEW', patch)
        # The retained patch is what would have published: main's newer health
        # report is kept, so this run's own report is not in it.
        self.assertNotIn('RUN-HEALTH', patch)
        self.assertEqual(r['moved'], meta['base'])


if __name__=='__main__': unittest.main()
