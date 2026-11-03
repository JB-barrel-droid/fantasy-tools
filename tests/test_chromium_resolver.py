"""Browser selection must never launch the desktop Chrome app (JEG-1475)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _render_env


class ChromiumResolverTest(unittest.TestCase):
    def test_mac_cache_precedes_desktop_chrome(self):
        with tempfile.TemporaryDirectory() as home:
            shell = Path(home) / 'Library/Caches/ms-playwright/chromium_headless_shell-999/chrome-headless-shell-mac-arm64/chrome-headless-shell'
            shell.parent.mkdir(parents=True)
            shell.touch()
            original_exists = Path.exists
            def exists(path):
                return str(path) == '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' or original_exists(path)
            with patch.dict(os.environ, {'HOME': home, 'CHROMIUM_PATH': ''}), patch.object(Path, 'exists', exists), patch('subprocess.run', side_effect=FileNotFoundError):
                self.assertEqual(_render_env.chromium_executable(), str(shell))

    def test_explicit_override_and_default(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {'HOME': home, 'CHROMIUM_PATH': '/explicit/browser'}), patch.object(_render_env, '_registered_headless_shell', return_value=None):
            self.assertEqual(_render_env.chromium_executable(), '/explicit/browser')
            os.environ.pop('CHROMIUM_PATH')
            self.assertIsNone(_render_env.chromium_executable())

    def test_active_registry_precedes_other_cached_versions(self):
        with tempfile.TemporaryDirectory() as home:
            shell = Path(home) / 'active-shell'
            shell.touch()
            with patch.dict(os.environ, {'HOME': home, 'CHROMIUM_PATH': ''}), patch.object(_render_env, '_registered_headless_shell', return_value=shell):
                self.assertEqual(_render_env.chromium_executable(), str(shell))
