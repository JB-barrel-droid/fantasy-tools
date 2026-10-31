"""JEG-1219: saved-team choices retain IDs, duplicates and empty rosters."""
import subprocess
import unittest
from pathlib import Path


class FinderSavedTeamTest(unittest.TestCase):
    def test_choices_do_not_resolve_names_or_mutate_the_workspace(self):
        script = """
const assert = require('node:assert/strict');
const F = require('./app/v2/finder.js');
const W = require('./app/v2/workspace.js');
let ws = W.newWorkspace({id:'league'});
ws = W.ops.addTeam(ws, 'Duplicate', {id:'one',entries:[{key:'1', name:'Player'}]});
ws = W.ops.addTeam(ws, 'Duplicate', {id:'two',entries:[]});
ws = W.ops.setMyTeam(ws,'one');
const original = JSON.stringify(ws);
const choices = F.savedTeamChoices(ws);
assert.deepEqual(choices.map(c=>c.id), ['one','two']);
assert.notEqual(choices[0].label, choices[1].label);
assert.match(choices[1].label, /0 players/);
assert.match(choices[0].label, /Your team/);
assert.equal(JSON.stringify(ws), original);
ws = W.ops.renameTeam(ws, 'two', 'Renamed');
assert.equal(F.savedTeamChoices(ws)[1].id, 'two');
assert.match(F.savedTeamChoices(ws)[1].label, /Renamed/);
ws = W.ops.removeTeam(ws, 'one');
assert.deepEqual(F.savedTeamChoices(ws).map(c=>c.id), ['two']);
assert.deepEqual(F.savedTeamChoices(W.newWorkspace()), []);
"""
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
