// Trade Value v2 — the Simplified site section (JEG-1263): the same trade ideas, answer first.
//
// Jeremy, 2026-10-29: "start out by making a section of our site called "Simplified site." We can have that in its own
// section in the hamburger. Then once it is working, we can set up a site that hides everything else."
//
// No value math here. The section reads the Trade ideas output (manager-recs.js build(): recommendations ranked by your gain,
// each with the other manager's likelihood in words, why lines and sources; stretch offers; counts) and draws it with the
// dashboard's own number format (opportunities.js fmt, the Trade opportunities capture cell). It never re-ranks, re-prices,
// adds a threshold or a Natural-fit rule, and never writes a store: rosters and settings are only read, by the adapter.
//
// Three layers, each usable alone:
//   * parseRoute / routeFor: the address contract. #simplified-site is the section; #simplified-site/trade/<id> opens one
//     trade's detail. Both are plain hashes, so Back and deep links work.
//   * viewModel(ctx, route): pure. Context in, the exact strings to show out. The states: loading, error, empty (no league or
//     no team of yours), incomplete (missing, mixed or unsupported data: the answer is withheld), none (nothing qualifies),
//     answer. A context that came from a fixture is labelled on screen as such.
//   * render(container, vm) and mount(container, opts): the DOM. mount re-renders on hashchange and manages focus.
//
// Context (what an adapter hands in; liveContext() below is the dashboard's):
//   {status: "loading" | "error" | "ready", error?: text,
//    fixture?: {kind: "synthetic" | "historical", label},     // set by every fixture; absent only for the live adapter
//    league: {name, myTeam} | null,
//    basis: {horizon: "ros" | "weekly", label},                // the trade ideas are rest-of-season DDF Value only
//    missing: [{key, text}],                                   // anything listed withholds the answer
//    ideas: manager-recs build() output | null}
(function (root) {
  "use strict";

  const ROUTE = "#simplified-site";
  const DETAIL = "/trade/";
  const NAME = "Simplified site";
  const HORIZON = "ros";   // Trade ideas are priced in rest-of-season DDF Value; weekly values are never mixed in
  const BANDS = ["likely", "possible", "longShot"];
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const text = s => typeof s === "string" && s.trim() !== "";
  const opps = () => (typeof module !== "undefined" && module.exports ? require("./opportunities.js") : root.TradeValueOpportunities);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || `${one}s`)}`;
  const names = list => list.map(p => p.name).join(" + ");
  const QUESTION_IDS = ["our-starters", "our-roster", "their-starters", "their-roster"];
  const basisName = key => ({ddf_value: "DDF Value", ddf_value_projections: "DDF Projections",
    "published-average": "Published-chart average", fantasycalc: "FantasyCalc", usatoday: "USA Today",
    fantasypros: "FantasyPros", cbs: "CBS"})[key] || String(key || "Unavailable");

  // Consumer schema only: the canonical owner supplies every value, predicate, label and coverage decision.
  function canonicalUsable(rec) {
    const d = rec && rec.record;
    const keys = list => list.map(p => String(p.player_key)).sort().join(",");
    return Boolean(d && d.contract === "JEG-1483/1" && text(d.label) && d.participants && text(d.participants.mine)
      && String(d.participants.theirs) === String(rec.opponentId) && text(rec.opponent) && rec.id
      && Array.isArray(rec.give) && Array.isArray(rec.receive) && rec.receive.length
      && (rec.give.length || d.partnerKind === "waivers") && rec.give.concat(rec.receive).every(p => p && text(p.name))
      && d.deal && Array.isArray(d.deal.give) && Array.isArray(d.deal.get)
      && keys(rec.give) === d.deal.give.map(String).sort().join(",") && keys(rec.receive) === d.deal.get.map(String).sort().join(",")
      && Array.isArray(d.questions) && d.questions.length === 4 && d.questions.every((q, i) => q && q.id === QUESTION_IDS[i]
        && text(q.label) && text(q.subject) && text(q.scope) && text(q.basis) && text(q.sign) && text(q.aggregation)
        && Array.isArray(q.sources) && q.sources.every(text) && q.coverage && text(q.coverage.text) && "tolerance" in q
        && (q.status === "known" ? typeof q.pass === "boolean" && (q.scope === "roster" ? typeof q.value === "boolean" : finite(q.value))
          : ["unknown", "not_applicable"].includes(q.status) && q.value === null && q.pass === null)));
  }

  const quantityText = q => !q || q.status === "unknown" ? "Unavailable" : q.status === "not_applicable" ? q.reason || "Not applicable"
    : typeof q.value === "boolean" ? q.value ? "Not hindered" : "Hindered" : opps().fmt(q.value);

  function canonicalItem(rec, rank, stretch) {
    const d = rec.record, q = d.questions[0], p = d.supporting?.theirs?.market?.package;
    const questions = d.questions.map(q => ({id: q.id, label: q.label, status: q.status, value: quantityText(q),
      result: q.status === "not_applicable" ? "Not applicable" : q.pass === null ? "Unknown" : q.pass ? "Pass" : "Does not pass",
      meta: `${q.subject} · ${q.scope} · ${basisName(q.basis)} · ${q.coverage.text} · ${q.sign}`,
      detail: `${q.aggregation}; sources: ${q.sources.join(", ") || "unavailable"}; tolerance: ${q.tolerance ?? "unavailable"}`
        + (q.operator ? `; ${q.operator} ${q.threshold ?? "unavailable"} (${q.tier})` : "") + (q.reason ? `; ${q.reason}` : "")}));
    return {id: rec.id, rank: Number.isInteger(rec.rank) && rec.rank > 0 ? rec.rank : rank, stretch,
      href: routeFor(rec.id), opponent: rec.opponent, partnerKind: d.partnerKind,
      give: names(rec.give) || "No drop", receive: names(rec.receive), gainText: quantityText(q),
      gainLine: `${q.label}: ${quantityText(q)} (${basisName(q.basis)}).`, fitWord: d.label, canonical: true, questions,
      evidence: d.partnerKind === "waivers" ? "No other manager: Waivers." : `Their ${basisName(p?.basis)} package: ${quantityText(p)}${p?.coverage?.text ? ` · ${p.coverage.text}` : ""}.`,
      health: [], offer: d.partnerKind === "waivers" ? `Pick up ${names(rec.receive)} from ${rec.opponent}.`
        : `Offer ${names(rec.give)} to ${rec.opponent} for ${names(rec.receive)}.`,
      why: d.label, whyAll: [d.label], sources: [...new Set(d.questions.flatMap(q => q.sources))], fallback: null};
  }

  // Controller boundary for runCanonical's page. Preserve row identity/order so canonicalReadout(row) keeps its captured
  // inputs. The caller owns generation, invalidation, pagination and shared settings; this function never runs a search.
  function canonicalContext(result, options) {
    const o = options || {}, base = {league: o.league || null, fixture: o.fixture, basis: o.basis || {horizon: HORIZON, label: "Canonical starter readout"},
      missing: [], ideas: null, canonicalResult: result};
    if (!result || result.cancelled || result.status === "cancelled" || result.status === "running") return {...base, status: "loading"};
    if (result.status === "error") return {...base, status: "error", error: result.reason};
    if (result.status !== "ready" || !Array.isArray(result.rows)) return {...base, status: "ready",
      missing: [{key: "canonical", text: result.reason || "Canonical trade results are not ready."}]};
    base.ideas = {recommendations: result.rows, stretch: [], counts: result.counts};
    const row = o.detailId ? result.rows.find(r => r.id === o.detailId) : null;
    if (row && o.readoutFor) {
      base.readout = o.readoutFor(row);
      if (!base.readout || JSON.stringify(base.readout.decision) !== JSON.stringify(row.record)) {
        base.readout = null;
        base.missing.push({key: "readout", text: "The shared readout does not match this canonical package."});
      }
    }
    return {...base, status: "ready"};
  }

  // ---------- the address ----------
  // hash -> {detail: trade id | null} when the hash is this section's, else null.
  function parseRoute(hash) {
    const base = String(hash || "").split("?")[0];
    if (base === ROUTE) return {detail: null};
    if (!base.startsWith(ROUTE + DETAIL)) return null;
    let id = base.slice((ROUTE + DETAIL).length);
    try { id = decodeURIComponent(id); } catch (error) { return {detail: null}; }
    return {detail: id || null};
  }
  const routeFor = id => (id ? `${ROUTE}${DETAIL}${encodeURIComponent(id)}` : ROUTE);

  // ---------- checks: withhold rather than guess ----------
  // A trade idea the section can show as given: priced, both sides and the other manager named, a likelihood in one of the
  // existing bands, at least one why line, and every source it cites labelled (sources may be absent: "nothing available").
  function usable(rec) {
    if (rec && "record" in rec) return canonicalUsable(rec);
    return Boolean(rec && rec.id && text(rec.opponent) && Array.isArray(rec.give) && rec.give.length && Array.isArray(rec.receive)
      && rec.receive.length && rec.give.concat(rec.receive).every(p => p && p.name) && finite(rec.ourGain) && BANDS.includes(rec.band)
      && rec.likelihood && Array.isArray(rec.why) && rec.why.length && rec.why.every(text)
      && (rec.sources == null || (Array.isArray(rec.sources) && rec.sources.every(s => s && text(s.label) && text(s.status))))
      && (!rec.horizon || rec.horizon === HORIZON));
  }
  // Why the answer is withheld, or [] when it can be shown. The ideas must be the worked-out output itself (not a Promise)
  // with a recommendations list; anything else is withheld rather than read as "nothing qualifies".
  function gaps(ctx) {
    const out = (ctx.missing || []).map(m => m.text || String(m.key));
    const horizon = ctx.basis && ctx.basis.horizon;
    if (!horizon) out.push("The values behind these trades are not labelled rest of season or weekly.");
    else if (horizon !== HORIZON) out.push("This section answers rest-of-season trades. Weekly values are not mixed in.");
    const ideas = ctx.ideas;
    if (!ideas) out.push("The trade ideas have not been worked out for this league yet.");
    else if (typeof ideas.then === "function") out.push("The trade ideas are still being worked out.");
    else if (typeof ideas !== "object" || !Array.isArray(ideas.recommendations) || !(ideas.stretch == null || Array.isArray(ideas.stretch))) {
      out.push("The trade ideas came back in a form this section cannot read.");
    } else {
      const bad = ideas.recommendations.concat(ideas.stretch || []).filter(rec => !usable(rec)).length;
      if (bad) out.push(`${plural(bad, "trade idea is", "trade ideas are")} missing required shared values, players, decisions or source metadata.`);
    }
    return out;
  }

  // ---------- the view model ----------
  function item(rec, rank, stretch, labels) {
    if (rec.record) return canonicalItem(rec, rank, stretch);
    const O = opps();
    const gainText = O.fmt(rec.ourGain);
    const market = rec.gains && rec.gains.market;
    const chartBasis = (rec.basis || []).find(x => x.anchor === "market");
    const theirPackage = finite(market) ? market : chartBasis && chartBasis.gain;
    return {
      id: rec.id, rank, stretch, href: routeFor(rec.id), opponent: rec.opponent,
      give: names(rec.give), receive: names(rec.receive),
      gainText, gainLine: `You gain ${gainText} in ${labels.value}.`,
      likelihood: rec.likelihood, band: rec.band,
      evidence: finite(theirPackage) ? `Their ${labels.market} package ${O.fmt(theirPackage)}.` : `Their ${labels.market} package value is unavailable.`,
      health: rec.health ? [rec.health.ours && rec.health.ours.length ? `Your roster: ${rec.health.ours.join("; ")}.` : "",
        rec.health.theirs && rec.health.theirs.length ? `Their roster: ${rec.health.theirs.join("; ")}.` : ""].filter(Boolean) : [],
      offer: `Offer ${names(rec.give)} to ${rec.opponent} for ${names(rec.receive)}.`,
      why: rec.why[0] || "",
      whyAll: rec.why.slice(),
      fitWord: text(rec.fitLabel) ? rec.fitLabel : rec.fit && O.FIT_WORD[rec.fit] ? O.FIT_WORD[rec.fit] : null,
      sources: (rec.sources || []).map(s => `${s.label} (${s.status})`),
      fallback: rec.fallback || null
    };
  }
  const APPEAL_NOTE = "Package evidence describes their side; it is not a prediction or a starter-fit judgment.";

  function countsLine(counts) {
    const c = counts || {};
    if (!c.considered) return "There were no trade opportunities to read.";
    const left = [];
    if (c.excluded) left.push(`${plural(c.excluded, "trade")} with managers marked won't trade`);
    if (c.notWin) left.push(`${plural(c.notWin, "trade")} that ${c.notWin === 1 ? "isn't" : "aren't"} a gain for you`);
    if (c.hidden) left.push(`${plural(c.hidden, "trade")} too far below even for them`);
    if (c.noAppeal) left.push(`${plural(c.noAppeal, "trade")} with nothing to judge their side by`);
    return `Read from ${plural(c.considered, "trade opportunity", "trade opportunities")}.${left.length ? ` Left out: ${left.join("; ")}.` : ""}`;
  }

  // ctx: the context above; route: parseRoute()'s result (or null for the section itself). Never mutates ctx.
  function viewModel(ctx, route) {
    const c = ctx || {};
    const vm = {name: NAME, state: null, fixture: c.fixture ? {kind: c.fixture.kind, label: c.fixture.label} : null,
      league: c.league ? c.league.name || null : null, basis: c.basis && c.basis.label || null,
      heading: "", text: "", reasons: [], answer: null, more: [], stretch: [], counts: "", detail: null, detailGone: false,
      appealNote: APPEAL_NOTE, readout: null, valueLabel: c.basis && c.basis.valueLabel || "DDF Value"};
    const set = (state, heading, text) => Object.assign(vm, {state, heading, text});
    if (c.status === "loading") return set("loading", "Working out your trades", "Reading your league and its trade ideas.");
    if (c.status === "error") return set("error", "Something went wrong", c.error ? `The trade ideas could not be read: ${c.error}` : "The trade ideas could not be read.");
    if (c.status !== "ready") return set("error", "Something went wrong", "The section was given no context to read.");
    if (!c.league || !c.league.myTeam) {
      return set("empty", "Add your league first", "Load your league and mark which team is yours. The answer appears here once the trade ideas have been worked out.");
    }
    const why = gaps(c);
    if (why.length) {
      set("incomplete", "No answer yet", "Some of what the answer needs is missing, so no trade is recommended.");
      vm.reasons = why;
      return vm;
    }
    const recs = c.ideas.recommendations;
    const stretch = c.ideas.stretch || [];
    const labels = {value: vm.valueLabel, market: c.basis && c.basis.marketLabel || "trade-chart"};
    vm.counts = c.canonicalResult ? `Evaluated ${c.canonicalResult.evaluated ?? "unknown"} packages; ${c.canonicalResult.total ?? "unknown"} match this search.`
      + (c.canonicalResult.bounded || c.canonicalResult.capped ? " Search limits apply; this is not an exhaustive league result." : "")
      + (c.canonicalResult.hasMore ? " More results are available in the full dashboard." : "") : countsLine(c.ideas.counts);
    vm.stretch = stretch.map((rec, i) => item(rec, i + 1, true, labels));
    if (!recs.length) {
      const emptyPage = c.canonicalResult && c.canonicalResult.total > 0;
      set("none", emptyPage ? "No packages on this page" : "No trade to recommend right now", c.canonicalResult
        ? emptyPage ? "Return to the full dashboard to choose another results page." : "No packages match this canonical search."
        : "None of the trade opportunities is a gain for you that these managers may take.");
    } else {
      set("answer", c.canonicalResult ? "A package from your search" : "Your best trade right now", "");
      const all = recs.map((rec, i) => item(rec, i + 1, false, labels));
      vm.answer = all[0];
      vm.more = all.slice(1);
    }
    if (route && route.detail) {
      const found = [vm.answer].concat(vm.more, vm.stretch).find(x => x && x.id === route.detail);
      if (found) { vm.detail = found; vm.readout = c.readout || null; }
      else vm.detailGone = true;
    }
    return vm;
  }

  // ---------- the live adapter (read only) ----------
  // The three prerequisite contracts have landed. Read their actual APIs and the page's current context, rather than
  // waiting for globals no owner sets. The ideas provider remains a separate dependency (#1084).
  const GATES = [
    ["context", "JEG-1259", "Your current league settings and saved team could not be read together."],
    ["readout", "JEG-1260", "The shared trade readout is not available on this page yet."],
    ["lineup", "JEG-1249", "The current roster shape and starter/bench rules are not available yet."]
  ];

  function liveContracts(r, ws) {
    const TC = r.TradeValueTradeContext, R = r.TradeValueReadout, C = r.TradeValueCurveControls;
    const V = r.TradeValueV2, O = r.DDFOverrides, F = r.TradeValueFinder;
    let context = null;
    if (TC && TC.fromLeague && TC.commonFromPage && TC.sourcesFromEngine && V && V.leagueQuery && O && O.snapshotContext
      && C && C.getBasis && C.getSourceInfo) {
      const common = TC.commonFromPage({leagueQuery: V.leagueQuery(),
        valueContext: {...O.snapshotContext(), basis: C.getBasis()}, sources: TC.sourcesFromEngine(C.getSourceInfo())});
      context = TC.fromLeague({common}, ws);
    }
    const shape = C && C.getRosterShape ? C.getRosterShape() : null;
    return {context, shape, contracts: {
      context: Boolean(context && context.common.league && !context.warnings.length && context.teams.mine
        && !context.teams.mine.missing && context.teams.mine.matchesSaved),
      readout: Boolean(R && R.VERSION === 1 && R.inputFromContext && R.build && R.renderSide && F && F.rosterImpact),
      lineup: Boolean(shape && F && F.pickStarters && r.ValueModel && r.ValueModel.isReserveSlot
        && r.TradeValueLineupComparison && r.TradeValueLineupComparison.renderTable)
    }};
  }

  // #1084 keeps the exact completed search's pricingRows (including DDF/market league levels). Never replace those
  // with getAllRows(): doing so would silently reprice league-level trades at the standard bench.
  function readoutFor(r, context, rec, snapshot, shape) {
    if (!snapshot || !Array.isArray(snapshot.pricingRows)) return null;
    const TC = r.TradeValueTradeContext, R = r.TradeValueReadout;
    const opponent = context.teams.opponents.find(t => t.id === rec.opponentId);
    if (!opponent) return null;
    const key = p => String(p.player_key);
    const trade = TC.createContext({route: "league", common: context.common, workspaceId: context.workspaceId,
      mine: context.teams.mine, opponents: [opponent], deal: {give: rec.give.map(key), get: rec.receive.map(key)}});
    if (!TC.dealPartner(trade)) return null;
    const rowsByKey = new Map(snapshot.pricingRows.map(row => [key(row), row]));
    const env = {rowsByKey, shape, chartKeys: r.TradeValueCurveControls.getSourceInfo().filter(s => s.available)
      .map(s => s.key).filter(k => r.TradeValueFinder.CHART_KEYS.includes(k))};
    return R.build(R.inputFromContext(trade, env, {context: TC}),
      {finder: r.TradeValueFinder, isReserveSlot: r.ValueModel.isReserveSlot});
  }

  function liveContext(r) {
    const W = r.TradeValueWorkspace;
    const ideas = r.TradeValueTradeIdeas;
    if (!W || !W.store) return {status: "loading"};
    let ws;
    try { ws = W.store.get(); } catch (error) { return {status: "error", error: String(error && error.message || error)}; }
    const mine = ws && ws.myTeamId && (ws.teams || []).find(t => t.id === ws.myTeamId);
    const out = {status: "ready", league: ws && (ws.teams || []).length ? {name: ws.name || "Your league", myTeam: mine ? mine.name : null} : null,
      basis: {horizon: HORIZON, label: "Rest of season, DDF Value"},
      missing: [], ideas: null};
    if (!mine) return out;
    try {
      const state = liveContracts(r, ws), contracts = state.contracts;
      out.context = state.context;
      out.contracts = contracts;
      out.missing = GATES.filter(([key]) => contracts[key] !== true).map(([key, ticket, text]) => ({key, ticket, text}));
      if (!ideas || typeof ideas.compute !== "function") out.missing.push({key: "ideas", text: "Trade ideas are not available on this page yet."});
      if (out.missing.length) return out;
      const ui = r.TradeValueLeague && r.TradeValueLeague.ui;
      // The old result can remain in ui.result during a new search. Never show it while its context is being rebuilt.
      if (!ui || !ui.ready || ui.running || ui.timer) return {...out, status: "loading"};
      const snapshot = ui.result;
      if (!snapshot || !Array.isArray(snapshot.pricingRows)) {
        out.missing.push({key: "ideas", text: "The league's priced trade opportunities are not ready yet."});
        return out;
      }
      out.ideas = ideas.compute();
      if (!out.ideas || typeof out.ideas.then === "function" || ui.result !== snapshot || W.store.get() !== ws) {
        return {...out, status: "loading", ideas: null};
      }
      if (!gaps(out).length) {
        const detail = parseRoute(r.location && r.location.hash);
        const all = out.ideas.recommendations.concat(out.ideas.stretch || []);
        const rec = detail && detail.detail ? all.find(x => x.id === detail.detail) : all[0];
        if (rec) {
          if (rec.record) {
            out.missing.push({key: "canonical", text: "This canonical package needs its controller's captured shared readout."});
            return out;
          }
          out.readout = readoutFor(r, state.context, rec, snapshot, state.shape);
          const readout = out.readout;
          if (!readout || !readout.ready || ["mine", "theirs"].some(side => !readout.sides[side].ddf
            || readout.sides[side].ddf.tradedUnpriced.length)) {
            out.missing.push({key: "readout", text: "This trade is missing a roster player or a DDF Value; no answer is shown."});
          }
        }
      }
    } catch (error) { return {status: "error", error: String(error && error.message || error)}; }
    return out;
  }

  // ---------- the DOM ----------
  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (v === false || v === null || v === undefined) return;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v);
    });
    node.append(...kids.filter(k => k !== null && k !== undefined && k !== false));
    return node;
  }
  const band = x => el("span", {class: "ss-evidence", text: x.evidence});
  const questionNodes = x => !x.questions ? [] : [el("ol", {class: "ss-questions"}, ...x.questions.map(q =>
    el("li", {"data-question-id": q.id, "data-status": q.status}, el("b", {text: q.label}),
      el("p", {text: `${q.value} · ${q.result}`}), el("p", {class: "ss-note", text: q.meta}),
      el("p", {class: "ss-note", text: q.detail}))))];

  function card(x) {
    return el("li", {class: "ss-item", "data-trade-id": x.id},
      el("div", {class: "ss-item-head"},
        el("span", {class: "ss-rank", text: `${x.rank}.`}),
        el("a", {class: "ss-item-link", href: x.href, "data-detail-for": x.id, text: x.offer})),
      el("p", {class: "ss-item-meta"}, el("span", {class: "ss-gain", text: x.gainLine}), " ", band(x)),
      ...questionNodes(x),
      ...x.health.map(line => el("p", {class: "ss-health", text: line})),
      x.why ? el("p", {class: "ss-why", text: x.why}) : null);
  }

  function detailView(vm) {
    const x = vm.detail;
    const detail = el("section", {class: "ss-detail", "aria-labelledby": "ssDetailTitle"},
      el("p", {}, el("a", {class: "ss-back", href: ROUTE, text: "Back to the answer"})),
      el("h2", {id: "ssDetailTitle", tabindex: "-1", text: x.offer}),
      el("dl", {class: "ss-facts"},
        el("dt", {text: "You give"}), el("dd", {text: x.give}),
        el("dt", {text: "You get"}), el("dd", {text: x.receive}),
        el("dt", {text: x.canonical ? "Your starter change" : "Your gain"}), el("dd", {text: x.canonical ? x.gainLine : `${x.gainText} in ${vm.valueLabel}`}),
        el("dt", {text: "Their package evidence"}), el("dd", {}, band(x), " ", el("span", {class: "ss-note", text: vm.appealNote})),
        x.fitWord ? el("dt", {text: x.canonical ? "Canonical decision" : "Current engine fit"}) : null, x.fitWord ? el("dd", {text: x.fitWord}) : null),
      ...questionNodes(x),
      el("h3", {text: "Why"}),
      ...x.health.map(line => el("p", {class: "ss-health", text: line})),
      el("ul", {class: "ss-lines"}, ...x.whyAll.map(line => el("li", {text: line}))),
      el("h3", {text: "Where the numbers come from"}),
      el("ul", {class: "ss-lines ss-provenance"},
        el("li", {text: `Your gain: ${vm.basis || "DDF Value"}.`}),
        el("li", {text: `Their side judged on: ${x.sources.join("; ") || "nothing available"}.`}),
        x.fallback ? el("li", {text: `Uncertain: their side fell back to the trade charts (${x.fallback}).`}) : null,
        x.stretch ? el("li", {text: "Other package from the same search; inspect their side's evidence."}) : null));
    if (vm.readout) {
      [["mine", "Your roster"], ["theirs", `${x.opponent}'s roster`]].forEach(([who, title]) => {
        if (x.partnerKind === "waivers" && who === "theirs") return;
        detail.append(el("h3", {text: title}));
        ["ddf", "market", "projections"].forEach(view => detail.append(root.TradeValueReadout.renderSide(vm.readout, who, view)));
      });
    }
    return detail;
  }

  function render(container, vm) {
    const kids = [];
    kids.push(el("h1", {id: "ssTitle", tabindex: "-1", text: vm.name}));
    kids.push(el("nav", {class: "ss-access", "aria-label": "Dashboard access"},
      el("a", {href: ROUTE, text: "Simplified site"}), el("a", {href: "#find-league", text: "Full dashboard"})));
    if (vm.fixture) {
      kids.push(el("p", {class: "ss-fixture", role: "note", "data-fixture": vm.fixture.kind},
        el("b", {text: vm.fixture.kind === "historical" ? "Historical example. " : "Synthetic example. "}),
        vm.fixture.label || "Not your league and not a live answer."));
    }
    if (vm.league) kids.push(el("p", {class: "ss-context", text: `${vm.league}${vm.basis ? ` · ${vm.basis}` : ""}`}));
    if (vm.detail) {
      kids.push(detailView(vm));
      container.replaceChildren(...kids);
      container.dataset.state = vm.state;
      container.dataset.view = "detail";
      return container;
    }
    const busy = vm.state === "loading";
    const status = el("section", {class: `ss-status is-${vm.state}`, "aria-labelledby": "ssStatusTitle",
      role: vm.state === "error" ? "alert" : "status", "aria-busy": busy ? "true" : null},
      el("h2", {id: "ssStatusTitle", text: vm.heading}),
      vm.text ? el("p", {text: vm.text}) : null,
      vm.reasons.length ? el("ul", {class: "ss-lines ss-reasons"}, ...vm.reasons.map(r => el("li", {text: r}))) : null);
    if (vm.detailGone) kids.push(el("p", {class: "ss-gone", role: "status", text: "That trade is no longer in the list. Here is the current answer."}));
    if (vm.answer) {
      const a = vm.answer;
      status.append(
        el("p", {class: "ss-offer", text: a.offer}),
        el("p", {class: "ss-item-meta"}, el("span", {class: "ss-gain", text: a.gainLine}), " ", band(a)),
        ...questionNodes(a),
        ...a.health.map(line => el("p", {class: "ss-health", text: line})),
        a.why ? el("p", {class: "ss-why", text: a.why}) : null,
        el("p", {class: "ss-note", text: vm.appealNote}),
        el("p", {}, el("a", {class: "ss-item-link", href: a.href, "data-detail-for": a.id, text: "Why this trade, and where the numbers come from"})));
    }
    kids.push(status);
    if (vm.more.length) {
      const list = el("ol", {class: "ss-list", start: "2"});
      let shown = 0;
      const more = el("button", {type: "button", class: "v2-btn", text: "Show 10 more trades"});
      const append = () => { const next = vm.more.slice(shown, shown + 10); shown += next.length;
        list.append(...next.map(card)); more.hidden = shown >= vm.more.length; };
      more.addEventListener("click", append);
      append();
      kids.push(el("section", {class: "ss-more", "aria-labelledby": "ssMoreTitle"},
        el("h2", {id: "ssMoreTitle", text: "More trades from the same search"}), list, more));
    }
    if (vm.stretch.length) {
      const list = el("ol", {class: "ss-list"});
      let shown = 0;
      const more = el("button", {type: "button", class: "v2-btn", text: "Show 10 more other packages"});
      const append = () => { const next = vm.stretch.slice(shown, shown + 10); shown += next.length;
        list.append(...next.map(card)); more.hidden = shown >= vm.stretch.length; };
      more.addEventListener("click", append);
      append();
      kids.push(el("section", {class: "ss-stretch", "aria-labelledby": "ssStretchTitle"},
        el("h2", {id: "ssStretchTitle", text: "Other packages"}), list, more));
    }
    if (vm.counts) kids.push(el("p", {class: "ss-counts", text: vm.counts}));
    container.replaceChildren(...kids);
    container.dataset.state = vm.state;
    container.dataset.view = "section";
    return container;
  }

  // opts: {getContext() -> context, hash() -> current hash (default location.hash)}. Returns {update(), destroy()}.
  // Focus: entering the section moves focus to its title, opening a trade to the trade's heading, and coming back from a
  // trade to that trade's link, so keyboard and screen reader users keep their place. A refresh on the same route keeps
  // focus on the same link (or the title, if that trade is gone) instead of dropping it to the page.
  // A context that throws renders the error state, so an earlier answer is never left on screen.
  function mount(container, opts) {
    const o = opts || {};
    const hash = o.hash || (() => root.location.hash);
    container.classList.add("simplified-site");
    let last = null;
    function focusKey() {
      const node = typeof document !== "undefined" ? document.activeElement : null;
      if (!node || node === container || !container.contains(node)) return null;
      if (node.dataset.detailFor) return `[data-detail-for="${CSS.escape(node.dataset.detailFor)}"]`;
      if (node.classList.contains("ss-back")) return ".ss-back";
      return node.id ? `#${CSS.escape(node.id)}` : "#ssTitle";
    }
    function update(focus) {
      const route = parseRoute(hash());
      if (!route) { last = null; return null; }
      const keep = focusKey();
      let model;
      try { model = viewModel(o.getContext(), route); } catch (error) {
        model = viewModel({status: "error", error: String(error && error.message || error)}, route);
      }
      const vm = render(container, model);
      const was = last;
      last = route;
      const target = vm.dataset.view === "detail" ? container.querySelector("#ssDetailTitle")
        : was && was.detail ? container.querySelector(`[data-detail-for="${CSS.escape(was.detail)}"]`) || container.querySelector("#ssTitle")
        : focus || !was ? container.querySelector("#ssTitle") : null;
      if (target && (focus || !was || (was.detail || null) !== (route.detail || null))) target.focus();
      else if (keep) (container.querySelector(keep) || container.querySelector("#ssTitle")).focus();
      return vm;
    }
    const onHash = () => update(false);
    root.addEventListener("hashchange", onHash);
    update(true);
    return {update, destroy: () => root.removeEventListener("hashchange", onHash)};
  }

  // The one call the dashboard makes (v2.js refresh() on this route): mount once on the live adapter, then re-read on each
  // refresh without moving focus (the hashchange listener in mount() handles focus when the route changes).
  let mounted = null;
  function followLive(handle) {
    let queued = false;
    const refresh = () => {
      if (queued) return;
      queued = true;
      queueMicrotask(() => { queued = false; handle.update(false); });
    };
    [root.TradeValueWorkspace, root.TradeValueManagerProfiles].forEach(api => {
      if (api && api.store && api.store.onChange) api.store.onChange(refresh);
    });
    root.addEventListener("trade-value-rows-change", refresh);
    document.addEventListener("ddf:league-settings-changed", refresh);
    const body = document.getElementById("v2LgOppsBody");
    if (body) new MutationObserver(refresh).observe(body, {childList: true, subtree: true, attributes: true, attributeFilter: ["aria-busy"]});
  }
  function activate(container) {
    if (!container) return null;
    if (!mounted) { mounted = mount(container, {getContext: () => liveContext(root)}); followLive(mounted); }
    else mounted.update(false);
    return mounted;
  }

  const api = {NAME, ROUTE, HORIZON, GATES, parseRoute, routeFor, usable, canonicalUsable, canonicalContext, gaps, viewModel, countsLine, liveContracts, readoutFor, liveContext, render, mount, activate};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueSimplifiedSite = api;
})(typeof window !== "undefined" ? window : globalThis);
