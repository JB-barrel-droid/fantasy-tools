// AI connection panel (JEG-1266) logic checks, pure Node. Usage: node ai_connection_panel_harness.cjs <dir with ai-connection-panel.js>
// Prints {check: true | "failure text"} as JSON. tests/test_jeg1266_ai_connection_panel.py runs it, and runs it again on broken
// copies of the module to prove each check catches what it guards.
"use strict";
const path = require("path");
const fs = require("fs");

const dir = path.resolve(process.argv[2] || path.join(__dirname, "..", "app", "v2"));
const P = require(path.join(dir, "ai-connection-panel.js"));
const FIX = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "ai-connection-panel", "synthetic-states.json"), "utf8"));
const ctxOf = name => Object.assign({fixture: FIX.fixture}, JSON.parse(JSON.stringify(FIX.states[name])));
const CONNECTED_CLAIM = /\b(you're|you are|is|are|now|it's) connected\b|\bconnected\.|✓/i;

const results = {};
const checks = [];
function check(name, fn) { checks.push([name, fn]); }
function assert(cond, text) { if (!cond) throw new Error(text); }

check("test_states_are_distinct", () => {
  const want = {
    "ready": ["available", "ready"], "default-league": ["available", "ready"], "setup-unavailable": ["unavailable", "ready"],
    "setup-unknown": ["unknown", "ready"], "link-unavailable": ["available", "unavailable"], "link-unknown": ["available", "unknown"],
    "clipboard-off": ["available", "ready"], "missing-league": ["available", "missing"], "claims-connected": ["available", "ready"]
  };
  Object.entries(want).forEach(([name, [setup, share]]) => {
    const vm = P.viewModel(ctxOf(name), null);
    assert(vm.setup.state === setup, `${name}: setup ${vm.setup.state}, want ${setup}`);
    assert(vm.share.state === share, `${name}: share ${vm.share.state}, want ${share}`);
  });
  const texts = ["setup-unavailable", "setup-unknown", "link-unavailable", "link-unknown", "missing-league", "clipboard-off"]
    .map(name => { const vm = P.viewModel(ctxOf(name), null); return vm.setup.text + "|" + vm.share.text; });
  assert(new Set(texts).size === texts.length, "two different states read the same");
});

check("test_never_claims_connected", () => {
  const plain = P.viewModel(ctxOf("ready"), null);
  const claimed = P.viewModel(ctxOf("claims-connected"), null);
  assert(claimed.connection === "unknown" && plain.connection === "unknown", "connection is not the constant unknown");
  const strip = vm => JSON.stringify(Object.assign({}, vm, {capabilities: null}));
  assert(strip(plain) === strip(claimed), "a fixture's connected flag changed what the panel shows");
  [plain, claimed, P.viewModel(ctxOf("ready"), {status: "copied", url: FIX.link})].forEach(vm => {
    const text = [vm.heading, vm.body, vm.setup.label, vm.setup.note, vm.setup.text, vm.next.heading, vm.next.note,
      vm.share.more, vm.share.local, vm.share.line, vm.share.text, vm.share.carries, vm.copy.text].filter(Boolean).join(" ");
    assert(!CONNECTED_CLAIM.test(text), `claims a connection: ${text.match(CONNECTED_CLAIM)}`);
  });
  assert(claimed.next.heading === P.COPY["ai.next.h"], "the connected-user step is not the pack's question");
});

check("test_unknown_is_not_true", () => {
  const setup = P.viewModel(ctxOf("setup-unknown"), null).setup;
  assert(!setup.href && !setup.label, "an unknown setup guide still shows the Connect link");
  const ctx = ctxOf("ready");
  ctx.capabilities.linkCodec = null;
  const share = P.viewModel(ctx, null).share;
  assert(share.state === "unknown" && !share.button && !share.carries, "an unknown link builder still offers Copy link");
  const junk = P.viewModel({capabilities: {setupGuide: "yes", linkCodec: 1, clipboard: "true"}, share: {league: "saved", work: []}}, null);
  assert(junk.setup.state === "unknown" && junk.share.state === "unknown", "a truthy non-boolean counted as supported");
  const none = P.viewModel(null, null);
  assert(none.setup.state === "unknown" && none.share.state === "unknown" && none.copy.state === "idle", "no context is not all unknown");
});

check("test_connect_explained_once", () => {
  const vm = P.viewModel(ctxOf("ready"), null);
  assert(vm.setup.href === P.GUIDE_URL && vm.setup.label === P.COPY["ai.cta"], "the one setup path is not the connect guide");
  assert(vm.share.more.includes("Pasting a link does not connect the tool."), "the share step does not say pasting doesn't connect");
  assert(vm.share.local === P.COPY["ai.link.local"], "browser-local line missing");
  assert(vm.share.line === P.COPY["ai.link.line"], "Copy link line is not Jeremy's pick A");
});

check("test_copy_actions", async () => {
  const calls = [];
  const ok = await P.copyLink({getLink: () => FIX.link, writeClipboard: t => { calls.push(t); return Promise.resolve(); }, clipboard: true});
  assert(ok.status === "copied" && calls.length === 1 && calls[0] === FIX.link, `success: ${JSON.stringify(ok)}`);
  const denied = await P.copyLink({getLink: () => FIX.link, writeClipboard: () => Promise.reject(new Error("NotAllowedError")), clipboard: true});
  assert(denied.status === "failed" && denied.url === FIX.link, `permission failure: ${JSON.stringify(denied)}`);
  const unknownClip = await P.copyLink({getLink: () => FIX.link, writeClipboard: () => Promise.reject(new Error("x")), clipboard: null});
  assert(unknownClip.status === "failed" && unknownClip.url === FIX.link, "unknown clipboard failure not shown as a failure");
  const off = [];
  const manual = await P.copyLink({getLink: () => FIX.link, writeClipboard: t => { off.push(t); return Promise.resolve(); }, clipboard: false});
  assert(manual.status === "failed" && manual.url === FIX.link && off.length === 0, "clipboard off still tried the clipboard");
  const nothing = await P.copyLink({getLink: () => null, writeClipboard: () => Promise.resolve(), clipboard: true});
  assert(nothing.status === "nothing", "no link not reported as nothing to copy");
  const broken = await P.copyLink({getLink: () => { throw new Error("codec"); }, writeClipboard: () => Promise.resolve(), clipboard: true});
  assert(broken.status === "error", "a link builder error not reported");
});

check("test_copy_failure_shows_link", () => {
  const vm = P.viewModel(ctxOf("ready"), {status: "failed", url: FIX.link});
  assert(vm.copy.state === "failed" && vm.copy.text === P.COPY["ai.err.copy"] && vm.copy.url === FIX.link, `failure: ${JSON.stringify(vm.copy)}`);
  const ok = P.viewModel(ctxOf("ready"), {status: "copied", url: FIX.link});
  assert(ok.copy.state === "copied" && !ok.copy.url && ok.copy.text === P.UI.copied, "success state wrong");
  assert(P.viewModel(ctxOf("ready"), {status: "error"}).copy.text === P.UI.noLink, "error state wrong");
  assert(P.viewModel(ctxOf("ready"), {status: "nothing"}).copy.text === P.UI.nothing, "nothing state wrong");
  const manual = P.viewModel(ctxOf("clipboard-off"), null).share;
  assert(manual.button === P.UI.copyManual && manual.text === P.UI.clipboardOff, "clipboard off is not labelled as copy by hand");
});

check("test_copy_result_only_when_ready", () => {
  ["missing-league", "link-unavailable", "link-unknown"].forEach(name => {
    const vm = P.viewModel(ctxOf(name), {status: "copied", url: FIX.link});
    assert(vm.copy.state === "idle", `${name}: shows a copy result with no Copy link button`);
  });
});

check("test_missing_league", () => {
  const vm = P.viewModel(ctxOf("missing-league"), null);
  assert(vm.share.state === "missing" && !vm.share.button && vm.share.text === P.UI.nothing, "missing league still offers a link");
  const def = ctxOf("missing-league");
  def.share.league = "default";
  assert(P.viewModel(def, null).share.state === "missing", "default settings alone counted as something to share");
});

check("test_default_league_labelled", () => {
  const saved = P.viewModel(ctxOf("ready"), null).share.carries;
  const def = P.viewModel(ctxOf("default-league"), null).share.carries;
  assert(saved === "The link carries: your league settings, a trade (1 for 1).", `saved: ${saved}`);
  assert(def === "The link carries: the default league settings, the target Synthetic WR.", `default: ${def}`);
});

check("test_fixture_labelled", () => {
  const vm = P.viewModel(ctxOf("ready"), null);
  assert(vm.fixture && vm.fixture.kind === "synthetic" && vm.fixture.label === FIX.fixture.label, "fixture label dropped");
  const bare = P.viewModel({fixture: {}, capabilities: {}}, null);
  assert(bare.fixture && bare.fixture.label === P.UI.fixtureDefault, "an unlabelled fixture shows no label");
  assert(P.viewModel(Object.assign(ctxOf("ready"), {fixture: undefined}), null).fixture === null, "a live context shows a fixture label");
});

check("test_context_not_mutated", () => {
  Object.keys(FIX.states).forEach(name => {
    const ctx = ctxOf(name);
    const before = JSON.stringify(ctx);
    P.viewModel(ctx, {status: "copied", url: FIX.link});
    assert(JSON.stringify(ctx) === before, `${name}: context changed`);
  });
});

// ---- the live adapter, against fake pages ----
function fakeRoot(o) {
  const r = {
    document: {readyState: o.readyState || "complete", querySelector: sel => (o.guide && sel.includes(P.GUIDE_URL) ? {} : null)},
    navigator: o.clipboard === undefined ? {clipboard: {writeText: () => Promise.resolve()}} : o.clipboard,
    isSecureContext: o.secure !== false
  };
  if (o.codec) r.DDFState = {};
  if (o.assist) r.DDFAssist = o.assist;
  if (o.teams) r.TradeValueWorkspace = {store: {get: () => ({teams: o.teams})}};
  return r;
}
const LINK = {text: FIX.link, built: {state: {league: {scoring: "half_ppr", teams: 12}, work: {give: [{key: "1"}], get: [{key: "2"}, {key: "3"}]}}}};

check("test_live_adapter_unknown_before_attach", () => {
  const notAttached = P.liveAdapter(fakeRoot({guide: true, codec: true, assist: {linkText: () => { throw new TypeError("H is null"); }}}));
  const ctx = notAttached.getContext();
  assert(ctx.capabilities.linkCodec === null && ctx.share === null, `not attached: ${JSON.stringify(ctx)}`);
  assert(notAttached.getLink() === null, "not attached still gives a link");
  const notLoaded = P.liveAdapter(fakeRoot({guide: true})).getContext();
  assert(notLoaded.capabilities.linkCodec === null, "scripts not loaded yet counted as known");
  const noBuilder = P.liveAdapter(fakeRoot({guide: true, codec: true, assist: {}})).getContext();
  assert(noBuilder.capabilities.linkCodec === false, "an assist without a link builder not reported unavailable");
  assert(!("fixture" in ctx) && !("connection" in ctx), "the live adapter claims a fixture or a connection");
});

check("test_live_adapter_reads_link", () => {
  const live = P.liveAdapter(fakeRoot({guide: true, codec: true, assist: {linkText: () => LINK}, teams: [{id: "a"}]}));
  const ctx = live.getContext();
  assert(ctx.capabilities.linkCodec === true && ctx.share.league === "saved", `share: ${JSON.stringify(ctx.share)}`);
  assert(JSON.stringify(ctx.share.work) === JSON.stringify(["a trade (1 for 2)"]), `work: ${JSON.stringify(ctx.share.work)}`);
  assert(live.getLink() === FIX.link, "getLink is not the page's link");
  const noLeague = P.liveAdapter(fakeRoot({guide: true, codec: true, assist: {linkText: () => LINK}})).getContext();
  assert(noLeague.share.league === "default", "settings with no saved league not labelled default");
  const empty = P.liveAdapter(fakeRoot({guide: true, codec: true, assist: {linkText: () => null}})).getContext();
  assert(empty.share && empty.share.league === null && empty.share.work.length === 0, "no link state not the missing state");
  assert(P.viewModel(empty, null).share.state === "missing", "no link state does not render as missing");
});

check("test_live_adapter_guide_and_clipboard", () => {
  assert(P.liveAdapter(fakeRoot({guide: true})).getContext().capabilities.setupGuide === true, "guide link not found");
  assert(P.liveAdapter(fakeRoot({guide: false})).getContext().capabilities.setupGuide === false, "missing guide link not false");
  assert(P.liveAdapter(fakeRoot({guide: false, readyState: "loading"})).getContext().capabilities.setupGuide === null, "loading page not unknown");
  assert(P.liveAdapter(fakeRoot({clipboard: {}})).getContext().capabilities.clipboard === false, "no clipboard API not false");
  assert(P.liveAdapter(fakeRoot({secure: false})).getContext().capabilities.clipboard === false, "insecure page counted as able to copy");
  assert(P.liveAdapter(fakeRoot({clipboard: null})).getContext().capabilities.clipboard === null, "no navigator not unknown");
});

// ---- mount(), on a minimal fake DOM: a copy result belongs to the view it was started on (JEG-1300) ----
function fakeNode(tag) {
  const node = {
    tagName: tag.toUpperCase(), attrs: {}, children: [], parent: null, dataset: {}, listeners: {}, _text: "", value: "",
    classList: {add: c => { node.attrs.class = [node.attrs.class, c].filter(Boolean).join(" "); }},
    setAttribute(k, v) { node.attrs[k] = String(v); }, getAttribute: k => (k in node.attrs ? node.attrs[k] : null),
    get id() { return node.attrs.id || ""; },
    get textContent() { return node._text + node.children.map(c => c.textContent).join(""); },
    set textContent(v) { node.children = []; node._text = String(v); },
    append(...kids) { kids.forEach(k => { const n = typeof k === "string" ? textNode(k) : k; if (n.parent) n.parent.children = n.parent.children.filter(c => c !== n); n.parent = node; node.children.push(n); }); },
    appendChild(n) { node.append(n); return n; },
    replaceChildren(...kids) { node.children.forEach(c => { c.parent = null; }); node.children = []; node._text = ""; node.append(...kids); },
    matches(sel) {
      if (sel.startsWith("#")) return node.id === sel.slice(1);
      if (sel.startsWith(".")) return (node.attrs.class || "").split(" ").includes(sel.slice(1));
      return node.tagName === sel.toUpperCase();
    },
    querySelector(sel) {
      if (sel.startsWith(":scope > ")) return node.children.find(c => c.matches(sel.slice(9))) || null;
      for (const c of node.children) { if (c.matches(sel)) return c; const deep = c.querySelector(sel); if (deep) return deep; }
      return null;
    },
    closest(sel) { let n = node; while (n) { if (n.matches(sel)) return n; n = n.parent; } return null; },
    addEventListener(type, fn) { (node.listeners[type] = node.listeners[type] || []).push(fn); },
    removeEventListener(type, fn) { node.listeners[type] = (node.listeners[type] || []).filter(f => f !== fn); },
    focus() { fakeDom.active = node; }, select() { node.selected = true; }
  };
  return node;
}
function textNode(text) { const n = fakeNode("#text"); n._text = text; n.matches = () => false; n.querySelector = () => null; return n; }
const fakeDom = {active: null};
const windowListeners = {};
globalThis.document = {createElement: fakeNode};
globalThis.addEventListener = (type, fn) => { (windowListeners[type] = windowListeners[type] || []).push(fn); };
globalThis.removeEventListener = (type, fn) => { windowListeners[type] = (windowListeners[type] || []).filter(f => f !== fn); };
const fireHash = () => (windowListeners.hashchange || []).slice().forEach(fn => fn({type: "hashchange"}));

// A mounted panel whose context and link the check can change, and whose clipboard writes wait until the check settles them.
function mounted(name) {
  const page = {ctx: ctxOf(name), link: FIX.link, writes: [], pending: []};
  page.container = fakeNode("section");
  page.handle = P.mount(page.container, {
    getContext: () => page.ctx, getLink: () => page.link,
    writeClipboard: text => { page.writes.push(text); return new Promise((resolve, reject) => page.pending.push({resolve, reject})); }
  });
  page.click = () => {
    const button = page.container.querySelector("#aipCopy");
    assert(button, "no Copy link button to press");
    return Promise.all((page.container.listeners.click || []).map(fn => fn({target: button})));
  };
  page.shown = () => {
    const area = page.container.querySelector("#aipLinkText");
    const result = page.container.querySelector("#aipResult");
    return {copy: page.container.dataset.copy, result: result ? result.textContent : null, link: area ? area.value : null,
      live: page.container.querySelector(".aip-live").textContent, carries: (page.container.querySelector(".aip-carries") || {}).textContent};
  };
  return page;
}
const LINK_B = "https://example.invalid/fantasy-tools/#trade-targets?v=1&scoring=half_ppr&teams=12&target=9";
function moveToViewB(page) { page.ctx = ctxOf("default-league"); page.link = LINK_B; }
function assertIdle(page, label) {
  const s = page.shown();
  assert(s.copy === "idle" && s.result === null && s.link === null && s.live === "", `${label}: ${JSON.stringify(s)}`);
}

check("test_copy_result_on_its_own_view", async () => {
  const ok = mounted("ready");
  const pressed = ok.click();
  ok.pending[0].resolve();
  await pressed;
  const s = ok.shown();
  assert(s.copy === "copied" && s.live === P.UI.copied && ok.writes[0] === FIX.link, `copy on the same view not shown: ${JSON.stringify(s)}`);
  const bad = mounted("ready");
  const pressedBad = bad.click();
  bad.pending[0].reject(new Error("NotAllowedError"));
  await pressedBad;
  const f = bad.shown();
  assert(f.copy === "failed" && f.link === FIX.link && f.live === P.COPY["ai.err.copy"], `failure on the same view not shown: ${JSON.stringify(f)}`);
  ok.handle.destroy(); bad.handle.destroy();
});

check("test_late_copy_dropped_after_hashchange", async () => {
  for (const settle of ["resolve", "reject"]) {
    const page = mounted("ready");
    const pressed = page.click();
    moveToViewB(page);
    fireHash();
    page.pending[0][settle](settle === "reject" ? new Error("NotAllowedError") : undefined);
    await pressed;
    assertIdle(page, `late ${settle} for view A shown on view B`);
    assert(page.shown().carries === P.viewModel(ctxOf("default-league"), null).share.carries, "view B not shown");
    page.handle.destroy();
  }
  // A hashchange alone ends the view, even if the adapter still reads the same context and link.
  const same = mounted("ready");
  const pressed = same.click();
  fireHash();
  same.pending[0].resolve();
  await pressed;
  assertIdle(same, "a copy started before a hashchange was applied after it");
  same.handle.destroy();
});

check("test_same_route_change_drops_copy", async () => {
  // A result already shown does not survive a league or roster change on the same route.
  const shownFirst = mounted("ready");
  const pressed = shownFirst.click();
  shownFirst.pending[0].resolve();
  await pressed;
  assert(shownFirst.shown().copy === "copied", "precondition: the copy was shown");
  shownFirst.handle.update();
  assert(shownFirst.shown().copy === "copied", "update() with nothing changed dropped a current result");
  shownFirst.ctx.share.work = ["a trade (2 for 1)"];
  shownFirst.handle.update();
  assertIdle(shownFirst, "a copied result survived a roster change");
  // A copy still running when the settings change is dropped when it settles, with or without update() in between.
  for (const callUpdate of [true, false]) {
    for (const settle of ["resolve", "reject"]) {
      const page = mounted("ready");
      const pressing = page.click();
      page.ctx.share.league = "default";
      page.link = LINK_B;
      if (callUpdate) page.handle.update();
      page.pending[0][settle](settle === "reject" ? new Error("NotAllowedError") : undefined);
      await pressing;
      assertIdle(page, `late ${settle} applied after a settings change (update ${callUpdate})`);
      page.handle.destroy();
    }
  }
});

check("test_newer_press_and_destroy_drop_copy", async () => {
  const page = mounted("ready");
  const first = page.click();
  const second = page.click();
  page.pending[1].resolve();
  page.pending[0].reject(new Error("slow and denied"));
  await Promise.all([first, second]);
  assert(page.shown().copy === "copied", `an older press overwrote the newer one: ${JSON.stringify(page.shown())}`);
  page.handle.destroy();
  const gone = mounted("ready");
  const pressed = gone.click();
  gone.handle.destroy();
  gone.pending[0].reject(new Error("late"));
  await pressed;
  assertIdle(gone, "a copy settled after destroy() was applied");
  gone.handle.destroy();
});

(async () => {
  for (const [name, fn] of checks) {
    try { await fn(); results[name] = true; } catch (error) { results[name] = String(error && error.message || error); }
  }
  process.stdout.write(JSON.stringify(results));
})();
