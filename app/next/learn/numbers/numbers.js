/* Learn > How we get our numbers (JEG-1536).
   Value pie (one player's DDF Value by chart, plus the league Health check), Source build-up,
   Trace, Glossary and the full value logic, all read from the live engine on this page through
   learn/numbers/learn-engine.js. This file renders; it never computes a value.
   Routes: #numbers/pie/<player_key>, #numbers/build-up/<source>[/<position>], #numbers/trace/<player_key>,
   #numbers/glossary[/<term>], #numbers/logic. Any of them may end in
   ?scoring=<standard|half_ppr|ppr>&teams=<8|10|12|14>&roster=QB1.RB2.WR2.TE1.FLEX1.SF0.BN7 to pin the league settings. */
(function () {
  'use strict';
  var VIEWS = ['pie', 'build-up', 'trace', 'glossary', 'logic'];
  var POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE'];
  var COLORS = ['#0f5139', '#2f8f6b', '#6bb394', '#b5dcc8'];
  var PAGE = 50;
  var QUICK = 5;
  var LE = function () { return window.DDFLearnEngine; };

  var snap = null, byKey = {}, byName = {}, loading = null, loadedQuery = null;
  var state = { view: 'pie', player: null, source: 'cbs', position: 'ALL', limit: PAGE, query: '' };
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var calm = function () { return !window.matchMedia || !window.matchMedia('(prefers-reduced-motion: no-preference)').matches; };
  var isNumbersHash = function () { return /^#numbers(\/|\?|$)/.test(location.hash); };

  /* ---------- number formatting ---------- */
  var DASH = '—';
  var num = function (n) { return typeof n === 'number' && isFinite(n); };
  var f1 = function (n) { return num(n) ? Number(n).toFixed(1).replace(/^-0\.0$/, '0.0').replace('-', '−') : DASH; };
  var fPub = function (src, n) {
    if (!num(n)) return DASH;
    return src === 'fantasycalc' ? Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 }) : f1(n);
  };
  var fPts = function (n) { return num(n) ? Number(n).toFixed(2) : DASH; };
  var fInt = function (n) { return num(n) ? Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 }) : DASH; };
  var fFactor = function (n) { return num(n) ? String(Number(n.toPrecision(6))) : DASH; };
  var tenths = function (n) { return Math.round(Number(n) * 10); };
  var trim = function (s) { return s.replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '.0'); };
  var pct = function (v) { return (v * 100).toFixed(1) + '%'; };
  var label = function (s) { return LE().LABELS[s] || s; };

  /* ---------- settings ---------- */
  var SLOT_CODE = { QB: 'QB', RB: 'RB', WR: 'WR', TE: 'TE', FLEX: 'FLEX', SUPERFLEX: 'SF', BENCH: 'BN' };
  function rosterParam(r) {
    return ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX', 'BENCH'].map(function (k) { return SLOT_CODE[k] + (r[k] || 0); }).join('.');
  }
  function parseRoster(text) {
    var out = {};
    String(text || '').split('.').forEach(function (part) {
      var m = /^(QB|RB|WR|TE|FLEX|SF|BN)(\d{1,2})$/.exec(part);
      if (!m) return;
      var key = { SF: 'SUPERFLEX', BN: 'BENCH' }[m[1]] || m[1];
      out[key] = Number(m[2]);
    });
    return Object.keys(out).length ? out : null;
  }
  function querySettings(q) {
    var p = new URLSearchParams(q || '');
    var s = {};
    var sc = p.get('scoring');
    if (sc && LE().SCORING_LABEL[sc]) s.scoring = sc;
    var t = Number(p.get('teams'));
    if ([8, 10, 12, 14].indexOf(t) >= 0) s.teams = t;
    var r = parseRoster(p.get('roster'));
    if (r) s.roster = r;
    return Object.keys(s).length ? s : null;
  }
  function settingsQuery(st) {
    return '?scoring=' + st.scoring + '&teams=' + st.teams + '&roster=' + rosterParam(st.roster);
  }
  function settingsLine(st) {
    return st.scoringLabel + ', ' + st.teams + ' teams, roster ' + st.rosterLabel + (st.superflex ? ' (superflex)' : '');
  }
  /* ---------- formulas ---------- */
  function shownMean(p) {
    var t = snap.charts.reduce(function (a, s) { return a + tenths(p.sources[s].adjusted); }, 0);
    return t / (10 * snap.charts.length);
  }
  function tiesOut(p) { return f1(shownMean(p)) === f1(p.ddf); }
  function inDdf(p) { return snap.charts.every(function (s) { return p.sources[s] && num(p.sources[s].adjusted); }) && snap.basis.isDefault; }
  function formula(p) {
    if (!inDdf(p)) return f1(p.ddf) + ' (' + basisNote(p) + ')';
    var parts = snap.charts.map(function (s) { return f1(p.sources[s].adjusted); });
    var m = trim(shownMean(p).toFixed(3));
    return '(' + parts.join(' + ') + ') ÷ ' + snap.charts.length + ' = ' + m + (tiesOut(p) ? ' → ' + f1(p.ddf) : '; DDF Value ' + f1(p.ddf));
  }
  function basisNote(p) {
    if (!snap.basis.isDefault) return 'built from your value basis, ' + snap.basis.label;
    var have = p.ddfSources.map(label);
    return 'the average of the ' + have.length + ' chart' + (have.length === 1 ? '' : 's') + ' that price him: ' + have.join(', ');
  }
  var ROUNDING_NOTE = 'The adjusted values are shown rounded to one decimal; DDF Value averages the unrounded values.';
  function chartWord() { return snap.charts.length === 4 ? 'four' : String(snap.charts.length); }
  function pieText() {
    return fInt(snap.pie) + (num(snap.perSlot) && Number.isInteger(snap.perSlot)
      ? ' = ' + snap.perSlot + ' × ' + snap.settings.teams + ' teams × ' + snap.startSlots + ' starting slots' : '');
  }
  function snapshotLine() {
    var m = snap.meta;
    return [m.week ? 'Week ' + m.week : null, m.asOf ? 'as of ' + m.asOf : null, m.build ? 'build ' + m.build : null].filter(Boolean).join(' · ');
  }
  /* Learn shows the model's own DDF Value at the default basis; the reader's overrides and basis apply on the other pages. */
  function overridesLine() {
    var notes = [];
    if (snap.overrides) notes.push('your ' + snap.overrides + ' override' + (snap.overrides === 1 ? ' is' : 's are') + ' not applied here');
    if (snap.readerBasis) notes.push('your value basis (' + snap.readerBasis + ') is not applied here');
    return notes.length ? notes.join('; ') + ' (the model’s own value, four-chart average)' : 'no overrides (the model’s own value)';
  }
  function permalink(view, arg) {
    return location.href.split('#')[0] + '#numbers/' + view + (arg !== undefined && arg !== '' ? '/' + arg : '') + settingsQuery(snap.settings);
  }
  function link(view, arg) { return '#numbers/' + view + (arg !== undefined && arg !== '' ? '/' + arg : '') + state.query; }

  function llmText(p) {
    var inputs = snap.charts.map(function (s) {
      var r = p.sources[s];
      if (!r) return label(s) + ': not priced';
      return label(s) + ' published ' + fPub(s, r.published).replace(/,/g, '') + ' → indexed ' + f1(r.indexed) + ' → adjusted ' + f1(r.adjusted) + (r.estimated ? ' (filled in from other charts)' : '');
    }).join('; ');
    return 'DDF Value, ' + p.name + ' (' + p.pos + '), ' + settingsLine(snap.settings) + ', ' + snapshotLine() + '.\n' +
      'Inputs: ' + inputs + '.\n' +
      'Rule: DDF Value = mean of the ' + chartWord() + ' adjusted trade charts = ' + formula(p) +
      (inDdf(p) && !tiesOut(p) ? ' (the tool averages the unrounded adjusted values)' : '') + '. Overrides and value basis: not applied (the model’s own value).\n' +
      'Indexed = published x one factor per chart: ' + snap.charts.map(function (s) { return label(s) + ' ' + fFactor(snap.sources[s].factor); }).join(', ') + '.\n' +
      'Adjusted totals per chart = value pie ' + pieText() + '.\n' +
      'Trace: ' + permalink('trace', p.player_key);
  }
  function jsonFor(p) {
    var srcMeta = {};
    snap.charts.forEach(function (s) {
      var m = snap.sources[s];
      srcMeta[s] = { label: m.label, players_listed: m.listed, filled_in: m.filledIn, totals: m.totals, index_factor: m.factor };
    });
    return JSON.stringify({
      snapshot: { week: snap.meta.week, as_of: snap.meta.asOf, build: snap.meta.build, settings: snap.settings, overrides: 'not applied (model value)', basis: 'default (four trade charts, equal weight)',
        rule: 'DDF Value = mean of the adjusted trade charts that price the player', value_pie: snap.pie },
      player: { player_key: p.player_key, name: p.name, pos: p.pos, ddf_value: p.ddf, ddf_rank: p.rank, sources: p.sources },
      sources: srcMeta, permalink: permalink('trace', p.player_key)
    }, null, 2);
  }

  /* ---------- tabs ---------- */
  function setArea(area) {
    var numbers = area === 'numbers';
    $('panel-writing').hidden = numbers;
    $('panel-numbers').hidden = !numbers;
    setTabs($('learn-area-tabs'), numbers ? 'tab-numbers' : 'tab-writing');
  }
  function setTabs(list, activeId) {
    Array.prototype.forEach.call(list.querySelectorAll('[role=tab]'), function (t) {
      var on = t.id === activeId;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
    });
  }
  function wireTabKeys(list) {
    list.addEventListener('keydown', function (e) {
      var tabs = Array.prototype.slice.call(list.querySelectorAll('[role=tab]'));
      var i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      var j = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
      if (j === null) return;
      e.preventDefault();
      j = (j + tabs.length) % tabs.length;
      tabs[j].focus();
      tabs[j].click();
    });
  }

  /* ---------- player pickers ---------- */
  function fillPickers() {
    $('nx-players').innerHTML = snap.players.map(function (p) { return '<option data-key="' + p.player_key + '" value="' + esc(p.name) + '">' + esc(p.pos + ' · ' + f1(p.ddf)) + '</option>'; }).join('');
  }
  function wirePicker(input, view) {
    var status = $(input.id + '-hint');
    var tryPick = function (final) {
      if (!snap) return;
      var p = byName[input.value.trim().toLowerCase()];
      if (p) { status.textContent = ''; if (p.player_key !== state.player || state.view !== view) location.hash = link(view, p.player_key); return; }
      if (final && input.value.trim()) {
        var q = input.value.trim().toLowerCase();
        var hits = snap.players.filter(function (x) { return x.name.toLowerCase().indexOf(q) >= 0; });
        if (hits.length === 1) { input.value = hits[0].name; tryPick(false); return; }
        status.textContent = hits.length ? hits.length + ' players match. Pick one from the list.' : 'No player by that name has a DDF Value at these settings.';
      }
    };
    input.addEventListener('input', function () { tryPick(false); });
    input.addEventListener('change', function () { tryPick(true); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); tryPick(true); } });
  }
  function quickPicks(el, view) {
    el.innerHTML = snap.players.slice(0, QUICK).map(function (p) {
      return '<a class="nx-chip" href="' + link(view, p.player_key) + '"' + (p.player_key === state.player ? ' aria-current="true"' : '') + '>' + esc(p.name) + '</a>';
    }).join('');
  }
  function estTag(r) { return r && r.estimated ? ' <span class="nx-est" title="Filled in from other charts">est.</span>' : ''; }

  /* ---------- (a) Value pie: one player ---------- */
  function renderPie(p, animate) {
    var parts = snap.charts.map(function (s) { return { s: s, v: p.sources[s] ? p.sources[s].adjusted : null }; });
    var sum = parts.reduce(function (a, g) { return a + (num(g.v) ? g.v : 0); }, 0);
    var R = 70, C = 2 * Math.PI * R, start = 0, GAP = 1.5;
    var segs = parts.map(function (g, i) {
      var share = num(g.v) && sum > 0 ? g.v / sum : 0;
      var len = share * C;
      var seg = { s: g.s, i: i, share: share, len: Math.max(len - GAP, 0.1), off: -start, v: g.v };
      start += len;
      return seg;
    });
    var n = snap.charts.length;
    $('pie-title').textContent = 'What makes up ' + p.name + '’s ' + f1(p.ddf);
    $('pie-chart').innerHTML = '<svg viewBox="0 0 200 200" class="nx-donut" role="img" aria-labelledby="pie-svg-title pie-svg-desc">' +
      '<title id="pie-svg-title">Each chart’s share of ' + esc(p.name) + '’s DDF Value</title>' +
      '<desc id="pie-svg-desc">' + esc(segs.map(function (g) { return label(g.s) + ' ' + (num(g.v) ? trim((tenths(g.v) / (10 * n)).toFixed(3)) : 'not priced') + ' (' + pct(g.share) + ')'; }).join(', ')) + '. Total ' + f1(p.ddf) + '.</desc>' +
      '<g transform="rotate(-90 100 100)">' + segs.filter(function (g) { return g.share > 0; }).map(function (g) {
        return '<circle cx="100" cy="100" r="' + R + '" fill="none" stroke="' + COLORS[g.i % COLORS.length] + '" stroke-width="36" data-len="' + g.len.toFixed(2) + '"' +
          ' stroke-dasharray="' + (animate ? '0 ' + C.toFixed(2) : g.len.toFixed(2) + ' ' + C.toFixed(2)) + '" stroke-dashoffset="' + g.off.toFixed(2) + '"></circle>';
      }).join('') + '</g>' +
      '<text x="100" y="98" text-anchor="middle" class="nx-donut-val">' + f1(p.ddf) + '</text>' +
      '<text x="100" y="120" text-anchor="middle" class="nx-donut-cap">DDF Value</text></svg>';
    var tSum = snap.charts.reduce(function (a, s) { return a + (p.sources[s] && num(p.sources[s].adjusted) ? tenths(p.sources[s].adjusted) : 0); }, 0);
    $('pie-table').innerHTML = '<caption class="nx-sr">' + esc(p.name) + ': each chart’s contribution to DDF Value</caption>' +
      '<thead><tr><th scope="col">Chart</th><th scope="col">Adjusted</th><th scope="col">÷ ' + n + ' = contribution</th><th scope="col">Share</th></tr></thead><tbody>' +
      segs.map(function (g) {
        var r = p.sources[g.s];
        return '<tr data-src="' + g.s + '"><th scope="row"><span class="nx-sw" style="background:' + COLORS[g.i % COLORS.length] + '"></span>' + esc(label(g.s)) + estTag(r) + '</th><td class="nx-n">' + f1(g.v) + '</td><td class="nx-n">' + (num(g.v) ? trim((tenths(g.v) / (10 * n)).toFixed(3)) : DASH) + '</td><td class="nx-n">' + pct(g.share) + '</td></tr>';
      }).join('') +
      '</tbody><tfoot><tr><th scope="row">DDF Value</th><td class="nx-n">' + trim((tSum / 10).toFixed(1)) + '</td><td class="nx-n">' + (inDdf(p) ? trim(shownMean(p).toFixed(3)) : f1(p.ddf)) + '</td><td class="nx-n">100%</td></tr></tfoot>';
    $('pie-formula').textContent = 'DDF Value = ' + formula(p);
    var round = inDdf(p) && !tiesOut(p);
    $('pie-round').textContent = round ? ROUNDING_NOTE : '';
    $('pie-round').hidden = !round;
    $('pie-trace').href = link('trace', p.player_key);
    $('pie-dd').textContent = p.name + ' is #' + p.rank + ' by DDF Value at these settings.';
    if (animate) requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Array.prototype.forEach.call($('pie-chart').querySelectorAll('circle'), function (c, i) {
          c.style.transition = 'stroke-dasharray .7s cubic-bezier(.2,.7,.2,1) ' + (i * 0.12) + 's';
          c.setAttribute('stroke-dasharray', c.getAttribute('data-len') + ' ' + C.toFixed(2));
        });
      });
    });
  }

  /* ---------- (a2) Health check: does every source add up to the value pie? ---------- */
  var STATUS = { pass: 'Pass', flag: 'Look', info: 'Info' };
  var CHECK_NAME = { reconcile: 'Indexed values vs DDF Value' };
  function checkReason(c) {
    return String(c.reason || '').replace(/Player values add up/g, 'Values add up').replace(/Rescaled/g, 'Indexed');
  }
  function renderHealth() {
    var data = LE().health(snap);
    var host = $('hc-body');
    if (!data) { host.innerHTML = '<p class="nx-hint">The checks could not be computed.</p>'; return; }
    var flagged = data.checks.filter(function (c) { return c.status === 'flag'; }).length;
    $('hc-sum').textContent = flagged ? flagged + ' of ' + data.checks.length + ' checks need a look.' : 'All ' + data.checks.length + ' checks pass or are for information.';
    var rows = data.rows;
    var src = function (r) { return esc(label(r.src)); };
    var POS = ['QB', 'RB', 'WR', 'TE'];
    var totalsFlag = (data.checks.filter(function (c) { return c.id === 'totals'; })[0] || {}).sources || [];
    var html = '<ul class="nx-checks">' + data.checks.map(function (c) {
      return '<li class="nx-check is-' + esc(c.status) + '"><span class="nx-pill">' + (STATUS[c.status] || esc(c.status)) + '</span><b>' + esc(CHECK_NAME[c.id] || c.name) + '</b><span>' + esc(checkReason(c)) + '</span></li>';
    }).join('') + '</ul>';
    html += '<h3 class="nx-h3">Do sources agree on total value?</h3><p class="nx-hint">Each row is a source. Starter and bench totals should be similar across sources; the total is the value pie (' + f1(data.pie) + ') by construction.</p>' +
      '<div class="nx-scroll" tabindex="0" role="region" aria-label="Totals by source"><table class="nx-table nx-hc"><thead><tr><th scope="col">Source</th><th scope="col">Starters</th><th scope="col">Bench</th><th scope="col">Total</th><th scope="col">Per roster slot</th></tr></thead><tbody>' +
      rows.map(function (r) {
        var off = totalsFlag.indexOf(r.src) >= 0 || Math.abs(r.totalAdjusted - data.pie) > 0.5;
        return '<tr data-src="' + esc(r.src) + '"><th scope="row">' + src(r) + '</th><td class="nx-n">' + f1(r.starterTotal) + '</td><td class="nx-n">' + f1(r.benchTotal) + '</td><td class="nx-n' + (off ? ' nx-off' : '') + '">' + f1(r.totalAdjusted) + '</td><td class="nx-n">' + (num(r.perRosterable) ? r.perRosterable.toFixed(2) : DASH) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    html += '<details class="nx-details"><summary>Do sources agree by position?</summary><p class="nx-hint">Within each position, starter values should agree within 24%. QB is shown for reference and never flagged. The budget is the position’s share of the value pie.</p>' +
      POS.map(function (pos, pi) {
        return '<h4 class="nx-h4">' + pos + '</h4><div class="nx-scroll" tabindex="0" role="region" aria-label="' + pos + ' by source"><table class="nx-table nx-hc"><thead><tr><th scope="col">Source</th><th scope="col">Starters</th><th scope="col">Bench</th><th scope="col">Total</th><th scope="col">Budget</th></tr></thead><tbody>' +
          rows.map(function (r) {
            var d = r.positions[pi];
            return '<tr><th scope="row">' + src(r) + '</th><td class="nx-n">' + f1(d.starterAdj) + '</td><td class="nx-n">' + f1(d.benchAdj) + '</td><td class="nx-n">' + f1(d.posAdj) + '</td><td class="nx-n">' + f1(d.budget) + '</td></tr>';
          }).join('') + '</tbody></table></div>';
      }).join('') + '</details>';
    html += '<details class="nx-details"><summary>Are any players filled in?</summary><p class="nx-hint">A filled-in player is one the source did not list, so the engine gave him a value from the other charts. Each cell is filled-in players out of the rostered slots at that position; over 75% needs a look.</p>' +
      '<div class="nx-scroll" tabindex="0" role="region" aria-label="Filled-in players by source"><table class="nx-table nx-hc"><thead><tr><th scope="col">Source</th>' + POS.map(function (p) { return '<th scope="col">' + p + '</th>'; }).join('') + '<th scope="col">All</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr><th scope="row">' + src(r) + '</th>' + r.positions.map(function (d) {
          return '<td class="nx-n' + (d.estShare > 0.75 ? ' nx-off' : '') + '">' + d.nEstimated + ' of ' + d.rostered + '</td>';
        }).join('') + '<td class="nx-n">' + r.totalEstimated + ' of ' + r.totalRostered + '</td></tr>';
      }).join('') + '</tbody></table></div></details>';
    host.innerHTML = html;
  }

  /* ---------- (b) Source build-up ---------- */
  function curveSvg(model) {
    var stages = model.family === 'chart' ? ['indexed', 'adjusted'] : ['adjusted'];
    var pts = model.rows.slice(0, Math.max(state.limit, PAGE));
    var max = 0;
    stages.forEach(function (st) { pts.forEach(function (r) { if (num(r[st]) && r[st] > max) max = r[st]; }); });
    if (!pts.length || !max) return '';
    var W = 640, H = 180, L = 34, B = 22, n = pts.length;
    var x = function (i) { return L + (n === 1 ? 0 : i * (W - L - 6) / (n - 1)); };
    var y = function (v) { return 6 + (H - B - 6) * (1 - v / max); };
    var line = function (st) {
      var d = pts.map(function (r, i) { return num(r[st]) ? (x(i).toFixed(1) + ',' + y(r[st]).toFixed(1)) : null; }).filter(Boolean).join(' ');
      return '<polyline points="' + d + '" fill="none" stroke="' + (st === 'adjusted' ? '#0f5139' : '#8fb9a3') + '" stroke-width="2"' + (st === 'indexed' ? ' stroke-dasharray="5 4"' : '') + '></polyline>';
    };
    return '<svg class="nx-curve" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(model.label + ': ' + stages.join(' and ') + ' value by the source’s own rank, top ' + n) + '">' +
      '<line x1="' + L + '" y1="' + (H - B) + '" x2="' + W + '" y2="' + (H - B) + '" stroke="#c9d1cb"></line>' +
      '<text x="' + (L - 6) + '" y="12" text-anchor="end" class="nx-ax">' + Math.round(max) + '</text><text x="' + (L - 6) + '" y="' + (H - B) + '" text-anchor="end" class="nx-ax">0</text>' +
      '<text x="' + L + '" y="' + (H - 6) + '" class="nx-ax">rank 1</text><text x="' + W + '" y="' + (H - 6) + '" text-anchor="end" class="nx-ax">rank ' + n + '</text>' +
      stages.map(line).join('') + '</svg>' +
      '<p class="nx-legend-line">' + (stages.length > 1 ? '<span><i class="nx-key nx-key-dash"></i>Indexed</span>' : '') + '<span><i class="nx-key"></i>Adjusted</span></p>';
  }
  function renderBuildUp() {
    var src = state.source, pos = state.position;
    var model = LE().buildUp(snap, src, pos);
    Array.prototype.forEach.call($('bu-sources').querySelectorAll('a'), function (a) {
      if (a.getAttribute('data-src') === src) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
      a.href = link('build-up', a.getAttribute('data-src') + (pos !== 'ALL' ? '/' + pos : ''));
    });
    Array.prototype.forEach.call($('bu-positions').querySelectorAll('a'), function (a) {
      var p = a.getAttribute('data-pos');
      if (p === pos) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
      a.href = link('build-up', src + (p !== 'ALL' ? '/' + p : ''));
    });
    var name = label(src);
    $('bu-title').textContent = 'Source build-up: ' + name + (pos !== 'ALL' ? ', ' + pos : '');
    var url = LE().sourceUrl(src, pos);
    $('bu-link').innerHTML = url ? '<a class="nx-link" href="' + esc(url) + '" target="_blank" rel="noopener">Open ' + esc(name) + '’s own page (new tab)</a>' : '';
    if (!model || !model.hasData) {
      $('bu-explain').innerHTML = '';
      $('bu-curve').innerHTML = '';
      $('bu-worked').innerHTML = '';
      $('bu-table').innerHTML = '';
      $('bu-meta').textContent = name + ' has no values at these settings this week' + (model && model.status ? ' (' + model.status + ')' : '') + '.';
      $('bu-more').hidden = true;
      return;
    }
    var chart = model.family === 'chart';
    var ex = model.rows[0];
    var exP = byKey[ex.key];
    var srcMeta = snap.sources[src];
    var explain = chart
      ? '<li><b>Published</b><span>The source’s own units. ' + esc(name) + ' lists ' + esc(ex.name) + ' at ' + fPub(src, ex.published) + '.</span></li>' +
        '<li><b>Indexed</b><span>Put on one scale: published × one factor for the chart (' + fFactor(srcMeta && srcMeta.factor) + '), so the chart lines up with DDF Value. ' + fPub(src, ex.published) + ' → ' + f1(ex.indexed) + '.</span></li>'
      : '<li><b>Projected points</b><span>' + esc(name) + ' projects ' + esc(ex.name) + ' at ' + fPts(ex.published) + ' points a game. A projection is not indexed to another chart.</span></li>';
    explain += '<li><b>Adjusted</b><span>For your league settings: valued at starter or bench level by where the player ranks at his position across the league (roster sizes and team count), rescaled so the source’s total is the league’s value pie (' + esc(pieText()) + '). ' + (chart ? f1(ex.indexed) + ' → ' : '') + f1(ex.adjusted) + '.</span></li>';
    explain += chart
      ? '<li><b>DDF Value</b><span>The average of the ' + chartWord() + ' charts’ adjusted values. ' + (exP ? esc(ex.name) + ': ' + esc(formula(exP)) + '.' : '') + '</span></li>'
      : '<li><b>DDF Value</b><span>Projections are an alternate view: they are not in DDF Value, which averages the ' + chartWord() + ' trade charts.</span></li>';
    $('bu-explain').innerHTML = explain;
    $('bu-curve').innerHTML = curveSvg(model);
    renderWorked(model);
    var rows = model.rows.slice(0, state.limit);
    var others = snap.charts.filter(function (s) { return s !== src; });
    var head = '<tr><th scope="col">#</th><th scope="col">Player</th><th scope="col">Pos</th><th scope="col">Role</th>' +
      (chart ? '<th scope="col">Published</th><th scope="col">Indexed</th>' : '<th scope="col">Projected points / game</th>') +
      '<th scope="col">Adjusted</th>' + (chart ? '<th scope="col"><span class="nx-th2">Other charts, adjusted</span><span class="nx-th3">' + esc(others.map(label).join(' · ')) + '</span></th>' : '') + '<th scope="col">DDF Value</th></tr>' +
      '<tr class="nx-explain-row"><td></td><td>What each column is</td><td></td><td></td>' + (chart ? '<td>' + esc(name) + '’s own units</td><td>On one scale</td>' : '<td>' + esc(name) + '’s projection</td>') +
      '<td>For your league</td>' + (chart ? '<td>The other charts</td>' : '') + '<td>Average of ' + chartWord() + '</td></tr>';
    var ROLE = { starter: 'Starter', bench: 'Bench', waiver: 'Waiver' };
    var body = rows.map(function (r) {
      var p = byKey[r.key];
      var oth = p ? others.map(function (s) { return p.sources[s] ? f1(p.sources[s].adjusted) : DASH; }).join(' · ') : DASH;
      return '<tr data-key="' + esc(r.key) + '"><td class="nx-n nx-muted">' + r.rank + '</td><th scope="row">' + esc(r.name) + (r.estimated ? ' <span class="nx-est" title="Filled in from other charts">est.</span>' : '') + '</th><td>' + esc(r.pos) + '</td><td>' + esc(ROLE[r.role] || r.role || DASH) + '</td>' +
        (chart ? '<td class="nx-n">' + fPub(src, r.published) + '</td><td class="nx-n">' + f1(r.indexed) + '</td>' : '<td class="nx-n">' + fPts(r.published) + '</td>') +
        '<td class="nx-n nx-strong">' + f1(r.adjusted) + '</td>' + (chart ? '<td class="nx-n nx-muted">' + oth + '</td>' : '') +
        '<td class="nx-n nx-ddf">' + (p ? '<a href="' + link('trace', p.player_key) + '" aria-label="Trace ' + esc(r.name) + '’s DDF Value ' + f1(p.ddf) + '">' + f1(p.ddf) + '</a>' : DASH) + '</td></tr>';
    }).join('');
    $('bu-table').innerHTML = '<caption class="nx-sr">' + esc(name) + ' build-up, ' + esc(settingsLine(snap.settings)) + '</caption><thead>' + head + '</thead><tbody>' + body + '</tbody>' +
      '<tfoot><tr><td></td><th scope="row">Totals, all ' + model.shown + ' players</th><td></td><td></td>' +
      (chart ? '<td class="nx-n">' + fPub(src, sumListed(model)) + '</td><td class="nx-n">' + f1(model.totals.indexed) + '</td>' : '<td></td>') +
      '<td class="nx-n">' + f1(model.totals.adjusted) + '</td>' + (chart ? '<td></td>' : '') + '<td></td></tr></tfoot>';
    $('bu-meta').textContent = (pos === 'ALL' ? 'Adjusted total = the value pie, ' + fInt(snap.pie) + '. ' : '') +
      model.shown + ' players, ' + model.estimatedCount + ' filled in from other charts (marked est.). Showing ' + rows.length + ' of ' + model.shown + ' in ' + name + '’s order.' + (chart ? ' The published total counts only the players ' + name + ' lists.' : '') + ' A dash means the engine has no value there; it is never zero.' +
      (model.status ? ' Left out of DDF Value this week: ' + model.status + '.' : '');
    var more = $('bu-more');
    more.hidden = model.shown <= state.limit;
    more.textContent = 'Show ' + Math.min(PAGE, model.shown - state.limit) + ' more';
  }
  /* Projection sources: the worked path from projected points to the adjusted value, from the engine's own
     readouts (DDFAuditSource row.trace), as the old Source build-up showed it. */
  function renderWorked(model) {
    var host = $('bu-worked');
    if (!model || model.family !== 'projection' || !model.rows.length) { host.innerHTML = ''; return; }
    var r = model.rows.filter(function (x) { return x.key === state.worked; })[0] || model.rows[0];
    var t = r.trace || {};
    var v = function (n, kind) {
      if (!num(n)) return DASH;
      return kind === 'pct' ? (n * 100).toFixed(1) + '%' : kind === 'rate' ? n.toFixed(4) : kind === 'ppg' ? n.toFixed(2) + ' points a game' : f1(n);
    };
    var row = function (labelText, n, kind) { return '<tr><th scope="row">' + esc(labelText) + '</th><td class="nx-n">' + v(n, kind) + '</td></tr>'; };
    host.innerHTML = '<details class="nx-details" open><summary>From projection to adjusted value, one player</summary>' +
      '<div class="nx-pick"><label for="bu-worked-pick">Player</label><select id="bu-worked-pick" class="nx-select">' +
      model.rows.map(function (x) { return '<option value="' + esc(x.key) + '"' + (x.key === r.key ? ' selected' : '') + '>' + esc(x.name + ' (' + x.pos + ')') + '</option>'; }).join('') + '</select></div>' +
      '<div class="nx-scroll"><table class="nx-table nx-worked"><caption class="nx-sr">' + esc(r.name) + ': projection to adjusted value</caption><tbody>' +
      row('Projected points', r.published, 'ppg') +
      row(r.pos + ' waiver line', t.waiver, 'ppg') + row(r.pos + ' starter line', t.starterLine, 'ppg') +
      row('Value above waivers', t.aboveWaivers, 'ppg') +
      row('Availability', t.availability, 'pct') + row('Chance above the starter line', t.startWorthy, 'pct') + row('Expected lineup share', t.lineupShare, 'pct') +
      row('Starter part', t.starterPart) + row('Fill-in part', t.fillInPart) +
      row('Starter rate', t.starterRate, 'rate') + row('Fill-in rate', t.fillInRate, 'rate') +
      row('Adjusted = starter part × starter rate + fill-in part × fill-in rate', r.adjusted) +
      '</tbody></table></div><p class="nx-hint">The league’s roster sets the waiver line and the starter line at his position. The rates fund each position’s starter and fill-in budget from the value pie (' + esc(pieText()) + '). A dash means the engine does not expose that readout.</p></details>';
    $('bu-worked-pick').addEventListener('change', function () { state.worked = this.value; renderWorked(model); $('bu-worked-pick').focus(); });
  }

  function sumListed(model) {
    return model.rows.reduce(function (t, r) { return t + (!r.estimated && num(r.published) ? r.published : 0); }, 0);
  }

  /* ---------- (c) Trace ---------- */
  function renderTrace(p) {
    $('tr-name').textContent = p.name + ' · ' + p.pos;
    $('tr-big').textContent = f1(p.ddf);
    $('tr-sub').textContent = 'DDF Value · #' + p.rank + ' by DDF Value · ' + settingsLine(snap.settings);
    $('tr-step1').textContent = chartWord().replace(/^./, function (c) { return c.toUpperCase(); }) + ' charts publish a value, it is indexed onto one scale, then adjusted for your league';
    $('tr-step2').textContent = 'Average of the ' + chartWord() + ' adjusted values';
    $('tr-pub').innerHTML = '<caption class="nx-sr">' + esc(p.name) + ': published, indexed and adjusted by chart</caption><thead><tr><th scope="col">Chart</th><th scope="col">Published</th><th scope="col" class="nx-fac">× factor</th><th scope="col">Indexed</th><th scope="col">Adjusted</th></tr></thead><tbody>' +
      snap.charts.map(function (s) {
        var r = p.sources[s];
        return '<tr data-src="' + s + '"><th scope="row">' + esc(label(s)) + estTag(r) + '</th><td class="nx-n">' + fPub(s, r && r.published) + '</td><td class="nx-n nx-muted nx-fac">' + fFactor(snap.sources[s].factor) + '</td><td class="nx-n">' + f1(r && r.indexed) + '</td><td class="nx-n nx-strong">' + f1(r && r.adjusted) + '</td></tr>';
      }).join('') + '</tbody>';
    $('tr-avg').textContent = formula(p);
    var round = inDdf(p) && !tiesOut(p);
    $('tr-round').textContent = round ? ROUNDING_NOTE : '';
    $('tr-round').hidden = !round;
    $('tr-pin').textContent = snapshotLine() + ' · ' + settingsLine(snap.settings) + ' · ' + overridesLine();
    $('tr-ov').innerHTML = p.overrideSet ? 'Your override for ' + esc(p.name) + ' is ' + f1(p.override) + '. It replaces DDF Value on the other pages; this trace shows the model’s own value. <a href="values.html#overrides">See your overrides</a>' : '';
    $('tr-ov').hidden = !p.overrideSet;
    $('tr-llm').textContent = llmText(p);
    $('tr-status').textContent = '';
  }

  /* ---------- (d) Glossary: examples filled from the engine ---------- */
  function fillGlossary() {
    var top = snap.players[0];
    if (!top) return;
    var cbs = top.sources.cbs, fc = top.sources.fantasycalc;
    var set = function (k, text) { Array.prototype.forEach.call(document.querySelectorAll('[data-gl="' + k + '"]'), function (el) { el.textContent = text; }); };
    set('published', cbs && fc && !cbs.estimated && !fc.estimated ? ' Right now CBS Sports lists ' + top.name + ' at ' + fPub('cbs', cbs.published) + ' and FantasyCalc lists him at ' + fPub('fantasycalc', fc.published) + '.' : '');
    set('pie', ' (' + pieText() + ' at ' + settingsLine(snap.settings) + ')');
    var vaw = top.sources && snap.inspection.rows[String(top.player_key)];
    var vals = vaw && vaw.vorp ? snap.charts.map(function (s) { return vaw.vorp[s]; }).filter(num) : [];
    set('vaw', vals.length === snap.charts.length ? ' (right now ' + top.name + ': ' + f1(vals.reduce(function (a, b) { return a + b; }, 0) / vals.length) + ' above waivers, DDF Value ' + f1(top.ddf) + ')' : '');
  }

  /* ---------- (e) Full value logic (the engine-built explainer, framed) ---------- */
  function showLogic() {
    var frame = $('logic-frame');
    if (!frame.getAttribute('src')) frame.setAttribute('src', frame.getAttribute('data-src'));
  }
  window.addEventListener('message', function (e) {
    var d = e.data;
    var frame = $('logic-frame');
    if (frame && e.source === frame.contentWindow && d && d.type === 'ddf-value-logic-height' && d.height > 0) frame.style.height = Math.ceil(d.height) + 'px';
  });

  /* ---------- routing ---------- */
  function parse() {
    var raw = location.hash.replace(/^#numbers\/?/, '');
    var qAt = raw.indexOf('?');
    var path = qAt >= 0 ? raw.slice(0, qAt) : raw;
    var query = qAt >= 0 ? raw.slice(qAt) : '';
    var parts = path.split('/');
    var view = VIEWS.indexOf(parts[0]) >= 0 ? parts[0] : 'pie';
    return { view: view, arg: decodeURIComponent(parts[1] || ''), arg2: decodeURIComponent(parts[2] || ''), query: query, canonical: VIEWS.indexOf(parts[0]) >= 0 };
  }
  function syncSubTabs() {
    $('nx-tab-pie').href = link('pie', state.player || '');
    $('nx-tab-build-up').href = link('build-up', state.source + (state.position !== 'ALL' ? '/' + state.position : ''));
    $('nx-tab-trace').href = link('trace', state.player || '');
    $('nx-tab-glossary').href = link('glossary');
    $('nx-tab-logic').href = link('logic');
    setTabs($('nx-tabs'), 'nx-tab-' + state.view);
    VIEWS.forEach(function (v) { $('nx-view-' + v).hidden = v !== state.view; });
    $('nx-settings-wrap').hidden = state.view === 'glossary' || state.view === 'logic';
  }
  function setBusy(on) {
    $('panel-numbers').setAttribute('aria-busy', String(on));
    $('nx-loading').hidden = !on;
  }

  function ensureLoaded(query) {
    var want = querySettings(query);
    var key = want ? settingsQuery(Object.assign({ scoring: '', teams: 0, roster: {} }, want)) : '';
    if (snap && (!want || key === loadedQuery)) return Promise.resolve(snap);
    if (loading && loading.key === key) return loading.p;
    setBusy(true);
    var p = LE().load(want).then(function (s) {
      snap = s;
      loadedQuery = key || settingsQuery(s.settings);
      byKey = {}; byName = {};
      s.players.forEach(function (pl) { byKey[pl.player_key] = pl; byName[pl.name.toLowerCase()] = pl; });
      onSnapshot();
      setBusy(false);
      return s;
    }, function (err) {
      setBusy(false);
      console.warn('Numbers: ', err);
      $('nx-error').hidden = false;
      throw err;
    });
    loading = { key: key, p: p };
    return p;
  }

  function onSnapshot() {
    var st = snap.settings;
    state.query = settingsQuery(st);
    $('nx-snapshot').textContent = snapshotLine();
    $('nx-settings').textContent = settingsLine(st) + ' · ' + overridesLine();
    $('nx-method').textContent = 'DDF Value is the average of the ' + chartWord() + ' published trade charts (' + snap.charts.map(label).join(', ') + '), each adjusted to your league: how much more a player is worth than a freely available one at his position, valued at starter or bench level by where he ranks across the league.';
    $('nx-sources').textContent = 'The analyst charts are CBS Sports, USA Today and FantasyPros; the live market is FantasyCalc. A chart that is held this week is left out of the average, never counted as zero.';
    $('set-scoring').value = st.scoring;
    $('set-teams').value = String(st.teams);
    $('set-sf').checked = st.superflex;
    fillPickers();
    fillGlossary();
    if (!state.player || !byKey[state.player]) state.player = snap.players.length ? snap.players[0].player_key : null;
    lastRendered = '';
  }

  var lastRendered = '';
  function route() {
    if (!isNumbersHash()) { setArea('writing'); return; }
    setArea('numbers');
    var r = parse();
    state.view = r.view;
    if (r.view === 'glossary') { syncSubTabs(); showGlossary(r.arg); return; }
    if (r.view === 'logic') { syncSubTabs(); showLogic(); $('nx-live').textContent = 'Full value logic selected.'; return; }
    syncSubTabs();
    ensureLoaded(r.query).then(function () { if (parse().view === r.view) render(r); }, function () {});
  }
  function render(r) {
    if (!r.canonical) { history.replaceState(null, '', link('pie', state.player || '')); r = parse(); }
    var prev = { view: lastView, player: state.player, source: state.source, position: state.position };
    if ((r.view === 'pie' || r.view === 'trace') && r.arg) {
      if (byKey[r.arg]) state.player = +r.arg;
      else if (state.player) { $('nx-live').textContent = 'That player has no DDF Value at these settings. Showing ' + byKey[state.player].name + '.'; history.replaceState(null, '', link(r.view, state.player)); r = parse(); }
    }
    if (r.view === 'build-up') {
      var known = LE().buildUpSources().map(function (s) { return s.key; });
      if (r.arg && known.indexOf(r.arg) >= 0) state.source = r.arg;
      else if (r.arg) { history.replaceState(null, '', link('build-up', state.source)); r = parse(); }
      var pos = r.arg2 && POSITIONS.indexOf(r.arg2.toUpperCase()) >= 0 ? r.arg2.toUpperCase() : 'ALL';
      if (pos !== state.position || state.source !== prev.source) state.limit = PAGE;
      state.position = pos;
    }
    if (!r.query) history.replaceState(null, '', location.hash + state.query);
    syncSubTabs();
    var p = byKey[state.player];
    var key = state.view + '|' + loadedQuery + '|' + (state.view === 'build-up' ? state.source + state.position + state.limit : state.player);
    if (key === lastRendered) return;
    lastRendered = key;
    lastView = state.view;
    if (state.view === 'pie' && p) {
      $('pie-pick').value = p.name; quickPicks($('pie-quick'), 'pie');
      renderPie(p, !calm());
      renderHealth();
    } else if (state.view === 'trace' && p) {
      $('tr-pick').value = p.name; quickPicks($('tr-quick'), 'trace');
      renderTrace(p);
    } else if (state.view === 'build-up') {
      renderBuildUp();
    }
    var changed = state.view !== prev.view || state.player !== prev.player || state.source !== prev.source || state.position !== prev.position;
    if (changed || !$('nx-live').textContent) {
      $('nx-live').textContent = state.view === 'build-up'
        ? 'Source build-up: ' + label(state.source) + (state.position !== 'ALL' ? ', ' + state.position : '') + ' selected.'
        : p ? (state.view === 'pie' ? 'Value pie: ' : 'Trace: ') + p.name + ' selected, DDF Value ' + f1(p.ddf) + '.' : '';
    }
  }
  var lastView = null;

  function showGlossary(term) {
    var prevView = lastView;
    lastView = 'glossary';
    /* Source rename (Jeremy, 2026-11-06): the old Market term now lives at Analyst charts; old links still land on it. */
    if (term === 'market') { term = 'analyst-charts'; history.replaceState(null, '', '#numbers/glossary/analyst-charts' + state.query); }
    var el = term ? $('g-' + term) : null;
    if (term && !el) history.replaceState(null, '', '#numbers/glossary' + state.query);
    Array.prototype.forEach.call($('nx-view-glossary').querySelectorAll('.nx-term'), function (t) { t.classList.toggle('is-current', t === el); });
    var key = 'glossary|' + (el ? term : '');
    if (key === lastRendered) return;
    lastRendered = key;
    if (el) {
      el.scrollIntoView({ block: 'start', behavior: calm() ? 'auto' : 'smooth' });
      el.focus({ preventScroll: true });
      $('nx-live').textContent = 'Glossary: ' + el.querySelector('dt').textContent + '.';
    } else if (prevView !== 'glossary') {
      $('nx-live').textContent = 'Glossary selected.';
    }
  }

  function copy(text, btn) {
    btn.focus();
    var status = $('tr-status');
    if (window.DDF && DDF.copyText) return DDF.copyText(text, status, 'Copied.');
    return navigator.clipboard.writeText(text).then(function () { status.textContent = 'Copied.'; }, function () { status.textContent = 'Copy did not work here. Select the text below instead.'; });
  }

  function changeSettings() {
    if (!snap) return;
    var r = Object.assign({}, snap.settings.roster);
    r.SUPERFLEX = $('set-sf').checked ? 1 : 0;
    var q = settingsQuery({ scoring: $('set-scoring').value, teams: Number($('set-teams').value), roster: r });
    var cur = parse();
    var arg = cur.view === 'build-up' ? state.source + (state.position !== 'ALL' ? '/' + state.position : '') : (cur.view === 'pie' || cur.view === 'trace') ? state.player : '';
    location.hash = '#numbers/' + cur.view + (arg ? '/' + arg : '') + q;
  }

  function init() {
    wireTabKeys($('learn-area-tabs'));
    wireTabKeys($('nx-tabs'));
    $('bu-sources').innerHTML = LE() ? LE().buildUpSources().map(function (s) { return '<a class="nx-chip" href="#numbers/build-up/' + s.key + '" data-src="' + s.key + '">' + esc(s.label) + '</a>'; }).join('') : '';
    $('bu-positions').innerHTML = POSITIONS.map(function (p) { return '<a class="nx-chip" href="#numbers/build-up/cbs/' + p + '" data-pos="' + p + '">' + (p === 'ALL' ? 'All' : p) + '</a>'; }).join('');
    wirePicker($('pie-pick'), 'pie');
    wirePicker($('tr-pick'), 'trace');
    $('bu-more').addEventListener('click', function () { state.limit += PAGE; lastRendered = ''; renderBuildUp(); lastRendered = 'build-up|' + loadedQuery + '|' + state.source + state.position + state.limit; });
    $('tr-copy-llm').addEventListener('click', function () { copy(llmText(byKey[state.player]), this); });
    $('tr-copy-link').addEventListener('click', function () { copy(permalink('trace', state.player), this); });
    $('tr-copy-json').addEventListener('click', function () { copy(jsonFor(byKey[state.player]), this); });
    ['set-scoring', 'set-teams', 'set-sf'].forEach(function (id) { $(id).addEventListener('change', changeSettings); });
    window.addEventListener('hashchange', route);
    /* The reader's league or overrides changed elsewhere (another tab): read the engine again. */
    if (LE()) LE().onRebuild(function () { snap = null; loadedQuery = null; loading = null; lastRendered = ''; if (isNumbersHash()) route(); });
    route();
  }
  window.DDFNumbers = { isNumbersHash: isNumbersHash, snapshot: function () { return snap; } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
