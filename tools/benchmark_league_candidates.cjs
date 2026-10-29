// Usage: node --expose-gc tools/benchmark_league_candidates.cjs 2 [capped]
// Repeat with 3 or 4; capped simulates the old early truncation for comparison.
// Synthetic 12-team, 15-player/roster comparison, not Jeremy's saved league.
'use strict';
const {performance}=require('node:perf_hooks');
const F=require('../app/v2/finder.js');
const O=require('../app/v2/opportunities.js');
const size=Number(process.argv[2]||2), limit=process.argv[3]==='capped'?10:Infinity;
let seed=4811129; const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
const CH=F.CHART_KEYS;
const positions=['QB','QB','RB','RB','RB','RB','RB','WR','WR','WR','WR','WR','WR','TE','TE'];
const rows=[]; const teams=Array.from({length:12},(_,t)=>({id:'t'+t,name:'Team '+t,entries:positions.map((pos,j)=>{
 const key=`t${t}p${j}`;
 // Each position has starter/bench tiers; independent chart variation around shared player value.
 const at=positions.slice(0,j).filter(p=>p===pos).length;
 const base=(pos==='QB'?16:pos==='TE'?19:31)*Math.pow(.72,at)*(0.8+0.4*random());
 const chart=CH.map(()=>Math.round(base*(.65+.7*random())*10)/10);
 const ddf=chart.reduce((a,b)=>a+b)/chart.length;
 const values={...Object.fromEntries(CH.map((k,i)=>[k,chart[i]])),ddf_value:ddf,ddf_value_charts:ddf,ddf_value_projections:ddf*(.6+.8*random())};
 rows.push({player_key:key,name:key,pos,values});return {key,name:key,pos};
})}));
const ctx={rowsByKey:new Map(rows.map(r=>[r.player_key,r])),shape:{QB:1,RB:2,WR:2,TE:1,FLEX:1,SUPERFLEX:0},expected:F.expectedDepth([{pos:'QB',rostered:24,lineup:12,bench:12},{pos:'RB',rostered:60,lineup:30,bench:30},{pos:'WR',rostered:72,lineup:30,bench:42},{pos:'TE',rostered:24,lineup:12,bench:12}],12),weights:{overall:.3,QB:.2,RB:.3,WR:.3,TE:.25},charts:CH,market:CH,maxSize:size,keepMine:true,keepTheirs:true,findTrades:(mine,theirs,opts)=>F.findTrades(mine,theirs,{...opts,limit})};

(async()=>{
 const cache=O.createCache();
 const timing=[];let previous=performance.now();
 const mem=()=>({heapUsedMiB:+(process.memoryUsage().heapUsed/1048576).toFixed(1),maxRSSMiB:+(process.resourceUsage().maxRSS/1024).toFixed(1)});
 const start=previous;
 const cold=await O.runAll(teams[0],teams.slice(1),ctx,{cache,budgetMs:12,yieldFn:()=>{const now=performance.now();timing.push(now-previous);previous=now;return new Promise(resolve=>setImmediate(resolve));}});
 const coldEnd=performance.now();timing.push(coldEnd-previous);
 const coldMem=mem();if(global.gc)global.gc();const retainedColdMem=mem();
 const warmStart=performance.now();const warm=await O.runAll(teams[0],teams.slice(1),ctx,{cache});const warmMs=performance.now()-warmStart;
 const sort=[...timing].sort((a,b)=>a-b);
 const equality=cold.rows.length===warm.rows.length && cold.rows.every((r,i)=>r.id===warm.rows[i].id&&r.edge===warm.rows[i].edge&&r.overall===warm.rows[i].overall);
 console.log(JSON.stringify({synthetic:true,teams:12,playersPerTeam:15,size,mode:limit===Infinity?'complete':'legacy-cap',coldMs:+(coldEnd-start).toFixed(1),warmMs:+warmMs.toFixed(1),coldRows:cold.rows.length,warmRows:warm.rows.length,coldComputed:cold.computed,warmReused:warm.reused,warmEquality:equality,yields:timing.length-1,maxGapMs:+sort.at(-1).toFixed(1),p95GapMs:+sort[Math.floor(sort.length*.95)].toFixed(1),coldMem,retainedColdMem,finalMem:mem()}));
})();
