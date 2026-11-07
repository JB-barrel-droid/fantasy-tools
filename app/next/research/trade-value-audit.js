/* Trade value source audit (JEG-1565). Draws every chart from trade-value-audit-data.json.
   Vanilla JS, inline SVG, no external code. Motion only when the reader allows it. */
(function () {
  'use strict';
  var REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var NS = 'http://www.w3.org/2000/svg';
  var CHARTS = ['cbs', 'usatoday', 'fantasypros', 'fantasycalc'];
  var GRADED = CHARTS.concat(['dynastyprocess']);  /* the four redraft charts plus the open dynasty values */
  var NAME = { cbs: 'CBS Sports', usatoday: 'USA Today', fantasypros: 'FantasyPros', fantasycalc: 'FantasyCalc', dynastyprocess: 'DynastyProcess (dynasty)',
    espn: 'ESPN', cbsros: 'CBS rest-of-season', razzball: 'Razzball', ddf: 'Our model (DDF Value)',
    proj: 'Projections (our model)', analyst: 'Analyst charts' };
  var POS = ['QB', 'RB', 'WR', 'TE'];
  var DIMS = ['balance', 'scoring', 'superflex', 'league_size', 'depth', 'freshness', 'consolidation'];
  var DIM_NAME = { balance: 'Position balance', scoring: 'Scoring formats', superflex: 'Superflex', league_size: 'League size',
    depth: 'Depth', freshness: 'Freshness', consolidation: '2-for-1 sense' };
  var D = null;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  function svg(tag, attrs) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    return n;
  }
  function fmt(v) { return v == null ? 'n/a' : String(v); }  /* the script already rounds; show its value as written */
  function get(path) {
    return path.split('.').reduce(function (o, k) { return o == null ? undefined : o[k]; }, D);
  }
  function color(k) { return 'var(--c-' + k + ')'; }
  function onVisible(node, fn) {
    if (REDUCE || !('IntersectionObserver' in window)) { fn(); return; }
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { io.disconnect(); fn(); } });
    }, { threshold: 0.2 });
    io.observe(node);
  }
  function table(host, head, rows) {
    var t = el('table'), th = el('thead'), tr = el('tr');
    head.forEach(function (h, i) { tr.appendChild(el('th', { scope: 'col', class: i ? 'num' : '' }, h)); });
    th.appendChild(tr); t.appendChild(th);
    var tb = el('tbody');
    rows.forEach(function (r) {
      var row = el('tr');
      r.forEach(function (c, i) { row.appendChild(el(i ? 'td' : 'th', i ? { class: 'num' } : { scope: 'row' }, c)); });
      tb.appendChild(row);
    });
    t.appendChild(tb);
    host.innerHTML = '';
    host.appendChild(t);
  }
  function width(node) { return Math.max(280, Math.round(node.getBoundingClientRect().width)); }

  /* Numbers in the text: the HTML carries the script's values; JS re-binds them and counts the big ones up. */
  function bindNumbers() {
    $all('[data-n]').forEach(function (n) {
      var v = get(n.getAttribute('data-n'));
      if (v === undefined) return;
      n.textContent = fmt(v);
      /* Count up only from below the final value, and never duplicate the number in the DOM:
         the element keeps its final text at rest, so copy, reader views and screen readers get one number. */
      if (!n.classList.contains('count') || REDUCE || typeof v !== 'number' || Math.abs(v) < 2) return;
      onVisible(n, function () {
        n.textContent = '0';
        var t0 = null, dec = !Number.isInteger(v);
        function step(t) {
          if (!t0) t0 = t;
          var p = Math.min(1, (t - t0) / 1100), e = 1 - Math.pow(1 - p, 3);
          n.textContent = dec ? (v * e).toFixed(1) : String(Math.round(v * e));
          if (p < 1) requestAnimationFrame(step); else n.textContent = fmt(v);
        }
        requestAnimationFrame(step);
      });
    });
  }

  function reveals() {
    $all('.reveal').forEach(function (n) { onVisible(n, function () { n.classList.add('in'); }); });
  }

  /* Scorecard */
  function badge(dim) {
    var lv = dim ? dim.level : null;
    var dots = lv == null ? '–' : '●●●'.slice(0, lv) + '○○○'.slice(0, 3 - lv);
    var b = el('span', { class: 'badge b' + (lv == null ? 0 : lv) });
    b.appendChild(el('span', { class: 'd', 'aria-hidden': 'true' }, dots));
    b.appendChild(document.createTextNode(lv == null ? 'Not measured' : dim.label));
    return b;
  }
  function scorecard() {
    var fig = $('#scorecard'), tb = $('tbody', fig);
    GRADED.concat(['espn', 'cbsros', 'razzball']).forEach(function (k) {
      var tr = el('tr');
      tr.appendChild(el('th', { scope: 'row' }, NAME[k] + (k === 'fantasycalc' ? ' (Live market)' : '')));
      DIMS.forEach(function (dname) { var td = el('td'); td.appendChild(badge(D.scorecard[k][dname])); tr.appendChild(td); });
      tb.appendChild(tr);
    });
    var ul = $('#rules');
    DIMS.forEach(function (dname) { ul.appendChild(el('li', null, D.rules[dname])); });
    var bs = $all('.badge', fig);
    bs.forEach(function (b, i) { b.style.transitionDelay = (i * 25) + 'ms'; });
    onVisible(fig, function () { fig.classList.add('in'); });
    $all('.src[data-src]').forEach(function (card) {
      var k = card.getAttribute('data-src'), host = $('.rate', card);
      DIMS.forEach(function (dname) {
        var dim = D.scorecard[k][dname];
        if (!dim || dim.level == null) return;
        var b = badge(dim);
        b.insertBefore(document.createTextNode(DIM_NAME[dname] + ': '), b.childNodes[1]);
        host.appendChild(b);
      });
    });
  }

  /* 1. Position shares: stacked bars that reshuffle between settings */
  function positions() {
    var fig = $('#fig-pos'), host = $('.stack', fig), cur = 'half_ppr/12/1qb', shown = false;
    var rowsK = ['cbs', 'usatoday', 'fantasypros', 'fantasycalc', 'dynastyprocess', 'analyst', 'proj'];
    var segs = {};
    rowsK.forEach(function (k) {
      host.appendChild(el('div', { class: 'name' }, NAME[k]));
      var bar = el('div', { class: 'bar', role: 'img' });
      segs[k] = {};
      POS.forEach(function (p) {
        var s = el('div', { class: 'seg' });
        s.style.background = 'var(--p-' + p + ')';
        bar.appendChild(s);
        segs[k][p] = s;
      });
      segs[k].bar = bar;
      host.appendChild(bar);
    });
    function shares(c, k) {
      var pw = D.position_weighting[c];
      return k === 'proj' ? pw.projections_mean : k === 'analyst' ? pw.analyst_charts_mean : pw.sources[k];
    }
    function draw() {
      rowsK.forEach(function (k) {
        var s = shares(cur, k), label = [];
        POS.forEach(function (p) {
          segs[k][p].style.flexBasis = (shown ? s[p] : 0) + '%';
          var px = s[p] / 100 * segs[k].bar.getBoundingClientRect().width;
          segs[k][p].textContent = px >= 62 ? p + ' ' + Math.round(s[p]) + '%' : px >= 34 ? Math.round(s[p]) + '%' : '';
          label.push(p + ' ' + fmt(s[p]) + '%');
        });
        segs[k].bar.setAttribute('aria-label', NAME[k] + ': ' + label.join(', '));
      });
      table($('[data-table=pos]'), ['Source'].concat(POS.map(function (p) { return p + ' %'; })),
        rowsK.map(function (k) { var s = shares(cur, k); return [NAME[k]].concat(POS.map(function (p) { return fmt(s[p]); })); }));
    }
    $all('[data-case]', fig).forEach(function (b) {
      b.addEventListener('click', function () {
        cur = b.getAttribute('data-case');
        $all('[data-case]', fig).forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        draw();
      });
    });
    draw();
    onVisible(fig, function () { shown = true; draw(); });
    var rw; window.addEventListener('resize', function () { clearTimeout(rw); rw = setTimeout(draw, 150); });
  }

  /* 2. Value curves with a scoring toggle that morphs the lines */
  function curves() {
    var host = $('#curve'), keys = GRADED.concat(['ddf']), sc = 'half_ppr', cur = {}, raf = null;
    var N = 120, range = $('#rank'), out = $('#rank-out'), read = $('#rank-read'), drawn = REDUCE;
    var readTable = el('table', { class: 'rank-table' });
    var rh = el('thead'), rhr = el('tr');
    ['Source', 'Value', 'Player at this rank'].forEach(function (h, i) { rhr.appendChild(el('th', { scope: 'col', class: i === 1 ? 'num' : '' }, h)); });
    rh.appendChild(rhr); readTable.appendChild(rh); readTable.appendChild(el('tbody'));
    $('#rank-names').appendChild(readTable);
    function shortName(full, narrow) {
      if (!narrow) return full;
      var parts = full.split(' ');
      if (parts.length < 2) return full;
      var tail = parts.slice(1).join(' ');
      return parts[0].charAt(0) + '. ' + tail;
    }
    keys.forEach(function (k) { cur[k] = D.curves[sc][k].slice(); });
    var box = {};
    function geom() {
      var w = width(host), h = Math.round(Math.min(380, Math.max(240, w * 0.5)));
      return { w: w, h: h, l: 36, r: w < 500 ? 12 : 120, t: 10, b: 30 };
    }
    function path(vals, g) {
      return vals.map(function (v, i) {
        var x = g.l + (i / (N - 1)) * (g.w - g.l - g.r), y = g.t + (1 - v / 100) * (g.h - g.t - g.b);
        return (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
      }).join('');
    }
    function render() {
      var g = geom();
      host.innerHTML = '';
      var s = svg('svg', { viewBox: '0 0 ' + g.w + ' ' + g.h, width: g.w, height: g.h, 'aria-hidden': 'true' });
      var ax = svg('g', { class: 'axis' });
      [0, 25, 50, 75, 100].forEach(function (v) {
        var y = g.t + (1 - v / 100) * (g.h - g.t - g.b);
        ax.appendChild(svg('line', { x1: g.l, x2: g.w - g.r, y1: y, y2: y }));
        var t = svg('text', { x: g.l - 6, y: y + 4, 'text-anchor': 'end' }); t.textContent = v; ax.appendChild(t);
      });
      [1, 24, 50, 100, 120].forEach(function (rk) {
        var x = g.l + ((rk - 1) / (N - 1)) * (g.w - g.l - g.r);
        var t = svg('text', { x: x, y: g.h - 8, 'text-anchor': 'middle' }); t.textContent = '#' + rk; ax.appendChild(t);
      });
      s.appendChild(ax);
      box.lines = {};
      keys.forEach(function (k) {
        var p = svg('path', { d: path(cur[k], g), fill: 'none', 'stroke-width': k === 'ddf' ? 2.5 : 2.2,
          'stroke-dasharray': k === 'ddf' ? '6 5' : k === 'dynastyprocess' ? '2 3' : '', style: 'stroke:' + color(k) });
        s.appendChild(p);
        box.lines[k] = p;
      });
      if (g.r > 40) {
        var used = [];
        keys.forEach(function (k) {
          var y = g.t + (1 - cur[k][cur[k].length - 1] / 100) * (g.h - g.t - g.b);
          used.forEach(function (u) { if (Math.abs(u - y) < 14) y = u + 14; });
          used.push(y);
          var t = svg('text', { x: g.w - g.r + 8, y: y + 4, class: 'lbl', style: 'fill:' + color(k) });
          t.textContent = k === 'ddf' ? 'Our model' : k === 'dynastyprocess' ? 'DynastyProcess' : NAME[k];
          s.appendChild(t);
        });
      }
      box.cross = svg('line', { y1: g.t, y2: g.h - g.b, style: 'stroke:var(--muted)', 'stroke-dasharray': '3 3' });
      s.appendChild(box.cross);
      box.g = g; box.svg = s;
      host.appendChild(s);
      if (!drawn) {
        keys.forEach(function (k) {
          var p = box.lines[k], L = p.getTotalLength();
          p.style.strokeDasharray = L + ' ' + L; p.style.strokeDashoffset = L;
        });
      }
      s.style.touchAction = 'pan-y';
      s.addEventListener('pointerdown', function (e) { pick(e); });
      function pick(e) {
        var rect = s.getBoundingClientRect(), x = (e.clientX - rect.left) * (g.w / rect.width);
        var rk = Math.round(1 + (x - g.l) / (g.w - g.l - g.r) * (N - 1));
        if (rk >= 1 && rk <= N) { range.value = rk; cross(); }
      }
      s.addEventListener('pointermove', pick);
      cross();
    }
    function cross() {
      var rk = +range.value, g = box.g;
      out.textContent = rk;
      var x = g.l + ((rk - 1) / (N - 1)) * (g.w - g.l - g.r);
      box.cross.setAttribute('x1', x); box.cross.setAttribute('x2', x);
      var narrow = width(host) < 500, said = [], tb = el('tbody');
      keys.forEach(function (k) {
        var v = D.curves[sc][k][rk - 1], who = (D.curve_players[sc][k] || [])[rk - 1];
        var label = k === 'ddf' ? 'Our model' : k === 'dynastyprocess' ? 'DynastyProcess' : NAME[k];
        var name = who ? shortName(who[0], narrow) + ' (' + who[1] + ')' : 'not listed';
        var tr = el('tr');
        var th = el('th', { scope: 'row' }); var sw = el('span', { 'aria-hidden': 'true', style: 'display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:' + color(k) });
        th.appendChild(sw); th.appendChild(document.createTextNode(label)); tr.appendChild(th);
        tr.appendChild(el('td', { class: 'num' }, v == null ? '–' : fmt(v)));
        tr.appendChild(el('td', null, name));
        tb.appendChild(tr);
        said.push(label + ' ' + (v == null ? 'not listed' : fmt(v) + ', ' + who[0] + ', ' + who[1]));
      });
      readTable.replaceChild(tb, readTable.tBodies[0]);
      read.textContent = 'Rank ' + rk + ': ' + said.join('; ') + '.';
    }
    function morph(to) {
      var from = {}, t0 = null;
      keys.forEach(function (k) { from[k] = cur[k].slice(); });
      cancelAnimationFrame(raf);
      function frame(t) {
        if (!t0) t0 = t;
        var p = REDUCE ? 1 : Math.min(1, (t - t0) / 700), e = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
        keys.forEach(function (k) {
          var a = from[k], b = D.curves[to][k];
          cur[k] = b.map(function (v, i) { var x = a[i] == null ? v : a[i]; return x + (v - x) * e; });
          box.lines[k].setAttribute('d', path(cur[k], box.g));
        });
        if (p < 1) raf = requestAnimationFrame(frame); else { keys.forEach(function (k) { cur[k] = D.curves[to][k].slice(); }); }
      }
      raf = requestAnimationFrame(frame);
    }
    $all('[data-sc]', $('#fig-curve')).forEach(function (b) {
      b.addEventListener('click', function () {
        sc = b.getAttribute('data-sc');
        $all('[data-sc]', $('#fig-curve')).forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        morph(sc); cross(); tbl();
      });
    });
    range.addEventListener('input', cross);
    function tbl() {
      table($('[data-table=curve]'), ['Overall rank'].concat(keys.map(function (k) { return k === 'ddf' ? 'Our model' : NAME[k]; })),
        [1, 6, 12, 24, 36, 50, 75, 100, 120].map(function (rk) {
          return ['#' + rk].concat(keys.map(function (k) { return fmt(D.curves[sc][k][rk - 1]); }));
        }));
    }
    render(); tbl();
    var rw; window.addEventListener('resize', function () { clearTimeout(rw); rw = setTimeout(function () { drawn = true; render(); }, 150); });
    onVisible(host, function () {
      drawn = true;
      keys.forEach(function (k, i) {
        var p = box.lines[k];
        p.style.transition = 'stroke-dashoffset 1.4s ease ' + (i * 120) + 'ms';
        requestAnimationFrame(function () { p.style.strokeDashoffset = '0'; });
        setTimeout(function () { p.style.transition = ''; p.style.strokeDasharray = k === 'ddf' ? '6 5' : k === 'dynastyprocess' ? '2 3' : ''; }, 1700 + i * 120);
      });
    });
  }

  /* 3 and 6: racing bars */
  function race(host, rows, max, tableHost, head) {
    var fills = [];
    rows.forEach(function (r) {
      host.appendChild(el('div', { class: 'name' }, r.name));
      var tr = el('div', { class: 'track', role: 'img', 'aria-label': r.label });
      r.bars.forEach(function (b) {
        var f = el('div', { class: 'fill' });
        f.style.background = b.color;
        if (b.opacity) f.style.opacity = b.opacity;
        if (r.bars.length > 1) { f.style.height = (100 / r.bars.length) + '%'; f.style.borderRadius = '3px'; }
        tr.appendChild(f);
        fills.push([f, b.value / max * 100]);
      });
      host.appendChild(tr);
      host.appendChild(el('div', { class: 'val', 'aria-hidden': 'true' }, r.text));
    });
    function go() { fills.forEach(function (f, i) { f[0].style.transitionDelay = (i * 90) + 'ms'; f[0].style.width = f[1] + '%'; }); }
    onVisible(host, go);
    table(tableHost, head, rows.map(function (r) { return r.cells; }));
  }
  function scoringRace() {
    var h = D.headline.reorder_avg_pct;
    var ks = Object.keys(h).sort(function (a, b) { return h[b] - h[a] || (a < b ? -1 : 1); });
    race($('#fig-race .race'), ks.map(function (k) {
      return { name: NAME[k], text: fmt(h[k]) + '%', label: NAME[k] + ': ' + fmt(h[k]) + '% change places',
        bars: [{ value: h[k], color: color(k) }], cells: [NAME[k]].concat(['RB', 'WR', 'TE'].map(function (p) { return fmt(D.scoring[k][p].order_changed_pct); }), [fmt(h[k])]) };
    }), 100, $('[data-table=race]'), ['Source', 'RB %', 'WR %', 'TE %', 'Average %']);
  }
  function pairsRace() {
    var c = D.consolidation;
    var rows = GRADED.map(function (k) {
      return { name: NAME[k], text: fmt(c[k].after_waiver_beats_star_pct) + '%',
        label: NAME[k] + ': ' + fmt(c[k].raw_beats_star_pct) + '% raw, ' + fmt(c[k].after_waiver_beats_star_pct) + '% after subtracting waiver value',
        bars: [{ value: c[k].raw_beats_star_pct, color: color(k), opacity: .4 }, { value: c[k].after_waiver_beats_star_pct, color: color(k) }],
        cells: [NAME[k], fmt(c[k].raw_beats_star_pct), fmt(c[k].after_waiver_beats_star_pct)] };
    });
    rows.push({ name: NAME.ddf, text: fmt(c.ddf.after_waiver_beats_star_pct) + '%', label: 'Our model: ' + fmt(c.ddf.after_waiver_beats_star_pct) + '%',
      bars: [{ value: c.ddf.after_waiver_beats_star_pct, color: color('ddf') }], cells: [NAME.ddf, 'n/a', fmt(c.ddf.after_waiver_beats_star_pct)] });
    race($('#pairs'), rows, 100, $('[data-table=pairs]'), ['Source', 'Raw %', 'After waiver %']);
  }

  /* 4. Superflex dumbbell */
  function superflex() {
    var host = $('#sf'), ks = GRADED.concat(['espn', 'cbsros', 'razzball']), started = REDUCE;
    function render() {
      var w = width(host), rowH = 40, l = w < 500 ? 120 : 190, r = 20, h = ks.length * rowH + 34;
      var x = function (v) { return l + v / 60 * (w - l - r); };
      host.innerHTML = '';
      var s = svg('svg', { viewBox: '0 0 ' + w + ' ' + h, width: w, height: h, role: 'img', 'aria-label': 'Quarterback share of value, one-QB to superflex' });
      [0, 20, 40, 60].forEach(function (v) {
        s.appendChild(svg('line', { x1: x(v), x2: x(v), y1: 0, y2: h - 24, style: 'stroke:var(--line)' }));
        var t = svg('text', { x: x(v), y: h - 6, 'text-anchor': 'middle' }); t.textContent = v + '%'; s.appendChild(t);
      });
      ks.forEach(function (k, i) {
        var y = 18 + i * rowH, a = D.superflex[k].qb_share_1qb, b = D.superflex[k].qb_share_sf;
        var t = svg('text', { x: 0, y: y + 4, class: 'lbl' }); t.textContent = NAME[k]; s.appendChild(t);
        var stem = svg('line', { class: 'stem', x1: x(a), x2: x(started ? b : a), y1: y, y2: y, 'stroke-width': 4, style: 'stroke:' + color(k), opacity: .45 });
        s.appendChild(stem);
        s.appendChild(svg('circle', { cx: x(a), cy: y, r: 7, fill: 'var(--surface)', 'stroke-width': 2.5, style: 'stroke:' + color(k) }));
        var dot = svg('circle', { class: 'dot', cx: x(started ? b : a), cy: y, r: 8, style: 'fill:' + color(k) });
        s.appendChild(dot);
        var v = svg('text', { x: x(b) + 12, y: y + 4, class: 'lbl' }); v.textContent = fmt(b) + '%'; s.appendChild(v);
        if (!started) { dot.dataset.to = x(b); stem.dataset.to = x(b); }
      });
      host.appendChild(s);
    }
    render();
    onVisible(host, function () {
      started = true;
      $all('[data-to]', host).forEach(function (n) { n.setAttribute(n.tagName === 'circle' ? 'cx' : 'x2', n.dataset.to); });
    });
    var rw; window.addEventListener('resize', function () { clearTimeout(rw); rw = setTimeout(function () { started = true; render(); }, 150); });
    table($('[data-table=sf]'), ['Source', 'QB share, one-QB %', 'QB share, superflex %', 'Superflex QBs listed'],
      ks.map(function (k) { var v = D.superflex[k]; return [NAME[k], fmt(v.qb_share_1qb), fmt(v.qb_share_sf), v.superflex_qbs_listed == null ? 'n/a' : fmt(v.superflex_qbs_listed)]; }));
  }

  /* 5. Depth against the waiver line */
  function depth() {
    var host = $('#depth'), fig = $('#fig-depth'), dv = D.depth_vs_waiver, teams = '12', pos = 'RB', started = REDUCE;
    var VERDICT = { short: 'Stops short', near: 'Ends near the line', past: 'Reaches past' };
    function render() {
      var w = width(host), narrow = w < 500, h = Math.round(Math.min(340, Math.max(230, w * 0.45)));
      var g = { l: 36, r: narrow ? 14 : 24, t: 14, b: 30 };
      var ros = dv.rostered[teams][pos], maxX = Math.min(130, Math.max(ros + 25, Math.round(ros * 1.6)));
      var x = function (rk) { return g.l + (Math.min(rk, maxX) - 1) / (maxX - 1) * (w - g.l - g.r); };
      var y = function (v) { return g.t + (1 - v / 100) * (h - g.t - g.b); };
      host.innerHTML = '';
      var s = svg('svg', { viewBox: '0 0 ' + w + ' ' + h, width: w, height: h, 'aria-hidden': 'true' });
      [0, 25, 50, 75, 100].forEach(function (v) {
        s.appendChild(svg('line', { x1: g.l, x2: w - g.r, y1: y(v), y2: y(v), style: 'stroke:var(--line)' }));
        var t = svg('text', { x: g.l - 6, y: y(v) + 4, 'text-anchor': 'end' }); t.textContent = v; s.appendChild(t);
      });
      [1, ros + 1, maxX].forEach(function (rk) { var t = svg('text', { x: x(rk), y: h - 8, 'text-anchor': 'middle' }); t.textContent = pos + rk; s.appendChild(t); });
      var lx = x(ros + 1);
      s.appendChild(svg('rect', { x: lx, y: g.t, width: Math.max(0, w - g.r - lx), height: h - g.t - g.b, style: 'fill:var(--soft)', opacity: .6 }));
      s.appendChild(svg('line', { x1: lx, x2: lx, y1: g.t, y2: h - g.b, 'stroke-width': 2, 'stroke-dasharray': '5 4', style: 'stroke:var(--ink)' }));
      var wl = svg('text', { x: lx + 6, y: g.t + 12, class: 'lbl' }); wl.textContent = 'Waiver line'; s.appendChild(wl);
      GRADED.forEach(function (k, idx) {
        var c = dv.sources[k]['12'][pos].curve, n = dv.sources[k][teams][pos].listed;
        var d = c.map(function (v, i) { return (i ? 'L' : 'M') + x(i + 1).toFixed(1) + ' ' + y(v).toFixed(1); }).join('');
        var p = svg('path', { d: d, fill: 'none', 'stroke-width': 2, style: 'stroke:' + color(k) });
        s.appendChild(p);
        var endRank = Math.min(n, maxX), endV = c[Math.min(n, c.length) - 1];
        var dot = svg('circle', { cx: x(endRank), cy: y(endV), r: started ? 6 : 0, style: 'fill:' + color(k) + ';transition:r .5s ' + (idx * 120) + 'ms', stroke: 'var(--surface)', 'stroke-width': 2 });
        s.appendChild(dot);
        if (n > maxX) { var t = svg('text', { x: w - g.r, y: y(endV) - 8, 'text-anchor': 'end', style: 'fill:' + color(k) }); t.textContent = '→ ' + n; s.appendChild(t); }
        if (!started) {
          var L = p.getTotalLength(); p.style.strokeDasharray = L + ' ' + L; p.style.strokeDashoffset = L;
        }
      });
      host.appendChild(s);
      return s;
    }
    function animateIn(svgEl) {
      $all('path', svgEl).forEach(function (p, i) { p.style.transition = 'stroke-dashoffset 1.2s ease ' + (i * 120) + 'ms'; p.style.strokeDashoffset = '0'; });
      $all('circle', svgEl).forEach(function (c) { c.setAttribute('r', 6); });
    }
    function readout() {
      var narrow = width(host) < 500, host2 = $('[data-table=depth]');
      host2.innerHTML = '';
      host2.appendChild(el('p', { class: 'meta' }, pos + ', ' + teams + ' teams: the waiver line falls after ' + pos + dv.rostered[teams][pos] + '.'));
      var ul = el('ul', { class: 'depth-list' });
      GRADED.forEach(function (k) {
        var r = dv.sources[k][teams][pos], parts = r.last_name.split(' ');
        var name = narrow && parts.length > 1 ? parts[0].charAt(0) + '. ' + parts.slice(1).join(' ') : r.last_name;
        var where = r.class === 'short' ? r.unpriced + ' rostered players unpriced' : r.class === 'past' ? r.beyond + ' players the waiver wire could replace' : 'within ' + Math.abs(r.gap) + ' of the line';
        var li = el('li');
        var hd = el('div', { class: 'dl-head' });
        hd.appendChild(el('span', { 'aria-hidden': 'true', class: 'sw', style: 'background:' + color(k) }));
        hd.appendChild(el('b', null, NAME[k]));
        hd.appendChild(el('span', { class: 'dl-tag dl-' + r.class }, VERDICT[r.class]));
        li.appendChild(hd);
        li.appendChild(el('div', null, fmt(r.listed) + ' listed; last player listed: ' + name + ', ' + fmt(r.last_pct_of_top) + '% of its top ' + pos + '. ' + where.charAt(0).toUpperCase() + where.slice(1) + '.'));
        ul.appendChild(li);
      });
      var m = dv.ddf[teams][pos], li = el('li'), hd = el('div', { class: 'dl-head' });
      hd.appendChild(el('span', { 'aria-hidden': 'true', class: 'sw', style: 'background:' + color('ddf') }));
      hd.appendChild(el('b', null, NAME.ddf));
      li.appendChild(hd);
      li.appendChild(el('div', null, fmt(m.valued) + ' players valued above a token amount (0.05); ' + (m.valued < m.rostered ? (m.rostered - m.valued) + ' rostered players below it.' : 'every rostered player valued.') + (m.past_line_valued ? ' ' + m.past_line_valued + ' past the line valued above zero.' : '')));
      ul.appendChild(li);
      host2.appendChild(ul);
    }
    function draw(anim) { var el2 = render(); readout(); if (!anim && started) animateIn(el2); }
    $all('[data-teams]', fig).forEach(function (b) { b.addEventListener('click', function () { teams = b.getAttribute('data-teams'); $all('[data-teams]', fig).forEach(function (x2) { x2.setAttribute('aria-pressed', String(x2 === b)); }); started = true; draw(true); }); });
    $all('[data-dpos]', fig).forEach(function (b) { b.addEventListener('click', function () { pos = b.getAttribute('data-dpos'); $all('[data-dpos]', fig).forEach(function (x2) { x2.setAttribute('aria-pressed', String(x2 === b)); }); started = true; draw(true); }); });
    var first = render(); readout();
    onVisible(host, function () { started = true; requestAnimationFrame(function () { animateIn(first); }); });
    var rw; window.addEventListener('resize', function () { clearTimeout(rw); rw = setTimeout(function () { started = true; draw(true); }, 150); });
  }

  /* 6. Trade it yourself */
  function trade() {
    var P = D.players, give = $('#give'), g1 = $('#get1'), g2 = $('#get2'), sub = $('#sub'), out = $('#verdicts');
    [give, g1, g2].forEach(function (s) {
      P.forEach(function (p, i) { s.appendChild(el('option', { value: i }, p.name + ' (' + p.pos + ')')); });
    });
    function idx(name) { for (var i = 0; i < P.length; i++) if (P[i].name === name) return i; return 0; }
    give.value = idx('Puka Nacua'); g1.value = idx('George Pickens'); g2.value = idx('Zay Flowers');
    function val(k, p) {
      var v = p.published[k];
      if (v == null) return null;
      return sub.checked ? Math.max(0, v - D.waiver_line[k][p.pos]) : v;
    }
    function verdictRow(name, c, giveV, getV) {
      var row = el('div', { class: 'verdict' });
      row.appendChild(el('div', { style: 'font-weight:600' }, name));
      var m = el('div', { class: 'meter', 'aria-hidden': 'true' }), fill = el('div', { class: 'fill' });
      m.appendChild(el('div', { class: 'mid' })); m.appendChild(fill);
      var text;
      if (giveV == null || getV == null || giveV <= 0) { text = 'Not on this chart'; }
      else {
        var pct = (getV - giveV) / giveV * 100, capped = Math.max(-100, Math.min(100, pct));
        fill.style.background = c;
        fill.style.left = (capped < 0 ? 50 + capped / 2 : 50) + '%';
        fill.style.width = Math.abs(capped) / 2 + '%';
        text = Math.abs(pct) <= 5 ? 'Even' : (pct > 0 ? 'You win by ' : 'You lose by ') + Math.round(Math.abs(pct)) + '%';
      }
      row.appendChild(m);
      row.appendChild(el('div', { class: 'vtext' }, text));
      return [row, name + ': ' + text];
    }
    function update() {
      var a = P[+give.value], b = P[+g1.value], c = P[+g2.value];
      out.innerHTML = '';
      var said = [];
      GRADED.forEach(function (k) {
        var gv = val(k, a), x = val(k, b), y = val(k, c);
        var r = verdictRow(NAME[k], color(k), gv, x == null || y == null ? null : x + y);
        out.appendChild(r[0]); said.push(r[1]);
      });
      var r = verdictRow(NAME.ddf, color('ddf'), a.ddf, b.ddf + c.ddf);
      out.appendChild(r[0]); said.push(r[1]);
      if (+g1.value === +g2.value || +give.value === +g1.value || +give.value === +g2.value) {
        out.appendChild(el('p', { class: 'meta' }, 'Pick three different players for a real 2-for-1.'));
      }
      out.setAttribute('aria-label', said.join('. '));
    }
    [give, g1, g2, sub].forEach(function (s) { s.addEventListener('change', update); });
    update();
  }

  /* 7. Disagreement scatter */
  function scatter() {
    var host = $('#scatter'), read = $('#scatter-read'), src = 'cbs', tip = el('div', { class: 'tip', role: 'presentation' });
    var MAXR = 36, pts = [], focusI = -1, circles = [];
    D.players.forEach(function (p) {
      var rk = p.pos_rank;
      if (CHARTS.some(function (k) { return rk[k] == null; })) return;
      pts.push(p);
    });
    function med(p, k) { var o = CHARTS.filter(function (x) { return x !== k; }).map(function (x) { return p.pos_rank[x]; }).sort(function (a, b) { return a - b; }); return o[1]; }
    var g;
    function render() {
      var w = width(host), size = Math.min(w, 560);
      g = { w: size, h: size, l: 40, r: 12, t: 10, b: 34 };
      var sx = function (v) { return g.l + (Math.min(v, MAXR + 4) - 1) / (MAXR + 3) * (g.w - g.l - g.r); };
      var sy = function (v) { return g.t + (Math.min(v, MAXR + 4) - 1) / (MAXR + 3) * (g.h - g.t - g.b); };
      g.sx = sx; g.sy = sy;
      host.innerHTML = '';
      host.appendChild(tip);
      var s = svg('svg', { viewBox: '0 0 ' + g.w + ' ' + g.h, width: g.w, height: g.h, tabindex: '0', role: 'img',
        'aria-label': 'Scatter of position ranks. Use the left and right arrow keys to step through players, biggest disagreements first.', style: 'max-width:560px' });
      s.appendChild(svg('line', { x1: sx(1), y1: sy(1), x2: sx(MAXR + 4), y2: sy(MAXR + 4), style: 'stroke:var(--muted)', 'stroke-dasharray': '4 4' }));
      [1, 12, 24, 36].forEach(function (v) {
        var t = svg('text', { x: sx(v), y: g.h - 16, 'text-anchor': 'middle' }); t.textContent = v; s.appendChild(t);
        var u = svg('text', { x: g.l - 8, y: sy(v) + 4, 'text-anchor': 'end' }); u.textContent = v; s.appendChild(u);
      });
      var xl = svg('text', { x: (g.l + g.w) / 2, y: g.h - 1, 'text-anchor': 'middle' }); xl.textContent = 'Other three charts (median rank)'; s.appendChild(xl);
      var yl = svg('text', { x: g.w - g.r, y: g.t + 12, 'text-anchor': 'end' }); yl.textContent = '\u2191 ' + NAME[src] + ' rank (1 = best)'; yl.setAttribute('class', 'lbl ylab'); s.appendChild(yl); g.ylab = yl;
      circles = pts.map(function (p) {
        var c = svg('circle', { cx: sx(med(p, src)), cy: sy(REDUCE ? p.pos_rank[src] : med(p, src)), r: 5, style: 'fill:var(--p-' + p.pos + ');opacity:.85' });
        c.addEventListener('pointerenter', function () { show(p, c); });
        c.addEventListener('pointerdown', function () { show(p, c); });
        c.addEventListener('pointerleave', function () { tip.classList.remove('on'); });
        s.appendChild(c);
        return c;
      });
      s.addEventListener('keydown', function (e) {
        if (['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].indexOf(e.key) < 0) return;
        e.preventDefault();
        var order = sorted();
        focusI = (focusI + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : -1) + order.length) % order.length;
        var i = order[focusI]; show(pts[i], circles[i]);
      });
      s.addEventListener('blur', function () { tip.classList.remove('on'); });
      host.appendChild(s);
      place();
    }
    function sorted() {
      return pts.map(function (p, i) { return i; }).filter(function (i) { return Math.min(pts[i].pos_rank[src], med(pts[i], src)) <= MAXR; })
        .sort(function (a, b) { return Math.abs(pts[b].pos_rank[src] - med(pts[b], src)) - Math.abs(pts[a].pos_rank[src] - med(pts[a], src)) || a - b; });
    }
    function place() {
      circles.forEach(function (c, i) {
        var p = pts[i], m = med(p, src), r = p.pos_rank[src], vis = Math.min(r, m) <= MAXR;
        c.setAttribute('cx', g.sx(m)); c.setAttribute('cy', g.sy(r)); c.setAttribute('r', vis ? 5 : 0);
      });
    }
    function show(p, c) {
      var m = med(p, src), r = p.pos_rank[src];
      var text = p.name + ' (' + p.pos + '): ' + NAME[src] + ' ranks him ' + p.pos + r + ', the other three ' + p.pos + m + ' (median).';
      tip.textContent = text; read.textContent = text;
      var cx = +c.getAttribute('cx'), cy = +c.getAttribute('cy');
      tip.style.left = Math.min(cx + 12, g.w - 200) + 'px'; tip.style.top = Math.max(0, cy - 44) + 'px';
      tip.classList.add('on');
      circles.forEach(function (x) { x.style.stroke = ''; });
      c.style.stroke = 'var(--ink)'; c.style.strokeWidth = '2';
    }
    $all('[data-src]', $('#fig-scatter')).forEach(function (b) {
      b.addEventListener('click', function () {
        src = b.getAttribute('data-src'); focusI = -1; tip.classList.remove('on');
        $all('[data-src]', $('#fig-scatter')).forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        if (g.ylab) g.ylab.textContent = '\u2191 ' + NAME[src] + ' rank (1 = best)';
        place();
      });
    });
    render();
    onVisible(host, function () { setTimeout(place, 60); });
    var rw; window.addEventListener('resize', function () { clearTimeout(rw); rw = setTimeout(render, 150); });
    table($('[data-table=outliers]'), ['Player', 'Chart', 'Its rank', 'Others (median)', 'Gap'],
      D.outliers.slice(0, 16).map(function (o) { return [o.name + ' (' + o.pos + ')', NAME[o.source], o.pos + o.rank, o.pos + o.others_median_rank, (o.gap > 0 ? '+' : '') + o.gap]; }));
  }

  function freshness() {
    var ks = GRADED.concat(['espn', 'cbsros', 'razzball']), w = D.weekly;
    table($('[data-table=fresh]'), ['Source', 'Snapshot dates (weeks 5 to 9)', 'Rank move per week', 'Same number per week %'],
      ks.map(function (k) { return [NAME[k], w[k].snapshot_dates.join(', '), w[k].rank_move.map(fmt).join(', '), w[k].unchanged_pct.map(fmt).join(', ')]; }));
  }

  /* DynastyProcess is computed in its own block; fold it into the shared shapes the charts read. */
  function foldDynasty() {
    var dp = D.dynastyprocess, k = 'dynastyprocess';
    Object.keys(dp.shares).forEach(function (c) { D.position_weighting[c].sources[k] = dp.shares[c]; });
    Object.keys(D.curves).forEach(function (sc) { D.curves[sc][k] = dp.curve; });
    Object.keys(D.curve_players).forEach(function (sc) { D.curve_players[sc][k] = dp.curve_players; });
    D.superflex[k] = dp.superflex;
    D.sources[k] = { listed: dp.listed, rostered: dp.rostered, filled_in: dp.filled_in };
    D.consolidation[k] = dp.consolidation;
    D.weekly[k] = { snapshot_dates: dp.weekly.snapshot_dates, rank_move: dp.weekly.rank_move, unchanged_pct: dp.weekly.unchanged_pct };
  }
  function ageBands() {
    var host = $('#age'); if (!host) return;
    var b = D.dynastyprocess.age_bands, max = 5, fills = [];
    b.forEach(function (x) {
      host.appendChild(el('div', { class: 'name' }, 'Age ' + x.band + ' (' + x.n + ')'));
      var tr = el('div', { class: 'track', role: 'img', 'aria-label': 'Age ' + x.band + ': ' + fmt(x.mean_rank_gain) + ' places' });
      tr.style.position = 'relative';
      tr.appendChild(el('div', { class: 'mid', style: 'position:absolute;left:50%;top:0;bottom:0;width:2px;background:var(--muted);opacity:.5' }));
      var f = el('div', { class: 'fill' }), v = x.mean_rank_gain;
      f.style.position = 'absolute'; f.style.background = v >= 0 ? 'var(--c-dynastyprocess)' : 'var(--warn)';
      f.style.left = v >= 0 ? '50%' : (50 - Math.abs(v) / max * 50) + '%';
      tr.appendChild(f); host.appendChild(tr);
      host.appendChild(el('div', { class: 'val', 'aria-hidden': 'true' }, (v > 0 ? '+' : '') + fmt(v)));
      fills.push([f, Math.abs(v) / max * 50]);
    });
    onVisible(host, function () { fills.forEach(function (f, i) { f[0].style.transitionDelay = (i * 120) + 'ms'; f[0].style.width = f[1] + '%'; }); });
    table($('[data-table=age]'), ['Age', 'Players', 'Average places gained at his position'], b.map(function (x) { return [x.band, fmt(x.n), fmt(x.mean_rank_gain)]; }));
  }
  function start(data) {
    D = data;
    foldDynasty();
    bindNumbers(); reveals(); scorecard(); ageBands(); positions(); curves(); scoringRace(); superflex(); depth(); trade(); pairsRace(); scatter(); freshness();
  }
  if (REDUCE) document.documentElement.classList.add('no-motion');
  /* The single-file copy (pipelines/build_trade_value_audit_single.py) carries the data inline. */
  var inline = document.getElementById('tva-data');
  if (inline) { start(JSON.parse(inline.textContent)); return; }
  fetch('trade-value-audit-data.json', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(start).catch(function () {
    $all('.chart').forEach(function (c) { c.textContent = 'The chart data did not load. The numbers in the text are still current.'; });
  });
})();
