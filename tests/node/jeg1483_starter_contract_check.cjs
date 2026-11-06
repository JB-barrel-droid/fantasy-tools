"use strict";
const assert=require('node:assert/strict');
const F=require('../../app/v2/finder.js'),R=require('../../app/v2/trade-readout.js');
const pubs=['usatoday','fantasypros','cbs'],all=[...pubs,'fantasycalc'];
const shape={QB:0,RB:1,WR:0,TE:0,FLEX:0,SUPERFLEX:0,BENCH:3};
const row=(key,ddf,market,proj)=>({player_key:key,name:key,pos:'RB',values:{ddf_value:ddf,ddf_value_projections:proj,usatoday:market,fantasypros:market,cbs:market,fantasycalc:1000,espn:proj,cbsros:proj,razzball:proj}});
function input(){return {shape,chartKeys:all,calculationSettings:{},mine:{rows:[row('m',10,12,10),row('mb',3,3,3)]},theirs:{rows:[row('t',12,10,1),row('tb',4,4,4)]},give:['m'],receive:['t']};}
const clone=x=>JSON.parse(JSON.stringify(x));let checks=0;const ok=(value,msg)=>{assert.ok(value,msg);checks++;};
ok(R.marketQuote(row('fc',10,12,10),{market:'fantasycalc'}).value===1000,'explicit FantasyCalc works with the default available-key argument');
const ancestry=R.marketQuote({...row('zero',10,0,10),estimated:{cbs:'Existing fill-in'},missingReasons:{usatoday:'Not on published list'}},{market:'published-average'}).inputs;
ok(ancestry.find(s=>s.key==='cbs').status==='estimated'&&ancestry.find(s=>s.key==='usatoday').status==='unlisted_zero'&&ancestry.find(s=>s.key==='fantasypros').status==='zero_listing_unknown','reuse original estimated/unlisted/unknown-zero provenance without inventing listing');
for(let count=0;count<=3;count++){
  const q=R.marketQuote(row('x',10,0,10),{market:'published-average'},pubs.slice(0,count));
  ok(q.coverage.available===count&&q.coverage.total===3,'coverage exact '+count);
  ok(q.average===(count>=2?0:null),'zero is an average only with >=2 complete sources '+count);
  ok(q.fitAvailable===(count>=2),'fit gate '+count);
  ok(q.value===(count?0:null),'one published source shows its real zero '+count);
  ok(!q.sources.includes('fantasycalc'),'FantasyCalc never joins published average');
}
let x=input(),a=R.build(x),d=a.decision;
const displayBasis=R.build({...input(),ourKey:'cbs'});assert.deepEqual(displayBasis.decision,d);checks++;
ok(R.build({...input(),calculationSettings:undefined,ourKey:'cbs'}).ourKey==='cbs','released unflagged legacy basis remains unchanged');
ok(d.label==='Natural fit'&&d.questions.length===4&&d.questions.every(q=>q.pass===true),'four visible predicates alone decide Natural fit');
ok(d.questions[0].value===2&&d.questions[2].value===2,'subject-positive starter deltas');
ok(a.sides.mine.projections.starterDelta<0&&d.natural,'projections support; they do not add a fifth gate');
ok(a.views.market.coverage.text==='3 of 3'&&!a.views.market.chartKeys.includes('fantasycalc'),'complete published source set');
ok(d.questions.every(q=>q.subject&&q.scope&&q.basis&&q.aggregation&&q.sign&&q.status&&q.coverage&&'tolerance' in q),'canonical quantity metadata complete');
x=input();x.give=['mb'];x.receive=['tb'];a=R.build(x);ok(a.sides.mine.ddf.totalDelta>0&&a.decision.questions[0].value===0&&!a.decision.natural,'bench-only/package gain is not starter gain');
x=input();x.calculationSettings.basis='ddf_value_projections';a=R.build(x);ok(a.decision.questions[0].value<0&&!a.decision.natural,'selected projections basis changes starter predicate');
x=input();x.theirs.rows[0].values.usatoday=12.01;x.theirs.rows[0].values.fantasypros=12.01;x.theirs.rows[0].values.cbs=12.01;a=R.build(x);ok(a.decision.questions[2].value<0&&a.decision.questions[2].pass===false,'default their minimum is exactly zero');
x.calculationSettings.theirMinimum={tier:'noise'};a=R.build(x);ok(a.decision.questions[2].pass&&a.decision.questions[2].threshold<0&&a.decision.questions[2].tolerance===F.PROJ_FLOOR,'explicit within-noise tier uses existing floor');
x=input();x.calculationSettings.ourMinimum={tier:'custom',value:3};ok(!R.build(x).decision.questions[0].pass,'custom our minimum');x.calculationSettings.ourMinimum={tier:'any'};ok(R.build(x).decision.natural,'reversible thresholds');
x=input();x.mine.rows[0].values.ddf_value_projections=null;x.calculationSettings.basis='ddf_value_projections';a=R.build(x);ok(a.decision.questions[0].status==='unknown'&&!a.decision.natural,'missing selected projections never becomes zero');
x=input();x.chartKeys=['usatoday','fantasycalc'];a=R.build(x);ok(a.views.market.status==='unavailable'&&a.decision.questions[2].status==='unknown'&&!a.decision.natural,'one remaining published chart cannot judge default market fit');
ok(a.views.market.chartKeys[0]==='usatoday'&&R.marketQuote(x.mine.rows[0],a.decision.settings,a.views.market.chartKeys).status==='individual','single-source display remains available without an average fit judgment');
x=input();x.chartKeys=['usatoday','fantasypros'];a=R.build(x);ok(a.views.market.status==='available'&&a.views.market.coverage.text==='2 of 3'&&a.decision.natural,'two-source average works');
x=input();x.theirs.rows[0].values.cbs=null;a=R.build(x);ok(a.views.market.coverage.text==='2 of 3'&&a.views.market.chartKeys.length===2,'only complete compatible roster sources join readout');
x=input();x.mine.entries=[...x.mine.rows.map(r=>({key:r.player_key,name:r.name,pos:r.pos})),{key:'unknown',name:'Unmatched offensive player',pos:'RB'}];a=R.build(x);ok(a.decision.questions[0].status==='unknown'&&a.decision.questions[1].status==='unknown','unknown roster identities block certainty');
ok(a.decision.supporting.mine.ddf.package.status==='known'&&a.decision.supporting.mine.ddf.package.coverage.text==='1 of 1'&&a.decision.supporting.mine.ddf.package.basis==='ddf_value','known moving-player package evidence stays separate from unknown roster fit');
x=input();a=R.build(x);const before=JSON.stringify(x);const other=R.build({...clone(x),displayColumns:['cbs','fantasycalc','espn']});assert.deepEqual(a.decision,other.decision);ok(JSON.stringify(x)===before,'inputs immutable and display-only columns cannot change calculation');
x=input();x.partnerKind='waivers';x.give=[];a=R.build(x);ok(a.ready&&a.decision.label==='Pickup'&&!a.decision.natural&&a.decision.questions.slice(2).every(q=>q.status==='not_applicable'),'add-only Waivers has no manager predicates');
ok(a.decision.supporting.theirs===null,'no invented manager evidence for Waivers');
ok(a.roster.theirs===null&&Object.values(a.sides.theirs).every(s=>s===null),'Waivers has no fictitious roster limit or lineup');
x=input();x.partnerKind='waivers';x.give=[];x.theirs.rows.push({player_key:'unpriced-fa',name:'Unpriced free agent',pos:'RB',values:{ddf_value:1}});a=R.build(x);ok(a.views.market.coverage.text==='3 of 3'&&a.decision.passes,'unrelated free agents cannot remove known package sources from a pickup');
x=input();x.give=['m','m'];a=R.build(x);ok(!a.ready&&!a.decision.natural,'duplicate package identities cannot judge fit');
x=input();x.sourceInfo=F.PROJECTION_KEYS.map(key=>({key,available:false,excludedReason:'held: data check'}));x.calculationSettings.basis=F.PROJECTIONS_KEY;a=R.build(x);ok(a.decision.questions[0].status==='unknown','held projections cannot leak stale selected-basis values');
x=input();x.sourceInfo=F.PROJECTION_KEYS.map(key=>({key,available:true,excludedReason:'held: data check'}));x.calculationSettings.basis=F.PROJECTIONS_KEY;a=R.build(x);ok(a.decision.questions[0].status==='unknown','explicit hold wins over a contradictory available flag');
x=input();x.theirs.rows.push(clone(x.mine.rows[0]));a=R.build(x);ok(!a.ready&&a.decision.label==='Not judged','ambiguous player ownership cannot create a fit judgment');
x=input();x.calculationSettings.ourMinimum={tier:'custom',value:0};x.give=['mb'];x.receive=['tb'];a=R.build(x);ok(!a.decision.questions[0].pass&&a.decision.questions[0].operator==='>','custom zero exposes the strict positive predicate');
for(const market of [...pubs,'fantasycalc']){x=input();x.calculationSettings.market=market;a=R.build(x);ok(a.views.market.coverage.text==='1 of 1'&&a.views.market.chartKeys[0]===market,'explicit individual market uses named selected-source coverage, not average '+market);}
const TC=require('../../app/v2/trade-context.js'),W=require('../../app/v2/workspace.js');
const routeInput=input(),ids={m:'101',mb:'102',t:'201',tb:'202'};
routeInput.mine.id='us';routeInput.theirs.id='them';
for(const who of ['mine','theirs'])routeInput[who].rows.forEach(r=>r.player_key=ids[r.player_key]);
routeInput.give=['101'];routeInput.receive=['201'];
let ws=W.newWorkspace({id:'contract-league',name:'Contract fixture',now:1});
for(const [who,id] of [['mine','us'],['theirs','them']])ws=W.ops.addTeam(ws,id,{id,entries:routeInput[who].rows.map(r=>({key:r.player_key,name:r.name,pos:r.pos})),now:1});
ws=W.ops.setMyTeam(ws,'us');const saved=JSON.stringify(ws);
const rows=routeInput.mine.rows.concat(routeInput.theirs.rows),common=TC.commonFromPage({leagueQuery:'scoring=ppr&teams=12&roster=QB0.RB1.WR0.TE0.FLEX0.SF0.BN3'}),pricing={mode:'modeled',levels:{modeled:TC.levelIdentity('modeled',{rows})}},deal={give:['101'],get:['201']},env={common,pricing};
const pair=TC.fromPair(env,ws,{mineId:'us',theirId:'them',deal},ws.ui.finderSettings),league=TC.fromLeague({...env,deal},ws),compare=TC.fromCompare(env,ws,{give:deal.give,receive:deal.get},{mineId:'us',theirId:'them'});
const arrived=TC.receive(TC.decodeTransfer(TC.encodeTransfer(TC.toTransfer(pair))),{route:'compare',common,pricing,ws});assert.equal(arrived.status,'ok');
const oracle=R.summary(R.build(routeInput)).decision,readoutEnv={shape,chartKeys:all,calculationSettings:{},rowsByKey:new Map(rows.map(r=>[r.player_key,r]))};
ok(oracle.participants.mine==='us'&&oracle.participants.theirs==='them'&&oracle.deal.give[0]==='101'&&oracle.deal.get[0]==='201','canonical record retains explicit stable party and package identities');
for(const context of [pair,league,compare,arrived.context]){assert.deepEqual(R.summary(R.build(R.inputFromContext(context,readoutEnv,{context:TC}))).decision,oracle);checks++;}
ok(JSON.stringify(ws)===saved,'actual pair/league/Compare/transfer context adapters preserve saved rosters');
const policyCases=[];
for(const basis of [F.OUR_KEY,F.PROJECTIONS_KEY])for(const ourMinimum of [{tier:'any'},{tier:'noise'},{tier:'custom',value:0},{tier:'custom',value:3}])for(const theirMinimum of [{tier:'neutral'},{tier:'noise'},{tier:'gain'},{tier:'custom',value:-1}]){
  const spec=input();spec.calculationSettings={basis,ourMinimum,theirMinimum};const record=R.build(spec).decision;
  policyCases.push({name:JSON.stringify(spec.calculationSettings),settings:record.settings,questions:record.questions,label:record.label,natural:record.natural});
}
console.log(JSON.stringify({checks,passed:true,canonicalDefault:d,policyCases},null,2));
