"""JEG-1251: the JEG-1198 research joins never read the alias table, whatever the environment says.

tools/research/ros_rank_keys.py claims its player_key joins come from stored fixtures only.
player_aliases.load() reads Supabase public.player_name_aliases whenever credentials are set
and PLAYER_ALIASES_SOURCE is anything but "json", so a pre-set value such as "supabase" or ""
must be overwritten, not kept. These tests import the helper under a conflicting value and
dummy credentials with every network entry point replaced by a spy that records and refuses
the call. No real read is made: the dummy host is never contacted.
"""
from __future__ import annotations

import http.client
import os
import importlib
import socket
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "tools" / "research"
LIB = ROOT / "pipelines" / "lib"
FRESH = ("ros_rank_keys", "player_aliases", "canonical_players")
DUMMY = {"SUPABASE_URL": "https://dummy.invalid", "SUPABASE_SERVICE_KEY": "dummy-not-a-key"}


class _Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, name):
        def refuse(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError(f"network call attempted: {name}")
        return refuse


def _purge():
    for name in FRESH:
        sys.modules.pop(name, None)


class OfflineAliasSource(unittest.TestCase):
    def setUp(self):
        _purge()
        for p in (str(RESEARCH), str(LIB)):
            if p not in sys.path:
                sys.path.insert(0, p)
        self.spy = _Spy()
        self.patches = [
            mock.patch.object(urllib.request, "urlopen", self.spy("urllib.request.urlopen")),
            mock.patch.object(socket, "create_connection", self.spy("socket.create_connection")),
            mock.patch.object(socket.socket, "connect", self.spy("socket.socket.connect")),
            mock.patch.object(http.client.HTTPConnection, "connect", self.spy("HTTPConnection.connect")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        _purge()

    def test_spy_catches_the_table_read(self):
        # Control: without the helper, these settings make player_aliases try the table.
        with mock.patch.dict("os.environ", {**DUMMY, "PLAYER_ALIASES_SOURCE": "supabase"}):
            player_aliases = importlib.import_module("player_aliases")
            with self.assertRaises(AssertionError):
                player_aliases.fetch_curated_rows()
        self.assertEqual(self.spy.calls, ["urllib.request.urlopen"])

    def test_conflicting_source_is_overwritten(self):
        for given in ("supabase", "", "JSON-ish"):
            with self.subTest(given=given):
                _purge()
                self.spy.calls.clear()
                with mock.patch.dict("os.environ", {**DUMMY, "PLAYER_ALIASES_SOURCE": given}):
                    K = importlib.import_module("ros_rank_keys")
                    self.assertIsNotNone(K.pk("Patrick Mahomes", "QB", "probe"))
                    prov = K.provenance()["alias_list"]
                self.assertEqual(self.spy.calls, [])
                self.assertEqual(prov["loaded_from"], "json")
                self.assertGreater(prov["entries_loaded"], 0)
                self.assertEqual(len(prov["entries_sha256"]), 64)

    def test_unset_source_is_offline_too(self):
        with mock.patch.dict("os.environ", DUMMY):
            os.environ.pop("PLAYER_ALIASES_SOURCE", None)
            K = importlib.import_module("ros_rank_keys")
            self.assertEqual(K.provenance()["alias_list"]["loaded_from"], "json")
        self.assertEqual(self.spy.calls, [])

    def test_stops_if_the_list_came_from_elsewhere(self):
        # A list already cached from the table (e.g. imported earlier in the process) is refused.
        with mock.patch.dict("os.environ", {"PLAYER_ALIASES_SOURCE": "json"}):
            player_aliases = importlib.import_module("player_aliases")
            player_aliases.load()
            player_aliases._loaded_from = "supabase"
            with self.assertRaises(SystemExit):
                importlib.import_module("ros_rank_keys")
        self.assertEqual(self.spy.calls, [])


if __name__ == "__main__":
    unittest.main()
