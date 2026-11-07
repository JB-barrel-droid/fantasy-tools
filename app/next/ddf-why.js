/* "Why" for one trade (JEG-1561). Shared by find.html (offer cards) and any page that shows a trade.
 *
 * No value math of its own. Every number is TradeValueFinder output on the rows given: lineupValue / pickStarters
 * (starters by slot, before and after, so FLEX / SUPERFLEX re-slotting is visible), tradeFit (the same call
 * find-engine.js makes: starter change, bench change weighted by benchWeight, net, the Natural fit predicate) and
 * withChartAverage when a side is valued on the Analyst charts. This file only compares those outputs and words them.
 * Percent framing comes only from window.DDFOpportunity.rosterImprovementPct (JEG-1558); without it the % slot hides.
 *
 * API: window.DDFWhy
 *   explain(trade, ctx) -> {headline, pct:{sender, partner}|null, natural, needs:{you, them, youSurplus, themSurplus}, table:{give, get, net}, reasons:[{kind, text, amount}],
 *                           you:view, them:view, fit} or null when the inputs are missing or the trade is not judged
 *                           (no depth context, or an Analyst charts valuation without the charts: find-engine's `judged`)
 *     trade: {mine:[row], theirs:[row], give:[row], receive:[row]}  (whole rosters; give leaves mine, receive leaves theirs)
 *     ctx:   DDF.find.context() ({shape, expected, weights, analyst, ...}); optional ourKey (default ddf_value) and
 *            marketKey (default chart_avg when the analyst charts are available, else ourKey)
 *     view:  {key, starterDelta, benchDelta, net, posDelta:{QB,RB,WR,TE}, slots:{QB:{before, after, delta, from:[pos], to:[pos]}..},
 *             arriving:[{row, slot|null}], leaving:[{row, slot|null}], promoted:[{row, slot}], displaced:[row],
 *             emptyBefore, emptyAfter, unvalued:[row]}
 *   text(trade, ctx)    -> plain text of the same explanation (no "DDF", no team names)
 *   html(trade, ctx, opts) -> '<details class="why">..' tap-to-expand panel; opts.id (unique), opts.extra (html after the table)
 *   body(trade, ctx, opts) -> the panel's inside only (a page that renders <details> itself and fills it on first open)
 */
(function () {
  "use strict";
  var F = function () { return window.TradeValueFinder; };
  var POS = ["QB", "RB", "WR", "TE"];
  var SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  var FLOOR = 0.05;   // the display floor every page uses (a change under 0.05 shows as 0.0)
  var finite = function (v) { return typeof v === "number" && isFinite(v); };
  var keyOf = function (r) { return String(r.player_key); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var list = function (a) { return a.length < 2 ? a.join("") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]; };
  var article = function (pos) { return /^[AEFHILMNORSX]/.test(pos) ? "an " + pos : "a " + pos; };
  var shown = function (n) { return !finite(n) ? "—" : Math.abs(n) < FLOOR ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1); };

  function slotOf(picked, row) {
    var k = keyOf(row);
    for (var i = 0; i < SLOTS.length; i += 1) {
      if ((picked.slots[SLOTS[i]] || []).some(function (r) { return keyOf(r) === k; })) return SLOTS[i];
    }
    return null;
  }
  // One team in one point of view: lineupValue before / after, compared slot by slot and by player position.
  function view(roster, leaving, arriving, shape, key, fitSide) {
    var f = F();
    var gone = new Set(leaving.map(keyOf)), arrivingKeys = new Set(arriving.map(keyOf));
    var after = roster.filter(function (r) { return !gone.has(keyOf(r)); }).concat(arriving);
    var b = f.lineupValue(roster, shape, key), a = f.lineupValue(after, shape, key);
    var val = function (r) { return r.values[key]; };
    var sum = function (rows) { return rows.reduce(function (t, r) { return t + val(r); }, 0); };
    var slots = {};
    SLOTS.forEach(function (s) {
      if (!(shape && shape[s])) return;
      var bs = b.slots[s] || [], as = a.slots[s] || [];
      slots[s] = {before: sum(bs), after: sum(as), delta: sum(as) - sum(bs),
        from: bs.map(function (r) { return r.pos; }), to: as.map(function (r) { return r.pos; })};
    });
    var posDelta = {};
    POS.forEach(function (p) {
      var at = function (l) { return sum(l.starters.filter(function (r) { return r.pos === p; })); };
      posDelta[p] = at(a) - at(b);
    });
    var bStart = new Set(b.starters.map(keyOf)), aStart = new Set(a.starters.map(keyOf));
    var empty = function (l) { return Object.keys(l.empty).reduce(function (t, s) { return t + l.empty[s]; }, 0); };
    return {key: key,
      starterDelta: fitSide ? fitSide.starterDelta : a.starterValue - b.starterValue,
      benchDelta: fitSide ? fitSide.benchDelta : null,   // bench weighted by benchWeight (tradeFit); null when not judged
      net: fitSide ? fitSide.net : null,
      posDelta: posDelta, slots: slots,
      arriving: arriving.map(function (r) { return {row: r, slot: slotOf(a, r), valued: finite(r.values && r.values[key])}; }),
      leaving: leaving.map(function (r) { return {row: r, slot: slotOf(b, r), valued: finite(r.values && r.values[key])}; }),
      promoted: a.starters.filter(function (r) { return !bStart.has(keyOf(r)) && !arrivingKeys.has(keyOf(r)); }).map(function (r) { return {row: r, slot: slotOf(a, r)}; }),
      displaced: b.starters.filter(function (r) { return !aStart.has(keyOf(r)) && !gone.has(keyOf(r)); }),
      emptyBefore: empty(b), emptyAfter: empty(a),
      unvalued: leaving.concat(arriving).filter(function (r) { return !(r.values && finite(r.values[key])); })};
  }

  function keys(ctx) {
    var our = ctx.ourKey || "ddf_value";
    var market = ctx.marketKey || (ctx.analyst ? F().MARKET_KEY : our);
    return {our: our, market: market, avg: our === F().MARKET_KEY || market === F().MARKET_KEY};
  }
  // Need and surplus come from tradeFit's own depth readout (teamFit depth / towardAt / awayAt against the league's
  // expected players per position), not from value: a need is a position a side receives at where its depth moves toward
  // the expected range (it was short); a surplus is a position it gives from without going away from the range or
  // ending short (it had one to spare). No value math here.
  function depthNeeds(side, received) {
    if (!side || !side.ready) return [];
    return POS.filter(function (p) { return received.indexOf(p) >= 0 && side.towardAt.indexOf(p) >= 0; });
  }
  function depthSurplus(side, given) {
    if (!side || !side.ready) return [];
    return POS.filter(function (p) { var d = side.depth[p]; return given.indexOf(p) >= 0 && d && side.awayAt.indexOf(p) < 0 && d.statusAfter !== "under"; });
  }
  var positionsOf = function (rows) { return POS.filter(function (p) { return rows.some(function (r) { return r.pos === p; }); }); };
  function flexMoves(v) {
    return ["FLEX", "SUPERFLEX"].filter(function (s) {
      var x = v.slots[s];
      return x && x.from.slice().sort().join() !== x.to.slice().sort().join() && x.from.length && x.to.length;
    }).map(function (s) { return {slot: s, from: v.slots[s].from, to: v.slots[s].to, delta: v.slots[s].delta}; });
  }
  function benchShift(v) {
    // bench players by position, before vs after: who leaves the bench or joins it (no values, just counts)
    var moved = {};
    v.leaving.forEach(function (x) { if (!x.slot) moved[x.row.pos] = (moved[x.row.pos] || 0) - 1; });
    v.arriving.forEach(function (x) { if (!x.slot) moved[x.row.pos] = (moved[x.row.pos] || 0) + 1; });
    v.promoted.forEach(function (x) { moved[x.row.pos] = (moved[x.row.pos] || 0) - 1; });
    v.displaced.forEach(function (r) { moved[r.pos] = (moved[r.pos] || 0) + 1; });
    return {thinner: POS.filter(function (p) { return moved[p] < 0; }), deeper: POS.filter(function (p) { return moved[p] > 0; })};
  }
  var role = function (x) { return x.slot ? "starts at " + x.slot : x.valued ? "bench" : "no value yet"; };
  var roleBefore = function (x) { return x.slot ? "a starter at " + x.slot : x.valued ? "bench" : "no value yet"; };

  function reasons(you, them, trade, needs) {
    var out = [];
    var gone = you.unvalued.concat(them.unvalued.filter(function (r) { return you.unvalued.indexOf(r) < 0; }));
    if (gone.length) out.push({kind: "unvalued", amount: Infinity,
      text: list(gone.map(function (r) { return r.name; })) + (gone.length === 1 ? " has" : " have") + " no value yet, so " + (gone.length === 1 ? "it is" : "they are") + " left out here, never counted as 0."});
    POS.forEach(function (p) {
      var x = you.arriving.filter(function (y) { return y.row.pos === p; }).sort(function (a, b) { return (b.slot ? 1 : 0) - (a.slot ? 1 : 0); })[0];
      if (!x) return;
      var need = needs.you.indexOf(p) >= 0, gain = you.posDelta[p] >= FLOOR;
      if (!need && !gain) return;
      var bumped = you.displaced.filter(function (r) { return r.pos === p; })[0];
      var how = !x.slot ? "" : you.emptyBefore > you.emptyAfter ? ", a slot you could not fill before" : bumped ? ", ahead of " + bumped.name : "";
      out.push({kind: need ? "need" : "upgrade", pos: p, amount: Math.max(you.posDelta[p], need ? FLOOR : 0),
        text: (need ? "Fills your " + p + " need: " + x.row.name + (x.slot ? " " + role(x) : " adds " + p + " depth")
          : "Upgrades your " + p + " starters: " + x.row.name + " " + role(x)) + how + "."});
    });
    needs.youSurplus.forEach(function (p) {
      var d = you.fit.depth[p];
      out.push({kind: "surplus", pos: p, amount: FLOOR * 0.6, text: "You have " + p + " to spare: " + d.before + " counted now, " + d.after + " after (" + d.range + " expected)."});
    });
    POS.forEach(function (p) {
      if (!(you.posDelta[p] <= -FLOOR)) return;
      var left = you.leaving.filter(function (x) { return x.row.pos === p && x.slot; }).map(function (x) { return x.row.name; });
      var up = you.promoted.filter(function (x) { return x.row.pos === p; })[0];
      out.push({kind: "loss", pos: p, amount: -you.posDelta[p],
        text: "Your " + p + " starters get weaker" + (left.length ? " without " + list(left) : "") + (up ? "; " + up.row.name + " moves up from the bench" : "") + "."});
    });
    flexMoves(you).forEach(function (m) {
      out.push({kind: "flex", amount: Math.abs(m.delta), text: "Your " + m.slot + " changes from " + list(m.from.map(article)) + " to " + list(m.to.map(article)) + "."});
    });
    if (finite(you.benchDelta) && Math.abs(you.benchDelta) >= FLOOR) {
      var sh = benchShift(you), at = you.benchDelta < 0 ? sh.thinner : sh.deeper;
      out.push({kind: "bench", amount: Math.abs(you.benchDelta),
        text: "Your bench gets " + (you.benchDelta < 0 ? "thinner" : "deeper") + (at.length ? " at " + list(at) : "") + "."});
    }
    var opened = trade.give.length - trade.receive.length;
    if (opened > 0) out.push({kind: "spots", amount: FLOOR / 2,
      text: "You send " + trade.give.length + " players for " + trade.receive.length + ", which opens " + (opened === 1 ? "a roster spot" : opened + " roster spots") + "."});
    needs.them.forEach(function (p) {
      var x = them.arriving.filter(function (y) { return y.row.pos === p; })[0];
      out.push({kind: "partner", pos: p, amount: Math.max(them.posDelta[p], FLOOR), text: "They fill their " + p + " need with " + x.row.name + "."});
    });
    if (finite(them.starterDelta) && them.starterDelta <= -FLOOR) {
      var lost = POS.filter(function (p) { return them.posDelta[p] <= -FLOOR; });
      out.push({kind: "partner-loss", amount: -them.starterDelta, text: "Their starters get weaker" + (lost.length ? " at " + list(lost) : "") + "."});
    }
    return out.sort(function (a, b) { return b.amount - a.amount; });
  }

  // Led by the card's own number (your starters' change); the bench-weighted net is named when it reads differently.
  // Their side is read the way the fit judges it (their roster, bench counted): a gain only past the 0.05 floor,
  // "about even" inside the charts' disagreement (tradeFit's tolerance), never a gain that is not there.
  function headline(you, them, natural, needs) {
    var sign = function (n) { return !finite(n) ? null : n >= FLOOR ? 1 : n <= -FLOOR ? -1 : 0; };
    var ys = sign(you.starterDelta), yn = sign(you.net);
    if (ys < 1 && !(yn === 1)) return "This does not make your team better.";
    var mineText = ys === 1 ? "Your starters get better" : ys === 0 ? "Your starters stay about the same" : "Your starters get weaker";
    if (yn !== null && yn !== ys) mineText += " (counting your bench, your roster " + (yn === 1 ? "gains" : yn === 0 ? "is about even" : "loses") + ")";
    var tn = them.net !== null ? them.net : them.starterDelta, tau = them.fit ? them.fit.tau : FLOOR;
    var theirs = tn >= FLOOR ? "their roster gets better too" : tn >= -tau ? "their roster stays about even, within how much the sources disagree"
      : "their roster gets worse, so it is a harder sell";
    var fill = natural ? ": you fill " + list(needs.you) + " and they fill " + list(needs.them) : "";
    return mineText + (tn >= -tau ? ", and " : ", but ") + theirs + fill + ".";
  }
  function netWords(v) {
    var w = function (n, up, down) { return !finite(n) ? null : n >= FLOOR ? up : n <= -FLOOR ? down : null; };
    var parts = [w(v.starterDelta, "starters better", "starters weaker"), w(v.benchDelta, "bench deeper", "bench thinner")].filter(Boolean);
    return parts.length ? parts.join(", ").replace(/^./, function (c) { return c.toUpperCase(); }) : "About even";
  }
  function pct(trade, ctx) {
    var O = window.DDFOpportunity;
    if (!O || typeof O.rosterImprovementPct !== "function") return null;
    try {
      var s = O.rosterImprovementPct(trade, "sender", ctx), p = O.rosterImprovementPct(trade, "partner", ctx);
      if (!s || !p || !finite(s.pct) || !finite(p.pct)) return null;
      return {sender: s, partner: p, text: "Your roster " + s.shown + ". Theirs " + p.shown + ", " + p.label + "."};
    } catch (e) { console.error(e); return null; }
  }

  function explain(trade, ctx) {
    var f = F();
    if (!f || !trade || !ctx || !ctx.shape || !Array.isArray(trade.mine) || !Array.isArray(trade.theirs)) return null;
    var k = keys(ctx);
    if (!ctx.expected || (k.avg && !ctx.analyst)) return null;   // find-engine's `judged`: no chart average, no depth -> not judged
    var widen = function (rows) { return k.avg && ctx.analyst ? f.withChartAverage(rows, ctx.analyst) : rows; };
    var mine = widen(trade.mine), theirs = widen(trade.theirs);
    var byKey = new Map(mine.concat(theirs).map(function (r) { return [keyOf(r), r]; }));
    var wide = function (rows) { return rows.map(function (r) { return byKey.get(keyOf(r)) || widen([r])[0]; }); };
    var give = wide(trade.give || []), recv = wide(trade.receive || []);
    // The fit exactly as find-engine.js computes it (both sides, Natural fit predicate, bench weighted by benchWeight).
    var fit = f.tradeFit({mine: {roster: mine, leaving: give, arriving: recv}, theirs: {roster: theirs, leaving: recv, arriving: give}},
      {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: k.our, marketKey: k.market, chartKeys: ctx.analyst || undefined, z: f.FIT_Z});
    if (!fit) return null;   // the trade is not judged (find-engine leaves it unjudged): no Why
    var you = view(mine, give, recv, ctx.shape, k.our, fit.us);
    var them = view(theirs, recv, give, ctx.shape, k.market, fit.them);
    you.fit = fit.us; them.fit = fit.them;
    var gp = positionsOf(give), rp = positionsOf(recv);
    var needs = {you: depthNeeds(fit.us, rp), them: depthNeeds(fit.them, gp), youSurplus: depthSurplus(fit.us, gp), themSurplus: depthSurplus(fit.them, rp)};
    // "Natural fit" only when tradeFit's predicate holds AND, for both teams, the side received is a need and the side
    // given is a surplus (tradeFit's depth readout).
    var natural = Boolean(fit.label === "natural" && needs.you.length && needs.youSurplus.length && needs.them.length && needs.themSurplus.length);
    var rs = reasons(you, them, {give: give, receive: recv}, needs);
    var p = pct({mine: trade.mine, theirs: trade.theirs, give: trade.give, receive: trade.receive}, ctx);
    return {headline: headline(you, them, natural, needs), pct: p, natural: natural, needs: needs,
      table: {give: you.leaving.map(function (x) { return {name: x.row.name, pos: x.row.pos, role: roleBefore(x)}; }),
        get: you.arriving.map(function (x) { return {name: x.row.name, pos: x.row.pos, role: role(x)}; }),
        net: netWords(you)},
      reasons: rs.slice(0, 3), allReasons: rs, you: you, them: them, fit: fit};
  }

  function text(trade, ctx) {
    var e = explain(trade, ctx);
    if (!e) return "";
    var side = function (rows) { return rows.map(function (r) { return r.name + " (" + r.pos + ", " + r.role + ")"; }).join(", ") || "nothing"; };
    return [e.natural ? "Natural fit. " + e.headline : e.headline, e.pct ? e.pct.text : null,
      "You give up: " + side(e.table.give), "You get: " + side(e.table.get), "Net: " + e.table.net + "."]
      .concat(e.reasons.map(function (r) { return "- " + r.text; })).filter(Boolean).join("\n");
  }

  var CSS = ".why{margin-top:8px}.why>summary{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 14px;border:1px solid #176c4d;border-radius:99px;color:#176c4d;font-weight:700;font-size:14px;cursor:pointer;list-style:none;background:#fff}"
    + ".why>summary::-webkit-details-marker{display:none}.why>summary::after{content:\"\\25BE\";font-size:12px}.why[open]>summary::after{content:\"\\25B4\"}"
    + ".why>summary:focus-visible,.why .why-raw>summary:focus-visible{outline:3px solid #176c4d;outline-offset:2px}"
    + ".why .why-body{margin-top:8px;padding:12px 14px;border:1px solid #dbe0dc;border-radius:10px;background:#fbfcfb}"
    + ".why .why-head{margin:0 0 6px;font-weight:700;font-size:15px;line-height:1.4}.why .why-tag{display:inline-block;font-size:12px;font-weight:700;border-radius:99px;padding:2px 10px;background:#176c4d;color:#fff;margin-right:8px}"
    + ".why .why-pct{margin:0 0 8px;font-size:14px}.why table{width:100%;border-collapse:collapse;font-size:14px;margin:4px 0 8px}.why th{background:none;text-align:left;font-size:12px;color:#5c6a76;width:7.5em;vertical-align:top;padding:6px 8px 6px 0;border-bottom:1px solid #eef1ec;white-space:normal}"
    + ".why td{padding:6px 0;border-bottom:1px solid #eef1ec;overflow-wrap:anywhere}.why ol{margin:6px 0 4px;padding-left:20px;font-size:14px;line-height:1.45}"
    + ".why .why-raw>summary{display:inline-flex;align-items:center;min-height:44px;color:#176c4d;font-size:13px;font-weight:600;cursor:pointer}.why .why-raw table{font-family:'IBM Plex Mono',monospace;font-size:12.5px}"
    // A host page may restyle tables as phone cards (find.html): the panel's tables stay tables.
    + ".why table{display:table!important}.why tbody{display:table-row-group!important}.why tr{display:table-row!important;padding:0!important;border:0!important}"
    + ".why th,.why td{display:table-cell!important;text-align:left!important}.why td:before{content:none!important;display:none!important}"
    + ".why .why-raw td{white-space:nowrap;overflow-wrap:normal;padding-right:12px}.why .why-charts a{color:#176c4d;font-weight:700}";
  function injectCss() {
    if (document.getElementById("ddf-why-css")) return;
    var s = document.createElement("style");
    s.id = "ddf-why-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }
  function html(trade, ctx, opts) {
    opts = opts || {};
    var e = explain(trade, ctx);
    if (!e) return "";
    if (typeof document !== "undefined") injectCss();
    return '<details class="why"' + (opts.id ? ' id="' + esc(opts.id) + '"' : "") + ' data-why' + (e.natural ? " data-natural" : "") + '><summary>Why</summary>'
      + bodyOf(e, opts) + "</details>";
  }
  // The panel's inside (for a page that renders the <details> itself and fills it on first open).
  function body(trade, ctx, opts) {
    var e = explain(trade, ctx);
    if (!e) return "";
    if (typeof document !== "undefined") injectCss();
    return bodyOf(e, opts || {});
  }
  function bodyOf(e, opts) {
    var side = function (rows) { return rows.map(function (r) { return esc(r.name) + " <small>" + esc(r.pos) + ", " + esc(r.role) + "</small>"; }).join("<br>") || "—"; };
    var you = e.you, them = e.them;
    var raw = '<details class="why-raw"><summary>Show the numbers</summary><table><tr><th></th><td>You</td><td>Them</td></tr>'
      + "<tr><th>Starters</th><td>" + shown(you.starterDelta) + "</td><td>" + shown(them.starterDelta) + "</td></tr>"
      + "<tr><th>Bench (weighted)</th><td>" + shown(you.benchDelta) + "</td><td>" + shown(them.benchDelta) + "</td></tr>"
      + "<tr><th>Net</th><td>" + shown(you.net) + "</td><td>" + shown(them.net) + "</td></tr>"
      + POS.map(function (p) { return "<tr><th>" + p + " starters</th><td>" + shown(you.posDelta[p]) + "</td><td>" + shown(them.posDelta[p]) + "</td></tr>"; }).join("")
      + "</table></details>";
    return '<div class="why-body" data-natural="' + (e.natural ? "1" : "0") + '">'
      + '<p class="why-head">' + (e.natural ? '<span class="why-tag">Natural fit</span>' : "") + esc(e.headline) + "</p>"
      + (e.pct ? '<p class="why-pct" data-pct>' + esc(e.pct.text) + "</p>" : "")
      + '<table class="why-table"><tr><th scope="row">You give up</th><td>' + side(e.table.give) + '</td></tr><tr><th scope="row">You get</th><td>' + side(e.table.get)
      + '</td></tr><tr><th scope="row">Net</th><td>' + esc(e.table.net) + "</td></tr></table>"
      + (opts.extra || "")
      + (e.reasons.length ? '<ol class="why-reasons">' + e.reasons.map(function (r) { return '<li data-kind="' + r.kind + '">' + esc(r.text) + "</li>"; }).join("") + "</ol>" : "")
      + raw + "</div>";
  }

  if (typeof document !== "undefined" && document.head) injectCss();
  window.DDFWhy = {explain: explain, text: text, html: html, body: body, FLOOR: FLOOR};
})();
