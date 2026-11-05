// JEG-1183: portable lifecycle regressions and discriminating controls.
// mount ownership and completion
{
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {createRequire}=require('node:module');
const ROOT=require('node:path').resolve(__dirname,'../..'),SOURCE=ROOT;
const panelSource=fs.readFileSync(SOURCE+'/app/v2/trade-package-panel.js','utf8');
const leagueSource=fs.readFileSync(SOURCE+'/app/v2/league.js','utf8');
const {makeCase}=require(ROOT+'/tests/jeg1183_package_cases.js');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.listeners={};this.className='';this.textContent='';this.classList={add:(...ns)=>{this.className+=' '+ns.join(' ');}};}
  setAttribute(k,v){this.attrs[k]=v;if(k==='class')this.className=v;if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;}
  removeAttribute(k){delete this.attrs[k];}
  append(...kids){for(const k of kids){this.children.push(k);if(k instanceof Element)k.parent=this;}}
  replaceChildren(...kids){for(const k of this.children)if(k instanceof Element)k.parent=null;this.children=[];this.append(...kids);}
  get nextSibling(){return this.parent?.children[this.parent.children.indexOf(this)+1]||null;}
  before(node){this.beforeCalls=(this.beforeCalls||0)+1;if(node.parent){const i=node.parent.children.indexOf(node);node.parent.children.splice(i,1);}const i=this.parent.children.indexOf(this);this.parent.children.splice(i,0,node);node.parent=this.parent;}
  addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);}
  removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(f=>f!==fn);}
  click(){if(!this.disabled)for(const fn of [...this.listeners.click||[]])fn();}
}
global.document={createElement:t=>new Element(t)};
const walk=e=>[e,...e.children.filter(c=>c instanceof Element).flatMap(walk)];
const cls=(e,c)=>walk(e).filter(n=>n.className.split(/\s+/).includes(c));
function loadPanel(source=panelSource){const s={module:{exports:{}},require:createRequire(ROOT+'/app/v2/trade-package-panel.js'),document:global.document};vm.runInNewContext(source,s);return s.module.exports;}
function mounted(source=panelSource){const P=loadPanel(source),element=new Element('section'),api=P.mount(element);return {P,element,api,button:walk(element).find(x=>x.tag==='button')};}
const snap=()=>({status:'ready',...makeCase()});
function beforeMount(source=panelSource){const P=loadPanel(source),parent=new Element('main'),target=new Element('section');parent.append(target);const a=P.mountBefore(target),b=P.mountBefore(target);assert.equal(parent.children.filter(n=>n.id==='v2LgPackage').length,1);assert.equal(a,b);assert.equal(target.beforeCalls,1,'idempotent remount must not move the already-positioned DOM');}
function sameMount(source=panelSource){const p=mounted(source),s=snap();p.api.update(s);p.button.click();const before=cls(p.element,'pcp-trade')[0],again=p.P.mount(p.element);assert.equal(again,p.api);assert.equal(cls(p.element,'pcp-trade')[0],before);assert.equal(p.button.listeners.click.length,1);}
function destroyed(source=panelSource){const p=mounted(source);p.api.update(snap());p.button.click();p.api.destroy();p.api.destroy();assert.equal(p.button.listeners.click.length,0);assert.equal(cls(p.element,'pcp-trade').length,0);assert.equal(p.button.disabled,true);p.api.update(snap());assert.equal(p.button.disabled,true);}
function staleUpdate(source=panelSource){const p=mounted(source);p.api.update(snap());p.api.destroy();const newer=p.P.mount(p.element);newer.update(snap());const b=walk(p.element).find(n=>n.tag==='button');b.click();assert.equal(cls(p.element,'pcp-trade').length,3);p.api.update({status:'pending'});assert.equal(p.element.dataset.state,'ready');assert.equal(cls(p.element,'pcp-trade').length,3);assert.equal(b.disabled,false);}
test('regression: repeated mountBefore returns one panel and one handle',()=>beforeMount());
test('regression: same-container mount preserves result/handle and one listener',()=>sameMount());
test('regression: destroy removes listener/clears output and is idempotent',()=>destroyed());
test('regression: destroyed generation cannot mutate a remounted panel',()=>staleUpdate());
test('regression: destroy + mountBefore reuses its container with a fresh handle',()=>{const P=loadPanel(),parent=new Element('main'),target=new Element('section');parent.append(target);const a=P.mountBefore(target);a.destroy();const b=P.mountBefore(target);assert.notEqual(a.update,b.update);assert.equal(a.element,b.element);assert.equal(parent.children.length,2);a.update({status:'pending'});assert.equal(b.element.dataset.state,'empty');});
test('preserved: identity update retains result; pending clears immediately',()=>{const p=mounted(),s=snap();p.api.update(s);p.button.click();const before=cls(p.element,'pcp-trade')[0];p.api.update(s);assert.equal(cls(p.element,'pcp-trade')[0],before);p.api.update({status:'pending'});assert.equal(cls(p.element,'pcp-trade').length,0);assert.equal(p.button.disabled,true);});

function route(source=leagueSource){const a=source.indexOf('  function scheduleOpps() {'),b=source.indexOf('  // ---------- keeping the page in step ----------',a);assert.ok(a>=0&&b>a);const c=makeCase(),ws={...c.league,ui:{}},body=new Element('div'),live=new Element('p'),pending=[],renders=[];const s={UI:{runId:1,timer:null,running:false,result:{marker:'old'},cache:new Map()},store:{get:()=>ws},mathContext:()=>c.ctx,teamById:(w,id)=>w.teams.find(t=>t.id===id),searchedOpponents:w=>w.teams.slice(1),$:id=>id==='v2LgOppsBody'?body:live,Date,OPP_DEBOUNCE_MS:300,setTimeout:()=>17,clearTimeout(){},O:{runAll:()=>new Promise(resolve=>pending.push(resolve))},renderOpps:()=>renders.push(s.UI.result),announce(){},plural(){return '';}};vm.createContext(s);vm.runInContext(source.slice(a,b),s);return {s,body,live,pending,renders};}
const result=marker=>({marker,rows:[],perOpponent:[],cancelled:false});
async function missingCleanup(source=leagueSource){const h=route(source),old=h.s.runOpps(1);h.s.scheduleOpps();h.pending[0](result('old'));await old;h.s.mathContext=()=>null;await h.s.runOpps(h.s.UI.runId);assert.equal(h.s.UI.running,false);assert.equal(h.body.attrs['aria-busy'],undefined);assert.equal(h.live.textContent,'');assert.equal(h.s.UI.result,null);}
async function currentCancelled(source=leagueSource){const h=route(source),p=h.s.runOpps(1);h.pending[0]({...result('cancelled'),cancelled:true});await p;assert.equal(h.s.UI.running,false);assert.equal(h.body.attrs['aria-busy'],undefined);assert.equal(h.s.UI.result,null);assert.equal(h.renders.length,1);}
test('regression: cancelled older run then missing context clears current busy state',()=>missingCleanup());
test('regression: current cancelled completion clears busy and stale result',()=>currentCancelled());
async function staleBusy(source=leagueSource){const h=route(source),old=h.s.runOpps(1);h.s.scheduleOpps();const current=h.s.runOpps(h.s.UI.runId);h.pending[0](result('old'));await old;assert.equal(h.s.UI.running,true);assert.equal(h.body.attrs['aria-busy'],'true');assert.equal(h.renders.length,0);h.pending[1](result('current'));await current;assert.equal(h.s.UI.result.marker,'current');assert.equal(h.s.UI.running,false);}
test('preserved: stale completion cannot clear a newer active run busy state',()=>staleBusy());
function staleStart(source=leagueSource){const h=route(source);h.s.UI.runId=2;h.s.UI.timer=99;const p=h.s.runOpps(1);assert.equal(h.s.UI.timer,99);assert.equal(h.pending.length,0);return p;}
test('regression: stale scheduled callback cannot consume current timer/start work',()=>staleStart());
test('preserved: valid current completion publishes once and settles busy state',async()=>{const h=route(),p=h.s.runOpps(1),r=result('current');h.pending[0](r);await p;assert.equal(h.s.UI.result,r);assert.equal(h.s.UI.running,false);assert.equal(h.body.attrs['aria-busy'],undefined);assert.equal(h.renders.length,1);});

function mutant(source,anchor,replacement){assert.equal(source.split(anchor).length-1,1);return source.replace(anchor,replacement);}
{
  test('control: deleting idempotent mount guard fails the regression',()=>{assert.throws(()=>sameMount(mutant(panelSource,'    if (mounted) return mounted;','    // guard removed')),{code:'ERR_ASSERTION'});});
  test('control: deleting update generation guard fails the stale-handle regression',()=>{assert.throws(()=>staleUpdate(mutant(panelSource,'if (!isCurrent() || next === snapshot) return;','if (next === snapshot) return;')),{code:'ERR_ASSERTION'});});
  test('control: deleting invalid-context busy cleanup fails regression',async()=>{const m=mutant(leagueSource,'    if (!ctx || !mine || !ctx.charts.length) {\n      UI.result = null;\n      UI.running = false;\n      if (body) body.removeAttribute("aria-busy");','    if (!ctx || !mine || !ctx.charts.length) {\n      UI.result = null;\n      // busy cleanup removed');await assert.rejects(missingCleanup(m),{code:'ERR_ASSERTION'});});
  test('control: deleting completion generation guard fails busy ownership regression',async()=>{const m=mutant(leagueSource,'    if (id !== UI.runId) return;\n    UI.running = false;','    UI.running = false;');await assert.rejects(staleBusy(m),{code:'ERR_ASSERTION'});});
  test('control: deleting entry generation guard fails stale callback regression',()=>{const m=mutant(leagueSource,'    if (id !== UI.runId) return;\n    UI.searchError = false;\n    UI.timer = null;','    UI.searchError = false;\n    UI.timer = null;');assert.throws(()=>staleStart(m),{code:'ERR_ASSERTION'});});
}

}
// progress and captured pricing
{
'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ROOT=require('node:path').resolve(__dirname,'../..');
const SOURCE=ROOT;
const source=fs.readFileSync(SOURCE+'/app/v2/league.js','utf8');
const actualRunner=require(ROOT+'/app/v2/opportunities.js');
const {makeCase}=require(ROOT+'/tests/jeg1183_package_cases.js');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const result=marker=>({marker,rows:[],perOpponent:[],cancelled:false});
const node=()=>({hidden:false,textContent:'',attrs:{},classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}});
function harness(text=source){
  const a=text.indexOf('  function scheduleOpps() {'),b=text.indexOf('  // ---------- keeping the page in step ----------',a);assert.ok(a>=0&&b>a);
  const c=makeCase(),ws={...c.league,ui:{}},nodes={v2LgOppsBody:node(),v2LgOppsStatus:node(),v2FindLeague:node()};
  const calls=[],renders=[];let clock=1000;
  const s={UI:{runId:1,timer:null,running:false,result:result('old'),cache:new Map()},
    store:{get:()=>ws},mathContext:()=>c.ctx,teamById:(w,id)=>w.teams.find(t=>t.id===id),searchedOpponents:w=>w.teams.slice(1),
    $:id=>nodes[id]||(nodes[id]=node()),Date:{now:()=>clock},OPP_DEBOUNCE_MS:300,setTimeout:()=>17,clearTimeout(){},
    O:{runAll:(...args)=>{const d=deferred();calls.push({d,args});return d.promise;}},
    renderOpps:()=>renders.push({result:s.UI.result,running:s.UI.running}),announce(){},plural(){return '';}};
  vm.createContext(s);vm.runInContext(text.slice(a,b),s);
  return {s,c,calls,nodes,renders,tick:()=>{clock=2000;}};
}
async function staleProgress(text=source){
  const h=harness(text),old=h.s.runOpps(1);h.s.scheduleOpps();const newer=h.s.runOpps(h.s.UI.runId);h.tick();
  const p={index:0,total:3,name:'NEW'};h.calls[1].args[3].onProgress(p);const before=h.nodes.v2LgOppsStatus.textContent;
  h.calls[0].args[3].onProgress({...p,name:'OLD'});
  const after=h.nodes.v2LgOppsStatus.textContent;
  h.calls[0].d.resolve(result('old'));h.calls[1].d.resolve(result('new'));await Promise.all([old,newer]);
  assert.equal(after,before);assert.match(after,/NEW/);
}
test('regression: late old progress cannot overwrite current search status',()=>staleProgress());
test('regression: callback retained after its current run settles cannot restore progress',async()=>{
  const h=harness(),p=h.s.runOpps(1),progress=h.calls[0].args[3].onProgress;h.calls[0].d.resolve(result('done'));await p;h.tick();
  progress({index:0,total:3,name:'LATE'});assert.equal(h.nodes.v2LgOppsStatus.textContent,'');
});
async function currentReject(text=source){
  const h=harness(text),p=h.s.runOpps(1),error=new Error('controlled failure');h.tick();h.calls[0].args[3].onProgress({index:0,total:3,name:'CURRENT'});
  h.calls[0].d.reject(error);await p;assert.equal(h.s.UI.searchError,true);
  assert.equal(h.s.UI.running,false);assert.equal(h.s.UI.result,null);assert.equal(h.nodes.v2LgOppsBody.attrs['aria-busy'],undefined);
  assert.equal(h.nodes.v2LgOppsStatus.textContent,'');assert.equal(h.renders.length,1);assert.equal(h.renders[0].running,false);
}
test('regression: current rejected run clears busy/result/status and handles rejection',()=>currentReject());
async function staleReject(text=source){
  const h=harness(text),old=h.s.runOpps(1);const outcome=old.then(()=>({ok:true}),error=>({ok:false,error}));
  h.s.scheduleOpps();const newer=h.s.runOpps(h.s.UI.runId);h.tick();h.calls[1].args[3].onProgress({index:0,total:3,name:'NEW'});
  const before=h.nodes.v2LgOppsStatus.textContent;h.calls[0].d.reject(new Error('old failure'));const oldOutcome=await outcome;
  const state={running:h.s.UI.running,busy:h.nodes.v2LgOppsBody.attrs['aria-busy'],status:h.nodes.v2LgOppsStatus.textContent,renders:h.renders.length};
  h.calls[1].d.resolve(result('new'));await newer;
  assert.equal(oldOutcome.ok,true,'obsolete rejection is contained');assert.equal(state.running,true);assert.equal(state.busy,'true');
  assert.equal(state.status,before);assert.equal(state.renders,0);assert.equal(h.s.UI.result.marker,'new');
}
test('regression: old rejection neither escapes nor clears newer active work',()=>staleReject());
test('regression: old rejection cannot erase an already completed newer result',async()=>{
  const h=harness(),old=h.s.runOpps(1),outcome=old.then(()=>true,()=>false);h.s.scheduleOpps();const newer=h.s.runOpps(h.s.UI.runId),r=result('new');
  h.calls[1].d.resolve(r);await newer;h.calls[0].d.reject(new Error('old'));assert.equal(await outcome,true);
  assert.equal(h.s.UI.result,r);assert.equal(h.renders.length,1);assert.equal(h.s.UI.running,false);
});
test('preserved: current progress and valid success still work',async()=>{
  const h=harness(),p=h.s.runOpps(1);h.tick();h.calls[0].args[3].onProgress({index:1,total:3,name:'CURRENT'});
  assert.match(h.nodes.v2LgOppsStatus.textContent,/CURRENT \(2 of 3\)/);h.calls[0].d.resolve(result('done'));await p;
  assert.equal(h.nodes.v2LgOppsStatus.textContent,'');assert.equal(h.s.UI.result.marker,'done');
});
test('actual runner reachability: cancellation observes obsolete id, not current generation',async()=>{
  const h=harness(),entered=deferred(),release=deferred(),observed=[];
  h.s.O.runAll=async(mine,opponents,ctx,options)=>{
    const r=await actualRunner.runAll(mine,opponents,ctx,{...options,budgetMs:-1,yieldFn:()=>{entered.resolve();return release.promise;}});
    observed.push({cancelled:r.cancelled,id:h.s.UI.runId,rows:r.rows.length,cache:h.s.UI.cache.size});return r;
  };
  const old=h.s.runOpps(1);await entered.promise;h.s.scheduleOpps();release.resolve();await old;
  assert.deepEqual(observed,[{cancelled:true,id:2,rows:0,cache:0}]);assert.equal(h.s.UI.result.marker,'old');
  h.s.mathContext=()=>null;await h.s.runOpps(2);assert.equal(h.s.UI.running,false);
});
test('actual runner reachability: current generation finishes without cancellation',async()=>{
  const h=harness(),observed=[];h.s.O.runAll=async(...args)=>{const r=await actualRunner.runAll(...args);observed.push(r.cancelled);return r;};
  await h.s.runOpps(1);assert.deepEqual(observed,[false]);assert.equal(h.s.UI.running,false);assert.equal(h.renders.length,1);
});
test('actual runner rejection: thrown pairing failure reaches handled recoverable cleanup',async()=>{
  const h=harness(),error=new Error('controlled actual pairing failure');
  h.s.O.runAll=(mine,opponents,ctx,options)=>actualRunner.runAll(mine,opponents,{...ctx,findTrades(){throw error;}},options);
  await h.s.runOpps(1);assert.equal(h.s.UI.searchError,true);assert.equal(h.s.UI.running,false);
  assert.equal(h.s.UI.result,null);assert.equal(h.nodes.v2LgOppsBody.attrs['aria-busy'],undefined);
});

async function capturedPricing(code=source) {
  const h=harness(code),captured=h.c.ctx,changed=makeCase().ctx;
  h.s.mathContext=()=>captured;
  const p=h.s.runOpps(1),passed=h.calls[0].args[2];
  assert.equal(passed.rowsByKey,captured.rowsByKey);
  // Engine state changes while the deferred run still owns its original context.
  h.s.mathContext=()=>changed;
  const r=result('captured');h.calls[0].d.resolve(r);await p;
  const expected=[...passed.rowsByKey.values()];
  assert.equal(r.pricingRows.length,expected.length);
  expected.forEach((row,i)=>assert.equal(r.pricingRows[i],row));
  assert.notEqual(r.pricingRows[0],[...changed.rowsByKey.values()][0]);
  return {h,r,captured,changed};
}
test('compatibility: completion publishes pricing rows from the exact captured run context',()=>capturedPricing());
test('compatibility: retained result keeps original pricing through a newer pending/completed search',async()=>{
  const {h,r,changed}=await capturedPricing(),original=r.pricingRows;
  h.s.scheduleOpps();const next=h.s.runOpps(h.s.UI.runId);
  assert.equal(h.s.UI.result,r);assert.equal(h.s.UI.result.pricingRows,original);
  h.tick();h.calls[1].args[3].onProgress({index:0,total:3,name:'NEW'});
  const status=h.nodes.v2LgOppsStatus.textContent;
  h.calls[0].args[3].onProgress({index:0,total:3,name:'OLD'});
  assert.equal(h.nodes.v2LgOppsStatus.textContent,status);
  const newer=result('new');h.calls[1].d.resolve(newer);await next;
  assert.equal(r.pricingRows,original);
  assert.equal(newer.pricingRows[0],[...changed.rowsByKey.values()][0]);
});
async function stalePricing(code=source) {
  const h=harness(code),old=h.s.runOpps(1);h.s.scheduleOpps();const newer=h.s.runOpps(h.s.UI.runId);
  const fresh=result('new');h.calls[1].d.resolve(fresh);await newer;
  const stale=result('old');h.calls[0].d.resolve(stale);await old;
  assert.equal(h.s.UI.result,fresh);assert.equal(stale.pricingRows,undefined);
  const current=h.s.runOpps(h.s.UI.runId),cancelled={...result('cancelled'),cancelled:true};
  h.calls[2].d.resolve(cancelled);await current;assert.equal(cancelled.pricingRows,undefined);
}
test('compatibility: stale/cancelled completions never publish or annotate pricing snapshots',()=>stalePricing());
test('control: recomputing completed pricing from a newer context is caught',async()=>{
  const m=mutate(source,'result.pricingRows = Array.from(ctx.rowsByKey.values());','result.pricingRows = Array.from(mathContext().rowsByKey.values());');
  await assert.rejects(capturedPricing(m),{code:'ERR_ASSERTION'});
});
test('control: moving pricing annotation before completion ownership checks is caught',async()=>{
  const removed=mutate(source,'    result.pricingRows = Array.from(ctx.rowsByKey.values());\n','');
  const m=mutate(removed,'    if (id !== UI.runId) return;\n    UI.running = false;',
    '    result.pricingRows = Array.from(ctx.rowsByKey.values());\n    if (id !== UI.runId) return;\n    UI.running = false;');
  await assert.rejects(stalePricing(m),{code:'ERR_ASSERTION'});
});

// Run exact existing applyRoute: normal navigation hides the host; it does not tear it down.
function applyExistingRoute(h){
  const text=fs.readFileSync(ROOT+'/app/v2/v2.js','utf8'),a=text.indexOf('  function applyRoute() {'),b=text.indexOf('  // ---------- wiring ----------',a);assert.ok(a>=0&&b>a);
  Object.assign(h.s,{syncBasisLabels(){},currentView:()=> 'values',writingSection:()=>'',applyStatic(){},document:{querySelectorAll:()=>[],querySelector:()=>node()},
    hashBase:()=> '#player-values',closePopover(){},expanded:false,refreshValues(){},syncTitle(){}});
  const c=text.indexOf('  function refresh() {'),d=text.indexOf('  // Values auditing',c);assert.ok(c>=0&&d>c);
  vm.runInContext(text.slice(a,b)+'\n'+text.slice(c,d),h.s);h.s.applyRoute();
}
test('actual route call path: navigating away hides persistent host without cancelling same-workspace search',async()=>{
  const h=harness(),p=h.s.runOpps(1),host=h.nodes.v2FindLeague;applyExistingRoute(h);
  assert.equal(host.hidden,true);assert.equal(h.nodes.v2FindLeague,host);assert.equal(h.s.UI.runId,1);
  h.calls[0].d.resolve(result('background'));await p;assert.equal(h.s.UI.result.marker,'background');
});
test('prospective replacement control: replacing host alone still permits old completion',async()=>{
  const h=harness(),p=h.s.runOpps(1);h.nodes.v2FindLeague=node();h.nodes.v2LgOppsBody=node();h.nodes.v2LgOppsStatus=node();
  h.calls[0].d.resolve(result('old-host'));await p;assert.equal(h.s.UI.result.marker,'old-host');assert.equal(h.renders.length,1);
});
test('prospective replacement acceptance: explicit generation invalidation blocks old completion',async()=>{
  const h=harness(),p=h.s.runOpps(1);h.s.UI.runId++;h.s.UI.running=false;h.s.UI.result=null;
  h.nodes.v2FindLeague=node();h.nodes.v2LgOppsBody=node();h.nodes.v2LgOppsStatus=node();
  h.calls[0].d.resolve(result('old-host'));await p;assert.equal(h.s.UI.result,null);assert.equal(h.renders.length,0);
});
test('actual store replacement callback advances generation and rejects old completion',async()=>{
  const h=harness(),p=h.s.runOpps(1),text=fs.readFileSync(ROOT+'/app/v2/league.js','utf8');
  const a=text.indexOf('  function refreshAll(reason) {'),b=text.indexOf('  // The league settings changed',a);
  const c=text.indexOf('    store.onChange((ws, change) => {'),d=text.indexOf('    store.onStatus(',c);assert.ok(a>=0&&b>a&&c>=0&&d>c);
  Object.assign(h.s,{renderTeams(){},renderStatus(){},renderSummary(){}});h.s.UI.ready=true;h.s.UI.comps=new Map();
  h.s.store.onChange=fn=>{h.changed=fn;};vm.runInContext(text.slice(a,b)+'\n'+text.slice(c,d),h.s);
  h.changed(h.s.store.get(),{reason:'replace'});assert.equal(h.s.UI.runId,2);h.renders.length=0;
  h.calls[0].d.resolve(result('old-workspace'));await p;assert.equal(h.s.UI.result.marker,'old');assert.equal(h.renders.length,0);
});
function mutate(text,anchor,replacement){assert.equal(text.split(anchor).length-1,1);return text.replace(anchor,replacement);}
{
  test('control: removed progress ownership guard is caught',async()=>{
    const m=mutate(source,'if (id !== UI.runId || !UI.running) return;','/* progress guard removed */');await assert.rejects(staleProgress(m),{code:'ERR_ASSERTION'});
  });
  test('control: removed rejection cleanup is caught',async()=>{
    const m=mutate(source,'      UI.searchError = true;\n      UI.result = null;\n      UI.running = false;\n      if (body) body.removeAttribute("aria-busy");\n      if (live) live.textContent = "";\n      renderOpps();\n      return;','      UI.searchError = true;\n      return;');await assert.rejects(currentReject(m),{code:'ERR_ASSERTION'});
  });
  test('control: removed stale rejection guard is caught',async()=>{
    const m=mutate(source,'      if (id !== UI.runId) return;\n      UI.searchError = true;','      UI.searchError = true;');await assert.rejects(staleReject(m),{code:'ERR_ASSERTION'});
  });
}

}
// recoverable failure
{
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ROOT=require('node:path').resolve(__dirname,'../..'),SOURCE=ROOT;
const source=fs.readFileSync(SOURCE+'/app/v2/league.js','utf8');
const {makeCase}=require(ROOT+'/tests/jeg1183_package_cases.js');
class Element{
  constructor(tag,props={}){this.tag=tag;this.props=props;this.children=[];this.attrs={};this.textContent=props.text||'';}
  append(...kids){this.children.push(...kids);}
  replaceChildren(...kids){this.children=kids;}
  setAttribute(k,v){this.attrs[k]=v;}
  removeAttribute(k){delete this.attrs[k];}
}
const text=e=>e.textContent+e.children.map(text).join(' ');
function harness(code=source){
  const c=makeCase(),ws={...c.league,ui:{}},calls=[],nodes={v2LgOpps:new Element('section'),v2LgOppsBody:new Element('div'),v2LgOppsStatus:new Element('p')};
  const s={UI:{runId:1,running:false,timer:null,result:null,cache:new Map()},store:{get:()=>ws},mathContext:()=>c.ctx,
    teamById:(w,id)=>w.teams.find(t=>t.id===id),rowsOfTeam:(t,ctx)=>t.entries.map(e=>ctx.rowsByKey.get(e.key)).filter(Boolean),
    searchedOpponents:w=>w.teams.slice(1),renderInclusion(){},$:id=>nodes[id],
    el:(tag,props)=>new Element(tag,props),button:(label,props,fn)=>Object.assign(new Element('button',{...props,text:label}),{click:fn}),
    Date,OPP_DEBOUNCE_MS:300,setTimeout:fn=>{s.timerFn=fn;return 17;},clearTimeout(){},announce(){},plural(){return '';},
    O:{runAll:()=>new Promise((resolve,reject)=>calls.push({resolve,reject}))}};
  const a=code.indexOf('  function scheduleOpps() {'),b=code.indexOf('  // ---------- keeping the page in step ----------',a);
  const p=code.indexOf('  function renderOppsNow() {'),q=code.indexOf('    const summary = summaryData();',p);
  assert.ok(a>=0&&b>a&&p>=0&&q>p);vm.createContext(s);
  vm.runInContext(code.slice(a,b)+'\n'+code.slice(p,q)+'\n return;\n}\n this.renderOpps=renderOppsNow;',s);
  return {s,calls,body:nodes.v2LgOppsBody,live:nodes.v2LgOppsStatus};
}
const done=()=>({rows:[],perOpponent:[],cancelled:false});
async function failed(h){const p=h.s.runOpps(h.s.UI.runId),settled=p.then(()=>true,()=>false);h.calls.at(-1).reject(new Error('controlled failure'));return settled;}
async function currentRecovery(code=source){
  const h=harness(code);assert.equal(await failed(h),true,'current search failure must be handled');
  assert.equal(h.s.UI.running,false);assert.equal(h.s.UI.result,null);assert.equal(h.s.UI.searchError,true);
  assert.equal(h.body.attrs['aria-busy'],undefined);assert.equal(h.live.textContent,'');
  assert.equal(text(h.body).includes('Finding trades'),false);assert.match(text(h.body),/Trade search failed\. Try again\./);
  assert.equal(h.body.children.filter(e=>e.tag==='button'&&e.props.id==='v2LgOppsRetry').length,1);
}
test('current failure resolves to one recoverable state without Finding or rejected promise',()=>currentRecovery());
test('retry clears error during debounce and recovers after current success',async()=>{
  const h=harness();assert.equal(await failed(h),true);const retry=h.body.children.find(e=>e.tag==='button');assert.ok(retry);
  retry.click();assert.equal(h.s.UI.searchError,false);assert.equal(h.s.UI.timer,17);assert.match(text(h.body),/Finding trades/);
  assert.equal(h.body.children.filter(e=>e.tag==='button').length,0);
  const p=h.s.timerFn();h.calls.at(-1).resolve(done());await p;assert.equal(h.s.UI.searchError,false);assert.equal(h.s.UI.running,false);
  assert.equal(h.s.UI.result.cancelled,false);h.s.renderOpps();assert.equal(text(h.body).includes('Trade search failed'),false);
});
test('repeated failure/redraw retains one retry control',async()=>{
  const h=harness();await failed(h);h.s.renderOpps();h.s.renderOpps();assert.equal(h.body.children.filter(e=>e.tag==='button').length,1);
  h.body.children.find(e=>e.tag==='button').click();const p=h.s.timerFn();h.calls.at(-1).reject(new Error('again'));await p;
  assert.equal(h.body.children.filter(e=>e.tag==='button').length,1);assert.equal(h.s.UI.searchError,true);
});
test('stale failure cannot replace newer active search or its eventual result',async()=>{
  const h=harness(),old=h.s.runOpps(1),oldState=old.then(()=>true,()=>false);h.s.scheduleOpps();const newer=h.s.timerFn();
  h.calls[0].reject(new Error('stale'));assert.equal(await oldState,true);assert.equal(h.s.UI.searchError,false);assert.equal(h.s.UI.running,true);
  const r=done();h.calls[1].resolve(r);await newer;assert.equal(h.s.UI.result,r);assert.equal(h.s.UI.searchError,false);
});
test('stale success cannot erase a newer recoverable failure',async()=>{
  const h=harness(),old=h.s.runOpps(1);h.s.scheduleOpps();const newer=h.s.timerFn();h.calls[1].reject(new Error('new failed'));await newer;
  const before=text(h.body);h.calls[0].resolve(done());await old;assert.equal(h.s.UI.searchError,true);assert.equal(text(h.body),before);
});
test('missing context and current cancellation clear obsolete error state',async()=>{
  const h=harness();await failed(h);h.s.mathContext=()=>null;await h.s.runOpps(1);assert.equal(h.s.UI.searchError,false);assert.equal(h.s.UI.running,false);
  const c=makeCase();h.s.mathContext=()=>c.ctx;const p=h.s.runOpps(1);h.calls.at(-1).resolve({...done(),cancelled:true});await p;
  assert.equal(h.s.UI.searchError,false);assert.equal(h.s.UI.result,null);
});
function mutate(code,anchor,replacement){assert.equal(code.split(anchor).length-1,1);return code.replace(anchor,replacement);}
{
  test('control: restoring current rejection is caught',async()=>{await assert.rejects(currentRecovery(mutate(source,'      UI.searchError = true;','      UI.searchError = true;\n      throw new Error("mutant unhandled");')),{code:'ERR_ASSERTION'});});
  test('control: removing recoverable renderer is caught',async()=>{
    const a=source.indexOf('    if (UI.searchError && !UI.running && !UI.timer) {'),b=source.indexOf('    const res = UI.result;',a);assert.ok(a>=0&&b>a);
    await assert.rejects(currentRecovery(source.slice(0,a)+source.slice(b)),{code:'ERR_ASSERTION'});
  });
}

}
