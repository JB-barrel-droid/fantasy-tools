"""Real offline build: setting coverage, missing inputs, retention and byte stability."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipelines'))
from build_site_waiver_boards import publish
from lib.waiver_board import validate


class SiteBoards(unittest.TestCase):
    def test_build_missing_weekly_is_valid_and_stable(self):
        # Use the real identity/reference inputs, but no weekly source files.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            dist = Path(tmp) / 'dist'
            for name in ('players_identity_snapshot.json', 'player_aliases.json'):
                path = root / 'data/inputs' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / 'data/inputs' / name).read_bytes())
            (root / 'app').symlink_to(ROOT / 'app', target_is_directory=True)
            (root / 'data/fixtures').symlink_to(ROOT / 'data/fixtures', target_is_directory=True)
            archive = root / 'data/weekly'
            archive.mkdir()
            (archive / 'waiver-board-wk7-sentinel.json').write_text('prior board')
            args = (root, dist, 'tv-test', '2026-10-31T12:00:00Z')
            manifest = publish(*args)
            target = dist / 'data/weekly'
            expected = {(s, t, sf) for s in ('standard', 'half_ppr', 'ppr')
                        for t in (8, 10, 12, 14) for sf in (0, 1)}
            self.assertEqual(len(manifest['boards']), 24)
            self.assertEqual({(e['setting']['scoring'], e['setting']['teams'],
                              e['setting']['superflex']) for e in manifest['boards']}, expected)
            self.assertEqual(manifest['build_tag'], 'tv-test')
            self.assertEqual(json.loads((target / 'waiver-boards.json').read_text()), manifest)
            self.assertEqual((target / 'waiver-board-wk7-sentinel.json').read_text(), 'prior board')
            for entry in manifest['boards']:
                payload = (target / entry['file']).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry['sha256'])
                doc = json.loads(payload)
                self.assertEqual(validate(doc), [])
                self.assertFalse(doc['sources']['points']['enabled'])
                self.assertTrue(doc['sources']['points']['disabled_reason'])
            archive_bytes = (archive / 'waiver-boards-wk8.json.gz').read_bytes()
            before = {p.name: p.read_bytes() for p in target.glob('*.json')}
            publish(*args)
            self.assertEqual(archive_bytes, (archive / 'waiver-boards-wk8.json.gz').read_bytes())
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.glob('*.json')})

            # A new week's build starts with an empty dist. It must recover the
            # exact previous board and manifest bytes from the committed gzip.
            clean_dist = Path(tmp) / 'clean-dist'
            next_manifest = publish(root, clean_dist, 'tv-next', '2026-11-03T12:00:00Z')
            clean_target = clean_dist / 'data/weekly'
            self.assertEqual(next_manifest['board_week'], 9)
            for entry in manifest['boards']:
                self.assertEqual((clean_target / entry['file']).read_bytes(), before[entry['file']])
            previous_manifest = 'waiver-boards-wk8.json'
            self.assertEqual((clean_target / previous_manifest).read_bytes(), before[previous_manifest])
            self.assertEqual((archive / 'waiver-boards-wk8.json.gz').read_bytes(), archive_bytes)
            self.assertEqual(json.loads((clean_target / 'waiver-boards.json').read_text()), next_manifest)
            for entry in next_manifest['boards']:
                payload = (clean_target / entry['file']).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry['sha256'])
                self.assertEqual(validate(json.loads(payload)), [])
