(()=>{
// Overrides tab: live engine + all players + basis section. No inline sample data.
// JEG-1535: runs on DDF.engine and DDFValues; zero demo/example/illustrative data.

const $=id=>document.getElementById(id);
const E=()=>window.DDF&&window.DDF.engine;
const V=()=>window.DDFValues;
const VL=()=>window.DDFValueLink;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const f1=v=>(typeof v==='number'&&isFinite(v))?v.toFixed(1):'—';
const sg=v=>(typeof v==='number'&&isFinite(v))?(Math.abs(v)<0.05?'±':v>0?'+':'−')+Math.abs(v).toFixed(1):'—';
const isAdj=e=>!!(e&&typeof e==='object'&&e.type==='adjustment');
const NEAR=4,LINK_BUDGET=1800;

/* basis config */
const SINGLE_ORDER=['fantasycalc','usatoday','fantasypros','cbs','espn','cbsros','razzball'];
const DEFAULT_SOURCES=['fantasycalc','usatoday','fantasypros','cbs'];
const SRC_LABELS={espn:'ESPN',cbsros:'CBS rest of season',razzball:'Razzball',fantasycalc:'FantasyCalc',usatoday:'USA Today',fantasypros:'FantasyPros',cbs:'CBS trade chart'};
const labelOf=k=>SRC_LABELS[k]||k;
function bKeys(){const vl=VL();return vl&&vl.BASIS_KEYS?vl.BASIS_KEYS:['espn','cbsros','razzball','fantasycalc','usatoday','fantasypros','cbs']}
let bMode='default',bSingle='fantasycalc',bBlend={};
function blankBlend(){const o={};bKeys().forEach(k=>{o[k]={on:DEFAULT_SOURCES.includes(k),w:25}});return o}
bBlend=blankBlend();

function syncBasisFromEngine(){
  const e=E();if(!e)return;
  const rec=e.basis();
  if(!rec||rec.mode==='default'){bMode='default';bBlend=blankBlend();return}
  if(rec.mode==='single'){bMode='single';bSingle=rec.source||'fantasycalc';return}
  if(rec.mode==='blend'){
    bMode='blend';const nb=blankBlend();bKeys().forEach(k=>{nb[k].on=false});
    (rec.sources||[]).forEach(k=>{if(nb[k]!=null){nb[k].on=true;nb[k].w=rec.weights&&rec.weights[k]!=null?rec.weights[k]:25}});
    bBlend=nb;
  }
}

function isUsable(key){
  const e=E();if(!e)return true;
  const info=e.basisInfo();if(!info||!info.sourceStates)return true;
  const st=info.sourceStates.find(s=>s.key===key);return !st||st.usable;
}

function usableReason(key){
  const e=E();if(!e)return'Not available this week';
  const info=e.basisInfo();if(!info||!info.sourceStates)return'Not available this week';
  const st=info.sourceStates.find(s=>s.key===key);
  return(st&&!st.usable&&st.reason)?st.reason:'Not available this week';
}

function basisRecordLocal(){
  if(bMode==='single')return{mode:'single',source:bSingle};
  if(bMode==='blend'){
    const on=bKeys().filter(k=>bBlend[k]&&bBlend[k].on);
    return on.length?{mode:'blend',sources:on,weights:Object.fromEntries(on.map(k=>[k,bBlend[k].w]))}:{mode:'default'};
  }
  return{mode:'default'};
}

function percents(){
  const on=bKeys().filter(k=>bBlend[k]&&bBlend[k].on&&isUsable(k));
  if(!on.length)return{};
  const total=on.reduce((s,k)=>s+(bBlend[k].w||1),0);
  const ex=on.map(k=>[k,100*(bBlend[k].w||1)/total]);
  const out=Object.fromEntries(ex.map(([k,v])=>[k,Math.floor(v)]));
  let left=100-Object.values(out).reduce((a,b)=>a+b,0);
  ex.slice().sort((a,b)=>(b[1]-Math.floor(b[1]))-(a[1]-Math.floor(a[1]))).forEach(([k])=>{if(left>0){out[k]+=1;left-=1}});
  return out;
}

function applyBasis(){
  const e=E();if(!e)return;
  const rec=basisRecordLocal();e.setBasis(rec.mode==='default'?null:rec);
}

/* picker state */
let cur=null;let mode='absolute';let opts=[],act=-1;
const inp=$('ov-search'),list=$('ov-list');

function getAllPlayers(){const e=E();return e?e.players():[]}
function pRec(key){const e=E();return e&&key!=null?e.player(String(key)):null}

/* combobox */
function openList(){
  if(!inp||!list)return;
  const q=inp.value.trim().toLowerCase();
  if(!q){list.innerHTML='<li class="none" role="option" aria-disabled="true" aria-selected="false">Search a player by name.</li>';list.hidden=false;inp.setAttribute('aria-expanded','true');act=-1;inp.removeAttribute('aria-activedescendant');return}
  const e=E();const oAll=e?e.overrides.all():{};
  opts=getAllPlayers().filter(p=>p.n.toLowerCase().includes(q)).slice(0,50);
  if(act>=opts.length)act=opts.length-1;
  list.innerHTML=opts.length?opts.map((p,i)=>`<li role="option" id="ov-o${i}" data-k="${esc(p.key)}" aria-selected="${i===act}"><span>${esc(p.n)} <span class="pos pos-${esc(p.pos)}">${esc(p.pos)}</span>${oAll[p.key]!=null?'<span class="ov-badge">Yours</span>':''}</span><small>DDF ${f1(p.ddf)}</small></li>`).join(''):'<li class="none" role="option" aria-disabled="true" aria-selected="false">No player matches.</li>';
  list.hidden=false;inp.setAttribute('aria-expanded','true');
  if(act>=0){inp.setAttribute('aria-activedescendant','ov-o'+act);const el=$('ov-o'+act);if(el)el.scrollIntoView({block:'nearest'})}else inp.removeAttribute('aria-activedescendant');
}

function closeList(){if(!list||!inp)return;list.hidden=true;inp.setAttribute('aria-expanded','false');inp.removeAttribute('aria-activedescendant');act=-1}

function pick(key){
  cur=key;const p=pRec(key);
  if(p&&inp)inp.value=p.n;closeList();
  const sv=$('ov-saved');if(sv)sv.hidden=true;
  renderEditor(false);const num=$('ov-num');if(num){num.focus();num.select()}
}

if(inp){
  inp.addEventListener('input',()=>{act=inp.value.trim()?0:-1;openList()});
  inp.addEventListener('click',()=>{if(list&&list.hidden)openList()});
  inp.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){
      e.preventDefault();if(list.hidden){act=e.key==='ArrowDown'?0:opts.length-1;openList();return}
      const n=opts.length;if(!n)return;act=e.key==='ArrowDown'?(act+1)%n:(act-1+n)%n;openList()
    }else if(e.key==='Enter'){if(!list.hidden&&opts.length){e.preventDefault();pick(opts[Math.max(0,act)].key)}}
    else if(e.key==='Escape'){if(!list.hidden){e.preventDefault();e.stopPropagation();closeList()}}
  });
  inp.addEventListener('blur',()=>setTimeout(()=>{if(document.activeElement!==inp)closeList()},150));
}
if(list){
  list.addEventListener('mousedown',e=>e.preventDefault());
  list.addEventListener('click',e=>{const li=e.target.closest('li[data-k]');if(li)pick(li.dataset.k)});
}

/* editor */
function readNum(){const s=($('ov-num')&&$('ov-num').value||'').trim();const v=+s;return s!==''&&isFinite(v)?v:null}

function getEffective(p,v){
  if(mode==='adjustment'){const base=p.base!=null?p.base:(p.ddf||0);return Math.min(100,Math.max(0,base+v))}
  return v;
}

function comparablesHTML(key,effVal){
  const all=getAllPlayers().filter(p=>p.ddf!=null);if(!all.length)return'';
  const replaced=all.map(p=>p.key===String(key)?{...p,ddf:effVal}:p).sort((a,b)=>b.ddf-a.ddf);
  const rank=replaced.findIndex(p=>p.key===String(key));if(rank<0)return'';
  const above=replaced.slice(Math.max(0,rank-NEAR),rank);
  const below=replaced.slice(rank+1,Math.min(replaced.length,rank+1+NEAR));
  return[...above,{...replaced[rank],isSelf:true},...below].map(p=>`<li class="${p.isSelf?'ov-comp-self':''}">${esc(p.n)} <span class="pos pos-${esc(p.pos||'')} ov-comp-pos">${esc(p.pos||'')}</span> <span class="ov-comp-val">${f1(p.ddf)}</span></li>`).join('');
}

function preview(){
  const p=cur&&pRec(cur);if(!p)return;const v=readNum();
  const err=$('ov-err'),pre=$('ov-preview'),comp=$('ov-comparables');
  if(err)err.textContent=v===null?('Enter a value from '+(mode==='adjustment'?'−100 to +100':'0 to 100')+'.'):'' ;
  if(!pre)return;
  if(v===null){pre.textContent='';if(comp)comp.hidden=true;return}
  const eff=getEffective(p,v);
  const all=getAllPlayers().filter(q=>q.ddf!=null);
  const sorted=all.map(q=>q.key===String(cur)?{key:q.key,ddf:eff}:{key:q.key,ddf:q.ddf}).sort((a,b)=>b.ddf-a.ddf);
  const rank=sorted.findIndex(q=>q.key===String(cur))+1;
  const base=p.base!=null?p.base:p.ddf;
  if(mode==='absolute')pre.textContent=Math.abs(v-(base||0))<0.005?'Same as DDF Value (rank #'+rank+').':'At '+f1(eff)+' ('+sg(eff-(base||0))+' vs DDF): rank #'+rank+' by DDF Value.';
  else pre.textContent=Math.abs(v)<0.005?'No change.':'Adjust by '+sg(v)+': '+f1(base||0)+' → '+f1(eff)+' (rank #'+rank+').';
  if(comp){comp.innerHTML='<ul class="ov-comp-list">'+comparablesHTML(cur,eff)+'</ul>';comp.hidden=false}
}

function renderEditor(keepField){
  const p=cur&&pRec(cur);const ed=$('ov-editor');if(!ed)return;
  if(!p){ed.hidden=true;return}ed.hidden=false;
  const name=$('ov-name'),pos=$('ov-pos'),team=$('ov-team'),ddfEl=$('ov-ddf'),mktEl=$('ov-mkt'),curEl=$('ov-cur');
  if(name)name.textContent=p.n;
  if(pos){pos.className='pos pos-'+p.pos;pos.textContent=p.pos}
  if(team)team.textContent=p.team||'';
  const base=p.base!=null?p.base:p.ddf;
  if(ddfEl)ddfEl.textContent=f1(base);
  if(mktEl){
    const D=V()&&V().D;const dp=D&&D.find(q=>q.key===String(cur));
    if(dp&&V().bs&&typeof V().bs.marketOf==='function')mktEl.textContent=f1(V().bs.marketOf(dp));
    else if(typeof p.cbs==='number'&&isFinite(p.cbs)&&typeof p.fc==='number'&&isFinite(p.fc))mktEl.textContent=f1((p.cbs+p.fc)/2);
    else mktEl.textContent='—';
  }
  const e=E();const curEntry=e?e.overrides.get(String(cur)):null;const hasEntry=curEntry!==null&&curEntry!==undefined;
  if(curEl){
    if(!hasEntry)curEl.textContent='= DDF';
    else if(isAdj(curEntry))curEl.textContent=sg(curEntry.delta)+' adj.';
    else curEl.textContent=f1(Number(curEntry));
    curEl.className=hasEntry?'yours':'';
  }
  const mAbs=$('ov-mode-abs'),mAdj=$('ov-mode-adj');
  const lbl=$('ov-num-lbl'),range=$('ov-range'),num=$('ov-num');
  if(!keepField){
    if(hasEntry){
      if(isAdj(curEntry)){mode='adjustment';if(mAdj)mAdj.checked=true;if(mAbs)mAbs.checked=false}
      else{mode='absolute';if(mAbs)mAbs.checked=true;if(mAdj)mAdj.checked=false}
    }else{mode='absolute';if(mAbs)mAbs.checked=true;if(mAdj)mAdj.checked=false}
  }
  if(mAbs)mAbs.checked=(mode==='absolute');if(mAdj)mAdj.checked=(mode==='adjustment');
  if(lbl)lbl.textContent=mode==='absolute'?'Your value (0 to 100)':'Adjust by (−100 to +100)';
  if(range){range.min=mode==='adjustment'?'-100':'0';range.max='100';range.step='0.1'}
  if(num){num.min=mode==='adjustment'?'-100':'0';num.max='100';num.step='0.1'}
  if(!keepField){
    const initV=hasEntry?(isAdj(curEntry)?Number(curEntry.delta):Number(curEntry)):(mode==='absolute'?(base||0):0);
    if(range)range.value=initV;if(num)num.value=+initV.toFixed(2);
  }
  const ap=$('ov-apply'),rs=$('ov-reset');
  if(ap)ap.textContent=hasEntry?'Update override':'Set override';
  if(rs)rs.disabled=!hasEntry;
  preview();
}

const mAbsEl=$('ov-mode-abs'),mAdjEl=$('ov-mode-adj');
function updateMode(m){
  mode=m;const p=cur&&pRec(cur);if(!p)return;
  const lbl=$('ov-num-lbl'),range=$('ov-range'),num=$('ov-num');
  if(lbl)lbl.textContent=m==='absolute'?'Your value (0 to 100)':'Adjust by (−100 to +100)';
  if(range)range.min=m==='adjustment'?'-100':'0';if(num)num.min=m==='adjustment'?'-100':'0';
  const e=E();const curEntry=e?e.overrides.get(String(cur)):null;const hasEntry=curEntry!==null&&curEntry!==undefined;
  const base=p.base!=null?p.base:p.ddf;
  if(!hasEntry){const dfl=m==='absolute'?(base||0):0;if(range)range.value=dfl;if(num)num.value=+dfl.toFixed(2)}
  preview();
}
if(mAbsEl)mAbsEl.addEventListener('change',()=>{if(mAbsEl.checked)updateMode('absolute')});
if(mAdjEl)mAdjEl.addEventListener('change',()=>{if(mAdjEl.checked)updateMode('adjustment')});
$('ov-num')&&$('ov-num').addEventListener('input',()=>{const v=readNum();const r=$('ov-range');if(v!==null&&r)r.value=v;preview()});
$('ov-num')&&$('ov-num').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('ov-apply')&&$('ov-apply').click()}});
$('ov-range')&&$('ov-range').addEventListener('input',()=>{const r=$('ov-range'),n=$('ov-num');if(r&&n)n.value=(+r.value).toFixed(1);preview()});

$('ov-apply')&&$('ov-apply').addEventListener('click',()=>{
  const p=cur&&pRec(cur);const v=readNum();if(!p)return;
  if(v===null){preview();$('ov-num')&&$('ov-num').focus();return}
  const e=E();if(!e){const err=$('ov-err');if(err)err.textContent='Overrides are not available in this browser.';return}
  if(mode==='adjustment'){
    if(Math.abs(v)<0.005){e.overrides.remove(String(cur));const sv=$('ov-saved');if(sv)sv.hidden=true;const c=onChange();announce(p.n+' is back to DDF Value. '+c+(c===1?' change.':' changes.'));return}
    e.overrides.set(String(cur),{type:'adjustment',delta:v});const c=onChange();showSaved(p.n,mode,v);announce('Override set: '+p.n+' '+sg(v)+'. '+c+(c===1?' change.':' changes.'));
  }else{
    const base=p.base!=null?p.base:p.ddf;
    if(Math.abs(v-(base||0))<0.005){const ce=e.overrides.get(String(cur));if(ce!=null)e.overrides.remove(String(cur));const sv=$('ov-saved');if(sv)sv.hidden=true;const c=onChange();announce(p.n+' is back to DDF Value. '+c+(c===1?' change.':' changes.'));return}
    e.overrides.set(String(cur),v);const c=onChange();showSaved(p.n,mode,v);announce('Override set: '+p.n+' '+f1(v)+'. '+c+(c===1?' change.':' changes.'));
  }
});

$('ov-reset')&&$('ov-reset').addEventListener('click',()=>{
  const p=cur&&pRec(cur);if(!p)return;const e=E();if(e)e.overrides.remove(String(cur));
  const sv=$('ov-saved');if(sv)sv.hidden=true;const c=onChange();announce(p.n+' reset to DDF Value. '+c+(c===1?' change.':' changes.'));
  $('ov-num')&&$('ov-num').focus();
});

function showSaved(n,m,v){
  const s=$('ov-saved');if(!s)return;
  const q=encodeURIComponent(n).replace(/%20/g,'+');
  if(m==='adjustment')s.innerHTML='Saved: '+esc(n)+' adjusted by '+sg(v)+'. <a href="#buy-sell?player='+q+'">See it in Buy / Sell</a>';
  else s.innerHTML='Saved: '+esc(n)+' at '+f1(v)+'. <a href="#buy-sell?player='+q+'">See it in Buy / Sell</a> · <a href="find.html">See it in Trade &amp; Waiver Recommendations</a>';
  s.hidden=false;
}

/* override list */
function renderActive(){
  const e=E();const oAll=e?e.overrides.all():{};const keys=Object.keys(oAll),n=keys.length;
  const nEl=$('ov-n');if(nEl)nEl.textContent=n;
  const cl=$('ov-clear');if(cl)cl.hidden=!n;
  const cp=$('ov-copylink');if(cp)cp.hidden=!n;
  const L=window.DDF&&DDF.link;
  const ch=$('ov-chat');if(ch)ch.hidden=!(n&&L&&typeof L.copyForChat==='function'&&L.current&&L.current());
  const tb=$('ov-tabn');if(tb){tb.hidden=!n;tb.textContent=n;tb.setAttribute('aria-label',n+(n===1?' override':' overrides'))}
  const sn=$('ov-session-note');
  if(sn){if(e&&e.overrides.session()){sn.textContent='These overrides came from a link and apply for this visit. Any change you make here saves them as your own.';sn.hidden=false}else sn.hidden=true}
  const ov=$('ov-active');if(!ov)return;
  if(!n){ov.innerHTML='<li class="ov-empty">None yet. Pick a player and set your value; every tab then uses it in place of DDF Value.</li>';return}
  ov.innerHTML=keys.map(key=>{
    const p=pRec(key);const entry=oAll[key];const adj=isAdj(entry);
    if(!p)return`<li><div class="ov-who"><strong>${esc(key)}</strong><span>Player not in this build, so nothing is recomputed here.</span></div><div class="ov-acts"><button type="button" class="btn" data-rm="${esc(key)}" aria-label="Remove override">Remove</button></div></li>`;
    const name=p.n,base=p.base!=null?p.base:p.ddf;
    const disp=adj?(sg(entry.delta)+' adjustment'):('Yours '+f1(Number(entry)));
    const dVal=adj?Number(entry.delta):(Number(entry)-(base||0));
    return`<li><div class="ov-who"><strong>${esc(name)} <span class="pos pos-${esc(p.pos)}">${esc(p.pos)}</span></strong><span>DDF ${f1(base)} → ${adj?disp:disp} <span class="ov-d ${(typeof dVal==='number'&&dVal>=0)?'up':'dn'}">${sg(dVal)}</span></span></div><div class="ov-acts"><button type="button" class="btn" data-edit="${esc(key)}" aria-label="Edit override for ${esc(name)}">Edit</button><button type="button" class="btn" data-rm="${esc(key)}" aria-label="Remove override for ${esc(name)}">Remove</button></div></li>`;
  }).join('');
}

$('ov-clear')&&$('ov-clear').addEventListener('click',clearAll);
$('ov-loaded-clear')&&$('ov-loaded-clear').addEventListener('click',clearAll);

function clearAll(){
  const e=E();if(e)e.overrides.clear();const sv=$('ov-saved');if(sv)sv.hidden=true;
  const lo=$('ov-loaded');if(lo)lo.hidden=true;onChange();announce('All overrides removed. Every tab uses DDF Value again.');if(inp)inp.focus();
}

$('ov-active')&&$('ov-active').addEventListener('click',ev=>{
  const ed=ev.target.closest('[data-edit]'),rm=ev.target.closest('[data-rm]');
  if(ed){
    const key=ed.dataset.edit;cur=key;const p=pRec(key);if(p&&inp)inp.value=p.n;renderEditor(false);
    const ph=$('ov-pick-h');if(ph)ph.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});
    const num=$('ov-num');if(num){num.focus();num.select()}return
  }
  if(rm){
    const key=rm.dataset.rm;const p=pRec(key);const name=p?p.n:key;const e=E();if(e)e.overrides.remove(key);
    const c=onChange();announce('Override removed: '+name+'. '+c+(c===1?' change.':' changes.'));
    const oa=$('ov-active');if(!oa)return;const btns=[...oa.querySelectorAll('[data-rm]')];const idx=btns.indexOf(rm);
    const nb=[...oa.querySelectorAll('[data-rm]')];const next=nb[Math.min(idx,nb.length-1)]||inp;if(next)next.focus();
  }
});

/* copy link with my overrides */
$('ov-copylink')&&$('ov-copylink').addEventListener('click',()=>{
  const e=E();const vl=VL();const st=$('ov-share');if(!e||!vl)return;
  const basis=vl.formatBasisParam(e.basis());
  const ov=vl.formatOvParam(e.overrides.all());
  const basePart=basis?'&basis='+encodeURIComponent(basis):'';
  const ovPart=ov?'&ov='+encodeURIComponent(ov):'';
  const full=location.origin+location.pathname+'#overrides?valuecontext=1'+basePart+ovPart;
  if(full.length>LINK_BUDGET){
    const short=location.origin+location.pathname+'#overrides?valuecontext=1'+basePart;
    if(st)st.textContent='Player overrides are too large for a link; they were left out. Use Export to share them as a file.';
    navigator.clipboard&&navigator.clipboard.writeText(short);return;
  }
  navigator.clipboard?navigator.clipboard.writeText(full).then(()=>{if(st)st.textContent='Link copied.'},()=>{if(st)st.textContent='Could not copy link in this browser.'}):(st&&(st.textContent='Could not copy link in this browser.'));
});

$('ov-chat')&&$('ov-chat').addEventListener('click',()=>{const L=window.DDF&&DDF.link;if(L&&L.copyForChat)L.copyForChat($('ov-share'))});

/* export / import */
function exportDoc(){
  const e=E();if(!e)return null;
  const rec=e.basis();const vals=e.overrides.all();
  const names={};Object.keys(vals).forEach(key=>{const p=pRec(key);if(p)names[key]=p.n});
  return{v:2,basis:rec,values:vals,names};
}

$('ov-export')&&$('ov-export').addEventListener('click',()=>{
  const doc=exportDoc();if(!doc)return;
  const blob=new Blob([JSON.stringify(doc,null,2)+'\n'],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='ddf-overrides.json';document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});

$('ov-import')&&$('ov-import').addEventListener('click',()=>{
  const input=document.createElement('input');input.type='file';input.accept='application/json,.json';
  input.addEventListener('change',()=>{
    const file=input.files&&input.files[0];input.remove();if(!file)return;
    file.text().then(text=>{
      let doc=null;try{doc=JSON.parse(text)}catch(_){}
      const note=$('ov-import-note');
      if(!doc||typeof doc!=='object'||![1,2].includes(doc.v)||!doc.values){if(note)note.textContent='That file is not an overrides export, so nothing was changed.';return}
      const e=E();if(!e)return;const vl=VL();
      let basisSet=false;
      if(doc.basis&&doc.basis.mode&&doc.basis.mode!=='default'){e.setBasis(doc.basis);syncBasisFromEngine();renderBasis();basisSet=true;}
      const vals={};
      Object.keys(doc.values||{}).forEach(key=>{
        const raw=doc.values[key];const entry=vl?vl.normalizeEntry(raw):raw;if(entry!=null)vals[key]=entry;
      });
      e.overrides.replaceAll(vals);const n=Object.keys(vals).length;
      if(note)note.textContent='Imported '+n+' player override'+(n===1?'':'s')+(basisSet?' and the value basis':'')+'.';
      onChange();
    });
  });
  document.body.append(input);input.click();
});

/* basis section */
function renderBasis(){
  const box=$('ov-basis-presets');if(!box)return;
  box.innerHTML='';
  const presets=[{id:'default',text:'Our method'}];
  SINGLE_ORDER.forEach(k=>presets.push({id:'single:'+k,text:labelOf(k),key:k}));
  presets.push({id:'blend',text:'Custom blend'});
  const curId=bMode==='single'?'single:'+bSingle:bMode;
  const grp=document.createElement('div');grp.className='ov-basis-grp';grp.setAttribute('role','radiogroup');grp.setAttribute('aria-label','Value basis');
  presets.forEach(preset=>{
    const usable=!preset.key||isUsable(preset.key);
    const btn=document.createElement('button');btn.type='button';btn.setAttribute('role','radio');
    btn.className='btn ov-basis-btn'+(preset.id===curId?' is-on':'');
    btn.setAttribute('aria-checked',String(preset.id===curId));
    btn.textContent=preset.text;
    if(!usable){btn.setAttribute('aria-disabled','true');btn.title=usableReason(preset.key)}
    btn.addEventListener('click',()=>{
      if(preset.key&&!isUsable(preset.key))return;
      if(preset.id==='default')bMode='default';else if(preset.id==='blend')bMode='blend';else{bMode='single';bSingle=preset.key}
      applyBasis();renderBasis();renderBlendEditor();updateBasisLabel();
    });
    grp.append(btn);
  });
  box.append(grp);
}

function updateBasisLabel(){
  const lbl=$('ov-basis-label');if(!lbl)return;
  const info=E()&&E().basisInfo();
  if(bMode==='default'){lbl.textContent='DDF Value = our method: average of four trade charts (Analyst charts: CBS Sports, USA Today, FantasyPros; Live market: FantasyCalc), adjusted and averaged for your league.';return}
  if(bMode==='single'){lbl.textContent='DDF Value = '+labelOf(bSingle)+' only: that source\'s values for your league, on the same scale.';return}
  const pct=percents();const on=bKeys().filter(k=>pct[k]!=null);
  if(on.length)lbl.textContent='DDF Value = '+on.map(k=>pct[k]+'% '+labelOf(k)).join(' + ')+'.';
  else lbl.textContent='DDF Value = your custom blend.';
  if(info&&info.fellBackToDefault)lbl.textContent+=' None of the chosen sources is available this week; using the default.';
}

function renderBlendEditor(){
  const box=$('ov-basis-blend');if(!box)return;
  box.hidden=bMode!=='blend';if(bMode!=='blend')return;
  box.innerHTML='';
  const intro=document.createElement('p');intro.className='bs-note';intro.textContent='Set each source\'s weight (1–100; proportions matter). Unusable sources are paused and left out.';box.append(intro);
  const pct=percents();const wl=document.createElement('div');wl.className='ov-wlist';
  SINGLE_ORDER.forEach(key=>{
    const label=labelOf(key);const usable=isUsable(key);
    if(!bBlend[key])bBlend[key]={on:DEFAULT_SOURCES.includes(key),w:25};
    const on=bBlend[key].on;
    const ticked=bKeys().filter(k=>bBlend[k]&&bBlend[k].on&&isUsable(k));
    const isLast=on&&usable&&ticked.length===1&&ticked[0]===key;
    const row=document.createElement('div');row.className='ov-wrow'+(usable?'':' is-paused');
    const chkId='ov-bl-'+key;
    const chk=document.createElement('input');chk.type='checkbox';chk.id=chkId;chk.checked=on&&usable;chk.disabled=(!usable)||isLast;
    const lbl=document.createElement('label');lbl.htmlFor=chkId;lbl.className='ov-wlabel';lbl.textContent=label;
    const range=document.createElement('input');range.type='range';range.min='1';range.max='100';range.step='1';range.value=String(bBlend[key].w);range.setAttribute('aria-label',label+' weight');range.disabled=!on||!usable;
    const numinput=document.createElement('input');numinput.type='number';numinput.min='1';numinput.max='100';numinput.step='1';numinput.value=String(bBlend[key].w);numinput.className='ov-wnum';numinput.setAttribute('aria-label',label+' weight, number');numinput.disabled=!on||!usable;
    const pctSpan=document.createElement('span');pctSpan.className='ov-wpct';pctSpan.setAttribute('data-pct',key);
    pctSpan.textContent=usable&&on?(pct[key]!=null?pct[key]+'%':'—'):(!usable?usableReason(key):'off');
    const repaint=()=>{bKeys().filter(k=>bBlend[k]).forEach(k=>{const sp=wl.querySelector('[data-pct="'+k+'"]');if(sp){const p2=percents();sp.textContent=bBlend[k].on&&isUsable(k)?(p2[k]!=null?p2[k]+'%':'—'):(!isUsable(k)?usableReason(k):'off')}});updateBasisLabel()};
    const setW=v=>{if(!bBlend[key])return;const w=Math.min(100,Math.max(1,Math.round(Number(v)||1)));bBlend[key].w=w;range.value=String(w);numinput.value=String(w);repaint();applyBasis()};
    range.addEventListener('input',()=>setW(range.value));
    numinput.addEventListener('change',()=>setW(numinput.value));
    chk.addEventListener('change',()=>{
      if(!bBlend[key])bBlend[key]={on:false,w:25};bBlend[key].on=chk.checked;
      if(!bKeys().some(k=>bBlend[k]&&bBlend[k].on))bBlend[key].on=true;
      applyBasis();renderBlendEditor();const again=document.getElementById(chkId);if(again)again.focus();
    });
    row.append(lbl,chk,range,numinput,pctSpan);
    if(!usable){const note=document.createElement('span');note.className='ov-wnote';note.textContent=usableReason(key);row.append(note)}
    if(isLast){const note=document.createElement('span');note.className='ov-wnote';note.textContent='Last source, stays on';row.append(note)}
    wl.append(row);
  });
  box.append(wl);
}

/* what changes */
function ranks(useBase){
  const D=V()&&V().D;if(!D)return new Map();
  const m=new Map();D.map((p,i)=>({p,i})).sort((a,b)=>(useBase?b.p.base-a.p.base:b.p.ddf-a.p.ddf)||a.i-b.i).forEach((o,j)=>m.set(o.p.key,j+1));return m;
}

const cell=(b,a,ch)=>`<span class="ov-num">${esc(b)}</span> → <span class="ov-num">${ch?'<strong>'+esc(a)+'</strong>':esc(a)}</span>`;

function renderWhat(){
  const box=$('ov-what');if(!box)return 0;
  const e=E();const oAll=e?e.overrides.all():{};
  if(!Object.keys(oAll).length){box.innerHTML='<p class="ov-empty">No overrides yet. Set a value above and this panel lists what moves: ranks and the Buy / Sell lists.</p>';return 0}
  const D=V()&&V().D;const rows=[];
  if(D){
    const r0=ranks(true),r1=ranks(false);
    D.filter(p=>p.ov||(r0.get(p.key)!==r1.get(p.key))).sort((a,b)=>(r1.get(a.key)||0)-(r1.get(b.key)||0)).forEach(p=>{
      const b=r0.get(p.key),a=r1.get(p.key);
      rows.push({area:'Rank by DDF Value',what:p.n+(p.ov?' (your value)':''),before:'#'+b,after:'#'+a,changed:a!==b,up:a<b});
    });
  }
  const bs=V()&&V().bs;
  if(bs&&typeof bs.makeDB==='function'&&typeof bs.isLeague==='function'){
    const lg=bs.isLeague();
    (lg?['sell','buy']:['buy']).forEach(side=>{
      const fn=side==='sell'?bs.sellList:bs.buyList;if(typeof fn!=='function')return;
      let baseDB,effDB;try{baseDB=bs.makeDB(true);effDB=bs.makeDB(false)}catch(_){return}
      const b=fn(baseDB).slice(0,5),a=fn(effDB).slice(0,5);
      const bn=b.map(o=>o.p.n),an=a.map(o=>o.p.n);const L=side==='sell'?'Sell':'Buy';
      const gap=o=>(o&&o.g)?('gap '+f1(Math.abs(o.g.g))+' '+o.g.c):'';
      a.forEach((o,i)=>{const j=bn.indexOf(o.p.n);
        if(j<0)rows.push({area:L,what:o.p.n+' enters '+L+' top 5',before:'not in top 5',after:'#'+(i+1)+(gap(o)?' · '+gap(o):''),changed:true});
        else if(b[j]&&o.g&&b[j].g&&Math.abs(b[j].g.g-o.g.g)>=0.005)rows.push({area:L,what:o.p.n+' gap changes',before:'#'+(j+1)+(b[j].g?' · '+gap(b[j]):''),after:'#'+(i+1)+(o.g?' · '+gap(o):''),changed:true});
        else if(i!==j)rows.push({area:L,what:o.p.n+' moves in '+L+' top 5',before:'#'+(j+1),after:'#'+(i+1),changed:true});
      });
      b.forEach((o,j)=>{if(!an.includes(o.p.n))rows.push({area:L,what:o.p.n+' leaves '+L+' top 5',before:'#'+(j+1)+(gap(o)?' · '+gap(o):''),after:'not in top 5',changed:true})});
    });
  }
  const n=rows.filter(r=>r.changed).length;
  const areas=['Rank by DDF Value','Sell','Buy'];const byArea={};areas.forEach(a=>{byArea[a]=rows.filter(r=>r.area===a)});
  box.innerHTML='<div class="ov-areas">'+areas.filter(a=>byArea[a].length>0).map(areaTitle=>`<section class="ov-area"><h4>${esc(areaTitle)}</h4><ul>${byArea[areaTitle].map(r=>`<li class="${r.changed?'':'same'}">${esc(r.what)}: ${cell(r.before,r.after,r.changed)}${!r.changed?' · unchanged':''}</li>`).join('')}</ul></section>`).join('')+'</div><p class="bs-note" style="margin-top:12px">Trade &amp; Waiver Recommendations and Build a Trade use the same values.</p>';
  return n;
}

/* render all */
function renderAll(){renderActive();renderEditor(true);renderBasis();renderBlendEditor();updateBasisLabel();renderWhat()}

function announce(msg){const l=$('ov-live');if(!l)return;l.textContent='';setTimeout(()=>{l.textContent=msg},60)}

let sig=null;const sigNow=()=>JSON.stringify(E()?E().overrides.all():{});

function onChange(){
  sig=sigNow();const v=V();
  if(v){if(typeof v.applyOverrides==='function')v.applyOverrides();if(typeof v.hideCard==='function')v.hideCard();if(typeof v.render==='function')v.render();if(v.bs&&typeof v.bs.refresh==='function')v.bs.refresh()}
  renderActive();renderEditor(false);return renderWhat();
}

document.addEventListener('ddf:values-change',()=>queueMicrotask(()=>{
  const curSig=sigNow();
  if(curSig!==sig){const c=onChange();announce('Updated. '+c+(c===1?' change.':' changes.'))}
  else{syncBasisFromEngine();renderBasis();renderBlendEditor();updateBasisLabel()}
}));

/* start */
function start(){
  sig=sigNow();syncBasisFromEngine();renderAll();
  const v=V();if(!v)return;
  if(typeof v.applyOverrides==='function')v.applyOverrides();
  if(v.D&&v.D.some(p=>p.ov)){if(typeof v.render==='function')v.render();if(v.bs&&typeof v.bs.refresh==='function')v.bs.refresh()}
}

/* exported API: Chart tab and #overrides?player=Name routing */
const v0=window.DDFValues;
if(v0){
  v0.ovRender=renderAll;
  v0.ovPreselect=(n,focus)=>{
    const q=getAllPlayers().find(p=>p.n.toLowerCase()===String(n).toLowerCase());if(!q)return;
    cur=q.key;if(inp)inp.value=q.n;closeList();const sv=$('ov-saved');if(sv)sv.hidden=true;renderEditor(false);
    if(focus){const ph=$('ov-pick-h');if(ph)ph.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});const num=$('ov-num');if(num){num.focus();num.select()}}
  };
}

/* wait for engine then start */
const vv=window.DDFValues;
if(vv&&vv.ready&&typeof vv.ready.then==='function')vv.ready.then(start);
else{if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start()}

})();
