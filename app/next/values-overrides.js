(()=>{
/* Overrides tab: your value replaces DDF Value (applied after the pipeline); everything in "What changes" is recomputed here. */
const $=id=>document.getElementById(id);
const V=()=>window.DDFValues;
const OV=()=>window.DDF&&window.DDF.overrides;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const f1=v=>v.toFixed(1),f2=v=>v.toFixed(2);
const sg=(v,d)=>(Math.abs(v)<.005?'±':v>0?'+':'−')+Math.abs(v).toFixed(d);
const short=n=>{const t=n.replace(/\s+(Jr\.?|Sr\.?|II|III|IV)$/,'').split(' ');return t.length>2&&/^St\.?$/.test(t[t.length-2])?t.slice(-2).join(' '):t[t.length-1]};
/* Example numbers copied from build.html (MY_ROSTER: name, pos, DDF Value; Love from TEAM_03) and the Buy / Sell tab (Rice, Metcalf),
   and find.html rows: [partner, give, get, your starters DDF, fit, their starters on analyst charts (key: Market)]. Keep in sync with those pages. */
const MY_ROSTER=[["Josh Allen","QB",41.53],["Bo Nix","QB",0],["Jahmyr Gibbs","RB",96.66],["Rachaad White","RB",7.24],["Rhamondre Stevenson","RB",21.22],["Keaton Mitchell","RB",0.55],["Jaxon Smith-Njigba","WR",79.04],["Stefon Diggs","WR",12.75],["George Pickens","WR",28.81],["Antonio Williams","WR",2.58],["Malachi Fields","WR",0.68],["Trey McBride","TE",36.93],["Dalton Schultz","TE",0]];
const GET_DDF={'Jeremiyah Love':22.72,'Rashee Rice':13.61,'DK Metcalf':12.88};
const PKGS=[['Team 03','Rhamondre Stevenson','Jeremiyah Love',1.50,'natural',1.36],['Team 08','Stefon Diggs','Rashee Rice',0.85,'natural',0.64],['Team 03','Stefon Diggs','DK Metcalf',0.13,'natural',0.08],['Team 07','Bo Nix','Omarion Hampton',0.53,'neutral',0.00]];
const SLOTS={QB:1,RB:2,WR:3,TE:1},FLEX=['RB','WR','TE'];
const D=()=>V().D,pOf=n=>D().find(p=>p.n===n);
const val=(n,fallback,eff)=>{const p=pOf(n);return p?(eff?p.ddf:p.base):fallback};
const buildHref=pk=>'build.html?'+new URLSearchParams({partner:pk[0],give:pk[1],get:pk[2]}).toString();

/* ---- arithmetic ---- */
function lineup(list){/* best lineup DDF total: QB1 RB2 WR3 TE1 + one FLEX (RB/WR/TE) */
 const by={};list.forEach(p=>(by[p.pos]=by[p.pos]||[]).push(p.v));let sum=0;const rest=[];
 Object.keys(by).forEach(pos=>{const k=SLOTS[pos]||0;by[pos].sort((a,b)=>b-a).forEach((v,i)=>{if(i<k)sum+=v;else if(FLEX.includes(pos))rest.push(v)})});
 return rest.length?sum+Math.max(...rest):sum}
const roster=eff=>MY_ROSTER.map(([n,pos,d])=>({n,pos,v:val(n,d,eff)}));
function starterGain(give,get,eff){const r=roster(eff),g=r.find(p=>p.n===give),gv=val(get,GET_DDF[get],eff);if(!g||gv===undefined)return null;
 return lineup(r.filter(p=>p.n!==give).concat([{n:get,pos:g.pos,v:gv}]))-lineup(r)}
/* before = find.html's number; after = that number plus the change in your best-lineup DDF total caused by your overrides */
function pkgEval(pk,eff){const [,give,get,g0,fit,their]=pk,gb=starterGain(give,get,false);
 if(gb===null)return{known:false,your:g0,their,natural:fit==='natural'};
 const your=eff?g0+(starterGain(give,get,true)-gb):g0,raw=val(get,GET_DDF[get],eff)-val(give,(MY_ROSTER.find(r=>r[0]===give)||[])[2],eff);
 return{known:true,your,their,raw,giveV:val(give,0,eff),getV:val(get,GET_DDF[get],eff),natural:fit==='natural'&&your>0&&their>=0}}
function verdict(net,give,get){/* same wording rule as tradechart.js verdictText */
 const big=Math.max(give,get)||1;if(Math.abs(net)<.005)return'Even by DDF Value';
 if(Math.abs(net)/big<=.10)return net>0?'Slight edge to you':'Slight edge to them';
 return net>0?'You get more than you give':'You give more than you get'}
function ranks(eff){const m=new Map();D().map((p,i)=>({p,i})).sort((a,b)=>(eff?b.p.ddf-a.p.ddf:b.p.base-a.p.base)||a.i-b.i).forEach((o,j)=>m.set(o.p.n,j+1));return m}

function compute(){
 const act=D().filter(p=>p.ov),rows=[];
 const r0=ranks(false),r1=ranks(true);
 const rankRows=D().filter(p=>p.ov||r0.get(p.n)!==r1.get(p.n)).sort((a,b)=>r1.get(a.n)-r1.get(b.n)).map(p=>{const b=r0.get(p.n),a=r1.get(p.n);
  return{area:'Rank',p,ov:p.ov,what:p.n+(p.ov?' (your value)':''),before:'#'+b,after:'#'+a,changed:a!==b,up:a<b,href:'#chart',link:'Chart'}});
 rows.push(...rankRows);
 const bs=V().bs,lg=bs.isLeague(),bsRows=[];
 (lg?['sell','buy']:['buy']).forEach(side=>{const fn=side==='sell'?bs.sellList:bs.buyList,b=fn(bs.makeDB(true)).slice(0,5),a=fn(bs.makeDB(false)).slice(0,5),bn=b.map(o=>o.p.n),an=a.map(o=>o.p.n),L=side==='sell'?'Sell':'Buy';
  const gap=o=>sg(Math.abs(o.g.g),2)+' '+o.g.c;
  a.forEach((o,i)=>{const j=bn.indexOf(o.p.n);
   if(j<0)bsRows.push({area:L,what:o.p.n+' enters '+L+' top 5',before:'not in top 5',after:'#'+(i+1)+' · gap '+gap(o),changed:true});
   else if(Math.abs(b[j].g.g-o.g.g)>=.005)bsRows.push({area:L,what:o.p.n+' gap changes',before:'#'+(j+1)+' · gap '+gap(b[j]),after:'#'+(i+1)+' · gap '+gap(o),changed:true});
   else if(i!==j)bsRows.push({area:L,what:o.p.n+' moves in '+L+' top 5',before:'#'+(j+1),after:'#'+(i+1),changed:true})});
  b.forEach((o,j)=>{if(!an.includes(o.p.n))bsRows.push({area:L,what:o.p.n+' leaves '+L+' top 5',before:'#'+(j+1)+' · gap '+gap(o),after:'not in top 5',changed:true})});
 });
 bsRows.forEach(r=>{r.href='#buy-sell';r.link='Buy / Sell'});rows.push(...bsRows);
 const touched=MY_ROSTER.some(r=>{const p=pOf(r[0]);return p&&p.ov});
 const recRows=PKGS.map(pk=>{const a=pkgEval(pk,false),b=pkgEval(pk,true),name=short(pk[1])+' → '+short(pk[2]);
  const fit=e=>pk[4]==='neutral'?'Partner neutral':e.natural?'Natural fit':'Not a natural fit';
  if(!b.known)return{area:'Recommendation',what:name+' ('+pk[0]+')',before:'+'+f2(a.your)+' DDF',after:touched?'not recomputed':'unchanged',changed:false,na:touched,note:touched?'Omarion Hampton has no DDF Value on this page, so this one is not recomputed.':'',href:'find.html',link:'Recommendations'};
  const ch=Math.abs(b.your-a.your)>=.005||a.natural!==b.natural;
  return{area:'Recommendation',what:name+' ('+pk[0]+')',before:sg(a.your,2)+' DDF · '+fit(a),after:sg(b.your,2)+' DDF · '+fit(b),changed:ch,dropped:a.natural&&!b.natural,href:'find.html',link:'Recommendations'}});
 const ord=list=>list.map((e,i)=>({i,y:e.your})).sort((x,y)=>y.y-x.y).map(o=>o.i);
 const o0=ord(PKGS.map(pk=>pkgEval(pk,false))),o1=ord(PKGS.map(pk=>pkgEval(pk,true)));
 const orderChanged=o0.join()!==o1.join();
 if(orderChanged)recRows.push({area:'Recommendation',what:'Order by your gain',before:o0.map(i=>short(PKGS[i][2])).join(', '),after:o1.map(i=>short(PKGS[i][2])).join(', '),changed:true,href:'find.html',link:'Recommendations'});
 rows.push(...recRows);
 const pk=PKGS[0],t0=pkgEval(pk,false),t1=pkgEval(pk,true),pass=e=>e.your>0&&e.their>=0;
 const tradeRows=[
  {area:'Build a Trade',what:'Your starters (DDF)',before:sg(t0.your,2),after:sg(t1.your,2),changed:Math.abs(t1.your-t0.your)>=.005},
  {area:'Build a Trade',what:'Their starters (analyst charts)',before:sg(t0.their,2),after:sg(t1.their,2),changed:false},
  {area:'Build a Trade',what:'Trade checks',before:pass(t0)?'✓ Pass':'Review',after:pass(t1)?'✓ Pass':'Review',changed:pass(t0)!==pass(t1)},
  {area:'Build a Trade',what:'DDF Value verdict',before:verdict(t0.raw,t0.giveV,t0.getV)+' ('+sg(t0.raw,2)+')',after:verdict(t1.raw,t1.giveV,t1.getV)+' ('+sg(t1.raw,2)+')',changed:Math.abs(t1.raw-t0.raw)>=.005}];
 tradeRows.forEach(r=>{r.href=buildHref(pk);r.link='Build a Trade'});
 rows.push(...tradeRows);
 return{act,rows,rankRows,bsRows,recRows,tradeRows,lg,tradeSame:tradeRows.every(r=>!r.changed),verdictSame:tradeRows[2].after===tradeRows[2].before&&verdict(t0.raw,t0.giveV,t0.getV)===verdict(t1.raw,t1.giveV,t1.getV),n:rows.filter(r=>r.changed).length};
}

/* ---- render ---- */
const cell=(b,a,ch)=>`<span class="ov-num">${esc(b)}</span> → <span class="ov-num">${ch?'<strong>'+esc(a)+'</strong>':esc(a)}</span>`;
function areaHTML(title,list,emptyText,max){
 const shown=max?list.slice(0,max):list,more=list.length-shown.length;
 return `<section class="ov-area"><h4>${title}</h4><ul>${shown.length?shown.map(r=>`<li class="${r.changed?'':'same'}">${esc(r.what)}: ${r.na?esc(r.note):cell(r.before,r.after,r.changed)}${r.changed||r.na?'':' · unchanged'}</li>`).join(''):`<li class="same">${esc(emptyText)}</li>`}${more>0?`<li class="same">${more} more in “Show every change”.</li>`:''}</ul></section>`}
function renderWhat(){
 const box=$('ov-what'),c=compute();
 if(!c.act.length){box.innerHTML='<p class="ov-empty">No overrides yet. Set a value above and this panel lists what moves: ranks, the Buy / Sell lists, the example recommendations and the Stevenson → Love trade.</p>';return c}
 const others=c.rankRows.filter(r=>!r.ov&&r.changed),ups=others.filter(r=>r.up),dropped=c.recRows.filter(r=>r.dropped).length,recCh=c.recRows.filter(r=>r.changed).length;
 const bits=c.act.map(p=>{const r=c.rankRows.find(x=>x.p===p);return`<strong>${esc(p.n)}</strong> ${f1(p.base)} → ${f1(p.ddf)} (your value), rank ${r.before.slice(1)} → ${r.after.slice(1)}`});
 const tail=[];
 if(others.length)tail.push(others.length===1?short(others[0].p.n)+(others[0].up?' moves up':' moves down'):others.length+' other players move ('+[ups.length?ups.length+' up':'',others.length-ups.length?(others.length-ups.length)+' down':''].filter(Boolean).join(', ')+')');
 tail.push(c.bsRows.length?c.bsRows.length+' Buy / Sell '+(c.bsRows.length===1?'change':'changes'):'Buy / Sell top 5 unchanged');
 const na=c.recRows.filter(r=>r.na).length,naTxt=na?' ('+na+' not recomputed)':'';
 tail.push((dropped?dropped+' recommendation'+(dropped===1?' drops':'s drop')+' out of natural fit':recCh?recCh+' recommendation '+(recCh===1?'change':'changes'):na?'other recommendations unchanged':'recommendations unchanged')+naTxt);
 tail.push('Stevenson → Love verdict '+(c.verdictSame?'unchanged':'changes'));
 const every=c.rows.filter(r=>r.changed||r.na);
 box.innerHTML=`<p class="ov-sum">${bits.join('; ')}. ${esc(tail.join(' · '))}.</p><div class="ov-areas">`+
  areaHTML('Rank by DDF Value',c.rankRows,'No rank changes.',8)+
  areaHTML('Buy / Sell'+(c.lg?'':' (Buy list; Sell needs your league)'),c.bsRows,'Top 5 unchanged.',6)+
  areaHTML('Recommendations',c.recRows,'',0)+
  areaHTML('Build a Trade · Stevenson → Love',c.tradeRows,'',0)+
  `</div><p class="bs-note" style="margin-top:12px">Trade &amp; Waiver Recommendations and Build a Trade still show DDF’s own numbers; the “after” values here are computed on this page.</p>`+
  `<details class="ov-every"><summary>Show every change (${every.length})</summary>${every.length?`<table><thead><tr><th scope="col">Area</th><th scope="col">Change</th><th scope="col">Before → after</th><th scope="col">Open</th></tr></thead><tbody>${every.map(r=>`<tr><td>${esc(r.area)}</td><td>${esc(r.what)}</td><td>${r.na?esc(r.note):cell(r.before,r.after,true)}</td><td><a href="${esc(r.href)}">${esc(r.link)}</a></td></tr>`).join('')}</tbody></table>`:'<p class="ov-empty">Your values differ from DDF’s, but nothing computed here moves.</p>'}</details>`;
 return c;
}
function renderActive(){
 const o=OV()?OV().get():{},names=Object.keys(o),n=names.length;
 $('ov-n').textContent=n;$('ov-clear').hidden=!n;const L=window.DDF&&DDF.link;$('ov-copylink').hidden=!(n&&L&&typeof L.encode==='function'&&typeof DDF.copyText==='function');$('ov-chat').hidden=!(n&&L&&typeof L.copyForChat==='function'&&L.current&&L.current());if(!n)$('ov-loaded').hidden=true;const tb=$('ov-tabn');tb.hidden=!n;tb.textContent=n;tb.setAttribute('aria-label',n+(n===1?' override':' overrides'));
 $('ov-active').innerHTML=n?names.map(nm=>{const p=pOf(nm),v=+o[nm];
  if(!p)return`<li><div class="ov-who"><strong>${esc(nm)}</strong><span>Yours ${f1(v)} · not on this page, so nothing is computed here</span></div><div class="ov-acts"><button type="button" class="btn" data-rm="${esc(nm)}" aria-label="Remove override for ${esc(nm)}">Remove</button></div></li>`;
  const d=v-p.base;return`<li><div class="ov-who"><strong>${esc(nm)} <span class="pos pos-${p.pos}">${p.pos}</span></strong><span>DDF ${f1(p.base)} → Yours ${f1(v)} <span class="ov-d ${d>=0?'up':'dn'}">${sg(d,1)}</span></span></div><div class="ov-acts"><button type="button" class="btn" data-edit="${esc(nm)}" aria-label="Edit override for ${esc(nm)}">Edit</button><button type="button" class="btn" data-rm="${esc(nm)}" aria-label="Remove override for ${esc(nm)}">Remove</button></div></li>`}).join(''):'<li class="ov-empty">None yet. Pick a player and set your value; every tab then uses it in place of DDF Value.</li>';
}
let cur=null;
function renderEditor(keepField){
 const p=cur&&pOf(cur);$('ov-editor').hidden=!p;if(!p)return;
 $('ov-name').textContent=p.n;$('ov-pos').className='pos pos-'+p.pos;$('ov-pos').textContent=p.pos;$('ov-team').textContent=p.team+(p.star?' · ★ your player':'');
 $('ov-ddf').textContent=f1(p.base);$('ov-mkt').textContent=f1(V().bs.marketOf(p));
 const cv=$('ov-cur');cv.textContent=p.ov?f1(p.ddf):'= DDF';cv.className=p.ov?'yours':'';
 if(!keepField){const v=p.ov?p.ddf:p.base;$('ov-num').value=+v.toFixed(2);$('ov-range').value=v}
 $('ov-apply').textContent=p.ov?'Update override':'Set override';$('ov-reset').disabled=!p.ov;
 preview();
}
function readNum(){const s=$('ov-num').value.trim(),v=+s;return s!==''&&isFinite(v)&&v>=0&&v<=100?Math.round(v*100)/100:null}
function preview(){
 const p=cur&&pOf(cur);if(!p)return;const v=readNum();
 $('ov-err').textContent=v===null?'Enter a value from 0 to 100.':'';
 if(v===null){$('ov-preview').textContent='';return}
 const sorted=D().map(q=>({n:q.n,v:q.n===p.n?v:q.ddf})).sort((a,b)=>b.v-a.v),r=sorted.findIndex(q=>q.n===p.n)+1,r0=ranks(false).get(p.n);
 $('ov-preview').textContent=Math.abs(v-p.base)<.005?'Same as DDF Value (rank #'+r0+').':'At '+f1(v)+' ('+sg(v-p.base,1)+' vs DDF): rank #'+r0+' → #'+r+' by DDF Value.';
}
function renderAll(){renderActive();renderEditor(true);renderWhat()}
function announce(msg){const l=$('ov-live');l.textContent='';setTimeout(()=>{l.textContent=msg},60)}
let sig=null;const sigNow=()=>JSON.stringify(OV()?OV().get():{});
/* overrides can also change from outside this tab's controls (e.g. a link loading them); re-render when the stored set differs */
document.addEventListener('ddf:overrides',()=>queueMicrotask(()=>{if(sigNow()!==sig){const c=onChange();linkNote();announce('Overrides updated. '+c.n+(c.n===1?' change.':' changes.'))}}));
function onChange(){sig=sigNow();const v=V();v.applyOverrides();v.hideCard();v.render();v.bs.refresh();renderActive();renderEditor(false);const c=renderWhat();return c}

/* ---- picker (combobox) ---- */
let opts=[],act=-1;
const inp=$('ov-search'),list=$('ov-list');
function openList(){const q=inp.value.trim().toLowerCase();opts=D().filter(p=>p.n.toLowerCase().includes(q));if(act>=opts.length)act=opts.length-1;
 list.innerHTML=opts.length?opts.map((p,i)=>`<li role="option" id="ov-o${i}" data-n="${esc(p.n)}" aria-selected="${i===act}"><span>${esc(p.n)} <span class="pos pos-${p.pos}">${p.pos}</span>${p.ov?'<span class="ov-badge">Yours</span>':''}</span><small>DDF ${f1(p.base)}</small></li>`).join(''):'<li class="none" role="option" aria-disabled="true" aria-selected="false">No player on this page matches.</li>';
 list.hidden=false;inp.setAttribute('aria-expanded','true');
 if(act>=0){inp.setAttribute('aria-activedescendant','ov-o'+act);const el=$('ov-o'+act);if(el)el.scrollIntoView({block:'nearest'})}else inp.removeAttribute('aria-activedescendant')}
function closeList(){list.hidden=true;inp.setAttribute('aria-expanded','false');inp.removeAttribute('aria-activedescendant');act=-1}
function pick(n){cur=n;inp.value=n;closeList();$('ov-saved').hidden=true;renderEditor(false);$('ov-num').focus();$('ov-num').select()}
inp.addEventListener('input',()=>{act=inp.value.trim()?0:-1;openList()});
inp.addEventListener('click',()=>{if(list.hidden)openList()});
inp.addEventListener('keydown',e=>{
 if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(list.hidden){act=e.key==='ArrowDown'?0:opts.length-1;openList();return}const n=opts.length;if(!n)return;act=e.key==='ArrowDown'?(act+1)%n:(act-1+n)%n;openList()}
 else if(e.key==='Enter'){if(!list.hidden&&opts.length){e.preventDefault();pick(opts[Math.max(0,act)].n)}}
 else if(e.key==='Escape'){if(!list.hidden){e.preventDefault();e.stopPropagation();closeList()}}});
inp.addEventListener('blur',()=>setTimeout(()=>{if(document.activeElement!==inp)closeList()},150));
list.addEventListener('mousedown',e=>e.preventDefault());
list.addEventListener('click',e=>{const li=e.target.closest('li[data-n]');if(li)pick(li.dataset.n)});

/* ---- editor ---- */
$('ov-num').addEventListener('input',()=>{const v=readNum();if(v!==null)$('ov-range').value=v;preview()});
$('ov-num').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('ov-apply').click()}});
$('ov-range').addEventListener('input',()=>{$('ov-num').value=(+$('ov-range').value).toFixed(1);preview()});
$('ov-apply').addEventListener('click',()=>{const p=cur&&pOf(cur),v=readNum();if(!p)return;if(v===null){preview();$('ov-num').focus();return}
 if(!OV()){$('ov-err').textContent='Overrides are not available in this browser.';return}
 if(Math.abs(v-p.base)<.005){if(p.ov)OV().remove(p.n);$('ov-saved').hidden=true;const c=onChange();announce(p.n+' is back to DDF Value. '+c.n+(c.n===1?' change.':' changes.'));return}
 OV().set(p.n,v);const c=onChange();showSaved(p.n,v);announce('Override set: '+p.n+' '+f1(v)+'. '+c.n+(c.n===1?' change.':' changes.'));
 if(window.DDF&&DDF.celebrate&&c.n&&!matchMedia('(prefers-reduced-motion:reduce)').matches)DDF.celebrate($('ov-apply'))});
$('ov-reset').addEventListener('click',()=>{const p=cur&&pOf(cur);if(!p)return;if(p.ov&&OV())OV().remove(p.n);$('ov-saved').hidden=true;const c=onChange();announce(p.n+' reset to DDF Value. '+c.n+(c.n===1?' change.':' changes.'));$('ov-num').focus()});
function clearAll(){if(!OV())return;OV().clear();$('ov-saved').hidden=true;onChange();$('ov-loaded').hidden=true;announce('All overrides removed. Every tab uses DDF Value again.');inp.focus()}
$('ov-clear').addEventListener('click',clearAll);$('ov-loaded-clear').addEventListener('click',clearAll);
/* sharing: DDF.link carries DDF.overrides in links and chat blocks; feature-tested because the engine may still be landing */
const DEFAULT_SETTINGS={scoring:'half_ppr',teams:12,superflex:false,slots:[1,2,3,1,1,6]};
$('ov-copylink').addEventListener('click',()=>{const L=window.DDF&&DDF.link,st=$('ov-share');if(!L||!L.encode)return;
 const cur=L.current&&L.current(),state=Object.assign({},cur||{settings:DEFAULT_SETTINGS},{view:'values'});
 L.encode(state,{page:'values.html'}).then(url=>DDF.copyText(url,st,'Link copied.'),()=>{st.textContent='Could not make a link in this browser.'})});
$('ov-chat').addEventListener('click',()=>{const L=window.DDF&&DDF.link;if(L&&L.copyForChat)L.copyForChat($('ov-share'))});
$('ov-active').addEventListener('click',e=>{const ed=e.target.closest('[data-edit]'),rm=e.target.closest('[data-rm]');
 if(ed){cur=ed.dataset.edit;inp.value=cur;renderEditor(false);$('ov-pick-h').scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});$('ov-num').focus();$('ov-num').select();return}
 if(rm&&OV()){const n=rm.dataset.rm,btns=[...$('ov-active').querySelectorAll('[data-rm]')],i=btns.indexOf(rm);OV().remove(n);const c=onChange();announce('Override removed: '+n+'. '+c.n+(c.n===1?' change.':' changes.'));
  const nb=[...$('ov-active').querySelectorAll('[data-rm]')];(nb[Math.min(i,nb.length-1)]||inp).focus()}});

/* ---- start: site.js (deferred) provides DDF.overrides before DOMContentLoaded ---- */
V().ovRender=renderAll;
/* preselect a player in the picker (from the Chart tab actions or #overrides?player=Name) */
V().ovPreselect=(n,focus)=>{const q=D().find(p=>p.n.toLowerCase()===String(n).toLowerCase());if(!q)return;cur=q.n;inp.value=q.n;closeList();$('ov-saved').hidden=true;renderEditor(false);
 if(focus){$('ov-pick-h').scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});$('ov-num').focus();$('ov-num').select()}};
function showSaved(n,v){const s=$('ov-saved'),q=encodeURIComponent(n).replace(/%20/g,'+');s.innerHTML='Saved: '+esc(n)+' at '+f1(v)+'. <a href="#buy-sell?player='+q+'">See it in Buy / Sell</a> · <a href="find.html">See it in Trade &amp; Waiver Recommendations</a>';s.hidden=false}
function linkNote(){const L=window.DDF&&DDF.link,n=OV()?OV().count():0;
 if(n&&L&&L.current&&L.current()){$('ov-loaded-t').textContent='Loaded from your link: '+n+(n===1?' override':' overrides');$('ov-loaded').hidden=false}
 const chip=$('vchip-ctx');let t='';try{t=L&&typeof L.describeContext==='function'?String(L.describeContext()||''):''}catch(_){}chip.textContent=t;chip.hidden=!t}
function start(){sig=sigNow();const v=V();v.applyOverrides();if(D().some(p=>p.ov)){v.render();v.bs.refresh()}renderAll();
 const r=window.DDF&&DDF.link&&DDF.link.ready;if(r&&r.then)r.then(()=>{onChange();linkNote()},()=>linkNote());else linkNote()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
