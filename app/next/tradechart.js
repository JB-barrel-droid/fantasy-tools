/* Trade chart component: verdict card + "Difference by source" table with horizontal waterfalls.
   window.DDF_TC.render(containerEl, {sources:[{name, give:[{n,v}], receive:[{n,v}]}], mainSourceIndex, note, emptyText, verdict?:{lead, tail, tone:'pos'|'neg'|'even'}})
   emptyText: shown when no source has a value for every player (default asks for players on both sides).
   Numbers are shown as given (original source values, never rescaled). Every waterfall shares one scale. */
(function(){
  var EPS = 0.005;
  var esc = function(s){ return String(s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var sum = function(list){ return list.reduce(function(t, p){ return t + p.v; }, 0); };
  var num = function(v){ return Math.abs(v).toFixed(2); };
  var signed = function(v){ return Math.abs(v) < EPS ? '0.00' : (v > 0 ? '+' : '−') + num(v); };
  var sign = function(v){ return Math.abs(v) < EPS ? 0 : v > 0 ? 1 : -1; };
  var lastName = function(n){ var parts = String(n).trim().split(/\s+/); return parts.length > 1 ? parts.slice(1).join(' ') : parts[0]; };
  var motionOK = function(){ return !!(window.matchMedia && matchMedia('(prefers-reduced-motion: no-preference)').matches); };

  function summarize(src){
    var give = sum(src.give), receive = sum(src.receive);
    return {name: src.name, giveList: src.give, receiveList: src.receive, give: give, receive: receive, net: receive - give};
  }

  /* Waterfall steps: from 0 down by each give, up by each receive, then a solid result bar from 0. */
  function steps(row, perPlayer){
    var out = [], at = 0;
    var giveItems = perPlayer || row.giveList.length === 1 ? row.giveList.map(function(p){ return {label: lastName(p.n), v: p.v}; }) : [{label: 'Give', v: row.give}];
    var recvItems = perPlayer || row.receiveList.length === 1 ? row.receiveList.map(function(p){ return {label: lastName(p.n), v: p.v}; }) : [{label: 'Receive', v: row.receive}];
    giveItems.forEach(function(p){ out.push({kind: 'give', from: at, to: at - p.v, text: p.label + ' −' + num(p.v)}); at -= p.v; });
    recvItems.forEach(function(p){ out.push({kind: 'receive', from: at, to: at + p.v, text: p.label + ' +' + num(p.v)}); at += p.v; });
    out.push({kind: 'result', from: 0, to: row.net, text: (sign(row.net) > 0 ? '▲ ' : sign(row.net) < 0 ? '▼ ' : 'Even ') + signed(row.net)});
    return out;
  }

  function scaleFor(rows){
    var lo = 0, hi = 0;
    rows.forEach(function(r){
      steps(r, true).forEach(function(s){ lo = Math.min(lo, s.from, s.to); hi = Math.max(hi, s.from, s.to); });
    });
    if(hi - lo < EPS){ lo = -1; hi = 1; }
    return {lo: lo, hi: hi, pct: function(x){ return (x - lo) / (hi - lo) * 100; }};
  }

  function waterfall(row, scale, perPlayer, label){
    var zero = scale.pct(0);
    var lines = steps(row, perPlayer).map(function(s){
      var a = scale.pct(Math.min(s.from, s.to)), b = scale.pct(Math.max(s.from, s.to)), w = b - a;
      var cls = s.kind === 'result' ? 'tc-result ' + (sign(row.net) > 0 ? 'is-pos' : sign(row.net) < 0 ? 'is-neg' : 'is-even') : 'tc-' + s.kind;
      /* growth origin: give grows leftward from its start, receive rightward, result away from zero */
      var origin = s.kind === 'give' ? 'right' : s.kind === 'receive' ? 'left' : (s.to < 0 ? 'right' : 'left');
      /* label inside a wide bar; otherwise beside it (result labels always sit beside the bar) */
      var place, lab;
      var roomAfter = 100 - b, roomBefore = a;
      if(s.kind !== 'result' && w >= 22) place = 'in';
      else if(s.kind === 'result'){ var pref = s.to < 0 ? ['before', 'after'] : ['after', 'before'], room = {before: roomBefore, after: roomAfter}; place = room[pref[0]] >= 16 ? pref[0] : room[pref[1]] >= 16 ? pref[1] : 'in'; }
      else place = roomAfter >= roomBefore ? 'after' : 'before';
      if(place === 'in') lab = '<span class="tc-lab tc-lab-in' + (s.kind === 'result' ? ' tc-lab-onbar' : '') + '" style="left:' + a.toFixed(3) + '%">' + esc(s.text) + '</span>';
      else if(place === 'after') lab = '<span class="tc-lab" style="left:calc(' + b.toFixed(3) + '% + 5px)">' + esc(s.text) + '</span>';
      else lab = '<span class="tc-lab tc-lab-before" style="right:calc(' + (100 - a).toFixed(3) + '% + 5px)">' + esc(s.text) + '</span>';
      return '<div class="tc-line ' + (s.kind === 'result' ? 'tc-line-result' + (place === 'in' ? ' tc-line-onbar' : '') : '') + '"><span class="tc-bar ' + cls + '" data-tc-grow style="left:' + a.toFixed(3) + '%;width:' + Math.max(w, 0).toFixed(3) + '%;transform-origin:' + origin + ' center"></span>' + lab + '</div>';
    }).join('');
    return '<div class="tc-wf" aria-hidden="true"><span class="tc-zero" style="left:' + zero.toFixed(3) + '%"></span>' + lines + '</div><span class="tc-sr">' + esc(label) + '</span>';
  }

  function plain(net){ var s = sign(net); return s > 0 ? 'you get more by this source' : s < 0 ? 'you give more by this source' : 'even by this source'; }
  function ariaFor(r){ return r.name + ': give ' + num(r.give) + ', receive ' + num(r.receive) + ', result ' + signed(r.net) + ', ' + plain(r.net) + '.'; }

  function verdictText(main){
    var s = sign(main.net), big = Math.max(main.give, main.receive) || 1, slight = Math.abs(main.net) / big <= 0.10;
    if(s === 0) return {lead: 'Even by ' + main.name + ':', tone: 'even'};
    if(slight) return {lead: s > 0 ? 'Slight edge to you:' : 'Slight edge to them:', tone: s > 0 ? 'pos' : 'neg'};
    return {lead: 'By ' + main.name + ', you ' + (s > 0 ? 'get more than you give:' : 'give more than you get:'), tone: s > 0 ? 'pos' : 'neg'};
  }

  function agreement(rows){
    var up = 0, down = 0, even = 0;
    rows.forEach(function(r){ var s = sign(r.net); if(s > 0) up++; else if(s < 0) down++; else even++; });
    if(rows.length === 1) return 'One source shown.';
    if(up === rows.length) return 'Every source agrees: you get more.';
    if(down === rows.length) return 'Every source agrees: you give more.';
    if(even === rows.length) return 'Every source calls it even.';
    var parts = [];
    if(up) parts.push(up + (up === 1 ? ' says' : ' say') + ' you get more');
    if(down) parts.push(down + (down === 1 ? ' says' : ' say') + ' you give more');
    if(even) parts.push(even + (even === 1 ? ' calls' : ' call') + ' it even');
    return 'Sources split: ' + parts.join(', ') + '.';
  }

  function countUp(el, to){
    var start = null, dur = 700;
    function frame(t){
      if(start === null) start = t;
      var p = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = p < 1 ? signed(to * e) : signed(to);
      if(p < 1) requestAnimationFrame(frame);
    }
    el.textContent = signed(0);
    requestAnimationFrame(frame);
  }

  function animate(root){
    if(!motionOK()) return;
    var bars = root.querySelectorAll('[data-tc-grow]');
    Array.prototype.forEach.call(bars, function(b, i){
      b.style.transform = 'scaleX(0)';
      b.style.transition = 'transform 500ms cubic-bezier(.2,.8,.2,1) ' + (Math.min(i, 12) * 80) + 'ms';
    });
    void root.offsetWidth;
    requestAnimationFrame(function(){ Array.prototype.forEach.call(bars, function(b){ b.style.transform = 'scaleX(1)'; }); });
    var n = root.querySelector('[data-tc-count]');
    if(n) countUp(n, Number(n.getAttribute('data-tc-count')));
  }

  var uid = 0;
  function render(container, data){
    if(!container) return;
    var key = JSON.stringify(data || null);
    if(container._tcKey === key) return;
    container._tcKey = key;
    var sources = (data && data.sources || []).filter(function(s){ return s && s.give && s.give.length && s.receive && s.receive.length; });
    if(!sources.length){ container.innerHTML = '<p class="tc-empty">' + esc(data && data.emptyText || 'Add players on both sides to see the trade charts.') + '</p>'; return; }
    var rows = sources.map(summarize);
    var mainIdx = Math.min(Math.max(data.mainSourceIndex | 0, 0), rows.length - 1), main = rows[mainIdx];
    /* data.verdict {lead, tail, tone} optionally replaces the default verdict wording (e.g. a waiver pickup) */
    var custom = data.verdict && typeof data.verdict === 'object' ? data.verdict : null;
    var scale = scaleFor(rows), v = custom ? {lead: custom.lead || '', tail: custom.tail || '', tone: custom.tone || 'even'} : verdictText(main), id = 'tc' + (++uid);
    var multi = rows.some(function(r){ return r.giveList.length > 1 || r.receiveList.length > 1; });

    var verdict = '<section class="tc-verdict tc-' + v.tone + '" aria-labelledby="' + id + '-v">' +
      '<p class="tc-eyebrow">Verdict · by ' + esc(main.name) + '</p>' +
      '<h3 class="tc-headline" id="' + id + '-v">' + (v.lead ? esc(v.lead) + ' ' : '') + '<span class="tc-big" data-tc-count="' + main.net.toFixed(4) + '">' + signed(main.net) + '</span>' + (v.tail ? ' ' + esc(v.tail) : '') + '</h3>' +
      '<p class="tc-agree">' + esc(agreement(rows)) + '</p>' +
      '<div class="tc-grid tc-verdict-chart"><p class="tc-caption">From 0: down by each player you give, then up by each you receive, then the result — same scale as the table below.</p>' +
      '<div class="tc-cell-wf">' + waterfall(main, scale, true, ariaFor(main)) + '</div></div></section>';

    var head = '<div class="tc-grid tc-head" role="row"><span role="columnheader">Source</span><span role="columnheader" class="tc-num">Give</span><span role="columnheader" class="tc-num">Receive</span><span role="columnheader">From 0: give ← · receive → · result</span><span role="columnheader" class="tc-num">Receive − give</span></div>';
    var body = rows.map(function(r, i){
      var s = sign(r.net), pid = id + '-p' + i, hasPlayers = r.giveList.length > 1 || r.receiveList.length > 1;
      var players = hasPlayers ? '<button type="button" class="tc-show" aria-expanded="false" aria-controls="' + pid + '">Show players</button>' : '';
      var row = '<div class="tc-grid tc-row' + (i === mainIdx ? ' is-main' : '') + '" role="row">' +
        '<span class="tc-src" role="rowheader"><strong>' + esc(r.name) + '</strong>' + (i === mainIdx ? '<small class="tc-tag">Decides the verdict</small>' : '') + players + '</span>' +
        '<span class="tc-num tc-c-give" role="cell" data-label="Give">' + num(r.give) + '</span>' +
        '<span class="tc-num tc-c-recv" role="cell" data-label="Receive">' + num(r.receive) + '</span>' +
        '<span class="tc-cell-wf" role="cell">' + waterfall(r, scale, false, ariaFor(r)) + '</span>' +
        '<span class="tc-num tc-net" role="cell"><b class="' + (s > 0 ? 'is-pos' : s < 0 ? 'is-neg' : 'is-even') + '">' + signed(r.net) + '</b><small>' + plain(r.net) + '</small></span></div>';
      if(hasPlayers){
        var list = r.giveList.map(function(p){ return '<li>Give ' + esc(p.n) + ' <span>' + num(p.v) + '</span></li>'; }).concat(r.receiveList.map(function(p){ return '<li>Receive ' + esc(p.n) + ' <span>' + num(p.v) + '</span></li>'; })).join('');
        row += '<div class="tc-grid tc-players" role="row" id="' + pid + '" hidden><ul class="tc-plist" role="cell">' + list + '</ul><span class="tc-cell-wf" role="cell">' + waterfall(r, scale, true, r.name + ' by player: ' + ariaFor(r)) + '</span></div>';
      }
      return row;
    }).join('');

    var lo = scale.lo, hi = scale.hi;
    var table = '<section class="tc-table" aria-labelledby="' + id + '-t"><h3 id="' + id + '-t">Difference by source</h3>' +
      '<p class="tc-sub">Receive − give, by source. DDF Value is the average of the four charts’ adjusted values (fitted to your league settings), so it is not the average of the chart rows here: each chart row, and Analyst charts, uses indexed values, the chart’s published numbers on DDF Value’s scale, not adjusted to your league.' + (rows.some(function(r){ return /projections/.test(r.name); }) ? ' Projection rows are adjusted values.' : '') + ' Every row shares one scale, ' + signed(lo).replace('+', '') + ' to ' + signed(hi).replace('+', '') + '; the line marks 0.' + (multi ? ' Open “Show players” to see each player.' : '') + '</p>' +
      '<div class="tc-rows" role="table" aria-label="Difference by source">' + head + body + '</div>' +
      (data.note ? '<p class="tc-note">' + esc(data.note) + '</p>' : '') + '</section>';

    container.classList.add('tc-root');
    /* one persistent polite live region so screen readers hear each new verdict (container content is replaced on every render) */
    if(!container._tcLive){
      var live = document.createElement('div'); live.className = 'tc-sr'; live.setAttribute('role', 'status'); live.setAttribute('aria-live', 'polite');
      container.parentNode.insertBefore(live, container); container._tcLive = live;
    }
    container._tcLive.textContent = '';
    var liveText = (v.lead ? v.lead + ' ' : '') + signed(main.net) + (v.tail ? ' ' + v.tail : '') + '. ' + agreement(rows);
    setTimeout(function(){ container._tcLive.textContent = liveText; }, 60);
    container.innerHTML = verdict + table;
    container.querySelectorAll('.tc-show').forEach(function(b){
      b.addEventListener('click', function(){
        var panel = document.getElementById(b.getAttribute('aria-controls')), open = b.getAttribute('aria-expanded') !== 'true';
        b.setAttribute('aria-expanded', String(open)); b.textContent = open ? 'Hide players' : 'Show players'; panel.hidden = !open;
        if(open) animate(panel);
      });
    });
    animate(container);
  }

  window.DDF_TC = {render: render};
})();
