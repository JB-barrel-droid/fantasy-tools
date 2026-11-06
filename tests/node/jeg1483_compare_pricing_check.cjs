"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs');
const TC=require('../../app/v2/trade-context.js'),F=require('../../app/v2/finder.js'),R=require('../../app/v2/trade-readout.js'),O=require('../../app/v2/opportunities.js');
const V=require('../../app/trade-value-chart/assets/value-model.js'),PV=require('../../app/v2/roster-provenance-transitions.js');
let checks=0;const eq=(a,b,m)=>{assert.deepEqual(a,b,m);checks++;},ok=(v,m)=>{assert.ok(v,m);checks++;};
async function main(){
 for(const name of ['uso','charlotte']){
  const doc=JSON.parse(fs.readFileSync(`tests/fixtures/league_levels/${name}.json`,'utf8'));
  const shape={QB:1,RB:2,WR:doc.roster_slots.WR,TE:1,FLEX:1,SUPERFLEX:0,BENCH:doc.setting.bench_per_team};
  const now=Date.parse('2026-10-29T12:00:00Z'),teams=doc.league.teams.map(t=>({id:t.id,name:t.id,entries:t.players.filter(p=>p.key).map(p=>({...p,key:String(p.key),pos:doc.players[p.key]?.pos||p.pos})),provenance:PV.replaceFromSource(null,{now,unresolved:0,coverage:PV.COVERAGE.WHOLE_ROSTER})}));
  const ws={id:'complete-'+name,teams,myTeamId:doc.mine,ui:{}};const savedBefore=JSON.stringify(ws);
  const runs=new Map(),level=({level='modeled',rostered=[],reserve=[]}={})=>{
   const sig=JSON.stringify([level,rostered,reserve]);if(runs.has(sig))return runs.get(sig);
   const out=V.runValuePipeline({setting:{...doc.setting,...(level==='modeled'?{}:{league_rostered:rostered,league_reserve:reserve,bench_level:level})},players:doc.players,sources:doc.inputs});
   const rows=Object.entries(out.rows).map(([key,r])=>({player_key:key,name:doc.players[key].name,pos:r.pos,ddfTier:r.tier,values:{...r.adjusted,...r.indexed,ddf_value:r.ddfByVersion.blended.value,ddf_value_charts:r.ddfByVersion.charts.value,ddf_value_projections:r.ddfByVersion.projections.value}}));
   const result={rows,allocation:Object.entries(out.allocation).map(([pos,a])=>({pos,lineup:a.starters,rostered:a.rostered,bench:a.bench})),counts:out.allocation,readout:out.benchShare};runs.set(sig,result);return result;
  };
  const C={getState:()=>({teams:12}),getRosterShape:()=>shape,getLeagueLevel:level,getAllRows:()=>level().rows,getAdjustmentWeights:()=>({allocation:level().allocation}),getBenchShareReadout:()=>level().readout};
  const mine=teams.find(t=>t.id===doc.mine),theirs=teams.find(t=>t.id!==doc.mine),deal={give:[mine.entries.find(e=>e.pos==='RB').key],get:[theirs.entries.find(e=>e.pos==='WR').key]};
  const keys=TC.pricingKeys({mine:mine.entries,theirs:theirs.entries,deal});
  const p=TC.comparePricing(C,{workspace:ws,keys,now});
  eq(p.status,'ok');eq(p.pricing.mode,'league');eq(Object.keys(p.pricing.levels),['ddf','market']);
  const rawD=level({level:'ddf',rostered:p.pricing.rostered,reserve:p.pricing.reserve}),rawM=level({level:'market',rostered:p.pricing.rostered,reserve:p.pricing.reserve});
  eq(p.rows.map(r=>r.values.ddf_value),rawD.rows.map(r=>r.values.ddf_value));
  eq(p.rows.map(r=>r.values.cbs),rawM.rows.map(r=>r.values.cbs));
  ok(p.rows.some((r,i)=>r.values.ddf_value!==C.getAllRows()[i].values.ddf_value),'league pricing must discriminate modeled baseline');
  eq(p.pricing.levels.ddf,TC.levelIdentity('ddf',{...rawD,weights:rawD.readout,keys}));
  eq(p.pricing.levels.market,TC.levelIdentity('market',{...rawM,weights:rawM.readout,keys}));
  eq(p.zonesFor('cbs','ALL').bench_to_waiver,rawM.allocation.reduce((n,a)=>n+a.rostered,0)+0.5);
  const common=TC.commonFromPage({leagueQuery:`scoring=half_ppr&teams=12&roster=QB1.RB2.WR${shape.WR}.TE1.FLEX1.SF0.BN${shape.BENCH}`,sources:Object.fromEntries(F.CHART_KEYS.map(k=>[k,{available:true}]))});
  const context=TC.createContext({route:'league',workspaceId:ws.id,common,mine:TC.savedTeam(ws,mine.id),opponents:[TC.savedTeam(ws,theirs.id)],deal,pricing:p.pricing});
  const transfer=TC.decodeTransfer(TC.encodeTransfer(TC.toTransfer(context)));
  const receivedPricing=TC.comparePricing(C,{transfer,workspace:{...ws,ui:{leagueRosters:false}},keys,now});
  eq(receivedPricing.pricing,p.pricing,'carry selected level beats unrelated local toggle');
  const received=TC.receive(transfer,{route:'compare',common,pricing:receivedPricing.pricing,ws});eq(received.status,'ok');
  const sourceInfo=[...F.CHART_KEYS,'ddf_value','ddf_value_projections'].map(key=>({key,available:true}));
  const env={rowsByKey:p.rowsByKey,shape,chartKeys:F.CHART_KEYS,sourceInfo,calculationSettings:{}};
  const find=R.build(R.inputFromContext(context,env,{context:TC})),compare=R.build(R.inputFromContext(received.context,{...env,rowsByKey:receivedPricing.rowsByKey},{context:TC}));
  eq(R.summary(compare),R.summary(find),'complete Find and Compare canonical evidence equal');
  eq(compare.sides.mine.ddf.totalDelta,find.sides.mine.ddf.totalDelta);
  eq(compare.sides.mine.market.totalDelta,find.sides.mine.market.totalDelta);
  eq(p.rows.map(r=>r.ddfTier),rawD.rows.map(r=>r.ddfTier));
  const result=await O.runCanonical(mine,[theirs],{rowsByKey:p.rowsByKey,shape,charts:F.CHART_KEYS,sourceInfo,calculationSettings:{},maxSize:1},{limit:2,budgetMs:1e6});
  ok(result.evaluated>0);for(const row of result.rows){
   const ctx=TC.withChanges(context,{deal:{give:row.give.map(r=>String(r.player_key)),get:row.receive.map(r=>String(r.player_key))}});
   eq(R.build(R.inputFromContext(ctx,env,{context:TC})).decision,row.record,'native pricing search and opened Review same');
  }
  const off=TC.comparePricing(C,{workspace:{...ws,ui:{leagueRosters:false}},keys,now});eq(off.pricing.mode,'modeled');eq(off.rows,C.getAllRows());
  const partial=TC.comparePricing(C,{workspace:{...ws,teams:teams.slice(0,-1)},keys,now});eq(partial.pricing.mode,'modeled');ok(partial.check.reasons.includes('team_count'));
  const stale=TC.comparePricing(C,{workspace:ws,keys,now:now+8*86400000});eq(stale.pricing.mode,'modeled');
  const malformed={...transfer,pricing:{mode:'league',levels:{}}};eq(TC.comparePricing(C,{transfer:malformed,keys}).status,'hold');
  const noLevel=TC.comparePricing({...C,getLeagueLevel:()=>null},{transfer,keys});eq(noLevel.status,'hold');ok(!noLevel.rows.length,'no modeled fallback');
  const changedEngine={...C,getLeagueLevel:args=>{const x=level(args);return args.level==='market'?{...x,readout:{...x.readout,overall:0.999}}:x;}};
  const changed=TC.comparePricing(changedEngine,{transfer,keys});eq(TC.receive(transfer,{route:'compare',common,pricing:changed.pricing,ws}).status,'hold');
  const broken={...C,getLeagueLevel:args=>{const x=level(args);return args.level==='market'?{...x,rows:x.rows.slice(1)}:x;}};eq(TC.comparePricing(broken,{transfer,keys}).status,'hold');
  eq(JSON.stringify(ws),savedBefore,'pricing and carry leave saved league unchanged');
  
 }
 console.log(JSON.stringify({passed:true,checks,leagues:['uso','charlotte']}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
