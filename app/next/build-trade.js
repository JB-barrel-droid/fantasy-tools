/* Build a Trade on the live engine (JEG-1537): one screen, three ways in (Any players, My league, Add from waivers).

   No value math here. Every player number is a row of the engine that runs hidden on this page (window.DDF.engine,
   ddf-engine.js over TradeValueCurveControls): DDF Value and the indexed charts from DDF.engine.player(), Analyst charts
   = the mean of the CBS Sports, USA Today and FantasyPros values the engine lists for the player (all three, else none),
   the reference charts' published numbers from getInspection() (each chart's own units, filled-in estimates left out).
   Roster checks and waiver gains come from TradeValueFinder (v2/finder.js: tradeFit, teamFit, lineupValue), the same
   functions the live Find a trade and Waivers tabs use. A value the engine does not have stays missing, never 0.

   Links in: ?give=&get= (names, player keys or n:Name tokens, repeated or comma separated), ?partner=&yv=&tv=&constraints=
   (Trade & Waiver Recommendations), ?mode=any|league, ?waivers=1&drop=&add=; the live Compare a trade link forwarded by
   v2.js as #?give=<keys>&get=<keys>&scoring=&teams=&roster=&shares=&wk=&basis=&ov= (league settings apply for this visit
   only; basis and overrides are read by ddf-engine.js). The address is then rewritten to ?give=<names>&get=<names>.
   Leagues: a chat link (DDF.link, #s=) or the live League tab's saved rosters (DDF.engine.league()). */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const finite = v => typeof v === 'number' && isFinite(v);
  const fmt = v => finite(v) ? v.toFixed(2) : '—';
  const present = v => Array.isArray(v) && v.length > 0;
  const E = () => window.DDF && window.DDF.engine;
  const F = () => window.TradeValueFinder;
  const POS_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'];
  const ANALYST = ['cbs', 'usatoday', 'fantasypros'];
  const SCORING_LABEL = {standard: 'Standard', half_ppr: 'Half PPR', ppr: 'Full PPR'};
  const LIVE_CANDS = 'ddf.v2.waiverCandidates';   // the live Waivers tab's available players (v2/waivers.js)

  let C = null, ROWS = new Map(), BYNAME = new Map(), RC = new Map(), INS = null, FX = null;
  let L = null, S = {style: '', chart: ''}, W = null, P = null, linkNote = '';
  const undoLog = [];

  /* ---------- engine records ---------- */
  function reindex() {
    ROWS = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
    BYNAME = new Map();
    const priced = r => r.values && finite(r.values.ddf_value);
    C.getAllRows().slice().sort((a, b) => Number(priced(b)) - Number(priced(a))).forEach(r => {
      const k = normName(r.name);
      if (k && !BYNAME.has(k)) BYNAME.set(k, String(r.player_key));
    });
    RC = new Map(); INS = null; FX = null;
  }
  function normName(n) { return String(n || '').toLowerCase().replace(/[’`]/g, "'").replace(/\s+/g, ' ').trim(); }
  function inspection() {
    if (INS === null) { try { INS = C.getInspection ? C.getInspection() : false; } catch (e) { INS = false; } }
    return INS || null;
  }
  function rec(key) {
    key = String(key);
    if (RC.has(key)) return RC.get(key);
    let r;
    if (key.startsWith('n:')) r = {key, n: key.slice(2), pos: '', unknown: true};
    else {
      const p = E().player(key), row = ROWS.get(key);
      if (p) r = Object.assign({}, p);
      else if (row) r = {key, n: row.name, pos: row.pos, team: row.team || '', ddf: null, cbs: null, usat: null, fp: null, fc: null, espn: null, cbsros: null, razzball: null};
      else r = {key, n: 'Player ' + key, pos: '', unknown: true};
    }
    if (r.pos === 'DST') r.pos = 'DEF';
    const an = [r.cbs, r.usat, r.fp];
    r.an = an.every(finite) ? (an[0] + an[1] + an[2]) / 3 : null;
    const row = ROWS.get(key), v = row && row.values;
    r.proj = v && finite(v.ddf_value_projections) ? v.ddf_value_projections : null;
    r.ddf = finite(r.ddf) ? r.ddf : null;
    RC.set(key, r);
    return r;
  }
  /* A link or recommendation token -> a player key: a known key, a name the engine has, or n:<name> for a name it does not. */
  function resolve(token) {
    let t = String(token == null ? '' : token).trim();
    if (!t) return null;
    try { t = decodeURIComponent(t); } catch (e) { /* already plain */ }
    if (/^n:/i.test(t)) t = t.slice(2);
    if (/^\d+$/.test(t)) return ROWS.has(t) ? t : null;
    return BYNAME.get(normName(t)) || 'n:' + t;
  }
  const nm = k => rec(k).n;
  const catalog = () => E().players().map(p => p.key);

  /* ---------- league ---------- */
  function linkState() { try { return window.DDF && DDF.link && DDF.link.current() || null; } catch (e) { return null; } }
  function linkEntryKey(entry) {
    try {
      const p = DDF.link.player(entry), n = typeof entry === 'string' ? entry : (p.name || DDF.link.playerName(entry));
      return resolve(n);
    } catch (e) { return resolve(entry); }
  }
  function summarize(source, name, teams, me, want) {
    const entered = teams.filter(t => t.keys.length).length;
    const partners = teams.map((t, i) => i).filter(i => i !== me && teams[i].keys.length);
    const hasRoster = me >= 0 && teams[me].keys.length > 0;
    const available = hasRoster && partners.length > 0;
    return {source, name, teams, me, want, entered, partners, available, hasRoster, full: available && teams.length >= want && entered === teams.length};
  }
  function readLeague() {
    const st = linkState();
    if (st && st.settings) {
      const teams = (Array.isArray(st.teams) ? st.teams : []).map((t, i) => ({id: String(i), name: (t && t.name) || 'Team ' + (i + 1),
        keys: (t && Array.isArray(t.players) ? t.players : []).map(linkEntryKey).filter(Boolean)}));
      const me = Number.isInteger(st.me) && teams[st.me] ? st.me : -1;
      return Object.assign(summarize('link', 'From your chat', teams, me, +st.settings.teams || teams.length), {st});
    }
    // The shared league read (ddf-league.js: a chat link, a pasted league from connect/setup, or the saved League tab),
    // the same one the header pill and the workspace pages use (JEG-1559: a pasted league was missed here).
    const shared = window.DDF && DDF.league && DDF.league.current ? DDF.league.current() : null;
    if (shared && shared.teams && shared.teams.length) {
      const teams = shared.teams.map(t => ({id: String(t.index), name: t.name,
        keys: (t.players || []).map(p => p && p.key != null ? String(p.key) : null).filter(k => k && ROWS.has(k))}));
      const me = Number.isInteger(shared.me) ? teams.findIndex(t => t.id === String(shared.me)) : -1;
      return summarize(shared.source === 'saved' ? 'live' : shared.source === 'link' ? 'pasted' : shared.source, shared.name || 'Your league', teams, me, (shared.settings && +shared.settings.teams) || teams.length);
    }
    const lg = E().league();
    if (lg) {
      const teams = lg.teams.map(t => ({id: t.id, name: t.name, keys: [...t.keys].filter(k => ROWS.has(k))}));
      return summarize('live', lg.name, teams, teams.findIndex(t => t.id === lg.mine), C.getState().teams);
    }
    return summarize('none', '', [], -1, C.getState().teams);
  }

  /* ---------- link parameters ---------- */
  const VALUE_CONTEXT = ['valuecontext', 'basis', 'ov'];
  function linkParams() {
    const q = new URLSearchParams(location.search);
    const at = location.hash.indexOf('?');
    if (at >= 0 && !/^#s=/.test(location.hash)) {
      new URLSearchParams(location.hash.slice(at + 1)).forEach((v, k) => { if (!VALUE_CONTEXT.includes(k) && !q.has(k)) q.append(k, v); });
    }
    return q;
  }
  function readParams() {
    const q = linkParams();
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem('ddf-recommendation')); } catch (e) { saved = null; }
    if (!saved || typeof saved !== 'object') saved = null;
    const list = v => (Array.isArray(v) ? v : [v]).filter(x => typeof x === 'string').flatMap(x => x.split(',')).map(x => x.trim()).filter(Boolean);
    const fromQuery = ['partner', 'give', 'get', 'receive'].some(k => q.has(k));
    const src = fromQuery
      ? {partner: q.get('partner'), give: q.getAll('give'), get: q.getAll('get').concat(q.getAll('receive')), constraints: q.get('constraints'), yv: q.get('yv'), tv: q.get('tv')}
      : saved ? {partner: saved.partner, give: saved.give, get: saved.get || saved.receive, constraints: saved.constraints, yv: saved.yourValuation, tv: saved.theirValuation} : {};
    const mode = ['any', 'league'].includes(q.get('mode')) ? q.get('mode') : null;
    return {q, mode, waivers: q.get('waivers') === '1' || q.get('tab') === 'waivers', drop: q.get('drop'), add: q.get('add'), fromQuery,
      partner: typeof src.partner === 'string' && src.partner.trim() ? src.partner.trim() : null,
      give: list(src.give || []), get: list(src.get || []),
      constraints: typeof src.constraints === 'string' ? src.constraints : '',
      yourValuation: typeof src.yv === 'string' ? src.yv : null, theirValuation: typeof src.tv === 'string' ? src.tv : null};
  }
  /* The live link's league (v2 leagueLinkParts): scoring, teams, roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN6, shares, wk. */
  const LINK_ROSTER = {QB: 'QB', RB: 'RB', WR: 'WR', TE: 'TE', FLEX: 'FLEX', SF: 'SUPERFLEX', BN: 'BENCH'};
  function linkLeague(q) {
    const out = {};
    const scoring = q.get('scoring');
    if (['standard', 'half_ppr', 'ppr'].includes(scoring)) out.scoring = scoring;
    const teams = Number(q.get('teams'));
    if ([8, 10, 12, 14].includes(teams)) out.teams = teams;
    const roster = {};
    String(q.get('roster') || '').split('.').forEach(part => {
      const m = /^([A-Z]+)(\d+)$/.exec(part);
      if (m && LINK_ROSTER[m[1]]) roster[LINK_ROSTER[m[1]]] = Number(m[2]);
    });
    if (Object.keys(roster).length) out.roster = roster;
    const shares = {};
    String(q.get('shares') || '').split('_').forEach(part => { const m = /^(QB|RB|WR|TE)(\d*\.?\d+)$/.exec(part); if (m) shares[m[1]] = Number(m[2]); });
    if (Object.keys(shares).length === 4) out.shares = shares;
    if (q.has('wk') && Number.isInteger(Number(q.get('wk')))) out.week = Number(q.get('wk'));
    // A link that carries a league carries its advanced settings and season weeks too; missing ones mean the defaults
    // (v2 applyLinkLeague, JEG-537 / JEG-527).
    if (q.has('scoring') && C.getLineupSettingsDefaults) {
      const def = C.getLineupSettingsDefaults();
      if (C.getLineupSettings && C.setLineupSettings) {
        const inj = q.get('inj'), conf = Number(q.get('conf'));
        let bso = q.has('bso') ? Number(q.get('bso')) : null;
        if (!q.has('bso') && q.has('bench')) { const old = Number(q.get('bench')); bso = Number.isFinite(old) && Math.abs(old - 0.15) > 5e-4 ? old : null; }
        out.adv = {injuryHistory: ['recent', 'all'].includes(inj) ? inj : def.injuryHistory,
          projectionConfidence: [0.5, 1, 1.5].includes(conf) ? conf : def.projectionConfidence,
          benchShareOverride: Number.isFinite(bso) && bso !== null ? Math.min(0.30, Math.max(0.01, bso)) : null};
      }
      const build = C.getBuildContentWeek ? C.getBuildContentWeek() : null;
      if (Number.isInteger(build) && C.setLeagueWeeks && C.getLeagueWeeks && C.setOptimizeFor && C.setContentWeek) {
        const po = /^(\d+)-(\d+)$/.exec(q.get('playoffs') || ''), optimize = q.get('optimize') || def.optimizeFor;
        const week = q.has('week') ? Number(q.get('week')) : build;
        out.weeks = {build, content: Number.isInteger(week) ? week : build,
          regularEnd: q.has('regend') && Number.isInteger(Number(q.get('regend'))) ? Number(q.get('regend')) : def.regularSeasonEnd,
          playoffLo: po ? Number(po[1]) : def.playoffWeeks[0], playoffHi: po ? Number(po[2]) : def.playoffWeeks[1],
          optimize: ['season', 'regular', 'playoffs'].includes(optimize) ? optimize : def.optimizeFor};
      }
    }
    return Object.keys(out).length ? out : null;
  }
  function settingsText() {
    const st = C.getState(), r = C.getRosterShape();
    return `${SCORING_LABEL[st.scoring] || st.scoring} · ${st.teams} teams · ${r.SUPERFLEX ? 'Superflex' : '1 QB'}`;
  }
  /* After reading: the address says ?give=<names>&get=<names> (the redesign's link form); the link's league stays in
     it so a reload prices the same league; basis and overrides stay in the hash for ddf-engine.js. */
  function tidyAddress(give, get) {
    const at = location.hash.indexOf('?');
    if (at < 0 || /^#s=/.test(location.hash)) return;
    const hashQ = new URLSearchParams(location.hash.slice(at + 1));
    const q = new URLSearchParams(location.search);
    const keep = new URLSearchParams();
    hashQ.forEach((v, k) => { if (VALUE_CONTEXT.includes(k)) keep.append(k, v); else if (!['give', 'get'].includes(k) && !q.has(k)) q.append(k, v); });
    q.delete('give'); q.delete('get');
    // A name two engine rows share keeps its key, so a reload opens the same player.
    const token = k => (/^\d+$/.test(k) && BYNAME.get(normName(nm(k))) !== k) ? k : nm(k);
    give.forEach(k => q.append('give', token(k)));
    get.forEach(k => q.append('get', token(k)));
    const rest = keep.toString(), base = location.hash.slice(0, at) === '#' ? '' : location.hash.slice(0, at);
    try { history.replaceState(history.state, '', location.pathname + (q.toString() ? '?' + q : '') + (rest ? (base || '#') + '?' + rest : base)); } catch (e) { /* the link still worked */ }
  }

  /* ---------- state ---------- */
  const partnerName = () => S.partner >= 0 && L.teams[S.partner] ? L.teams[S.partner].name : '';
  function rosterKeys(side) {
    if (side === 'give') return (L.me >= 0 ? myRosterKeys() : []).concat(S.extras.give.filter(k => !(L.me >= 0 && myRosterKeys().includes(k))));
    const base = S.partner >= 0 ? L.teams[S.partner].keys : [];
    return base.concat((S.extras.get[S.partner] || []).filter(k => !base.includes(k)));
  }
  const isExtra = (side, k) => side === 'give' ? S.extras.give.includes(k) && !(L.me >= 0 && myRosterKeys().includes(k)) : (S.extras.get[S.partner] || []).includes(k);
  function addExtra(side, k) {
    if (rosterKeys(side).includes(k)) return;
    if (side === 'give') S.extras.give.push(k); else (S.extras.get[S.partner] = S.extras.get[S.partner] || []).push(k);
  }
  const picked = side => S.mode === 'any' ? S.any[side].slice() : rosterKeys(side).filter(k => S.lg[side].has(k));
  const joinNames = list => list.length < 3 ? (list.join(' and ') || 'No players') : list.slice(0, -1).join(', ') + ' and ' + list[list.length - 1];
  const joinKeys = keys => joinNames(keys.map(nm));

  /* ---------- fit (league mode and waivers) ---------- */
  const VALUATION_KEY = {'DDF': 'ddf_value', 'DDF (Projection based)': 'ddf_value_projections', 'Market': 'chart_avg', 'CBS Sports': 'cbs', 'USA Today': 'usatoday',
    'FantasyPros': 'fantasypros', 'FantasyCalc': 'fantasycalc', 'ESPN projections': 'espn', 'CBS rest-of-season projections': 'cbsros', 'Razzball projections': 'razzball'};
  const VALUATION_LABEL = {'Market': 'Analyst charts', 'FantasyCalc': 'Live market (FantasyCalc)', 'DDF': 'DDF Value', 'DDF (Projection based)': 'DDF Value (projections)'};
  const valuationLabel = v => VALUATION_LABEL[v] || v;
  function fitBase() {
    if (FX !== null) return FX || null;
    FX = false;
    try {
      const Fd = F();
      if (!Fd || !Fd.tradeFit || !C.getAdjustmentWeights) return null;
      const shape = C.getRosterShape();
      const expected = Fd.expectedDepth(C.getAdjustmentWeights().allocation, C.getState().teams);
      const info = C.getSourceInfo ? C.getSourceInfo() : [], avail = new Set(info.filter(i => i.available).map(i => i.key));
      const analyst = ANALYST.filter(k => avail.has(k));
      const market = Fd.CHART_KEYS.filter(k => avail.has(k));
      const readout = C.getBenchShareReadout ? C.getBenchShareReadout() : null;
      const overall = readout && finite(readout.overall) ? readout.overall : (C.getBenchShare ? C.getBenchShare() : null);
      if (!finite(overall)) return null;   // no bench share: the checks and gains say not evaluated rather than count the bench as 0
      const weights = {overall};
      ['QB', 'RB', 'WR', 'TE'].forEach(pos => { if (readout && finite(readout[pos])) weights[pos] = readout[pos]; });
      if (!shape || !expected) return null;
      // Analyst charts = the three analyst charts' mean (all three, as finder.js withChartAverage), only when all three run.
      const rows = new Map(Fd.withChartAverage([...ROWS.values()], analyst.length === 3 ? analyst : []).map(r => [String(r.player_key), r]));
      FX = {Fd, shape, expected, weights, analyst, market: market.length >= Fd.MIN_CHARTS ? market : null, rows};
    } catch (err) { console.warn('Build a Trade: no fit context', err); FX = false; }
    return FX || null;
  }
  const rowsOf = keys => { const X = fitBase(); return X ? keys.map(k => X.rows.get(String(k))).filter(Boolean) : []; };
  function tradeFit() {
    const X = fitBase();
    if (!X || L.me < 0 || S.partner < 0) return null;
    const ourKey = VALUATION_KEY[$('your-valuation').value] || 'ddf_value', theirKey = VALUATION_KEY[$('their-valuation').value] || 'chart_avg';
    if ((ourKey === 'chart_avg' || theirKey === 'chart_avg') && X.analyst.length !== 3) return {missing: 'Analyst charts are not available for this league this week.'};
    const give = rowsOf(picked('give')), get = rowsOf(picked('get'));
    try {
      const fit = X.Fd.tradeFit({mine: {roster: rowsOf(myRosterKeys()), leaving: give, arriving: get}, theirs: {roster: rowsOf(L.teams[S.partner].keys), leaving: get, arriving: give}},
        {shape: X.shape, expected: X.expected, weights: X.weights, ourKey, marketKey: theirKey, chartKeys: X.analyst.length ? X.analyst : X.market || undefined, z: X.Fd.FIT_Z});
      return fit ? {fit, ourKey, theirKey} : null;
    } catch (err) { console.warn('Build a Trade: trade checks not run', err); return null; }
  }
  const signed2 = n => (Math.abs(n) < 0.005 ? '0.00' : (n > 0 ? '+' : '−') + Math.abs(n).toFixed(2));
  function checksHTML() {
    const t = tradeFit();
    if (!t) return {pass: false, html: '<p>The trade checks need your roster, the partner\'s roster and this week\'s values.</p>'};
    if (t.missing) return {pass: false, html: `<p>${esc(t.missing)}</p>`};
    const {fit} = t, yl = valuationLabel($('your-valuation').value), tl = valuationLabel($('their-valuation').value);
    const mark = ok => ok ? '✓' : '✕';
    const moved = (d, who, label) => `${who} starters ${Math.abs(d) < 0.005 ? 'do not change' : d > 0 ? 'improve by ' + signed2(d) : 'decline by ' + signed2(d)} on ${esc(label)}`;
    const issues = c => c.issues && c.issues.length ? ': ' + esc(c.issues.join('; ')) : '';
    const coverage = ANALYST.filter(k => picked('give').concat(picked('get')).every(key => finite(chartListed(rec(key), k)))).length;
    const lines = [
      `<p>${mark(fit.us.starterDelta >= -0.05)} ${moved(fit.us.starterDelta, 'Your', yl)}</p>`,
      `<p>${mark(fit.them.starterDelta >= -0.05)} ${moved(fit.them.starterDelta, 'Their', tl)}</p>`,
      `<p>${mark(fit.myConstruction.ok)} Your roster construction ${fit.myConstruction.ok ? 'passes' : 'does not pass' + issues(fit.myConstruction)}</p>`,
      `<p>${mark(fit.theirConstruction.ok)} Their roster construction ${fit.theirConstruction.ok ? 'passes' : 'does not pass' + issues(fit.theirConstruction)}</p>`,
      `<p>${mark(coverage === 3)} Their analyst-charts coverage: ${coverage} of 3 charts</p>`
    ];
    return {pass: Boolean(fit.natural && fit.natural.ok), html: lines.join(''), fit};
  }
  const chartListed = (p, k) => k === 'cbs' ? p.cbs : k === 'usatoday' ? p.usat : k === 'fantasypros' ? p.fp : k === 'fantasycalc' ? p.fc : null;

  /* ---------- init ---------- */
  function init() {
    reindex();
    L = readLeague();
    P = readParams();
    W = loadWaivers();
    if (W.roster && L.me >= 0) L.teams[L.me] = Object.assign({}, L.teams[L.me], {keys: W.roster.slice()});
    L.hasRoster = L.me >= 0 && myRosterKeys().length > 0;
    const st = L.st;
    const wv = S.wv || {min: 2, pos: 'All'};
    S = {mode: 'any', kind: P.waivers || (st && st.view === 'waivers') ? 'waivers' : 'trade', any: {give: [], get: []}, lg: {give: new Set(), get: new Set()},
      partner: L.partners.length ? L.partners[0] : -1, extras: {give: [], get: {}}, style: S.style || '', userStyle: Boolean(S.userStyle), chart: S.chart || '', chartUser: S.chartUser || '', dirty: false,
      wv: {drop: P.drop ? resolve(P.drop) : null, add: P.add ? resolve(P.add) : null, min: wv.min, pos: wv.pos, countKey: ''}, claimDirty: false};
    let note = '';
    const trade = st && st.trade && (present(st.trade.give) || present(st.trade.get)) ? st.trade : null;
    if (trade) {
      const g = (trade.give || []).map(linkEntryKey).filter(Boolean), r = (trade.get || []).map(linkEntryKey).filter(Boolean);
      if (Number.isInteger(trade.partner) && trade.partner !== L.me && L.teams[trade.partner]) { if (!L.partners.includes(trade.partner)) L.partners.push(trade.partner); S.partner = trade.partner; }
      S.lg = {give: new Set(g), get: new Set(r)}; S.any = {give: g.slice(), get: r.slice()};
      note = 'Loaded from your chat: ' + joinKeys(g) + ' for ' + joinKeys(r) + '.';
    }
    if (P.partner) {
      let idx = L.teams.findIndex(t => t.name === P.partner);
      if (idx < 0 && /^\d+$/.test(P.partner) && L.teams[+P.partner]) idx = +P.partner;
      if (idx >= 0 && idx !== L.me) { if (!L.partners.includes(idx)) L.partners.push(idx); S.partner = idx; }
    }
    const missing = [];
    const keysOf = list => [...new Set(list.map(t => { const k = resolve(t); if (!k) missing.push(t); return k; }).filter(Boolean))];
    if (P.give.length || P.get.length) {
      const g = keysOf(P.give), r = keysOf(P.get).filter(k => !g.includes(k));
      S.lg = {give: new Set(g), get: new Set(r)}; S.any = {give: g, get: r};
      note = (P.partner ? 'Prefilled from Trade & Waiver Recommendations: ' : 'Prefilled: ') + joinKeys(g) + ' for ' + joinKeys(r) + '.';
      tidyAddress(g, r);
    }
    const unknown = S.any.give.concat(S.any.get).filter(k => rec(k).unknown).map(nm).concat(missing.map(t => 'player ' + t));
    if (unknown.length) note += ` ${joinNames(unknown)} ${unknown.length === 1 ? 'has' : 'have'} no value this week, so ${unknown.length === 1 ? 'that player is' : 'they are'} left out of the numbers.`;
    if (linkNote) note = (note ? note + ' ' : '') + linkNote;
    for (const k of S.lg.give) addExtra('give', k);
    if (S.partner >= 0) for (const k of S.lg.get) addExtra('get', k);
    S.mode = L.full ? 'league' : P.mode || (P.partner && P.fromQuery && L.available ? 'league' : (L.source !== 'none' && L.available ? 'league' : (S.kind === 'waivers' && L.hasRoster ? 'league' : 'any')));
    $('prefill-note').hidden = !note; $('prefill-note').textContent = note.trim();
    const relabel = s => s.replace(/(valuation: )Market\b/g, '$1Analyst charts').replace(/(valuation: )FantasyCalc\b/g, '$1Live market (FantasyCalc)');
    $('constraints').textContent = P.constraints ? relabel(P.constraints) : defaultConstraints;
    $('constraints-note').textContent = P.constraints ? 'Carried constraints: ' + relabel(P.constraints) : 'Default search constraints shown.';
    /* Option values keep the old tokens ('Market' = Analyst charts, 'FantasyCalc' = Live market); old links and the new labels both load. */
    const VAL_ALIAS = {'analyst charts': 'Market', 'analyst': 'Market', 'market': 'Market', 'live market': 'FantasyCalc', 'live market (fantasycalc)': 'FantasyCalc', 'fantasycalc': 'FantasyCalc', 'ddf': 'DDF', 'ddf value': 'DDF'};
    const valTok = v => typeof v === 'string' && VAL_ALIAS[v.trim().toLowerCase()] || v;
    const f = st && st.filters || {}, val = v => v === 'market' || v === 'analyst' ? 'Market' : v === 'fantasycalc' || v === 'live' ? 'FantasyCalc' : v === 'ddf' ? 'DDF' : null;
    if (val(f.yourValuation)) $('your-valuation').value = val(f.yourValuation);
    if (val(f.theirValuation)) $('their-valuation').value = val(f.theirValuation);
    const pick = (id, v) => { v = valTok(v); if (v && [...$(id).options].some(o => o.value === v)) $(id).value = v; };
    pick('your-valuation', P.yourValuation); pick('their-valuation', P.theirValuation);
    $('partner').innerHTML = L.partners.map(i => `<option value="${i}"${i === S.partner ? ' selected' : ''}>${esc(L.teams[i].name)}</option>`).join('');
    for (const side of ['give', 'get']) { $('any-' + side + '-search').value = ''; $(side + '-search').value = ''; }
    render();
  }
  const defaultConstraints = $('constraints').textContent;

  /* ---------- rendering ---------- */
  function show(key) {
    const any = S.mode === 'any';
    return {any, 'any-noleague': any && !L.hasRoster, league: !any && L.available, 'league-off': !any && !L.available, full: !any && L.full, note: !any && !L.full, roster: !any && L.hasRoster, 'roster-off': !any && !L.hasRoster}[key];
  }
  function rosterNote() {
    if (L.source === 'none') return 'No league added yet · <a href="connect.html">add your league</a>';
    if (L.source === 'link' && !L.teams.length) return 'No rosters entered yet · <a href="connect.html">add your league</a>';
    const missing = Math.max(0, L.want - L.entered);
    return `${L.entered} of ${L.want} rosters entered` + (missing ? ` · <a href="connect.html">${missing} ${missing === 1 ? 'team' : 'teams'} missing, add ${missing === 1 ? 'it' : 'them'}</a>` : '');
  }
  function sellSuggestion() {
    /* With your roster: the player the analyst charts price furthest above DDF Value (the Values page's Sell side). */
    if (L.me < 0) return null;
    const mine = myRosterKeys().map(rec).filter(p => finite(p.ddf) && finite(p.an) && p.an > p.ddf);
    return mine.sort((a, b) => (b.an - b.ddf) - (a.an - a.ddf))[0] || null;
  }
  function render() {
    const any = S.mode === 'any', waivers = S.kind === 'waivers';
    document.body.classList.toggle('mode-any', any); document.body.classList.toggle('mode-league', !any); document.body.classList.toggle('kind-waivers', waivers);
    document.querySelectorAll('[data-only],[data-kind]').forEach(el => { el.hidden = (el.dataset.kind && el.dataset.kind !== S.kind) || (el.dataset.only && !show(el.dataset.only)); });
    $('mode-seg').hidden = L.full;
    document.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === S.mode)));
    document.querySelectorAll('[data-pick-kind]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.pickKind === S.kind)));
    $('roster-note').innerHTML = rosterNote();
    $('settings-line').textContent = 'Values for ' + settingsText() + '. ';
    $('charts-title').textContent = waivers ? 'Pickup charts' : 'Trade charts';
    const strip = document.querySelector('.ctx-strip > span:first-child');
    if (strip) strip.textContent = (L.source === 'none' ? 'No league yet' : 'My league · ' + (L.source === 'link' ? 'From your chat' : L.name)) + ' · ' + settingsText();
    if (waivers) {
      $('lede').textContent = any ? 'Adding from waivers works with your league: your roster and its available players.' : L.hasRoster ? 'Pick who to drop, then pick your best add from the available players.' : 'Add your roster to find your best adds from waivers.';
      $('suggest').hidden = true;
      if (!any && L.hasRoster) renderWaivers();
      const ready = !any && L.hasRoster && waiverReady();
      $('empty-state').hidden = true; $('result').hidden = !ready;
      if (ready) { renderWaiverCharts(); if (!S.claimDirty) writeClaim(); }
      return;
    }
    const ready = picked('give').length > 0 && picked('get').length > 0;
    if (any) $('lede').textContent = 'Pick any players for each side to see who gets more, then propose it.';
    else if (L.available) { $('lede').innerHTML = 'Refine your offer to <span id="partner-name"></span>, then pick how to propose it.'; $('partner-name').textContent = partnerName(); }
    else $('lede').textContent = 'Add your league to build a trade with your leaguemates.';
    const sug = any && !S.any.give.length && !S.any.get.length ? sellSuggestion() : null;
    $('suggest').hidden = !sug;
    if (sug) { $('suggest-give').textContent = `${sug.n} · ${sug.pos} — add him`; $('suggest-give').dataset.key = sug.key; }
    if (any) { renderPick('give'); renderPick('get'); }
    else if (L.available) {
      renderChooser('give'); renderChooser('get');
      $('get-title').textContent = partnerName() + ' · Pick players'; $('get-region').setAttribute('aria-label', partnerName() + ' players');
      if (L.full) { renderOutside('give'); renderOutside('get'); }
    }
    for (const side of ['give', 'get']) $(side + '-names').textContent = joinKeys(picked(side));
    if (!any && L.available) {
      const c = ready ? checksHTML() : {pass: false, html: '<p>Add a player to each side to run the trade checks.</p>'};
      $('check-pass').textContent = c.pass ? '✓ Trade checks pass' : 'Review trade checks';
      $('check-pass').classList.toggle('check-review', !c.pass);
      $('checks').innerHTML = c.html; S.fit = c.fit || null;
    } else S.fit = null;
    const shop = picked('give').length > 0 && !picked('get').length;
    $('empty-state').hidden = ready || shop; $('result').hidden = !(ready || shop); $('trade-charts').hidden = shop; $('shop-note').hidden = !shop;
    if (ready || shop) { renderChartPick(); if (ready) renderCharts(); if (!S.dirty) writeMessage(); else renderOffer(); }
  }
  function matchRow(p, label) {
    const v = finite(p.ddf) ? 'DDF ' + p.ddf.toFixed(2) : finite(p.an) ? 'Analyst charts ' + p.an.toFixed(2) : '';
    return `<li><button type="button" data-add="${esc(p.key)}" aria-label="${esc(label + ' ' + p.n)}"><span>${esc(p.n)}<small>${esc(p.pos)}</small></span><span><span class="pick-num">${v}</span><span class="pick-add" aria-hidden="true">Add</span></span></button></li>`;
  }
  const byValue = (a, b) => ((b.ddf ?? b.an ?? -1) - (a.ddf ?? a.an ?? -1)) || a.n.localeCompare(b.n);
  function search(query, exclude) {
    const q = normName(query);
    return q ? catalog().filter(k => !exclude.has(k)).map(rec).filter(p => normName(p.n).includes(q)).sort(byValue).slice(0, 6) : [];
  }
  const countText = (query, n) => query.trim() ? (n ? n + (n === 1 ? ' player matches.' : ' players match.') : 'No players match. Check the spelling.') : '';
  function renderPick(side) {
    const query = $('any-' + side + '-search').value, taken = new Set(S.any.give.concat(S.any.get)), found = search(query, taken);
    $('any-' + side + '-results').innerHTML = found.map(p => matchRow(p, 'Add')).join('');
    $('any-' + side + '-count').textContent = countText(query, found.length);
    $('any-' + side + '-chosen').innerHTML = S.any[side].length ? S.any[side].map(k => {
      const p = rec(k);
      return `<li><span>${esc(p.n)}<small>${esc(p.pos)}</small> <span class="pick-num">${finite(p.ddf) ? 'DDF ' + p.ddf.toFixed(2) : 'No value this week'}</span></span><button type="button" data-remove="${esc(k)}" aria-label="Remove ${esc(p.n)}">Remove</button></li>`;
    }).join('') : '<li class="pick-none">No player added yet</li>';
  }
  function renderChooser(side) {
    const query = normName($(side + '-search').value);
    const keys = rosterKeys(side);
    $(side + '-picker').innerHTML = keys.map((k, i) => {
      const p = rec(k), chosen = S.lg[side].has(k);
      return `<tr class="${chosen ? 'selected' : ''}" data-key="${esc(k)}" ${normName(p.n).includes(query) ? '' : 'hidden'}><td>${esc(p.n)}${isExtra(side, k) ? '<small class="outside-tag">Added from any player</small>' : ''}</td><td>${esc(p.pos)}</td><td class="number">${fmt(p.ddf)}</td><td class="number">${fmt(p.an)}</td><td><button type="button" data-side="${side}" data-index="${i}" aria-pressed="${chosen}" aria-label="${chosen ? 'Remove' : 'Add'} ${esc(p.n)}"><span class="b-full">${chosen ? 'Remove' : 'Add'}</span><span class="b-short" aria-hidden="true">${chosen ? '−' : '+'}</span></button></td></tr>`;
    }).join('') || '<tr><td colspan="5">No players on this roster yet.</td></tr>';
  }
  function renderOutside(side) {
    const query = $(side + '-outside-search').value, found = search(query, new Set(rosterKeys(side).concat(rosterKeys(side === 'give' ? 'get' : 'give'))));
    $(side + '-outside-results').innerHTML = found.map(p => matchRow(p, 'Include')).join('') || (query.trim() ? '<li class="pick-count">No players match.</li>' : '');
  }
  /* Difference by source: each source the engine lists for every player in the trade (league-adjusted values). */
  const SOURCES = [
    ['DDF', 'DDF Value', p => p.ddf], ['CBS Sports', 'CBS Sports', p => p.cbs], ['FantasyPros', 'FantasyPros', p => p.fp], ['USA Today', 'USA Today', p => p.usat],
    ['Market', 'Analyst charts', p => p.an], ['FantasyCalc', 'Live market (FantasyCalc)', p => p.fc]
  ];
  const EXTRA_SOURCES = {'DDF (Projection based)': ['DDF Value (projections)', p => p.proj], 'ESPN projections': ['ESPN projections', p => p.espn],
    'CBS rest-of-season projections': ['CBS rest-of-season projections', p => p.cbsros], 'Razzball projections': ['Razzball projections', p => p.razzball]};
  function tradeSources() {
    const yv = S.mode === 'league' ? $('your-valuation').value : 'DDF';
    const list = SOURCES.slice();
    if (EXTRA_SOURCES[yv]) list.push([yv].concat(EXTRA_SOURCES[yv]));
    const give = picked('give').map(rec), get = picked('get').map(rec), sources = [], missing = [];
    for (const [id, name, value] of list) {
      const g = give.map(p => ({n: p.n, v: value(p)})), r = get.map(p => ({n: p.n, v: value(p)}));
      if (g.concat(r).every(x => finite(x.v))) sources.push({id, name, give: g, receive: r}); else missing.push(name);
    }
    let main = sources.findIndex(s => s.id === yv);
    if (main < 0) main = Math.max(0, ['DDF', 'Market'].map(n => sources.findIndex(x => x.id === n)).find(i => i >= 0) ?? 0);
    return {sources, missing, main};
  }
  function renderCharts() {
    const {sources, missing, main} = tradeSources();
    window.DDF_TC.render($('charts'), {sources, mainSourceIndex: main,
      note: missing.length && sources.length ? 'Not shown for this package: ' + missing.join(', ') + ' (values not available for every selected player).' : '',
      emptyText: 'None of the sources has a value for every player in this trade yet, so there is no chart to draw.'});
  }

  /* ---------- Add from waivers ---------- */
  /* Available players: this tab's list (DDF.state 'waivers', after a paste or a confirmed move), else a chat link's
     waivers, else the live Waivers tab's list (localStorage ddf.v2.waiverCandidates, written back on a paste). */
  function readLive(key) { try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { return null; } }
  function loadWaivers() {
    let saved = null;
    try { saved = DDF.state.get('waivers', null); } catch (e) { saved = null; }
    const keys = list => Array.isArray(list) ? list.map(String).filter(k => /^\d+$/.test(k) ? ROWS.has(k) : k.startsWith('n:')) : null;
    if (saved && saved.v === 2 && saved.source === L.source && keys(saved.players)) return {players: keys(saved.players), roster: keys(saved.roster)};
    if (L.source === 'link') return {players: (Array.isArray(L.st.waivers) ? L.st.waivers : []).map(linkEntryKey).filter(Boolean), roster: null};
    const live = readLive(LIVE_CANDS);
    return {players: Array.isArray(live) ? live.map(p => p && String(p.key)).filter(k => k && ROWS.has(k)) : [], roster: null};
  }
  function saveWaivers(candidatesChanged) {
    try { DDF.state.set('waivers', {v: 2, source: L.source, players: W.players, roster: W.roster}); } catch (e) { /* this visit still has it */ }
    if (candidatesChanged && L.source !== 'link') {
      try { localStorage.setItem(LIVE_CANDS, JSON.stringify(W.players.filter(k => ROWS.has(k)).map(k => { const r = ROWS.get(k); return {key: k, name: r.name, pos: r.pos, team: r.team || ''}; }))); } catch (e) { /* private window */ }
    }
  }
  function myRosterKeys() { return L.me >= 0 ? (W && W.roster ? W.roster : L.teams[L.me].keys) : []; }
  const availableNow = () => { const mine = new Set(myRosterKeys()); return W.players.filter(k => !mine.has(k)); };
  function benchSet() {
    const X = fitBase();
    if (!X) return new Set();
    try { return new Set(X.Fd.lineupValue(rowsOf(myRosterKeys()), X.shape, 'ddf_value').bench.map(r => String(r.player_key))); } catch (e) { return new Set(); }
  }
  /* The change in your roster's DDF Value (starters in full, bench at its weights: finder.js teamFit net, the measure
     the live Waivers tab ranks by) when you drop `drop` and add `add`. null when either has no DDF Value. */
  const gainCache = new Map();
  function gainFor(drop, add) {
    const id = drop + '|' + add + '|' + myRosterKeys().join(',');
    if (gainCache.has(id)) return gainCache.get(id);
    let g = null;
    const X = fitBase(), d = X && X.rows.get(drop), a = X && X.rows.get(add);
    if (X && d && a && finite(a.values.ddf_value)) {
      try { g = X.Fd.teamFit({roster: rowsOf(myRosterKeys()), leaving: [d], arriving: [a]}, {shape: X.shape, expected: X.expected, weights: X.weights, chartKeys: X.market || undefined, z: X.Fd.FIT_Z}, 'ddf_value').net; }
      catch (e) { g = null; }
    }
    g = finite(g) ? Math.round(g * 100) / 100 : null;
    gainCache.set(id, g);
    return g;
  }
  function suggestion() {
    /* The drop that costs your roster least (live Waivers dropRanking: the smallest loss in weighted worth). */
    const X = fitBase(), keys = myRosterKeys(), bench = benchSet(), pool = keys.filter(k => bench.has(k)).length ? keys.filter(k => bench.has(k)) : keys;
    if (!X || !pool.length) return null;
    const roster = rowsOf(keys);
    const loss = k => {
      const r = X.rows.get(k);
      if (!r) return Infinity;
      try { return -X.Fd.teamFit({roster, leaving: [r], arriving: []}, {shape: X.shape, expected: X.expected, weights: X.weights, chartKeys: X.market || undefined, z: X.Fd.FIT_Z}, 'ddf_value').net; } catch (e) { return Infinity; }
    };
    const best = pool.map(k => ({k, l: loss(k)})).sort((a, b) => a.l - b.l || (rec(a.k).ddf ?? 0) - (rec(b.k).ddf ?? 0) || nm(a.k).localeCompare(nm(b.k)))[0];
    return best ? {k: best.k, label: pool.length < keys.length ? 'your lowest-value bench player' : 'your lowest-value player'} : null;
  }
  const minText = () => S.wv.min > 0 ? S.wv.min + '+' : 'over 0';
  function reasonFor(add, drop) {
    const ap = add.pos, dp = rec(drop).pos;
    if (!ap) return '';
    if (ap === dp) return 'upgrades your ' + ap + ' depth';
    const have = myRosterKeys().filter(k => k !== drop && rec(k).pos === ap).length;
    return have ? 'adds ' + ap + ' depth (you have ' + have + ')' : 'fills your empty ' + ap + ' spot';
  }
  function boardRows() {
    const drop = S.wv.drop, min = S.wv.min;
    return availableNow().map(rec).filter(p => S.wv.pos === 'All' || p.pos === S.wv.pos).map(p => {
      const gain = gainFor(drop, p.key), pass = gain !== null && gain > 0.05 && gain >= min;
      return {key: p.key, n: p.n, pos: p.pos, gain, pass};
    }).sort((a, b) => (b.pass - a.pass) || ((b.gain ?? -1e9) - (a.gain ?? -1e9)) || a.n.localeCompare(b.n));
  }
  function waiverReady() { return !!(S.wv.drop && S.wv.add && myRosterKeys().includes(S.wv.drop) && availableNow().includes(S.wv.add)); }
  const lastName = n => { const parts = String(n).trim().split(/\s+/); return parts.length > 1 ? parts.slice(1).join(' ') : parts[0]; };
  function renderWaivers() {
    const roster = myRosterKeys(), sug = suggestion(), bench = benchSet();
    if (!S.wv.drop || !roster.includes(S.wv.drop)) S.wv.drop = sug ? sug.k : null;
    if (S.wv.add && !availableNow().includes(S.wv.add)) S.wv.add = null;
    const drop = S.wv.drop;
    $('wv-suggest').textContent = sug ? 'Suggested: ' + sug.label : '';
    const opt = k => { const v = rec(k); return `<label class="wv-opt"><input type="radio" name="wv-drop" value="${esc(k)}"${k === drop ? ' checked' : ''}><span>${esc(v.n)}<small>${esc(v.pos)}</small></span>${sug && k === sug.k ? '<small class="wv-sugg-tag">Suggested</small>' : ''}<span class="wv-opt-val">${fmt(v.ddf)}<span class="sr-action"> DDF</span></span></label>`; };
    const byLow = (a, b) => (rec(a).ddf ?? -1) - (rec(b).ddf ?? -1) || nm(a).localeCompare(nm(b));
    const benchKeys = roster.filter(k => bench.has(k)).sort(byLow), starters = roster.filter(k => !bench.has(k)).sort(byLow);
    $('wv-roster').innerHTML = benchKeys.length ? `<p class="wv-group" aria-hidden="true">Bench · DDF</p>${benchKeys.map(opt).join('')}<p class="wv-group" aria-hidden="true">Starters · DDF</p>${starters.map(opt).join('')}` : `<p class="wv-group" aria-hidden="true">Your roster · DDF</p>${starters.map(opt).join('')}`;
    const avail = availableNow(), n = avail.length, empty = !n;
    $('wv-count').innerHTML = empty ? '' : `${n} available player${n === 1 ? '' : 's'} entered · <a href="waivers.html">Manage list</a>`;
    $('wv-empty').hidden = !empty; $('wv-filters').hidden = empty; $('wv-adds').hidden = empty;
    if (empty) { $('wv-adds').innerHTML = ''; return; }
    const positions = POS_ORDER.filter(pos => avail.some(k => rec(k).pos === pos));
    if (S.wv.pos !== 'All' && !positions.includes(S.wv.pos)) S.wv.pos = 'All';
    $('wv-pos').innerHTML = '<span class="wv-chip-label" aria-hidden="true">Position</span>' + ['All'].concat(positions).map(pos => `<button type="button" data-pos="${pos}" aria-pressed="${S.wv.pos === pos}">${pos}</button>`).join('');
    document.querySelectorAll('[data-min]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.min === S.wv.min)));
    const rows = boardRows(), best = rows.find(r => r.pass), dropShort = lastName(nm(drop)), dv = rec(drop);
    $('wv-adds').innerHTML = rows.map(r => {
      const isBest = r === best, isPicked = S.wv.add === r.key, reason = reasonFor(r, drop);
      let meta, hero, act = '';
      if (r.gain === null) {
        meta = fitBase() ? `No DDF Value for ${esc(r.n)} this week, so this add is not evaluated.` : 'This week\'s bench share is not available yet, so adds are not evaluated.';
        hero = '<span class="wv-gain" aria-hidden="true">—</span><span class="wv-gain-lab">Not evaluated</span>';
      } else {
        meta = (r.pass ? '' : `<strong>${r.gain > 0.05 ? 'Below your ' + minText() + ' filter' : 'No gain over ' + esc(dropShort)}</strong> · `) +
          `Value vs ${esc(dropShort)} (DDF ${fmt(dv.ddf)}): ${r.gain >= 0 ? '+' : '−'}${Math.abs(r.gain).toFixed(1)} DDF Value to your roster (starters in full, bench weighted)` + (reason && !isBest ? ' · ' + esc(reason) : '');
        hero = `<span class="wv-gain">${r.gain >= 0 ? '+' : '−'}<span data-gain="${Math.abs(r.gain).toFixed(1)}">${Math.abs(r.gain).toFixed(1)}</span></span><span class="wv-gain-lab">gain vs ${esc(dropShort)}</span>`;
        act = `<div class="wv-act"><button type="button" class="${r.pass && !isPicked ? 'primary' : ''}" data-pick="${esc(r.key)}" aria-pressed="${isPicked}" aria-label="${isPicked ? 'Picked' : r.pass ? 'Pick this add' : 'Check anyway'}: ${esc(r.n)}">${isPicked ? '✓ Picked' : r.pass ? 'Pick this add' : 'Check anyway'}</button></div>`;
      }
      return `<li class="wv-add${isBest ? ' is-best' : ''}${r.pass ? '' : ' is-dim'}${isPicked ? ' is-picked' : ''}"><div class="wv-main">${isBest ? `<p class="wv-tag">★ BEST ADD${reason ? ' · ' + esc(reason) : ''}</p>` : ''}<h3 class="wv-name">${esc(r.n)}<small>${esc(r.pos)} · available</small></h3><p class="wv-meta">${meta}</p></div><div class="wv-gainbox">${hero}</div>${act}</li>`;
    }).join('') || '<li class="wv-meta">No available players at this position.</li>';
    const pass = rows.filter(r => r.pass).length, below = rows.filter(r => r.gain !== null && !r.pass).length, unrated = rows.filter(r => r.gain === null).length;
    $('wv-filter-note').textContent = (pass ? `${pass} add${pass === 1 ? ' clears' : 's clear'} your ${minText()} filter for ${nm(drop)}` : `No add clears your ${minText()} filter for ${nm(drop)}. Lower the minimum gain or try another drop`) +
      (below ? ` · ${below} below it` : '') + (unrated ? ` · ${unrated} not evaluated (no DDF Value)` : '') + '.';
    const key = drop + '|' + S.wv.pos;
    if (S.wv.countKey !== key) { S.wv.countKey = key; if (window.DDF && DDF.countUp) $('wv-adds').querySelectorAll('[data-gain]').forEach(el => DDF.countUp(el, el.dataset.gain, {decimals: 1, duration: 800})); }
  }
  function renderWaiverCharts() {
    const drop = rec(S.wv.drop), add = rec(S.wv.add), gain = gainFor(drop.key, add.key);
    const sources = [];
    for (const [, name, value] of SOURCES) { const d = value(drop), a = value(add); if (finite(d) && finite(a)) sources.push({name, give: [{n: drop.n, v: d}], receive: [{n: add.n, v: a}]}); }
    if (gain === null || !sources.length) {
      window.DDF_TC.render($('charts'), {sources: [], emptyText: `There is no DDF Value yet for dropping ${drop.n} to add ${add.n}, so there is no chart to draw.`});
      return;
    }
    const worth = gain > 0.05 && gain >= S.wv.min;
    const g = (gain >= 0 ? '+' : '−') + Math.abs(gain).toFixed(1);
    window.DDF_TC.render($('charts'), {sources, mainSourceIndex: 0,
      verdict: {lead: 'Player for player:', tail: `· your roster ${g} DDF Value with this move: ${worth ? 'worth the move' : 'not worth the move' + (gain > 0.05 ? ` (below your ${minText()} filter)` : '')}`, tone: worth ? 'pos' : gain > 0.05 ? 'even' : 'neg'},
      note: `The chart compares the two players' own values. The roster change (${g}) counts your starters in full and your bench at its weights, so it can differ from the player-for-player difference.`});
  }
  const posTag = k => { const p = rec(k).pos; return p ? ' (' + p + ')' : ''; };
  function writeClaim() { $('claim').value = `Waiver claim: add ${nm(S.wv.add)}${posTag(S.wv.add)}, drop ${nm(S.wv.drop)}${posTag(S.wv.drop)}.`; S.claimDirty = false; }

  /* Paste parsing, as waivers.html: "Name · POS" lines, otherwise player names the engine knows found in messy site text. */
  function parseAvailable(text) {
    const names = [...ROWS.values()].map(r => ({n: String(r.name || ''), key: String(r.player_key)})).filter(p => p.n.length >= 5).sort((a, b) => b.n.length - a.n.length);
    const found = new Map();
    let skipped = 0, unmatched = 0;
    for (const raw of String(text).split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) continue;
      const m = /^([A-Za-z][A-Za-z.'’\- ]+?)\s*(?:·|,|\||\t| - | – )\s*(QB|RB|WR|TE|K|DEF|D\/ST)\b/i.exec(line);
      const exact = m ? resolve(m[1]) : resolve(line);
      if (exact && !exact.startsWith('n:')) { found.set(exact, true); continue; }
      let rest = line, hit = false;
      for (const p of names) if (rest.includes(p.n)) { found.set(p.key, true); rest = rest.split(p.n).join(' | '); hit = true; }
      if (!hit) { if (m || /^[A-Z][A-Za-z.'’\-]+(?: [A-Z][A-Za-z.'’\-]+){1,3}$/.test(line)) unmatched++; else skipped++; }
    }
    return {keys: [...found.keys()], skipped, unmatched};
  }

  /* ---------- reference trade charts (published values) ----------
     Each chart's own published numbers (CBS Sports, USA Today, FantasyPros points; FantasyCalc trade value) from the
     engine's inspection, not indexed or adjusted to the league; a filled-in estimate is not published, so it reads
     "Not on this chart". Charts use different scales, so every comparison is a percentage:
     pct = (value they RECEIVE - value they SEND) / value they SEND x 100. "Even" band: |pct| <= 1%. Ranked by pct. */
  const CHARTS = [['cbs', 'CBS Sports'], ['usatoday', 'USA Today'], ['fantasypros', 'FantasyPros'], ['fantasycalc', 'FantasyCalc']];
  const chartName = k => (CHARTS.find(c => c[0] === k) || [])[1] || '';
  const chartGroup = k => k === 'fantasycalc' ? 'live' : 'analyst', CHART_GROUPS = [['analyst', 'Analyst charts'], ['live', 'Live market']];
  const chartFull = k => k === 'fantasycalc' ? 'Live market (' + chartName(k) + ')' : chartName(k);
  const poss = n => /s$/i.test(n) ? n + "'" : n + "'s";
  const chartSrc = k => k === 'fantasycalc' ? poss(chartName(k)) + ' live market values' : poss(chartName(k)) + ' trade chart';
  function cval(k, key) {
    const ins = inspection(), p = ins && ins.players && ins.players[k] && ins.players[k][String(key)];
    return p && !p.estimated && finite(p.native) ? p.native : null;
  }
  const cfmt = (k, v) => k === 'fantasycalc' ? Math.round(v).toLocaleString('en-US') : v.toFixed(1);
  const csum = a => a.reduce((t, v) => t + v, 0);
  function chartEval(k) {
    const g = picked('give'), r = picked('get'), gv = g.map(n => cval(k, n)), rv = r.map(n => cval(k, n));
    const e = {k, name: chartName(k), give: null, get: null, diff: null, tol: null, status: 'missing'};
    if (!g.length || gv.some(v => v === null)) return e;
    e.give = csum(gv);
    if (!r.length) { e.status = 'giveonly'; return e; }
    if (rv.some(v => v === null)) return e;
    e.get = csum(rv);
    if (!(e.get > 0)) return e;
    e.diff = +(e.give - e.get).toFixed(4); e.pct = e.diff / e.get * 100; e.tol = 1;
    e.status = e.pct > e.tol ? 'helps' : e.pct >= -e.tol ? 'even' : 'against';
    return e;
  }
  /* Plain words above the cap (Jeremy, 2026-11-06: "Cap with plain words"): the exact percent up to 25%, "a lot more" above. */
  const PCT_CAP = 25;
  const pctWords = p => Math.round(p) <= PCT_CAP ? Math.round(p) + '% more' : 'a lot more';
  const pctExact = e => e.diff === null ? '' : e.status === 'even' ? 'Within 1% (exact ' + (Math.round(e.pct * 10) / 10) + '%)' : Math.round(Math.abs(e.pct)) + '%';
  function chartLabel(e) {
    if (e.status === 'helps') return `Helps your pitch (they get ${pctWords(e.pct)})`;
    if (e.status === 'even') return 'Even (within 1%)';
    if (e.status === 'against') return `Works against you (they give up ${pctWords(-e.pct)})`;
    if (e.status === 'giveonly') return `Lists your player${picked('give').length > 1 ? 's' : ''} at ${cfmt(e.k, e.give)}`;
    return 'Not on this chart';
  }
  function chartRank() {
    const all = inspection() ? CHARTS.map(c => chartEval(c[0])) : [];
    const scored = all.filter(e => e.diff !== null).sort((a, b) => b.pct - a.pct), rest = all.filter(e => e.diff === null).sort((a, b) => (a.status === 'giveonly' ? 0 : 1) - (b.status === 'giveonly' ? 0 : 1));
    const best = scored.length && scored[0].status === 'helps' ? scored[0].k : null;
    return {list: scored.concat(rest), best};
  }
  function renderChartPick() {
    const sel = $('ref-chart');
    if (!inspection()) { sel.innerHTML = '<option value="">None</option>'; sel.disabled = true; $('chart-live').textContent = 'Trade chart values did not load.'; return; }
    sel.disabled = false;
    const {list, best} = chartRank();
    const opt = e => `<option value="${e.k}"${e.diff !== null ? ` title="${esc(pctExact(e))}"` : ''}>${e.k === best ? 'Best for your pitch · ' : ''}${esc(e.name)}: ${esc(chartLabel(e))}</option>`;
    sel.innerHTML = '<option value="">None</option>' + CHART_GROUPS.map(([g, lab]) => { const items = list.filter(e => chartGroup(e.k) === g); return items.length ? `<optgroup label="${lab}">${items.map(opt).join('')}</optgroup>` : ''; }).join('');
    sel.value = S.chart; if (sel.value !== S.chart) S.chart = '';
    chartLive(best);
  }
  function chartLive(best) {
    const live = $('chart-live'), warn = $('chart-warn');
    warn.hidden = true;
    if (S.chart) {
      const e = chartEval(S.chart);
      warn.hidden = e.status !== 'against';
      if (e.diff !== null) live.textContent = `${chartFull(e.k)}: they receive ${cfmt(e.k, e.give)} and send ${cfmt(e.k, e.get)}, ${e.status === 'even' ? 'about even value' : e.pct > 0 ? `about ${Math.round(e.pct)}% more than they send` : `about ${Math.round(-e.pct)}% less than they send`}. ${chartLabel(e)}.`;
      else if (e.status === 'giveonly') live.textContent = `${chartFull(e.k)}: ${chartLabel(e)}.`;
      else live.textContent = `${chartFull(e.k)}: Not on this chart. The message makes no chart claim.`;
    } else {
      if (best === undefined) best = chartRank().best;
      if (best) { const e = chartEval(best); live.innerHTML = `Best for your pitch: ${esc(chartFull(e.k))} (${esc(chartLabel(e))}). <button type="button" class="linkish" id="chart-best" data-chart="${e.k}">Use ${esc(chartFull(e.k))}</button>`; }
      else live.textContent = 'No chart is picked, so the message makes no chart claim.';
    }
  }
  function claimFor(k) {
    if (!k) return null;
    const e = chartEval(k);
    if (e.status !== 'helps' && e.status !== 'even') return null;   // claims only when the chart's numbers support them
    const nums = `${e.k === 'fantasycalc' ? 'they have' : 'it has'} it at ${cfmt(e.k, e.give)} for ${cfmt(e.k, e.get)}`, pct = Math.round(e.pct);
    const line = e.status === 'even' ? 'you get about even value' : pct <= PCT_CAP ? `you get about ${pct}% more value than you give` : 'you get a lot more value than you give';
    const src = chartSrc(e.k);
    return {k: e.k, status: e.status, text: `${src[0].toUpperCase() + src.slice(1)} ${e.k === 'fantasycalc' ? 'show' : 'shows'} ${line} (${nums}).`};
  }

  /* ---------- the offer message: options by the shape of the offer (build-offer.js, JEG-1559) ---------- */
  function lineupStarters(keys) {
    const X = fitBase();
    if (!X || !keys.length) return null;
    try { return new Set(X.Fd.lineupValue(rowsOf(keys), X.shape, 'ddf_value').starters.map(r => String(r.player_key))); } catch (e) { return null; }
  }
  function offerInput() {
    const userChart = S.chartUser && S.chartUser !== 'none' ? S.chartUser : '';
    const league = S.mode === 'league' && L.available;
    const mine = league ? lineupStarters(myRosterKeys()) : null, theirs = league && S.partner >= 0 ? lineupStarters(L.teams[S.partner].keys) : null;
    const player = (k, starters) => { const p = rec(k); return {n: p.n, pos: p.pos, ddf: p.ddf, an: p.an, starter: starters ? starters.has(k) : null}; };
    const give = picked('give'), get = picked('get');
    const fit = league && S.fit ? {usStarter: S.fit.us.starterDelta, themStarter: S.fit.them.starterDelta, themNeed: S.fit.them.towardAt || []} : null;
    const shopText = (() => {
      if (!userChart || get.length) return '';
      const vs = give.map(k => cval(userChart, k));
      if (!vs.length || vs.some(v => v === null)) return '';
      return ` By ${chartSrc(userChart)} ${give.length > 1 ? "they're" : "he's"} about ${cfmt(userChart, csum(vs))}${give.length > 1 ? ' together' : ''}, so I'm looking for something close.`;
    })();
    const pickedClaim = claimFor(userChart);
    // JEG-1558: each roster's % change (DDFOpportunity.rosterImprovementPct, ddf-opportunity.js) when that module is on
    // the page; not computed here. Without it the message says nothing about roster %.
    const pct = side => {
      const O = window.DDFOpportunity, X = fitBase();
      if (!league || !O || !O.rosterImprovementPct || !X || S.partner < 0) return null;
      try {
        return O.rosterImprovementPct({mine: rowsOf(myRosterKeys()), theirs: rowsOf(L.teams[S.partner].keys), give: rowsOf(give), receive: rowsOf(get)}, side,
          {shape: X.shape, weights: X.weights, chartKeys: X.analyst, senderKey: 'ddf_value', partnerKey: 'chart_avg'});
      } catch (e) { return null; }
    };
    return {give: give.map(k => player(k, mine)), get: get.map(k => player(k, theirs)), league, fit,
      // The value option cites the reader's chart; with none picked, the best chart for the pitch; after an explicit
      // None, no chart (and so no value option). Other pitches cite only a chart the reader picked.
      claim: S.chartUser === 'none' ? null : userChart ? pickedClaim : claimFor(chartRank().best), pickedClaim, shopText,
      // JEG-1561 / JEG-1558 SLOT: the natural-fit rationale (shared explanation module, Workspace agent) and the roster %
      // improvement ("your roster gets x% better", JEG-1558 denominator) go here as {text} once their signatures are
      // published. Never computed on this page; null keeps the line out of the message.
      rationale: null, partner: pct('partner'), sender: pct('sender')};
  }
  let OFFER = null;
  function renderOffer() {
    OFFER = window.DDFOffer.options(offerInput());
    if (!OFFER.options.some(o => o.id === S.style) || !S.userStyle) S.style = OFFER.preselect;
    // "Offer with the numbers" cites a chart: with none picked it uses the best one for the pitch, and the picker says so.
    // The picker shows the chart the message cites: the reader's pick, else (value option on) the best chart, re-picked
    // on every render so a trade change never leaves a stale chart; nothing after an explicit None.
    const userChart = S.chartUser && S.chartUser !== 'none' ? S.chartUser : '';
    const auto = !userChart && S.chartUser !== 'none' && S.style === 'value' ? (offerInput().claim || {}).k || '' : '';
    const want = userChart || auto;
    if (want !== S.chart) { S.chart = want; $('ref-chart').value = S.chart; chartLive(); }
    $('offer-shape').textContent = OFFER.summary;
    $('styles').innerHTML = OFFER.options.map(o => `<button type="button" data-style="${o.id}" aria-pressed="${o.id === S.style}"><span class="style-label">${esc(o.label)}</span><small>${esc(o.hint)}</small></button>`).join('');
  }
  function message() { const o = OFFER && OFFER.options.find(x => x.id === S.style); return o ? o.text : ''; }
  function writeMessage() { renderOffer(); $('message').value = message(); S.dirty = false; }

  /* ---------- events ---------- */
  function changed() { $('copy-status').textContent = ''; render(); }
  function wire() {
    $('copy').onclick = () => DDF.copyText($('message').value, $('copy-status'), 'Message copied. Ready to paste into your league chat.');
    document.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => {
      if (S.mode === b.dataset.mode) return;
      S.mode = b.dataset.mode; S.dirty = false;
      setUrl(q => q.set('mode', S.mode));
      changed();
    });
    for (const side of ['give', 'get']) {
      $('any-' + side + '-search').oninput = () => renderPick(side);
      $('any-' + side + '-search').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); const first = $('any-' + side + '-results').querySelector('button'); if (first) first.click(); } };
      $('any-' + side + '-results').onclick = e => { const b = e.target.closest('[data-add]'); if (!b) return; S.any[side].push(b.dataset.add); $('any-' + side + '-search').value = ''; changed(); $('any-' + side + '-search').focus(); };
      $('any-' + side + '-chosen').onclick = e => { const b = e.target.closest('[data-remove]'); if (!b) return; S.any[side] = S.any[side].filter(k => k !== b.dataset.remove); changed(); $('any-' + side + '-search').focus(); };
      $(side + '-search').oninput = () => renderChooser(side);
      $(side + '-picker').onclick = e => {
        const b = e.target.closest('button[data-index]'); if (!b) return;
        const k = rosterKeys(side)[Number(b.dataset.index)];
        if (S.lg[side].has(k)) S.lg[side].delete(k); else S.lg[side].add(k);
        changed();
        const again = $(side + '-picker').querySelector(`button[data-index="${b.dataset.index}"]`); if (again) again.focus();
      };
      const toggle = document.querySelector(`[aria-controls="${side}-outside"]`);
      toggle.onclick = () => { const panel = $(side + '-outside'), open = panel.hidden; panel.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); if (open) $(side + '-outside-search').focus(); };
      $(side + '-outside-search').oninput = () => renderOutside(side);
      $(side + '-outside-results').onclick = e => { const b = e.target.closest('[data-add]'); if (!b) return; addExtra(side, b.dataset.add); S.lg[side].add(b.dataset.add); $(side + '-outside-search').value = ''; changed(); };
    }
    $('suggest-give').onclick = () => { const k = $('suggest-give').dataset.key; if (k && !S.any.give.includes(k)) S.any.give.push(k); changed(); $('any-get-search').focus(); };
    $('partner').onchange = () => { S.partner = Number($('partner').value); S.lg.get = new Set(); $('get-search').value = ''; changed(); };
    $('your-valuation').onchange = () => changed();
    $('their-valuation').onchange = () => changed();
    $('styles').onclick = e => { const b = e.target.closest('[data-style]'); if (!b) return; S.style = b.dataset.style; S.userStyle = true; writeMessage(); const again = $('styles').querySelector(`[data-style="${b.dataset.style}"]`); if (again) again.focus(); };
    $('ref-chart').onchange = () => { S.chart = $('ref-chart').value; S.chartUser = S.chart || 'none'; chartLive(); writeMessage(); };
    $('chart-live').onclick = e => { const b = e.target.closest('#chart-best'); if (!b) return; S.chart = b.dataset.chart; S.chartUser = S.chart; $('ref-chart').value = S.chart; chartLive(); writeMessage(); $('ref-chart').focus(); };
    document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('details.info[open]').forEach(d => { d.open = false; d.querySelector('summary').focus(); }); });
    document.addEventListener('click', e => { document.querySelectorAll('details.info[open]').forEach(d => { if (!d.contains(e.target)) d.open = false; }); });
    $('message').oninput = () => { S.dirty = true; }; $('regenerate').onclick = writeMessage;

    document.querySelectorAll('[data-pick-kind]').forEach(b => b.onclick = () => {
      if (S.kind === b.dataset.pickKind) return;
      S.kind = b.dataset.pickKind;
      setUrl(q => { q.delete('tab'); if (S.kind === 'waivers') q.set('waivers', '1'); else q.delete('waivers'); });
      changed();
    });
    $('wv-to-league').onclick = () => { S.mode = 'league'; setUrl(q => q.set('mode', 'league')); changed(); $('wv-drop-title').focus(); };
    $('wv-roster').onchange = e => { if (e.target.name !== 'wv-drop') return; S.wv.drop = e.target.value; S.wv.add = null; S.claimDirty = false; changed(); const again = $('wv-roster').querySelector('input:checked'); if (again) again.focus(); };
    document.querySelectorAll('[data-min]').forEach(b => b.onclick = () => { S.wv.min = +b.dataset.min; changed(); b.focus(); });
    $('wv-pos').onclick = e => { const b = e.target.closest('[data-pos]'); if (!b) return; S.wv.pos = b.dataset.pos; changed(); const again = $('wv-pos').querySelector(`[data-pos="${b.dataset.pos}"]`); if (again) again.focus(); };
    $('wv-adds').onclick = e => {
      const b = e.target.closest('[data-pick]'); if (!b) return;
      S.wv.add = S.wv.add === b.dataset.pick ? null : b.dataset.pick; S.claimDirty = false; changed();
      const again = $('wv-adds').querySelector(`[data-pick="${CSS.escape(b.dataset.pick)}"]`); if (again) again.focus();
    };
    $('claim').oninput = () => { S.claimDirty = true; };
    $('wv-copy').onclick = () => DDF.copyText($('claim').value, $('wv-copy-status'), 'Claim note copied.');
    $('wv-confirm').onclick = () => {
      if (!waiverReady()) return;
      const drop = S.wv.drop, add = S.wv.add;
      undoLog.push({players: W.players.slice(), roster: W.roster ? W.roster.slice() : null, drop, add});
      W.roster = myRosterKeys().filter(k => k !== drop).concat([add]);
      W.players = W.players.filter(k => k !== add).concat([drop]);
      S.lg.give.delete(drop); saveWaivers(false); gainCache.clear();
      S.wv.add = null; S.wv.drop = null; $('wv-copy-status').textContent = '';
      $('wv-move-status').textContent = `Roster updated in this tab: added ${nm(add)}, dropped ${nm(drop)}. ${nm(drop)} is now in your available players.`;
      $('wv-undo').hidden = false; changed(); $('wv-undo').focus();
    };
    $('wv-undo').onclick = () => {
      const last = undoLog.pop(); if (!last) return;
      W.players = last.players; W.roster = last.roster; saveWaivers(false); gainCache.clear();
      S.wv.drop = last.drop; S.wv.add = last.add; S.claimDirty = false;
      $('wv-move-status').textContent = `Undone: ${nm(last.add)} is back in your available players and ${nm(last.drop)} is back on your roster.`;
      $('wv-undo').hidden = !undoLog.length; changed(); ($('wv-confirm').offsetParent ? $('wv-confirm') : $('wv-drop-title')).focus();
    };
    $('wv-open-entry').onclick = () => { const panel = $('wv-entry'), open = panel.hidden; panel.hidden = !open; $('wv-open-entry').setAttribute('aria-expanded', String(open)); if (open) $('wv-paste').focus(); };
    $('wv-paste-add').onclick = () => {
      const text = $('wv-paste').value;
      if (!text.trim()) { $('wv-paste-status').textContent = 'Paste or type at least one player.'; return; }
      const {keys, skipped, unmatched} = parseAvailable(text), mine = new Set(myRosterKeys()), have = new Set(W.players);
      const fresh = keys.filter(k => !mine.has(k) && !have.has(k)), onRoster = keys.filter(k => mine.has(k)).length;
      const tail = (unmatched ? `, ${unmatched} name${unmatched === 1 ? '' : 's'} not found in this week's values` : '') + (skipped ? `, ${skipped} line${skipped === 1 ? '' : 's'} skipped` : '');
      if (!fresh.length) { $('wv-paste-status').textContent = 'No new players found' + (onRoster ? ` (${onRoster} already on your roster)` : '') + tail + '. Check the text and try again.'; return; }
      W.players = W.players.concat(fresh); saveWaivers(true);
      $('wv-paste').value = ''; $('wv-paste-status').textContent = '';
      $('wv-move-status').textContent = `${fresh.length} available player${fresh.length === 1 ? '' : 's'} added` + (onRoster ? `, ${onRoster} already on your roster` : '') + tail + '.';
      changed(); $('wv-board-title').focus();
    };
    document.querySelectorAll('[data-wv-provider]').forEach(b => b.onclick = () => {
      document.querySelectorAll('[data-wv-provider]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      document.querySelectorAll('[data-wv-walkthrough]').forEach(w => { w.hidden = w.dataset.wvWalkthrough !== b.dataset.wvProvider; });
    });
    const wrap = document.querySelector('.morewrap');
    if (wrap) {
      const menuButton = wrap.querySelector('button');
      new MutationObserver(() => menuButton.setAttribute('aria-expanded', String(wrap.classList.contains('open')))).observe(wrap, {attributes: true, attributeFilter: ['class']});
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && wrap.classList.contains('open')) { wrap.classList.remove('open'); menuButton.focus(); } });
    }
  }
  function setUrl(fn) { try { const u = new URL(location.href); fn(u.searchParams); history.replaceState(history.state, '', u); } catch (e) { /* the page still works */ } }

  /* A link to the trade charts (build.html?give=..&get=..#trade-charts, from the "N/4 public trade charts" labels):
     the section appears only once the trade renders, so the browser's own jump misses it. Scroll there after the
     render, below the sticky header (and the sub-nav when it is shown). A visit without the anchor is unchanged. */
  const CHARTS_ANCHOR = /^#trade-charts(\?|$)/;
  let scrolledToCharts = false;
  function scrollToChartsIfLinked() {
    const el = $('trade-charts');
    if (scrolledToCharts || !CHARTS_ANCHOR.test(location.hash) || !el || el.hidden || $('result').hidden) return;
    const stuck = [...document.querySelectorAll('header, .subnav')].filter(n => n.offsetParent !== null && /sticky|fixed/.test(getComputedStyle(n).position));
    const offset = stuck.reduce((t, n) => t + n.getBoundingClientRect().height, 0) + 12;
    const top = el.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({top: Math.max(0, top), behavior: 'auto'});
    scrolledToCharts = true;
  }

  /* ---------- start ---------- */
  wire();
  if (!E()) { $('build-status').textContent = 'The value engine did not load. Reload the page to try again.'; return; }
  E().ready.then(c => Promise.resolve(window.DDF && DDF.league && DDF.league.ready ? DDF.league.ready.catch(() => null) : null).then(() => c)).then(c => {
    C = c;
    reindex();
    const league = linkLeague(linkParams());
    if (league) { E().applyVisit(league); linkNote = `Opened with the link's league settings: ${settingsText()} (this visit only).`; }
    init();
    document.body.classList.add('build-live');
    requestAnimationFrame(scrollToChartsIfLinked);
    let busy = false;
    E().on(() => { if (busy) return; busy = true; try { gainCache.clear(); reindex(); render(); } finally { busy = false; } });
    if (window.DDF && DDF.link && DDF.link.ready) DDF.link.ready.then(r => { if (r && r.source === 'link' && !r.error) { init(); requestAnimationFrame(scrollToChartsIfLinked); } });
  }).catch(err => { console.error(err); $('build-status').textContent = 'The value engine did not load. Reload the page to try again.'; });

  window.DDFBuild = {state: () => S, picked, rec, tradeSources, chartEval, gainFor, league: () => L, offer: () => OFFER, offerInput};
})();
