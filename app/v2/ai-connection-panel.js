// Trade Value v2 — the homepage "use DDF in your AI assistant" panel (JEG-1266, part of JEG-1137).
//
// What it says: connect the DDF tool once, through the supported setup path (a custom connector in Claude or ChatGPT, explained
// on the connect guide), and later copy this view's link into a chat that already has the tool. Pasting a link does not connect
// anything. Every reader-facing AI claim is a string from the corrected copy pack (docs/product/jeg-1223-ai-onboarding-copy.md,
// JEG-1223 / JEG-1252, PR #1078 head 91b0328), kept verbatim under its string ID in COPY. The only other words are about this
// page's own controls (UI below): what the Copy link button can do here and what happened when it was pressed.
//
// The site cannot tell whether a reader's chat is connected, so there is no connection input at all: nothing an adapter or a
// fixture hands in can make the panel say "connected". The connected-user step is always the pack's conditional question.
//
// Three layers, each usable alone:
//   * viewModel(ctx, copy): pure. Context in, the exact strings and states to show out. Never mutates ctx.
//   * copyLink(io): the Copy link action over injected getLink / writeClipboard, returning one of the copy results below.
//   * render(container, vm) and mount(container, opts): the DOM. mount wires the button, keeps a live region and manages focus.
//
// Context (what an adapter hands in; liveAdapter() below is the dashboard's, read only):
//   {fixture?: {kind: "synthetic", label},     // set by every fixture; absent only for the live adapter
//    capabilities: {setupGuide, linkCodec, clipboard},   // each true | false | null (null = not known yet, never assumed)
//    share: {league: "saved" | "default" | null, work: [text]} | null}   // what a copied link would carry; null = not known
//   setupGuide: the page carries the link to the connect guide (the one setup path, and the single explanation).
//   linkCodec: the page can build a link for this view (ddf-state.js loaded and ddf-assist.js attached).
//   clipboard: the browser offers a clipboard write here. true still may fail (permission), which is the copy failure state.
// Copy results: null (not pressed) | {status: "copied", url} | {status: "failed", url} | {status: "nothing"} | {status: "error"}.
(function (root) {
  "use strict";

  const NAME = "ai-connection-panel";
  const GUIDE_URL = "connect/";   // same href as the footer's Connect the tool

  // The copy pack, verbatim by string ID (JEG-1223 / JEG-1252). Change these only with the pack.
  const COPY = Object.freeze({
    "ai.h": "Find your best trade in Claude or ChatGPT",
    "ai.body": "Give the chat your roster and the other team's, or your whole league's. It looks for trades that add value for you and still look fair to them on the trade charts, checks each one against both lineups and depth, and labels how natural a fit each one is. Answers include a link to the matching page on this site.",
    "ai.cta": "Connect the tool",
    "ai.cta.note": "Data Driven Football is free, with no DDF account or sign-in. You add one web address as a custom connector in Claude or ChatGPT. You still need your own Claude or ChatGPT account, and whether you can add custom connectors depends on your plan and settings there.",
    "ai.next.h": "Already connected? Try asking:",
    "ai.next.ex1": "\"Using Data Driven Football, find me a trade with this team in my 12-team half-PPR league. My roster: … Their roster: … Give me the link to open it on the site.\"",
    "ai.next.ex2": "\"Using Data Driven Football, find the best trades across my 12-team half-PPR league. My roster: … Then each team's roster: …\"",
    "ai.next.ex3": "\"Using Data Driven Football, is Bijan Robinson for Ja'Marr Chase fair in my 12-team half-PPR league?\"",
    "ai.next.note": "Each answer gives the date of the values and a link to the matching page here, usually with your league settings and the players you asked about filled in. After a league-wide search, the link brings only your roster: add the other teams on the page.",
    "ai.link.line": "Opens this view. A chat with the DDF tool reads it too.",
    "ai.link.more": "Copy link puts this view's address on your clipboard: your league settings and the trade, rosters or target you're working on. Paste it into a chat that has the DDF tool connected and the tool reads your league settings and players from it. Pasting a link does not connect the tool.",
    "ai.link.local": "Your saved work stays on this device. A link carries only what is in its address.",
    "ai.err.copy": "Couldn't copy. Copy this link:"
  });
  // This page's own controls and states. No AI or connector claim belongs here.
  const UI = Object.freeze({
    shareTitle: "Share this view with a connected chat",
    copy: "Copy link",
    copyManual: "Show the link to copy",
    copied: "Copied the link.",
    linkLabel: "Link to copy",
    nothing: "There is nothing to share yet. Add your league, or open a trade, a target or two rosters, then copy the link.",
    noLink: "Couldn't make a link for this view.",
    carries: "The link carries",
    setupUnavailable: "The setup guide isn't linked from this page right now.",
    setupUnknown: "This page couldn't confirm where the setup guide is.",
    linkUnavailable: "Copy link isn't available on this page.",
    linkUnknown: "Copy link isn't ready yet.",
    clipboardOff: "This browser doesn't let the page copy for you, so the button shows the link to copy yourself.",
    fixture: "Synthetic example. ",
    fixtureDefault: "Mock capabilities for a preview: not a live check of this page or of any chat connection."
  });
  const EXAMPLES = ["ai.next.ex1", "ai.next.ex2", "ai.next.ex3"];
  const known = v => v === true || v === false;

  // ---------- the view model ----------
  function setupState(cap) {
    if (cap === true) return {state: "available", href: GUIDE_URL, label: COPY["ai.cta"], note: COPY["ai.cta.note"], text: ""};
    return {state: cap === false ? "unavailable" : "unknown", href: null, label: null, note: null,
      text: cap === false ? UI.setupUnavailable : UI.setupUnknown};
  }
  function shareState(caps, share) {
    if (caps.linkCodec === false) return {state: "unavailable", text: UI.linkUnavailable, button: null, carries: ""};
    if (caps.linkCodec !== true || !share) return {state: "unknown", text: UI.linkUnknown, button: null, carries: ""};
    const work = Array.isArray(share.work) ? share.work.filter(Boolean) : [];
    if (share.league !== "saved" && !work.length) return {state: "missing", text: UI.nothing, button: null, carries: ""};
    const parts = [share.league === "saved" ? "your league settings" : share.league === "default" ? "the default league settings" : ""]
      .concat(work).filter(Boolean);
    return {state: "ready", text: caps.clipboard === false ? UI.clipboardOff : "",
      button: caps.clipboard === false ? UI.copyManual : UI.copy, carries: `${UI.carries}: ${parts.join(", ")}.`};
  }
  function copyState(copy) {
    if (!copy) return {state: "idle", text: "", url: null};
    if (copy.status === "copied") return {state: "copied", text: UI.copied, url: null};
    if (copy.status === "failed" && copy.url) return {state: "failed", text: COPY["ai.err.copy"], url: copy.url};
    if (copy.status === "nothing") return {state: "nothing", text: UI.nothing, url: null};
    return {state: "error", text: UI.noLink, url: null};
  }

  // ctx: the context above; copy: the last copy result for this context (null before the button is pressed).
  function viewModel(ctx, copy) {
    const c = ctx || {};
    const raw = c.capabilities || {};
    const caps = {setupGuide: known(raw.setupGuide) ? raw.setupGuide : null, linkCodec: known(raw.linkCodec) ? raw.linkCodec : null,
      clipboard: known(raw.clipboard) ? raw.clipboard : null};
    const share = shareState(caps, c.share || null);
    return {
      name: NAME,
      fixture: c.fixture ? {kind: c.fixture.kind || "synthetic", label: c.fixture.label || UI.fixtureDefault} : null,
      connection: "unknown",   // constant: the site cannot detect a chat connection
      capabilities: caps,
      heading: COPY["ai.h"], body: COPY["ai.body"],
      setup: setupState(caps.setupGuide),
      next: {heading: COPY["ai.next.h"], examples: EXAMPLES.map(id => COPY[id]), note: COPY["ai.next.note"]},
      share: Object.assign({title: UI.shareTitle, line: COPY["ai.link.line"], more: COPY["ai.link.more"], local: COPY["ai.link.local"]}, share),
      copy: share.state === "ready" ? copyState(copy) : copyState(null)
    };
  }

  // ---------- the Copy link action ----------
  // io: {getLink() -> url | null, writeClipboard(text) -> Promise, clipboard: true | false | null}.
  // clipboard false: no attempt; the link is shown to copy by hand (the failure state, which is what the reader needs).
  async function copyLink(io) {
    let url;
    try { url = io.getLink(); } catch (error) { return {status: "error"}; }
    if (!url) return {status: "nothing"};
    if (io.clipboard === false || typeof io.writeClipboard !== "function") return {status: "failed", url};
    try {
      await io.writeClipboard(url);
      return {status: "copied", url};
    } catch (error) {
      return {status: "failed", url};
    }
  }

  // ---------- the live adapter (read only) ----------
  // What the dashboard can say about itself. It reads ddf-assist.js's link builder and the footer's guide link; it never writes a
  // store and never guesses: anything it can't read is null (unknown), not true.
  function shareFrom(state, hasSavedLeague) {
    const w = state.work || {};
    const work = [];
    if (w.give || w.get) work.push(`a trade (${(w.give || []).length} for ${(w.get || []).length})`);
    if (w.mine && w.theirs) work.push("both rosters on Find a trade");
    else if (w.mine) work.push("your roster on Find a trade");
    else if (w.theirs) work.push("their roster on Find a trade");
    if (w.target && w.target.name) work.push(`the target ${w.target.name}`);
    return {league: state.league ? (hasSavedLeague ? "saved" : "default") : null, work};
  }
  function liveAdapter(r) {
    const doc = r.document;
    const assist = () => r.DDFAssist;
    function built() {
      const A = assist();
      if (!r.DDFState || !A || typeof A.linkText !== "function") return {codec: r.DDFState && A ? false : null, link: null};
      try { return {codec: true, link: A.linkText()}; } catch (error) { return {codec: null, link: null}; }   // not attached yet
    }
    function savedLeague() {
      const W = r.TradeValueWorkspace;
      try { const ws = W && W.store && W.store.get(); return Boolean(ws && (ws.teams || []).length); } catch (error) { return false; }
    }
    function getContext() {
      const guide = doc ? doc.querySelector(`#v2AssistLine a[href="${GUIDE_URL}"]`) : null;
      const b = built();
      const nav = r.navigator;
      const clip = nav ? Boolean(nav.clipboard && typeof nav.clipboard.writeText === "function" && r.isSecureContext !== false) : null;
      return {
        capabilities: {setupGuide: guide ? true : (doc && doc.readyState !== "loading" ? false : null), linkCodec: b.codec, clipboard: clip},
        share: b.codec === true ? (b.link ? shareFrom(b.link.built.state, savedLeague()) : {league: null, work: []}) : null
      };
    }
    return {
      getContext,
      getLink: () => { const b = built(); return b.link ? b.link.text : null; },
      writeClipboard: text => r.navigator.clipboard.writeText(text)
    };
  }

  // ---------- the DOM ----------
  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (v === false || v === null || v === undefined) return;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v);
    });
    node.append(...kids.filter(k => k !== null && k !== undefined && k !== false && k !== ""));
    return node;
  }

  function render(container, vm) {
    const body = container.querySelector(":scope > .aip-body") || container.appendChild(el("div", {class: "aip-body"}));
    const kids = [];
    if (vm.fixture) {
      kids.push(el("p", {class: "aip-fixture", role: "note", "data-fixture": vm.fixture.kind},
        el("b", {text: UI.fixture}), vm.fixture.label));
    }
    kids.push(el("h2", {id: "aipTitle", class: "aip-title", text: vm.heading}), el("p", {class: "aip-lede", text: vm.body}));
    const s = vm.setup;
    kids.push(el("div", {class: `aip-setup is-${s.state}`, "data-setup": s.state},
      s.href ? el("a", {class: "aip-cta", id: "aipConnect", href: s.href}, s.label) : null,
      s.note ? el("p", {class: "aip-note", text: s.note}) : null,
      s.text ? el("p", {class: "aip-unavailable", role: "note", text: s.text}) : null));
    kids.push(el("section", {class: "aip-next", "aria-labelledby": "aipNextTitle"},
      el("h3", {id: "aipNextTitle", text: vm.next.heading}),
      el("ul", {class: "aip-examples"}, ...vm.next.examples.map(x => el("li", {text: x}))),
      el("p", {class: "aip-note", text: vm.next.note})));
    const sh = vm.share;
    const cp = vm.copy;
    kids.push(el("section", {class: `aip-share is-${sh.state}`, "aria-labelledby": "aipShareTitle", "data-share": sh.state, "data-copy": cp.state},
      el("h3", {id: "aipShareTitle", text: sh.title}),
      el("p", {text: sh.more}),
      el("p", {class: "aip-note", text: sh.local}),
      sh.carries ? el("p", {class: "aip-carries", text: sh.carries}) : null,
      sh.text ? el("p", {class: "aip-unavailable", role: "note", text: sh.text}) : null,
      sh.button ? el("button", {type: "button", class: "aip-btn", id: "aipCopy", "aria-describedby": "aipCopyLine"}, sh.button) : null,
      sh.button ? el("p", {class: "aip-note", id: "aipCopyLine", text: sh.line}) : null,
      cp.text ? el("p", {class: `aip-result is-${cp.state}`, id: "aipResult", text: cp.text}) : null,
      cp.url ? el("textarea", {class: "aip-linktext", id: "aipLinkText", readonly: true, rows: "3", "aria-label": UI.linkLabel}) : null));
    body.replaceChildren(...kids);
    const area = body.querySelector("#aipLinkText");
    if (area) area.value = cp.url;
    container.dataset.setup = s.state;
    container.dataset.share = sh.state;
    container.dataset.copy = cp.state;
    return container;
  }

  // opts: {getContext() -> context, getLink() -> url | null, writeClipboard(text) -> Promise}. Returns {update(), reset(), destroy()}.
  // The live region sits outside the re-rendered body, so a copy result is announced; focus stays on Copy link after a copy and
  // moves to the selected link text when the reader has to copy by hand.
  // A copy result belongs to the view it was started on (JEG-1300). Each press takes a revision and the view's key (its context
  // and link); a result that settles after a newer press, a hashchange, reset() or destroy(), or after the key moved, is dropped,
  // so the panel never shows an old link as the fallback or says "Copied" for a view that was not copied. update() keeps the
  // last result only while the key still matches.
  function mount(container, opts) {
    const o = opts || {};
    const getLink = o.getLink || (() => null);
    container.classList.add(NAME);
    if (!container.getAttribute("aria-labelledby")) container.setAttribute("aria-labelledby", "aipTitle");
    const live = el("p", {class: "aip-live", role: "status", "aria-live": "polite", "aria-atomic": "true"});
    let last = null;
    let lastKey = null;
    let revision = 0;
    let destroyed = false;
    function viewKey(ctx) {
      let link;
      try { link = getLink(); } catch (error) { link = {error: true}; }
      return JSON.stringify({ctx: ctx === undefined ? null : ctx, link: link === undefined ? null : link});
    }
    function show(ctx, copy, key) {
      last = copy || null;
      lastKey = last ? key : null;
      const vm = viewModel(ctx, last);
      render(container, vm);
      container.append(live);
      return vm;
    }
    function update(copy) { return show(o.getContext(), copy, null); }
    function refresh() {
      const ctx = o.getContext();
      const key = viewKey(ctx);
      if (last && key !== lastKey) { revision += 1; live.textContent = ""; return show(ctx, null, null); }
      return show(ctx, last, key);
    }
    function clear() { revision += 1; live.textContent = ""; return update(null); }
    async function onClick(event) {
      if (destroyed || !event.target.closest || !event.target.closest("#aipCopy")) return;
      const mine = ++revision;
      const ctx = o.getContext();
      const key = viewKey(ctx);
      const result = await copyLink({getLink, writeClipboard: o.writeClipboard,
        clipboard: ctx && ctx.capabilities ? ctx.capabilities.clipboard : null});
      if (destroyed || mine !== revision) return;   // the view moved on, or a newer press owns the result
      const now = o.getContext();
      if (viewKey(now) !== key) { clear(); return; }   // same route, but the league, roster or link changed while copying
      const vm = show(now, result, key);
      live.textContent = vm.copy.text;
      const area = container.querySelector("#aipLinkText");
      if (area) { area.focus(); area.select(); } else { const b = container.querySelector("#aipCopy"); if (b) b.focus(); }
    }
    const onHash = () => { clear(); };   // a new view means a new link: the old result, and any copy still running, no longer hold
    container.addEventListener("click", onClick);
    root.addEventListener("hashchange", onHash);
    update(null);
    return {update: () => refresh(), reset: () => clear(), destroy: () => {
      destroyed = true;
      revision += 1;
      container.removeEventListener("click", onClick);
      root.removeEventListener("hashchange", onHash);
    }};
  }

  const api = {NAME, GUIDE_URL, COPY, UI, viewModel, copyLink, shareFrom, liveAdapter, render, mount};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueAiConnectionPanel = api;
})(typeof window !== "undefined" ? window : globalThis);
