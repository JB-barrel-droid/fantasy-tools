import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from lanes.pr_attribution import LANE_PREFIXES, check_prefix, parse_lane
from scripts.check_pr_lane import is_warn_only, main


def line(builder='Codex'):
    return f'Lane: built by {builder} (gpt-6.1-sol); coordinated by Claude Duet; review pending.'


class TestPRLane(unittest.TestCase):
    def test_all_builders_and_prefixes(self):
        for builder, prefix in LANE_PREFIXES.items():
            with self.subTest(builder=builder):
                attribution = parse_lane(line(builder))
                self.assertEqual(attribution.model, 'gpt-6.1-sol')
                self.assertEqual(attribution.coordinator, 'Claude Duet')
                check_prefix(attribution, prefix + 'JEG-1453')
                for bad in ('be/JEG-1453', prefix, 'x' + prefix + 'task'):
                    with self.assertRaises(ValueError):
                        check_prefix(attribution, bad)

    def test_missing_malformed_and_duplicate_lines(self):
        for body in ('', 'docs only', line() + '\n' + line(),
                     line().replace('(gpt-6.1-sol)', '()'),
                     line().replace('Claude Duet', ' '),
                     line().replace('Codex', 'Unknown'),
                     line().replace('gpt-6.1-sol', '<model>'),
                     '<!--\n' + line() + '\n-->', '```text\n' + line() + '\n```'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_lane(body)

    def test_comments_and_fenced_examples_do_not_duplicate(self):
        self.assertEqual(parse_lane('~~~\n' + line('Muse') + '\n~~~\n' + line()).builder, 'Codex')

    def test_unclosed_comment_hides_rest(self):
        with self.assertRaises(ValueError):
            parse_lane('<!-- unclosed\n' + line())
        self.assertEqual(parse_lane(line() + '\n<!--\n' + line('Muse')).builder, 'Codex')

    def test_visible_indentation(self):
        for spaces in range(4):
            self.assertEqual(parse_lane(' ' * spaces + line()).builder, 'Codex')
        for indent in ('    ', '     ', '\t'):
            with self.assertRaises(ValueError):
                parse_lane(indent + line())

    def test_comment_markers_inside_fences_are_literal(self):
        for opener, closer in (('```text', '```'), ('~~~~python', '~~~~~')):
            body = opener + '\n<!--\n' + line('Muse') + '\n' + closer + '\n' + line()
            self.assertEqual(parse_lane(body).builder, 'Codex')

    def test_only_matching_long_enough_bare_fence_closes(self):
        for false_closer in ('```', '~~~~', '````python'):
            body = '````text\n' + false_closer + '\n' + line('Muse') + '\n````\n' + line()
            self.assertEqual(parse_lane(body).builder, 'Codex')

    def test_comments_outside_fences_hide_fence_markers(self):
        self.assertEqual(parse_lane('<!--\n```\n-->\n' + line()).builder, 'Codex')

    def test_config_errors_are_clear_even_with_warnings_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            event, config = Path(directory)/'event.json', Path(directory)/'config.json'
            event.write_text(json.dumps({'pull_request': {'body': line(), 'head': {'ref': 'codex/task'}}}))
            for values in (
                {'warn_only': False, 'enforce_after': '2026-11-07T16:30:00'},
                {'warn_only': True, 'enforce_after': 'invalid'},
                {'warn_only': 'true', 'enforce_after': '2026-11-07T16:30:00Z'},
            ):
                config.write_text(json.dumps(values))
                output = io.StringIO()
                with contextlib.redirect_stderr(output):
                    self.assertEqual(main(['--event', str(event), '--config', str(config)]), 2)
                self.assertIn('Config error:', output.getvalue())
            self.assertIn('timezone offset', self._naive_config_error())

    def _naive_config_error(self):
        with self.assertRaises(ValueError) as caught:
            is_warn_only({'warn_only': True, 'enforce_after': '2026-11-07T16:30:00'}, datetime.now(timezone.utc))
        return str(caught.exception)

    def test_open_pr_sweep_checks_every_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            prs, config = Path(directory)/'prs.json', Path(directory)/'config.json'
            prs.write_text(json.dumps([
                {'number': 1, 'body': None, 'head': {'ref': 'codex/task'}},
                {'number': 2, 'body': line(), 'head': {'ref': 'codex/task'}},
            ]))
            config.write_text(json.dumps({'warn_only': False, 'enforce_after': '2026-11-07T16:30:00Z'}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['--open-prs', str(prs), '--config', str(config)]), 1)
            self.assertIn('Checking PR #2', output.getvalue())

    def test_deadline_and_flag(self):
        config = {'warn_only': True, 'enforce_after': '2026-11-07T16:30:00+00:00'}
        self.assertTrue(is_warn_only(config, datetime(2026, 11, 7, 16, 29, tzinfo=timezone.utc)))
        self.assertFalse(is_warn_only(config, datetime(2026, 11, 7, 16, 30, tzinfo=timezone.utc)))
        config['warn_only'] = False
        self.assertFalse(is_warn_only(config, datetime(2026, 10, 31, tzinfo=timezone.utc)))

    def test_cli_invalid_warning_failure_and_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            event, config = Path(directory)/'event.json', Path(directory)/'config.json'
            for body, branch, warning, expected in (
                (None, 'codex/task', True, 0),
                (None, 'codex/task', False, 1),
                (line(), 'claude/task', False, 1),
                (line(), 'codex/task', False, 0),
            ):
                event.write_text(json.dumps({'pull_request': {'body': body, 'head': {'ref': branch}}}))
                config.write_text(json.dumps({'warn_only': warning, 'enforce_after': '2099-01-01T00:00:00+00:00'}))
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--event', str(event), '--config', str(config)]), expected)


class TestExistingPRRollout(unittest.TestCase):
    def test_old_pr_warns_new_pr_fails_in_event_and_sweep(self):
        with tempfile.TemporaryDirectory() as directory:
            source, config = Path(directory)/'prs.json', Path(directory)/'config.json'
            config.write_text(json.dumps({
                'warn_only': False, 'enforce_after': '2026-11-02T03:56:10Z',
                'grandfather_before': '2026-11-02T03:56:10Z',
            }))
            for created, expected in (
                ('2026-11-02T03:56:09Z', 0),
                ('2026-11-02T03:56:10Z', 1),
                ('2026-11-03T00:00:00Z', 1), (None, 1), ('invalid', 1),
                ('2026-11-01T00:00:00', 1),
            ):
                pr = {'number': 1, 'created_at': created, 'body': None,
                      'head': {'ref': 'be/old-branch'}}
                for option, payload in (('--event', {'pull_request': pr}),
                                        ('--open-prs', [pr])):
                    with self.subTest(created=created, option=option):
                        source.write_text(json.dumps(payload))
                        output = io.StringIO()
                        with contextlib.redirect_stdout(output):
                            self.assertEqual(main([option, str(source), '--config', str(config)]), expected)
                        self.assertIn('::warning::' if expected == 0 else '::error::', output.getvalue())

    def test_claude_lanes_cannot_use_each_others_prefix(self):
        for builder, wrong in (('Mac Claude', 'claude/task'),
                               ('cloud Claude', 'mac-claude/task')):
            with self.subTest(builder=builder), self.assertRaises(ValueError):
                check_prefix(parse_lane(line(builder)), wrong)
