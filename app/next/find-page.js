/* find.html: Trade & Waiver Recommendations on the live engine (JEG-1539, lane "find").
 *
 * Every number on the page is the output of the live modules (DDF.find in find-engine.js runs TradeValueFinder and
 * TradeValueWaivers on engine rows). The league is DDF.league (ddf-league.js). This file is the page: filters, the
 * natural fit / partner neutral / force fit sections, waiver pickups, and the Build a Trade hand-off.
 * Display-only controls (partner, fit, sort, repeat cap, page size, minimum gain) never re-run the search; the
 * valuations, players each side, minimum bench and the league itself do.
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var BUILD = "build.html";
  var SOURCE_WORD = {link: "From your chat", pasted: "Pasted", saved: "Saved league"};
  var FIT_WORD = {natural: "Natural fit", neutral: "Partner neutral", force: "Force fit", unjudged: "Fit not judged"};
  var HEAVY_PARTNERS = 5;
  var S = {pageSize: 10, sig: "", groups: [], partners: [], notes: [], pick: {}, token: 0, pickups: null, running: false, cur: null};
  var shown = function (n) { return DDF.find.shown(n); };
  var keyOf = function (r) { return String(r.player_key); };
  var names = function (rows) { return rows.map(function (r) { return r.name; }).join(", "); };

  /* ---------- valuation labels (F08: every basis name follows the selects) ---------- */
  var optText = function (id) { var o = $(id).selectedOptions[0]; return o ? o.text : $(id).value; };
  function basis() { return {you: optText("your-valuation"), them: optText("their-valuation"), yv: $("your-valuation").value, tv: $("their-valuation").value}; }
  var onBasis = function (b) { return /projections$/.test(b) ? b : b === "Analyst charts" ? "the analyst charts" : b === "Live market (FantasyCalc)" ? "live market (FantasyCalc) value" : b + " value"; };
  function updateBasisText() {
    var B = basis();
    $("natural-def").textContent = "Both sides improve: your team on " + onBasis(B.you) + ", their team on " + onBasis(B.them) + ".";
    $("neutral-def").textContent = "Your team improves on " + onBasis(B.you) + "; their team does not get worse on " + onBasis(B.them) + " (within the sources' disagreement).";
    $("force-def").textContent = "Your team improves on " + onBasis(B.you) + ", but their team loses on " + onBasis(B.them) + ". Shown so you can see them; they are a harder sell.";
    $("fit-note").textContent = "Natural fit: both teams improve (you on " + B.you + ", them on " + (B.them === "Analyst charts" ? "the analyst charts" : B.them) + "). Partner neutral: you improve and their side does not get worse. Force fits: they lose; listed only when you pick them.";
    $("sort-ddf").textContent = "Biggest " + B.you + " gain";
    $("sort-note").textContent = "Order offers by how much your starters improve, how much theirs improve, or the biggest " + B.you + " gain.";
  }

  /* ---------- filters ---------- */
  var sizes = function () { return [].slice.call(document.querySelectorAll(".size:checked")).map(function (x) { return +x.value; }); };
  var benchInputs = function () { return [].slice.call(document.querySelectorAll(".menu-panel .cluster input[type=number]")).slice(0, 4); };
  function minBench() { var b = benchInputs(), out = {}; ["QB", "RB", "WR", "TE"].forEach(function (p, i) { out[p] = Math.max(0, +b[i].value || 0); }); return out; }
  var repeatCap = function () { return Math.max(1, +$("repeat").value || 20); };
  function constraintsText() {
    var mb = minBench();
    return "Players each side: " + sizes().join(", ") + "; your valuation: " + optText("your-valuation") + "; their valuation: " + optText("their-valuation")
      + "; partner: " + optText("partner") + "; fit: " + optText("fit") + "; minimum bench QB/RB/WR/TE: " + [mb.QB, mb.RB, mb.WR, mb.TE].join("/") + "; repeat player cap: " + repeatCap() + ".";
  }
  var defaults = {};
  function updateChips() {
    var lab = {"your-valuation": "You: ", "their-valuation": "Them: ", sort: "Sort: ", fit: "Fit: ", partner: "Partner: "}, n = 0;
    var chips = Object.keys(defaults).map(function (id) {
      var el = $(id), o = el.selectedOptions[0], nd = el.value !== defaults[id];
      if (nd) n++;
      return '<button type="button" class="fchip' + (nd ? " nd" : "") + '">' + esc((lab[id] || "") + (o ? o.text : "")) + "</button>";
    });
    var sz = [].slice.call(document.querySelectorAll(".size")), on = sz.filter(function (x) { return x.checked; });
    var szNd = on.map(function (x) { return x.value; }).join(",") !== S.defaultSizes;
    if (szNd) n++;
    chips.push('<button type="button" class="fchip' + (szNd ? " nd" : "") + '">Players each side: ' + esc(on.map(function (x) { return x.value; }).join(", ")) + "</button>");
    $("filter-chips").innerHTML = chips.join("");
    $("filters-n").textContent = n; $("filters-n").hidden = !n;
  }

  /* ---------- the league ---------- */
  function fillContext(cur) {
    var span = document.querySelector(".ctx-strip > span:first-child");
    if (!span) return;
    if (!cur) { span.textContent = "No league yet"; return; }
    var label = DDF.link && DDF.link.settingsLabel ? DDF.link.settingsLabel(cur.settings) : "";
    span.textContent = "My league · " + (SOURCE_WORD[cur.source] || "Your league") + (label ? " · " + label : "");
  }
  function held() { return new Set(DDF.league.held().map(String)); }
  function partners(cur) {
    var skip = new Set(DDF.league.skipped());
    return DDF.league.opponents().filter(function (t) { return !skip.has(t.name) && DDF.find.rowsOf(t).length > 0; });
  }
  // Available players: the list entered on waivers.html (names) when there is one, else the league's (a chat link's list,
  // or every priced player on no roster).
  function available(cur) {
    var saved = DDF.state ? DDF.state.get("available", null) : null;
    var list = saved && Array.isArray(saved.players) ? saved.players : [];
    if (list.length) {
      var recs = DDF.engine.players(), rows = recs.map(function (r) { return r.row; });
      var m = window.TradeValueFinder.matchNames(list.map(function (p) { return {name: p.n, pos: p.pos || ""}; }), rows);
      var byRow = new Map(recs.map(function (r) { return [r.row, r]; }));
      return {source: "entered", entries: m.matched.map(function (row) { var r = byRow.get(row); return {key: r.key, name: r.n, pos: r.pos, team: r.team}; })};
    }
    return {source: cur.waiversFromLink ? "link" : "inferred", entries: cur.waivers.map(function (r) { return {key: r.key, name: r.n, pos: r.pos, team: r.team}; })};
  }

  function flags(state) {
    document.querySelector(".flag-noleague").hidden = state !== "noleague";
    document.querySelector(".flag-noteam").hidden = state !== "noteam";
    document.querySelector(".flag-rosters").hidden = state !== "norosters";
    var off = state === "noleague" || state === "noteam";
    ["sec-natural", "sec-neutral"].forEach(function (id) { $(id).hidden = off || state === "norosters"; });
    $("sec-force").hidden = off || state === "norosters" || $("fit").value !== "force";
    $("sec-waivers").hidden = off;
  }

  /* ---------- the search ---------- */
  function searchSig(cur, ctx, list) {
    var me = DDF.league.myTeam();
    return JSON.stringify([DDF.engine.settings(), DDF.engine.basis(), DDF.engine.overrides.count(), ctx.gate, ctx.analyst, basis().yv, basis().tv, sizes(), minBench(),
      [].concat(held().size ? Array.from(held()).sort() : []), DDF.find.rowsOf(me).map(keyOf),
      list.map(function (t) { return [t.index, t.name, DDF.find.rowsOf(t).map(keyOf)]; })]);
  }
  var wait = function () { return new Promise(function (r) { setTimeout(r, 0); }); };
  async function run(force) {
    var cur = DDF.league.current();
    S.cur = cur;
    fillContext(cur);
    updateBasisText();
    if (!cur) { flags("noleague"); S.groups = []; S.pickups = null; S.partners = []; return finish(); }
    var me = DDF.league.myTeam();
    if (!me) { flags("noteam"); S.groups = []; S.pickups = null; S.partners = []; return finish(); }
    var ctx = DDF.find.context();
    if (!ctx) return;
    var list = partners(cur);
    fillPartners(list);
    fillBench(me, ctx);
    flags(list.length ? "ok" : "norosters");
    runPickups(cur, me, ctx);
    // Four-for-four is too large to search every team at once in a browser: it runs for one chosen partner.
    var heavy = sizes().indexOf(4) >= 0 && list.length > HEAVY_PARTNERS;
    S.heavy = heavy && $("partner").value === "all";
    if (heavy) list = list.filter(function (t) { return String(t.index) === $("partner").value; });
    var sig = searchSig(cur, ctx, list);
    if (!force && sig === S.sig) return render();
    S.sig = sig;
    var token = ++S.token;
    var mine = DDF.find.rowsOf(me), opts = {your: basis().yv, their: basis().tv, sizes: sizes(), minBench: minBench(), held: held()};
    var groups = [], notes = {sanity: 0, guardrail: 0, partial: [], unjudged: false, searchedTop: false};
    S.running = true;
    for (var i = 0; i < list.length; i++) {
      $("search-status").textContent = "Searching " + (i + 1) + " of " + list.length + " teams: " + list[i].name + ".";
      await wait();
      if (token !== S.token) return;
      var res = DDF.find.searchPartner(ctx, mine, DDF.find.rowsOf(list[i]), opts);
      notes.sanity += res.sanityDropped; notes.guardrail += res.guardrailDropped;
      if (res.partial) notes.partial.push(list[i].name);
      if (!res.judged) notes.unjudged = true;
      if (res.searched.mine.searched < res.searched.mine.of || res.searched.theirs.searched < res.searched.theirs.of) notes.searchedTop = true;
      var team = list[i], theirRows = DDF.find.rowsOf(list[i]);
      DDF.find.group(res.trades, opts).forEach(function (g) {
        groups.push(Object.assign(g, {partner: team.name, partnerIndex: team.index, id: team.index + "|" + g.cls + "|" + g.key, mineRows: mine, theirRows: theirRows}));
      });
    }
    if (token !== S.token) return;
    S.running = false;
    S.groups = groups; S.notes = notes; S.partners = list;
    finish();
  }
  function finish() { $("search-status").textContent = statusText(); render(); }
  function statusText() {
    if (!S.cur || !DDF.league.myTeam()) return "";
    var n = S.notes || {}, parts = [];
    if (S.heavy) return "Four players each side is searched one partner at a time. Pick a partner to search.";
    if (S.partners.length) parts.push("Searched " + S.partners.length + (S.partners.length === 1 ? " team" : " teams") + (DDF.league.skipped().length ? " (skipped teams left out)" : "") + ".");
    if (n.guardrail) parts.push(n.guardrail + (n.guardrail === 1 ? " trade was" : " trades were") + " left out by your minimum bench.");
    if (n.sanity) parts.push(n.sanity + (n.sanity === 1 ? " trade was" : " trades were") + " left out because a starting lineup would be short at a position.");
    if (n.searchedTop) parts.push("Large rosters are searched among each team's top players by your valuation.");
    if (n.partial && n.partial.length) parts.push("Partial roster: " + n.partial.join(", ") + ".");
    if (n.unjudged) parts.push("Fit is not judged: not enough analyst charts are available this week.");
    if (held().size) parts.push("Players you hold are left out.");
    return parts.join(" ");
  }

  /* ---------- results ---------- */
  function selected(g) { var i = S.pick[g.id] || 0; return g.trades[i] || g.best; }
  function sorter() {
    var by = $("sort").value;
    var val = function (t) { return by === "partner" ? t.them : by === "ddf" ? t.edge : t.you; };
    return function (a, b) {
      var ta = selected(a), tb = selected(b), va = val(ta), vb = val(tb);
      if (va === null && vb !== null) return 1;
      if (vb === null && va !== null) return -1;
      return (vb || 0) - (va || 0) || tb.edge - ta.edge || tb.score - ta.score || a.partner.localeCompare(b.partner) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    };
  }
  // The groups the page lists, in order, after the display filters (partner, fit, repeat cap, page size).
  function visible() {
    var partner = $("partner").value, fit = $("fit").value;
    var pool = S.groups.filter(function (g) { return partner === "all" || String(g.partnerIndex) === partner; });
    var cls = function (c) { return pool.filter(function (g) { return g.cls === c; }).sort(sorter()); };
    var nat = fit === "all" || fit === "natural" ? cls("natural") : [];
    var neu = fit === "all" || fit === "neutral" ? cls("neutral").concat(cls("unjudged")) : [];
    var frc = fit === "force" ? cls("force") : [];
    // The repeat cap runs over the list in page order; "Show 10 / 50 / 200" then applies to each section.
    var used = {}, cap = repeatCap(), out = [], per = {};
    nat.concat(neu, frc).forEach(function (g) {
      var t = selected(g), players = t.give.concat(t.receive).map(keyOf);
      if (players.some(function (k) { return (used[k] || 0) >= cap; })) return;
      players.forEach(function (k) { used[k] = (used[k] || 0) + 1; });
      var sec = g.cls === "unjudged" ? "neutral" : g.cls;
      per[sec] = (per[sec] || 0) + 1;
      if (per[sec] <= S.pageSize) out.push(g);
    });
    return {list: out, forceHidden: fit === "force" ? 0 : cls("force").length};
  }
  function recOf(row) { return {key: keyOf(row), n: row.name}; }
  function hrefFor(t) { return DDF.engine.buildHref({give: t.give.map(recOf), get: t.receive.map(recOf)}); }
  // JEG-1560 (Jeremy 2026-11-07): the chart count is a link to Build a Trade for this trade, scrolled to its charts
  // (build.html?give=..&get=..#trade-charts, the anchor JEG-1559 adds). Same count: charts even or better for them.
  function chartsHref(t) { return hrefFor(t) + "#trade-charts"; }
  function chartsLink(t) {
    return '<a class="charts-link" data-charts href="' + esc(chartsHref(t)) + '" aria-label="See the ' + t.rivalOkCount + " of " + t.chartCount
      + ' public trade charts for this trade">' + t.rivalOkCount + "/" + t.chartCount + " public trade charts</a>";
  }
  function card(g, k, mx) {
    var B = basis(), t = selected(g);
    var pct = function (v) { return v === null ? "0" : Math.max(0, Math.min(100, v / mx * 100)).toFixed(1); };
    var giveCell = g.trades.length > 1
      ? '<select aria-label="You give, for ' + esc(names(g.heavy)) + '" data-group="' + esc(g.id) + '">' + g.trades.map(function (x, i) {
        var extra = x.receive.length !== g.heavy.length ? " for " + names(x.receive) : "";
        return '<option value="' + i + '"' + (x === t ? " selected" : "") + ">" + esc(names(x.give) + extra) + "</option>";
      }).join("") + "</select>"
      : "<b>" + esc(names(t.give)) + "</b>";
    var gets = t.receive.map(function (r) { return esc(r.name) + " · " + esc(r.pos); }).join("<br>");
    var throwIns = t.throwIns ? t.throwIns.give.concat(t.throwIns.receive) : [];
    var added = (t.addedThrowIns || []).map(function (a) { return a.row.name + (a.side === "give" ? " (you add)" : " (they add)"); });
    var you = t.you, them = t.them;
    return '<article class="pkg ddf-lift" style="--d:' + (k * 40) + 'ms" data-offer data-cls="' + g.cls + '" data-partner="' + esc(g.partner)
      + '" data-give="' + esc(t.give.map(keyOf).join(",")) + '" data-receive="' + esc(t.receive.map(keyOf).join(","))
      + '" data-you="' + (you === null ? "" : you) + '" data-them="' + (them === null ? "" : them) + '" data-edge="' + t.edge + '">'
      + '<div class="pk-main"><div class="pk-ex"><div class="pk-side"><small>You give</small>' + giveCell + '</div><span class="pk-arrow" aria-hidden="true">&rarr;</span>'
      + '<div class="pk-side"><small>You get</small><b>' + gets + "</b></div></div>"
      + '<div class="pk-meta"><span class="ptag">' + esc(g.partner) + '</span><span class="fit">' + FIT_WORD[g.cls] + "</span>"
      + '<span class="fit">' + chartsLink(t) + " even or better for them</span></div>"
      + (added.length ? '<p class="muted pk-note">Players even out: ' + esc(added.join(", ")) + ".</p>" : "")
      + (throwIns.length ? '<p class="muted pk-note">Also seen with ' + esc(names(throwIns)) + " (worth 0.0) added.</p>" : "")
      + (t.unbalanced ? '<p class="muted pk-note">Uneven player counts: the team getting more players has no bench player left to add.</p>' : "")
      + (window.DDFWhy && t.fit ? '<details class="why" data-why data-group="' + esc(g.id) + '"><summary aria-label="Why this offer: ' + esc(names(t.give)) + " for " + esc(names(t.receive)) + '">Why</summary><div class="why-slot"></div></details>' : "")
      + "</div>"
      + '<div class="pk-gain"><small>Your starters (' + esc(B.you) + ')</small><b class="gain" data-shown="' + (you === null ? "" : shown(you)) + '">' + (you === null ? "—" : shown(you)) + "</b>"
      + '<div class="meter" role="img" aria-label="Your starters ' + (you === null ? "no value" : shown(you)) + " on " + esc(B.you) + "; their starters " + (them === null ? "no value" : shown(them)) + " on " + esc(B.them) + '"><span class="ml"><i data-grow style="width:' + pct(you) + '%"></i></span><span class="mr"><i data-grow style="width:' + pct(them) + '%"></i></span></div>'
      + '<div class="mlab"><span>You ' + (you === null ? "—" : shown(you)) + " " + esc(B.you) + "</span><span>Them " + (them === null ? "—" : shown(them)) + " " + esc(B.them) + "</span></div>"
      + '<small class="pk-total">Trade value ' + shown(t.edge) + " " + esc(B.you) + "</small></div>"
      + '<div class="pk-act"><a class="button" data-build href="' + esc(hrefFor(t)) + '">Build a Trade <span class="arr" aria-hidden="true">&rarr;</span></a></div></article>';
  }
  // JEG-1561: the Why panel, filled on first open from DDFWhy (ddf-why.js) on the same rows and valuations as the card.
  function whyFill(det) {
    var g = S.groups.filter(function (x) { return x.id === det.dataset.group; })[0];
    var slot = det.querySelector(".why-slot");
    if (!g || !slot || slot.dataset.filled === "1") return;
    var t = selected(g), B = basis(), ctx = Object.assign({}, DDF.find.context(), {ourKey: DDF.find.valuation(B.yv).key, marketKey: DDF.find.valuation(B.tv).key});
    slot.innerHTML = window.DDFWhy.body({mine: g.mineRows, theirs: g.theirRows, give: t.give, receive: t.receive}, ctx,
      {extra: '<p class="why-charts">' + chartsLink(t) + " even or better for them</p>"}) || '<p class="muted">No explanation for this offer yet.</p>';
    slot.dataset.filled = "1";
  }
  function section(id, list, tableId, empty) {
    var mx = Math.max(1, Math.max.apply(null, list.map(function (g) { var t = selected(g); return Math.max(t.you || 0, t.them || 0); }).concat([0])));
    $(id).textContent = list.length + (list.length === 1 ? " offer" : " offers");
    $(tableId).innerHTML = list.length ? '<div class="pkgs">' + list.map(function (g, k) { return card(g, k, mx); }).join("") + "</div>" : '<p class="empty">' + empty + "</p>";
    if (DDF.growBars) DDF.growBars($(tableId));
  }
  var footerTargets = 0;
  function render() {
    updateBasisText();
    updateChips();
    var v = visible();
    var empty = S.running ? "Searching your league." : "No offers clear the bar. Add partners, allow more players each side, or lower the minimum bench.";
    section("natural-count", v.list.filter(function (g) { return g.cls === "natural"; }), "natural-table", empty);
    section("neutral-count", v.list.filter(function (g) { return g.cls === "neutral" || g.cls === "unjudged"; }), "all-table", empty);
    section("force-count", v.list.filter(function (g) { return g.cls === "force"; }), "force-table", empty);
    $("sec-force").hidden = $("fit").value !== "force" || $("sec-natural").hidden;
    $("force-note").textContent = v.forceHidden ? v.forceHidden + (v.forceHidden === 1 ? " force fit is" : " force fits are") + " not listed. Pick Fit: Force fits to see " + (v.forceHidden === 1 ? "it" : "them") + "." : "";
    footerTargets = $("sec-natural").hidden ? 0 : v.list.length;
    var first = v.list[0];
    $("continue").href = first ? hrefFor(selected(first)) : BUILD;
    renderPickups();
  }

  /* ---------- waiver pickups ---------- */
  function runPickups(cur, me, ctx) {
    var av = available(cur);
    S.available = av;
    document.querySelector(".flag-waivers").hidden = av.entries.length > 0;
    S.pickups = av.entries.length ? DDF.find.pickups(ctx, DDF.find.entriesOf(me), av.entries, basis().yv) : null;
  }
  var gainOf = function (r) { return Math.round(r.starterDelta * 10) / 10; };
  function renderPickups() {
    var box = $("pickup-cards"), note = $("pickup-note"), combos = $("pickup-combos");
    var on = $("see-waivers").checked && !$("sec-waivers").hidden;
    var res = S.pickups ? S.pickups.results.filter(function (r) { return r.starterDelta !== null && gainOf(r) > 0; }) : [];
    res.sort(function (a, b) { return b.starterDelta - a.starterDelta || (b.totalDelta || 0) - (a.totalDelta || 0) || String(a.name).localeCompare(String(b.name)); });
    var min = +$("minimum-gain").value;
    var pass = res.filter(function (r) { return gainOf(r) >= min; }), below = res.filter(function (r) { return gainOf(r) < min; });
    var B = basis();
    box.innerHTML = pass.map(function (r) {
      var drop = r.drop ? r.drop.name : null;
      var href = BUILD + "?mode=league&waivers=1" + (drop ? "&drop=" + encodeURIComponent(drop) : "") + "&add=" + encodeURIComponent(r.name);
      return '<article class="pkg ddf-lift" data-pickup data-pickup-gain="' + gainOf(r) + '" data-add="' + esc(r.candidate.player_key) + '" data-drop="' + esc(r.drop ? r.drop.player_key : "") + '">'
        + '<div class="pk-main"><div class="pk-ex"><div class="pk-side"><small>You drop</small><b>' + esc(drop || "Nobody (open roster spot)") + "</b></div>"
        + '<span class="pk-arrow" aria-hidden="true">&rarr;</span><div class="pk-side"><small>You add</small><b>' + esc(r.name) + " · " + esc(r.pos) + "</b></div></div>"
        + '<div class="pk-meta"><span class="ptag wv">Waivers</span><span class="fit">' + esc(r.verdict) + "</span></div></div>"
        + '<div class="pk-gain"><small>Your starters (' + esc(B.you) + ')</small><b class="gain">' + shown(r.starterDelta) + "</b>"
        + '<small class="pk-total">With bench ' + shown(r.totalDelta) + "</small></div>"
        + '<div class="pk-act"><a class="button" href="' + esc(href) + '">Evaluate pickup <span class="arr" aria-hidden="true">&rarr;</span></a></div></article>';
    }).join("");
    var none = !S.pickups ? "" : !res.length ? "No available player improves your starters right now." : "";
    note.textContent = below.length && min > 0
      ? below.length + (below.length === 1 ? " more pickup sits" : " more pickups sit") + " below the " + min + "-point bar: " + below.slice(0, 3).map(function (r) { return r.name + " (" + shown(r.starterDelta) + ")"; }).join(", ") + (below.length > 3 ? " and more" : "") + ". Lower the minimum gain to see " + (below.length === 1 ? "it" : "them") + "."
      : none;
    var src = S.available ? S.available.source : null;
    $("pickup-source").textContent = !S.pickups ? "" : src === "entered" ? "From the available players you entered on Waivers." : src === "link" ? "From the available players in your chat link." : "Available players: everyone with a value who is on no roster in your league.";
    var cs = S.pickups ? S.pickups.combos : [];
    combos.hidden = !cs.length;
    combos.innerHTML = cs.length ? "<summary>Two-for-two pickups (" + cs.length + ")</summary><ul>" + cs.slice(0, 10).map(function (c) { return "<li>" + esc(c.text) + "</li>"; }).join("") + "</ul>" : "";
    $("pickup-count").textContent = pass.length + (pass.length === 1 ? " pickup" : " pickups");
    var p = on ? pass.length : 0, t = footerTargets;
    $("result-count").textContent = t + (t === 1 ? " target" : " targets") + (p ? " · " + p + (p === 1 ? " pickup" : " pickups") : "") + " · alternative give players grouped";
  }

  /* ---------- page wiring ---------- */
  function fillPartners(list) {
    var sel = $("partner"), was = sel.value;
    var sig = list.map(function (t) { return t.index + ":" + t.name; }).join("|");
    if (sel.dataset.sig !== sig) {
      sel.dataset.sig = sig;
      sel.innerHTML = '<option value="all">All partners</option>' + list.map(function (t) { return '<option value="' + t.index + '">' + esc(t.name) + "</option>"; }).join("");
      sel.value = list.some(function (t) { return String(t.index) === was; }) ? was : "all";
    }
  }
  function fillBench(me, ctx) {
    var line = $("bench-line");
    var key = DDF.find.valuation(basis().yv).key;
    var rows = DDF.find.rowsOf(me);
    if (DDF.find.valuation(basis().yv).avg && ctx.analyst) rows = window.TradeValueFinder.withChartAverage(rows, ctx.analyst);
    var bench = ctx.shape ? window.TradeValueFinder.pickStarters(rows, ctx.shape, key).bench : [];
    line.textContent = bench.length ? "Bench: " + bench.map(function (r) { return r.name + " (" + r.pos + ")"; }).join(", ") + "." : "Bench: nobody on your bench has a value in this view.";
  }
  function remember(a) {
    var card = a.closest("[data-offer]"); if (!card) return;
    var B = basis();
    try {
      sessionStorage.setItem("ddf-recommendation", JSON.stringify({partner: card.dataset.partner, give: card.dataset.give.split(","), receive: card.dataset.receive.split(","),
        type: card.dataset.cls, constraints: constraintsText(), yourValuation: B.yv, theirValuation: B.tv}));
    } catch (e) { /* the link still carries the players */ }
  }
  function wire() {
    ["your-valuation", "their-valuation", "partner", "fit", "sort"].forEach(function (id) { defaults[id] = $(id).value; });
    S.defaultSizes = [].slice.call(document.querySelectorAll(".size:checked")).map(function (x) { return x.value; }).join(",");
    var rerun = function () { run(false); };
    $("your-valuation").addEventListener("change", rerun);
    $("their-valuation").addEventListener("change", rerun);
    document.querySelectorAll(".size").forEach(function (x) {
      x.addEventListener("change", function () {
        if (!sizes().length) x.checked = true;   // at least one size
        $("sizes-text").textContent = sizes().join(", ");
        rerun();
      });
    });
    ["fit", "sort"].forEach(function (id) { $(id).addEventListener("change", render); });
    $("partner").addEventListener("change", function () { if (sizes().indexOf(4) >= 0) run(false); else render(); });
    $("minimum-gain").addEventListener("change", renderPickups);
    $("see-waivers").addEventListener("change", renderPickups);
    $("apply").addEventListener("click", function () { document.querySelector(".find-constraints").open = false; $("constraint-note").textContent = ""; run(false); });
    $("reset").addEventListener("click", function () {
      document.querySelectorAll(".size").forEach(function (x) { x.checked = S.defaultSizes.split(",").indexOf(x.value) >= 0; });
      $("sizes-text").textContent = sizes().join(", ");
      Object.keys(defaults).forEach(function (id) { $(id).value = defaults[id]; });
      benchInputs().forEach(function (x) { x.value = 0; });
      $("repeat").value = 20;
      run(false);
    });
    $("repeat").addEventListener("change", render);
    document.querySelectorAll("[data-page-size]").forEach(function (b) {
      b.addEventListener("click", function () {
        S.pageSize = +b.dataset.pageSize;
        document.querySelectorAll("[data-page-size]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        render();
      });
    });
    document.querySelector(".find-page").addEventListener("change", function (e) {
      var sel = e.target.closest("select[data-group]");
      if (!sel) return;
      S.pick[sel.dataset.group] = +sel.value;
      render();
      var again = document.querySelector('select[data-group="' + (window.CSS && CSS.escape ? CSS.escape(sel.dataset.group) : sel.dataset.group) + '"]');
      if (again) again.focus();
    });
    document.querySelector(".find-page").addEventListener("click", function (e) { var a = e.target.closest("a[data-build]"); if (a) remember(a); });
    document.querySelector(".find-page").addEventListener("toggle", function (e) { if (e.target.matches && e.target.matches("details[data-why]") && e.target.open) whyFill(e.target); }, true);
    var t = $("filters-toggle"), f = $("find-filters");
    var tog = function () { f.hidden = !f.hidden; t.setAttribute("aria-expanded", String(!f.hidden)); };
    t.addEventListener("click", tog);
    $("filter-chips").addEventListener("click", function (e) { if (e.target.closest(".fchip") && f.hidden) tog(); });
    var more = document.querySelector(".morewrap>button");
    if (more) {
      document.addEventListener("click", function () { more.setAttribute("aria-expanded", String(document.querySelector(".morewrap").classList.contains("open"))); });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { document.querySelector(".morewrap").classList.remove("open"); more.setAttribute("aria-expanded", "false"); document.querySelector(".find-constraints").open = false; }
      });
    }
  }

  function start() {
    wire();
    updateBasisText();
    updateChips();
    Promise.all([DDF.engine.ready, DDF.league.ready]).then(function () {
      run(true);
      var timer = null;
      DDF.league.on(function () { clearTimeout(timer); timer = setTimeout(function () { run(false); }, 50); });
    }).catch(function (e) {
      console.error(e);
      $("search-status").textContent = "The values did not load. Reload the page to try again.";
    });
  }
  DDF.findPage = {visible: function () { return visible().list; }, selected: selected, state: S, run: run};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
