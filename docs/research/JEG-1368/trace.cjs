// Read-only, three scoring trace using the same engine/input builder as get-values.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const read = p => JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const ValueModel = require(path.join(root,'app/trade-value-chart/assets/value-model.js'));
const {mapLeague} = require(path.join(root,'supabase/functions/get-values/league.ts'));
const {planWeek,buildPipelineInput} = require(path.join(root,'supabase/functions/get-values/pipeline.ts'));
const detail = read('data/fixtures/current/comparison-sources-data.json');
const bundle = {detail, players:read('data/fixtures/current/players.json').players, ValueModel,
 lineupConfig:read('config/lineup_parameters.json'), history:null};
const names = ['josh allen','bijan robinson','jahmyr gibbs','jamarr chase','brock bowers'];
const out = {};
for(const scoring of ['standard','half_ppr','ppr']) {
 const mapped = mapLeague({scoring,teams:12},bundle.lineupConfig);
 const plan = planWeek(bundle,mapped,null,'2026-10-30');
 if(!plan.ok) throw new Error(JSON.stringify(plan));
 const input = buildPipelineInput(bundle,mapped,plan);
 const result = ValueModel.runValuePipeline(input);
 const factor = result.sources.fantasycalc.indexedFactor;
 const players = {};
 for(const name of names) {
  const key = detail.player_keys[name];
  if(!key) throw new Error('Missing sample '+name);
  const native = input.sources.fantasycalc.values[key];
  const indexed = result.rows[key].indexed.fantasycalc;
  if(Math.abs(indexed-native*factor)>1e-9) throw new Error('factor mismatch');
  players[name] = {key,native,indexed,display:Number(indexed.toFixed(1))};
 }
 out[scoring] = {factor,players};
}
console.log(JSON.stringify(out,null,2));
