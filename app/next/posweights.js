/* Position weights module. Renders into every <div data-posweights></div>.
   Storage: sessionStorage 'ddf:posweights' = {starter:[qb,rb,wr,te], bench:[qb,rb,wr,te]}; absent means DDF defaults.
   Also drives any <button data-posweights-flag> ("Custom weights" flag; click opens the Advanced section). */
(function(){
  var KEY='ddf:posweights',POS=['qb','rb','wr','te'],DEF={s:[1,1,1,1],b:[1.9,5.7,3.4,0.1]},n=0;
  function info(label,text){return '<details class="info"><summary aria-label="About '+label+'">&#9432;</summary><span role="note">'+text+'</span></details>';}
  function row(kind,id){return '<div class="pw-row" role="group" aria-labelledby="'+id+'">'+POS.map(function(k,j){
    var s=kind==='s',U=k.toUpperCase();
    return '<label class="pw-box" data-def="'+DEF[kind][j]+'"><span>'+U+'</span><input type="number" min="0" max="'+(s?5:100)+'" step="'+(s?0.5:0.1)+'" value="'+DEF[kind][j]+'" data-kind="'+kind+'" data-pos="'+k+'" aria-label="'+(s?'Starter ':'Bench ')+U+' weight"><span class="pw-tag" aria-hidden="true">Edited</span></label>';}).join('')+'</div>';}
  function markup(i){return '<section class="pw" aria-label="Position weights"><div class="pw-head"><h3 class="pw-title">Position weights'
    +info('position weights','Change how much each position counts toward player value. Edits apply to this browser session and are included in links you share. Reset restores the DDF defaults.')+'</h3>'
    +'<p class="pw-state" role="status"><span class="pw-chip">Using DDF defaults</span><button type="button" class="pw-reset" disabled>Reset to defaults</button></p></div>'
    +'<div class="pw-grid" role="group" aria-label="Position weights">'
    +'<div class="pw-rowlbl" id="pw-ls'+i+'">Starters relative weight'+info('starters relative weight','A multiplier from 0 to 5 for each position’s starters, relative to the others. 1 is the default.')+'</div>'+row('s','pw-ls'+i)
    +'<div class="pw-rowlbl" id="pw-lb'+i+'">Bench share of value, %'+info('bench share of value','Each position’s bench share of total value, in percent.')+'</div>'+row('b','pw-lb'+i)
    +'</div><p class="pw-note">These are the DDF defaults. Edits apply to your session only; Reset restores the defaults.</p></section>';}

  function read(){try{var w=JSON.parse(sessionStorage.getItem(KEY)||'null');return w&&typeof w==='object'?w:null;}catch(e){return null;}}
  function write(v){try{if(v)sessionStorage.setItem(KEY,JSON.stringify(v));else sessionStorage.removeItem(KEY);}catch(e){}}
  function same(a,b){return Math.abs(a-b)<1e-9;}
  function countEdited(w){var c=0;if(!w)return 0;['s','b'].forEach(function(p){var a=p==='s'?w.starter:w.bench;POS.forEach(function(k,j){var v=a&&parseFloat(a[j]);if(isFinite(v)&&!same(v,DEF[p][j]))c++;});});return c;}
  function flags(){var w=read(),c=countEdited(w);[].forEach.call(document.querySelectorAll('[data-posweights-flag]'),function(b){b.hidden=!c;});}

  function mount(host,i){
    host.innerHTML=markup(i);
    var boxes=[].slice.call(host.querySelectorAll('.pw-box')),chip=host.querySelector('.pw-chip'),reset=host.querySelector('.pw-reset');
    function vals(p){return POS.map(function(k){var e=host.querySelector('input[data-kind="'+p+'"][data-pos="'+k+'"]');return e?(parseFloat(e.value)||0):0;});}
    function paint(){var c=0;boxes.forEach(function(b){var inp=b.querySelector('input'),e=!same(parseFloat(inp.value)||0,parseFloat(b.dataset.def));b.classList.toggle('edited',e);if(e)c++;});
      chip.textContent=c?'Custom weights ('+c+' edited)':'Using DDF defaults';chip.classList.toggle('custom',!!c);reset.disabled=!c;return c;}
    function save(){var c=paint();write(c?{starter:vals('s'),bench:vals('b')}:null);flags();document.dispatchEvent(new CustomEvent('ddf:posweights',{detail:{edited:c}}));}
    function load(){var w=read(),s=w&&w.starter,b=w&&w.bench;boxes.forEach(function(bx){var inp=bx.querySelector('input'),a=inp.dataset.kind==='s'?s:b,j=POS.indexOf(inp.dataset.pos);inp.value=a&&isFinite(parseFloat(a[j]))?a[j]:bx.dataset.def;});paint();flags();}
    boxes.forEach(function(b){var inp=b.querySelector('input');inp.addEventListener('input',save);inp.addEventListener('change',save);});
    reset.addEventListener('click',function(){boxes.forEach(function(b){b.querySelector('input').value=b.dataset.def;});save();reset.blur();});
    load();document.addEventListener('ddf:link',load);
  }

  function init(){
    [].forEach.call(document.querySelectorAll('[data-posweights]'),function(h){mount(h,n++);});
    [].forEach.call(document.querySelectorAll('[data-posweights-flag]'),function(b){
      b.addEventListener('click',function(){
        var host=document.querySelector('[data-posweights]');if(!host)return;
        var d=host.closest('details');while(d){d.open=true;d=d.parentElement&&d.parentElement.closest('details');}
        var f=document.getElementById('find-filters'),t=document.getElementById('filters-toggle');
        if(f&&f.hidden&&t)t.click();
        host.scrollIntoView({block:'center'});var x=host.querySelector('input');if(x)x.focus({preventScroll:true});});
    });
    flags();
    if(!window.__pwInfoClose){window.__pwInfoClose=1;
      document.addEventListener('keydown',function(e){if(e.key!=='Escape')return;var o=document.querySelectorAll('.pw details.info[open]');if(!o.length)return;
        e.stopImmediatePropagation();[].forEach.call(o,function(d){d.open=false;d.querySelector('summary').focus();});},true);
      document.addEventListener('click',function(e){[].forEach.call(document.querySelectorAll('.pw details.info[open]'),function(d){if(!d.contains(e.target))d.open=false;});});}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
