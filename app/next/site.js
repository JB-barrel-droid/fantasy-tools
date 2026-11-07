document.addEventListener('click', function(e){
  var wrap = document.querySelector('.morewrap');
  if(!wrap) return;
  if(e.target.closest('.morewrap > button')) wrap.classList.toggle('open');
  else if(!e.target.closest('.morewrap')) wrap.classList.remove('open');
  /* Keep aria-expanded in step on pages without their own More script (values.html had none; QA sweep 2026-11-06). */
  var mb = wrap.querySelector(':scope > button');
  if(mb) mb.setAttribute('aria-expanded', String(wrap.classList.contains('open')));
});
document.querySelectorAll('[data-copy]').forEach(function(b){
  b.addEventListener('click', function(){
    if(navigator.clipboard) navigator.clipboard.writeText(b.getAttribute('data-copy'));
    var t = b.textContent; b.textContent = 'Copied'; setTimeout(function(){ b.textContent = t; }, 1500);
  });
});

document.querySelectorAll('[data-slideshow]').forEach(function(slideshow){
  var slides = slideshow.querySelectorAll('.slide');
  var step = slideshow.querySelector('.slide-step');
  var index = 0;
  function showSlide(nextIndex){
    index = (nextIndex + slides.length) % slides.length;
    slides.forEach(function(slide, slideIndex){
      slide.hidden = slideIndex !== index;
      slide.classList.toggle('is-active', slideIndex === index);
    });
    step.textContent = 'Step ' + (index + 1) + ' of ' + slides.length;
  }
  slideshow.querySelector('[data-prev]').addEventListener('click', function(){ showSlide(index - 1); });
  slideshow.querySelector('[data-next]').addEventListener('click', function(){ showSlide(index + 1); });
  showSlide(0);
});

/* ===== Journey-aware nav (Jeremy, 2026-11-06; key screens in the bar before a league, short bar on Home) =====
   No league yet: Home, Values, Learn + one green "Get started". League loaded: the workspace in journey order
   (Team, Trade & Waiver Recommendations, Build a Trade, Values menu) + a quiet "Your league" chip.
   League = a #s= link in the URL or ddf:league in sessionStorage. Pages without the main nav (entry flow) are untouched. */
(function(){
  function leagueLoaded(){
    /* JEG-1539: DDF.league (ddf-league.js) sets DDF.leagueKnown after it reads the league, so a pasted or saved league counts too. */
    if(window.DDF && DDF.leagueKnown === true) return true;
    try{
      if(/^#s=/.test(location.hash) || sessionStorage.getItem('ddf:league')) return true;
      /* JEG-1539: the same leagues DDF.league reads, so pages without ddf-league.js (Home, Values, Learn, Build a Trade) show the same nav. */
      var pasted = JSON.parse(sessionStorage.getItem('ddf:pasted') || 'null');
      if(pasted && Array.isArray(pasted.teams) && pasted.teams.length) return true;
      var saved = JSON.parse(localStorage.getItem('ddf.v2.workspaces') || 'null');
      if(!saved || saved.v !== 1 || !Array.isArray(saved.workspaces)) return false;
      /* The active saved league only, as DDF.engine.league() reads it. */
      var ws = saved.workspaces.filter(function(w){ return w && w.id === saved.activeId; })[0] || saved.workspaces[0];
      return !!(ws && Array.isArray(ws.teams) && ws.teams.length);
    }
    catch(e){ return false; }
  }
  var PRE = [['index.html','Home'],['connect.html','Add your league'],['build.html?mode=any','Quick trade check'],['values.html','Values'],['ai.html','Use with AI'],['learn.html','Learn']];
  /* The home page asks for one thing, so its nav stays short: Values, Learn and the green Get started. */
  var PRE_HOME = [['values.html','Values'],['learn.html','Learn']];
  /* Pick players and Pick trading partners are settings along the way: they live in the step row, not the top nav (Jeremy, 2026-11-06). */
  var POST = [['team.html','Team'],['find.html','Trade &amp; Waiver Recommendations'],['build.html','Build a Trade'],['values.html','Values']];
  var MENU_PRE = [['index.html','Home'],['build.html?mode=any','Quick trade check'],['values.html','Values'],['values.html#buy-sell','Buy / Sell'],['values.html#overrides','Overrides'],['learn.html','Learn'],['learn.html#numbers/pie','How we get our numbers'],['ai.html','Use DDF with AI'],['connect.html','Get started']];
  var MENU_POST = [['index.html','Home'],['values.html','Values'],['values.html#buy-sell','Buy / Sell'],['values.html#overrides','Overrides'],['waivers.html','Waivers'],['learn.html','Learn'],['learn.html#numbers/pie','How we get our numbers'],['ai.html','Use DDF with AI'],['connect.html','Paste my league'],['setup.html','Your team'],['settings.html','League settings']];
  var PAGE_ALIAS = {'waivers.html':'find.html','check.html':'build.html','trade.html':'build.html','compare.html':'build.html'};
  function file(){ var f = location.pathname.split('/').pop() || 'index.html'; return PAGE_ALIAS[f] || f; }
  /* Values opens a small menu so Buy / Sell and Overrides have a visible way in (Jeremy, 2026-11-06). */
  var VALUE_VIEWS = [['values.html','Chart','Every player ranked by trade value'],['values.html#buy-sell','Buy / Sell','Who to buy and sell on your roster'],['values.html#overrides','Overrides','Set your own value for a player']];
  function valueMenu(cur){
    var onValues = cur === 'values.html';
    return '<span class="valwrap"><a href="values.html"' + (onValues ? ' aria-current="page"' : '') + '>Values</a>' +
      '<button type="button" class="valcaret" aria-label="Values views" aria-haspopup="true" aria-expanded="false">&#9662;</button>' +
      '<div class="valmenu" role="menu">' + VALUE_VIEWS.map(function(v){
        return '<a role="menuitem" href="' + v[0] + '"><strong>' + v[1] + '</strong><small>' + v[2] + '</small></a>';
      }).join('') + '</div></span>';
  }
  function links(list, current, withValueMenu){
    return list.map(function(it){
      if(withValueMenu && it[0] === 'values.html') return valueMenu(current);
      var cur = it[0] === current ? ' aria-current="page"' : '';
      return '<a href="' + it[0] + '"' + cur + '>' + it[1] + '</a>';
    }).join('');
  }
  /* Chip dropdown text: source line + settings line, from the page's league strip text when it has one, else from the loaded link. */
  function fillChipMenu(wrap){
    wrap = wrap || document.querySelector('.ddf-chipwrap'); if(!wrap) return;
    var src = 'My league', set = '';
    var strip = document.querySelector('.ctx-strip > span:first-child');
    var parts = strip ? strip.textContent.split(' · ') : null;
    if(parts && parts.length > 2){ src = parts[0] + ' · ' + parts[1]; set = parts.slice(2).join(' · '); }
    else if(window.DDF && DDF.link && DDF.link.current){
      var st = DDF.link.current();
      if(st && st.settings){ src = 'My league · From your chat'; set = DDF.link.settingsLabel(st.settings); }
      else if(DDF.league && DDF.league.current && DDF.league.current()){ var lg = DDF.league.current(); src = lg.name; set = DDF.link.settingsLabel(lg.settings); }
    }
    var M = window.DDF && DDF.leagueMeta, info = M ? M.info() : null;
    if(info && info.named) src = info.name + (info.team ? ' · ' + info.team : '');
    wrap.querySelector('.ddf-cm-src').textContent = src;
    var p = wrap.querySelector('.ddf-cm-set'); p.textContent = set; p.hidden = !set;
    /* JEG-1564: the same age line as the page banner (DDF.leagueMeta.ageLine) */
    var age = wrap.querySelector('.ddf-cm-age'), line = M ? M.ageLine() : '';
    if(age){ age.textContent = line; age.hidden = !line; }
  }
  window.DDF = window.DDF || {}; window.DDF.fillChipMenu = fillChipMenu;
  document.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('.ddf-chipwrap .ddf-chip');
    document.querySelectorAll('.ddf-chipwrap.open').forEach(function(w){ if(!b || !w.contains(b)){ w.classList.remove('open'); w.querySelector('.ddf-chip').setAttribute('aria-expanded','false'); } });
    if(b){ var w = b.parentNode, on = !w.classList.contains('open'); if(on) fillChipMenu(w); w.classList.toggle('open', on); b.setAttribute('aria-expanded', String(on)); }
  });
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape') document.querySelectorAll('.ddf-chipwrap.open').forEach(function(w){ w.classList.remove('open'); var c = w.querySelector('.ddf-chip'); c.setAttribute('aria-expanded','false'); c.focus(); });
  });
  function apply(){
    var nav = document.querySelector('header nav[aria-label="Main navigation"]');
    if(!nav) return;
    var loaded = leagueLoaded(), cur = file();
    var wrap = nav.querySelector('.morewrap'), menu = wrap && wrap.querySelector('.menu');
    Array.prototype.slice.call(nav.querySelectorAll(':scope > a, :scope > .valwrap')).forEach(function(a){ a.remove(); });
    var holder = document.createElement('div');
    var isHome = (cur === 'index.html'); holder.innerHTML = links(loaded ? POST : (isHome ? PRE_HOME : PRE), cur, true);
    Array.prototype.slice.call(holder.children).forEach(function(a){ nav.insertBefore(a, wrap || null); });
    if(menu && !menu.querySelector('.menu-group')){
      menu.innerHTML = links(loaded ? MENU_POST : MENU_PRE, cur);
    }
    /* right-hand slot: Get started before a league, a quiet chip after */
    var host = nav.parentNode;
    var old = host.querySelector('.ddf-gs, .ddf-chipwrap, .ddf-chip, .getstarted');
    if(old) old.remove();
    var x = document.createElement(loaded ? 'span' : 'a');
    if(loaded){
      x.className = 'ddf-chipwrap';
      x.innerHTML = '<button type="button" class="ddf-chip" aria-haspopup="true" aria-expanded="false" aria-controls="ddf-chip-menu"><i aria-hidden="true"></i><span class="ddf-chip-t">Your league</span><span class="ddf-caret" aria-hidden="true">&#9662;</span></button>' +
        '<div class="ddf-chipmenu" id="ddf-chip-menu"><p class="ddf-cm-src"></p><p class="ddf-cm-set"></p><p class="ddf-cm-age" hidden></p><a href="settings.html">Edit league</a></div>';
      fillChipMenu(x);
      setTimeout(function(){ if(window.DDF && DDF.fitLeagueChip) DDF.fitLeagueChip(); }, 0);
    }
    else { x.className = 'ddf-gs'; x.href = 'connect.html'; x.innerHTML = 'Get started'; }
    host.appendChild(x);
    document.documentElement.setAttribute('data-league', loaded ? 'loaded' : 'none'); document.documentElement.setAttribute('data-nav', loaded ? 'journey' : (isHome ? 'home' : 'key'));
    /* Home hero: before a league the one big button starts setup; after it, continue to the team */
    var hero = document.querySelector('.hero2 .cta2'), quick = document.querySelector('.hero2 .quickcheck');
    if(hero){ hero.textContent = loaded ? 'Open your team →' : 'Get started →'; hero.setAttribute('href', loaded ? 'team.html' : 'connect.html'); }
    if(quick) quick.hidden = loaded;
  }
  window.DDF = window.DDF || {};
  window.DDF.refreshNav = apply;
  if(document.querySelector('header nav[aria-label="Main navigation"]')) apply();
  else document.addEventListener('DOMContentLoaded', apply);
  document.addEventListener('ddf:link', function(){ apply(); });
  window.addEventListener('hashchange', apply);
})();

/* ===== Shared chrome enhancements ===== */
(function(){
  /* Session state helper: window.DDF.state.get(key, fallback) / set(key, value) / remove(key).
     Suggested keys: partner, give, get, filters. Pages opt in; nothing here changes page behavior. */
  var PREFIX = 'ddf:';
  window.DDF = window.DDF || {};
  window.DDF.state = {
    get: function(key, fallback){
      try{ var v = sessionStorage.getItem(PREFIX + key); return v === null ? fallback : JSON.parse(v); }
      catch(e){ return fallback; }
    },
    set: function(key, value){
      try{ sessionStorage.setItem(PREFIX + key, JSON.stringify(value)); return true; }
      catch(e){ return false; }
    },
    remove: function(key){ try{ sessionStorage.removeItem(PREFIX + key); }catch(e){} }
  };

  function init(){
    var wrap = document.querySelector('.morewrap');
    var menu = wrap && wrap.querySelector('.menu');
    var button = wrap && wrap.querySelector(':scope > button');
    if(!wrap || !menu || !button) return;

    /* Menu label: "More" on desktop, "Menu" on mobile (CSS switches them). */
    if(!button.querySelector('.lbl-menu')){
      button.innerHTML = '<span class="ddf-lbl-more">More ▾</span><span class="ddf-lbl-menu">Menu ☰</span>';
    }

    /* Group links per the product map (F1-B). Pages without a link just skip that item. */
    var GROUPS = [
      ['', ['index.html']],
      ['Trade', ['build.html?mode=any','build.html','find.html','waivers.html']],
      ['Your league', ['team.html','explore.html','partners.html']],
      ['Player values', ['values.html','values.html#buy-sell','values.html#overrides']],
      ['Learn', ['learn.html','learn.html#numbers/pie','ai.html']],
      ['Settings', ['connect.html','setup.html','settings.html']]
    ];
    var links = {};
    menu.querySelectorAll(':scope > a').forEach(function(a){
      links[(a.getAttribute('href') || '')] = a;
    });
    var nav = wrap.closest('nav');
    if(nav){
      nav.querySelectorAll(':scope > a:not(.ddf-gs):not(.ddf-chip)').forEach(function(a){
        var key = (a.getAttribute('href') || '');
        if(links[key]) return;
        var c = a.cloneNode(true);
        c.classList.add('is-nav-dup');
        links[key] = c;
      });
    }
    var used = {}, frag = document.createDocumentFragment();
    function addGroup(label, hrefs){
      var items = hrefs.filter(function(h){ return links[h] && !used[h]; });
      if(!items.length) return;
      var g = document.createElement('div');
      g.className = 'menu-group';
      g.setAttribute('role', 'group');
      if(label){
        var l = document.createElement('span');
        l.className = 'menu-group-label';
        l.textContent = label;
        g.setAttribute('aria-label', label);
        g.appendChild(l);
      }
      var allDup = true;
      items.forEach(function(h){
        used[h] = 1; g.appendChild(links[h]);
        if(!links[h].classList.contains('is-nav-dup')) allDup = false;
      });
      if(allDup) g.classList.add('is-nav-dup');
      frag.appendChild(g);
    }
    GROUPS.forEach(function(g){ addGroup(g[0], g[1]); });
    var rest = Object.keys(links).filter(function(h){ return !used[h]; });
    addGroup('More', rest);
    menu.textContent = '';
    menu.appendChild(frag);

    /* Wrap bare tables so wide ones scroll inside the page instead of widening it. */
    document.querySelectorAll('main table').forEach(function(t){
      if(t.closest('.table-wrap,.ddf-table-wrap')) return;
      var w = document.createElement('div');
      w.className = 'ddf-table-wrap';
      t.parentNode.insertBefore(w, t);
      w.appendChild(t);
    });
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

/* Cross-device copy helper: clipboard API -> textarea+execCommand (iOS/old Android) -> visible box to copy by hand. */
(function(){
  window.DDF = window.DDF || {};
  window.DDF.copyText = async function(text, statusEl, okMsg){
    function say(m){ if(statusEl) statusEl.textContent = m; }
    okMsg = okMsg || 'Copied.';
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); say(okMsg); return true; }
    } catch(e) {}
    try {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly','');
      ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;font-size:16px';
      document.body.appendChild(ta);
      ta.focus(); ta.select(); ta.setSelectionRange(0, text.length);
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      if (ok) { say(okMsg); return true; }
    } catch(e) {}
    var box = document.getElementById('ddf-copy-fallback');
    if (!box) {
      box = document.createElement('textarea');
      box.id = 'ddf-copy-fallback'; box.readOnly = true; box.setAttribute('aria-label','Prompt text to copy');
      box.style.cssText = 'display:block;width:100%;max-width:640px;height:8rem;margin:.75rem auto;font:16px/1.4 monospace;padding:.5rem';
      (statusEl && statusEl.parentNode ? statusEl.parentNode.parentNode : document.body).appendChild(box);
    }
    box.value = text; box.focus(); box.select(); box.setSelectionRange(0, text.length);
    say('Select all in the box and copy it.');
    return false;
  };
})();

/* ===== Chat link state: window.DDF.link =====
   A chat sends people here with <page>#s=<token>+<check>. The league lives only in the link (no server).
   Wire format, schema and sizes: 08-ai-module/LINK-FORMAT.md. */
(function(){
  var DDF = window.DDF = window.DDF || {};
  var VIEW_PAGES = {team:'team.html', explore:'explore.html', partners:'partners.html', recommendations:'find.html',
    build:'build.html', check:'check.html', values:'values.html', waivers:'waivers.html'};
  var SCORING = ['ppr', 'half_ppr', 'standard'];           /* header code 3 = settings not given */
  var SCORING_LABEL = {ppr:'PPR', half_ppr:'Half PPR', standard:'Standard'};
  var SCORING_ALIAS = {ppr:'ppr', full:'ppr', full_ppr:'ppr', half_ppr:'half_ppr', half:'half_ppr', '0.5ppr':'half_ppr',
    '0.5_ppr':'half_ppr', standard:'standard', std:'standard', non_ppr:'standard', nonppr:'standard'};
  var TEAMS = [8, 10, 12, 14];
  var SLOT_KEYS = ['qb', 'rb', 'wr', 'te', 'flex', 'bench'];
  var SLOT_MAX = 20;
  var HEADER_LEN = 7, FORMAT_VERSION = 1;
  var ID_BITS = 10, ID_ESCAPE = 1023, ID_MAX = 1022;
  var B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  var B64_RE = /^[A-Za-z0-9_-]*$/;
  var LIST_PATHS = [['waivers'], ['trade', 'give'], ['trade', 'get']];   /* plus teams[i].players */

  /* ---- bytes / text ---- */
  function bytesToB64(bytes){
    var out = '', i, n;
    for(i = 0; i < bytes.length; i += 3){
      n = (bytes[i] << 16) | ((bytes[i + 1] || 0) << 8) | (bytes[i + 2] || 0);
      out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63];
      if(i + 1 < bytes.length) out += B64[(n >> 6) & 63];
      if(i + 2 < bytes.length) out += B64[n & 63];
    }
    return out;
  }
  function b64ToBytes(str){
    if(!B64_RE.test(str) || str.length % 4 === 1) return null;
    var out = new Uint8Array(Math.floor(str.length * 3 / 4)), bits = 0, acc = 0, j = 0;
    for(var i = 0; i < str.length; i++){
      acc = (acc << 6) | B64.indexOf(str[i]); bits += 6;
      if(bits >= 8){ bits -= 8; out[j++] = (acc >> bits) & 255; }
    }
    return out;
  }
  /* CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) of the token's ASCII; Python: binascii.crc_hqx(data, 0xFFFF). */
  function crc16(str){
    var crc = 0xFFFF;
    for(var i = 0; i < str.length; i++){
      crc ^= str.charCodeAt(i) << 8;
      for(var k = 0; k < 8; k++) crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xFFFF : (crc << 1) & 0xFFFF;
    }
    return crc;
  }
  function checkChars(token){ var c = crc16(token); return B64[(c >> 10) & 63] + B64[(c >> 4) & 63]; }

  function streamBytes(bytes, transform){
    return new Response(new Blob([bytes]).stream().pipeThrough(transform)).arrayBuffer().then(function(b){ return new Uint8Array(b); });
  }
  function canCompress(){ return typeof CompressionStream === 'function' && typeof DecompressionStream === 'function'; }

  /* ---- settings ---- */
  function normalizeSettings(s){
    if(!s || typeof s !== 'object') return null;
    var scoring = SCORING_ALIAS[String(s.scoring || '').trim().toLowerCase().replace(/[\s-]+/g, '_')];
    var teams = Number(s.teams);
    var sf = s.superflex;
    if(sf === 1 || sf === 0) sf = !!sf;
    var slots = Array.isArray(s.slots) ? s.slots.slice() : (s.slots && typeof s.slots === 'object' ? SLOT_KEYS.map(function(k){ return s.slots[k]; }) : null);
    if(!scoring || TEAMS.indexOf(teams) < 0 || typeof sf !== 'boolean' || !slots || slots.length !== 6) return null;
    slots = slots.map(Number);
    if(slots.some(function(n){ return !Number.isInteger(n) || n < 0 || n > SLOT_MAX; })) return null;
    if(slots[0] + slots[1] + slots[2] + slots[3] + slots[4] === 0) return null;
    var out = {scoring:scoring, teams:teams, superflex:sf, slots:slots};
    if(s.extras && typeof s.extras === 'object' && !Array.isArray(s.extras)) out.extras = s.extras;
    return out;
  }
  function settingsHeader(st){
    var h = new Uint8Array(HEADER_LEN);
    h[0] = (FORMAT_VERSION << 5) | (SCORING.indexOf(st.scoring) << 3) | (TEAMS.indexOf(st.teams) << 1) | (st.superflex ? 1 : 0);
    for(var i = 0; i < 6; i++) h[i + 1] = st.slots[i];
    return h;
  }
  function readHeader(bytes){
    if(bytes.length < HEADER_LEN) return {error:'settings'};
    var b = bytes[0];
    if((b >> 5) !== FORMAT_VERSION) return {error:'format'};
    var sc = (b >> 3) & 3;
    if(sc === 3) return {error:'settings'};
    var st = normalizeSettings({scoring:SCORING[sc], teams:TEAMS[(b >> 1) & 3], superflex:!!(b & 1), slots:Array.prototype.slice.call(bytes, 1, 7)});
    return st ? {settings:st} : {error:'settings'};
  }

  /* ---- player lists. In state: arrays of <id>|name. On the wire (packed): "#<count>" or "#<count>~Name~Name",
     taking <count> slots in order from one 10-bit ID stream stored before the deflated JSON; slot 1023 = next name. ---- */
  function packAll(body){
    var ids = [];
    mapLists(body, function(l){
      if(!Array.isArray(l) || !l.some(Number.isInteger)) return l;
      if(l.some(function(p){ return typeof p === 'string' && p.indexOf('~') >= 0; })) return l;
      var names = [];
      l.forEach(function(p){ if(Number.isInteger(p)) ids.push(p); else { ids.push(ID_ESCAPE); names.push(p); } });
      return ['#' + l.length].concat(names).join('~');
    });
    return ids;
  }
  function unpackAll(body, ids){
    var pos = 0;
    mapLists(body, function(l){
      if(Array.isArray(l)) return l;
      if(typeof l !== 'string' || l[0] !== '#') throw 'format';
      var parts = l.split('~'), k = Number(parts[0].slice(1)), names = parts.slice(1), out = [];
      if(!Number.isInteger(k) || k < 0 || pos + k > ids.length) throw 'format';
      for(var i = 0; i < k; i++){
        var id = ids[pos++];
        if(id !== ID_ESCAPE) out.push(id);
        else if(names.length) out.push(names.shift());
        else throw 'format';
      }
      if(names.length) throw 'format';
      return out;
    });
    if(pos !== ids.length) throw 'format';
    return body;
  }
  function bitsPack(ids){
    var bytes = new Uint8Array(Math.ceil(ids.length * ID_BITS / 8)), acc = 0, nbits = 0, j = 0;
    ids.forEach(function(id){
      acc = (acc << ID_BITS) | id; nbits += ID_BITS;
      while(nbits >= 8){ nbits -= 8; bytes[j++] = (acc >> nbits) & 255; acc &= (1 << nbits) - 1; }
    });
    if(nbits) bytes[j] = (acc << (8 - nbits)) & 255;
    return bytes;
  }
  function bitsUnpack(bytes, n){
    var out = [], acc = 0, nbits = 0;
    for(var i = 0; i < bytes.length && out.length < n; i++){
      acc = (acc << 8) | bytes[i]; nbits += 8;
      if(nbits >= ID_BITS){ nbits -= ID_BITS; out.push((acc >> nbits) & ID_ESCAPE); acc &= (1 << nbits) - 1; }
    }
    return out;
  }
  function varint(n){ var out = []; do { var b = n & 127; n >>>= 7; out.push(n ? b | 128 : b); } while(n); return out; }
  function readVarint(bytes, pos){
    var n = 0, shift = 0, b;
    do { if(pos >= bytes.length || shift > 21) return null; b = bytes[pos++]; n |= (b & 127) << shift; shift += 7; } while(b & 128);
    return {value:n, pos:pos};
  }
  function mapLists(state, fn){
    if(Array.isArray(state.teams)) state.teams.forEach(function(t){ if(t && 'players' in t) t.players = fn(t.players); });
    LIST_PATHS.forEach(function(p){
      var o = p.length === 1 ? state : state[p[0]], k = p[p.length - 1];
      if(o && typeof o === 'object' && k in o) o[k] = fn(o[k]);
    });
    return state;
  }
  function isPlayer(p){ return (Number.isInteger(p) && p >= 0 && p <= ID_MAX) || (typeof p === 'string' && p.trim() !== ''); }
  function validBody(st){
    if(!st || typeof st !== 'object' || st.v !== 1) return false;
    if('view' in st && typeof st.view !== 'string') return false;
    var ok = true;
    if('teams' in st){
      if(!Array.isArray(st.teams)) return false;
      st.teams.forEach(function(t){ if(!t || typeof t !== 'object' || (t.players && !Array.isArray(t.players))) ok = false; });
      if('me' in st && !(Number.isInteger(st.me) && st.me >= 0 && st.me < st.teams.length)) return false;
    }
    mapLists(st, function(l){ if(!Array.isArray(l) || !l.every(isPlayer)) ok = false; return l; });
    return ok;
  }
  function clone(o){ return JSON.parse(JSON.stringify(o)); }

  /* ---- reader context (LINK-FORMAT.md 3.2): state.overrides {<id>|name: 0-200}, state.basis {mode, source?, weights?},
     settings.extras.positionWeights {starter:[qb,rb,wr,te] 0-5, bench:[qb,rb,wr,te] 0-100}. All in the JSON body.
     Reading drops bad entries (strict = false); encoding an explicit state rejects them (strict = true, Error('format')).
     On arrival they move into their own session stores: DDF.overrides ('ddf:overrides'), 'ddf:basis', 'ddf:posweights'. ---- */
  var OV_MAX = 100, OV_HI = 200, PW_MAX = {starter:5, bench:100};
  var BASIS_MODES = ['default', 'source', 'custom'];
  var SOURCE_RE = /^[a-z0-9_]{1,24}$/, ID_KEY_RE = /^\d{1,4}$/;
  var SOURCE_LABEL = {cbs:'CBS', usatoday:'USA Today', fantasypros:'FantasyPros', fantasycalc:'FantasyCalc', espn:'ESPN'};
  function round(n, d){ var f = Math.pow(10, d); return Math.round(n * f) / f; }
  function isObj(o){ return !!o && typeof o === 'object' && !Array.isArray(o); }
  function isNum(v, hi){ return typeof v === 'number' && isFinite(v) && v >= 0 && v <= hi; }
  function cleanOverrides(o, strict){
    if(!isObj(o)){ if(strict) throw 'format'; return null; }
    var out = {}, n = 0;
    Object.keys(o).forEach(function(k){
      var key = String(k).trim(), isId = ID_KEY_RE.test(key);
      if(!key || key.length > 80 || (isId && Number(key) > ID_MAX) || !isNum(o[k], OV_HI) || n >= OV_MAX){ if(strict) throw 'format'; return; }
      out[isId ? String(Number(key)) : key] = round(o[k], 1); n++;
    });
    return out;
  }
  function cleanBasis(b, strict){
    function bad(){ if(strict) throw 'format'; return null; }
    if(!isObj(b) || BASIS_MODES.indexOf(b.mode) < 0) return bad();
    if(b.mode === 'default') return {mode:'default'};
    if(b.mode === 'source') return typeof b.source === 'string' && SOURCE_RE.test(b.source) ? {mode:'source', source:b.source} : bad();
    if(!isObj(b.weights)) return bad();
    var keys = Object.keys(b.weights), w = {}, any = false;
    if(!keys.length || keys.length > 12) return bad();
    for(var i = 0; i < keys.length; i++){
      if(!SOURCE_RE.test(keys[i]) || !isNum(b.weights[keys[i]], 100)) return bad();
      w[keys[i]] = round(b.weights[keys[i]], 2); if(w[keys[i]] > 0) any = true;
    }
    return any ? {mode:'custom', weights:w} : bad();
  }
  function cleanWeights(pw, strict){
    function bad(){ if(strict) throw 'format'; return null; }
    if(!isObj(pw)) return bad();
    var out = {};
    for(var k in PW_MAX){
      var a = pw[k];
      if(!Array.isArray(a) || a.length !== 4 || !a.every(function(v){ return isNum(v, PW_MAX[k]); })) return bad();
      out[k] = a.map(function(v){ return round(v, 2); });
    }
    return out;
  }
  /* League name and roster input date (JEG-1564), JSON body only: name = 1-40 chars, enteredAt = 'YYYY-MM-DD'.
     Readers drop a bad value; writers reject it. Header and ID stream unchanged; old decoders keep them as unknown keys. */
  var DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
  function cleanName(n){ if(typeof n !== 'string') return null; n = n.replace(/[\u0000-\u001f]/g, ' ').replace(/\s+/g, ' ').trim(); return n && Array.from(n).length <= 40 ? n : null; }
  function cleanDate(d){
    var m = typeof d === 'string' && DATE_RE.exec(d); if(!m) return null;
    var t = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return t.getUTCFullYear() === +m[1] && t.getUTCMonth() === +m[2] - 1 && t.getUTCDate() === +m[3] ? d : null;
  }
  function normalizeMeta(st, strict){
    if('name' in st){ var n = cleanName(st.name); if(n) st.name = n; else if(strict) throw new Error('format'); else delete st.name; }
    if('enteredAt' in st){ var d = cleanDate(st.enteredAt); if(d) st.enteredAt = d; else if(strict) throw new Error('format'); else delete st.enteredAt; }
    return st;
  }
  function normalizeContext(st, strict){
    normalizeMeta(st, strict);
    if('overrides' in st){ var o = cleanOverrides(st.overrides, strict); if(o) st.overrides = o; else delete st.overrides; }
    if('basis' in st){ var b = cleanBasis(st.basis, strict); if(b) st.basis = b; else delete st.basis; }
    var ex = st.settings && st.settings.extras;
    if(isObj(ex) && 'positionWeights' in ex){ var pw = cleanWeights(ex.positionWeights, strict); if(pw) ex.positionWeights = pw; else delete ex.positionWeights; }
    return st;
  }
  function hasIdKeys(o){ return isObj(o) && Object.keys(o).some(function(k){ return ID_KEY_RE.test(k); }); }

  /* ---- player table ("Name|POS|TEAM" strings, index = id), versioned ---- */
  var tables = {};
  function getTable(v){
    v = v || 1;
    if(!tables[v]){ var t = DDF.state.get('table:' + v, null); if(Array.isArray(t)) tables[v] = t; }
    return tables[v] || null;
  }
  function player(entry, v){
    if(typeof entry === 'string') return {id:null, name:entry, pos:'', team:'', key:''};
    var row = (getTable(v) || [])[entry];
    if(typeof row !== 'string') return {id:entry, name:null, pos:'', team:'', key:''};
    var f = row.split('|');
    return {id:entry, name:f[0], pos:f[1] || '', team:f[2] || '', key:f[3] || ''};   /* rows: Name|POS|TEAM|player_key (key optional) */
  }

  /* ---- token <-> state ---- */
  function encodeToken(state, opts){
    opts = opts || {};
    var st = normalizeSettings(state && state.settings);
    if(!st) return Promise.reject(new Error('settings'));
    if(!canCompress()) return Promise.reject(new Error('unsupported'));
    var body = clone(state);
    body.v = 1;
    try{ normalizeContext(body, true); }catch(e){ return Promise.reject(new Error('format')); }
    if(opts.useIds){
      var idx = nameIndex(body.table); mapLists(body, function(l){ return (l || []).map(function(p){ return typeof p === 'string' && idx[p.toLowerCase()] !== undefined ? idx[p.toLowerCase()] : p; }); });
      if(body.overrides) body.overrides = overridesById(body.overrides, body.table);
    }
    var hasIds = hasIdKeys(body.overrides);
    mapLists(body, function(l){ if((l || []).some(Number.isInteger)) hasIds = true; return l; });
    if(hasIds && !body.table) body.table = 1;
    if(!validBody(body)) return Promise.reject(new Error('format'));
    if(st.extras) body.settings = {extras:body.settings.extras}; else delete body.settings;
    var ids = opts.pack === false ? [] : packAll(body);
    var pre = [].concat(Array.from(settingsHeader(st)), varint(ids.length), Array.from(bitsPack(ids)));
    var json = new TextEncoder().encode(JSON.stringify(body));
    return streamBytes(json, new CompressionStream('deflate-raw')).then(function(z){
      var all = new Uint8Array(pre.length + z.length);
      all.set(pre); all.set(z, pre.length);
      var token = bytesToB64(all);
      return token + '+' + checkChars(token);
    });
  }
  function nameIndex(v){
    var idx = {};
    (getTable(v || 1) || []).forEach(function(r, i){ var n = String(r).split('|')[0].toLowerCase(); if(!(n in idx)) idx[n] = i; });
    return idx;
  }
  function parseToken(raw){
    var t = String(raw || '').trim();
    try{ t = decodeURIComponent(t); }catch(e){}
    var m = /^([A-Za-z0-9_-]+)[+ ]([A-Za-z0-9_-]{2})(?![A-Za-z0-9_-])/.exec(t);
    if(!m) return {error:'format'};
    return checkChars(m[1]) === m[2] ? {token:m[1]} : {error:'checksum'};
  }
  function decodeToken(raw){
    var p = parseToken(raw);
    if(p.error) return Promise.resolve({error:p.error});
    var bytes = b64ToBytes(p.token);
    if(!bytes) return Promise.resolve({error:'format'});
    var h = readHeader(bytes);
    if(h.error) return Promise.resolve({error:h.error});
    var n = readVarint(bytes, HEADER_LEN);
    if(!n) return Promise.resolve({error:'format'});
    var blobEnd = n.pos + Math.ceil(n.value * ID_BITS / 8);
    if(blobEnd > bytes.length) return Promise.resolve({error:'format'});
    var ids = bitsUnpack(bytes.slice(n.pos, blobEnd), n.value);
    if(!canCompress()) return Promise.resolve({error:'unsupported'});
    return streamBytes(bytes.slice(blobEnd), new DecompressionStream('deflate-raw')).then(function(out){
      var body = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(out));
      unpackAll(body, ids);
      if(!validBody(body)) return {error:'format'};
      var extras = body.settings && body.settings.extras;
      body.settings = h.settings;
      if(extras && typeof extras === 'object') body.settings.extras = extras;
      return normalizeContext(body, false);
    }).catch(function(){ return {error:'format'}; });
  }
  function fragmentToken(hash){
    var parts = String(hash || '').replace(/^#/, '').split('&');
    for(var i = 0; i < parts.length; i++) if(parts[i].slice(0, 2) === 's=') return parts[i].slice(2);
    return null;
  }
  function decodeJsonState(text){
    var st;
    try{ st = JSON.parse(text); }catch(e){ return {error:'format'}; }
    if(!st || typeof st !== 'object') return {error:'format'};
    if(st.v === 2) st.v = 1;   /* v:2 = a block the MCP server wrote: same schema (LINK-FORMAT.md 3.1) */
    var settings = normalizeSettings(st.settings);
    if(!settings) return {error:'settings'};
    st.settings = settings;
    return validBody(st) ? normalizeContext(st, false) : {error:'format'};
  }

  /* ---- reader context stores: DDF.overrides (names as keys), 'ddf:basis', 'ddf:posweights' ---- */
  function readOverrides(){ var o = DDF.overrides ? DDF.overrides.get() : DDF.state.get('overrides', {}); return isObj(o) ? o : {}; }
  /* _fromLink: the bookmark prompt (JEG-1564) does not count a link's overrides as the reader's own edits */
  function writeOverrides(o){ if(DDF.overrides && DDF.overrides.replace){ DDF.overrides._fromLink = true; try{ DDF.overrides.replace(o); } finally { DDF.overrides._fromLink = false; } } else DDF.state.set('overrides', o); }
  /* ID keys -> table names (unresolvable IDs are dropped: the site keys overrides by name). */
  function overridesByName(o, v){
    var out = {};
    Object.keys(o || {}).forEach(function(k){ var n = ID_KEY_RE.test(k) ? player(Number(k), v).name : k; if(n) out[n] = o[k]; });
    return out;
  }
  /* Names on the table -> ID keys (shorter on the wire); other names stay. */
  function overridesById(o, v){
    var idx = nameIndex(v), out = {};
    Object.keys(o || {}).forEach(function(k){ var i = ID_KEY_RE.test(k) ? undefined : idx[k.toLowerCase()]; out[i === undefined ? k : String(i)] = o[k]; });
    return out;
  }
  function storedContext(){
    var o = cleanOverrides(readOverrides(), false) || {};
    return {overrides:o, basis:cleanBasis(DDF.state.get('basis', null), false), positionWeights:cleanWeights(DDF.state.get('posweights', null), false)};
  }
  /* A copy of state plus the reader's stored context wherever state does not already say it. */
  function withContext(state, useIds){
    var s = clone(state), c = storedContext();
    if(!('overrides' in s) && Object.keys(c.overrides).length) s.overrides = useIds ? overridesById(c.overrides, s.table) : c.overrides;
    if(!('basis' in s) && c.basis) s.basis = c.basis;
    if(c.positionWeights && isObj(s.settings)){
      var ex = isObj(s.settings.extras) ? s.settings.extras : {};
      if(!('positionWeights' in ex)) s.settings.extras = Object.assign({}, ex, {positionWeights:c.positionWeights});
    }
    return s;
  }
  /* Arrival: the link's context replaces the stored one, field by field (a field the link does not carry is left alone). */
  function applyContext(st){
    if('overrides' in st) writeOverrides(overridesByName(st.overrides, st.table));
    if('basis' in st) DDF.state.set('basis', st.basis);
    var ex = st.settings && st.settings.extras;
    if(isObj(ex) && 'positionWeights' in ex) DDF.state.set('posweights', ex.positionWeights);
  }
  function stripContext(st){
    var c = clone(st);
    delete c.overrides; delete c.basis;
    if(c.settings && isObj(c.settings.extras) && 'positionWeights' in c.settings.extras){
      delete c.settings.extras.positionWeights;
      if(!Object.keys(c.settings.extras).length) delete c.settings.extras;
    }
    return c;
  }
  function describeContext(){
    var c = storedContext(), parts = [], n = Object.keys(c.overrides).length;
    if(n) parts.push(n + (n === 1 ? ' override' : ' overrides'));
    if(c.basis && c.basis.mode === 'source') parts.push((SOURCE_LABEL[c.basis.source] || c.basis.source) + ' only');
    if(c.basis && c.basis.mode === 'custom') parts.push('custom blend');
    if(c.positionWeights) parts.push('custom position weights');
    return parts.join(' · ');
  }

  /* ---- live state ---- */
  var current = null, lastError = null, fromLink = false;
  /* The league state is kept without its reader context: that lives in the stores above, so edits made on the site win. */
  function accept(state){
    current = stripContext(state); lastError = null;
    DDF.state.set('league', current);
    DDF.state.remove('pasted');   /* a league from a link replaces a pasted one in this tab (JEG-1538) */
    DDF.state.set('link', {source:'chat', at:Date.now()});
    return state;
  }
  function pageFor(view){ return VIEW_PAGES[view] || 'team.html'; }
  function livePage(view){ var p = pageFor(view); return p.indexOf('#') >= 0 ? 'values.html' : p; }
  function isConnectPage(){ return /(^|\/)connect\.html$/.test(location.pathname) || document.body.classList.contains('connect'); }

  /* Pretty JSON with primitive arrays on one line, so a 12-team block stays readable in a chat. */
  function readable(v, ind){
    ind = ind || '';
    if(Array.isArray(v)){
      if(v.every(function(x){ return x === null || typeof x !== 'object'; })) return '[' + v.map(function(x){ return JSON.stringify(x); }).join(', ') + ']';
      return '[\n' + v.map(function(x){ return ind + '  ' + readable(x, ind + '  '); }).join(',\n') + '\n' + ind + ']';
    }
    if(v && typeof v === 'object'){
      var keys = Object.keys(v);
      if(keys.length <= 3 && keys.every(function(k){ return v[k] === null || typeof v[k] !== 'object'; })) return '{' + keys.map(function(k){ return JSON.stringify(k) + ': ' + JSON.stringify(v[k]); }).join(', ') + '}';
      return '{\n' + keys.map(function(k){ return ind + '  ' + JSON.stringify(k) + ': ' + readable(v[k], ind + '  '); }).join(',\n') + '\n' + ind + '}';
    }
    return JSON.stringify(v);
  }

  DDF.link = {
    VIEW_PAGES: VIEW_PAGES,
    hasState: function(){ return fragmentToken(location.hash) !== null; },
    decode: function(){
      var raw = fragmentToken(location.hash);
      if(raw === null) return Promise.resolve(null);
      return decodeToken(raw).then(function(r){
        if(r && r.error){ lastError = r.error; return r; }
        fromLink = true;
        /* Apply a link's context once: a reload of the same link keeps what the reader changed since. */
        var p = parseToken(raw), mark = p.token ? p.token.length + '.' + crc16(p.token) : null;
        if(DDF.state.get('ctxlink', null) !== mark){ applyContext(r); DDF.state.set('ctxlink', mark); }
        return accept(r);
      });
    },
    decodeBlock: function(text){
      var t = String(text || '').trim();
      var fence = /```\s*ddf-state\s*\n([\s\S]*?)```/.exec(t);
      var p = fence ? Promise.resolve(decodeJsonState(fence[1]))
        : /^[{]/.test(t) ? Promise.resolve(decodeJsonState(t))
        : decodeToken(fragmentToken((/#(.*)$/.exec(t) || [])[1] || '') || t.replace(/^s=/, ''));
      return p.then(function(r){ if(r.error){ lastError = r.error; return r; } applyContext(r); return accept(r); });
    },
    /* Adds the reader's overrides, basis and position weights unless state carries them (opts.context === false: as given). */
    encode: function(state, opts){
      opts = opts || {};
      var st = opts.context === false || !state || typeof state !== 'object' ? state : withContext(state, true);
      return encodeToken(st, opts).then(function(token){
        var page = opts.page || 'connect.html';
        var base = opts.base ? new URL(page, opts.base) : new URL(page, location.href);
        base.hash = 's=' + token;
        return base.href;
      });
    },
    encodeToken: encodeToken,
    current: function(){ return current || (DDF.state.get('link', null) ? DDF.state.get('league', null) : null); },
    settings: function(){ var s = DDF.link.current(); return s ? s.settings : null; },
    error: function(){ return lastError; },
    clear: function(){ current = null; fromLink = false; DDF.state.remove('league'); DDF.state.remove('link'); },
    update: function(patch){ var s = DDF.link.current(); if(!s) return null; return accept(Object.assign(clone(s), patch)); },
    pageFor: pageFor,
    /* A view whose page is not live yet maps to a live hash route at the root build ('./#compare-trade'), where no page
       reads the league. Until that page swaps in, such a link opens Values with the token, as v2 did before the entry
       pages moved (values.html applies the link's overrides and basis to the live store) (JEG-1538). */
    go: function(state){ return DDF.link.encode(state, {page:livePage(state.view)}).then(function(u){ location.assign(u); }); },
    applyRouting: function(){
      var s = current;
      if(!s || !fromLink || !isConnectPage()) return false;
      location.replace(livePage(s.view) + location.hash);
      return true;
    },
    registerTable: function(version, rows){
      if(!Array.isArray(rows) || rows.length > ID_MAX + 1) throw new Error('table');
      tables[version] = rows; DDF.state.set('table:' + version, rows);
    },
    table: getTable,
    player: function(entry){ var s = DDF.link.current(); return player(entry, s && s.table); },
    playerName: function(entry){ var p = DDF.link.player(entry); return p.name || ('Player ' + p.id); },
    settingsLabel: function(st){
      st = st || DDF.link.settings();
      if(!st) return '';
      return SCORING_LABEL[st.scoring] + ' · ' + st.teams + ' teams' + (st.superflex ? ' · Superflex' : '');
    },
    copyForChat: function(statusEl){
      var s = DDF.link.current();
      if(!s){ if(statusEl) statusEl.textContent = 'Nothing from your chat to copy yet.'; return Promise.resolve(false); }
      var out = withContext(s, false), unresolved = false;
      mapLists(out, function(l){ return l.map(function(p){ var r = player(p, s.table); if(r.name) return r.name; unresolved = true; return p; }); });
      if(out.overrides){
        var named = {};
        Object.keys(out.overrides).forEach(function(k){ var n = ID_KEY_RE.test(k) ? player(Number(k), s.table).name : k; if(!n) unresolved = true; named[n || k] = out.overrides[k]; });
        out.overrides = named;
      }
      if(!unresolved) delete out.table;
      var text = '```ddf-state\n' + readable(out) + '\n```';
      return DDF.copyText(text, statusEl, 'Copied. Paste it into your chat.');
    },
    /* The reader context now in effect: {overrides (by name), basis|null, positionWeights|null}. */
    context: storedContext,
    /* Short label for pages, e.g. "2 overrides · custom blend"; '' when the reader uses plain DDF Value. */
    describeContext: describeContext,
    _internal: {packAll:packAll, unpackAll:unpackAll, bitsPack:bitsPack, bitsUnpack:bitsUnpack, crc16:crc16, checkChars:checkChars, bytesToB64:bytesToB64,
      b64ToBytes:b64ToBytes, settingsHeader:settingsHeader, normalizeSettings:normalizeSettings, decodeToken:decodeToken,
      normalizeContext:normalizeContext, withContext:withContext}
  };

  /* ---- page effects ---- */
  var NOTICE = {
    checksum:'The link from your chat looks changed or cut short, so your league was not loaded.',
    format:'The link from your chat could not be read, so your league was not loaded.',
    settings:'The link from your chat has no league settings, so your league was not loaded.',
    unsupported:'This browser cannot open links from your chat.'
  };
  function topOfMain(el){
    var main = document.querySelector('main');
    if(main) main.insertBefore(el, main.firstChild);
  }
  /* "Continued from your chat", plus "+ N overrides" while any are active. */
  function stripText(){
    var n = Object.keys(storedContext().overrides).length;
    return 'Continued from your chat' + (n ? ' + ' + n + (n === 1 ? ' override' : ' overrides') : '');
  }
  function showStrip(){
    if(isConnectPage()) return;
    /* A page with the league summary strip (.ctx-strip) already says "Edit league"; the chat strip is only for pages without it. */
    if(document.querySelector('.ctx-strip')){ var dup = document.querySelector('.ddf-chat-strip'); if(dup) dup.remove(); return; }
    var old = document.querySelector('.ddf-chat-strip');
    if(old){ old.firstChild.textContent = stripText(); return; }
    var d = document.createElement('div');
    d.className = 'ddf-chat-strip'; d.setAttribute('role', 'status');
    d.innerHTML = '<span></span><a href="connect.html">Edit league</a>';
    d.firstChild.textContent = stripText();
    topOfMain(d);
  }
  document.addEventListener('ddf:overrides', function(){ var s = document.querySelector('.ddf-chat-strip'); if(s) s.firstChild.textContent = stripText(); });
  function showNotice(err){
    if(document.querySelector('.ddf-link-notice')) return;
    var d = document.createElement('div');
    d.className = 'ddf-link-notice'; d.setAttribute('role', 'status');
    d.innerHTML = '<span></span>' + (isConnectPage() ? '' : '<a href="connect.html#paste">Paste it on Connect</a>') +
      '<button type="button" aria-label="Dismiss">×</button>';
    d.firstChild.textContent = (NOTICE[err] || NOTICE.format) + ' Ask your chat for the ddf-state block' + (isConnectPage() ? ' and paste it below.' : ' instead.');
    d.querySelector('button').addEventListener('click', function(){ d.remove(); });
    topOfMain(d);
  }
  function applySettings(st){
    var label = DDF.link.settingsLabel(st);
    document.querySelectorAll('.ctx-strip > span:first-child').forEach(function(s){ s.textContent = 'My league · From your chat · ' + label; });
    var link = DDF.state.get('link', {});
    if(!document.getElementById('lineup-qb') || link.prefilled === link.at) return;
    function setField(el, value){
      if(!el) return;
      if(el.tagName === 'SELECT'){
        var opt = Array.prototype.find.call(el.options, function(o){ return o.value === String(value) || o.text.trim() === String(value); });
        if(!opt) return;
        el.value = opt.value;
      } else el.value = value;
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new Event('change', {bubbles:true}));
    }
    setField(document.getElementById('scoring'), SCORING_LABEL[st.scoring]);
    setField(document.getElementById('teams'), st.teams);
    SLOT_KEYS.forEach(function(k, i){ setField(document.getElementById('lineup-' + k), st.slots[i]); });
    link.prefilled = link.at; DDF.state.set('link', link);
  }

  function run(){
    var hadToken = DDF.link.hasState();
    return DDF.link.decode().then(function(r){
      var error = r && r.error ? r.error : null;
      if(!error && hadToken && DDF.link.applyRouting()) return {state:r, error:null, source:'link', routed:true};
      var state = error ? null : DDF.link.current();
      var ev = new CustomEvent('ddf:link', {cancelable:true, detail:{state:state, error:error, source:error || r ? 'link' : (state ? 'stored' : 'none')}});
      var handled = !document.dispatchEvent(ev);
      if(error){ if(!handled) showNotice(error); }
      else if(state){ showStrip(); applySettings(state.settings); }
      return ev.detail;
    });
  }
  var started = new Promise(function(res){ if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', res); else res(); });
  DDF.link.ready = started.then(run);
  window.addEventListener('hashchange', function(){ if(DDF.link.hasState()) DDF.link.ready = run(); });
})();

/* Load the shared player table (id -> "Name|POS") so link IDs resolve to names before pages render. */
(function(){
  try {
    if (!window.DDF || !DDF.link || !DDF.link.registerTable) return;
    var x = new XMLHttpRequest();
    x.open('GET', 'players-table-1.json', false);
    x.send();
    if (x.status >= 200 && x.status < 300) DDF.link.registerTable(1, JSON.parse(x.responseText));
  } catch (e) {}
})();

/* ===== ddf-unify: delight utilities (DDF.countUp, growBars, celebrate; copyText button feedback) ===== */
(function(){
  var DDF = window.DDF = window.DDF || {};
  var calm = function(){ return !(window.matchMedia && matchMedia('(prefers-reduced-motion: no-preference)').matches); };
  /* editorial serif for pages that do not import it themselves */
  if(!document.querySelector('link[href*="Newsreader"]') && !/Newsreader/.test(document.documentElement.innerHTML.slice(0,4000))){
    var fl = document.createElement('link'); fl.rel = 'stylesheet';
    fl.href = 'https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,600;6..72,700&display=swap';
    document.head.appendChild(fl);
  }
  function fmt(v, d){ return v.toFixed(d); }
  DDF.countUp = function(el, to, opts){
    opts = opts || {};
    var d = opts.decimals == null ? (String(to).split('.')[1] || '').length : opts.decimals;
    var dur = opts.duration || 900;
    to = Number(to);
    if(!el || isNaN(to)) return;
    if(calm()){ el.textContent = fmt(to, d); return; }
    var t0 = null;
    function step(t){
      if(t0 === null) t0 = t;
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(to * e, d);
      if(p < 1) requestAnimationFrame(step); else el.textContent = fmt(to, d);
    }
    requestAnimationFrame(step);
  };
  function whenVisible(el, fn){
    if(!('IntersectionObserver' in window)){ fn(); return; }
    var io = new IntersectionObserver(function(es){
      es.forEach(function(e){ if(e.isIntersecting){ io.disconnect(); fn(); } });
    }, {threshold:.25});
    io.observe(el);
  }
  DDF.growBars = function(container){
    var root = container || document;
    var bars = root.querySelectorAll('[data-grow]:not(.ddf-ready)');
    Array.prototype.forEach.call(bars, function(b){
      b.classList.add('ddf-ready');
      if(!b.getAttribute('data-grow') || b.getAttribute('data-grow') === 'x') b.style.transformOrigin = 'left center';
      whenVisible(b, function(){ b.classList.add('ddf-grown'); });
    });
    if(calm()) Array.prototype.forEach.call(bars, function(b){ b.classList.add('ddf-grown'); });
  };
  DDF.celebrate = function(el){
    if(!el || calm()) return;
    var cs = getComputedStyle(el); if(cs.position === 'static') el.style.position = 'relative';
    var wrap = document.createElement('span'); wrap.className = 'ddf-confetti'; wrap.setAttribute('aria-hidden','true');
    var colors = ['#176c4d','#e96528','#d7ecd9','#f4c542','#17364c'];
    for(var i = 0; i < 14; i++){
      var a = (i / 14) * Math.PI * 2 + Math.random() * .4, r = 34 + Math.random() * 30, s = document.createElement('i');
      s.style.setProperty('--x', Math.round(Math.cos(a) * r) + 'px'); s.style.setProperty('--y', Math.round(Math.sin(a) * r) + 'px');
      s.style.setProperty('--c', colors[i % colors.length]); wrap.appendChild(s);
    }
    el.appendChild(wrap); setTimeout(function(){ if(wrap.parentNode) wrap.parentNode.removeChild(wrap); }, 900);
  };
  /* copyText: swap the triggering button to a checkmark for 1.8s after success */
  var baseCopy = DDF.copyText;
  if(baseCopy) DDF.copyText = function(text, statusEl){
    var trigger = document.activeElement;
    var res = baseCopy.apply(this, arguments);
    Promise.resolve(res).then(function(ok){
      if(ok !== true) return;
      var b = trigger && trigger.tagName === 'BUTTON' ? trigger : (statusEl && statusEl.parentNode && statusEl.parentNode.querySelector('.copybtn'));
      if(!b || b._ddfCopied) return;
      b._ddfCopied = true; var old = b.textContent;
      b.textContent = '✓ Copied'; b.classList.add('ddf-copied');
      setTimeout(function(){ b.textContent = old; b.classList.remove('ddf-copied'); b._ddfCopied = false; }, 1800);
    });
    return res;
  };
  function auto(){
    DDF.growBars();
    Array.prototype.forEach.call(document.querySelectorAll('[data-countup]'), function(el){
      if(el._ddfCount) return; el._ddfCount = true;
      var to = el.getAttribute('data-countup'), opts = {};
      var dec = el.getAttribute('data-decimals'); if(dec != null) opts.decimals = +dec;
      if(calm()) return;
      el.textContent = fmt(0, opts.decimals == null ? (to.split('.')[1] || '').length : opts.decimals);
      whenVisible(el, function(){ DDF.countUp(el, to, opts); });
    });
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', auto); else auto();
})();

/* Attached sub-nav: move the workspace step row and league strip into one dark tab row under the header. */
(function(){
  function build(){
    var steps = document.querySelector('nav.ws-steps');
    if (!steps || document.querySelector('.subnav') || document.body.classList.contains('home2')) return;
    var strip = document.querySelector('.ctx-strip');
    var bar = document.createElement('div');
    bar.className = 'subnav';
    steps.parentNode.insertBefore(bar, steps);
    bar.appendChild(steps);
    if (strip){
      /* The league summary now lives in the "Your league" chip dropdown; keep the node (page CSS keys off it) but hidden and link-free. */
      strip.hidden = true; strip.setAttribute('aria-hidden','true');
      Array.prototype.forEach.call(strip.querySelectorAll('a'), function(a){ a.remove(); });
      bar.appendChild(strip);
    }
    enhanceTrail(steps);
  }
  /* Step trail scrolls inside its row (never clipped): edge fades only where more content hides, current step centred on load. */
  function enhanceTrail(el){
    function fades(){
      el.classList.toggle('fade-l', el.scrollLeft > 4);
      el.classList.toggle('fade-r', el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
    }
    function centre(){
      var cur = el.querySelector('[aria-current]'); if(!cur) return fades();
      var to = cur.offsetLeft - (el.clientWidth - cur.offsetWidth) / 2;
      el.scrollLeft = Math.max(0, Math.min(to, el.scrollWidth - el.clientWidth)); fades();
    }
    el.addEventListener('scroll', fades, {passive:true});
    window.addEventListener('resize', centre);
    centre();
    if(document.fonts && document.fonts.ready) document.fonts.ready.then(centre);
    window.addEventListener('load', centre);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build); else build();
})();

/* DDF.overrides: user-set player values, kept for this browser session; a pill shows on every page while any are active. */
(function(){
  window.DDF = window.DDF || {};
  var KEY = 'ddf:overrides';
  function read(){ try { return JSON.parse(sessionStorage.getItem(KEY) || '{}') || {}; } catch(e){ return {}; } }
  function write(o){ try { sessionStorage.setItem(KEY, JSON.stringify(o)); } catch(e){} changed(); }
  function changed(){ pill(); try { document.dispatchEvent(new CustomEvent('ddf:overrides', {detail: read()})); } catch(e){} }
  function pill(){
    var n = Object.keys(read()).length, el = document.getElementById('ddf-ovr-pill');
    if (!n){ if (el) el.remove(); return; }
    if (!el){
      el = document.createElement('a'); el.id = 'ddf-ovr-pill'; el.href = 'values.html#overrides';
      el.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:50;background:#fff0e8;color:#a83e12;border:1px solid #a83e12;border-radius:99px;padding:8px 14px;font:600 13px/1.2 Archivo,system-ui,sans-serif;text-decoration:none;box-shadow:0 4px 14px #12202c26;min-height:44px;display:inline-flex;align-items:center';
      document.body.appendChild(el);
    }
    el.textContent = n + (n === 1 ? ' override active' : ' overrides active') + ' · your values, not DDF’s';
    el.setAttribute('aria-label', n + ' value overrides are active. Open Overrides.');
  }
  window.DDF.overrides = {
    get: read,
    value: function(name, fallback){ var o = read(); return Object.prototype.hasOwnProperty.call(o, name) ? o[name] : fallback; },
    set: function(name, v){ var o = read(); o[name] = Number(v); write(o); },
    remove: function(name){ var o = read(); delete o[name]; write(o); },
    clear: function(){ write({}); },
    count: function(){ return Object.keys(read()).length; },
    /* Replace every override at once (one event). DDF.link uses it when a chat link carries overrides. */
    replace: function(o){ var out = {}; Object.keys(o || {}).forEach(function(k){ var v = Number(o[k]); if (isFinite(v)) out[k] = v; }); write(out); }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', pill); else pill();
})();

/* Build a Trade is reachable at any time: the step trail never greys it out (Jeremy, 2026-11-06). */
(function(){
  function fix(){
    document.querySelectorAll('nav.ws-steps span, .subnav span').forEach(function(s){
      if(s.textContent.trim()!=='Build a Trade'||s.closest('a'))return;
      var a=document.createElement('a');a.href='build.html';a.textContent='Build a Trade';
      s.parentNode.replaceChild(a,s);
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fix);else fix();
  document.addEventListener('ddf:link',fix);
})();

/* Values menu behavior: click the caret (or hover/focus on desktop), Esc and outside click close it. */
(function(){
  document.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('.valcaret');
    document.querySelectorAll('.valwrap.open').forEach(function(w){ if(!b || !w.contains(b)){ w.classList.remove('open'); var c=w.querySelector('.valcaret'); c&&c.setAttribute('aria-expanded','false'); } });
    if(b){ var w=b.parentNode, on=!w.classList.contains('open'); w.classList.toggle('open', on); b.setAttribute('aria-expanded', String(on)); }
  });
  document.addEventListener('keydown', function(e){
    if(e.key==='Escape'){ document.querySelectorAll('.valwrap.open').forEach(function(w){ w.classList.remove('open'); var c=w.querySelector('.valcaret'); if(c){c.setAttribute('aria-expanded','false'); c.focus();} }); }
  });
})();

/* ===== League meta (JEG-1564): league name, team, roster input date, freshness, page title =====
   One helper so every surface agrees: the header chip, the banner at the top of each workspace page (Team, Build a Trade,
   Explore, ...) and document.title all read DDF.leagueMeta.
   League read order (same as ddf-league.js): a chat link with teams (sessionStorage ddf:league), the pasted league
   (ddf:pasted), the saved league (localStorage ddf.v2.workspaces). Default name "My league".
   Freshness: calendar days since the roster was entered (local dates), banded by FRESHNESS below. Dismissing a band hides
   that band for the session (ddf:freshdismiss:<band>); a later, stronger band still shows. */
(function(){
  var DDF = window.DDF = window.DDF || {};
  var DEFAULT_NAME = 'My league';
  /* Rosters change daily (waivers, injuries); the NFL week is the natural cycle. 0-1 day: current. 2-3: a quiet note.
     4-6: most of a week of moves, a gentle prompt. 7+: a full week or more, values and lineup effects may be off. */
  var FRESHNESS = {bands: [
    {id: 'fresh', maxDays: 1},
    {id: 'note', maxDays: 3},
    {id: 'prompt', maxDays: 6},
    {id: 'stale', maxDays: Infinity}
  ]};
  var DISMISS = 'ddf:freshdismiss:';
  function json(store, key){ try{ return JSON.parse(store.getItem(key) || 'null'); }catch(e){ return null; } }
  function today(now){ var d = now || new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function ageDays(iso, now){
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || ''); if(!m) return null;
    var n = now || new Date();
    var a = Date.UTC(+m[1], +m[2] - 1, +m[3]), b = Date.UTC(n.getFullYear(), n.getMonth(), n.getDate());
    var d = Math.round((b - a) / 864e5);
    return d < 0 ? 0 : d;
  }
  function ageWords(d){ return d === 0 ? 'today' : d === 1 ? 'yesterday' : d + ' days ago'; }
  function band(d){
    if(d === null || d === undefined) return null;
    for(var i = 0; i < FRESHNESS.bands.length; i++) if(d <= FRESHNESS.bands[i].maxDays) return FRESHNESS.bands[i].id;
    return null;
  }
  function savedLeague(){
    var data = json(localStorage, 'ddf.v2.workspaces');
    if(!data || data.v !== 1 || !Array.isArray(data.workspaces)) return null;
    var ws = data.workspaces.filter(function(w){ return w && w.id === data.activeId; })[0] || data.workspaces[0];
    return ws && Array.isArray(ws.teams) && ws.teams.length ? ws : null;
  }
  function info(){
    var out = null;
    try{
      var link = DDF.link && DDF.link.current && DDF.link.current();
      if(link && Array.isArray(link.teams) && link.teams.length){
        out = {source: 'link', name: link.name, enteredAt: link.enteredAt, team: link.teams[link.me] && link.teams[link.me].name};
      }
      var pasted = !out && DDF.state && DDF.state.get('pasted', null);
      if(pasted && Array.isArray(pasted.teams) && pasted.teams.length){
        out = {source: 'pasted', name: pasted.name, enteredAt: pasted.enteredAt, leagueId: pasted.leagueId, team: pasted.teams[pasted.me] && pasted.teams[pasted.me].name};
      }
      var ws = !out && savedLeague();
      if(ws){
        var mine = ws.teams.filter(function(t){ return t && t.id === ws.myTeamId; })[0];
        out = {source: 'saved', name: ws.name && ws.name !== DEFAULT_NAME ? ws.name : null, enteredAt: ws.enteredAt, leagueId: ws.leagueId, team: mine && mine.name};
      }
    }catch(e){ out = null; }
    if(!out) return null;
    out.named = !!out.name;
    out.name = out.name || DEFAULT_NAME;
    out.days = ageDays(out.enteredAt);
    out.band = band(out.days);
    return out;
  }
  function ageLine(i){ i = i === undefined ? info() : i; return i && i.days !== null ? 'Roster entered ' + ageWords(i.days) : ''; }
  var MESSAGES = {
    note: function(w){ return 'Roster entered ' + w + '.'; },
    prompt: function(w){ return 'Roster entered ' + w + '. Rosters change during the week, so check it is still current.'; },
    stale: function(w){ return 'Roster entered ' + w + '. Rosters have likely changed since then, so trade values and lineup effects on these pages may be off.'; }
  };
  function workspacePage(){ return !!document.querySelector('header nav[aria-label="Main navigation"]') && document.documentElement.getAttribute('data-league') === 'loaded'; }
  function dismissed(b){ try{ return sessionStorage.getItem(DISMISS + b) === '1'; }catch(e){ return false; } }
  function renderBanner(){
    var main = document.querySelector('main'); if(!main) return;
    var el = document.getElementById('ddf-fresh'), i = workspacePage() ? info() : null;
    var b = i && i.band, show = b && b !== 'fresh' && MESSAGES[b] && !dismissed(b);
    if(!show){ if(el) el.remove(); return; }
    if(!el){ el = document.createElement('div'); el.id = 'ddf-fresh'; el.setAttribute('role', 'status'); main.insertBefore(el, main.firstChild); }
    if(el.getAttribute('data-band') === b && el.getAttribute('data-days') === String(i.days)) return;
    el.className = 'ddf-fresh ddf-fresh-' + b; el.setAttribute('data-band', b); el.setAttribute('data-days', String(i.days));
    var action = b === 'note' ? '' : '<a class="ddf-fresh-go" href="connect.html">' + (b === 'stale' ? 'Paste rosters again' : 'Update rosters') + '</a>';
    el.innerHTML = '<p class="ddf-fresh-t"></p>' + action + '<button type="button" class="ddf-fresh-x" aria-label="Dismiss this note">&times;</button>';
    el.querySelector('.ddf-fresh-t').textContent = MESSAGES[b](ageWords(i.days));
    el.querySelector('.ddf-fresh-x').addEventListener('click', function(){ try{ sessionStorage.setItem(DISMISS + b, '1'); }catch(e){} el.remove(); });
  }
  var BASE_TITLE = 'Data Driven Football';
  function cut(s, n){ s = String(s || ''); return s.length > n ? s.slice(0, n - 1).trim() + '…' : s; }
  function title(i){
    i = i === undefined ? info() : i; if(!i) return null;
    var week = null;
    try{ var m = DDF.engine && DDF.engine.meta && DDF.engine.meta(); week = m && m.week; }catch(e){ week = null; }
    return [cut(i.name, 28), i.team ? cut(i.team, 22) : null, Number.isInteger(week) ? 'Week ' + week : null, BASE_TITLE].filter(Boolean).join(' – ');
  }
  function applyTitle(){
    if(!workspacePage() && !/(^|\/)settings\.html$/.test(location.pathname)) return;
    var t = title(); if(t && document.title !== t) document.title = t;
  }
  /* A big input (rosters read, team confirmed, settings confirmed, a batch of overrides) asks for a bookmark once:
     sessionStorage ddf:bmwant {reason, sig}; the Bookmark button shows the prompt when it is visible and sig is new. */
  function want(reason, sig){ try{ sessionStorage.setItem('ddf:bmwant', JSON.stringify({reason: reason, sig: reason + ':' + sig})); }catch(e){} document.dispatchEvent(new CustomEvent('ddf:bmwant')); }
  /* Header chip (JEG-1564): the league's name, shortened to fit. Candidates, longest first: the full name; acronyms,
     numbers and roman numerals kept with other words cut to an initial ("USO Season XVIII" -> "USO S. XVIII"); then
     whole words with an ellipsis. The first that fits wins; never wider than "Your league" on a phone, 200px otherwise,
     and never wider than the header has room for. No name: "Your league". Full name in the tooltip and aria-label. */
  var KEEP_WORD = /^(?:[A-Z0-9&]{2,}|[IVXLC]+|\d.*|.*\d.*)$/;
  function chipCandidates(name){
    var words = String(name).split(/\s+/).filter(Boolean), out = [String(name)];
    if(words.length > 1){
      /* only when a later word is worth keeping (acronym, number, roman numeral): "USO S. XVIII", not "The E. L. N." */
      if(words.slice(1).some(function(w){ return KEEP_WORD.test(w); })){
        var smart = words.map(function(w, i){ return KEEP_WORD.test(w) || i === 0 ? w : (Array.from(w)[0] || '') + '.'; }).join(' ');
        if(smart !== name) out.push(smart);
      }
      for(var k = words.length - 1; k >= 1; k--) out.push(words.slice(0, k).join(' ') + '…');
    }
    var chars = Array.from(String(name));
    for(var n = Math.min(chars.length - 1, 14); n >= 4; n--) out.push(chars.slice(0, n).join('').trim() + '…');
    return out;
  }
  var canvas;
  function textWidth(text, el){
    canvas = canvas || document.createElement('canvas');
    var ctx = canvas.getContext('2d'), cs = getComputedStyle(el);
    ctx.font = cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
    return ctx.measureText(text).width;
  }
  function fitLeagueChip(){
    var chip = document.querySelector('header .ddf-chip'), t = chip && chip.querySelector('.ddf-chip-t');
    if(!t) return;
    var i = info(), full = i && i.named ? i.name : null;
    if(!full){ t.textContent = 'Your league'; chip.removeAttribute('title'); chip.setAttribute('aria-label', 'Your league. Open the league menu'); return; }
    chip.title = full + (i.team ? ' · ' + i.team : '');
    chip.setAttribute('aria-label', 'Your league: ' + full + '. Open the league menu');
    var max = window.innerWidth < 768 ? 120 : 200;
    var list = chipCandidates(full), pick = list[list.length - 1];
    for(var k = 0; k < list.length; k++){ if(textWidth(list[k], t) <= max){ pick = list[k]; break; } }
    t.textContent = pick;
    /* the header itself must not overflow (Menu and Bookmark keep their place) */
    var host = chip.closest('.header-inner') || chip.parentNode.parentNode, at = list.indexOf(pick);
    while(host && host.scrollWidth > host.clientWidth + 1 && at < list.length - 1){ at++; t.textContent = list[at]; }
  }
  window.addEventListener('resize', function(){ clearTimeout(fitLeagueChip._t); fitLeagueChip._t = setTimeout(fitLeagueChip, 100); });
  try{ if(document.fonts && document.fonts.ready) document.fonts.ready.then(function(){ fitLeagueChip(); }); }catch(e){}
  function refresh(){ renderBanner(); applyTitle(); fitLeagueChip(); }
  var t0;
  function soon(){ clearTimeout(t0); t0 = setTimeout(refresh, 60); }
  ['ddf:link', 'ddf:pasted', 'ddf:overrides', 'pageshow', 'focus'].forEach(function(ev){ (ev === 'pageshow' || ev === 'focus' ? window : document).addEventListener(ev, soon); });
  window.addEventListener('storage', soon);
  function init(){
    refresh();
    if(DDF.engine && DDF.engine.ready && DDF.engine.ready.then) DDF.engine.ready.then(soon, function(){});
    if(DDF.league && DDF.league.ready && DDF.league.ready.then) DDF.league.ready.then(soon, function(){});
    if(DDF.link && DDF.link.ready && DDF.link.ready.then) DDF.link.ready.then(soon, function(){});
    if(window.MutationObserver) new MutationObserver(soon).observe(document.documentElement, {attributes: true, attributeFilter: ['data-league']});
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  DDF.leagueMeta = {FRESHNESS: FRESHNESS, DEFAULT_NAME: DEFAULT_NAME, info: info, ageDays: ageDays, ageWords: ageWords, band: band,
    ageLine: ageLine, message: function(b, d){ return MESSAGES[b] ? MESSAGES[b](ageWords(d)) : ''; }, title: title, today: today,
    want: want, refresh: refresh, savedLeague: savedLeague, chipCandidates: chipCandidates};
  DDF.fitLeagueChip = fitLeagueChip;
})();

/* ===== Bookmark button (Jeremy, 2026-11-06) =====
   Header right slot, next to the "Your league" chip. Shown once a league is loaded and its settings are confirmed
   (workspace pages: league loaded; settings.html: after Looks right, continue / Settings saved). Click = fresh #s= token for
   this page in the address bar (history.replaceState), link copied, short how-to. We never claim a bookmark was added.
   Re-bookmark prompt: sessionStorage ddf:bookmarked = token at the last click; a different token now = "Bookmark again" + dot. */
(function(){
  var DDF = window.DDF = window.DDF || {};
  var BM_KEY = 'ddf:bookmarked', HINT_KEY = 'ddf:bmhint', OK_KEY = 'ddf:settingsok';
  var ICON = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4.5L5 21V4a1 1 0 0 1 1-1z"/></svg>';
  var wrap, btn, pop, popText, live, hint, keep, timer, hintTimer, checkSeq = 0, changed = false, visible = false;
  var WANT_KEY = 'ddf:bmwant', DONE_KEY = 'ddf:bmdone';
  var WANT_TEXT = {
    rosters: 'Rosters added. Bookmark this page to come back to your league.',
    team: 'Team confirmed. Bookmark this page to come back to your league.',
    settings: 'Settings confirmed. Bookmark this page to keep your league and settings.',
    overrides: 'Your values changed. Bookmark again to keep them.'
  };
  function wantNow(){ try{ var w = JSON.parse(sessionStorage.getItem(WANT_KEY) || 'null'); return w && w.sig && w.sig !== sget(DONE_KEY) ? w : null; }catch(e){ return null; } }
  function markWantDone(){ var w = wantNow(); if(w) sset(DONE_KEY, w.sig); }
  function keyHint(p){
    return p === 'mac' ? 'Press ⌘D.' : p === 'ios' ? 'Tap Share, then Add Bookmark.' : p === 'android' ? 'Open the browser menu, then tap the star.' : 'Press Ctrl+D.';
  }

  function sget(k){ try{ return sessionStorage.getItem(k); }catch(e){ return null; } }
  function sset(k, v){ try{ sessionStorage.setItem(k, v); }catch(e){} }
  function isEntry(){ return !!document.querySelector('header.entry-head'); }
  function pageName(){ return (location.pathname.split('/').pop() || 'index.html'); }
  function tokenOfUrl(u){ var m = /#s=(.*)$/.exec(u); return m ? m[1] : null; }
  function platform(){
    var ua = navigator.userAgent || '', touch = navigator.maxTouchPoints > 1;
    if(/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && touch)) return 'ios';
    if(/Android/.test(ua)) return 'android';
    if(/Windows|Linux|CrOS|X11/.test(ua)) return 'other';
    if(/Mac/.test(ua)) return 'mac';
    return 'other';
  }
  function howTo(p, copied){
    var start = copied ? 'Link copied. ' : 'Your link is in the address bar. ';
    var step = p === 'mac' ? 'Now press ⌘D to bookmark this page. '
      : p === 'ios' ? 'Now tap Share, then Add Bookmark. '
      : p === 'android' ? 'Now open the browser menu, then tap the star or Add to bookmarks. '
      : 'Now press Ctrl+D to bookmark this page. ';
    return start + step + 'Your league, settings and values are saved inside the link. Bookmark again after you make changes.';
  }
  function slot(){
    if(isEntry()) return document.querySelector('header.entry-head .entry-head-inner');
    var nav = document.querySelector('header nav[aria-label="Main navigation"]');
    return nav && nav.parentNode;
  }
  /* The league's settings for the link: the link's own, else the reader's saved engine settings (a pasted or saved league). */
  function cleanLeagueName(n){
    if(typeof n !== 'string') return null;
    var c = Array.from(n.replace(/[\u0000-\u001f]/g, ' ').replace(/\s+/g, ' ').trim());
    return c.length ? c.slice(0, 40).join('').trim() : null;
  }
  function linkSettings(){
    var st = DDF.link && DDF.link.settings && DDF.link.settings();
    if(st) return st;
    try{
      var e = DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.engine.settings(), r = e && e.roster;
      if(!r) return null;
      return {scoring: e.scoring, teams: e.teams, superflex: (r.SUPERFLEX || 0) > 0, slots: [r.QB, r.RB, r.WR, r.TE, r.FLEX, r.BENCH].map(function(n){ return Number(n) || 0; })};
    }catch(err){ return null; }
  }
  /* JEG-1564: what the Bookmark link carries. The chat league when it has teams; otherwise the pasted or saved league's
     teams, your team, name and roster date go into the link with the settings, so a bookmark reopens the whole league. */
  function linkState(){
    var cur = DDF.link && DDF.link.current && DDF.link.current(), settings = linkSettings();
    if(!settings) return null;
    var st = cur ? JSON.parse(JSON.stringify(cur)) : {v: 1};
    st.settings = Object.assign({}, cur && cur.settings, settings);
    if(!st.view) st.view = 'team';
    if(Array.isArray(st.teams) && st.teams.length) return st;
    delete st.name; delete st.enteredAt; delete st.me;   /* a settings-only chat state lends no name, date or team */
    var table = (DDF.link.table && DDF.link.table(1)) || [], idByKey = {};
    table.forEach(function(row, i){ var k = String(row).split('|')[3]; if(k && idByKey[k] === undefined) idByKey[k] = i; });
    var entry = function(p){ return Number.isInteger(p.id) ? p.id : (p.key && idByKey[String(p.key)] !== undefined ? idByKey[String(p.key)] : p.name); };
    var pasted = DDF.state.get('pasted', null), ws = DDF.leagueMeta && DDF.leagueMeta.savedLeague();
    var teams = null, me = null, name = null, at = null;
    if(pasted && Array.isArray(pasted.teams) && pasted.teams.length){
      teams = pasted.teams.map(function(t){ return {name: t.name, players: (Array.isArray(t.players) ? t.players : []).map(entry).filter(function(x){ return x !== undefined && x !== null && x !== ''; })}; });
      me = pasted.me; name = pasted.name; at = pasted.enteredAt;
    } else if(ws){
      teams = ws.teams.map(function(t){ return {name: t.name, players: (t.entries || []).map(function(e){ return entry({key: e.key, name: e.name}); }).filter(function(x){ return x !== undefined && x !== null && x !== ''; })}; });
      ws.teams.forEach(function(t, i){ if(t.id === ws.myTeamId) me = i; });
      name = ws.name && ws.name !== 'My league' ? ws.name : null; at = ws.enteredAt;
    }
    if(teams){
      st.teams = teams.map(function(t){ return {name: String(t.name || '').slice(0, 60), players: t.players}; });
      if(Number.isInteger(me) && st.teams[me]) st.me = me;
      if(st.teams.some(function(t){ return t.players.some(Number.isInteger); })) st.table = 1;
      var nm = cleanLeagueName(name), dt = /^\d{4}-\d{2}-\d{2}$/.test(at || '') ? at : null;
      if(nm) st.name = nm;
      if(dt) st.enteredAt = dt;
    }
    return st;
  }
  function shouldShow(){
    if(!linkSettings()) return false;
    if(isEntry()) return /(^|\/)settings\.html$/.test(location.pathname) && sget(OK_KEY) === '1';
    return !!document.querySelector('header nav[aria-label="Main navigation"]') && document.documentElement.getAttribute('data-league') === 'loaded';
  }
  function build(){
    if(wrap) return;
    wrap = document.createElement('span'); wrap.className = 'ddf-bm-wrap'; wrap.hidden = true;
    btn = document.createElement('button'); btn.type = 'button'; btn.className = 'ddf-bm';
    btn.innerHTML = ICON + '<span class="ddf-bm-t">Bookmark</span><i class="ddf-bm-dot" aria-hidden="true" hidden></i>';
    btn.setAttribute('aria-label', 'Bookmark'); btn.title = 'Bookmark this page to come back to your league';
    btn.addEventListener('click', onClick);
    live = document.createElement('span'); live.className = 'ddf-bm-live'; live.setAttribute('role', 'status'); live.setAttribute('aria-live', 'polite');
    pop = document.createElement('div'); pop.className = 'ddf-bm-pop'; pop.setAttribute('role', 'status'); pop.hidden = true;
    popText = document.createElement('p'); popText.className = 'ddf-bm-poptext';
    var x = document.createElement('button'); x.type = 'button'; x.className = 'ddf-bm-x'; x.setAttribute('aria-label', 'Close'); x.innerHTML = '&times;';
    x.addEventListener('click', function(){ closePop(true); });
    pop.appendChild(popText); pop.appendChild(x);
    hint = document.createElement('div'); hint.className = 'ddf-bm-hint'; hint.hidden = true; hint.setAttribute('role', 'status');
    var ht = document.createElement('span'); ht.className = 'ddf-bm-ht'; ht.textContent = 'Bookmark this page to come back to your league';
    var hgo = document.createElement('button'); hgo.type = 'button'; hgo.className = 'ddf-bm-go'; hgo.textContent = 'Bookmark'; hgo.hidden = true;
    hgo.addEventListener('click', function(){ closeHint(); onClick(); });
    var hx = document.createElement('button'); hx.type = 'button'; hx.className = 'ddf-bm-x'; hx.setAttribute('aria-label', 'Dismiss this tip'); hx.innerHTML = '&times;';
    hx.addEventListener('click', function(){ sset(HINT_KEY, 'done'); markWantDone(); closeHint(); });
    hint.appendChild(ht); hint.appendChild(hgo); hint.appendChild(hx);
    /* one bookmark on this device: the page address without the link, which opens the latest saved league here */
    keep = document.createElement('button'); keep.type = 'button'; keep.className = 'ddf-bm-keep'; keep.hidden = true;
    keep.textContent = 'Keep one bookmark on this device instead';
    keep.addEventListener('click', function(){
      try{ history.replaceState(history.state, '', location.pathname + location.search); }catch(e){}
      keep.hidden = true;
      popText.textContent = 'The address bar now shows this page without the link. Bookmark it once: on this device it always opens your latest saved league, so there is no old bookmark to replace. ' + keyHint(platform());
    });
    var popBody = document.createElement('div'); popBody.className = 'ddf-bm-popbody'; popBody.style.flex = '1';
    pop.insertBefore(popBody, popText); popBody.appendChild(popText); popBody.appendChild(keep);
    wrap.appendChild(btn); wrap.appendChild(live); wrap.appendChild(pop); wrap.appendChild(hint);
  }
  function place(){
    var host = slot(); if(!host) return false;
    build();
    var chip = host.querySelector(':scope > .ddf-chipwrap');
    if(wrap.parentNode !== host || (chip && wrap.nextSibling !== chip)){
      if(chip) host.insertBefore(wrap, chip); else host.appendChild(wrap);
    }
    return true;
  }
  function anchor(el){
    var r = btn.getBoundingClientRect(), small = window.innerWidth < 640;
    el.style.top = Math.round(r.bottom + 8) + 'px';
    if(small){ el.style.left = '16px'; el.style.right = '16px'; el.style.width = 'auto'; }
    else { el.style.left = 'auto'; el.style.width = ''; el.style.right = Math.max(16, Math.round(window.innerWidth - r.right)) + 'px'; }
  }
  function closeHint(){ if(hint) hint.hidden = true; clearTimeout(hintTimer); }
  function closePop(focus){
    if(!pop || pop.hidden) return;
    pop.hidden = true; clearTimeout(timer);
    if(focus && btn) btn.focus();
  }
  function showPop(text){
    closeHint(); popText.textContent = text; anchor(pop); pop.hidden = false;
    clearTimeout(timer); timer = setTimeout(function(){ closePop(false); }, 10000);
  }
  /* After a big input: one prompt per change (sig), shown when the button is visible; never blocks, closes itself. */
  function showWant(){
    var w = wantNow();
    if(!w || !hint || !visible || !pop.hidden) return false;
    if(w.reason === 'settings' && /(^|\/)settings\.html$/.test(location.pathname)) return false;   /* this page moves on; the next one asks */
    sset(DONE_KEY, w.sig);
    hint.querySelector('.ddf-bm-ht').textContent = WANT_TEXT[w.reason] || WANT_TEXT.rosters;
    hint.querySelector('.ddf-bm-go').hidden = false;
    hint.setAttribute('data-reason', w.reason);
    anchor(hint); hint.hidden = false;
    clearTimeout(hintTimer); hintTimer = setTimeout(closeHint, 20000);
    return true;
  }
  function showHint(){
    if(!hint || !visible || !hint.hidden || sget(HINT_KEY) || sget(BM_KEY) || !pop.hidden) return;
    hint.querySelector('.ddf-bm-ht').textContent = 'Bookmark this page to come back to your league';
    hint.querySelector('.ddf-bm-go').hidden = true; hint.removeAttribute('data-reason');
    sset(HINT_KEY, 'seen'); anchor(hint); hint.hidden = false;
    clearTimeout(hintTimer); hintTimer = setTimeout(closeHint, 15000);
  }
  function render(){
    var want = shouldShow();
    document.documentElement.setAttribute('data-bm', want ? 'on' : 'off');
    if(!want){ if(wrap) wrap.hidden = true; visible = false; return; }
    if(!place()) return;
    wrap.hidden = false;
    var was = visible; visible = true;
    paint();
    if(!was) { check(); if(!showWant() && !(sget(OK_KEY) === '1' && /(^|\/)settings\.html$/.test(location.pathname) && wantNow())) showHint(); }
  }
  function paint(){
    var label = changed ? 'Bookmark again' : 'Bookmark';
    btn.querySelector('.ddf-bm-t').textContent = label;
    btn.setAttribute('aria-label', label);
    btn.title = changed ? 'Your league changed since your last bookmark. Bookmark again.' : 'Bookmark this page to come back to your league';
    btn.querySelector('.ddf-bm-dot').hidden = !changed;
    btn.classList.toggle('is-changed', changed);
  }
  function freshUrl(){
    var st = linkState();
    if(!st) return Promise.reject(new Error('settings'));
    return DDF.link.encode(st, {page: pageName() + location.search});
  }
  function onClick(){
    if(!linkState()) return;
    markWantDone();
    freshUrl().then(function(url){
      try{ history.replaceState(history.state, '', url); }catch(e){}
      sset(BM_KEY, tokenOfUrl(url) || '');
      changed = false; paint(); closeHint();
      btn._ddfCopied = true;
      return DDF.copyText(url).then(function(ok){ showPop(howTo(platform(), ok === true)); }, function(){ showPop(howTo(platform(), false)); })
        .then(function(){
          var M = DDF.leagueMeta, i = M && M.info();
          var ws = M && M.savedLeague();
          keep.hidden = !(ws && i && (i.source === 'saved' || (i.source === 'pasted' && sget('ddf:bridgedWs') === JSON.stringify(ws.id))));
          setTimeout(function(){ btn._ddfCopied = false; }, 2000);
        });
    }).catch(function(){});
  }
  /* Compare the current state's token with the one at the last bookmark. Cheap: debounced, skipped until a bookmark exists. */
  function check(){
    if(!visible) return;
    var prev = sget(BM_KEY);
    if(prev === null) { if(changed){ changed = false; paint(); } return; }
    var seq = ++checkSeq;
    freshUrl().then(function(url){
      if(seq !== checkSeq) return;
      var now = changed = tokenOfUrl(url) !== prev;
      paint();
      if(now && !btn._announced){ btn._announced = true; live.textContent = ''; setTimeout(function(){ live.textContent = 'Your league changed since your last bookmark.'; }, 50); }
      if(!now){ btn._announced = false; live.textContent = ''; }
    }).catch(function(){});
  }
  var debounce;
  function soon(){ clearTimeout(debounce); debounce = setTimeout(function(){ render(); check(); }, 150); }

  /* settings.html: Looks right / Settings saved = confirmed. Record the form's settings in the link state, then show the button. */
  var SC = {'PPR':'ppr','Half PPR':'half_ppr','Standard':'standard'};
  function confirmSettings(){
    var g = function(id){ var e = document.getElementById(id); return e ? e.value : null; };
    if(!g('scoring')) return;
    var form = {scoring:SC[g('scoring')] || g('scoring'), teams:Number(g('teams')), superflex:g('superflex') === 'true',
      slots:['qb','rb','wr','te','flex','bench'].map(function(k){ return Number(g('lineup-' + k)); })};
    try{
      var cur = DDF.link.current(), info = DDF.state.get('link', null);
      /* A hand-entered league stays 'manual' when re-confirmed (DDF.link.update would mark it as a chat league). */
      if(cur && !(info && info.source === 'manual')) DDF.link.update({settings:Object.assign({}, cur.settings, form)});
      else { DDF.state.set('league', Object.assign({v:1}, cur || {}, {settings:Object.assign({}, cur && cur.settings, form)})); DDF.state.set('link', {source:'manual', at:Date.now()}); }
    }catch(e){}
    sset(OK_KEY, '1');
    if(DDF.leagueMeta) DDF.leagueMeta.want('settings', JSON.stringify(form));
    soon();
  }
  function init(){
    if(/(^|\/)settings\.html$/.test(location.pathname)){
      var f = document.getElementById('editor'), fin = document.getElementById('finish-setup');
      if(f) f.addEventListener('submit', confirmSettings);
      if(fin) fin.addEventListener('click', confirmSettings, true);
    }
    if(sget('ddf:bmovbase') === null && DDF.overrides) sset('ddf:bmovbase', String(DDF.overrides.count()));
    render();
    if(DDF.link && DDF.link.ready) DDF.link.ready.then(function(){ setTimeout(render, 0); });
  }
  document.addEventListener('ddf:link', function(){ setTimeout(function(){ render(); check(); }, 0); });
  ['ddf:overrides','ddf:posweights','ddf:trade'].forEach(function(n){ document.addEventListener(n, soon); });
  /* a page that navigates right after the input (settings: Looks right, continue) never shows it; the next page does */
  document.addEventListener('ddf:bmwant', function(){ setTimeout(showWant, 1200); });
  /* A batch of override edits (3 or more since the last prompt) asks for a bookmark once. */
  var OV_BASE = 'ddf:bmovbase', OV_BATCH = 3;
  document.addEventListener('ddf:overrides', function(){
    var n = DDF.overrides ? DDF.overrides.count() : 0, base = Number(sget(OV_BASE));
    if(sget(OV_BASE) === null || DDF.overrides._fromLink){ sset(OV_BASE, String(n)); return; }
    if(Math.abs(n - base) >= OV_BATCH){ sset(OV_BASE, String(n)); if(DDF.leagueMeta) DDF.leagueMeta.want('overrides', n + '@' + Date.now()); }
  });
  window.addEventListener('pageshow', soon); window.addEventListener('focus', soon);
  window.addEventListener('hashchange', soon);
  window.addEventListener('resize', function(){ if(pop && !pop.hidden) anchor(pop); if(hint && !hint.hidden) anchor(hint); });
  document.addEventListener('keydown', function(e){ if(e.key === 'Escape'){ if(pop && !pop.hidden) closePop(true); else if(hint && !hint.hidden){ closeHint(); } } });
  /* Pages write state straight to the session stores; watch those writes instead of polling. */
  if(DDF.state && DDF.state.set && !DDF.state._bmWrapped){
    var set = DDF.state.set, rm = DDF.state.remove, WATCH = {league:1, basis:1, posweights:1, overrides:1, trade:1, pasted:1};
    DDF.state.set = function(k){ var r = set.apply(this, arguments); if(WATCH[k] && visible) soon(); return r; };
    DDF.state.remove = function(k){ var r = rm.apply(this, arguments); if(WATCH[k] && visible) soon(); return r; };
    DDF.state._bmWrapped = true;
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  DDF.bookmark = {refresh:render, check:check};
})();
