(()=>{
/* Buy / Sell tab (JEG-1535). Every number is an engine record (DDF.engine, ddf-engine.js); nothing is inlined.
   Charts = mean of the indexed values of the four charts (CBS Sports, USA Today, FantasyPros, FantasyCalc) the engine
   records give for the player. A chart that only estimates him (filled in from the other charts) gives null and is left
   out; a chart whose list ends before him gives the engine's indexed 0, which counts (and is in the n/4 badge) (JEG-1393
   R1-OP-11, checked against the live engine 2026-11-07). Largest gap = DDF Value (your override applied) minus each listed chart, the largest in size.
   League rosters come read-only from DDF.league (ddf-league.js; DDF.engine.league() before it is ready). Natural fit is the live site's one predicate,
   TradeValueFinder.tradeFit (v2/finder.js), with its context built as finder.js fitContext / opportunities.js pairingSteps. */
const $=id=>document.getElementById(id);
const V=()=>window.DDFValues;
const E=()=>window.DDF&&window.DDF.engine;
const F=()=>window.TradeValueFinder;
const num=v=>typeof v==='number'&&isFinite(v);
const CHARTS=[['cbs','CBS Sports'],['usat','USA Today'],['fp','FantasyPros'],['fc','Live market (FantasyCalc)']];
const f2=v=>v.toFixed(2),sg=v=>(v>=0?'+':'−')+Math.abs(v).toFixed(2);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const short=n=>{const t=n.replace(/\s+(Jr\.?|Sr\.?|II|III|IV)$/,'').split(' ');return t.length>2&&/^St\.?$/.test(t[t.length-2])?t.slice(-2).join(' '):t[t.length-1]};
const SHOW=5;
let live=false,hlName=null,DB=[],byKey=new Map(),LC=null,league=false,expanded={sell:false,buy:false},sel={give:null,get:null,chip:'',side:'sell'};
let FX=null,fitCache=new Map(),yoursSig='';

/* Charts for one record (engine record or a DDFValues.D row: both carry cbs/usat/fp/fc). */
function chartsOf(p){
 const used=CHARTS.filter(([k])=>num(p[k])).map(([k,name])=>[name,p[k]]);
 return{v:used.length?used.reduce((s,u)=>s+u[1],0)/used.length:null,used};
}
/* League bridge: only with a marked team. owner: player key -> team. */
/* JEG-1560 C: the reader's league comes through DDF.league (link, pasted ddf:pasted, saved workspace), the same read as
   team/partners/find; DDF.engine.league() (saved workspace only) is the fallback before DDF.league is ready or loaded. */
function sharedLeague(){
 const L=window.DDF&&DDF.league,cur=L&&L.current?L.current():null;
 if(!cur)return null;
 const teams=cur.teams.map(t=>({id:String(t.index),name:t.name,keys:new Set(t.players.filter(x=>!x.unpriced).map(x=>String(x.key)))}));
 return{name:cur.name,teams,mine:cur.me===null?null:String(cur.me)};
}
function leagueCtx(){
 const e=E();if(!e||!e.controls())return null;
 let lg=sharedLeague();if(!lg){try{lg=e.league()}catch(_){lg=null}}
 if(!lg)return{lg:null};
 const me=lg.mine?lg.teams.find(t=>t.id===lg.mine):null;
 if(!me)return{lg};
 const owner=new Map();lg.teams.forEach(t=>{if(t.id!==me.id)t.keys.forEach(k=>{if(!owner.has(k))owner.set(k,t)})});
 return{lg,me,mine:me.keys,owner};
}
/* makeDB(true) = the lists on DDF's pipeline values (p.base); makeDB() = with your overrides (what the tab shows). No side effects. */
function makeDB(useBase){
 const e=E();if(!e||!e.controls())return[];
 const ctx=leagueCtx(),lg=!!(ctx&&ctx.me);
 return e.players().map(r=>{
  const c=chartsOf(r),yours=lg&&ctx.mine.has(r.key),t=lg&&!yours?ctx.owner.get(r.key):null;
  return{key:r.key,n:r.n,pos:r.pos,ddf:useBase?r.base:r.ddf,base:r.base,ov:!useBase&&r.ov,mkt:c.v,charts:c.used,srcs:c.used.length,
   yours,owner:yours?'Your team':t?t.name:null,teamId:yours?ctx.me.id:t?t.id:null,rec:r};
 }).filter(p=>num(p.ddf)&&p.ddf>0&&num(p.mkt)&&p.mkt>0&&(!lg||p.teamId!==null));
}
function syncYours(){
 const keys=league?[...LC.mine].sort():[],sig=keys.join(',');
 if(sig===yoursSig||!V().setYours)return;yoursSig=sig;V().setYours(new Set(keys));
}
function build(){
 LC=leagueCtx();league=!!(LC&&LC.me);
 FX=null;fitCache=new Map();
 DB=makeDB();byKey=new Map(DB.map(p=>[p.key,p]));
 syncYours();
}
function gapOf(p){/* largest gap vs any listed chart, signed DDF minus chart */
 let best=null;p.charts.forEach(([c,v])=>{const g=p.ddf-v;if(!best||Math.abs(g)>Math.abs(best.g))best={g,c}});return best;
}
const byGap=(a,b)=>Math.abs(b.g.g)-Math.abs(a.g.g);
function sellList(db){return (db||DB).filter(p=>p.yours&&p.mkt>p.ddf).map(p=>({p,g:gapOf(p)})).sort(byGap)}
function buyList(db){return (db||DB).filter(p=>!p.yours&&p.ddf>p.mkt).map(p=>({p,g:gapOf(p)})).sort(byGap)}

/* ---- fit: the tradeFit context, built as finder.js fitContext()/benchWeights() and opportunities.js pairingSteps ---- */
function fitCtx(){
 if(FX!==null)return FX||null;
 FX=false;
 try{
  const C=E().controls(),Fd=F();
  if(!league||!C||!Fd||!Fd.tradeFit||!C.getAllRows)return null;
  const shape=C.getRosterShape();
  const expected=Fd.expectedDepth(C.getAdjustmentWeights().allocation,C.getState().teams);
  const info=C.getSourceInfo?C.getSourceInfo():[],avail=new Set(info.filter(i=>i.available).map(i=>i.key));
  const charts=Fd.CHART_KEYS.filter(k=>avail.has(k)),market=charts.length>=Fd.MIN_CHARTS?charts:null;
  if(!shape||!expected||!market)return null;
  const readout=C.getBenchShareReadout?C.getBenchShareReadout():null;
  const overall=readout&&num(readout.overall)?readout.overall:(C.getBenchShare?C.getBenchShare():null);
  const weights={overall:num(overall)?overall:0};
  ['QB','RB','WR','TE'].forEach(pos=>{if(readout&&num(readout[pos]))weights[pos]=readout[pos]});
  const all=new Map(C.getAllRows().map(r=>[String(r.player_key),r]));
  const rosters=new Map(),wide=new Map();
  LC.lg.teams.forEach(t=>{const rows=Fd.withChartAverage([...t.keys].map(k=>all.get(k)).filter(Boolean),market);rosters.set(t.id,rows);rows.forEach(r=>{if(!wide.has(String(r.player_key)))wide.set(String(r.player_key),r)})});
  FX={ctx:{shape,expected,weights,ourKey:'ddf_value',marketKey:Fd.MARKET_KEY,chartKeys:market,z:Fd.FIT_Z},rosters,wide};
 }catch(err){console.warn('Buy / Sell: no fit context',err);FX=false}
 return FX||null;
}
/* One-for-one: you give `give` (yours), get `get` (on get.teamId). natural: true/false from tradeFit, null when not judged. */
function pairStats(give,get){
 const k=give.key+'>'+get.key;if(fitCache.has(k))return fitCache.get(k);
 const X=fitCtx();let fit=null;
 if(X){const mine=X.rosters.get(LC.me.id),theirs=X.rosters.get(get.teamId),g=X.wide.get(give.key),r=X.wide.get(get.key);
  if(mine&&theirs&&g&&r)fit=F().tradeFit({mine:{roster:mine,leaving:[g],arriving:[r]},theirs:{roster:theirs,leaving:[r],arriving:[g]}},X.ctx)}
 let score;
 if(fit){const a=fit.us.totalDelta,b=fit.them.totalDelta;score=num(a)&&num(b)?Math.min(a,b):-Infinity}
 else score=Math.min(get.ddf-give.ddf,give.mkt-get.mkt);
 const s={fit,natural:fit&&fit.natural?!!fit.natural.ok:null,score};
 fitCache.set(k,s);return s;
}
const rank=(a,b)=>((b.s.natural===true)-(a.s.natural===true))||(b.s.score-a.s.score);
function comparables(give){return DB.filter(p=>!p.yours&&p.pos===give.pos).map(p=>({p,s:pairStats(give,p)})).sort(rank).slice(0,4)}
function gives(get){return DB.filter(p=>p.yours).map(p=>({p,s:pairStats(p,get)})).sort((a,b)=>((b.s.natural===true)-(a.s.natural===true))||((b.p.pos===get.pos)-(a.p.pos===get.pos))||(b.s.score-a.s.score)).slice(0,4)}
const natTag=s=>s.natural===true?'<span class="bs-tag nf">Natural fit</span>':s.natural===false?'<span class="bs-tag ck">Not a natural fit</span>':'<span class="bs-tag ck">Check fit in Build a Trade</span>';

/* ---- rendering ---- */
function srcCount(p){const n=p.srcs,names=p.charts.map(c=>c[0]).join(', ');return `<span class="bs-cnt" role="img" aria-label="${n} of 4 charts" title="${n} of 4 charts: ${esc(names)}">${n}/4</span>`}
function buyFit(p){if(!league)return false;return DB.some(q=>q.yours&&pairStats(q,p).natural===true)}
function rowHTML(o,side){
 const p=o.p,g=o.g,cls=g.g<0?'mh':'dg',nat=side==='buy'&&buyFit(p);
 const chartLow=g.c.charAt(0)==='L'?'l'+g.c.slice(1):g.c;
 const label=`${p.n}, ${p.pos}${p.owner&&side==='buy'?', '+p.owner:''}. ${p.ov?'Your value '+f2(p.ddf)+' (override; DDF '+f2(p.base)+')':'DDF '+f2(p.ddf)}, charts ${f2(p.mkt)} (${p.srcs} of 4 charts), largest gap ${sg(g.g)}, DDF minus ${chartLow}.${nat?' Natural fit.':''} Select to see a swap.`;
 const sub=`<small>${esc(p.pos)}${side==='buy'&&p.owner?' · '+esc(p.owner):''}</small>`;
 return `<li><button type="button" class="bs-row" data-side="${side}" data-k="${esc(p.key)}" data-n="${esc(p.n)}" aria-pressed="false" aria-label="${esc(label)}"><span class="bs-name"><strong>${p.yours?'<span aria-hidden="true">★</span> ':''}${esc(p.n)}</strong>${p.yours?'<span class="bs-yours">Yours</span>':''}${p.ov?'<span class="bs-ovr">Your value</span>':''}${sub}${nat?'<span class="bs-tag nf">Natural fit</span>':''}</span><span class="bs-n bs-ddf" data-label="${p.ov?'Your value':'DDF'}">${f2(p.ddf)}</span><span class="bs-n bs-mkt" data-label="Charts">${f2(p.mkt)} ${srcCount(p)}</span><span class="bs-gap"><span class="bs-tag ${cls}">${sg(g.g)} ${esc(g.c)}</span></span></button><div class="vp-bs"><button type="button" class="vp-act" data-act="own" data-n="${esc(p.n)}" aria-label="Set your own value for ${esc(p.n)}">Set your own value</button></div></li>`;
}
function renderList(side){
 const items=side==='sell'?sellList():buyList(),ul=$('bs-'+side),btn=$('bs-'+side+'-more'),open=expanded[side],shown=open?items:items.slice(0,SHOW);
 ul.innerHTML=shown.length?shown.map(o=>rowHTML(o,side)).join(''):`<li class="bs-empty">${side==='sell'?'None of your players are priced higher by the charts than by DDF Value.':league?'No players on the other teams are priced higher by DDF Value than by the charts.':'No players are priced higher by DDF Value than by the charts.'}</li>`;
 const extra=items.length-SHOW;btn.hidden=extra<=0;btn.setAttribute('aria-expanded',String(open));btn.textContent=open?'Show fewer ▴':`Show ${extra} more ▾`;
}
function hlFind(){if(!hlName)return null;let i=sellList().findIndex(o=>o.p.n===hlName);if(i>=0&&league)return['sell',i];i=buyList().findIndex(o=>o.p.n===hlName);return i>=0?['buy',i]:null}
function hlNote(){const n=$('bs-hlnote');if(!hlName||hlFind()){n.hidden=true;return}
 const p=DB.find(q=>q.n===hlName),yours=!!(p&&p.yours);
 n.textContent=!p?hlName+' is not on the Buy or Sell lists: DDF Value or the charts do not price this player'+(league?' on a team in your league.':'.')
  :league?hlName+' is not on the Buy or Sell lists: '+(yours?'the charts do not rate this player above DDF Value.':'DDF Value does not rate this player above the charts.')
  :'Add your league to see whether '+hlName+' is a sell. The Buy list shows players DDF Value rates above the charts.';
 n.hidden=false}
function renderLists(){
 if(!live)return;
 const hf=hlFind();if(hf&&hf[1]>=SHOW)expanded[hf[0]]=true;
 const noTeam=!!(LC&&LC.lg&&!LC.me),nolg=$('bs-nolg');
 nolg.hidden=league;
 nolg.querySelector('p').textContent=noTeam?'Confirm your team in your league to see which of your players to sell.':'Add your league to see which of your players to sell.';
 const a=nolg.querySelector('a');a.textContent=noTeam?'Confirm your team':'Add your league';a.href=noTeam?'setup.html':'connect.html';
 $('bs-sell-card').hidden=!league;
 $('bs-buy-note').textContent=league?'Players on the other teams DDF likes more than the charts · owner and fit · top 5':'Players DDF likes more than the charts · top 5';
 const two=document.querySelector('.bs-two');two.classList.toggle('solo',!league);two.style.gridTemplateColumns=league?'':'minmax(0,1fr)';
 renderList('sell');renderList('buy');syncPressed();hlNote();
}
function syncPressed(){
 document.querySelectorAll('.bs-list li').forEach(li=>{const r=li.querySelector('.bs-row');li.classList.toggle('bs-hl',!!(hlName&&r&&r.dataset.n===hlName))});
 document.querySelectorAll('.bs-row').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.side===sel.side&&b.dataset.k===(sel.side==='sell'?sel.give:sel.get))));
 document.querySelectorAll('.bs-opt').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.k===(sel.side==='sell'?sel.get:sel.give))));
}
function renderPick(){
 const box=$('bs-pick'),anchor=byKey.get(sel.side==='sell'?sel.give:sel.get);
 if(!league||!anchor){box.hidden=true;return}
 const opts=sel.side==='sell'?comparables(anchor):gives(anchor);
 $('bs-pick-h').textContent=sel.side==='sell'?'Comparable targets for '+anchor.n:'Players to give for '+anchor.n;
 $('bs-pick-note').textContent=sel.side==='sell'?'Same position on the other teams, natural fit first. Select one to compare.':'Your players, natural fit first, then same position. Select one to compare.';
 $('bs-opts').innerHTML=opts.map(({p,s})=>`<button type="button" class="bs-opt" data-k="${esc(p.key)}" aria-pressed="false"><strong>${p.yours?'★ ':''}${esc(p.n)} · ${esc(p.pos)}${p.owner&&!p.yours?' · '+esc(p.owner):''}</strong><span class="bs-meta">DDF ${f2(p.ddf)} / Charts ${f2(p.mkt)} ${p.srcs}/4</span>${natTag(s)}</button>`).join('')||'<p class="bs-empty">No comparable players in this league.</p>';
 box.hidden=false;
}
function check(cls,txt,sr){return `<li><span class="${cls}" aria-hidden="true">${cls==='ok'?'✓':cls==='no'?'✕':'•'}</span> <span class="vsr">${sr}: </span>${txt}</li>`}
const mark=b=>b?['ok','Pass']:['no','Fail'];
function fitHTML(give,get){
 const s=pairStats(give,get),fit=s.fit;
 if(!fit)return `<div class="bs-fithead"><h4>Roster fit</h4>${natTag(s)}</div><p class="bs-note">Roster fit could not be checked here. Check fit in Build a Trade.</p>`;
 const nat=fit.natural,li=(ok,txt)=>{const m=mark(ok);return check(m[0],txt,m[1])};
 let h=`<div class="bs-fithead"><h4>Roster fit</h4>${natTag(s)}</div><ul class="bs-checks">`+
  li(nat.us.value,`Your DDF Value starters ${sg(fit.us.starterDelta)}`)+
  li(nat.them.value,`Their starters on the charts ${sg(fit.them.starterDelta)}`)+
  (fit.constructionOk?li(true,'Both rosters valid'):li(false,'Rosters not both valid: '+esc(fit.myConstruction.issues.concat(fit.theirConstruction.issues).join('; '))));
 [[nat.us,'Your'],[nat.them,'Their']].forEach(([side,who])=>{if(side.projections===false)h+=li(false,`${who} DDF Value (projections) ${sg(side.projNet)}`)});
 if(nat.us.projections===null||nat.them.projections===null)h+=check('na','DDF Value (projections) not checked: a player in this trade has none. Confirm in Build a Trade.','Check');
 return h+'</ul>';
}
function renderDetail(pop){
 const d=$('bs-detail'),give=byKey.get(sel.give),get=byKey.get(sel.get);
 if(!get&&!give){d.hidden=true;return}
 d.hidden=false;
 $('bs-chip').textContent='After selecting '+sel.chip;
 $('bs-title').textContent=give&&get?short(give.n)+' → '+short(get.n):get?'Target: '+get.n:'Sell: '+give.n;
 const row=p=>`<tr><td>${p.yours?'★ ':''}${esc(short(p.n))} · ${esc(p.pos)}${p.ov?' <span class="bs-ovr">Your value</span>':''}</td><td>${f2(p.ddf)}</td><td>${f2(p.mkt)} ${srcCount(p)}</td></tr>`;
 $('bs-vals').innerHTML=(give?row(give):'')+(get?row(get):'');
 const fit=$('bs-fit');
 if(give&&get)fit.innerHTML=fitHTML(give,get);
 else if(!league)fit.innerHTML=`<div class="bs-fithead"><h4>Roster fit</h4></div><p class="bs-note">Add your league to see which of your players to give and whether it is a natural fit.</p><a class="btn" href="connect.html">Add your league</a>`;
 else fit.innerHTML=`<div class="bs-fithead"><h4>Roster fit</h4></div><p class="bs-note">No one-for-one swap at this position in your league. Check fit in Build a Trade.</p>`;
 $('bs-open').href=E().buildHref({give:give?[give.rec]:[],get:get?[get.rec]:[]});
 if(pop){d.classList.remove('pop');void d.offsetWidth;d.classList.add('pop')}
}
function select(side,key,fromRow){
 const p=byKey.get(key);if(!p)return;
 if(fromRow){
  sel.side=side;sel.chip=p.n;
  if(side==='sell'){sel.give=key;const c=comparables(p);sel.get=c.length?c[0].p.key:null}
  else{sel.get=key;if(league){const g=gives(p);sel.give=g.length?g[0].p.key:null}else sel.give=null}
  renderPick();
 }else{
  sel.chip=p.n;if(sel.side==='sell')sel.get=key;else sel.give=key;
 }
 syncPressed();renderDetail(true);
 const d=$('bs-detail');if(fromRow&&!d.hidden){const r=d.getBoundingClientRect();if(r.top>innerHeight*.85||r.bottom<0)d.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}
}
function defaultSel(){
 sel={give:null,get:null,chip:'',side:'sell'};
 const s=league?sellList():[],b=buyList();
 if(s.length)select('sell',s[0].p.key,true);else if(b.length)select('buy',b[0].p.key,true);
 else{renderPick();renderDetail(false)}
}
function init(){build();renderLists();defaultSel()}
/* re-price after a rebuild (settings, basis, overrides, league), keeping the current selection when it still exists */
function refresh(){if(!live)return;build();renderLists();
 const anchor=sel.side==='sell'?sel.give:sel.get,other=sel.side==='sell'?sel.get:sel.give;
 if(!anchor||!byKey.has(anchor)||(sel.side==='sell'&&!league))defaultSel();
 else{if(other&&!byKey.has(other))select(sel.side,anchor,true);else{renderPick();syncPressed();renderDetail(false)}}}
V().bs={makeDB,sellList,buyList,gapOf,isLeague:()=>league,refresh,marketOf:p=>chartsOf(p).v};
document.addEventListener('click',e=>{
 const r=e.target.closest('.bs-row');if(r){select(r.dataset.side,r.dataset.k,true);return}
 const o=e.target.closest('.bs-opt');if(o){select(sel.side,o.dataset.k,false);return}
 const m=e.target.closest('.bs-more');if(m){const s=m.id==='bs-sell-more'?'sell':'buy';expanded[s]=!expanded[s];renderList(s);syncPressed();$('bs-'+s+'-more').focus()}
});
V().ready.then(()=>{live=true;init();
 document.addEventListener('ddf:values-change',refresh);
 if(window.DDF&&DDF.league&&DDF.league.ready)DDF.league.ready.then(()=>{refresh();DDF.league.on(refresh)},()=>{});
 addEventListener('storage',e=>{if(e.key==='ddf.v2.workspaces')refresh()});
},()=>{});
/* tabs: state lives in the URL hash next to any #s= chat-link token */
const tabs=[...document.querySelectorAll('.screen-tabs [role=tab]')],panels={chart:$('panel-chart'),'buy-sell':$('panel-bs'),overrides:$('panel-ov')};
const dec=t=>{try{return decodeURIComponent(t.replace(/\+/g,' '))}catch(_){return t}};
/* hash tokens (joined by &): overrides | buy-sell, each optionally followed by ?player=Name+With+Pluses; #s= chat tokens are left alone */
function parseHash(){const toks=location.hash.slice(1).split('&');for(const k of ['overrides','buy-sell']){for(const t of toks){const m=t.startsWith(k)&&(t.length===k.length||t[k.length]==='?')?t.slice(k.length+1):null;if(m!==null||t===k){const pm=/(?:^|&)player=([^&]*)/.exec(m||'');return{k,player:pm&&pm[1]?dec(pm[1]):null}}}}return{k:'chart',player:null}}
const hashKey=()=>parseHash().k;
function setTab(k,opts){opts=opts||{};
 tabs.forEach(t=>{const on=t.dataset.tab===k;t.setAttribute('aria-selected',String(on));t.tabIndex=on?0:-1;if(on&&opts.focus)t.focus()});
 Object.keys(panels).forEach(p=>panels[p].hidden=p!==k);
 document.querySelectorAll('[data-for]').forEach(el=>el.hidden=el.dataset.for!==k);
 if(k==='chart'&&V()){V().hideCard();V().render()}
 if(k==='overrides'&&V()&&V().ovRender)V().ovRender();
 if(k==='overrides'&&opts.player&&V()&&V().ovPreselect)V().ovPreselect(opts.player,!!opts.ui);
 if(k==='buy-sell'||hlName)bsHighlight(k==='buy-sell'?(opts.player||null):null,!!opts.ui&&k==='buy-sell');
 if(opts.write){const parts=location.hash.slice(1).split('&').filter(x=>x&&!/^(buy-sell|chart|overrides)(\?|$)/.test(x));if(k!=='chart')parts.push(k+(opts.player?'?player='+encodeURIComponent(opts.player).replace(/%20/g,'+'):''));const base=location.pathname+location.search,url=base+(parts.length?'#'+parts.join('&'):'');if(opts.push){if(url!==base+location.hash)history.pushState(null,'',url)}else history.replaceState(null,'',url)}
}
tabs.forEach((t,i)=>{t.addEventListener('click',()=>setTab(t.dataset.tab,{write:true,push:true}));
 t.addEventListener('keydown',e=>{let j=null;if(e.key==='ArrowRight')j=(i+1)%tabs.length;else if(e.key==='ArrowLeft')j=(i-1+tabs.length)%tabs.length;else if(e.key==='Home')j=0;else if(e.key==='End')j=tabs.length-1;if(j!==null){e.preventDefault();setTab(tabs[j].dataset.tab,{focus:true,write:true,push:true})}})});
function bsHighlight(name,scroll){hlName=name||null;renderLists();
 if(!live)return;
 if(hlName&&scroll){const r=[...document.querySelectorAll('#panel-bs .bs-row')].find(b=>b.dataset.n===hlName);
  if(r){r.focus({preventScroll:true});r.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}else $('bs-hlnote').scrollIntoView({block:'nearest'})}}
V().bsHighlight=bsHighlight;
/* in-page path from a player: switch tab, update the hash (new history entry) and preselect / highlight */
V().go=(k,o)=>{o=o||{};V().hideCard();setTab(k,{write:true,push:true,player:o.player,ui:true})};
addEventListener('hashchange',()=>{const h=parseHash();setTab(h.k,{player:h.player,ui:true})});
setTab(hashKey());
V().ready.then(()=>{const h=parseHash();if(h.player)setTab(h.k,{player:h.player,ui:true})},()=>{});
})();
