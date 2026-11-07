(()=>{
const $=id=>document.getElementById(id);
const V=()=>window.DDFValues;
/* Analyst-charts averages (CBS Sports, FantasyPros, USA Today; key: mkt) for the players the old compare page priced; every other player uses the average of the two indexed charts on this page. */
const PUB={'Stefon Diggs':17.30,'Rhamondre Stevenson':21.71,'Josh Allen':25.87,'Jahmyr Gibbs':61.03};
const EXTRA=[['Rashee Rice','WR',13.61,16.65,'Team 08'],['DK Metcalf','WR',12.88,17.22,'Team 03']];
const FIT_OVERRIDE={'Stefon Diggs>Rashee Rice':{your:0.85,their:0.64}};
const f2=v=>v.toFixed(2),sg=v=>(v>=0?'+':'−')+Math.abs(v).toFixed(2);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const short=n=>{const t=n.replace(/\s+(Jr\.?|Sr\.?|II|III|IV)$/,'').split(' ');return t.length>2&&/^St\.?$/.test(t[t.length-2])?t.slice(-2).join(' '):t[t.length-1]};
const SHOW=5;
let hlName=null,DB=[],league=false,expanded={sell:false,buy:false},sel={give:null,get:null,chip:'',side:'sell'};

function baseDB(useBase){
 const d=V().D.map(p=>{const pub=PUB[p.n];return{n:p.n,pos:p.pos,ddf:useBase?p.base:p.ddf,base:p.base,ov:!useBase&&!!p.ov,mkt:pub!==undefined?pub:(p.cbs+p.fc)/2,charts:pub!==undefined?[['analyst charts',pub]]:[['CBS',p.cbs],['FantasyCalc',p.fc]],srcs:pub!==undefined?3:2,owner:p.team,yours:p.star,wk:null}});
 EXTRA.forEach(([n,pos,ddf,mkt,owner])=>d.push({n,pos,ddf,base:ddf,ov:false,mkt,charts:[['analyst charts',mkt]],srcs:3,owner,yours:false,wk:null}));
 return d;
}
function leagueCtx(){
 const st=window.DDF&&DDF.link&&DDF.link.current&&DDF.link.current();
 if(!st||!Array.isArray(st.teams)||st.me==null||!st.teams[st.me])return null;
 const owner=new Map(),mine=new Set();
 st.teams.forEach((t,i)=>(t.players||[]).forEach(e=>{let n;try{n=DDF.link.playerName(e)}catch(_){return}if(i===st.me)mine.add(n);else owner.set(n,t.name||('Team '+(i+1)))}));
 return{owner,mine};
}
/* makeDB(true) = the lists on DDF's own values; makeDB() = with your overrides (what the tab shows). No side effects. */
function makeDB(useBase){
 const all=baseDB(useBase),ctx=leagueCtx();let d;
 if(ctx)d=all.filter(p=>ctx.mine.has(p.n)||ctx.owner.has(p.n)).map(p=>Object.assign(p,{yours:ctx.mine.has(p.n),owner:ctx.mine.has(p.n)?'Your team':ctx.owner.get(p.n)}));
 else d=all.filter(p=>!p.yours).map(p=>Object.assign(p,{owner:null}));
 return d.filter(p=>p.ddf>0&&p.mkt>0);
}
function build(){
 const ctx=leagueCtx();league=!!ctx;
 if(ctx&&V().setYours)V().setYours(ctx.mine);
 DB=makeDB();
}
function gapOf(p){/* largest gap vs any chart shown, signed DDF minus chart */
 let best=null;p.charts.forEach(([c,v])=>{const g=p.ddf-v;if(!best||Math.abs(g)>Math.abs(best.g))best={g,c}});return best;
}
function pairStats(give,get){
 const o=FIT_OVERRIDE[give.n+'>'+get.n];
 const your=o?o.your+(get.ddf-get.base)-(give.ddf-give.base):get.ddf-give.ddf,their=o?o.their:give.mkt-get.mkt,same=give.pos===get.pos;
 return{your,their,same,natural:same&&your>0&&their>=0};
}
function sellList(db){return (db||DB).filter(p=>p.yours&&p.mkt>p.ddf).map(p=>({p,g:gapOf(p)})).sort((a,b)=>Math.abs(b.g.g)-Math.abs(a.g.g))}
function buyList(db){return (db||DB).filter(p=>!p.yours&&p.ddf>p.mkt).map(p=>({p,g:gapOf(p)})).sort((a,b)=>Math.abs(b.g.g)-Math.abs(a.g.g))}
function comparables(give){return DB.filter(p=>!p.yours&&p.pos===give.pos).map(p=>({p,s:pairStats(give,p)})).sort((a,b)=>(b.s.natural-a.s.natural)||(Math.min(b.s.your,b.s.their)-Math.min(a.s.your,a.s.their))).slice(0,4)}
function gives(get){const mine=DB.filter(p=>p.yours),same=mine.filter(p=>p.pos===get.pos),pool=same.length?same:mine;return pool.map(p=>({p,s:pairStats(p,get)})).sort((a,b)=>(b.s.natural-a.s.natural)||(Math.min(b.s.your,b.s.their)-Math.min(a.s.your,a.s.their))).slice(0,4)}
const byName=n=>DB.find(p=>p.n===n);
/* Charts count: how many of the four charts (three analyst charts + the live market) went into p.mkt. */
const CHART_NAMES=p=>p.srcs>=3?'CBS Sports, USA Today and FantasyPros (analyst charts)':p.srcs===2?'CBS Sports (analyst chart) and FantasyCalc (live market)':'one chart';
function srcCount(p){const n=Math.min(4,p.srcs);return `<span class="bs-cnt" role="img" aria-label="${n} of 4 charts" title="${n} of 4 charts: ${CHART_NAMES(p)}">${n}/4</span>`}
function wkBadge(p){return p.wk?`<span class="bs-wk">Wk ${p.wk}</span>`:''}
function fitTag(p){/* natural fit for a buy row = some one-for-one give of yours works */
 if(!league)return'';const g=gives(p);return g.length&&g[0].s.natural?'<span class="bs-tag nf">Natural fit</span>':''}
function rowHTML(o,side){
 const p=o.p,g=o.g,cls=side==='sell'?'mh':'dg',chart=g.c,chartLong=g.c==='FantasyCalc'?'live market (FantasyCalc)':g.c;
 const label=`${p.n}, ${p.pos}${p.owner&&side==='buy'?', '+p.owner:''}. ${p.ov?'Your value '+f2(p.ddf)+' (override; DDF '+f2(p.base)+')':'DDF '+f2(p.ddf)}, charts ${f2(p.mkt)} (${Math.min(4,p.srcs)} of 4 charts), largest gap ${sg(Math.abs(g.g))} on ${chartLong}. Select to see a swap.`;
 const sub=side==='buy'?`<small>${esc(p.pos)}${p.owner?' · '+esc(p.owner):''}${wkBadge(p)}</small>`:`<small>${esc(p.pos)}${wkBadge(p)}</small>`;
 return `<li><button type="button" class="bs-row" data-side="${side}" data-n="${esc(p.n)}" aria-pressed="false" aria-label="${esc(label)}"><span class="bs-name"><strong>${p.yours?'<span aria-hidden="true">★</span> ':''}${esc(p.n)}</strong>${p.yours?'<span class="bs-yours">Yours</span>':''}${p.ov?'<span class="bs-ovr">Your value</span>':''}${p.srcs<2?'<span class="bs-flag">◐ 1 source</span>':''}${sub}${side==='buy'?fitTag(p):''}</span><span class="bs-n bs-ddf" data-label="${p.ov?'Your value':'DDF'}">${f2(p.ddf)}</span><span class="bs-n bs-mkt" data-label="Charts">${f2(p.mkt)} ${srcCount(p)}</span><span class="bs-gap"><span class="bs-tag ${cls}">${sg(Math.abs(g.g))} ${esc(chart)}</span></span></button><div class="vp-bs"><button type="button" class="vp-act" data-act="own" data-n="${esc(p.n)}" aria-label="Set your own value for ${esc(p.n)}">Set your own value</button></div></li>`;
}
function renderList(side){
 const items=side==='sell'?sellList():buyList(),ul=$('bs-'+side),btn=$('bs-'+side+'-more'),open=expanded[side],shown=open?items:items.slice(0,SHOW);
 ul.innerHTML=shown.length?shown.map(o=>rowHTML(o,side)).join(''):`<li class="bs-empty">${side==='sell'?'None of your players are priced higher by the charts than by DDF in this snapshot.':'No players are priced higher by DDF than by the charts in this snapshot.'}</li>`;
 const extra=items.length-SHOW;btn.hidden=extra<=0;btn.setAttribute('aria-expanded',String(open));btn.textContent=open?'Show fewer ▴':`Show ${extra} more ▾`;
}
function hlFind(){if(!hlName)return null;let i=sellList().findIndex(o=>o.p.n===hlName);if(i>=0&&league)return['sell',i];i=buyList().findIndex(o=>o.p.n===hlName);return i>=0?['buy',i]:null}
function hlNote(){const n=$('bs-hlnote');if(!hlName){n.hidden=true;return}
 if(hlFind()){n.hidden=true;return}
 const p=D0().find(q=>q.n===hlName),yours=p&&(p.star||(leagueCtx()&&leagueCtx().mine.has(hlName)));
 n.textContent=league?hlName+' is not on the Buy or Sell lists: '+(yours?'the charts do not rate this player above DDF Value.':'DDF Value does not rate this player above the charts.'):'Add your league to see whether '+hlName+' is a sell. The Buy list shows players DDF Value rates above the charts.';
 n.hidden=false}
const D0=()=>V().D;
function renderLists(){
 const hf=hlFind();if(hf&&hf[1]>=SHOW)expanded[hf[0]]=true;
 $('bs-nolg').hidden=league;$('bs-sell-card').hidden=!league;
 $('bs-buy-note').textContent=league?'League-wide players DDF likes more than the charts · owner and fit · top 5':'Players DDF likes more than the charts · top 5';
 const two=document.querySelector('.bs-two');two.classList.toggle('solo',!league);two.style.gridTemplateColumns=league?'':'minmax(0,1fr)';
 renderList('sell');renderList('buy');syncPressed();hlNote();
}
function syncPressed(){
 document.querySelectorAll('.bs-list li').forEach(li=>{const r=li.querySelector('.bs-row');li.classList.toggle('bs-hl',!!(hlName&&r&&r.dataset.n===hlName))});
 document.querySelectorAll('.bs-row').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.side==='sell'?b.dataset.n===sel.give:b.dataset.n===sel.get)));
 document.querySelectorAll('.bs-opt').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.n===(sel.side==='sell'?sel.get:sel.give))));
}
function renderPick(){
 const box=$('bs-pick');
 if(!league||(sel.side==='sell'&&!byName(sel.give))||(sel.side==='buy'&&!byName(sel.get))){box.hidden=true;return}
 const anchor=byName(sel.side==='sell'?sel.give:sel.get),opts=sel.side==='sell'?comparables(anchor):gives(anchor);
 $('bs-pick-h').textContent=sel.side==='sell'?'Comparable targets for '+anchor.n:'Players to give for '+anchor.n;
 $('bs-pick-note').textContent=sel.side==='sell'?'Same position, natural fit first. Pick one to compare.':'Your players nearest in value, natural fit first. Pick one to compare.';
 $('bs-opts').innerHTML=opts.map(({p,s})=>`<button type="button" class="bs-opt" data-n="${esc(p.n)}" aria-pressed="false"><strong>${p.yours?'★ ':''}${esc(p.n)} · ${esc(p.pos)}${p.owner&&!p.yours?' · '+esc(p.owner):''}</strong><span class="bs-meta">DDF ${f2(p.ddf)} / Charts ${f2(p.mkt)}</span><span class="bs-tag ${s.natural?'nf':'ck'}">${s.natural?'Natural fit':'Check fit'}</span></button>`).join('')||'<p class="bs-empty">No comparable players in this league.</p>';
 box.hidden=false;
}
function check(cls,txt,sr){return `<li><span class="${cls}" aria-hidden="true">${cls==='ok'?'✓':cls==='no'?'✕':'•'}</span> <span class="vsr">${sr}: </span>${txt}</li>`}
function renderDetail(pop){
 const d=$('bs-detail'),give=byName(sel.give),get=byName(sel.get);
 if(!get&&!give){d.hidden=true;return}
 d.hidden=false;
 $('bs-chip').textContent='After selecting '+sel.chip;
 $('bs-title').textContent=give&&get?short(give.n)+' → '+short(get.n):'Target: '+get.n;
 const row=p=>`<tr><td>${p.yours?'★ ':''}${esc(short(p.n))} · ${esc(p.pos)}${p.ov?' <span class="bs-ovr">Your value</span>':''}</td><td>${f2(p.ddf)}</td><td>${f2(p.mkt)} ${srcCount(p)}</td></tr>`;
 $('bs-vals').innerHTML=(give?row(give):'')+(get?row(get):'');
 const fit=$('bs-fit');
 if(give&&get){const s=pairStats(give,get);
  fit.innerHTML=`<div class="bs-fithead"><h4>Roster fit</h4><span class="bs-tag ${s.natural?'nf':'ck'}">${s.natural?'Natural fit':'Not a natural fit'}</span></div><ul class="bs-checks">`+
   check(s.your>0?'ok':'no',`Your DDF starters ${sg(s.your)}`,s.your>0?'Pass':'Fail')+
   check(s.their>=0?'ok':'no',`Their starters on the charts ${sg(s.their)}`,s.their>=0?'Pass':'Fail')+
   (s.same?check('ok','Both rosters valid','Pass')+check('ok','Starting slots filled','Pass'):check('na','Roster slots change when positions differ. Confirm in Build a Trade.','Check'))+'</ul>';
 }else{
  fit.innerHTML=`<div class="bs-fithead"><h4>Roster fit</h4></div><p class="bs-note">Add your league to see which of your players to give and whether it is a natural fit.</p><a class="btn" href="connect.html">Add your league</a>`;
 }
 const q=[];if(give)q.push('give='+encodeURIComponent(give.n));if(get)q.push('get='+encodeURIComponent(get.n));
 $('bs-open').href='build.html'+(q.length?'?'+q.join('&'):'');
 if(pop){d.classList.remove('pop');void d.offsetWidth;d.classList.add('pop')}
}
function choose(side,name,fromRow){
 const p=byName(name);if(!p)return;
 if(fromRow){
  sel.side=side;sel.chip=name;
  if(side==='sell'){sel.give=name;const c=comparables(p);sel.get=c.length?c[0].p.n:null}
  else{sel.get=name;if(league){const g=gives(p);sel.give=g.length?g[0].p.n:null}else sel.give=null}
  renderPick();
 }else{
  sel.chip=name;if(sel.side==='sell')sel.get=name;else sel.give=name;
 }
 syncPressed();renderDetail(true);
 const d=$('bs-detail');if(fromRow&&!d.hidden){const r=d.getBoundingClientRect();if(r.top>innerHeight*.85||r.bottom<0)d.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}
}
function defaultSel(){
 sel={give:null,get:null,chip:'',side:'sell'};
 if(!league)return;
 const sells=sellList();if(!sells.length){const b=buyList();if(b.length)choose('buy',b[0].p.n,true);return}
 const diggs=sells.find(o=>o.p.n==='Stefon Diggs'),first=diggs||sells[0];
 choose('sell',first.p.n,true);
 if(diggs&&byName('Rashee Rice')){sel.get='Rashee Rice';sel.chip='Rashee Rice';renderPick();syncPressed();renderDetail(false)}
}
function init(){build();renderLists();defaultSel();if(!league){renderPick();renderDetail(false)}}
/* re-price after an override change, keeping the current selection when it still exists */
function refresh(){build();renderLists();const ok=sel.side==='sell'?byName(sel.give):byName(sel.get);if(!ok)defaultSel();else{renderPick();syncPressed();renderDetail(false)}}
V().bs={makeDB,sellList,buyList,gapOf,isLeague:()=>league,refresh,marketOf:p=>PUB[p.n]!==undefined?PUB[p.n]:(p.cbs+p.fc)/2};
document.addEventListener('click',e=>{
 const r=e.target.closest('.bs-row');if(r){choose(r.dataset.side,r.dataset.n,true);return}
 const o=e.target.closest('.bs-opt');if(o){choose(sel.side,o.dataset.n,false);return}
 const m=e.target.closest('.bs-more');if(m){const s=m.id==='bs-sell-more'?'sell':'buy';expanded[s]=!expanded[s];renderList(s);syncPressed();$('bs-'+s+'-more').focus()}
});
init();
document.addEventListener('DOMContentLoaded',()=>{const r=window.DDF&&DDF.link&&DDF.link.ready;if(r&&r.then)r.then(()=>{init()})});
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
 if(hlName&&scroll){const r=[...document.querySelectorAll('#panel-bs .bs-row')].find(b=>b.dataset.n===hlName);
  if(r){r.focus({preventScroll:true});r.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}else $('bs-hlnote').scrollIntoView({block:'nearest'})}}
V().bsHighlight=bsHighlight;
/* in-page path from a player: switch tab, update the hash (new history entry) and preselect / highlight */
V().go=(k,o)=>{o=o||{};V().hideCard();setTab(k,{write:true,push:true,player:o.player,ui:true})};
addEventListener('hashchange',()=>{const h=parseHash();setTab(h.k,{player:h.player,ui:true})});
setTab(hashKey());
document.addEventListener('DOMContentLoaded',()=>{const h=parseHash();if(h.player)setTab(h.k,{player:h.player})});
})();
