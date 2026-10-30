"""JEG-1213 summary fields preserve the displayed numbers and missing data."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class SummaryFieldsTest(unittest.TestCase):
    def test_every_summary_field_and_missing_values(self):
        code = r'''
const assert = require('node:assert/strict');
const T = require('./app/v2/team-summary.js');
const team = {name:'Team Alpha', rank:{fund:1,market:2,proj:3}, fund:{rosterValue:10.049,starterValue:8,benchValue:2},market:null,proj:{rosterValue:12,starterValue:9,benchValue:3},higher:[{name:'Kyren',gap:3.2}],lower:[],under:[{name:'Warren',gap:4}],over:[],strengths:[{text:'RB allocation above median'}],weaknesses:[],thinBench:null,positions:{RB:{have:4,range:'3–4',status:'over',starters:8,median:7}}};
const fields = T.summaryFields('fund');
for (const c of T.summaryColumns('fund')) assert.ok(fields.some(f => f.id === c.id));
for (const id of ['strengths','weaknesses','allocationQB','allocationRB','allocationWR','allocationTE','rosterP','starterP','benchP']) assert.ok(fields.some(f=>f.id===id),id);
assert.equal(T.summaryFieldText(team,fields.find(f=>f.id==='rosterF')),'10.0');
assert.equal(T.summaryFieldMatches(team,{field:'rosterF',op:'gte',value:'10.01'},'fund'),false,'filter uses shown value');
assert.equal(T.summaryFieldMatches(team,{field:'rosterF',op:'lte',value:'10'},'fund'),true);
assert.equal(T.summaryFieldMatches(team,{field:'starterM',op:'gte',value:'0'},'fund'),false,'missing never zero');
assert.equal(T.summaryFieldMatches(team,{field:'starterM',op:'missing'},'fund'),true);
assert.equal(T.summaryFieldMatches(team,{field:'starterM',op:'present'},'fund'),false);
assert.equal(T.summaryFieldText(team,fields.find(f=>f.id==='starterM')),'—');
assert.equal(T.summaryFieldMatches(team,{field:'under',op:'contains',value:'wArReN'},'fund'),true);
assert.equal(T.summaryFieldMatches(team,{field:'team',op:'notContains',value:'alpha'},'fund'),false);
assert.equal(T.summaryFieldMatches(team,{field:'strengths',op:'contains',value:'RB'},'fund'),true);
assert.equal(T.summaryFieldMatches(team,{field:'allocationRB',op:'contains',value:'4 counted'},'fund'),true);
assert.equal(T.summaryFieldMatches(team,{field:'rank',op:'eq',value:'2'},'market'),true,'ranking basis follows team summary');
assert.equal(T.summaryFieldMatches(team,{field:'altRank',op:'eq',value:'1'},'market'),true);
assert.equal(T.summaryFieldMatches(team,{field:'unknown',op:'gte',value:'100'},'fund'),true,'old field ignored');
console.log('all summary field assertions passed');
'''
        run = subprocess.run(['node', '-e', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

if __name__ == '__main__':
    unittest.main()
