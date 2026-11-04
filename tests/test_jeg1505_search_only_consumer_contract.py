"""JEG-1505 non-runtime contract checks against existing Waivers Node exports.

These are test-only caller examples, not a new production API or wiring.
No browser, server, provider fetch, recommendation math or newer owner adapter
is exercised. Computed rows are explicit synthetic inputs, never derived from
universe_only. The 741-key owner board is not available in this checkout.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from pipelines.lib.searchable_identity_eligibility import build_searchable_identities

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 11, 4)
HARNESS = """
const fs = require('fs');
const W = require(process.argv[1]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
function freeze(v) {
  if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); }
  return v;
}
freeze(input);
const before = JSON.stringify(input);
const byKey = new Map(input.computedRows.map(r => [String(r.player_key), r]));
const computedBefore = JSON.stringify([...byKey.entries()]);
const kept = W.dedupe(input.entries, input.ownRoster);
const lookup = W.rowsFor(kept.kept, byKey);
const hash = W.encodeHash(input.ownRoster.map(p => p.key), kept.kept.map(p => p.key), '');
const decoded = W.decodeHash(hash);
console.log(JSON.stringify({kept, lookup, hash, decoded: {mine: decoded.mine, cands: decoded.cands},
  computedKeys: [...byKey.keys()], computedRowsUnchanged: computedBefore === JSON.stringify([...byKey.entries()]),
  sameRowReferences: lookup.rows.every(r => byKey.get(String(r.player_key)) === r),
  inputUnchanged: before === JSON.stringify(input)}));
"""


def entry(identity):
    """Test-only projection to the existing rowsFor/dedupe entry shape."""
    return {"key": str(identity["player_key"]), "name": identity["name"],
            "pos": identity["pos"], "team": identity.get("team") or ""}


def consume(entries, computed_rows=(), own_roster=()):
    """Call real, existing Node exports; never add search identities to byKey."""
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    payload = {"entries": entries, "computedRows": list(computed_rows), "ownRoster": list(own_roster)}
    result = subprocess.run([node, "-e", HARNESS, str(ROOT / "app/v2/waivers.js")],
                            input=json.dumps(payload), capture_output=True, text=True,
                            check=True, timeout=30)
    return json.loads(result.stdout)


def aiyuk():
    baked = json.loads((ROOT / "data/fixtures/current/players.json").read_text())["players"]
    matches = [p for p in baked if p["player_key"] == 568]
    if len(matches) != 1 or matches[0]["sleeper_id"] != "6803":
        raise AssertionError("committed Aiyuk canonical/provider identity changed")
    p = matches[0]
    rows = [{"player_key": p["player_key"], "full_name": p["name"], "position": p["pos"],
             "metadata": {"sleeper_id": p["sleeper_id"]}}]
    snapshot = json.loads((ROOT / "data/inputs/sleeper_identity_base.json").read_text())
    return build_searchable_identities(rows, snapshot, as_of=AS_OF)


class SearchOnlyConsumerContractTest(unittest.TestCase):
    def test_aiyuk_provider_id_is_projected_to_canonical_entry_with_unknown_price(self):
        identity = aiyuk()["identities"][0]
        self.assertEqual((identity["player_key"], identity["sleeper_id"]), (568, "6803"))
        self.assertEqual(identity["pricing_status"], "unknown")
        self.assertTrue(identity["selectable"])
        self.assertNotIn("values", identity)
        self.assertNotIn("espn_ros", identity)
        projected = entry(identity)
        self.assertEqual(projected["key"], "568")
        self.assertNotEqual(projected["key"], identity["sleeper_id"])
        out = consume([projected])
        self.assertEqual(out["decoded"]["cands"], ["568"])
        self.assertEqual(out["lookup"]["gone"], [projected])

    def test_search_only_identity_never_enlarges_supplied_computed_membership(self):
        identity = entry(aiyuk()["identities"][0])
        # Synthetic priced control, not a price/projection assigned to Aiyuk.
        computed = {"player_key": 700001, "name": "Synthetic Priced Control", "pos": "WR",
                    "team": "", "values": {"ddf_value": 17.25, "espn": None}}
        control = entry(computed)
        out = consume([identity, control], [computed])
        self.assertEqual(out["computedKeys"], ["700001"])
        self.assertEqual(out["lookup"], {"rows": [computed], "gone": [identity]})
        self.assertTrue(out["computedRowsUnchanged"])
        self.assertTrue(out["sameRowReferences"])
        self.assertTrue(out["inputUnchanged"])

    def test_rostered_aiyuk_is_removed_only_after_upstream_canonical_resolution(self):
        canonical = entry(aiyuk()["identities"][0])
        out = consume([canonical], own_roster=[canonical])
        self.assertEqual(out["kept"], {"kept": [], "onRoster": 1, "repeats": 0})
        self.assertEqual(out["lookup"], {"rows": [], "gone": []})
        # The existing consumer does not translate provider IDs. Passing 6803
        # bypasses own-roster deduplication, proving resolution is upstream.
        raw_provider = {**canonical, "key": "6803"}
        raw = consume([raw_provider], own_roster=[canonical])
        self.assertEqual(raw["kept"]["onRoster"], 0)
        self.assertEqual(raw["lookup"], {"rows": [], "gone": [raw_provider]})

    def test_other_team_ownership_is_a_caller_filter_not_existing_dedupe_behavior(self):
        owned_elsewhere = entry(aiyuk()["identities"][0])
        free = {"key": "700002", "name": "Synthetic Free Agent", "pos": "WR", "team": ""}
        candidates = [owned_elsewhere, free]
        unfiltered = consume(candidates)
        self.assertEqual(unfiltered["kept"]["kept"], candidates)
        # Proposed caller responsibility demonstrated locally, not a wired
        # production filter: resolve canonical IDs, then exclude other owners
        # before constructing the candidate list passed to this interface.
        other_team_keys = {"568"}
        caller_filtered = [p for p in candidates if p["key"] not in other_team_keys]
        filtered = consume(caller_filtered)
        self.assertEqual(filtered["decoded"]["cands"], ["700002"])
        self.assertNotIn("568", filtered["decoded"]["cands"])

    def test_unresolved_retained_keys_stay_gone_without_fabricated_rows(self):
        first = entry(aiyuk()["identities"][0])
        canonical = [{"player_key": 700003, "full_name": "Synthetic Long Inactive FA",
                      "position": "WR", "active": False, "metadata": {"sleeper_id": "test-fa"}}]
        snapshot = {"by_sleeper_id": {"test-fa": {"pos": "WR", "active": False,
                                                "team": None, "last_news": None}}}
        retained = build_searchable_identities(canonical, snapshot, as_of=AS_OF)
        second = entry(retained["identities"][0])
        self.assertEqual(retained["eligible_player_keys"], [700003])
        out = consume([first, second, first])
        self.assertEqual(out["kept"]["repeats"], 1)
        self.assertEqual(out["lookup"], {"rows": [], "gone": [first, second]})
        self.assertEqual(out["computedKeys"], [])
        self.assertEqual(out["decoded"]["cands"], ["568", "700003"])

    def test_lifecycle_preserves_identity_and_roundtrips_same_key_after_return(self):
        canonical = [{"player_key": 700004, "full_name": "Synthetic Returning Player",
                      "position": "WR", "metadata": {"sleeper_id": "test-return"}}]
        retired = {"player_key": 700004, "kind": "retired", "date": "2024-01-01",
                   "source": "https://example.invalid/retirement"}
        returned = {"player_key": 700004, "kind": "returned", "date": "2026-01-01",
                    "source": "https://example.invalid/return"}
        phases = [build_searchable_identities(canonical, {}, events, as_of=AS_OF)
                  for events in ([], [retired], [retired, returned])]
        decoded = []
        for phase in phases:
            self.assertEqual([p["player_key"] for p in phase["identities"]], [700004])
            identity = phase["identities"][0]
            self.assertEqual(identity["sleeper_id"], "test-return")
            self.assertEqual(identity["pricing_status"], "unknown")
            selected = [entry(p) for p in phase["identities"] if p["selectable"]]
            out = consume(selected)
            self.assertEqual(out["lookup"]["rows"], [])
            decoded.append(out["decoded"]["cands"])
        self.assertEqual(decoded, [["700004"], [], ["700004"]])
        self.assertEqual(phases[1]["identities"][0]["lifecycle_history"], [retired])
        self.assertEqual(phases[2]["identities"][0]["lifecycle_history"], [retired, returned])


if __name__ == "__main__":
    unittest.main()
