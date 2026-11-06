/* Learn > How we get our numbers.
   Renders Value pie, Source build-up and Trace from learn/data/lineage-week9.json
   (real numbers captured from the DDF MCP server; see learn/data/README.md).
   Routes: #numbers/pie/<player_key>, #numbers/build-up/<source>, #numbers/trace/<player_key>,
   #numbers/glossary[/<term>] (static terms in learn.html, ids g-<term>; works before the data loads). */
(function () {
  'use strict';
  var DATA_URL = 'learn/data/lineage-week9.json';
  var VIEWS = ['pie', 'build-up', 'trace', 'glossary'];
  var DEFAULT_PLAYER = 2227; // Jahmyr Gibbs
  var DEFAULT_SOURCE = 'cbs';
  var COLORS = ['#0f5139', '#2f8f6b', '#6bb394', '#b5dcc8'];
  var BUILDUP_SHORT = 20;

  var data = null, byKey = {}, byName = {};
  var state = { view: 'pie', player: DEFAULT_PLAYER, source: DEFAULT_SOURCE, showAll: false };
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var calm = function () { return !window.matchMedia || !window.matchMedia('(prefers-reduced-motion: no-preference)').matches; };
  var isNumbersHash = function () { return /^#numbers(\/|$)/.test(location.hash); };

  /* ---------- number formatting (display precision follows the tool) ---------- */
  var f1 = function (n) { return Number(n).toFixed(1); };
  var fPub = function (src, n) { return src === 'fantasycalc' ? Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 }) : f1(n); };
  var fDdf = function (n) { return Number(n).toFixed(1); };
  var tenths = function (n) { return Math.round(Number(n) * 10); };
  var trim = function (s) { return s.replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '.0'); };
  /* exact mean of the four shown (rounded) adjusted values: sum of tenths / 40 */
  function meanText(p) {
    var t = data.basis.reduce(function (a, s) { return a + tenths(p.sources[s].adjusted); }, 0);
    return trim((t / 40).toFixed(3));
  }
  var quarter = function (n) { return trim((tenths(n) / 40).toFixed(3)); };
  var label = function (s) { return data.sources[s].label; };

  /* ---------- formula + LLM text ---------- */
  function formula(p) {
    var parts = data.basis.map(function (s) { return f1(p.sources[s].adjusted); });
    var m = meanText(p);
    return '(' + parts.join(' + ') + ') ÷ 4 = ' + m + (p.check.ties_out ? ' → ' + fDdf(p.ddf_value) : '; DDF Value ' + fDdf(p.ddf_value));
  }
  var ROUNDING_NOTE = 'The adjusted values are shown rounded to one decimal; DDF Value averages the unrounded values.';

  function settingsLine() {
    var st = data.settings;
    return st.scoring_label + ', ' + st.teams + ' teams, roster ' + st.roster_label + (st.superflex ? ', superflex' : ', no superflex');
  }
  function snapshotLine() { return 'Week ' + data.week + ' · as of ' + data.as_of + ' · build ' + data.build; }
  function permalink(view, arg) { return location.href.split('#')[0] + '#numbers/' + view + '/' + arg; }

  function llmText(p) {
    var inputs = data.basis.map(function (s) {
      var r = p.sources[s];
      return label(s) + ' published ' + fPub(s, r.published).replace(/,/g, '') + ' → indexed ' + f1(r.indexed) + ' → adjusted ' + f1(r.adjusted) + (r.estimated ? ' (filled in from other charts)' : '');
    }).join('; ');
    var m = meanText(p);
    return 'DDF Value, ' + p.name + ' (' + p.pos + '), ' + settingsLine() + ', week ' + data.week + ', as of ' + data.as_of + ', build ' + data.build + '.\n' +
      'Inputs: ' + inputs + '.\n' +
      'Rule: DDF Value = mean of four adjusted trade charts = (' + data.basis.map(function (s) { return f1(p.sources[s].adjusted); }).join(' + ') + ') / 4 = ' + m +
      (p.check.ties_out ? ', shown as ' + fDdf(p.ddf_value) + '.' : '; the tool shows ' + fDdf(p.ddf_value) + ' because it averages the unrounded adjusted values.') +
      ' Overrides: ' + data.overrides + '.\n' +
      'Indexed = published x one factor per chart (indexed total / published total): ' +
      data.basis.map(function (s) { return label(s) + ' ' + data.sources[s].index_factor.value; }).join(', ') + '.\n' +
      'Adjusted totals per chart = value pie ' + data.value_pie.points + ' = ' + data.value_pie.formula + '.\n' +
      'Trace: ' + permalink('trace', p.player_key) + '\n' +
      'Live values for these settings: ' + data.site_url;
  }
  function jsonFor(p) {
    var srcMeta = {};
    data.basis.forEach(function (s) {
      var m = data.sources[s];
      srcMeta[s] = { label: m.label, players_listed: m.players_listed, filled_in: m.filled_in, totals: m.totals, index_factor: m.index_factor };
    });
    return JSON.stringify({
      snapshot: { as_of: data.as_of, week: data.week, build: data.build, settings: data.settings, overrides: data.overrides, rule: data.rule, value_pie: data.value_pie, captured: data.captured },
      player: p, sources: srcMeta, permalink: permalink('trace', p.player_key)
    }, null, 2);
  }

  /* ---------- area tabs (Writing | How we get our numbers) ---------- */
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
  function fillPicker(input) {
    var dl = $(input.getAttribute('list'));
    if (dl && !dl.children.length) dl.innerHTML = data.players.map(function (p) { return '<option value="' + esc(p.name) + '">' + esc(p.pos + ' · ' + fDdf(p.ddf_value)) + '</option>'; }).join('');
  }
  function wirePicker(input, view) {
    fillPicker(input);
    var status = $(input.id + '-hint');
    var tryPick = function (final) {
      var p = byName[input.value.trim().toLowerCase()];
      if (p) { status.textContent = ''; if (p.player_key !== state.player || state.view !== view) location.hash = 'numbers/' + view + '/' + p.player_key; return; }
      if (final && input.value.trim()) {
        var q = input.value.trim().toLowerCase();
        var hits = data.players.filter(function (x) { return x.name.toLowerCase().indexOf(q) >= 0; });
        if (hits.length === 1) { input.value = hits[0].name; tryPick(false); return; }
        status.textContent = hits.length ? hits.length + ' players match. Pick one from the list.' : 'No player by that name in the week ' + data.week + ' snapshot.';
      }
    };
    input.addEventListener('input', function () { tryPick(false); });
    input.addEventListener('change', function () { tryPick(true); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); tryPick(true); } });
  }
  function quickPicks(el, view) {
    var keys = [2227, 751, 171, 71, 3716];
    el.innerHTML = keys.filter(function (k) { return byKey[k]; }).map(function (k) {
      return '<a class="nx-chip" href="#numbers/' + view + '/' + k + '"' + (k === state.player ? ' aria-current="true"' : '') + '>' + esc(byKey[k].name) + '</a>';
    }).join('');
  }

  /* ---------- (a) Value pie ---------- */
  function renderPie(p, animate) {
    var sum = data.basis.reduce(function (a, s) { return a + p.sources[s].adjusted; }, 0);
    var R = 70, C = 2 * Math.PI * R, start = 0, GAP = 1.5;
    var segs = data.basis.map(function (s, i) {
      var share = p.sources[s].adjusted / sum;
      var len = share * C;
      var seg = { s: s, i: i, share: share, len: Math.max(len - GAP, 0.1), off: -start };
      start += len;
      return seg;
    });
    $('pie-title').textContent = 'What makes up ' + p.name + '’s ' + fDdf(p.ddf_value);
    var svg = '<svg viewBox="0 0 200 200" class="nx-donut" role="img" aria-labelledby="pie-svg-title pie-svg-desc">' +
      '<title id="pie-svg-title">Each chart’s share of ' + esc(p.name) + '’s DDF Value</title>' +
      '<desc id="pie-svg-desc">' + esc(segs.map(function (g) { return label(g.s) + ' ' + quarter(p.sources[g.s].adjusted) + ' (' + (g.share * 100).toFixed(1) + '%)'; }).join(', ')) + '. Total ' + fDdf(p.ddf_value) + '.</desc>' +
      '<g transform="rotate(-90 100 100)">' + segs.map(function (g) {
        return '<circle cx="100" cy="100" r="' + R + '" fill="none" stroke="' + COLORS[g.i] + '" stroke-width="36" data-len="' + g.len.toFixed(2) + '"' +
          ' stroke-dasharray="' + (animate ? '0 ' + C.toFixed(2) : g.len.toFixed(2) + ' ' + C.toFixed(2)) + '" stroke-dashoffset="' + g.off.toFixed(2) + '"></circle>';
      }).join('') + '</g>' +
      '<text x="100" y="98" text-anchor="middle" class="nx-donut-val">' + fDdf(p.ddf_value) + '</text>' +
      '<text x="100" y="120" text-anchor="middle" class="nx-donut-cap">DDF Value</text></svg>';
    $('pie-chart').innerHTML = svg;
    $('pie-table').innerHTML = '<caption class="nx-sr">' + esc(p.name) + ': each chart’s contribution to DDF Value</caption>' +
      '<thead><tr><th scope="col">Chart</th><th scope="col">Adjusted</th><th scope="col">÷ 4 = contribution</th><th scope="col">Share</th></tr></thead><tbody>' +
      segs.map(function (g) {
        var r = p.sources[g.s];
        return '<tr><th scope="row"><span class="nx-sw" style="background:' + COLORS[g.i] + '"></span>' + esc(label(g.s)) + (r.estimated ? ' <span class="nx-est" title="Filled in from other charts">est.</span>' : '') + '</th><td class="nx-n">' + f1(r.adjusted) + '</td><td class="nx-n">' + quarter(r.adjusted) + '</td><td class="nx-n">' + (g.share * 100).toFixed(1) + '%</td></tr>';
      }).join('') +
      '</tbody><tfoot><tr><th scope="row">DDF Value</th><td class="nx-n">' + trim((data.basis.reduce(function (a, s) { return a + tenths(p.sources[s].adjusted); }, 0) / 10).toFixed(1)) + '</td><td class="nx-n">' + meanText(p) + '</td><td class="nx-n">100%</td></tr></tfoot>';
    $('pie-formula').textContent = 'DDF Value = ' + formula(p);
    $('pie-round').textContent = p.check.ties_out ? '' : ROUNDING_NOTE;
    $('pie-round').hidden = p.check.ties_out;
    $('pie-trace').href = '#numbers/trace/' + p.player_key;
    if (animate) requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Array.prototype.forEach.call($('pie-chart').querySelectorAll('circle'), function (c, i) {
          c.style.transition = 'stroke-dasharray .7s cubic-bezier(.2,.7,.2,1) ' + (i * 0.12) + 's';
          c.setAttribute('stroke-dasharray', c.getAttribute('data-len') + ' ' + C.toFixed(2));
        });
      });
    });
  }

  /* ---------- (b) Source build-up ---------- */
  function renderBuildUp(src) {
    var m = data.sources[src];
    Array.prototype.forEach.call($('bu-sources').querySelectorAll('a'), function (a) {
      if (a.getAttribute('data-src') === src) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
    $('bu-title').textContent = 'Source build-up: ' + m.label;
    var ex = m.rows[0];
    var exP = byKey[ex.player_key];
    $('bu-explain').innerHTML =
      '<li><b>Published</b><span>The source’s own units. ' + esc(m.label) + ' lists ' + esc(ex.name) + ' at ' + fPub(src, ex.published) + '.</span></li>' +
      '<li><b>Indexed</b><span>Put on one scale: published × one factor for the chart (' + m.index_factor.value + ' = indexed total ÷ published total), so the chart lines up with DDF Value. ' + fPub(src, ex.published) + ' → ' + f1(ex.indexed) + '.</span></li>' +
      '<li><b>Adjusted</b><span>For your league settings: valued at starter or bench level by where the player ranks at his position across the league (roster sizes and team count), rescaled so the chart’s total is the league’s value pie (' + data.value_pie.points.toLocaleString('en-US') + ' = ' + esc(data.value_pie.formula) + '). ' + f1(ex.indexed) + ' → ' + f1(ex.adjusted) + '.</span></li>' +
      '<li><b>DDF Value</b><span>The average of the four charts’ adjusted values. ' + (exP ? esc(ex.name) + ': ' + esc(formula(exP)) + '.' : '') + '</span></li>';
    var rows = state.showAll ? m.rows : m.rows.slice(0, BUILDUP_SHORT);
    var body = rows.map(function (r) {
      var p = byKey[r.player_key];
      var others = p ? data.basis.filter(function (s) { return s !== src; }).map(function (s) { return f1(p.sources[s].adjusted); }) : null;
      return '<tr><td class="nx-n nx-muted">' + r.rank + '</td><th scope="row">' + esc(r.name) + (r.estimated ? ' <span class="nx-est" title="Filled in from other charts">est.</span>' : '') + '</th><td>' + r.pos + '</td><td>' + (r.role === 'starter' ? 'Starter' : r.role === 'bench' ? 'Bench' : esc(r.role)) + '</td>' +
        '<td class="nx-n">' + fPub(src, r.published) + '</td><td class="nx-n">' + f1(r.indexed) + '</td><td class="nx-n nx-strong">' + f1(r.adjusted) + '</td>' +
        '<td class="nx-n nx-muted">' + (others ? others.join(' · ') : '—') + '</td>' +
        '<td class="nx-n nx-ddf">' + (p ? '<a href="#numbers/trace/' + p.player_key + '" aria-label="Trace ' + esc(r.name) + '’s DDF Value ' + fDdf(p.ddf_value) + '">' + fDdf(p.ddf_value) + '</a>' : '—') + '</td></tr>';
    }).join('');
    var others = data.basis.filter(function (s) { return s !== src; }).map(label).join(' · ');
    $('bu-table').innerHTML = '<caption class="nx-sr">' + esc(m.label) + ' build-up, week ' + data.week + ', ' + esc(settingsLine()) + '</caption>' +
      '<thead><tr><th scope="col">#</th><th scope="col">Player</th><th scope="col">Pos</th><th scope="col">Role</th><th scope="col">Published</th><th scope="col">Indexed</th><th scope="col">Adjusted</th><th scope="col"><span class="nx-th2">Other charts, adjusted</span><span class="nx-th3">' + esc(others) + '</span></th><th scope="col">DDF Value</th></tr>' +
      '<tr class="nx-explain-row"><td></td><td>What each column is</td><td></td><td></td><td>' + esc(m.label) + '’s own units</td><td>On one scale</td><td>For your league</td><td>The other three charts</td><td>Average of four</td></tr></thead>' +
      '<tbody>' + body + '</tbody>' +
      '<tfoot><tr><td></td><th scope="row" >Totals, all ' + m.players_listed + ' players listed</th><td></td><td></td><td class="nx-n">' + fPub(src, m.totals.published) + '</td><td class="nx-n">' + f1(m.totals.indexed) + '</td><td class="nx-n">' + f1(m.totals.adjusted) + '</td><td></td><td></td></tr></tfoot>';
    $('bu-meta').textContent = 'Adjusted total = the value pie, ' + data.value_pie.points.toLocaleString('en-US') + '. ' + m.players_listed + ' players listed, ' + m.filled_in + ' filled in from other charts (marked est.). Showing ' + rows.length + ' of the top ' + m.rows.length + ' in ' + m.label + '’s order.';
    var more = $('bu-more');
    more.hidden = m.rows.length <= BUILDUP_SHORT;
    more.textContent = state.showAll ? 'Show top ' + BUILDUP_SHORT : 'Show top ' + m.rows.length;
    more.setAttribute('aria-expanded', String(state.showAll));
  }

  /* ---------- (c) Trace ---------- */
  function renderTrace(p) {
    $('tr-name').textContent = p.name + ' · ' + p.pos;
    $('tr-big').textContent = fDdf(p.ddf_value);
    $('tr-sub').textContent = 'DDF Value · #' + p.ddf_rank + ' by DDF Value · ' + settingsLine();
    $('tr-pub').innerHTML = '<caption class="nx-sr">' + esc(p.name) + ': published, indexed and adjusted by chart</caption><thead><tr><th scope="col">Chart</th><th scope="col">Published</th><th scope="col" class="nx-fac">× factor</th><th scope="col">Indexed</th><th scope="col">Adjusted</th></tr></thead><tbody>' +
      data.basis.map(function (s) {
        var r = p.sources[s];
        return '<tr><th scope="row">' + esc(label(s)) + (r.estimated ? ' <span class="nx-est" title="Filled in from other charts">est.</span>' : '') + '</th><td class="nx-n">' + fPub(s, r.published) + '</td><td class="nx-n nx-muted nx-fac">' + data.sources[s].index_factor.value + '</td><td class="nx-n">' + f1(r.indexed) + '</td><td class="nx-n nx-strong">' + f1(r.adjusted) + '</td></tr>';
      }).join('') + '</tbody>';
    $('tr-avg').textContent = formula(p);
    $('tr-round').textContent = p.check.ties_out ? '' : ROUNDING_NOTE;
    $('tr-round').hidden = p.check.ties_out;
    $('tr-pin').textContent = snapshotLine() + ' · ' + settingsLine() + ' · overrides: ' + data.overrides;
    $('tr-llm').textContent = llmText(p);
    $('tr-status').textContent = '';
  }

  /* ---------- routing ---------- */
  function parse() {
    var parts = location.hash.replace(/^#numbers\/?/, '').split('/');
    var view = VIEWS.indexOf(parts[0]) >= 0 ? parts[0] : 'pie';
    var arg = decodeURIComponent(parts[1] || '');
    return { view: view, arg: arg, canonical: VIEWS.indexOf(parts[0]) >= 0 };
  }
  function syncSubTabs() {
    $('nx-tab-pie').href = '#numbers/pie/' + state.player;
    $('nx-tab-build-up').href = '#numbers/build-up/' + state.source;
    $('nx-tab-trace').href = '#numbers/trace/' + state.player;
    $('nx-tab-glossary').href = '#numbers/glossary';
    setTabs($('nx-tabs'), 'nx-tab-' + state.view);
    VIEWS.forEach(function (v) { $('nx-view-' + v).hidden = v !== state.view; });
  }
  var lastRendered = '';
  function route() {
    if (!isNumbersHash()) { setArea('writing'); return; }
    setArea('numbers');
    var r = parse();
    if (r.view === 'glossary') { showGlossary(r.arg); return; }
    if (!data) return;
    if (!r.canonical) { history.replaceState(null, '', '#numbers/pie/' + state.player); r = parse(); }
    var prevPlayer = state.player, prevView = state.view, prevSource = state.source;
    state.view = r.view;
    if ((r.view === 'pie' || r.view === 'trace') && r.arg) {
      if (byKey[r.arg]) state.player = +r.arg;
      else { $('nx-live').textContent = 'That player is not in the week ' + data.week + ' snapshot. Showing ' + byKey[state.player].name + '.'; history.replaceState(null, '', '#numbers/' + r.view + '/' + state.player); }
    }
    if (r.view === 'build-up' && r.arg) {
      if (data.sources[r.arg]) { if (r.arg !== state.source) state.showAll = false; state.source = r.arg; }
      else history.replaceState(null, '', '#numbers/build-up/' + state.source);
    }
    syncSubTabs();
    var p = byKey[state.player];
    var key = state.view + '|' + (state.view === 'build-up' ? state.source + state.showAll : state.player);
    if (key === lastRendered) return;
    lastRendered = key;
    if (state.view === 'pie') {
      $('pie-pick').value = p.name; quickPicks($('pie-quick'), 'pie');
      renderPie(p, !calm());
    } else if (state.view === 'trace') {
      $('tr-pick').value = p.name; quickPicks($('tr-quick'), 'trace');
      renderTrace(p);
    } else {
      renderBuildUp(state.source);
    }
    var changed = state.view !== prevView || state.player !== prevPlayer || state.source !== prevSource;
    if (changed || !$('nx-live').textContent) {
      $('nx-live').textContent = state.view === 'build-up'
        ? 'Source build-up: ' + data.sources[state.source].label + ' selected.'
        : (state.view === 'pie' ? 'Value pie: ' : 'Trace: ') + p.name + ' selected, DDF Value ' + fDdf(p.ddf_value) + '.';
    }
  }

  /* ---------- (d) Glossary (static markup; term = #numbers/glossary/<term>) ---------- */
  function showGlossary(term) {
    var prevView = state.view;
    state.view = 'glossary';
    syncSubTabs();
    /* Source rename (Jeremy, 2026-11-06): the old Market term now lives at Analyst charts; old links still land on it. */
    if (term === 'market') { term = 'analyst-charts'; history.replaceState(null, '', '#numbers/glossary/analyst-charts'); }
    var el = term ? $('g-' + term) : null;
    if (term && !el) history.replaceState(null, '', '#numbers/glossary');
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
    var done = window.DDF && DDF.copyText ? DDF.copyText(text, status, 'Copied.') : navigator.clipboard.writeText(text).then(function () { status.textContent = 'Copied.'; return true; });
    return done;
  }

  function init() {
    wireTabKeys($('learn-area-tabs'));
    wireTabKeys($('nx-tabs'));
    window.addEventListener('hashchange', route);
    route();
    fetch(DATA_URL).then(function (r) { if (!r.ok) throw new Error(DATA_URL + ' ' + r.status); return r.json(); }).then(function (d) {
      data = d;
      d.players.forEach(function (p) { byKey[p.player_key] = p; byName[p.name.toLowerCase()] = p; });
      $('nx-snapshot').textContent = snapshotLine();
      $('nx-settings').textContent = settingsLine() + ' · overrides: ' + d.overrides;
      $('nx-method').textContent = d.explain.methodology.join(' ');
      $('nx-sources').textContent = d.explain.sources[0].split('. ').slice(0, 2).join('. ') + '.';
      $('bu-sources').innerHTML = d.basis.map(function (s) { return '<a class="nx-chip" href="#numbers/build-up/' + s + '" data-src="' + s + '">' + esc(d.sources[s].label) + '</a>'; }).join('');
      wirePicker($('pie-pick'), 'pie');
      wirePicker($('tr-pick'), 'trace');
      $('bu-more').addEventListener('click', function () { state.showAll = !state.showAll; lastRendered = ''; renderBuildUp(state.source); lastRendered = 'build-up|' + state.source + state.showAll; });
      $('tr-copy-llm').addEventListener('click', function () { copy(llmText(byKey[state.player]), this); });
      $('tr-copy-link').addEventListener('click', function () { copy(permalink('trace', state.player), this); });
      $('tr-copy-json').addEventListener('click', function () { copy(jsonFor(byKey[state.player]), this); });
      route();
    }).catch(function (err) {
      console.warn('Numbers: ', err);
      $('nx-error').hidden = false;
    });
  }
  window.DDFNumbers = { isNumbersHash: isNumbersHash };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
