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
  const opps = () => (typeof module !== "undefined" && module.exports ? require("./opportunities.js") : root.TradeValueOpportunities);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || `${one}s`)}`;
  const names = list => list.map(p => p.name).join(" + ");

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
  // A trade idea the section can show as given: priced, both sides named, a likelihood in one of the existing bands.
  function usable(rec) {
    return Boolean(rec && rec.id && Array.isArray(rec.give) && rec.give.length && Array.isArray(rec.receive) && rec.receive.length
      && rec.give.concat(rec.receive).every(p => p && p.name) && finite(rec.ourGain) && BANDS.includes(rec.band) && rec.likelihood
      && Array.isArray(rec.why) && (!rec.horizon || rec.horizon === HORIZON));
  }
  // Why the answer is withheld, or [] when it can be shown.
  function gaps(ctx) {
    const out = (ctx.missing || []).map(m => m.text || String(m.key));
    const horizon = ctx.basis && ctx.basis.horizon;
    if (!horizon) out.push("The values behind these trades are not labelled rest of season or weekly.");
    else if (horizon !== HORIZON) out.push("This section answers rest-of-season trades. Weekly values are not mixed in.");
    if (!ctx.ideas) out.push("The trade ideas have not been worked out for this league yet.");
    else {
      const all = (ctx.ideas.recommendations || []).concat(ctx.ideas.stretch || []);
      const bad = all.filter(rec => !usable(rec)).length;
      if (bad) out.push(`${plural(bad, "trade idea is", "trade ideas are")} missing a value, a player or a likelihood.`);
    }
    return out;
  }

  // ---------- the view model ----------
  function item(rec, rank, stretch) {
    const O = opps();
    const gainText = O.fmt(rec.ourGain);
    return {
      id: rec.id, rank, stretch, href: routeFor(rec.id), opponent: rec.opponent,
      give: names(rec.give), receive: names(rec.receive),
      gainText, gainLine: `You gain ${gainText} in DDF Value.`,
      likelihood: rec.likelihood, band: rec.band,
      offer: `Offer ${names(rec.give)} to ${rec.opponent} for ${names(rec.receive)}.`,
      why: rec.why[0] || "",
      whyAll: rec.why.slice(),
      fitWord: rec.fit && O.FIT_WORD[rec.fit] ? O.FIT_WORD[rec.fit] : null,
      sources: (rec.sources || []).map(s => `${s.label} (${s.status})`),
      fallback: rec.fallback || null
    };
  }
  const APPEAL_NOTE = "How likely is your own read of this manager from the Managers card, not a prediction.";

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
      appealNote: APPEAL_NOTE};
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
    const recs = c.ideas.recommendations || [];
    const stretch = c.ideas.stretch || [];
    vm.counts = countsLine(c.ideas.counts);
    vm.stretch = stretch.map((rec, i) => item(rec, i + 1, true));
    if (!recs.length) {
      set("none", "No trade to recommend right now", "None of the trade opportunities is a gain for you that these managers may take.");
    } else {
      set("answer", "Your best trade right now", "");
      const all = recs.map((rec, i) => item(rec, i + 1, false));
      vm.answer = all[0];
      vm.more = all.slice(1);
    }
    if (route && route.detail) {
      const found = [vm.answer].concat(vm.more, vm.stretch).find(x => x && x.id === route.detail);
      if (found) vm.detail = found;
      else vm.detailGone = true;
    }
    return vm;
  }

  // ---------- the live adapter (read only) ----------
  // Where the gates plug in: until each lands, its line below stays in `missing` and the live section withholds the answer.
  //   JEG-1259: the saved league and settings carried through navigation (context).
  //   JEG-1260: the shared trade readout, truthful on missing players and bench counts (detail).
  //   JEG-1249: the integrated starter/bench behaviour behind the trade ideas.
  // Each flag is read from root.TradeValueSimplifiedGates, which the owning ticket sets when its reviewed contract merges.
  const GATES = [
    ["context", "JEG-1259", "Your saved league is not yet carried into this section reliably."],
    ["readout", "JEG-1260", "The shared trade readout is not yet confirmed for missing players and bench counts."],
    ["lineup", "JEG-1249", "Starter and bench handling behind the trade ideas is not yet confirmed."]
  ];
  function liveContext(r) {
    const W = r.TradeValueWorkspace;
    const ideas = r.TradeValueTradeIdeas;
    const gates = r.TradeValueSimplifiedGates || {};
    if (!W || !W.store) return {status: "loading"};
    let ws;
    try { ws = W.store.get(); } catch (error) { return {status: "error", error: String(error && error.message || error)}; }
    const mine = ws && ws.myTeamId && (ws.teams || []).find(t => t.id === ws.myTeamId);
    const out = {status: "ready", league: ws && (ws.teams || []).length ? {name: ws.name || "Your league", myTeam: mine ? mine.name : null} : null,
      basis: {horizon: HORIZON, label: "Rest of season, DDF Value"},
      missing: GATES.filter(([key]) => gates[key] !== true).map(([key, ticket, text]) => ({key, ticket, text})), ideas: null};
    if (!ideas || !ideas.compute) out.missing.push({key: "ideas", text: "The Trade ideas card is not on this page."});
    else {
      try { out.ideas = ideas.compute(); } catch (error) { return {status: "error", error: String(error && error.message || error)}; }
    }
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
  const band = x => el("span", {class: `ss-band is-${x.band}`, text: x.likelihood});

  function card(x) {
    return el("li", {class: "ss-item", "data-trade-id": x.id},
      el("div", {class: "ss-item-head"},
        el("span", {class: "ss-rank", text: `${x.rank}.`}),
        el("a", {class: "ss-item-link", href: x.href, "data-detail-for": x.id, text: x.offer})),
      el("p", {class: "ss-item-meta"}, el("span", {class: "ss-gain", text: x.gainLine}), " ", band(x)),
      x.why ? el("p", {class: "ss-why", text: x.why}) : null);
  }

  function detailView(vm) {
    const x = vm.detail;
    return el("section", {class: "ss-detail", "aria-labelledby": "ssDetailTitle"},
      el("p", {}, el("a", {class: "ss-back", href: ROUTE, text: "Back to the answer"})),
      el("h2", {id: "ssDetailTitle", tabindex: "-1", text: x.offer}),
      el("dl", {class: "ss-facts"},
        el("dt", {text: "You give"}), el("dd", {text: x.give}),
        el("dt", {text: "You get"}), el("dd", {text: x.receive}),
        el("dt", {text: "Your gain"}), el("dd", {text: `${x.gainText} in DDF Value`}),
        el("dt", {text: "They may take it"}), el("dd", {}, band(x), " ", el("span", {class: "ss-note", text: vm.appealNote})),
        x.fitWord ? el("dt", {text: "Fit"}) : null, x.fitWord ? el("dd", {text: x.fitWord}) : null),
      el("h3", {text: "Why"}),
      el("ul", {class: "ss-lines"}, ...x.whyAll.map(line => el("li", {text: line}))),
      el("h3", {text: "Where the numbers come from"}),
      el("ul", {class: "ss-lines ss-provenance"},
        el("li", {text: `Your gain: ${vm.basis || "DDF Value"}.`}),
        el("li", {text: `Their side judged on: ${x.sources.join("; ") || "nothing available"}.`}),
        x.fallback ? el("li", {text: `Uncertain: their side fell back to the trade charts (${x.fallback}).`}) : null,
        x.stretch ? el("li", {text: "Stretch offer: a long shot by your read of this manager."}) : null));
  }

  function render(container, vm) {
    const kids = [];
    kids.push(el("h1", {id: "ssTitle", tabindex: "-1", text: vm.name}));
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
        el("p", {class: "ss-item-meta"}, el("span", {class: "ss-gain", text: a.gainLine}), " ", el("span", {text: "They may take it:"}), " ", band(a)),
        a.why ? el("p", {class: "ss-why", text: a.why}) : null,
        el("p", {class: "ss-note", text: vm.appealNote}),
        el("p", {}, el("a", {class: "ss-item-link", href: a.href, "data-detail-for": a.id, text: "Why this trade, and where the numbers come from"})));
    }
    kids.push(status);
    if (vm.more.length) {
      kids.push(el("section", {class: "ss-more", "aria-labelledby": "ssMoreTitle"},
        el("h2", {id: "ssMoreTitle", text: "If they say no, try these next"}),
        el("ol", {class: "ss-list", start: "2"}, ...vm.more.map(card))));
    }
    if (vm.stretch.length) {
      kids.push(el("section", {class: "ss-stretch", "aria-labelledby": "ssStretchTitle"},
        el("h2", {id: "ssStretchTitle", text: "Stretch offers"}),
        el("p", {class: "ss-note", text: "Long shots by your read of the manager. Each one says which belief has to hold."}),
        el("ol", {class: "ss-list"}, ...vm.stretch.map(card))));
    }
    if (vm.counts) kids.push(el("p", {class: "ss-counts", text: vm.counts}));
    container.replaceChildren(...kids);
    container.dataset.state = vm.state;
    container.dataset.view = "section";
    return container;
  }

  // opts: {getContext() -> context, hash() -> current hash (default location.hash)}. Returns {update(), destroy()}.
  // Focus: entering the section moves focus to its title, opening a trade to the trade's heading, and coming back from a
  // trade to that trade's link, so keyboard and screen reader users keep their place.
  function mount(container, opts) {
    const o = opts || {};
    const hash = o.hash || (() => root.location.hash);
    container.classList.add("simplified-site");
    let last = null;
    function update(focus) {
      const route = parseRoute(hash());
      if (!route) { last = null; return null; }
      const vm = render(container, viewModel(o.getContext(), route));
      const was = last;
      last = route;
      const target = vm.dataset.view === "detail" ? container.querySelector("#ssDetailTitle")
        : was && was.detail ? container.querySelector(`[data-detail-for="${CSS.escape(was.detail)}"]`) || container.querySelector("#ssTitle")
        : focus || !was ? container.querySelector("#ssTitle") : null;
      if (target && (focus || !was || (was.detail || null) !== (route.detail || null))) target.focus();
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
  function activate(container) {
    if (!container) return null;
    if (!mounted) mounted = mount(container, {getContext: () => liveContext(root)});
    else mounted.update(false);
    return mounted;
  }

  const api = {NAME, ROUTE, HORIZON, GATES, parseRoute, routeFor, usable, gaps, viewModel, countsLine, liveContext, render, mount, activate};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueSimplifiedSite = api;
})(typeof window !== "undefined" ? window : globalThis);
