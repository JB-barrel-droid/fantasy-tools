"""Daily status never borrows the identity bake's date/status or changes values."""
import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page
import pull_player_status as P

AS_OF = "2026-10-30T13:10:00+00:00"


def raw_players():
    return {str(i): {"full_name": f"Test Player {i}", "position": "WR",
                     "team": "KC" if i < 800 else None,
                     "injury_status": "Out" if i == 1 else None}
            for i in range(2500)}


class TestDailyStatus(unittest.TestCase):
    def test_snapshot_is_keyed_by_existing_id_and_dates_the_observation(self):
        raw = raw_players()
        before = copy.deepcopy(raw)
        d = P.build_snapshot(raw, AS_OF)
        self.assertEqual(raw, before)
        self.assertEqual(d["as_of"], AS_OF)
        self.assertEqual(len(d["by_sleeper_id"]), 800)
        self.assertEqual(d["by_sleeper_id"]["1"]["injury_status"], "Out")
        self.assertIsNone(d["by_sleeper_id"]["2"]["injury_status"])
        self.assertNotIn("800", d["by_sleeper_id"])

    def test_partial_or_undated_pull_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            path.write_text("previous snapshot")
            with patch.object(P, "pull_sleeper", return_value={"1": raw_players()["1"]}):
                with self.assertRaisesRegex(ValueError, "partial pull"):
                    P.main(["--out", str(path)])
            self.assertEqual(path.read_text(), "previous snapshot")
        with self.assertRaisesRegex(ValueError, "as_of"):
            P.build_snapshot(raw_players(), "2026-10-30")
        with self.assertRaisesRegex(ValueError, "team-backed"):
            raw = raw_players()
            for p in raw.values():
                p["team"] = None
            P.build_snapshot(raw, AS_OF)

    def test_page_ships_only_the_snapshot_date_and_ids_without_rebaking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            d = P.build_snapshot(raw_players(), AS_OF)
            path.write_text(json.dumps(d))
            js = build_v2_page.player_status_js(path)
            result = json.loads(js.split(" = ", 1)[1][:-2])
            self.assertEqual(result, {k: d[k] for k in ("source", "as_of", "by_sleeper_id")})
            self.assertEqual(build_v2_page.player_status_js(Path(tmp) / "missing.json"),
                             'window.TradeValueStatus = {"source":"Sleeper","as_of":null,"by_sleeper_id":{}};\n')

    def test_history_reuses_the_pull_without_another_request_or_database_write(self):
        import save_player_status_history as history
        sb = Mock()
        sb.get_all.return_value = []
        index = Mock()
        index.resolve_sleeper.return_value = (None, "unresolved")
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.json"
            raw.write_text(json.dumps(raw_players()))
            with patch.dict(sys.modules, {"sbclient": sb}), patch.object(history, "PlayerIndex", return_value=index), \
                    patch("pull_sleeper_identity.pull_sleeper", side_effect=AssertionError("second API pull")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(history.main(["--dry-run", "--from-file", str(raw),
                                               "--summary", str(Path(tmp) / "summary.json")]), 0)
            sb.post.assert_not_called()

    def test_live_status_overrides_old_row_and_expires_without_value_changes(self):
        script = r"""
const assert = require('assert');
const W = require('./app/v2/waivers.js');
const daily = {as_of:'2026-10-30T13:10:00Z', by_sleeper_id:{
  '1':{team:'KC',pos:'WR',injury_status:'Questionable'},
  '2':{team:'KC',pos:'WR',injury_status:null},
  '3':{team:'LAR',pos:'WR',injury_status:'IR'}
}};
const now = Date.parse(daily.as_of), hour = 3600000;
const fresh = W.statusFreshness(daily, now + hour);
const row = {sleeper_id:'1', name:'Player', team:'KC', pos:'WR', injury_status:'Out', values:{ddf_value:14.7}};
const before = JSON.stringify(row);
assert.equal(W.statusOf(row,fresh),'Questionable');
assert.equal(W.statusOf({...row,sleeper_id:'2'},fresh),null); // cleared status, no old Out
assert.equal(W.statusOf({...row,sleeper_id:'missing'},fresh),null);
assert.equal(W.statusOf({...row,sleeper_id:null},fresh),null);
assert.equal(W.statusOf({...row,team:''},fresh),null);
assert.equal(W.statusOf({...row,team:'PHI'},fresh),null);
assert.equal(W.statusOf({...row,pos:'TE'},fresh),null);
assert.equal(W.statusOf({...row,sleeper_id:'3',team:'LA'},fresh),'IR');
assert.equal(W.injuryNote([], {starters:[row]}, {pos:'WR'}, fresh),null);
assert.equal(JSON.stringify(row),before);
assert(fresh.label.includes('Oct 30, 13:10 UTC'));
assert(W.statusFreshness(daily,now+30*hour).shown);
assert(!W.statusFreshness(daily,now+30*hour+1).shown);
assert(!W.statusFreshness(daily,now-1).shown);
assert(!W.statusFreshness({...daily,as_of:null},now).shown);
const sun = {...daily,as_of:'2026-11-01T16:30:00Z'};
assert(W.statusFreshness(sun,Date.parse(sun.as_of)+4*hour).shown);
assert(!W.statusFreshness(sun,Date.parse(sun.as_of)+4*hour+1).shown);
assert.equal(W.statusOf(row,W.statusFreshness(daily,now+31*hour)),null);
"""
        subprocess.run(["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_daily_workflow_publishes_status_even_if_database_history_fails(self):
        # This workflow intentionally installs no packages; keep its guard
        # runnable with the same Python standard library.
        workflow = (ROOT / ".github/workflows/player-status-history.yml").read_text()
        steps = workflow.split("      - ")
        status = next(s for s in steps if "id: status\n" in s)
        publish = next(s for s in steps if "id: publish\n" in s)
        self.assertIn("pull_player_status.py", status)
        self.assertNotIn("SUPABASE", str(status))
        self.assertIn("!cancelled()", publish)
        self.assertIn("steps.status.outcome == 'success'", publish)
        self.assertIn("data/inputs/player_status.json", publish)
        dispatch = next(s for s in steps if s.startswith("name: Request validated Pages"))
        self.assertIn("refs/heads/main", dispatch)
        self.assertIn("steps.publish.outputs.pushed == 'true'", dispatch)
        self.assertIn("pages.yml/dispatches", dispatch)


if __name__ == "__main__":
    unittest.main()
