/* DDF sticky action bar (reusable component). Pair with actionbar.css.
 *
 * Wire-up (two steps):
 *   <link rel="stylesheet" href="actionbar.css">
 *   <script src="actionbar.js"></script>              (no defer; safe before or after site.js)
 *   Add data attributes to the page's existing primary next link/button:
 *     data-sticky-next                        required marker
 *     data-back-href="explore.html"           optional; adds a Back link on the left
 *     data-back-label="Back"                  optional (default "Back")
 *     data-next-label="Next: pick trading partners"   optional (default: the original's text)
 *     data-summary="Review, then continue"    optional static one-line summary
 *     data-summary-source="#selection-count"  optional; mirrors that element's text live
 *     data-disabled-reason="Pick a player"    optional; shown while the next control is disabled
 * Live API (use when the summary is computed in page script; calls made before the bar builds are queued):
 *   DDF.actionBar.setSummary("3 players picked, next: pick trade partners")
 *   DDF.actionBar.setDisabled(true, "Pick at least one player to continue")
 * Disabled state is also read from the original: class off/disabled, aria-disabled="true", disabled attribute.
 * The original control stays in the page; the bar's Next forwards its click to it, so existing handlers still run.
 */
(function(){
  var DDF=window.DDF=window.DDF||{};
  var state={summary:null,disabled:null,reason:null},bar,sum,next,orig,srcEl;
  function isOrigDisabled(){
    return orig.classList.contains('off')||orig.classList.contains('disabled')||orig.getAttribute('aria-disabled')==='true'||orig.hasAttribute('disabled');
  }
  function render(){
    if(!bar)return;
    var dis=state.disabled!==null?state.disabled:isOrigDisabled();
    var reason=state.reason||orig.getAttribute('data-disabled-reason')||'';
    var text=state.summary!==null?state.summary:(srcEl?srcEl.textContent.replace(/\s+/g,' ').trim():(orig.getAttribute('data-summary')||''));
    var showReason=dis&&reason;
    sum.textContent=showReason?reason:text;
    sum.classList.toggle('is-reason',!!showReason);
    next.classList.toggle('is-disabled',dis);
    next.setAttribute('aria-disabled',String(dis));
    if(dis){next.removeAttribute('href');next.setAttribute('role','link');next.tabIndex=0}
    else{next.setAttribute('href',orig.getAttribute('href')||'#');next.removeAttribute('role')}
    next.textContent=orig.getAttribute('data-next-label')||orig.textContent.trim();
    bar.hidden=false;
  }
  function size(){document.documentElement.style.setProperty('--ddf-actionbar-h',bar.offsetHeight+'px')}
  function build(){
    orig=document.querySelector('[data-sticky-next]');
    if(!orig||bar)return;
    var src=orig.getAttribute('data-summary-source');
    srcEl=src?document.querySelector(src):null;
    bar=document.createElement('div');bar.className='ddf-actionbar';bar.setAttribute('role','region');bar.setAttribute('aria-label','Page actions');bar.hidden=true;
    var inner=document.createElement('div');inner.className='ddf-actionbar__in';
    var backHref=orig.getAttribute('data-back-href');
    if(backHref){var back=document.createElement('a');back.className='button ddf-actionbar__back';back.href=backHref;back.textContent=orig.getAttribute('data-back-label')||'Back';inner.appendChild(back)}
    sum=document.createElement('p');sum.className='ddf-actionbar__sum';sum.id='ddf-actionbar-sum';
    next=document.createElement('a');next.className='button primary ddf-actionbar__next';next.setAttribute('aria-describedby','ddf-actionbar-sum');
    next.addEventListener('click',function(e){e.preventDefault();if(next.getAttribute('aria-disabled')==='true')return;orig.click()});
    next.addEventListener('keydown',function(e){if(e.key===' '){e.preventDefault();next.click()}});
    inner.appendChild(sum);inner.appendChild(next);bar.appendChild(inner);document.body.appendChild(bar);
    document.documentElement.classList.add('has-actionbar');document.body.classList.add('has-actionbar');
    var mo=new MutationObserver(render);
    mo.observe(orig,{attributes:true,childList:true,characterData:true,subtree:true});
    if(srcEl)new MutationObserver(render).observe(srcEl,{childList:true,characterData:true,subtree:true});
    render();size();
    if(window.ResizeObserver)new ResizeObserver(size).observe(bar);else window.addEventListener('resize',size);
    requestAnimationFrame(function(){bar.classList.add('is-ready')});
  }
  DDF.actionBar={
    setSummary:function(t){state.summary=String(t);render()},
    setDisabled:function(d,r){state.disabled=d===null?null:!!d;state.reason=r||null;render()},
    refresh:render
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',build);else build();
})();
