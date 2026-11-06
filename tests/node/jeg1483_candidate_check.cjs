"use strict";
const assert=require('node:assert/strict'),F=require('../../app/v2/finder.js'),O=require('../../app/v2/opportunities.js'),R=require('../../app/v2/trade-readout.js');
let checks=0;const ok=(v,m)=>{assert.ok(v,m);checks++;};
const shape={QB:0,RB:1,WR:0,TE:0,FLEX:0,SUPERFLEX:0,BENCH:5},charts=['usatoday','fantasypros','cbs','fantasycalc'];
const row=(key,pos,ddf,mkt,proj=ddf)=>({player_key:key,name:key,pos,values:{ddf_value:ddf,ddf_value_projections:proj,usatoday:mkt,fantasypros:mkt,cbs:mkt,fantasycalc:999,espn:proj,cbsros:proj,razzball:proj}});
const mineRows=[row('101','RB',10,10),row('102','RB',9,12),row('103','WR',9,3)],theirRows=[row('201','RB',12,10),row('202','RB',4,4)];
const entry=r=>({key:r.player_key,name:r.name,pos:r.pos}),mine={id:'us',name:'Us',entries:mineRows.map(entry)},opp={id:'them',name:'Them',entries:theirRows.map(entry)};
const context=()=>({shape,rowsByKey:new Map([...mineRows,...theirRows].map(r=>[r.player_key,r])),charts,calculationSettings:{},maxSize:2,week:8});
const keys=xs=>xs.map(r=>r.player_key).sort().join(',');
async function main(){
 const legacy=F.findTrades(mineRows,theirRows,{chartKeys:charts,maxSize:2,limit:Infinity});
 ok(!legacy.trades.some(t=>keys(t.give)==='102,103'&&keys(t.receive)==='201'),'witness is discarded by legacy package/even-band gate');
 const before=JSON.stringify({mine,opp,rows:[...context().rowsByKey]});
 const result=await O.runCanonical(mine,[opp],context(),{limit:100,budgetMs:1e6});
 const recovered=result.rows.find(t=>keys(t.give)==='102,103'&&keys(t.receive)==='201');
 ok(!!recovered&&recovered.record.natural&&recovered.edge<0,'new pipeline recovers true starter fit with negative DDF package total');
 ok(result.evaluated===18&&result.totalPackages===18&&result.total===18,'every bounded subset pairing evaluated before canonical grouping');
 ok(result.rows.every(r=>r.record.questions.length===4),'every offer uses canonical entries, not legacy fit labels');
 for(const proposal of result.rows){assert.deepEqual(O.canonicalReadout(proposal).decision,proposal.record);checks++;}
 assert.deepEqual(O.canonicalReadout(recovered).decision,recovered.record);checks++;
 ok(JSON.stringify({mine,opp,rows:[...context().rowsByKey]})===before,'search leaves saved inputs unchanged');
 const alias=await O.runAll(mine,[opp],context(),{limit:100,budgetMs:1e6});assert.deepEqual(alias.rows.map(r=>r.id),result.rows.map(r=>r.id));checks++;
 const filtered=await O.runCanonical(mine,[opp],context(),{limit:1,fit:'natural',budgetMs:1e6});
 const second=await O.runCanonical(mine,[opp],context(),{limit:1,offset:1,fit:'natural',budgetMs:1e6});
 const naturals=result.rows.filter(r=>r.record.natural);ok(filtered.rows[0].id===naturals[0].id&&second.rows[0].id===naturals[1].id&&filtered.total===naturals.length,'pagination/filtering occurs after full canonical evaluation');
 ok(filtered.hasMore&&second.rows[0].rank===2,'retention is explicit pagination, never hidden candidate eligibility');
 const buy=await O.runCanonical(mine,[opp],{...context(),constraint:{direction:'buy',playerKey:'201'}},{limit:100,budgetMs:1e6});ok(buy.rows.length>0&&buy.rows.every(r=>r.record.deal.get.includes('201')),'buy target retained by stable player identity');
 const sell=await O.runCanonical(mine,[opp],{...context(),constraint:{direction:'sell',playerKey:'102'}},{limit:100,budgetMs:1e6});ok(sell.rows.length>0&&sell.rows.every(r=>r.record.deal.give.includes('102')),'sell target retained');
 const excluded=await O.runCanonical(mine,[opp],{...context(),excludedOpponentIds:['them']},{limit:10});ok(excluded.status==='missing-partners'&&excluded.rows.length===0,'saved exclusions never silently reset');
 const noMarket=await O.runCanonical(mine,[opp],{...context(),charts:['usatoday']},{limit:100,budgetMs:1e6});ok(noMarket.evaluated===18&&noMarket.counts.natural===0&&noMarket.counts.unknown===18,'insufficient markets produce honest unknown records, not silently dropped packages');
 let cancelled=false,paints=0;const interrupted=await O.runCanonical(mine,[opp],context(),{limit:100,budgetMs:0,yieldFn:async()=>{paints++;cancelled=true;},isCancelled:()=>cancelled});ok(interrupted.cancelled&&interrupted.rows.length===0&&paints>0,'cancelled computation never publishes partial answers');
 let finalCancelled=false;const superseded=await O.runCanonical(mine,[opp],context(),{limit:100,budgetMs:1e6,onProgress:p=>{if(p.phase==='complete')finalCancelled=true;},isCancelled:()=>finalCancelled});ok(superseded.cancelled&&superseded.rows.length===0,'latest-state cancellation is checked before publishing the final page');
 const projectedRows=[row('301','RB',20,12,10),row('401','RB',10,10,12)],projectedMine={id:'p-us',entries:[entry(projectedRows[0])]},projectedOpp={id:'p-them',entries:[entry(projectedRows[1])]};
 const projection=await O.runCanonical(projectedMine,[projectedOpp],{shape,rowsByKey:new Map(projectedRows.map(r=>[r.player_key,r])),charts,calculationSettings:{basis:F.PROJECTIONS_KEY},maxSize:1},{limit:10,budgetMs:1e6});ok(projection.rows[0].record.natural&&projection.rows[0].edge===-10,'selected projection gain is not prefiltered by DDF package loss');
 const tinyRows=[row('501','RB',10,12),row('601','RB',10.2,10)];
 const tiny=await O.runCanonical({id:'tiny-us',entries:[entry(tinyRows[0])]},[{id:'tiny-them',entries:[entry(tinyRows[1])]}],{shape,rowsByKey:new Map(tinyRows.map(r=>[r.player_key,r])),charts,calculationSettings:{},maxSize:1},{limit:10,budgetMs:1e6});ok(tiny.rows[0].record.natural&&tiny.rows[0].record.questions[0].value<1,'small positive starter gain survives old even-band cutoff');
 const mutable=context(),captured=await O.runCanonical(mine,[opp],mutable,{limit:100,budgetMs:1e6});const original=captured.rows[0].record;mutable.rowsByKey.get('101').values.ddf_value=999;assert.deepEqual(O.canonicalReadout(captured.rows[0]).decision,original);checks++;mutable.rowsByKey.get('101').values.ddf_value=10;
 const large=Array.from({length:60},(_,i)=>row(String(1000+i),'RB',60-i,60-i));const bounded=F.enumeratePackages(large,large.map((r,i)=>({...r,player_key:String(2000+i)})),{maxSize:4,requiredGive:['1059']});ok(bounded.bounded&&bounded.mine.rows.some(r=>r.player_key==='1059')&&F.subsetCount(bounded.mine.searched,4)<=F.MAX_SUBSETS,'existing subset bound is disclosed and explicit target survives pool trimming');
 const waiver={id:'waivers',partnerKind:'waivers',name:'Waivers',entries:theirRows.map(entry)};const pickups=await O.runCanonical(mine,[waiver],context(),{limit:100,budgetMs:1e6});ok(pickups.rows.some(r=>!r.give.length&&r.record.label==='Pickup')&&pickups.rows.every(r=>!r.record.natural),'same package pipeline supports explicit partnerKind add-only Pickup, never a fictitious manager fit');
 for(const proposal of pickups.rows){assert.deepEqual(O.canonicalReadout(proposal).decision,proposal.record);checks++;}
 ok(F.packageScore(10,1)===10&&F.packageScore(10,2)===10,'no invented score bonus for fewer than a one-for-one package');
 console.log(JSON.stringify({checks,passed:true,evaluated:result.evaluated,recovered:{id:recovered.id,record:recovered.record},groups:result.counts},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
