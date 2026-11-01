"""Real offline build: setting coverage, missing inputs, retention and byte stability."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipelines'))
from build_site_waiver_boards import publish, SETTINGS
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
            self.assertEqual(len(manifest['boards']), len(SETTINGS))
            self.assertEqual((target / 'waiver-board-wk7-sentinel.json').read_text(), 'prior board')
            for entry in manifest['boards']:
                doc = json.loads((target / entry['file']).read_text())
                self.assertEqual(validate(doc), [])
                self.assertFalse(doc['sources']['points']['enabled'])
                self.assertTrue(doc['sources']['points']['disabled_reason'])
            archive_bytes = (archive / 'waiver-boards-wk8.json.gz').read_bytes()
            before = {p.name: p.read_bytes() for p in target.glob('*.json')}
            publish(*args)
            self.assertEqual(archive_bytes, (archive / 'waiver-boards-wk8.json.gz').read_bytes())
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.glob('*.json')})
