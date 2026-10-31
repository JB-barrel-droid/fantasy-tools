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
