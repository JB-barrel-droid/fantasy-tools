// Trade Value v2 — Player values view.
//
// This file renders; it never computes a value. Every number comes from the
// current chart engine (curve-widget.js) through TradeValueCurveControls, which
// runs off-screen on this page. Settings changes go back through the engine's
// own setters, so v2 and the current page cannot disagree.
(function () {
  "use strict";

  const $ = id => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const PAGE_SIZE = 50;

  // Publisher identity: stable color + symbol + label (frame 17 / 22 #13).
  const PUBLISHERS = {
    espn: {label: "ESPN", color: "#0B7A4B", symbol: "●"},
    fantasycalc: {label: "FantasyCalc", color: "#1F5FBF", symbol: "■"},
    fantasypros: {label: "FantasyPros", color: "#7652B8", symbol: "▲"},
    usatoday: {label: "USA Today", color: "#0E7490", symbol: "◆"},
    cbs: {label: "CBS Sports", color: "#4B5563", symbol: "▼"},
    cbsros: {label: "CBS rest of season", color: "#6B7280", symbol: "▽"},
    razzball: {label: "Razzball", color: "#9D174D", symbol: "✚"}
  };
  // Dark theme: the same hues, lightened so symbols and lines keep 3:1 against the dark surfaces.
  const DARK_COLORS = {espn: "#3FBF85", fantasycalc: "#7AA7EE", fantasypros: "#AE93E4", usatoday: "#3DB6D0",
    cbs: "#A8B2BF", cbsros: "#B9BFC9", razzball: "#E7759F"};
  const darkQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const isDark = () => {
    const theme = document.documentElement.dataset.theme;
    return theme === "dark" || (theme !== "light" && Boolean(darkQuery && darkQuery.matches));
  };
  const pubColor = publisher => (isDark() && DARK_COLORS[publisher]) || PUBLISHERS[publisher]?.color || "#64736F";
  const PUBLISHER_NAMES = {
    espn: "ESPN", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", usatoday: "USA Today",
    cbs: "CBS Sports", cbsros: "CBS rest-of-season projections", razzball: "Razzball projections"
  };
  // Labels (Jeremy, 2026-10-08): plain words at 768 px and up, the short forms only below.
  const PLAIN_NAMES = {espn: "ESPN", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", usatoday: "USA Today",
    cbs: "CBS Sports", cbsros: "CBS rest of season", razzball: "Razzball"};
  const narrowQuery = window.matchMedia ? window.matchMedia("(max-width: 767px)") : null;
  const metaWideQuery = window.matchMedia ? window.matchMedia("(min-width: 1600px)") : null;   // JEG-473
  let metaNoRoom = false;   // set when the expanded columns would make the table scroll sideways
  let expanded = null;      // JEG-483: "chart" | "table" while the expanded view is open
  const metaColumnsShown = () => expanded === "table" || (Boolean(metaWideQuery && metaWideQuery.matches) && !metaNoRoom);
  const isNarrow = () => Boolean(narrowQuery && narrowQuery.matches);
  let RESCALED_TO = "";   // JEG-1044: " to FantasyCalc" under a reader basis (syncBasisLabels), so "rescaled" never misleads
  const SHORT_METHOD = {dda: "DDF Value", indexed: "Market", vorp: "Value above waivers"};
  const PLAIN_METHOD = {dda: "DDF Value", indexed: "Market", vorp: "Value above waivers"};
  const METHOD_LABEL = new Proxy({}, {get: (_, method) => (isNarrow() ? SHORT_METHOD : PLAIN_METHOD)[method]});
  // JEG-474 vocabulary: every series belongs to one of these groups, named the same everywhere.
  const SERIES_GROUPS = [
    {id: "ddf", title: "DDF Value", one: "DDF Value", many: "DDF Values",
      note: "DDF Value for each player: rooted in the trade charts, then adjusted for position weight and your league's rosters."},
    {id: "proj", title: "Projections", one: "projection", many: "projections",
      note: "What players are projected to score, turned into trade value for your league."},
    {id: "pub", title: "Published charts", one: "published chart", many: "published charts",
      note: "Published trade-value opinions. Each series labels its transformation."},
    {id: "observed", title: "Observed-trade estimates", one: "observed-trade estimate", many: "observed-trade estimates",
      note: "Algorithmic estimates from completed fantasy trades. Each series labels its transformation."},
    {id: "vorp", title: "Value above waivers", one: "value-above-waivers series", many: "value-above-waivers series",
      note: "Advanced: raw points above a replacement-level player, each source on its own scale and shown in its own panel."}
  ];
  function seriesGroup(key) {
    if (isDdfKey(key)) return "ddf";
    if (key.endsWith("_vorp")) return "vorp";
    const kind = window.DDFSourceViews.categoryOf(key)?.id;
    return {projections: "proj", published: "pub", observed: "observed"}[kind] || "pub";
  }
  // A series named in the JEG-474 group vocabulary: "DDF Value", "ESPN projection",
  // "FantasyCalc chart (rescaled)", "ESPN value above waivers".
  function groupSeriesName(key) {
    if (isDdfKey(key)) return sourceMeta(key).label;
    const meta = sourceMeta(key);
    const name = PLAIN_NAMES[meta.publisher] || PUBLISHER_NAMES[meta.publisher] || meta.label;
    return {proj: `${name} projection`, pub: `${name} chart (rescaled${RESCALED_TO})`,
      observed: `${name} observed-trade estimate (rescaled${RESCALED_TO})`,
      vorp: `${name} value above waivers`}[seriesGroup(key)];
  }
  const pickerGroupTitle = group => (group.id === "vorp" ? `${group.title} (Advanced)` : group.title);

  // JEG-466: the one series picker every tab uses (Player values' Rank by, Risers & fallers,
  // Compare's Player values shown). A native <select> with one <optgroup> per JEG-474 group,
  // DDF Value first. Each option: symbol, group-vocabulary name, "· Wk N" when the series is
  // on a prior week, and a disabled option carries its reason in the label and the title.
  // entries: [{key, reason}], reason set (a string) when the series cannot be picked.
  function renderSeriesPicker(select, entries, selected) {
    select.replaceChildren();
    select.classList.add("v2-series-picker");
    SERIES_GROUPS.forEach(group => {
      const inGroup = entries.filter(entry => seriesGroup(entry.key) === group.id);
      if (!inGroup.length) return;
      const optgroup = document.createElement("optgroup");
      optgroup.label = pickerGroupTitle(group);
      optgroup.dataset.group = group.id;
      inGroup.forEach(({key, reason}) => {
        const option = document.createElement("option");
        option.value = key;
        option.dataset.group = group.id;
        const item = view && view.infoByKey[key];
        const behind = !(item && item.stale) ? null : isDdfKey(key)
          ? {short: Number.isFinite(item.week) ? `Week ${item.week}` : "Earlier week", label: "Some DDF Value inputs are on an earlier week."}
          : priorWeekInfo(sourceMeta(key).publisher, item, view.refWeek);
        let text = `${sourceMeta(key).symbol} ${groupSeriesName(key)}`;
        if (behind) { text += ` · ${behind.short}`; option.dataset.priorWeek = behind.short; }
        if (reason) { text += ` — ${reason}`; option.disabled = true; }
        option.textContent = text;
        option.title = [behind && behind.label, reason].filter(Boolean).join(" ");
        optgroup.appendChild(option);
      });
      select.appendChild(optgroup);
    });
    const keys = entries.map(entry => entry.key);
    select.value = keys.includes(selected) ? selected : "";
    select.disabled = !entries.some(entry => !entry.reason);
  }
  // JEG-807: a held source is hidden (JEG-569); say "held", not "not available for this league".
  const heldReason = item => Boolean(item && item.excludedReason && /^held/i.test(item.excludedReason));
  const unavailableReason = item => (!item ? "not available" : item.available ? null
    : heldReason(item) ? "held this week (data check)"
      : item.paused ? "waiting on fresh inputs" : "not available for this league");

  // Prior-week badge for a series key: the shared JEG-459 badge, named by publisher.
  function weekBadge(key) {
    const item = view && view.infoByKey[key];
    const badge = priorWeekBadge(sourceMeta(key).publisher, {...item, stale: true}, view && view.refWeek);
    if (!badge) return null;   // the shared badge says nothing when the series is current
    badge.classList.add("v2-wk");
    badge.dataset.priorWeek = key;
    return badge;
  }

  // JEG-457: every source name links to the publisher's page for the served week (new tab). The addresses ship
  // with the data (assets/comparison-sources-data.json); a source with none (ESPN) stays plain text. Projection
  // sources with a page per position pick the page for the player's position in row context, and the QB page in
  // header context. One helper, so every place agrees.
  let sourcePages = {};
  let sourcePagesLoading = null;
  function loadSourcePages() {
    if (sourcePagesLoading) return sourcePagesLoading;
    sourcePagesLoading = fetch("assets/comparison-sources-data.json")
      .then(r => (r.ok ? r.json() : null))
      .catch(() => null)
      .then(doc => {
        const sources = (doc && doc.sources) || {};
        sourcePages = {};
        Object.entries(sources).forEach(([key, s]) => {
          const url = s && (s.url || s.source_url);
          if (typeof url === "string" && /^https?:\/\//.test(url)) sourcePages[key] = url;
        });
        if (C && view) refresh();   // the links arrive after the first draw
        return sourcePages;
      });
    return sourcePagesLoading;
  }
  function sourceUrl(key, position) {
    const publisher = sourceMeta(key).publisher;
    const url = sourcePages[publisher];
    if (!url) return "";
    const pos = ["QB", "RB", "WR", "TE"].includes(position) ? position : "QB";
    if (publisher === "cbsros") return url.replace("/QB/", `/${pos}/`);
    if (publisher === "razzball") return url.replace("-qb-", `-${pos.toLowerCase()}-`);
    return url;
  }
  // A link (or, with no address, plain text) for a source name. Clicking never reaches a row, sort or label behind it.
  function sourceLink(key, text, position) {
    const url = sourceUrl(key, position);
    if (!url) return document.createTextNode(text);
    const a = document.createElement("a");
    a.className = "v2-srclink";
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
    a.dataset.sourceLink = sourceMeta(key).publisher;
    a.textContent = text;
    a.setAttribute("aria-label", `${text}: open the publisher's page in a new tab`);
    // JEG-850: Escape still reaches the page, so it closes Customize from a source link too.
    ["click", "keydown", "pointerdown"].forEach(type => a.addEventListener(type, event => { if (event.key !== "Escape") event.stopPropagation(); }));
    return a;
  }

  // JEG-609 (JEG-460): source divergence "Check" chip. assets/reference-freshness.json publishes
  // source_divergence.<source> = {status: ok | warn | investigate | reviewed | n/a, message, resolution_issue}.
  // warn or investigate shows "Check" with the message as its tooltip; reviewed shows "Reviewed" and, where a
  // link is allowed, links to the resolution issue. It sits where the prior-week badge sits, never hides a
  // source and never blocks anything. Own value series (Data Driven Football) and VORP columns carry none.
  let divergence = {};
  // Jeremy, 2026-10-25: the live dashboard has no links to Linear. A bare ticket id or a linear.app URL is internal
  // bookkeeping, so only a public http(s) page can be linked.
  const resolutionHref = issue => {
    const text = String(issue || "").trim();
    return /^https?:\/\//.test(text) && !/^https?:\/\/([^/]+\.)?linear\.app(\/|$)/i.test(text) ? text : "";
  };
  function divergenceChip(key, opts) {
    const publisher = sourceMeta(key).publisher;
    const method = sourceMeta(key).method;
    if (method === "ddf" || method === "vorp") return null;
    const entry = divergence[publisher];
    const status = entry && entry.status;
    // JEG-834: warn / investigate come from a fixed ceiling as well as the source's own history. A source
    // within 5 points of its own usual rate is inside its usual range: the chip stays (GL-25) but says so plainly.
    const usualGap = entry && Number.isFinite(entry.outlier_rate) && Number.isFinite(entry.usual_outlier_rate)
      ? Math.round(entry.outlier_rate * 100) - Math.round(entry.usual_outlier_rate * 100) : null;
    let inRange = (status === "warn" || status === "investigate") && usualGap !== null && usualGap <= 5;
    // JEG-870: held (red, "Paused this week") replaces the chip; a lag hold (amber) replaces only the in-range check,
    // since an out-of-range finding on a lagging source is still a reading.
    const held = heldReason(view && view.infoByKey && view.infoByKey[key]);
    const level = held ? (sourceHoldLevel(publisher) === "amber" ? "amber" : "red") : sourceHoldLevel(publisher);
    if (held || level === "red") return holdChip(publisher, "red", opts);
    if (level === "amber" && (inRange || !entry || status === "ok" || status === "n/a")) return holdChip(publisher, "amber", opts);
    if (!entry) return null;
    if (status !== "warn" && status !== "investigate" && status !== "reviewed" && status !== "excluded") return null;
    const href = (status === "reviewed" || status === "excluded") && !(opts && opts.noLink) ? resolutionHref(entry.resolution_issue) : "";
    const chipClass = status === "excluded" ? "excluded" : (status === "reviewed" ? "reviewed" : (inRange ? "ok" : "check"));
    const chip = document.createElement(href ? "a" : "span");
    chip.className = `v2-div-chip is-${chipClass}`;
    chip.dataset.divergence = publisher;
    chip.dataset.status = status;
    const word = status === "excluded" ? "Excluded" : (status === "reviewed" ? "Reviewed" : (inRange ? "Normal range" : "Under review"));
    const message = inRange
      ? `${PUBLISHER_NAMES[publisher] || publisher}: in line with its usual range (${Math.round(entry.outlier_rate * 100)}% vs ${Math.round(entry.usual_outlier_rate * 100)}%).`
      : String(entry.message || "").trim() || `${PUBLISHER_NAMES[publisher] || publisher} disagrees with the other sources more than usual.`;
    chip.title = message;
    if (href) { chip.href = href; chip.target = "_blank"; chip.rel = "noopener"; }
    else { chip.setAttribute("role", "img"); }
    chip.setAttribute("aria-label", `${word}: ${message}`);
    // JEG-856: in range is a green checkmark glyph (no box, no word); its name is the aria-label and title.
    if (inRange) {
      chip.insertAdjacentHTML("beforeend", '<svg class="v2-ok-mark" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="8"/><path d="M4.5 8.4l2.4 2.4 4.6-5" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>');
      return chip;
    }
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = status === "excluded" ? "✗ " : (status === "reviewed" ? "✓ " : "⚑ ");
    const wordSpan = document.createElement("span");
    wordSpan.className = "v2-div-word";
    wordSpan.textContent = word;
    chip.append(sym, wordSpan);
    return chip;
  }
  // JEG-870: the pulse's hold on a source, from the published data: "red" (held, out of the blend, "Paused this
  // week"), "amber" (JEG-726: lagging, still in DDF Value, a refresh pending) or null. Derived sections carry the
  // root's hold.
  function sourceHoldLevel(publisher) {
    const sources = (window.TradeValueComparisonData && window.TradeValueComparisonData.sources) || {};
    for (const section of [publisher, `${publisher}_adjusted`, `${publisher}_vorp`]) {
      const hold = sources[section] && (sources[section].validationHold || sources[section].promotionHold);
      if (hold) return hold.hold_level === "amber" ? "amber" : "red";
    }
    return null;
  }
  // JEG-870: a held source's divergence is not a reading this week, so it never gets the in-range check. The chip
  // is the hold marker instead, in the existing hold words: an amber flag for a lag hold, "Paused" for a red hold.
  // Where the row already says "Paused this week" (Customize, opts.heldNoted) the red marker is the glyph only.
  function holdChip(publisher, level, opts) {
    const name = PUBLISHER_NAMES[publisher] || publisher;
    const amber = level === "amber";
    const word = amber ? "Lagging" : "Paused";
    const message = amber ? `${name} is lagging: included in DDF Value, a refresh is pending.`
      : `${name} is paused this week: temporarily held for a data check.`;
    const chip = document.createElement("span");
    chip.className = `v2-div-chip is-hold is-${amber ? "lag" : "paused"}`;
    chip.dataset.divergence = publisher;
    chip.dataset.status = "held";
    chip.dataset.hold = level;
    chip.title = message;
    chip.setAttribute("role", "img");
    chip.setAttribute("aria-label", `${word}: ${message}`);
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = amber ? "⚑" : "⏸";
    chip.appendChild(sym);
    if (amber || !(opts && opts.heldNoted)) {
      const wordSpan = document.createElement("span");
      wordSpan.className = "v2-div-word";
      wordSpan.textContent = word;
      chip.append(" ", wordSpan);
    }
    return chip;
  }
  const appendDivergence = (parent, key, opts) => {
    const chip = divergenceChip(key, opts);
    if (chip) parent.append(document.createTextNode(" "), chip);
  };

  // One series in plain words, whatever the width: "ESPN · Our value", "FantasyCalc chart".
  function plainSeries(publisher, method) {
    if (publisher === "ddf") return "DDF Value";
    const name = PLAIN_NAMES[publisher] || PUBLISHER_NAMES[publisher] || publisher;
    return method === "indexed" ? `${name} chart (rescaled${RESCALED_TO})` : `${name} · ${PLAIN_METHOD[method]}`;
  }

  // JEG-471: the DDF Value (engine key "ddf_value") is our composite. It lives on the engine's rows,
  // not in its source toggles, so v2 keeps whether it is shown (ddfShown) and draws it first and heavier.
  const DDF_KEY = "ddf_value";
  // JEG-542 / GL-09: the DDF Value versions. Blended (DDF_KEY) is shown and ranked by default; the projections
  // alternate is off until picked. `field` is the engine's row.ddfByVersion key.
  // JEG-1073 (Jeremy, 2026-10-25): DDF Value is the Adjusted trade chart average, so "DDF Value" and the engine's
  // charts version are one series, and the projections version is the alternate. (JEG-863 hid the projections id
  // for the same reason after JEG-804; this is the mirror.) The ids stay (saved selections and links carry them).
  // The duplicate id is hidden from every picker (`sameAs`), and a saved pick of it reads as the visible one
  // (ddfPickKey). `blend`: the version the reader's basis builds (the projections one is not).
  const DDF_VERSIONS = {
    ddf_value: {field: "blended", label: "DDF Value", symbol: "★", light: "#A84410", dark: "#F28C5B", blend: true},
    ddf_value_charts: {field: "charts", label: "DDF Value", symbol: "★", light: "#A84410", dark: "#F28C5B",
      blend: true, sameAs: "ddf_value"},
    ddf_value_projections: {field: "projections", label: "DDF Value (projections)", symbol: "✦", light: "#8A5A00", dark: "#E6B450", blend: false}
  };
  const DDF_KEYS = Object.keys(DDF_VERSIONS);
  const isDdfKey = key => Object.prototype.hasOwnProperty.call(DDF_VERSIONS, key);
  // The versions a reader can pick (one per distinct series), and the visible id for any DDF id.
  const DDF_PICK_KEYS = DDF_KEYS.filter(key => !DDF_VERSIONS[key].sameAs);
  const ddfPickKey = key => (isDdfKey(key) && DDF_VERSIONS[key].sameAs) || key;
  const pickableSeries = keys => [...new Set(keys.map(ddfPickKey))];
  // One version's entry on an engine row: {value, count, sources, reason, lowConfidence, confidenceNote, prior, ...}.
  const ddfEntry = (row, key) => (row && row.ddfByVersion && isDdfKey(key) ? row.ddfByVersion[DDF_VERSIONS[key].field] : null) || null;
  function sourceMeta(key) {
    if (isDdfKey(key)) {
      const version = DDF_VERSIONS[key];
      return {key, method: "ddf", publisher: "ddf", label: version.label, symbol: version.symbol,
        color: isDark() ? version.dark : version.light, short: version.label};
    }
    let method;
    let publisher;
    if (key.endsWith("_vorp")) { method = "vorp"; publisher = key.slice(0, -5); }
    // JEG-508: the engine's DDF inputs are now "<chart>_adj_values" (the chart's adjusted values).
    else if (key.endsWith("_adj_values")) { method = "dda"; publisher = key.slice(0, -11); }
    else if (key === "espn" || key === "cbsros" || key === "razzball") { method = "dda"; publisher = key; }
    else { method = "indexed"; publisher = key; }
    const pub = PUBLISHERS[publisher] || {label: key, color: "#64736F", symbol: "•"};
    return {key, method, publisher, ...pub, color: PUBLISHERS[publisher] ? pubColor(publisher) : pub.color,
      short: isNarrow() ? `${pub.label} · ${SHORT_METHOD[method]}` : plainSeries(publisher, method)};
  }

  const SHOW_DEFAULT = "100";
  const state = {
    search: "",
    range: {min: null, max: null},
    delta: false,
    window: null,          // [lo, hi] 1-based rank window (chart and table)
    windowPreset: SHOW_DEFAULT,   // the toolbar's "Show" (JEG-475); "custom" after a brush, zoom or exact ranks
    zoomFrom: null,        // JEG-483: the Show preset before a zoom or brush made it Custom (Reset zoom returns to it)
    rankZoom: false,       // JEG-483: the rank window itself was zoomed or brushed (not only the value range)
    axisZoom: true,        // JEG-483: in the expanded chart the Y axis fits the value range
    sort: null,            // {key, dir}; null = rank-series order
    shown: PAGE_SIZE,
    hoverIndex: null,
    focusIndex: 0,
    metaCols: {pos: true, team: true, tier: true},
    hiddenGroups: new Set(),  // JEG-473 Columns menu: method groups the reader hid
    hiddenSeries: new Set()   // JEG-503 legend toggles: series the reader turned off (the ranking series cannot be)
  };
  let C = null;            // TradeValueCurveControls
  let view = null;         // derived snapshot for rendering

  // ---------- engine bootstrap (fail closed) ----------
  function engineError() {
    const status = document.querySelector("#legacyEngine #curve-status");
    const text = status ? status.textContent || "" : "";
    return /unavailable|did not pass|failed/i.test(text) ? text.trim() : null;
  }

  function waitForEngine() {
    const started = Date.now();
    return new Promise((resolve, reject) => {
      (function poll() {
        const controls = window.TradeValueCurveControls;
        const err = engineError();
        if (err) return reject(new Error(err));
        if (controls && typeof controls.getRows === "function" && window.TradeValueCurveDiagnostics) {
          const rows = controls.getRows();
          if (rows.length) return resolve(controls);
        }
        if (Date.now() - started > 30000) return reject(new Error("The value engine did not finish loading."));
        setTimeout(poll, 120);
      })();
    });
  }

  // Frame 18: the engine failed or never finished. No tab is shown, so no
  // stale or partial value can be read as current; say why and offer a retry.
  function showFailure(reason) {
    setStatus("");
    ["v2Main", "v2Targets", "v2Risers", "v2Compare", "v2FindTrade", "v2FindLeague", "v2Waivers", "v2How", "v2Audit", "v2Research"].forEach(id => { $(id).hidden = true; });
    const card = $("v2State").querySelector(".v2-state");
    card.dataset.state = "failed";
    $("v2State").hidden = false;
    $("v2FreshnessLabel").textContent = "Values unavailable";
    $("v2StateSym").textContent = "!";
    $("v2StateTitle").textContent = "Values are unavailable right now";
    $("v2StateText").textContent = `${reason} No values are shown rather than showing wrong or partial ones.`;
    const retry = $("v2StateRetry");
    retry.hidden = false;
    retry.onclick = () => location.reload();
    applyStatic();
  }

  // ---------- Manifesto (static text) ----------
  // It needs no engine, so it shows at once, and still shows if the engine fails. The league bar and
  // the loading / failure card belong to the value tabs; until the engine is ready they follow the hash here.
  function applyStatic() {
    const section = writingSection();
    const onManifesto = section === "manifesto";
    const onResearch = section === "research";
    const onText = onManifesto || onResearch;
    $("v2Writing").hidden = !section;
    document.querySelectorAll("#v2WritingTabs .v2-subtab").forEach(tab => {
      if (tab.dataset.writing === section) tab.setAttribute("aria-current", "page"); else tab.removeAttribute("aria-current");
    });
    $("v2Manifesto").hidden = !onManifesto;
    $("v2Research").hidden = !onResearch;
    if (onResearch) showResearchPage();
    $("v2Context").hidden = onText;
    if (!C) {
      $("v2State").hidden = onText;
    }
  }

  // Research (JEG-543): #writing/research is the index, #writing/research/<slug> one post. Both are static text built into the
  // page, so they show without the engine. An unknown slug falls back to the index.
  function showResearchPage() {
    const slug = decodeURIComponent(hashBase().slice("#writing/research/".length));
    const posts = [...document.querySelectorAll("#v2Research .v2-rs-post")];
    const post = hashBase().startsWith("#writing/research/") ? posts.find(node => node.dataset.slug === slug) : null;
    posts.forEach(node => { node.hidden = node !== post; });
    $("v2ResearchIndex").hidden = Boolean(post);
    if (post) window.scrollTo(0, 0);
  }

  // Before the engine is ready, only the Manifesto can show; it follows the hash on its own.
  function bindManifesto() {
    window.addEventListener("hashchange", () => { canonicalizeHash(); if (!C) applyStatic(); });
    applyStatic();
  }

  function setStatus(text, isError) {
    const node = $("v2Status");
    node.textContent = text || "";
    node.hidden = !text;
    node.classList.toggle("is-error", Boolean(isError));
  }

  // ---------- derived view ----------
  // Week labels come from the data's own freshness record (content week and
  // which series are an older week), the same record that picks first-load sources.
  const isEngineAlias = key => key.endsWith("_adjusted");
  function sourceInfoWithFreshness() {
    // JEG-626: the engine still lists the deprecated "<chart>_adjusted" aliases; v2 reads the raw chart series.
    const info = C.getSourceInfo({includeComposite: true}).filter(item => !isEngineAlias(item.key));
    const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
    info.forEach(item => {
      const series = freshness?.series?.[item.key];
      if (series && typeof series.is_older_week === "boolean") item.stale = series.is_older_week;
      if (series && !item.week && Number.isFinite(series.vintage_week)) item.week = series.vintage_week;
    });
    // JEG-1178 (Jeremy, 2026-10-27): inside a week view a source is labelled with the week it contributes to that view.
    // One that already moved on to the next week still carries the newer week in its data; the view prices it on its
    // saved copy of the viewed week, so that is the week it shows. A source left out of the view keeps its own label.
    const weekState = C.getWeekState ? C.getWeekState() : null;
    if (weekState && weekState.servedWeeks && Number.isInteger(weekState.week)) {
      info.forEach(item => {
        if (isDdfKey(item.key)) return;
        const served = weekState.servedWeeks[sourceMeta(item.key).publisher];
        // Only a source that moved past the viewed week; one on the viewed week keeps its own label.
        if (Number.isInteger(served) && served > weekState.week) {
          item.servedWeek = served;
          item.week = weekState.week;
        }
      });
    }
    return info;
  }
  // JEG-912: a rounding residue never shows a sign ("-0.0" is "0.0").
  const fmt = v => { if (!Number.isFinite(v)) return "—"; const text = v.toFixed(1); return text === "-0.0" ? "0.0" : text.replace("-", "−"); };

  // JEG-502 (Jeremy, 2026-10-09): every active NFL player is searchable. A player no source
  // prices (engine universe_only) appears only in search results, never in a table or chart,
  // as "0.0" with the engine's reason. The engine builds his row (C.searchPlayers); no math here.
  const UNPRICED_REASON = "No chart or projection prices this player.";
  const UNPRICED_SHOWN = 8;
  const unpricedCache = new Map();   // query|position -> rows; cleared when the engine's rows change
  function unpricedMatches(query) {
    const q = String(query || "").trim();
    if (!q || !C || typeof C.searchPlayers !== "function") return [];
    const position = C.getState().position;
    const cacheKey = `${q.toLowerCase()}|${position}`;
    if (unpricedCache.has(cacheKey)) return unpricedCache.get(cacheKey);
    const fits = pos => !position || position === "ALL" ? true
      : position === "FLEX" ? ["RB", "WR", "TE"].includes(pos) : pos === position;
    // JEG-861: the engine's search is a plain "contains" on the whole query, so "Nacua Puka" would miss.
    // Pull a superset from the engine (each query word's first two letters; every match of the page's
    // matcher starts a name word with them) and keep only what the one shared matcher accepts.
    const NS = window.TradeValueNameSearch;
    const pool = new Map();
    NS.tokens(q).forEach(word => {
      C.searchPlayers(word.slice(0, 2), {limit: 5000}).forEach(row => { if (row && !pool.has(row.player_key)) pool.set(row.player_key, row); });
    });
    const rows = NS.filter([...pool.values()], q).filter(row => row.universe_only && fits(row.pos));
    if (unpricedCache.size > 50) unpricedCache.clear();
    unpricedCache.set(cacheKey, rows);
    return rows;
  }
  // GL-20: no source prices him, so he is worth 0.0 (the engine leaves DDF Value null for these rows since JEG-508).
  const unpricedValue = () => "0.0";
  const unpricedReason = row => row.unpriced_reason || UNPRICED_REASON;
  function renderUnpriced(id, query) {
    const box = $(id);
    const rows = unpricedMatches(query);
    box.replaceChildren();
    box.hidden = !rows.length;
    if (!rows.length) return rows;
    const head = document.createElement("p");
    head.className = "v2-unpriced-head";
    head.textContent = `○ Not valued · ${rows.length} player${rows.length === 1 ? "" : "s"} matching “${String(query).trim()}”: worth 0.0`;
    const list = document.createElement("ul");
    list.className = "v2-unpriced-list";
    rows.slice(0, UNPRICED_SHOWN).forEach(row => {
      const li = document.createElement("li");
      li.dataset.playerKey = String(row.player_key);
      li.dataset.unpriced = "";
      const name = document.createElement("b");
      name.textContent = row.name;
      const meta = document.createElement("span");
      meta.className = "v2-meta";
      meta.textContent = ` ${row.pos}`;   // the reason names his current status and team; row.team can be stale
      const value = document.createElement("span");
      value.className = "v2-unpriced-value";
      value.dataset.source = DDF_KEY;
      value.textContent = `DDF Value ${unpricedValue(row)}`;
      const why = document.createElement("span");
      why.className = "v2-meta v2-unpriced-why";
      why.textContent = unpricedReason(row);
      li.append(name, meta, value, why);
      list.appendChild(li);
    });
    box.append(head, list);
    if (rows.length > UNPRICED_SHOWN) {
      const more = document.createElement("p");
      more.className = "v2-meta";
      more.textContent = `${rows.length - UNPRICED_SHOWN} more not valued. Type more of the name to narrow it.`;
      box.appendChild(more);
    }
    return rows;
  }

  // GAP-025: a label + symbol badge for players ESPN projects at 0
  // (injured/out). The engine flags them from ESPN's own row; a player ESPN has
  // no row for is missing, not 0, and gets nothing. Published values stay as
  // published; the engine gives the player an ESPN value of 0.0.
  function espnZeroBadge(row) {
    let copy = row && row.espnProjectsZero ? window.TradeValueProductData?.ESPN_ZERO_BADGE : null;
    if (!copy) return null;
    // JEG-834: while ESPN is held its zero is not a reading we use. Say "held this week", not a zero.
    if (heldReason(view && view.infoByKey && view.infoByKey.espn)) {
      copy = {label: "ESPN: held this week", symbol: copy.symbol,
        title: "ESPN is held this week for a data check, so no ESPN value is used for this player."};
    }
    const badge = document.createElement("span");
    badge.className = "v2-espn-zero";
    badge.dataset.espnZero = "";
    badge.title = copy.title;
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = copy.symbol;
    badge.append(sym, document.createTextNode(` ${copy.label}`));
    return badge;
  }
  // JEG-947 (Jeremy 2026-10-23): on phones and touch screens the pinned name column reads "Last, First" and clips with an
  // ellipsis; the full "First Last" is the title (desktop hover, long press) and a tap on a clipped name shows it in a small
  // popover. Desktop keeps "First Last" untouched. The text swaps with the media query, so resizing stays correct.
  const PHONE_NAMES = window.matchMedia("(max-width: 767px), (pointer: coarse)");
  const phoneName = (name, pos) => (PHONE_NAMES.matches && window.DDFNameFormat ? window.DDFNameFormat.lastFirst(name, pos) : name);
  function nameSpan(row) {
    const span = document.createElement("span");
    span.className = "v2-nm";
    span.dataset.full = row.name;
    span.dataset.pos = row.pos || "";
    span.title = row.name;
    span.textContent = phoneName(row.name, row.pos);
    return span;
  }
  PHONE_NAMES.addEventListener("change", () => {
    document.querySelectorAll(".v2-nm").forEach(span => { span.textContent = phoneName(span.dataset.full, span.dataset.pos); });
    if (view) renderHeader();   // JEG-1193: the context strip's Reviewed chip is a link on desktop only
  });
  (() => {
    let pop = null;
    const hide = () => { if (pop) { pop.remove(); pop = null; } };
    // Capture phase: a tap on a clipped name only reveals it (the rest of the row still opens the drawer, as before).
    document.addEventListener("click", event => {
      const span = event.target.closest && event.target.closest(".v2-nm");
      const wasShown = pop && pop.dataset.for === (span && span.dataset.full);
      hide();
      if (!span || !PHONE_NAMES.matches || span.scrollWidth <= span.clientWidth + 1 || wasShown) return;
      event.stopPropagation();
      pop = document.createElement("div");
      pop.className = "v2-nm-pop";
      pop.setAttribute("role", "status");
      pop.dataset.for = span.dataset.full;
      pop.textContent = span.dataset.full;
      (document.querySelector(".v2-app") || document.body).appendChild(pop);   // body.v2 hides every other direct child
      const box = span.getBoundingClientRect();
      pop.style.left = `${Math.max(8, Math.min(box.left, innerWidth - pop.offsetWidth - 8))}px`;
      pop.style.top = `${box.bottom + 4}px`;
      setTimeout(hide, 3500);
    }, true);
    window.addEventListener("scroll", hide, {passive: true, capture: true});
  })();

  // JEG-892: the bye week on a player row's sub-line (player-flags.js), nothing for a free agent, then `tail`
  // (the tier), so the tier stays the sub-line's last part.
  function appendFlags(sub, row, tail) {
    const flags = window.DDFPlayerFlags ? window.DDFPlayerFlags.node(row) : null;
    if (flags) sub.appendChild(flags);
    if (tail) sub.appendChild(document.createTextNode(tail));
  }
  function appendEspnZero(parent, row) {
    const badge = espnZeroBadge(row);
    if (badge) parent.appendChild(badge);
  }
  const tierLabel = role => ({starter: "Starter", bench: "Bench", waiver: "Waiver"}[role] || "—");
  // JEG-483: sort order for the Tier column (Starter, Bench, Waiver, then —).
  const TIER_ORDER = {starter: 0, bench: 1, waiver: 2};

  // Tier / roster tier (Jeremy, 2026-10-08): it follows the series a tab ranks or values by, never
  // always ESPN. DDF Value: the engine's row.ddfTier. Any other series: the player's rank by that
  // series against the engine's roster zones for that ranking (rank < starter_to_bench = Starter,
  // < bench_to_waiver = Bench, else Waiver). A display mapping, not value math. null ("—") when the
  // series has no value for the player.
  // scope: {rows, pos, engineOrder}. rows = the list ranked within (engineOrder: C.getRows() order,
  // so the engine's own ranking series reads row order against getZones(), as the chart's lines do).
  const tierRanks = new WeakMap();
  function tierFor(row, key, scope) {
    if (!row || !key) return null;
    if (key === DDF_KEY) return row.ddfTier || null;
    if (isDdfKey(key)) return ddfTierFor(row, key, scope);
    const value = row.values ? row.values[key] : null;
    if (!Number.isFinite(value) || !scope || !scope.rows) return null;
    let byKey = tierRanks.get(scope.rows);
    if (!byKey) tierRanks.set(scope.rows, byKey = new Map());
    let entry = byKey.get(key);
    if (!entry) {
      const enginePos = C.getState().position;
      const pos = scope.pos || enginePos;
      const engineRanked = Boolean(scope.engineOrder) && key === C.getRankSource() && pos === enginePos;
      const ranks = new Map();
      if (engineRanked) {
        scope.rows.forEach((r, index) => ranks.set(String(r.player_key), index + 1));
      } else {
        scope.rows.map((r, index) => ({r, index})).filter(({r}) => Number.isFinite(r.values?.[key]))
          .sort((a, b) => b.r.values[key] - a.r.values[key] || a.index - b.index)
          .forEach(({r}, index) => ranks.set(String(r.player_key), index + 1));
      }
      const zones = engineRanked ? C.getZones()
        : typeof C.getZonesFor === "function" ? C.getZonesFor(key, pos)
        : C.getRankSource() !== DDF_KEY || pos === "ALL" ? C.getZones() : null;
      entry = {ranks, zones};
      byKey.set(key, entry);
    }
    const rank = entry.ranks.get(String(row.player_key));
    const sb = entry.zones && entry.zones.starter_to_bench;
    const bw = entry.zones && entry.zones.bench_to_waiver;
    if (!Number.isFinite(rank) || !Number.isFinite(sb) || !Number.isFinite(bw)) return null;
    return rank < sb ? "starter" : rank < bw ? "bench" : "waiver";
  }
  // A DDF Value version other than the blend has no engine tier: rank by that version in the same rows and
  // read the blend's roster zones (the same starter / bench cut-offs), so the three read alike.
  function ddfTierFor(row, key, scope) {
    if (!Number.isFinite(row.values?.[key]) || !scope || !scope.rows) return null;
    const blended = scope.rows.filter(r => r.ddfTier);
    if (!blended.length) return null;
    const counts = {starter: 0, bench: 0};
    blended.forEach(r => { if (r.ddfTier in counts) counts[r.ddfTier] += 1; });
    const ahead = scope.rows.filter(r => Number.isFinite(r.values?.[key]) && r.values[key] > row.values[key]).length;
    return ahead < counts.starter ? "starter" : ahead < counts.starter + counts.bench ? "bench" : "waiver";
  }
  const tierText = (row, key, scope) => tierLabel(tierFor(row, key, scope));
  // JEG-579 (P3-source-ranks): "12 overall · WR5" under a value cell = the player's rank within that series
  // (every position, priced players only); the # column carries the position rank under the overall rank.
  // Display only, from the series' own values; shown at 1200 px and wider (CSS).
  function sourceRanks(key) {
    view.sourceRanks = view.sourceRanks || {};
    if (view.sourceRanks[key]) return view.sourceRanks[key];
    const ranks = new Map();
    const perPos = {};
    (view.tierScope.rows || []).filter(r => Number.isFinite(r.values?.[key]))
      .sort((a, b) => b.values[key] - a.values[key])
      .forEach((r, index) => {
        perPos[r.pos] = (perPos[r.pos] || 0) + 1;
        ranks.set(String(r.player_key), {overall: index + 1, pos: `${r.pos}${perPos[r.pos]}`});
      });
    view.sourceRanks[key] = ranks;
    return ranks;
  }
  function rankSubLabel(className, text) {
    const span = document.createElement("span");
    span.className = className;
    span.textContent = text;
    return span;
  }
  // JEG-571: Start / Hold / Stash / Drop chip. The rule lives in assets/player-tags.js (pure, tested); the
  // tag follows the engine's DDF Value tier on the reader's league settings. null (no chip) when unpriced.
  const TAG_NOTES = {
    Start: "Inside the starter count on your league settings",
    Hold: "On the bench: keep",
    Stash: "Not a starter yet, but a real chance to start",
    Drop: "At or below the best free alternative"
  };
  function playerTagOf(row) {
    const tags = window.PlayerTags;
    return tags && typeof tags.playerTag === "function" ? tags.playerTag(row) : null;
  }
  // JEG-901: what a hover `title` says, as an accessible description too (keyboard, touch and screen readers).
  function describe(node, text) {
    if (text) node.setAttribute("aria-description", text);
    return node;
  }
  function tagChip(row) {
    const tag = playerTagOf(row);
    if (!tag) return null;
    const chip = document.createElement("span");
    chip.className = `v2-tag v2-tag-${tag.toLowerCase()}`;
    chip.dataset.tag = tag;
    chip.title = TAG_NOTES[tag];
    chip.setAttribute("role", "img");
    chip.setAttribute("aria-label", `${tag}: ${TAG_NOTES[tag]}`);
    chip.textContent = tag;
    return chip;
  }
  function appendTag(parent, row) {
    const chip = tagChip(row);
    if (chip) parent.appendChild(chip);
  }
  // The chip sits NEXT TO the sub-line, never inside it: the sub-line's text ("QB · KC · Starter") is the
  // tier a reader or screen reader gets, and the chip is its own element (it was concatenating "StarterStart").
  function subWithTag(sub, row) {
    const chip = tagChip(row);
    if (!chip) return sub;
    const wrap = document.createElement("span");
    wrap.className = "v2-subrow";
    wrap.append(sub, chip);
    return wrap;
  }
  function lineupShareText(row) {
    if (!Number.isFinite(row.lineupShare)) return null;
    return `Expected lineup share: ${Math.round(row.lineupShare * 100)}% how much of this player's production reaches a lineup.`;
  }

  // Low-confidence DDF Value (Jeremy, 2026-10-08): when exactly one input prices a player the engine
  // still gives a DDF Value (that input's value) and flags it (row.ddfLowConfidence). Shown everywhere
  // that value appears as "◐ 1 source" (symbol + label), with the engine's note as the tooltip.
  const LOW_CONFIDENCE_NOTE = "Only one source prices this player";
  const isLowConfidence = (row, key) => {
    const entry = ddfEntry(row, key);
    // The blend also honours the flat row.ddfLowConfidence the engine keeps for it.
    const flagged = key === DDF_KEY ? Boolean(row && row.ddfLowConfidence) : Boolean(entry && entry.lowConfidence);
    return flagged && Number.isFinite(row.values?.[key]);
  };
  function lowConfidenceNode(row, key = DDF_KEY) {
    const entry = ddfEntry(row, key);
    const node = document.createElement("span");
    node.className = "v2-lowconf";
    node.dataset.lowConfidence = "";
    const count = key === DDF_KEY ? (Number.isFinite(row.ddfCount) ? row.ddfCount : 1)
      : (entry && Number.isFinite(entry.count) ? entry.count : 1);
    const label = `${count} source${count === 1 ? "" : "s"}`;
    // Jeremy (2026-10-09): tag "◐ 1 source"; the engine's note is the tooltip and part of the accessible name.
    node.title = (key === DDF_KEY ? row.ddfConfidenceNote : entry && entry.confidenceNote) || LOW_CONFIDENCE_NOTE;
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", `${label}: ${node.title}`);
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = "◐";
    node.append(sym, document.createTextNode(` ${label}`));
    return node;
  }
  // Estimated values (VP-11, JEG-541): row.estimated = {seriesKey: reason} marks a chart value the
  // engine filled in for a rosterable player the chart doesn't list (VP-2.4). Wherever that value is
  // shown it carries "≈ estimated" (symbol + word), with the engine's reason as the tooltip.
  const estimatedReason = (row, key) => {
    const reason = row && row.estimated ? row.estimated[key] : null;
    return typeof reason === "string" && reason.trim() && Number.isFinite(row.values?.[key]) ? reason : null;
  };
  function estimatedNode(reason) {
    const node = document.createElement("span");
    node.className = "v2-estimated";
    node.dataset.estimated = "";
    node.title = reason;
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", `estimated: ${reason}`);
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = "≈";
    node.append(sym, document.createTextNode(" estimated"));
    return node;
  }
  // Every finite value v2 shows passes through here, so both value tags live in one place.
  function appendLowConfidence(parent, row, key) {
    if (isLowConfidence(row, key)) parent.appendChild(lowConfidenceNode(row, key));
    const reason = estimatedReason(row, key);
    if (reason) parent.appendChild(estimatedNode(reason));
  }
  // JEG-1059: the badge that marks a value the reader set on the Overrides tab. It sits next to the value
  // itself, on every view that shows one.
  function appendOverrideFlag(parent, row) {
    const badge = window.DDFOverrides && window.DDFOverrides.flag ? window.DDFOverrides.flag(row) : null;
    if (badge) parent.appendChild(badge);
    return badge;
  }
  // Player values: the Rank by series over the engine's ranked rows.
  const valuesTier = row => tierText(row, view.rankKey, view.tierScope);

  // DDF Value first, then the ranking series, then DDA, Index, VORP (frame 22: one ordering everywhere).
  function orderSeries(keys, rankKey) {
    const methodOrder = {ddf: -1, dda: 0, indexed: 1, vorp: 2};
    return keys.slice().sort((a, b) => (b === DDF_KEY) - (a === DDF_KEY) || (b === rankKey) - (a === rankKey)
      || methodOrder[sourceMeta(a).method] - methodOrder[sourceMeta(b).method]);
  }

  function collect() {
    const info = sourceInfoWithFreshness();
    const infoByKey = Object.fromEntries(info.map(item => [item.key, item]));
    const active = ddfShownList().filter(key => infoByKey[key]).concat(C.getActiveSources());
    const rankKey = C.getRankSource();
    // JEG-477: ranking by a DDF weighted projection (ESPN, CBS rest of season, Razzball) that is not among the shown
    // series puts that series on the chart and in the table, so the order can be read.
    if (!active.includes(rankKey) && !isDdfKey(rankKey) && infoByKey[rankKey]) active.push(rankKey);
    const ordered = orderSeries(active, rankKey);
    const plotKeys = ordered.filter(key => sourceMeta(key).method !== "vorp");
    const vorpKeys = ordered.filter(key => sourceMeta(key).method === "vorp");
    const allRows = C.getRows();
    allRows.forEach((row, index) => { row.fullRank = index + 1; });
    const needle = state.search.trim().toLowerCase();
    // Search narrows the list and renumbers it; the rank window (Show / X brush) and the value range
    // (Y brush) then compose: shown = ranks lo..hi ∩ ranking-series value in [min, max] (JEG-472).
    // JEG-477: a player no shown series prices above 0 (DDF Value included) is hidden; a search finds him again, as a 0.
    const pricedKeys = plotKeys.concat(vorpKeys);
    const pricedAbove0 = row => pricedKeys.some(key => Number.isFinite(row.values?.[key]) && row.values[key] > 0);
    const listed = needle ? allRows : allRows.filter(pricedAbove0);
    const hiddenZero = allRows.length - listed.length;
    const rows = needle ? window.TradeValueNameSearch.filter(allRows, state.search) : listed;
    rows.forEach((row, index) => { row.rank = index + 1; });
    const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
    // JEG-806: the header week is the data's week (first_load_reference_week),
    // not the calendar week (current_content_week). When no source has reached
    // the calendar week, the header must not claim a week it cannot back.
    const refWeek = freshness?.first_load_reference_week || C.getReferenceWeek();
    const calendarWeek = freshness?.current_content_week || null;
    const n = rows.length;
    // A Custom that comes only from the value range keeps the remembered preset's rank window (JEG-483).
    const preset = state.windowPreset === "custom" && !state.rankZoom ? state.zoomFrom || SHOW_DEFAULT : state.windowPreset;
    const zone = zoneWindow(rows, preset);
    if (zone) {
      state.window = [Math.min(zone[0], Math.max(1, n)), Math.max(1, Math.min(zone[1], n))];
    } else if (!state.window || preset !== "custom") {
      const hi = preset === "all" ? n : Number(preset) || n;
      state.window = [1, Math.max(1, Math.min(n, hi))];
    } else {
      state.window = [Math.max(1, Math.min(state.window[0], n)), Math.max(1, Math.min(state.window[1], n))];
    }
    const {min, max} = state.range;
    const rangeOn = min !== null || max !== null;
    let omittedMissing = 0;
    const visible = rows.slice(state.window[0] - 1, state.window[1]).filter(row => {
      if (!rangeOn) return true;
      const v = row.values[rankKey];
      if (!Number.isFinite(v)) { omittedMissing += 1; return false; }
      return (min === null || v >= min) && (max === null || v <= max);
    });
    // The Y brush's scale: the ranking series' own spread over the listed players (display only).
    const rankValues = rows.map(row => row.values[rankKey]).filter(Number.isFinite);
    const yScale = {lo: Math.floor(Math.min(0, ...rankValues)), hi: Math.max(1, Math.ceil(Math.max(0, ...rankValues)))};
    view = {info, infoByKey, active, rankKey, plotKeys, vorpKeys, rows, visible,
      tierScope: {rows: allRows, pos: C.getState().position, engineOrder: true}, totalRows: allRows.length, omittedMissing,
      rangeOn, yScale, rankValues, refWeek, calendarWeek, state: C.getState(), roster: C.getRosterShape(), hiddenZero};
  }

  // Frame 21 Starter / Bench / Waiver: the engine's roster boundaries (getZones, in
  // ranking-series order) mapped onto the filtered list. null for the other presets.
  function zoneWindow(rows, preset) {
    if (!["starter", "bench", "waiver"].includes(preset) || !rows.length) return null;
    const zones = C.getZones ? C.getZones() : {};
    const sb = zones.starter_to_bench;
    const bw = zones.bench_to_waiver;
    if (!Number.isFinite(sb) || !Number.isFinite(bw)) return null;
    const inZone = row => (preset === "starter" ? row.fullRank < sb
      : preset === "bench" ? row.fullRank > sb && row.fullRank < bw : row.fullRank > bw);
    const first = rows.findIndex(inZone);
    if (first < 0) return [1, 1];
    let lastIndex = first;
    rows.forEach((row, index) => { if (inZone(row)) lastIndex = index; });
    return [first + 1, lastIndex + 1];
  }

  // GAP-043: the same per-source freshness wording the main page uses.
  function freshnessText(item) {
    const pd = window.TradeValueProductData;
    const row = pd?.getSourceFreshness?.()?.series?.[item.key];
    if (row && pd.freshnessLabel) return pd.freshnessLabel(row).text;
    return item.week ? `Week ${item.week}${item.stale ? " · older week" : ""}` : "content week unknown";
  }

  // V2-WAIVER-COVERAGE: a published chart that lists fewer players than this
  // league rosters has its waiver line extrapolated from the other charts
  // (engine getSourceInfo().waiverNote). Say so wherever its source is listed.
  function withWaiverNote(text, item) {
    return item && item.waiverNote ? `${text} · ${item.waiverNote}` : text;
  }

  function sourceLabelFor(key) {
    const meta = sourceMeta(key);
    const item = view.infoByKey[key];
    const week = item && item.week ? ` · Week ${item.week}` : "";
    return `${meta.short}${week}`;
  }

  // JEG-475 "Show": one range control. A brush, zoom or exact ranks make it "Custom 12–48", naming the
  // ranks actually shown (rank window ∩ value range).
  function renderShow() {
    const custom = $("v2ShowCustom");
    const isCustom = state.windowPreset === "custom";
    custom.hidden = !isCustom;
    const first = view.visible[0];
    const last = view.visible[view.visible.length - 1];
    custom.textContent = first ? `Custom ${first.rank}–${last.rank}` : `Custom ${state.window[0]}–${state.window[1]}`;
    $("v2Show").value = state.windowPreset;
  }

  // ---------- week selector (JEG-1178, part of JEG-1176) ----------
  // While sources move from one week to the next, each serves its own week. The engine resolves one week view
  // (getWeekState: default = the newer week once more than half of the league's sources have it; setWeek picks).
  // No carry-forward: a source that has not published the view's week is left out and named here.
  const WEEK_MEMORY_KEY = "ddf.valuesWeek";
  const nameList = keys => keys.map(key => PLAIN_NAMES[key] || key).join(", ");
  function weekPickModel() {
    const ws = C && C.getWeekState ? C.getWeekState() : null;
    if (!ws || !Number.isInteger(ws.week) || !ws.views || !ws.views[ws.newest]) return null;
    const pd = window.TradeValueProductData;
    let fresh = null;
    try { fresh = pd && pd.getSourceFreshness ? pd.getSourceFreshness() : null; } catch (error) { fresh = null; }
    const total = ws.total;
    const countOn = week => (ws.views[week] ? ws.views[week].sources.length : 0);
    const options = ws.weeks.map(week => ({week, sources: countOn(week), total,
      label: `Week ${week} (${countOn(week)} of ${total} sources)`}));
    const newest = ws.newest;
    const calendar = fresh && Number.isInteger(fresh.current_content_week) ? fresh.current_content_week : null;
    // The week sources should be on by now. Past the newest served week, none has published it yet.
    const expected = Math.max(newest, calendar || 0);
    const onNewest = ws.views[newest];
    const lagging = expected > newest ? onNewest.sources.concat(onNewest.missing_sources).sort() : onNewest.missing_sources.slice();
    const stale = Boolean(lagging.length && pd && pd.pastThursdayNoon && pd.pastThursdayNoon(expected));
    const viewMissing = ws.views[ws.week].missing_sources;
    let text = "";
    if (expected > newest) {
      text = `Week ${expected} is not published by any of the ${total} sources yet. Showing Week ${ws.week}.`;
    } else if (ws.week === newest && viewMissing.length) {
      text = `${nameList(viewMissing)} ${stale ? `still on Week ${ws.week - 1} after Thursday 12:00 CT` : `not yet published for Week ${ws.week}`}. `
        + `Left out of these values, not carried over from Week ${ws.week - 1}.`;
    } else if (ws.week !== newest) {
      text = `Showing Week ${ws.week}. ${countOn(newest)} of ${total} sources have posted Week ${newest}; their saved Week ${ws.week} is used.`
        + (viewMissing.length ? ` ${nameList(viewMissing)} left out.` : "");
    }
    // Where the sentence above already says it (the newer week's view), the badge stands alone.
    const staleInline = stale && expected === newest && ws.week === newest && viewMissing.length > 0;
    const staleText = stale && !staleInline ? `${nameList(lagging)} still on Week ${expected - 1} after Thursday 12:00 CT.` : "";
    return {week: ws.week, newest, expected, transition: Boolean(ws.transition && ws.weeks.length > 1), selected: Boolean(ws.selected),
      default_week: ws.default_week, total, options, missing: viewMissing.slice(), lagging, stale, text, staleText,
      label: (options.find(o => o.week === ws.week) || {}).label || `Week ${ws.week}`};
  }
  function renderWeekPick() {
    const model = weekPickModel();
    const pick = $("v2WeekPick");
    const bar = $("v2WeekNoteBar");
    if (!pick || !bar) return;
    pick.hidden = !(model && model.transition);
    if (model && model.transition) {
      const select = $("v2WeekSelect");
      select.replaceChildren(...model.options.map(option => {
        const node = document.createElement("option");
        node.value = String(option.week);
        node.textContent = option.label;
        return node;
      }));
      select.value = String(model.week);
      select.title = model.selected ? "You picked this week. The default is Week " + model.default_week + "." : "";
    }
    const note = $("v2WeekNote");
    const shown = Boolean(model && (model.text || model.staleText));
    bar.hidden = !shown;
    note.replaceChildren();
    if (!shown) return;
    if (model.stale) {
      const badge = document.createElement("span");
      badge.className = "v2-weeknote-stale";
      badge.textContent = "Stale";
      note.append(badge, model.staleText ? `${model.staleText} ` : "");
    }
    note.append(model.text);
  }
  function rememberWeek() {
    try {
      const ws = C.getWeekState();
      if (ws && ws.selected) sessionStorage.setItem(WEEK_MEMORY_KEY, String(ws.week));
      else sessionStorage.removeItem(WEEK_MEMORY_KEY);
    } catch (error) { /* no session storage: the pick still holds for this page */ }
  }
  function restoreWeek() {
    try {
      const week = Number(sessionStorage.getItem(WEEK_MEMORY_KEY));
      if (Number.isInteger(week) && week > 0 && C.setWeek) C.setWeek(week, false);
    } catch (error) { /* nothing remembered */ }
  }

  // ---------- header, league, methods ----------
  // JEG-861: one "NFL Week 7 · as of Oct 22" line under every value page title, from the same data
  // the Player values line uses (the data week, never the calendar week, and the fixture's built_at).
  function pageStampText() {
    const asOf = dataAsOfLabel();
    return [view.refWeek ? `NFL Week ${view.refWeek}` : "", asOf ? `as of ${asOf}` : ""].filter(Boolean).join(" · ");
  }
  function renderPageStamps() {
    const text = pageStampText();
    document.querySelectorAll("[data-page-asof]").forEach(node => { node.textContent = text; });
  }
  function renderHeader() {
    renderPageStamps();
    renderWeekPick();
    const s = view.state;
    const scoring = {standard: "Standard", half_ppr: "Half PPR", ppr: "Full PPR"}[s.scoring] || s.scoring;
    $("v2LeagueName").textContent = `${scoring} · ${s.teams} teams`;
    const r = view.roster;
    $("v2RosterLine").textContent = `${r.QB} QB · ${r.RB} RB · ${r.WR} WR · ${r.TE} TE · ${r.FLEX} FLEX · `
      + `${r.SUPERFLEX ? `${r.SUPERFLEX} SUPERFLEX · ` : ""}`
      + `${r.K ? `${r.K} K · ` : ""}${r.DST ? `${r.DST} DEF · ` : ""}${r.BENCH} BN`;
    const older = view.active.some(key => view.infoByKey[key]?.stale);
    // JEG-463: the header chip summarizes root sources only; pipeline trouble shows as "not updating".
    const roots = rootFreshness();
    const stuck = roots.filter(r => r.status === "stuck").length;
    const behind = roots.filter(r => r.status === "prior").length;
    // Fail closed: "all sources current" only when every root source is confirmed current.
    const unknown = roots.filter(r => r.status === "unknown").length;
    // JEG-721: held sources are hidden from the chart; the header must not claim they are current.
    const held = roots.filter(r => r.status === "held").length;
    const weekText = view.refWeek ? `Week ${view.refWeek} · ` : "";
    // JEG-806: when the data week lags the calendar week, say so explicitly.
    // JEG-822: "updating" only when nothing is stuck; a stuck source gets the same week wording without it.
    const calendarNote = view.calendarWeek && view.refWeek && view.calendarWeek > view.refWeek
      ? `NFL Week ${view.calendarWeek} · data through Week ${view.refWeek}` : "";
    const updatingNote = calendarNote ? `${calendarNote}, updating` : "";
    const freshNotes = [behind ? `⚠ ${behind} source${behind === 1 ? "" : "s"} on a prior week` : "",
      held ? `${held} source${held === 1 ? "" : "s"} held` : "",
      unknown ? (pipeline ? `⚠ ${unknown} source${unknown === 1 ? "" : "s"} unconfirmed` : "checking sources…") : ""].filter(Boolean);
    $("v2FreshnessLabel").textContent = stuck
      ? `⚠ ${[calendarNote, `${stuck === roots.length && stuck > 1 ? "all " : ""}${stuck} source${stuck === 1 ? "" : "s"} not updating`].filter(Boolean).join(" · ")}`
      : updatingNote ? [updatingNote, ...freshNotes].join(" · ")
      : `${weekText}${freshNotes.join(" · ") || "all sources current"}`;
    // Phone header: a short form ("Week 7", with a warning mark when anything needs attention) shown under 420 px,
    // so the button stays beside the site name. The full text stays in the label, the aria-label and the panel.
    const flagged = stuck > 0 || behind > 0 || unknown > 0 || held > 0;
    $("v2FreshnessShort").textContent = view.refWeek ? `Week ${view.refWeek}${flagged ? " ⚠" : ""}` : $("v2FreshnessLabel").textContent;
    $("v2Freshness").classList.toggle("is-older", older || behind > 0 || unknown > 0 || held > 0);
    $("v2Freshness").classList.toggle("is-failing", stuck > 0);
    $("v2Freshness").setAttribute("aria-label", `Source freshness: ${$("v2FreshnessLabel").textContent}`);

    // JEG-474 / JEG-466: one "Showing: …" line, a compact legend (not buttons) and one Customize control.
    const page = pageOfView();
    // JEG-807: a page's list may name a held or missing series; "On this page" counts only what the page can read.
    const shownKeys = page === "values" ? view.active
      : pageKeys(page).filter(key => view.infoByKey[key] && view.infoByKey[key].available && !pageCannotUse(page, key));
    $("v2ShowingLabel").textContent = page === "values" ? "On the chart:" : "On this page:";
    const counts = SERIES_GROUPS.map(g => ({g, n: shownKeys.filter(key => seriesGroup(key) === g.id).length})).filter(c => c.n);
    // JEG-850: the line also says when the DDF blend is customized and when the chart legend has turned a line off.
    const customBlend = page === "values" && C.getBasis ? !C.getBasis().isDefault : false;
    const legendHidden = page === "values" ? shownKeys.filter(key => key !== view.rankKey && state.hiddenSeries.has(key)).length : 0;
    // JEG-863: one DDF version on its own is named ("DDF Value", "DDF Value (projections)").
    const oneDdf = shownKeys.filter(isDdfKey);
    $("v2ShowingText").textContent = `${counts.map(c => (c.g.id === "ddf" && c.n === 1 ? sourceMeta(oneDdf[0]).label : `${c.n} ${c.n === 1 ? c.g.one : c.g.many}`)
      + (c.g.id === "ddf" && customBlend ? " (your basis, not ours)" : "")).join(" + ") || "nothing selected"}`
      + (legendHidden ? ` · ${legendHidden} hidden with the chart legend` : "")
      + (view.refWeek ? ` · Week ${view.refWeek}` : "");
    // JEG-1134: the phone summary line ("Full PPR · 12 teams · 4 sources"). The count is outside sources only, so
    // DDF Value is not counted (Jeremy, 2026-10-26); with no outside source it names DDF Value instead of "0 sources".
    const outside = shownKeys.filter(key => !isDdfKey(key)).length;
    $("v2ContextSummaryText").textContent = `${scoring} · ${s.teams} teams · `
      + (outside ? `${outside} source${outside === 1 ? "" : "s"}` : oneDdf.length ? "DDF Value only" : "nothing selected");
    const legend = $("v2ShowingLegend");
    legend.replaceChildren();
    shownKeys.forEach(key => {
      const meta = sourceMeta(key);
      const item = view.infoByKey[key];
      const li = document.createElement("li");
      li.title = seriesName(key);
      describe(li, li.title);
      li.innerHTML = `<span class="v2-sym" style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span>`;
      li.append(document.createTextNode(" "), sourceLink(key, PLAIN_NAMES[meta.publisher] || meta.label));
      const badge = item?.stale ? weekBadge(key) : null;
      if (badge) li.appendChild(badge);
      // JEG-1193: on phones the one-line strip (JEG-1119) clips its legend, so a link there would be cut off and
      // untappable. The chip still shows; its link stays in Customize (and in this legend on desktop).
      appendDivergence(li, key, {noLink: PHONE_NAMES.matches});
      legend.appendChild(li);
    });

    const rankBy = $("v2RankBy");
    // The DDF Value versions lead the picker (all three, shown or not), then the other shown series.
    // JEG-477: ESPN, CBS rest of season and Razzball (DDF weighted projections) are always offered, shown or not.
    const rankKeys = DDF_PICK_KEYS.filter(key => view.infoByKey[key])
      .concat(view.plotKeys.concat(view.vorpKeys).filter(key => !isDdfKey(key)));
    ["espn", "cbsros", "razzball"].forEach(key => { if (view.infoByKey[key] && !rankKeys.includes(key)) rankKeys.push(key); });
    // The series ranked by now stays pickable even when it went unavailable, so the picker shows it.
    renderSeriesPicker(rankBy, rankKeys.map(key => ({key,
      reason: key === view.rankKey ? null : unavailableReason(view.infoByKey[key])})), view.rankKey);

    $("v2Position").value = view.state.position;
    // JEG-926: the on-graph search and position mirror the toolbar's.
    $("v2PlotPosition").value = view.state.position;
    if ($("v2PlotSearch").value !== $("v2Search").value) $("v2PlotSearch").value = $("v2Search").value;
    renderShow();
    // JEG-806: show data week and "as of <date>" so a reader knows how fresh the numbers are.
    const stamp = pageStampText();
    $("v2ValueLine").textContent = `Trade values for every player, tuned to your league${stamp ? ` · ${stamp}` : ""}`;
    $("v2DeltaBtn").textContent = `Prior week change · ${state.delta ? "On" : "Off"}`;
    $("v2DeltaBtn").setAttribute("aria-pressed", String(state.delta));
    const note = $("v2FilterNote");
    const notes = [];
    if (view.rangeOn && view.omittedMissing) {
      notes.push(`${view.omittedMissing} player${view.omittedMissing === 1 ? "" : "s"} omitted: no ${sourceMeta(view.rankKey).short} value to compare against the range.`);
    }
    if (view.hiddenZero) {
      notes.push(`${view.hiddenZero} player${view.hiddenZero === 1 ? "" : "s"} with a value of 0 on every shown series ${view.hiddenZero === 1 ? "is" : "are"} hidden. Search for a name to see ${view.hiddenZero === 1 ? "him" : "them"}.`);
    }
    if (state.delta) {
      const keys = view.plotKeys.concat(view.vorpKeys);
      const loaded = keys.filter(key => priorCache.has(key));
      const parts = loaded.map(key => {
        const prior = priorCache.get(key);
        return prior.available ? `${sourceMeta(key).short} vs Week ${prior.priorWeek}` : `${sourceMeta(key).short}: Δ —, ${prior.reason}`;
      });
      notes.push(`Change (Δ in the table) = prior-week change for the same source at your league settings; a player with no prior value shows Δ —, never zero.${parts.length ? ` ${parts.join(". ")}.` : " Recomputing last week…"}`);
    }
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
  }

  // ---------- chart ----------
  function niceScale(value) {
    if (!Number.isFinite(value) || value <= 0) return {max: 10, step: 5};
    const step = value > 60 ? 20 : value > 20 ? 10 : value > 8 ? 5 : 2;
    return {max: Math.ceil(value / step) * step, step};
  }

  function el(name, attrs, parent) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (parent) parent.appendChild(node);
    return node;
  }

  // JEG-503: a legend entry turns its line (and table column) off and on. The ranking series is the sort
  // basis, so it stays on.
  const isSeriesOn = key => key === view.rankKey || !state.hiddenSeries.has(key);
  function renderLegend() {
    const legend = $("v2Legend");
    legend.replaceChildren();
    const keys = view.plotKeys.concat(view.vorpKeys);
    keys.forEach(key => {
      const meta = sourceMeta(key);
      const span = document.createElement("button");
      span.type = "button";
      span.className = "v2-legend-item";
      span.dataset.series = key;
      const on = isSeriesOn(key);
      span.classList.toggle("is-off", !on);
      span.setAttribute("aria-pressed", String(on));
      if (key === view.rankKey) span.disabled = true;
      const mark = document.createElement("span");
      mark.className = "v2-legend-mark";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = on ? "☑" : "☐";
      span.appendChild(mark);
      const swatch = el("svg", {width: 22, height: 8, "aria-hidden": "true"});
      el("line", {x1: 0, y1: 4, x2: 22, y2: 4, stroke: meta.color, "stroke-width": meta.method === "ddf" ? 3.5 : 2,
        "stroke-dasharray": meta.method === "indexed" ? "6 4" : meta.method === "vorp" ? "1.5 4" : ""}, swatch);
      span.appendChild(swatch);
      const twice = keys.filter(k => sourceMeta(k).publisher === meta.publisher).length > 1;
      const name = meta.method === "vorp" || twice || isNarrow() ? meta.short : (PLAIN_NAMES[meta.publisher] || meta.label);
      span.append(document.createTextNode(`${meta.symbol} ${name}`));
      span.title = key === view.rankKey ? `${seriesName(key)}: the ranking series stays on` : `${seriesName(key)}: ${on ? "click to hide" : "click to show"}`;
      legend.appendChild(span);
    });
    // The line-style key is part of the legend (JEG-475): the styles on the chart, plain words at 768 px and up.
    const methods = new Set(view.plotKeys.map(k => sourceMeta(k).method));
    const words = isNarrow() ? {dda: "Solid = DDA", indexed: `Dashed = rescaled${RESCALED_TO}`} : {dda: "Solid = DDF Value", indexed: "Dashed = one chart of the Market" + (RESCALED_TO ? ` (rescaled${RESCALED_TO})` : "")};
    const key = document.createElement("span");
    key.className = "v2-legend-key";
    key.textContent = ["dda", "indexed"].filter(m => methods.has(m)).map(m => words[m]).join(" · ");
    if (key.textContent) legend.appendChild(key);
    // The expanded chart carries the same legend (clicks are handled by delegation on both).
    $("v2ExpandLegend").replaceChildren(...[...legend.childNodes].map(node => node.cloneNode(true)));
  }

  // JEG-477: the Y range of the visible window. null when no visible point is above 0.
  function fitAxis(slice, keys) {
    let lo = Infinity;
    let hi = -Infinity;
    slice.forEach(row => keys.forEach(key => {
      const v = row.values[key];
      if (Number.isFinite(v) && v > 0) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    }));
    if (!Number.isFinite(lo)) return null;
    if (hi - lo < 1) { lo = Math.max(0, lo - 0.5); hi += 0.5; }
    const pad = (hi - lo) * 0.04;
    const rough = [0.5, 1, 2, 5, 10, 20, 50].find(step => (hi - lo + 2 * pad) / step <= 6) || 50;
    const min = Math.max(0, Math.floor((lo - pad) / rough) * rough);
    const max = Math.ceil((hi + pad) / rough) * rough;
    return {min, max, step: rough};
  }

  function drawSeriesChart(container, keys, opts) {
    container.replaceChildren();
    const rect = container.getBoundingClientRect();
    const width = Math.max(280, rect.width);
    const height = Math.max(160, rect.height);
    // The rows shown: rank window ∩ value range (collect). X labels are each player's rank.
    const slice = view.visible;
    const n = slice.length;
    // Player names under the points once zoomed in far enough (Jeremy: "when you zoom in on the chart you see
    // the names"). The expanded chart staggers them on two lines, so it names players at half the spacing.
    const gap = n > 1 ? (width - 52) / (n - 1) : width;
    const names = opts.names && gap >= (opts.stagger ? 34 : 64);
    const stagger = names && opts.stagger && gap < 64;
    const pad = {l: 40, r: 12, t: 12, b: names ? (stagger ? 58 : 46) : 30};
    if (opts.plot) opts.plot.style.setProperty("--v2-plot-pad-b", `${pad.b}px`);   // the Y brush lines up with the axis
    const lo = n ? slice[0].rank : state.window[0];
    const hi = n ? slice[n - 1].rank : state.window[1];
    const svg = el("svg", {viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": `${opts.label}: ranks ${lo} to ${hi}`}, container);
    let vmax = 0;
    slice.forEach(row => keys.forEach(key => {
      const v = row.values[key];
      if (Number.isFinite(v) && v > vmax) vmax = v;
    }));
    let {max: ymax, step: ystep} = niceScale(vmax);
    let ymin = 0;
    // JEG-483 axis zoom (expanded chart only): the Y axis spans the value range; lines outside it are clipped.
    let axisZoom = Boolean(opts.axisZoom && view.rangeOn);
    if (axisZoom) {
      ymin = Math.max(0, state.range.min ?? 0);
      ymax = state.range.max ?? ymax;
      if (!(ymax > ymin)) ymax = ymin + 1;
      ystep = [0.5, 1, 2, 5, 10, 20, 50].find(step => (ymax - ymin) / step <= 6) || 50;
    } else if (opts.fit) {
      // JEG-477: the axis follows the top and bottom visible points (waiver 0s ignored), with 4% padding and
      // nice steps, so the lines show more differentiation. Lines below the axis are clipped like a zoomed axis.
      const fit = fitAxis(slice, keys);
      if (fit) { ymin = fit.min; ymax = fit.max; ystep = fit.step; axisZoom = true; }
    }
    const x = i => pad.l + (n <= 1 ? (width - pad.l - pad.r) / 2 : (i / (n - 1)) * (width - pad.l - pad.r));
    const y = axisZoom
      ? v => pad.t + (1 - (v - ymin) / (ymax - ymin)) * (height - pad.t - pad.b)
      : v => pad.t + (1 - (Math.min(ymax, Math.max(ymin, v)) - ymin) / (ymax - ymin)) * (height - pad.t - pad.b);
    const grid = el("g", {class: "grid"}, svg);
    const axis = el("g", {class: "axis"}, svg);
    const first = axisZoom ? Math.ceil(ymin / ystep - 1e-9) * ystep : ymin;
    for (let v = first; v <= ymax + 1e-9; v += ystep) {
      el("line", {x1: pad.l, x2: width - pad.r, y1: y(v), y2: y(v)}, grid);
      const label = el("text", {x: pad.l - 8, y: y(v) + 4, "text-anchor": "end"}, axis);
      label.textContent = ystep < 1 ? v.toFixed(1) : Math.round(v);
    }
    const xTicks = Math.min(5, n);
    for (let t = 0; t < xTicks; t += 1) {
      const i = xTicks === 1 ? 0 : Math.round((t / (xTicks - 1)) * (n - 1));
      const label = el("text", {x: x(i), y: height - (names ? 30 : 10), "text-anchor": "middle"}, axis);
      label.textContent = slice[i].rank;
    }
    if (names) {
      slice.forEach((row, i) => {
        const label = el("text", {x: x(i), y: height - (stagger && i % 2 ? 20 : 8), "text-anchor": "middle", class: "name-label"}, svg);
        const last = String(row.name || "").split(" ").slice(-1)[0];
        label.textContent = last.length > 11 ? `${last.slice(0, 10)}…` : last;
        label.dataset.playerKey = String(row.player_key);
      });
    }
    const zones = opts.zones ? drawZones(svg, slice, {x, pad, width, height}) : null;
    let lines = svg;
    if (axisZoom) {
      const clipId = `${container.id}Clip`;
      const clip = el("clipPath", {id: clipId}, el("defs", {}, svg));
      el("rect", {x: pad.l - 6, y: pad.t - 2, width: width - pad.l - pad.r + 12, height: height - pad.t - pad.b + 4}, clip);
      lines = el("g", {"clip-path": `url(#${clipId})`}, svg);
    }
    // The DDF Value line is drawn last so it sits on top of the others.
    keys.filter(key => !isDdfKey(key)).concat(DDF_KEYS.filter(key => keys.includes(key))).forEach(key => {
      const meta = sourceMeta(key);
      let d = "";
      let pen = false;
      slice.forEach((row, i) => {
        const v = row.values[key];
        if (Number.isFinite(v)) {
          d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(Math.max(0, v)).toFixed(1)}`;
          pen = true;
        } else {
          pen = false;
        }
      });
      if (!d) return;
      const cls = `series is-${meta.method}${view.infoByKey[key]?.stale ? " is-older" : ""}`;
      el("path", {d, class: cls, stroke: meta.color, "data-source": key}, lines);
    });
    if (opts.markers) drawSeriesMarkers(svg, keys, slice, {x, y, pad, height, axisZoom});
    const overlay = el("g", {class: "hover"}, svg);
    return {svg, overlay, x, y, slice, width, height, pad, keys, ymin, ymax, axisZoom, zones};
  }

  // JEG-926: each series' publisher symbol (the same one the legend shows) sits on the line at the left-most visible
  // player, so the legend reads straight off the left end of the chart. Where two symbols would overlap they are
  // spread vertically (a short leader joins a moved symbol to its point). A series with no value for the left-most
  // player is marked at its first valued player.
  function drawSeriesMarkers(svg, keys, slice, {x, y, pad, height, axisZoom}) {
    const gap = 14;
    const top = pad.t + 6;
    const bottom = height - pad.b - 6;
    const marks = [];
    keys.forEach(key => {
      const i = slice.findIndex(row => Number.isFinite(row.values[key]));
      if (i < 0) return;
      const py = y(Math.max(0, slice[i].values[key]));
      if (axisZoom && (py < pad.t || py > height - pad.b)) return;   // clipped off the zoomed axis: no symbol either
      marks.push({key, px: x(i), py, gy: Math.max(top, Math.min(bottom, py))});
    });
    marks.sort((a, b) => a.gy - b.gy);
    marks.forEach((m, k) => { if (k && m.gy < marks[k - 1].gy + gap) m.gy = marks[k - 1].gy + gap; });
    for (let k = marks.length - 1; k >= 0; k -= 1) {   // pushed past the bottom: pull the stack back up
      const limit = k === marks.length - 1 ? bottom : marks[k + 1].gy - gap;
      if (marks[k].gy > limit) marks[k].gy = limit;
    }
    const layer = el("g", {class: "series-marks", "aria-hidden": "true"}, svg);
    marks.forEach(m => {
      const meta = sourceMeta(m.key);
      if (Math.abs(m.gy - m.py) > 2) {
        el("line", {x1: m.px, y1: m.py, x2: m.px, y2: m.gy, class: "series-mark-leader", stroke: meta.color}, layer);
      }
      const glyph = el("text", {x: m.px, y: m.gy, class: "series-mark", fill: meta.color, "text-anchor": "middle",
        "dominant-baseline": "central", "data-source": m.key}, layer);
      glyph.textContent = meta.symbol;
    });
  }

  // JEG-503 (PV-04): Starter / Bench / Waiver. Two vertical lines at the engine's roster boundaries for the
  // ranking series (getZones(): starter_to_bench, bench_to_waiver, in the engine's rank order, which is the
  // value-based slot fill in the All view) and light grey labels centred in each section. A boundary is placed
  // between the two listed players it falls between; one outside the shown ranks is not drawn, and the
  // section labels are redrawn for what is on screen, so a zoom moves them.
  function drawZones(svg, slice, geo) {
    const zones = C.getZones ? C.getZones() : null;
    const sb = zones && zones.starter_to_bench;
    const bw = zones && zones.bench_to_waiver;
    if (!slice.length || !Number.isFinite(sb) || !Number.isFinite(bw) || C.getRankSource() !== view.rankKey) return null;
    const left = geo.pad.l;
    const right = geo.width - geo.pad.r;
    const ranks = slice.map(row => row.fullRank);
    const xAtZone = z => {
      if (z <= ranks[0]) return left;
      if (z >= ranks[ranks.length - 1]) return right;
      let i = 0;
      while (i < ranks.length - 2 && ranks[i + 1] < z) i += 1;
      const t = (z - ranks[i]) / (ranks[i + 1] - ranks[i]);
      return geo.x(i) + t * (geo.x(i + 1) - geo.x(i));
    };
    const xs = xAtZone(sb);
    const xb = xAtZone(bw);
    const group = el("g", {class: "zones"}, svg);
    // JEG-579: solid on one position ranked by DDF Value; dashed (approximate) across positions.
    const exact = C.getState().position !== "ALL" && view.rankKey === DDF_KEY;
    const top = geo.pad.t;
    const bottom = geo.height - geo.pad.b;
    const lines = [];
    [["starter_to_bench", xs], ["bench_to_waiver", xb]].forEach(([name, xv]) => {
      if (xv <= left + 0.5 || xv >= right - 0.5) return;
      el("line", {x1: xv, x2: xv, y1: top, y2: bottom, class: `zone-line${exact ? "" : " approx"}`, "data-zone": name}, group);
      lines.push({name, x: xv});
    });
    const labels = [];
    [["Starter", left, xs], ["Bench", xs, xb], ["Waiver", xb, right]].forEach(([name, a, b]) => {
      if (b - a < 46) return;
      const text = el("text", {x: (a + b) / 2, y: top + 12, class: "zone-label", "data-zone-label": name.toLowerCase(), "text-anchor": "middle"}, group);
      text.textContent = name === "Starter" ? "Starters" : name;
      labels.push({name, x: (a + b) / 2});
    });
    return {lines, labels, zones: {starter_to_bench: sb, bench_to_waiver: bw}};
  }

  let mainChart = null;
  let vorpChart = null;

  function renderCharts() {
    renderLegend();
    const big = expanded === "chart";
    mainChart = drawSeriesChart($("v2Chart"), view.plotKeys.filter(isSeriesOn), {zones: true, fit: true, markers: true, label: "Trade value by player rank", names: true, plot: $("v2Plot"),
      stagger: big, axisZoom: big && state.axisZoom});
    const vorpCard = $("v2VorpCard");
    vorpCard.hidden = !view.vorpKeys.length;
    vorpChart = view.vorpKeys.length
      ? drawSeriesChart($("v2VorpChart"), view.vorpKeys.filter(isSeriesOn), {label: "Value above waivers by player rank"})
      : null;
    const [lo, hi] = state.window;
    const n = Math.max(1, view.rows.length);
    // X rank brush: the whole list under two handles, an overview line, labels at the thumbs.
    ["v2BrushLo", "v2BrushHi"].forEach(id => { $(id).max = String(n); });
    $("v2BrushLo").value = String(lo);
    $("v2BrushHi").value = String(hi);
    const xAt = v => ((v - 1) / Math.max(1, n - 1)) * 100;
    const fill = $("v2BrushFill");
    fill.style.left = `${xAt(lo)}%`;
    fill.style.width = `${xAt(hi) - xAt(lo)}%`;
    $("v2XLoLabel").textContent = String(lo);
    $("v2XHiLabel").textContent = String(hi);
    $("v2XLoLabel").style.left = `${xAt(lo)}%`;
    $("v2XHiLabel").style.left = `${xAt(hi)}%`;
    $("v2BrushLo").setAttribute("aria-valuetext", `Rank ${lo}`);
    $("v2BrushHi").setAttribute("aria-valuetext", `Rank ${hi}`);
    drawOverview();
    renderYBrush();
    drawHover();
  }

  // JEG-472 Y value brush: the ranking series' values on a vertical track beside the plot. The
  // handles set state.range (the same filter as "Set exact values"); full extent = no filter.
  function renderYBrush() {
    const {lo: ylo, hi: yhi} = view.yScale;
    const loV = Math.max(ylo, Math.min(yhi, state.range.min ?? ylo));
    const hiV = Math.max(ylo, Math.min(yhi, state.range.max ?? yhi));
    const yAt = v => (1 - (v - ylo) / Math.max(1e-9, yhi - ylo)) * 100;
    ["v2YBrushLo", "v2YBrushHi"].forEach(id => { $(id).min = String(ylo); $(id).max = String(yhi); });
    if (document.activeElement !== $("v2YBrushLo")) $("v2YBrushLo").value = String(loV);
    if (document.activeElement !== $("v2YBrushHi")) $("v2YBrushHi").value = String(hiV);
    $("v2YBrushLo").setAttribute("aria-valuetext", `Value ${fmt(loV)}`);
    $("v2YBrushHi").setAttribute("aria-valuetext", `Value ${fmt(hiV)}`);
    const fill = $("v2YBrushFill");
    fill.style.top = `${yAt(hiV)}%`;
    fill.style.height = `${yAt(loV) - yAt(hiV)}%`;
    $("v2YHiLabel").textContent = fmt(hiV);
    $("v2YLoLabel").textContent = fmt(loV);
    $("v2YHiLabel").style.top = `${yAt(hiV)}%`;
    $("v2YLoLabel").style.top = `${yAt(loV)}%`;
    $("v2YBrush").classList.toggle("is-on", view.rangeOn);
    drawYOverview();
  }

  // Mini overview of the Y brush: how many listed players sit at each value (ranking series).
  function drawYOverview() {
    const svg = $("v2YBrushOverview");
    svg.replaceChildren();
    const {lo: ylo, hi: yhi} = view.yScale;
    const bins = 24;
    const counts = new Array(bins).fill(0);
    view.rankValues.forEach(v => {
      const b = Math.min(bins - 1, Math.max(0, Math.floor(((v - ylo) / Math.max(1e-9, yhi - ylo)) * bins)));
      counts[b] += 1;
    });
    const most = Math.max(1, ...counts);
    svg.setAttribute("viewBox", `0 0 100 ${bins}`);
    counts.forEach((count, b) => {
      if (!count) return;
      const w = Math.max(14, Math.sqrt(count / most) * 100);   // square root: the long tail near zero stays readable
      el("rect", {x: 100 - w, y: bins - b - 1 + 0.12, width: w, height: 0.76, class: "overview-bar",
        fill: sourceMeta(view.rankKey).color}, svg);
    });
  }

  function drawOverview() {
    const svg = $("v2BrushOverview");
    svg.replaceChildren();
    const rows = view.rows;
    const values = rows.map(row => row.values[view.rankKey]);
    const max = Math.max(0, ...values.filter(Number.isFinite));
    if (!rows.length || !(max > 0)) return;
    svg.setAttribute("viewBox", `0 0 ${Math.max(1, rows.length - 1)} 100`);
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (Number.isFinite(v)) { d += `${pen ? "L" : "M"}${i},${(100 - (Math.max(0, v) / max) * 90).toFixed(1)}`; pen = true; }
      else pen = false;
    });
    el("path", {d, class: "overview", stroke: sourceMeta(view.rankKey).color, "vector-effect": "non-scaling-stroke"}, svg);
  }

  let touchInspecting = false;   // JEG-954: the card on screen came from a finger, not a pointer
  function drawHover() {
    [mainChart, vorpChart].forEach(chart => {
      if (!chart) return;
      chart.overlay.replaceChildren();
      const i = state.hoverIndex;
      if (i === null || i < 0 || i >= chart.slice.length) return;
      const row = chart.slice[i];
      const cx = chart.x(i);
      el("line", {x1: cx, x2: cx, y1: chart.pad.t, y2: chart.height - chart.pad.b, class: "crosshair"}, chart.overlay);
      chart.keys.forEach(key => {
        const v = row.values[key];
        if (!Number.isFinite(v)) return;
        el("circle", {cx, cy: chart.y(Math.max(0, v)), r: key === view.rankKey ? 5 : 4,
          fill: sourceMeta(key).color, class: "hover-dot"}, chart.overlay);
      });
    });
    showTip();
  }

  function hoveredRow() {
    if (state.hoverIndex === null || !mainChart) return null;
    return mainChart.slice[state.hoverIndex] || null;
  }

  // Prior-week values come from the engine (getPriorWeek, recomputed at the
  // current setting). Cached per series; cleared whenever the engine's rows change.
  const priorCache = new Map();
  let priorStamp = 0;
  function priorsFor(keys) {
    const stamp = priorStamp;
    const todo = [...new Set(keys)].filter(key => !priorCache.has(key));
    return Promise.all(todo.map(key => Promise.resolve()
      .then(() => C.getPriorWeek(key))
      .catch(error => ({available: false, reason: `could not recompute the prior week: ${error.message}`}))
      .then(result => { if (stamp === priorStamp) priorCache.set(key, result || {available: false, reason: "no prior week"}); })));
  }
  // Δ for one cell: {text, cls, title}. "Δ —" plus a reason when there is no exact pair.
  function deltaInfo(row, key) {
    const prior = priorCache.get(key);
    if (!prior) return {text: "Δ …", cls: "", title: "Recomputing last week for your league…"};
    const d = window.TradeValueMovers.deltaFor(row.values[key], prior, String(row.player_key));
    if (d.delta === null) return {text: "Δ —", cls: "", title: d.reason};
    const text = fmtGap(d.delta);
    return {text: `Δ ${text}`, cls: text === "0.0" ? "" : d.delta > 0 ? "up" : "down", title: `vs Week ${prior.priorWeek}: ${fmt(d.before)}`};
  }
  function deltaText(row, key) {
    return deltaInfo(row, key).text;
  }

  function showTip() {
    const tip = $("v2Tip");
    const row = hoveredRow();
    if (!row || !mainChart) { tip.hidden = true; return; }
    const keys = view.plotKeys.concat(view.vorpKeys).filter(isSeriesOn);
    const weekNote = view.refWeek ? ` · Week ${view.refWeek}` : "";
    tip.innerHTML = "";
    const h = document.createElement("h3");
    h.textContent = row.name;
    appendEspnZero(h, row);
    const meta = document.createElement("span");
    meta.className = "v2-meta";
    meta.textContent = `#${row.rank} · ${row.pos} · ${row.team || "Free agent"} · ${valuesTier(row)}${weekNote}`;
    tip.append(h, meta);
    keys.forEach(key => {
      const m = sourceMeta(key);
      const line = document.createElement("div");
      line.className = `row${key === view.rankKey ? " is-rank" : ""}`;
      line.style.color = key === view.rankKey ? "" : m.color;
      const v = row.values[key];
      line.innerHTML = `<span aria-hidden="true">${m.symbol}</span>`;
      line.append(document.createTextNode(m.short));
      const val = document.createElement("span");
      val.className = "val";
      val.textContent = Number.isFinite(v) ? fmt(v) + (state.delta ? `  ${deltaText(row, key)}` : "") : "—";
      appendLowConfidence(val, row, key);
      if (estimatedReason(row, key)) {
        const why = document.createElement("span");
        why.className = "why";
        why.dataset.estimatedWhy = "";
        why.textContent = ` ${estimatedReason(row, key)}`;
        val.appendChild(why);
      }
      if (!Number.isFinite(v)) {
        val.title = missingReason(key, row);
        const why = document.createElement("span");
        why.className = "why";
        why.textContent = ` ${val.title}`;
        val.appendChild(why);
      }
      line.appendChild(val);
      tip.appendChild(line);
    });
    const hint = document.createElement("span");
    hint.className = "v2-meta";
    hint.style.marginTop = "8px";
    hint.textContent = touchInspecting ? "Tap again for player details" : "Click for player details";
    tip.appendChild(hint);
    tip.hidden = false;
    const box = $("v2Chart").getBoundingClientRect();
    const scale = box.width / mainChart.width;
    const px = box.left + mainChart.x(state.hoverIndex) * scale;
    const tipBox = tip.getBoundingClientRect();
    let left = px + 16;
    if (left + tipBox.width > window.innerWidth - 8) left = px - tipBox.width - 16;
    // A finger covers what is under it: the card takes the side of the chart away from the finger.
    if (touchInspecting) left = px < window.innerWidth / 2 ? window.innerWidth - tipBox.width - 8 : 8;
    left = Math.max(8, left);
    let top = box.top + 12;
    if (top + tipBox.height > window.innerHeight - 8) top = window.innerHeight - tipBox.height - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  }

  // JEG-897 / JEG-899: a row or card that opens the player drawer. It is focusable and opens on Enter or Space and
  // click; it announces that it opens a dialog and how (v2OpenHint). rove() then leaves one tab stop per list.
  function makeOpenable(node, open) {
    node.tabIndex = -1;
    node.setAttribute("aria-haspopup", "dialog");
    node.setAttribute("aria-describedby", "v2OpenHint");
    node.addEventListener("click", () => open());
    node.addEventListener("keydown", event => {
      if (event.target !== node) return;
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
    });
  }
  // Roving tabindex (JEG-899): the container has ONE tab stop (its last-focused item, else the first). ArrowUp/Down,
  // Home and End move between items; ArrowRight enters the item's value cells (the math tooltip cells), ArrowLeft/
  // Escape comes back. Cells stay focusable by pointer, so mouse and touch behaviour is unchanged.
  function rove(container, itemSelector) {
    const items = () => [...container.querySelectorAll(itemSelector)];
    const list = items();
    const keep = list.find(item => item.dataset.playerKey && item.dataset.playerKey === container._roveKey) || list[0];
    list.forEach(item => {
      item.tabIndex = item === keep ? 0 : -1;
      item.querySelectorAll(".has-math").forEach(cell => { cell.tabIndex = -1; });
    });
    if (container._roving) return;
    container._roving = true;
    container.addEventListener("focusin", event => {
      const all = items();
      const item = all.find(it => it.contains(event.target));
      if (!item) return;
      container._roveKey = item.dataset.playerKey;
      all.forEach(it => { it.tabIndex = it === item ? 0 : -1; });
    });
    container.addEventListener("keydown", event => {
      const all = items();
      const item = all.find(it => it.contains(event.target));
      if (!item) return;
      const move = at => { event.preventDefault(); const next = all[Math.max(0, Math.min(all.length - 1, at))]; if (next) next.focus(); };
      if (event.target === item) {
        const at = all.indexOf(item);
        if (event.key === "ArrowDown") move(at + 1);
        else if (event.key === "ArrowUp") move(at - 1);
        else if (event.key === "Home") move(0);
        else if (event.key === "End") move(all.length - 1);
        else if (event.key === "ArrowRight") {
          const first = item.querySelector(".has-math");
          if (first) { event.preventDefault(); first.focus(); }
        }
      } else if (event.target.classList && event.target.classList.contains("has-math")) {
        const cells = [...item.querySelectorAll(".has-math")];
        const at = cells.indexOf(event.target);
        if (event.key === "ArrowRight" && cells[at + 1]) { event.preventDefault(); cells[at + 1].focus(); }
        else if (event.key === "ArrowLeft") { event.preventDefault(); (cells[at - 1] || item).focus(); }
        else if (event.key === "Escape") item.focus();
      }
    });
  }

  function indexFromEvent(event, chart, container) {
    const box = container.getBoundingClientRect();
    const scale = chart.width / box.width;
    const px = (event.clientX - box.left) * scale;
    const n = chart.slice.length;
    if (n <= 1) return 0;
    const step = (chart.width - chart.pad.l - chart.pad.r) / (n - 1);
    return Math.max(0, Math.min(n - 1, Math.round((px - chart.pad.l) / step)));
  }

  // Touch-to-inspect (JEG-954): a finger on the chart shows what the pointer shows on desktop. The first tap or a
  // drag only inspects (the card sits on the side away from the finger); a second tap on the player who is still
  // shown opens the details. Lifting the finger leaves the card up for a few seconds. Page scroll stays vertical
  // (touch-action: pan-y inline, none in full screen).
  const TOUCH_HOLD_MS = 4000;
  let lastTouchAt = 0;
  let touchHold = null;
  function clearTouchInspect() {
    clearTimeout(touchHold);
    touchHold = null;
    if (!touchInspecting) return;
    touchInspecting = false;
    state.hoverIndex = null;
    drawHover();
  }
  function bindChartTouch(container, getChart) {
    let gesture = null;
    container.addEventListener("pointerdown", event => {
      if (event.pointerType === "mouse") return;
      const chart = getChart();
      if (!chart) return;
      lastTouchAt = Date.now();
      clearTimeout(touchHold);
      const index = indexFromEvent(event, chart, container);
      gesture = {startX: event.clientX, startY: event.clientY, drag: false, wasShown: touchInspecting && state.hoverIndex === index};
      // Redraw only on a change (a tap on the player already shown leaves the card and the dots alone).
      const redraw = !touchInspecting || index !== state.hoverIndex;
      touchInspecting = true;
      if (redraw) { state.hoverIndex = index; state.focusIndex = index; drawHover(); }
    });
    container.addEventListener("pointermove", event => {
      if (event.pointerType === "mouse" || !gesture) return;
      const chart = getChart();
      if (!chart) return;
      lastTouchAt = Date.now();
      if (Math.abs(event.clientX - gesture.startX) > 6 || Math.abs(event.clientY - gesture.startY) > 6) gesture.drag = true;
      const index = indexFromEvent(event, chart, container);
      if (index !== state.hoverIndex) { state.hoverIndex = index; state.focusIndex = index; drawHover(); }
    });
    const lift = () => {
      lastTouchAt = Date.now();
      clearTimeout(touchHold);
      touchHold = setTimeout(clearTouchInspect, TOUCH_HOLD_MS);
    };
    container.addEventListener("pointerup", event => { if (event.pointerType !== "mouse") lift(); });
    container.addEventListener("pointercancel", event => { if (event.pointerType !== "mouse") { gesture = null; lift(); } });
    container.addEventListener("click", event => {
      // Runs before the generic click handler below (registered first): a touch tap that only inspects stops here.
      if (!gesture) return;
      const g = gesture;
      gesture = null;
      if (g.drag || !g.wasShown) event.stopImmediatePropagation();
    });
  }

  function bindChart(containerId, getChart) {
    const container = $(containerId);
    bindChartTouch(container, getChart);
    container.addEventListener("mousemove", event => {
      const chart = getChart();
      if (!chart) return;
      if (Date.now() - lastTouchAt < 800) return;   // the mouse events a browser repeats after a touch
      touchInspecting = false;
      state.hoverIndex = indexFromEvent(event, chart, container);
      state.focusIndex = state.hoverIndex;
      drawHover();
    });
    container.addEventListener("mouseleave", () => {
      if (touchInspecting && Date.now() - lastTouchAt < 800) return;
      state.hoverIndex = null; drawHover();
    });
    container.addEventListener("click", event => {
      const chart = getChart();
      if (!chart) return;
      const row = chart.slice[indexFromEvent(event, chart, container)];
      if (row) openDrawer(row);
    });
  }

  function bindChartKeys() {
    const chartNode = $("v2Chart");
    // JEG-897: the player under the arrow keys is announced (the tooltip is visual only).
    const say = document.createElement("div");
    say.className = "v2-sr";
    say.id = "v2ChartSay";
    say.setAttribute("role", "status");
    say.setAttribute("aria-live", "polite");
    chartNode.insertAdjacentElement("afterend", say);
    chartNode.addEventListener("keydown", event => {
      if (!mainChart) return;
      const n = mainChart.slice.length;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        touchInspecting = false;
        const base = state.hoverIndex ?? state.focusIndex ?? 0;
        state.hoverIndex = Math.max(0, Math.min(n - 1, base + (event.key === "ArrowRight" ? 1 : -1)));
        state.focusIndex = state.hoverIndex;
        drawHover();
        const at = hoveredRow();
        if (at) say.textContent = `${at.name}, ${at.pos || ""} ${at.team || ""}, rank ${state.hoverIndex + 1} of ${n}. Enter for details.`.replace(/\s+,/g, ",");
      } else if (event.key === "Enter") {
        const row = hoveredRow();
        if (row) openDrawer(row);
      } else if (event.key === "Escape") {
        state.hoverIndex = null;
        drawHover();
      }
    });
    chartNode.addEventListener("blur", () => { state.hoverIndex = null; drawHover(); });
  }

  // ---------- table ----------
  // JEG-1212: group columns by input category; each column keeps its method label.
  // The Columns menu hides whole groups.
  const TABLE_GROUPS = [["ddf", "DDF Value"], ["projections", "Projections"],
    ["published", "Published charts"], ["observed", "Observed-trade estimates"],
    ["vorp", "Value above waivers"], ["spread", "Spread"]];
  function tableGroup(key) {
    if (isDdfKey(key)) return "ddf";
    const meta = sourceMeta(key);
    if (meta.method === "vorp") return "vorp";
    return window.DDFSourceViews.categoryOf(key)?.id || "projections";
  }
  const groupOrder = id => TABLE_GROUPS.findIndex(([g]) => g === id);

  function tableColumns() {
    const valueKeys = view.plotKeys.concat(view.vorpKeys)
      .filter(key => key === view.rankKey || (!state.hiddenGroups.has(tableGroup(key)) && !state.hiddenSeries.has(key)));
    const cols = [
      {id: "rank", label: "#", cls: "rank", get: row => row.rank},
      {id: "name", label: "Player", cls: "player", get: row => row.name, text: true},
      {id: "pos", label: "Pos", cls: "col-meta", get: row => row.pos, text: true},
      {id: "team", label: "Team", cls: "col-meta", get: row => row.team || "Free agent", text: true},
      {id: "tier", label: "Tier", cls: "col-meta", get: row => valuesTier(row), text: true,
        order: row => TIER_ORDER[tierFor(row, view.rankKey, view.tierScope)] ?? 3}
    ].filter(col => state.metaCols[col.id] !== false)
      .filter(col => col.cls !== "col-meta" || metaColumnsShown());
    // Ranking series first (it is the sort basis), then the groups in their fixed order.
    valueKeys.slice().sort((a, b) => (b === view.rankKey) - (a === view.rankKey) || groupOrder(tableGroup(a)) - groupOrder(tableGroup(b)))
      .forEach(key => cols.push({id: key, label: sourceLabelFor(key), source: key, cls: "num", group: tableGroup(key),
        get: row => row.values[key]}));
    const ddaKeys = view.plotKeys.filter(key => sourceMeta(key).method === "dda");
    if (ddaKeys.length >= 2 && !state.hiddenGroups.has("spread")) {
      cols.push({id: "spread", label: isNarrow() ? "DDA spread" : "Spread of our values", cls: "num", group: "spread", get: row => {
        const values = ddaKeys.map(key => row.values[key]).filter(Number.isFinite);
        return values.length >= 2 ? Math.max(...values) - Math.min(...values) : null;
      }});
    }
    return cols;
  }

  function sortedRows(cols) {
    const rows = view.visible.slice();
    if (!state.sort) return rows;
    const col = cols.find(c => c.id === state.sort.key);
    if (!col) return rows;
    const dir = state.sort.dir === "asc" ? 1 : -1;
    return rows.sort((a, b) => {
      if (col.order) return dir * (col.order(a) - col.order(b)) || a.rank - b.rank;
      const va = col.get(a);
      const vb = col.get(b);
      if (col.text) return dir * String(va).localeCompare(String(vb));
      const fa = Number.isFinite(va);
      const fb = Number.isFinite(vb);
      if (!fa && !fb) return a.rank - b.rank;
      if (!fa) return 1;   // missing values always sort last, never as zero
      if (!fb) return -1;
      return dir * (va - vb) || a.rank - b.rank;
    });
  }

  // Two-line header: publisher on line 1, method in small caps on line 2 (week only when older).
  function headerLabel(button, col) {
    const line1 = document.createElement("span");
    line1.className = "th-1";
    const line2 = document.createElement("span");
    line2.className = "th-2";
    if (col.source) {
      const meta = sourceMeta(col.source);
      const item = view.infoByKey[col.source];
      line1.innerHTML = `<span class="v2-sym" style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span> `;
      line1.append(document.createTextNode(PLAIN_NAMES[meta.publisher] || meta.label));
      line2.textContent = METHOD_LABEL[meta.method];
      // TT-06 (contract v1.2): a chart a week behind shows the shared "Wk N" badge here too.
      if (item?.stale) line2.append(document.createTextNode(" · "), weekBadge(col.source));
      appendDivergence(line2, col.source, {noLink: true});
      button.title = `${plainSeries(meta.publisher, meta.method)}${item?.week ? ` · Week ${item.week}` : ""}`;
    } else if (col.id === "spread") {
      line1.textContent = "Spread";
      line2.textContent = isNarrow() ? "DDA" : "of our values";
    } else {
      line1.textContent = col.label;
    }
    button.append(line1);
    if (line2.textContent) button.append(line2);
  }

  // Heatmap tint (presentational): a cell against the same row's ranking-series value, both shown in
  // the row. Colour only, never a number; the direction is also in the cell's title and screen-reader text.
  function heatFor(row, key) {
    if (key === view.rankKey || sourceMeta(key).method === "vorp" || sourceMeta(view.rankKey).method === "vorp") return null;
    const v = row.values[key];
    const r = row.values[view.rankKey];
    if (!Number.isFinite(v) || !Number.isFinite(r)) return null;
    const ratio = Math.abs(v - r) / Math.max(Math.abs(r), 1);
    const level = ratio >= 0.3 ? 3 : ratio >= 0.15 ? 2 : ratio >= 0.05 ? 1 : 0;
    return {dir: level === 0 ? "same" : v > r ? "above" : "below", level, rankValue: r};
  }
  const HEAT_WORDS = {above: "above", below: "below", same: "about level with"};

  // Why a value is "—", for every tab: the engine's own reason first (row.missingReasons[key], e.g.
  // "Not enough players to fit an adjustment"), then row.ddfReason for the DDF Value (JEG-479), then a
  // generic line. A finite 0 is a value ("0.0"), never missing.
  // JEG-850: when a DDF Value version has no source turned on, say that, not "No source prices this player".
  // JEG-921 / JEG-1073: DDF Value is the trade charts (JEG-804's projections-only rule was reversed); with every
  // trade chart paused it shows no value, never a projection fallback. The projections alternate says the same of
  // the projection sources.
  const ALL_PROJECTIONS_PAUSED = "All projection sources are paused this week";
  const ALL_CHARTS_PAUSED = "Every trade chart source is paused this week";
  function ddfNoInputsReason(key) {
    const info = C.getCompositeInputs ? C.getCompositeInputs(key) : null;
    if (!info || (info.series || []).length) return "";
    return (info.inputs || []).length ? (key === "ddf_value_projections" ? ALL_PROJECTIONS_PAUSED : ALL_CHARTS_PAUSED)
      : "No sources are turned on for this DDF Value (see Overrides)";
  }
  function missingReason(key, row) {
    const own = row && row.missingReasons ? row.missingReasons[key] : null;
    if (isDdfKey(key) && own === "No source prices this player" && ddfNoInputsReason(key)) return ddfNoInputsReason(key);   // JEG-850
    if (typeof own === "string" && own.trim()) return own;
    const ddfReason = isDdfKey(key) ? (key === DDF_KEY && row && row.ddfReason) || (ddfEntry(row, key) || {}).reason : null;
    if (ddfReason) return ddfReason === "No source prices this player" && ddfNoInputsReason(key) ? ddfNoInputsReason(key) : ddfReason;
    const item = view && view.infoByKey[key];
    const name = sourceMeta(key).short;
    if (item && !item.available) return `${name} is unavailable right now, so no player has a value from it`;
    return `${name} has no value for this player`;
  }

  function renderTable(retry) {
    if (!retry) metaNoRoom = false;
    const cols = tableColumns();
    const table = $("v2Table");
    table.replaceChildren();
    const thead = document.createElement("thead");
    // Grouped top row (JEG-473): one cell per run of columns in the same group.
    const gr = document.createElement("tr");
    gr.className = "v2-group-row";
    const runs = [];
    cols.forEach(col => {
      const id = col.source === view.rankKey ? "rank-series" : col.group || "";
      const last = runs[runs.length - 1];
      if (last && last.id === id) last.span += 1;
      else runs.push({id, span: 1});
    });
    runs.forEach(run => {
      const th = document.createElement("th");
      th.scope = "colgroup";
      th.colSpan = run.span;
      th.className = run.id ? `grp grp-${run.id}` : "grp";
      if (run.id) th.dataset.group = run.id;
      if (run.id === "rank-series") { th.textContent = "Ranking"; th.classList.add("is-rank"); }
      else if (run.id) th.textContent = TABLE_GROUPS.find(([g]) => g === run.id)[1];
      gr.appendChild(th);
    });
    const hr = document.createElement("tr");
    hr.className = "v2-head-row";
    cols.forEach(col => {
      const th = document.createElement("th");
      th.scope = "col";
      th.dataset.col = col.id;
      if (col.group) th.dataset.group = col.group;
      if (col.cls) th.className = col.cls;
      if (col.source === view.rankKey) th.classList.add("is-rank");
      const sortKey = state.sort ? state.sort.key : view.rankKey;
      if (sortKey === col.id) th.setAttribute("aria-sort", state.sort && state.sort.dir === "asc" ? "ascending" : "descending");
      if (col.id === "rank") { th.textContent = col.label; }
      else {
        const button = document.createElement("button");
        button.type = "button";
        headerLabel(button, col);
        button.addEventListener("click", () => {
          const current = state.sort ? state.sort.key : view.rankKey;
          const dir = current === col.id && (!state.sort || state.sort.dir === "desc") ? "asc" : "desc";
          state.sort = {key: col.id, dir: col.text && current !== col.id ? "asc" : dir};
          renderTable();
        });
        th.appendChild(button);
        if (col.source && sourceUrl(col.source)) {
          const link = sourceLink(col.source, "↗");
          link.classList.add("v2-srclink-head");
          link.setAttribute("aria-label", `${PUBLISHER_NAMES[sourceMeta(col.source).publisher] || col.label}: open the publisher's page in a new tab`);
          th.appendChild(link);
        }
      }
      hr.appendChild(th);
    });
    thead.append(gr, hr);
    const tbody = document.createElement("tbody");
    const rows = sortedRows(cols);
    const rankName = sourceMeta(view.rankKey).short;
    rows.slice(0, state.shown).forEach(row => {
      const tr = document.createElement("tr");
      tr.dataset.playerKey = String(row.player_key);
      makeOpenable(tr, () => openDrawer(row));
      cols.forEach(col => {
        const td = document.createElement("td");
        if (col.cls) td.className = col.cls;
        if (col.source === view.rankKey) td.classList.add("is-rank");
        if (col.source) td.dataset.source = col.source;
        const v = col.get(row);
        if (col.cls === "num") {
          if (Number.isFinite(v)) {
            td.textContent = fmt(v);
            appendLowConfidence(td, row, col.source);
            // JEG-1059: the badge next to the value the reader set (our DDF Value only).
            if (col.source === DDF_KEY) appendOverrideFlag(td, row);
            const sr0 = col.source ? sourceRanks(col.source).get(String(row.player_key)) : null;
            if (sr0) td.appendChild(rankSubLabel("v2-srank", `${sr0.overall} overall · ${sr0.pos}`));
            // JEG-457: a rescaled trade chart's cell shows the published number and the factor on hover, focus or tap.
            if (col.source && sourceMeta(col.source).method === "indexed" && PUBLISHER_NAMES[col.source]) {
              attachPublishedMath(td, {row, ours: null}, col.source, {value: v, gap: null, atWaiver: false});
            }
            const heat = col.source ? heatFor(row, col.source) : null;
            if (heat) {
              if (heat.level) td.classList.add(`heat-${heat.dir === "above" ? "up" : "down"}-${heat.level}`);
              td.dataset.vs = heat.dir;
              td.title = `${fmt(v)}: ${HEAT_WORDS[heat.dir]} the ranking value (${rankName} ${fmt(heat.rankValue)})`;
              const sr = document.createElement("span");
              sr.className = "v2-sr";
              sr.textContent = `, ${HEAT_WORDS[heat.dir]} the ranking value`;
              td.appendChild(sr);
            }
            if (state.delta && col.source) {
              const info = deltaInfo(row, col.source);
              const d = document.createElement("span");
              d.className = `delta ${info.cls}`;
              d.dataset.source = col.source;
              d.textContent = info.text;
              d.title = info.title;
              td.appendChild(d);
            }
          } else {
            const reason = col.source ? missingReason(col.source, row) : "Needs at least two of our values for this player";
            const dash = document.createElement("span");
            dash.className = "missing";
            dash.title = reason;
            dash.textContent = "—";
            const sr = document.createElement("span");
            sr.className = "v2-sr";
            sr.textContent = `: ${reason}`;
            dash.appendChild(sr);
            td.appendChild(dash);
          }
        } else {
          td.textContent = v;
          if (col.id === "rank") {
            const pr = sourceRanks(view.rankKey).get(String(row.player_key));
            if (pr) td.appendChild(rankSubLabel("v2-prank", pr.pos));
          }
          if (col.cls === "col-meta") td.dataset.col = col.id;
          if (col.id === "name") {
            td.textContent = "";
            td.appendChild(nameSpan(row));
            appendEspnZero(td, row);
            // Pos / Team / Tier fold into this sub-line where their columns are collapsed (below 1600 px).
            const parts = metaColumnsShown() ? [] : [state.metaCols.pos !== false && row.pos, state.metaCols.team !== false && (row.team || "Free agent"),
              state.metaCols.tier !== false && valuesTier(row)].filter(Boolean);
            if (parts.length) {
              const sub = document.createElement("span");
              sub.className = "player-sub";
              sub.textContent = parts.join(" · ");
              td.appendChild(subWithTag(sub, row));   // beside the sub-line, so a row stays as tall as before (JEG-470)
            } else appendTag(td, row);
          }
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    table.setAttribute("role", "grid");
    rove(table, ":scope > tbody > tr[data-player-key]");
    if (expanded !== "table" && metaColumnsShown() && cols.some(col => col.cls === "col-meta")) {
      const wrap = $("v2TableWrap");
      if (wrap.scrollWidth > wrap.clientWidth + 1) { metaNoRoom = true; renderTable(true); return; }
    }
    const more = $("v2ShowMore");
    more.hidden = rows.length <= state.shown;
    more.textContent = "Show more players";
    const weeks = [...new Set(cols.filter(col => col.source && !view.infoByKey[col.source]?.stale)
      .map(col => view.infoByKey[col.source]?.week).filter(Boolean))];
    const hidden = TABLE_GROUPS.filter(([g]) => state.hiddenGroups.has(g)).length;
    const [lo, hi] = state.window;
    const valueText = view.rangeOn ? ` · values ${fmt(state.range.min ?? view.yScale.lo)}–${fmt(state.range.max ?? view.yScale.hi)}` : "";
    $("v2TableMeta").textContent = `${rows.length} players · ranks ${lo}–${hi}${valueText}`
      + `${weeks.length === 1 ? ` · Week ${weeks[0]}` : ""}${hidden ? ` · ${hidden} column group${hidden === 1 ? "" : "s"} hidden` : ""}`
      + " · tint = above or below the ranking value";
    if (expanded === "table") $("v2ExpandMeta").textContent = $("v2TableMeta").textContent;
  }

  // ---------- player detail (frame 13 drawer, frame 14 full screen) ----------
  let lastFocus = null;
  let drawerRow = null;
  let drawerTierFrom = null;   // which tab's series the drawer's tier follows
  function drawerTier(row) {
    if (drawerTierFrom === "targets" && targetsView) return tierText(row, targetsView.ours, targetsView.tierScope);
    if (drawerTierFrom === "compare") return tierText(row, verdictKey(), compareTierScope());
    return valuesTier(row);
  }
  const METHOD_COLUMNS = [["dda", "DDF Value"], ["indexed", "Market"], ["vorp", "Value above waivers"]];
  const METHOD_FULL = {dda: "Our Data Driven Adjustments", indexed: "Rescaled", vorp: "Value above waivers"};

  function drawerSection(title, sub) {
    const section = document.createElement("section");
    section.className = "v2-dsection";
    const h = document.createElement("h3");
    h.textContent = title;
    section.appendChild(h);
    if (sub) {
      const p = document.createElement("p");
      p.className = "v2-meta";
      p.textContent = sub;
      section.appendChild(p);
    }
    return section;
  }

  function drawerSourceComparisons(row) {
    const sourceViews = window.DDFSourceViews;
    const section = drawerSection("Trade-value comparisons",
      "Your Rank by choice orders players. DDF Value follows your selected basis (the default uses four trade-value inputs). These two readouts are comparisons only; existing trade verdict rules are unchanged.");
    // The engine reuses these source keys for different units in its other views.
    // This readout is defined only for the Indexed values in row.values.
    if (view.state.viewMode !== "indexed") {
      const note = document.createElement("p");
      note.className = "v2-meta";
      note.textContent = "Switch to Market values to compare published charts and the observed-trade estimate on the same scale.";
      section.appendChild(note);
      return section;
    }
    const available = view.info.filter(item => item.available).map(item => item.key);
    sourceViews.VIEWS.forEach(def => {
      const result = sourceViews.read(row, def.id, available);
      const line = document.createElement("p");
      line.dataset.comparisonView = def.id;
      const label = document.createElement("strong");
      label.textContent = `${def.label}: `;
      line.append(label, document.createTextNode(result.complete ? fmt(result.value) : "Unavailable"));
      const detail = document.createElement("span");
      detail.className = "v2-meta";
      detail.textContent = ` · ${result.sourceCount}/${result.expectedSourceCount} series`
        + ` · ${result.listedCount} listed, ${result.estimatedCount} DDF estimate${result.estimatedCount === 1 ? "" : "s"}`
        + (result.unlistedZeroCount ? `, ${result.unlistedZeroCount} unlisted zero${result.unlistedZeroCount === 1 ? "" : "es"}` : "")
        + (result.zeroUnknownCount ? `, ${result.zeroUnknownCount} zero${result.zeroUnknownCount === 1 ? "" : "es"} with listing unknown` : "");
      line.appendChild(detail);
      if (result.inputs.some(input => input.estimated || input.missingReason)) {
        const ancestry = document.createElement("span");
        ancestry.className = "v2-meta";
        ancestry.textContent = ` · ${result.inputs.filter(input => input.estimated || input.missingReason)
          .map(input => `${input.key}: ${input.estimateReason || input.missingReason}`).join("; ")}`;
        line.appendChild(ancestry);
      }
      section.appendChild(line);
    });
    const caution = document.createElement("p");
    caution.className = "v2-meta";
    caution.textContent = "The published-chart average gives equal weight to USA Today, FantasyPros and CBS when all three have values. FantasyCalc is separate here, but DDF estimates can still borrow from it; the views are not independent evidence. A numeric zero is kept even when its listing status is unknown; a missing value is unavailable.";
    section.appendChild(caution);
    return section;
  }

  // Hero (frame 13): the ranking series' value, and the range across the selected
  // Data Driven Adjustments series (the same unit; frame 03: DDA only in a spread).
  function drawerHero(row) {
    const key = view.rankKey;
    const meta = sourceMeta(key);
    const item = view.infoByKey[key];
    const hero = document.createElement("div");
    hero.className = "v2-dhero";
    const main = document.createElement("div");
    const eyebrow = document.createElement("p");
    eyebrow.className = "v2-eyebrow";
    const methodName = METHOD_FULL[meta.method];
    eyebrow.textContent = `${PUBLISHER_NAMES[meta.publisher] || meta.label}${methodName ? ` · ${methodName}` : ""}${item?.week ? ` · Week ${item.week}` : ""}`;
    const big = document.createElement("p");
    big.className = "v2-dhero-value";
    big.dataset.source = key;
    const v = row.values[key];
    if (Number.isFinite(v)) {
      big.textContent = fmt(v);
      appendLowConfidence(big, row, key);
      // JEG-1059: the badge next to the value the reader set.
      if (key === DDF_KEY) appendOverrideFlag(big, row);
    }
    else big.appendChild(missingNode(missingReason(key, row), "not priced by this source"));
    const unit = document.createElement("p");
    unit.className = "v2-meta";
    unit.textContent = meta.method === "vorp" ? "Value above waivers, on this source's own scale" : "Trade-value points";
    main.append(eyebrow, big, unit);
    if (estimatedReason(row, key)) {
      const why = document.createElement("p");
      why.className = "v2-meta";
      why.dataset.estimatedWhy = "";
      why.textContent = `≈ ${estimatedReason(row, key)}`;
      main.appendChild(why);
    }
    hero.appendChild(main);
    const dda = view.active.filter(k => sourceMeta(k).method === "dda" && view.infoByKey[k]?.available)
      .map(k => row.values[k]).filter(Number.isFinite);
    if (dda.length >= 2) {
      const range = document.createElement("div");
      range.className = "v2-dhero-range";
      const label = document.createElement("p");
      label.className = "v2-eyebrow";
      label.textContent = "Range across our selected values";
      const value = document.createElement("p");
      value.dataset.range = "dda";
      value.textContent = `${fmt(Math.min(...dda))}–${fmt(Math.max(...dda))}`;
      range.append(label, value);
      hero.appendChild(range);
    }
    return hero;
  }

  // JEG-926 (Jeremy, 2026-10-23): the player page lists only the sources selected through the chart controls
  // (Customize / Show), each with its number. A source with no number for this player gets no row (never a blank
  // one); every listed row therefore has a number. "Show all sources"
  // (off by default, kept for this page load only, nothing saved) lists every source that has a number.
  let drawerAllSources = false;
  const isSelectedSource = key => view.active.includes(key) && (key === view.rankKey || !state.hiddenSeries.has(key));

  function drawerSourceRows(row, all) {
    const rows = [];
    // Our own DDF Value versions come first; they live on the engine's rows, not in its source list.
    DDF_KEYS.forEach(key => {
      const value = row.values[key];
      const selected = isSelectedSource(key);
      if ((selected || all) && Number.isFinite(value)) {
        rows.push({pub: "ddf", method: "ddf", label: "Our composite", item: view.infoByKey[key] || {key}, value, selected, ddf: true});
      }
    });
    Object.keys(PUBLISHERS).forEach(pub => {
      METHOD_COLUMNS.forEach(([method, label]) => {
        const item = view.info.find(i => sourceMeta(i.key).publisher === pub && sourceMeta(i.key).method === method);
        if (!item) return;
        const selected = isSelectedSource(item.key);
        if (!selected && !all) return;
        const has = item.available && Number.isFinite(row.values[item.key]);
        if (has) rows.push({pub, method, label, item, value: row.values[item.key], selected});
      });
    });
    return rows;
  }

  // Frame 13 "Source values": one row per listed source.
  function drawerMatrix(row) {
    const section = drawerSection("Source values", "Each source you have selected, with its number. A missing value is never shown as zero.");
    const toggle = document.createElement("label");
    toggle.className = "v2-check v2-dall";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.id = "v2DrawerAll";
    box.checked = drawerAllSources;
    box.addEventListener("change", () => {
      drawerAllSources = box.checked;
      openDrawer(drawerRow);
      const again = $("v2DrawerAll");
      if (again) again.focus();
    });
    toggle.append(box, document.createTextNode("Show all sources"));
    section.appendChild(toggle);
    // JEG-1059: the reader's own value, above the source breakdown. The source values themselves are untouched.
    if (row.valueOverride !== null && row.valueOverride !== undefined) {
      const own = document.createElement("p");
      own.className = "v2-meta v2-doverride";
      own.textContent = `Your override: ${fmt(row.valueOverride)}`;
      const unchanged = document.createElement("p");
      unchanged.className = "v2-meta";
      unchanged.textContent = "Individual source values are unchanged.";
      section.append(own, unchanged);
    }
    const listed = drawerSourceRows(row, drawerAllSources);
    if (!listed.length) {
      const none = document.createElement("p");
      none.className = "v2-meta v2-dnone";
      none.textContent = "None of the sources you selected has a number for this player. Show all sources lists every number we have.";
      section.appendChild(none);
      return section;
    }
    const wrap = document.createElement("div");
    wrap.className = "v2-dmatrix-wrap";
    const table = document.createElement("table");
    table.className = "v2-dmatrix";
    const head = document.createElement("tr");
    [["Source / week", "player"], ["Kind", "kind"], ["Value", "num"]].forEach(([text, cls]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.className = cls;
      th.textContent = text;
      head.appendChild(th);
    });
    const thead = document.createElement("thead");
    thead.appendChild(head);
    const tbody = document.createElement("tbody");
    listed.forEach(({pub, method, label, item, value, selected, ddf}) => {
      const tr = document.createElement("tr");
      tr.dataset.source = item.key;
      if (!selected) tr.className = "is-off";
      const th = document.createElement("th");
      th.scope = "row";
      th.className = `player${item.stale ? " is-older" : ""}`;
      if (ddf) {
        const meta = sourceMeta(item.key);
        th.innerHTML = `<span style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span> `;
        th.append(document.createTextNode(meta.label));
      } else {
        th.innerHTML = `<span style="color:${pubColor(pub)}" aria-hidden="true">${PUBLISHERS[pub].symbol}</span> `;
        th.append(sourceLink(pub, PUBLISHER_NAMES[pub], row.pos), document.createTextNode(item.week ? ` · Week ${item.week}` : ""));
      }
      const provText = ddf ? "" : withWaiverNote(freshnessText(item), item);
      if (provText && provText !== `Week ${item.week}`) {
        const prov = document.createElement("span");
        prov.className = "th-sub";
        prov.textContent = provText;
        th.appendChild(prov);
      }
      const kind = document.createElement("td");
      kind.className = "kind";
      kind.dataset.method = method;
      kind.textContent = label;
      const td = document.createElement("td");
      td.className = "num";
      td.dataset.source = item.key;
      td.textContent = fmt(value);
      appendLowConfidence(td, row, item.key);
      // JEG-1059: the badge on our composite, which is the value the reader set.
      if (ddf && item.key === DDF_KEY) appendOverrideFlag(td, row);
      tr.append(th, kind, td);
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    wrap.appendChild(table);
    const note = document.createElement("p");
    note.className = "v2-meta";
    note.textContent = "Adjusted and rescaled values share the trade-value point scale for your league. Value above waivers is each source's own unit and is not comparable to them. Choose sources with Customize.";
    section.append(wrap, note);
    return section;
  }

  // Frame 13: news and adjustments come from the data's own player context, read only.
  function drawerContext(row) {
    const out = [];
    const stats = drawerSection("Stats & context");
    const p = document.createElement("p");
    p.textContent = `Position: ${row.pos} · Team: ${row.team || "Free agent"} · Tier: ${drawerTier(row)}`
      + (row.rank ? ` · #${row.rank} by ${sourceMeta(view.rankKey).short}` : "");
    stats.appendChild(p);
    out.push(stats);
    let context = null;
    try { context = window.TradeValueProductData?.getPlayerContext?.(row.player_key) || null; } catch (error) { context = null; }
    const asOf = context?.as_of ? ` · as of ${String(context.as_of).slice(0, 10)}` : "";
    const news = drawerSection("Latest player news");
    const items = (context?.news || []).slice().sort((a, b) => String(b.published_at).localeCompare(String(a.published_at))).slice(0, 3);
    if (!items.length) {
      const none = document.createElement("p");
      none.className = "v2-meta";
      none.textContent = "No linked news available.";
      news.appendChild(none);
    } else {
      const ul = document.createElement("ul");
      ul.className = "v2-dnews";
      items.forEach(item => {
        const li = document.createElement("li");
        const link = document.createElement(item.url ? "a" : "span");
        if (item.url) { link.href = item.url; link.target = "_blank"; link.rel = "noopener noreferrer"; }
        link.textContent = item.title || "Untitled";
        const sub = document.createElement("span");
        sub.className = "v2-meta";
        sub.textContent = ` ${item.source || ""}${item.published_at ? ` · ${String(item.published_at).slice(0, 10)}` : ""}`;
        li.append(link, sub);
        ul.appendChild(li);
      });
      news.appendChild(ul);
    }
    out.push(news);
    const adj = drawerSection("Adjustments applied");
    const base = document.createElement("p");
    base.textContent = lineupShareText(row) || "Expected lineup share: not available for this player.";
    adj.appendChild(base);
    const notes = context?.adjustments || [];
    const line = document.createElement("p");
    line.className = "v2-meta";
    line.textContent = notes.length
      ? `News adjustment: ${notes.map(a => [a.kind, a.injury, a.date].filter(Boolean).join(", ")).join("; ")}${asOf}.`
      : `News adjustment: none for this player${asOf}.`;
    adj.appendChild(line);
    out.push(adj);
    return out;
  }

  // tierFrom: "targets" | "compare" | undefined (Player values); a re-open of the same row keeps it.
  function openDrawer(row, tierFrom) {
    if ($("v2Drawer").hidden) lastFocus = document.activeElement;
    if (tierFrom !== undefined || row !== drawerRow) drawerTierFrom = tierFrom || null;
    drawerRow = row;
    const drawer = $("v2Drawer");
    drawer.replaceChildren();
    const head = document.createElement("div");
    head.className = "v2-dhead";
    const titles = document.createElement("div");
    const title = document.createElement("h2");
    title.id = "v2DrawerTitle";
    title.textContent = row.name;
    const meta = document.createElement("p");
    meta.className = "v2-meta";
    meta.textContent = `${row.pos} · ${row.team || "Free agent"} · ${drawerTier(row)}`;
    const tagged = tagChip(row);
    if (tagged) meta.append(" ", tagged);
    titles.append(title, meta);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "v2-btn close";
    close.textContent = "✕";
    close.setAttribute("aria-label", "Close player details");
    close.addEventListener("click", closeDrawer);
    head.append(titles, close);
    drawer.appendChild(head);
    const zeroBadge = espnZeroBadge(row);
    if (zeroBadge) {
      const zeroNote = document.createElement("p");
      zeroNote.className = "v2-espn-zero-note";
      zeroNote.append(zeroBadge, document.createTextNode(` ${zeroBadge.title}`));
      zeroBadge.removeAttribute("title");
      drawer.appendChild(zeroNote);
    }
    drawer.append(drawerHero(row));
    // Risers can pass a row with one historical series over current other
    // series; do not compute a new aggregate from that mixed-week row.
    if (currentView() === "values") drawer.appendChild(drawerSourceComparisons(row));
    drawer.append(drawerMatrix(row), ...drawerContext(row), tradeActions(row));
    $("v2Scrim").hidden = false;
    drawer.hidden = false;
    close.focus();
  }
  // Player detail → trade targets or Compare a trade ("Add to trade" chooses Give or Get).
  function tradeActions(row) {
    const key = String(row.player_key);
    const on = ["give", "receive"].find(side => TR[side].some(p => p.key === key));
    const box = document.createElement("div");
    box.className = "v2-drawer-trade";
    const targets = document.createElement("button");
    targets.type = "button";
    targets.className = "v2-btn";
    targets.textContent = "See trade targets";
    targets.addEventListener("click", () => {
      T.search = row.name;
      $("v2TSearch").value = row.name;
      closeDrawer();
      location.hash = "#trade-targets";
    });
    box.appendChild(targets);
    if (on) {
      const p = document.createElement("p");
      p.className = "v2-meta";
      p.dataset.tradeOn = on;
      p.textContent = `✓ On your trade: ${SIDE_NAME[on].toLowerCase()}.`;
      const open = document.createElement("a");
      open.className = "v2-link";
      open.href = "v2/#compare-trade";
      open.textContent = "Open Compare a trade";
      open.addEventListener("click", closeDrawer);
      box.append(p, open);
      return box;
    }
    const add = document.createElement("button");
    add.type = "button";
    add.className = "v2-btn v2-btn-soft";
    add.textContent = "Add to trade";
    add.setAttribute("aria-expanded", "false");
    const menu = document.createElement("div");
    menu.className = "v2-dmenu";
    menu.hidden = true;
    [["give", "↑ You give"], ["receive", "↓ You receive"]].forEach(([side, label]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "v2-btn";
      b.dataset.tradeAdd = side;
      b.textContent = label;
      b.addEventListener("click", () => {
        TR[side] = TR[side].concat({key, name: row.name});
        closeDrawer();
        if (currentView() === "compare") renderCompare();
        else location.hash = "#compare-trade";
      });
      menu.appendChild(b);
    });
    add.addEventListener("click", () => {
      menu.hidden = !menu.hidden;
      add.setAttribute("aria-expanded", String(!menu.hidden));
      if (!menu.hidden) menu.querySelector("button").focus();
    });
    box.append(add, menu);
    return box;
  }

  function closeDrawer() {
    $("v2Drawer").hidden = true;
    $("v2Scrim").hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  // ---------- popovers (sources 09, league 12, weights 11, freshness 10, range) ----------
  let popoverAnchor = null;
  let hoverOpened = false;
  let hoverHold = null; // the hovered info button's timers, so the popover can hold or release it
  let popoverCloseHook = null;   // JEG-1020: a live panel (Your league) flushes its pending change when it closes
  function runPopoverCloseHook() { const hook = popoverCloseHook; popoverCloseHook = null; if (hook) hook(); }
  function openPopover(anchor, build) {
    const pop = $("v2Popover");
    runPopoverCloseHook();
    pop.replaceChildren();
    pop.classList.remove("v2-info-pop");
    build(pop);
    pop.hidden = false;
    popoverAnchor = anchor;
    const a = anchor.getBoundingClientRect();
    const p = pop.getBoundingClientRect();
    let left = Math.min(a.left, window.innerWidth - p.width - 16);
    let top = a.bottom + 8;
    if (top + p.height > window.innerHeight - 16) top = Math.max(16, a.top - p.height - 8);
    pop.style.left = `${Math.max(16, left)}px`;
    pop.style.top = `${top}px`;
    const first = pop.querySelector("input, select, button");
    if (first) first.focus();
  }
  function closePopover(skipFocus) {
    const pop = $("v2Popover");
    if (pop.hidden) return;
    runPopoverCloseHook();
    pop.hidden = true;
    if (panelOpen) {
      panelOpen = false;
      $("v2Scrim").hidden = $("v2Drawer").hidden;
    }
    // An anchor that announces its state (the ⓘ buttons) reads collapsed again.
    if (popoverAnchor && popoverAnchor.getAttribute("aria-expanded") === "true") popoverAnchor.setAttribute("aria-expanded", "false");
    if (skipFocus !== true && popoverAnchor && popoverAnchor.focus) popoverAnchor.focus();
    popoverAnchor = null;
    hoverOpened = false;
  }
  function toggleEngineSource(key) {
    if (isDdfKey(key)) { if (ddfShownSet.has(key)) ddfShownSet.delete(key); else ddfShownSet.add(key); return true; }
    const input = document.querySelector(`#legacyEngine #sourceToggles input[data-source="${key}"]`);
    if (!input || input.disabled) return false;
    input.click();
    return true;
  }

  // Overlay panels (frames 09–12, 20, 21): a titled panel with ✕, a draft the
  // user edits, and Cancel / Apply. Centered over a scrim on desktop, full
  // screen below 768 px (frame 17). Nothing reaches the engine until Apply.
  let panelOpen = false;
  function openPanel(anchor, title, sub, build) {
    openPopover(anchor, pop => {
      pop.classList.add("is-panel");
      const head = document.createElement("div");
      head.className = "v2-panel-head";
      const titles = document.createElement("div");
      const h = document.createElement("h2");
      h.id = "v2PanelTitle";
      h.textContent = title;
      titles.appendChild(h);
      if (sub) {
        const p = document.createElement("p");
        p.className = "v2-meta";
        p.textContent = sub;
        titles.appendChild(p);
      }
      const close = document.createElement("button");
      close.type = "button";
      close.className = "v2-btn v2-panel-close";
      close.textContent = "✕";
      close.setAttribute("aria-label", `Close ${title}`);
      close.addEventListener("click", closePopover);
      head.append(titles, close);
      pop.appendChild(head);
      pop.setAttribute("aria-labelledby", "v2PanelTitle");
      pop.setAttribute("aria-modal", "true");
      build(pop);
    });
    const pop = $("v2Popover");
    pop.style.left = "";
    pop.style.top = "";
    $("v2Scrim").hidden = false;
    panelOpen = true;
    const first = pop.querySelector(".v2-panel-body input, .v2-panel-body select, .v2-panel-body button") || pop.querySelector("button");
    if (first) first.focus();
  }
  function panelActions(pop, buttons, left) {
    const row = document.createElement("div");
    row.className = "actions v2-panel-foot";
    if (left) row.appendChild(left);
    buttons.forEach(([label, primary, fn, attrs]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `v2-btn${primary ? " v2-btn-primary" : ""}`;
      b.textContent = label;
      Object.entries(attrs || {}).forEach(([k, v]) => b.setAttribute(k, v));
      b.addEventListener("click", fn);
      row.appendChild(b);
    });
    pop.appendChild(row);
    return row;
  }
  function panelBody(pop) {
    const body = document.createElement("div");
    body.className = "v2-panel-body";
    pop.appendChild(body);
    return body;
  }
  function segmented(label, options, value, onPick) {
    const box = document.createElement("div");
    box.className = "v2-pseg";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", label);
    const buttons = options.map(([v, text]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.value = String(v);
      b.textContent = text;
      b.addEventListener("click", () => { onPick(v); sync(v); });
      box.appendChild(b);
      return b;
    });
    function sync(current) {
      buttons.forEach(b => {
        const on = b.dataset.value === String(current);
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", String(on));
      });
    }
    sync(value);
    return box;
  }
  function eyebrow(parent, text) {
    const h = document.createElement("h3");
    h.className = "v2-eyebrow";
    h.textContent = text;
    parent.appendChild(h);
    return h;
  }

  // ---------- JEG-498: Customize on every page ----------
  const PAGE_NAMES = {values: "Player values", targets: "Trade targets", risers: "Risers & fallers", compare: "Compare a trade"};
  const PAGE_SAVE_KEY = "ddf.v2.pages";
  const pageOfView = () => ({targets: "targets", risers: "risers", compare: "compare"}[currentView()] || "values");
  let pageSaved = (() => {
    try {
      const saved = JSON.parse(localStorage.getItem(PAGE_SAVE_KEY) || "null");
      return saved && saved.v === 1 && saved.pages && typeof saved.pages === "object" ? saved.pages : {};
    } catch (error) { return {}; }
  })();
  // Each page's default, chosen for its job: Trade targets compares our DDF Value with the as-published charts, Risers
  // opens on the DDF Value, Compare reads the DDF Value beside every chart. A held chart that returns is back in the
  // page without a new choice; availability is applied where the page reads the list.
  function pageDefault(page) {
    const TT = window.TradeValueTargets;
    if (page === "targets") return [DDF_KEY].concat(TT.CHART_KEYS);
    if (page === "risers") return [RISERS_DEFAULT];
    return [DDF_KEY].concat(C.getSourceInfo().filter(item => !isEngineAlias(item.key) && sourceMeta(item.key).method === "indexed").map(item => item.key));
  }
  function pageKeys(page) {
    const saved = pageSaved[page];
    // JEG-863: a saved list may name the hidden duplicate DDF id; it reads as the visible one.
    const keys = Array.isArray(saved) ? pickableSeries(saved.filter(key => typeof key === "string")) : [];
    return keys.length ? keys : pageDefault(page);
  }
  function savePageKeys(page, keys) {
    const base = pageDefault(page);
    const isDefault = keys.length === base.length && base.every(key => keys.includes(key));
    if (isDefault) delete pageSaved[page]; else pageSaved[page] = keys;
    try { localStorage.setItem(PAGE_SAVE_KEY, JSON.stringify({v: 1, pages: pageSaved})); }
    catch (error) { /* storage unavailable: the choice lasts this visit only */ }
  }
  // A series a page cannot read is listed, greyed, with the reason (Customize lists every dataset).
  function pageCannotUse(page, key) {
    const TT = window.TradeValueTargets;
    if (page === "targets" && !TT.OUR_KEYS.includes(key) && !TT.CHART_KEYS.includes(key)) return "Not compared on Trade targets";
    if (page === "risers" && !window.TradeValueMovers.SERIES.includes(key)) return "No prior-week history";
    return null;
  }
  function pageNeed(page, draft) {
    const TT = window.TradeValueTargets;
    if (page === "targets") {
      if (![...draft].some(key => TT.OUR_KEYS.includes(key))) return "Choose at least one value to compare against the charts (DDF Value or a projection).";
      if (![...draft].some(key => TT.CHART_KEYS.includes(key))) return "Choose at least one trade chart to compare.";
    }
    return null;
  }

  // ---------- 09 / 20 Customize values (JEG-466, spec JEG-474; JEG-850 two tabs) ----------
  // Two tabs: "Chart lines" (which series show on this page, a draft until Done) and "DDF blend" (which sources build
  // DDF Value, one shared choice that applies on every page; Player values only). Plain copy only: no raw ids or
  // pipeline strings. JEG-498 (contract GL-07): every page has its own Customize with its own default set, remembered
  // on this device. Player values drives the engine's shown series; the other pages keep a list of their own (pageKeys).
  const DIALOG_GROUPS = [
    {id: "ddf", title: "DDF Value", note: ""},
    {id: "pub", title: "Published charts", note: "Published trade-value opinions, rescaled to your league's scale."},
    {id: "observed", title: "Observed-trade estimates", note: "Estimates derived from completed trades."},
    {id: "proj", title: "Projection-based values", note: "Trade value derived from stat projections."},
    {id: "vorp", title: "Value above waivers (advanced)", note: "Points above the waiver line, each on its own scale. Shown in a separate panel."}];
  const DDF_ROW_TIPS = {
    ddf_value: "DDF Value: rooted in the trade charts, then adjusted for position weight and your league's rosters.",
    ddf_value_charts: "DDF Value: rooted in the trade charts, then adjusted for position weight and your league's rosters.",
    ddf_value_projections: "The alternate: the projection sources, equal weight, averaged for your league. It stays this way when you choose a different basis on Overrides."};
  // The engine's reason a source is out of the blend, in plain words (never "held: fidelity: scrape_validity").
  function plainOutReason(reason) {
    const text = String(reason || "");
    if (/divergence/i.test(text)) return "Left out this week";
    if (/not available for|missing from/i.test(text)) return "Not available for your league";
    if (/not yet published|older week|prior week/i.test(text)) return "Not published yet this week";
    return "Paused this week";
  }
  function openSources(anchor, pageArg) {
    const page = pageArg || pageOfView();
    const onValues = page === "values";
    // JEG-907: the dialog and the chart legend are one state. A line the legend turned off starts unticked here
    // (its row says why); ticking it, Select all or Reset to default turns it back on, and Done applies the draft as
    // shown, so no legend hide survives Done.
    const draft = new Set(onValues ? view.active.filter(key => key === view.rankKey || !state.hiddenSeries.has(key)) : pageKeys(page));
    // JEG-1044: the DDF blend lives on the Overrides tab now; this dialog only picks chart lines. It still asks the
    // engine whether a DDF version has anything to show (versionUsable).
    const hasBlend = onValues && typeof C.getCompositeInputs === "function";
    const legendHid = key => onValues && key !== view.rankKey && view.active.includes(key) && state.hiddenSeries.has(key);
    // JEG-930 / JEG-863: how many sources feed a DDF version this week (null: not a blend-built version).
    const versionUsable = versionKey => (versionKey === "ddf_value_projections" || DDF_VERSIONS[versionKey].blend
      ? ((C.getCompositeInputs && C.getCompositeInputs(versionKey).series) || []).length : null);
    openPanel(anchor || $("v2EditSources"), "Customize values", `Choose what appears on ${PAGE_NAMES[page]}.`, pop => {
      const body = panelBody(pop);
      const err = document.createElement("p");
      err.className = "v2-perror";
      err.setAttribute("role", "alert");
      err.hidden = true;
      err.textContent = "Choose at least one series.";
      body.appendChild(err);
      const panelFor = id => {
        const box = document.createElement("div");
        box.id = `v2CustPanel-${id}`;
        box.dataset.panel = id;
        return box;
      };
      const linesPanel = panelFor("lines");
      // Chart lines: intro, then the groups.
      const linesIntro = document.createElement("p");
      linesIntro.className = "v2-meta v2-cintro";
      linesIntro.textContent = onValues ? "Which values show on the chart and table. Other pages keep their own choice."
        : "Which values show on this page. Other pages keep their own choice.";
      const linesSummary = document.createElement("p");
      linesSummary.className = "v2-psummary";
      linesSummary.setAttribute("role", "status");
      const groupsBox = document.createElement("div");
      linesPanel.append(linesIntro, linesSummary, groupsBox);
      body.append(linesPanel);
      if (hasBlend) {
        // JEG-1044 (Jeremy, 2026-10-24): the DDF blend tab is gone; the basis picker on Overrides replaces it.
        const moved = document.createElement("p");
        moved.className = "v2-meta v2-cintro";
        moved.append("What DDF Value is built from (which sources, and their weights) is set on ");
        const link = document.createElement("a");
        link.href = "v2/#value-overrides";
        link.textContent = "Overrides";
        link.addEventListener("click", () => closePopover());
        moved.append(link, ".");
        body.append(moved);
      }

      function metaNote(label, text) {
        const why = document.createElement("span");
        why.className = "v2-meta";
        why.textContent = text;
        label.appendChild(why);
      }
      function refocus(selector) {
        const again = body.querySelector(selector);
        if (again) again.focus();
      }
      function rowFor(item) {
        const meta = sourceMeta(item.key);
        const label = document.createElement("label");
        const pageNo = onValues ? null : pageCannotUse(page, item.key);
        const usable = item.available && !pageNo;
        label.className = `v2-crow${usable ? "" : " is-disabled"}`;
        const box = document.createElement("input");
        box.type = "checkbox";
        box.dataset.series = item.key;
        box.checked = draft.has(item.key);
        box.disabled = !usable;
        box.addEventListener("change", () => {
          if (box.checked) draft.add(item.key); else draft.delete(item.key);
          err.hidden = true;
          render();
          refocus(`[data-series="${item.key}"]`);
        });
        const name = document.createElement("span");
        name.className = "v2-crow-name";
        name.innerHTML = `<span class="v2-sym" style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span> `;
        name.append(sourceLink(item.key, PLAIN_NAMES[meta.publisher] || meta.label));
        label.append(box, name);
        if (item.stale) label.appendChild(weekBadge(item.key));
        appendDivergence(label, item.key, {heldNoted: !item.available && heldReason(item)});
        if (!item.available || pageNo) {
          metaNote(label, !item.available ? (heldReason(item) ? "Paused this week"
            : item.paused ? "Waiting on fresh inputs" : "Not available for your league")
            : (page === "targets" ? `Not used on ${PAGE_NAMES[page]}` : pageNo));
        } else if (isDdfKey(item.key) && hasBlend && draft.has(item.key) && versionUsable(item.key) === 0) {
          metaNote(label, "No sources on in the DDF blend");   // JEG-850: a version with nothing to build from
        } else if (legendHid(item.key) && !draft.has(item.key)) {
          metaNote(label, "Hidden with the chart legend");
        }
        label.title = isDdfKey(item.key) ? DDF_ROW_TIPS[item.key] : (item.waiverNote && item.available ? item.waiverNote : "");
        return label;
      }
      function renderLines() {
        groupsBox.replaceChildren();
        DIALOG_GROUPS.forEach(g => {
          // JEG-863: the hidden duplicate DDF id has no row (one row per distinct series).
          const items = view.info.filter(item => seriesGroup(item.key) === g.id && ddfPickKey(item.key) === item.key);
          if (!items.length) return;
          const advanced = g.id === "vorp";
          const section = document.createElement(advanced ? "details" : "section");
          section.className = "v2-cgroup";
          section.dataset.group = g.id;
          const head = document.createElement(advanced ? "summary" : "div");
          head.className = "v2-cgroup-head";
          const title = document.createElement("h3");
          title.textContent = g.title;
          head.appendChild(title);
          if (g.id === "ddf") head.appendChild(namesInfoButton("Customize"));
          const selectable = items.filter(item => item.available && (onValues || !pageCannotUse(page, item.key)));
          const allOn = selectable.length > 0 && selectable.every(item => draft.has(item.key));
          const all = document.createElement("button");
          all.type = "button";
          all.className = "v2-link v2-call";
          all.textContent = allOn ? "Select none" : "Select all";
          all.disabled = !selectable.length;
          all.addEventListener("click", event => {
            event.preventDefault();
            selectable.forEach(item => (allOn ? draft.delete(item.key) : draft.add(item.key)));
            err.hidden = true;
            render();
          });
          head.appendChild(all);
          section.appendChild(head);
          const noteText = g.id === "ddf" ? (onValues ? "" : "The trade charts that build DDF Value are set on Player values.") : g.note;
          if (noteText) {
            const note = document.createElement("p");
            note.className = "v2-meta";
            note.textContent = noteText;
            section.appendChild(note);
          }
          items.forEach(item => section.appendChild(rowFor(item)));
          if (advanced && items.some(item => draft.has(item.key))) section.open = true;   // collapsed unless one is picked
          groupsBox.appendChild(section);
        });
        // The count says what Done will apply, and names a line the chart legend has turned off.
        const hiddenN = view.active.filter(key => legendHid(key) && !draft.has(key)).length;
        linesSummary.textContent = `${draft.size} series selected${hiddenN ? ` (${hiddenN} hidden with the chart legend)` : ""}`
          + ` · applies to ${PAGE_NAMES[page]} only`;
      }
      function render() {
        renderLines();
      }
      function fail(text) {
        err.textContent = text;
        err.hidden = false;
        render();
      }
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "v2-btn v2-preset";
      reset.textContent = "Reset to default";
      reset.addEventListener("click", () => {
        draft.clear();
        (onValues ? startActive || [] : pageDefault(page)).forEach(key => draft.add(key));
        err.hidden = true;
        render();
      });
      panelActions(pop, [["Cancel", false, closePopover], ["Done", true, () => {
        if (!onValues) {
          if (!draft.size) { fail("Choose at least one series."); return; }
          const need = pageNeed(page, draft);
          if (need) { fail(need); return; }
          savePageKeys(page, [...draft]);
          // The page follows its new set: Trade targets reads the first ticked value as ours, Risers opens on the first
          // ticked series. The on-page pickers still offer every series for a one-off look.
          if (page === "targets") {
            const TT = window.TradeValueTargets;
            const ticked = TT.OUR_KEYS.filter(key => draft.has(key));
            if (!ticked.includes(T.ours)) { T.ours = ticked[0]; saveTargetsOurs(T.ours); }
          }
          if (page === "risers") R.series = null;
          closePopover();
          refresh();
          return;
        }
        // JEG-850: the engine always keeps one source, so a draft with none cannot be applied as shown. Block it.
        if (![...draft].some(key => !isDdfKey(key) && view.infoByKey[key] && view.infoByKey[key].available)) {
          fail("Pick at least one source. DDF Value is built from sources, so it cannot be shown on its own.");
          return;
        }
        const adds = [...draft].filter(key => !view.active.includes(key));
        const drops = view.active.filter(key => !draft.has(key));
        adds.forEach(toggleEngineSource);
        drops.forEach(toggleEngineSource);
        state.hiddenSeries.clear();   // JEG-907: the draft is the whole state; a legend hide never survives Done
        saveSelection();
        closePopover();
        refresh();
        announceLeagueChange("sources");   // JEG-1020: Find a trade re-runs on a source change like on a league change
        announceLive("Results updated for the new source selection.");
      }, {"data-apply": "sources"}]], reset).classList.add("v2-cust-foot");
      body.classList.add("v2-cust-body");
      render();
    });
  }
  let startActive = null;   // the default selection: what "Reset to default" returns to
  // Which DDF Value versions are shown (they have no engine toggle). Blended on, the other two off (GL-09).
  const ddfShownSet = new Set([DDF_KEY]);
  const ddfShownList = () => DDF_KEYS.filter(key => ddfShownSet.has(key));
  const SAVE_KEY = "ddf.v2.selection";
  function defaultShown() {
    const info = C.getSourceInfo();
    return [DDF_KEY].concat(info.filter(item => item.available && !isEngineAlias(item.key) && sourceMeta(item.key).method === "indexed").map(item => item.key));
  }
  // Make the shown series equal `keys` (adds before drops, so the engine never has none).
  function applyShown(keys) {
    const want = new Set(pickableSeries(keys));   // JEG-863: a saved hidden duplicate id shows as the visible one
    const engineNow = C.getActiveSources();
    const available = new Set(C.getSourceInfo().filter(item => item.available && !isEngineAlias(item.key)).map(item => item.key));
    const adds = [...want].filter(key => !isDdfKey(key) && available.has(key) && !engineNow.includes(key));
    const drops = engineNow.filter(key => !want.has(key));
    adds.forEach(toggleEngineSource);
    if (C.getActiveSources().length > drops.length) drops.forEach(toggleEngineSource);
    ddfShownSet.clear();
    DDF_KEYS.filter(key => want.has(key)).forEach(key => ddfShownSet.add(key));
  }
  function saveSelection() {
    try {
      // JEG-1044: the DDF blend choice is the basis now (Overrides tab, its own saved record); `inputs` stays null.
      localStorage.setItem(SAVE_KEY, JSON.stringify({v: 1, shown: ddfShownList().concat(C.getActiveSources()),
        inputs: null, rank: C.getRankSource()}));
    } catch (error) { /* storage unavailable: the choice lasts this visit only */ }
  }
  function loadSelection() {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "null");
      // JEG-843: a saved selection may hold the retired *_adjusted aliases; applyShown drops them.
      return saved && saved.v === 1 && Array.isArray(saved.shown) ? saved : null;
    } catch (error) { return null; }
  }
  function applyStartSelection() {
    const hasDdf = typeof C.getCompositeInputs === "function";
    const saved = loadSelection();
    const shown = saved && saved.shown.length ? saved.shown : (hasDdf ? defaultShown() : C.getActiveSources());
    applyShown(shown.filter(key => hasDdf || !isDdfKey(key)));
    const rank = saved && saved.rank ? ddfPickKey(saved.rank) : (hasDdf ? DDF_KEY : null);
    if (rank && rank !== C.getRankSource() && (isDdfKey(rank) || C.getActiveSources().includes(rank))) C.setLockOrder(rank);
    startActive = hasDdf ? defaultShown() : C.getActiveSources().slice();
  }

  // Frame 18: when a league change makes a selected series unavailable, say which one was dropped.
  let statusTimer = null;
  // JEG-444: when the new league's feasible bench range moves the bench share, say so too.
  // JEG-1020: every consumer of the league settings outside v2.js (Find a trade) listens for this event; a handler
  // pushes a short sentence on detail.notes when it changed something the reader should hear about.
  const LEAGUE_EVENT = "ddf:league-settings-changed";
  function announceLeagueChange(reason) {
    const detail = {reason, notes: []};
    try { document.dispatchEvent(new CustomEvent(LEAGUE_EVENT, {detail})); } catch (error) { console.warn("League change listener failed:", error); }
    return detail.notes;
  }
  function leagueChange(apply) {
    const before = C.getActiveSources();
    try { apply(); } finally {
      try { refresh(); } catch (error) { console.warn("Refresh after a league change failed:", error); }
    }
    const after = new Set(C.getActiveSources());
    const dropped = before.filter(key => !after.has(key));
    const notes = [];
    if (dropped.length) notes.push(`Removed ${dropped.map(key => sourceMeta(key).short).join(", ")}: not available for this league.`);
    const others = announceLeagueChange("league");
    if (notes.length) {
      setStatus(notes.join(" "));
      clearTimeout(statusTimer);
      statusTimer = setTimeout(() => setStatus(""), 6000);
    }
    return notes.concat(others);   // the live region reads these after "Results updated for the new league settings"
  }

  // ---------- 12 Your league ----------
  let leagueDefaults = null;   // the engine's state at first load: what "Reset defaults" returns to
  const ROSTER_SLOTS = [["QB", "QB", 1, 5], ["RB", "RB", 1, 5], ["WR", "WR", 1, 5], ["TE", "TE", 1, 5], ["FLEX", "FLEX", 1, 5],
    ["SUPERFLEX", "SUPERFLEX", 0, 1], ["K", "K", 0, 3], ["DST", "DEF", 0, 3], ["BENCH", "Bench slots", 0, 14]];
  // JEG-527: the reader's season weeks as a draft (null when the engine has no lineup parameters).
  function seasonWeeksState(defaults) {
    if (!C.getLeagueWeeks || !C.getContentWeek || !C.setLeagueWeeks || !C.setOptimizeFor || !C.setContentWeek) return null;
    const build = C.getBuildContentWeek ? C.getBuildContentWeek() : null;
    if (!Number.isInteger(build)) return null;
    const weeks = defaults ? C.getLineupSettingsDefaults() : null;
    const cur = C.getLeagueWeeks();
    const src = weeks ? {regularSeasonEnd: weeks.regularSeasonEnd, playoffWeeks: weeks.playoffWeeks, optimizeFor: weeks.optimizeFor}
      : {regularSeasonEnd: cur.regularSeasonEnd, playoffWeeks: cur.playoffWeeks, optimizeFor: C.getOptimizeFor()};
    return {build, content: weeks ? build : C.getContentWeek(), regularEnd: src.regularSeasonEnd,
      playoffLo: src.playoffWeeks[0], playoffHi: src.playoffWeeks[1], optimize: src.optimizeFor};
  }
  // Returns "" or the reason the engine refused the weeks (the panel then stays open).
  function applySeasonWeeks(w) {
    const cur = C.getLeagueWeeks();
    try {
      if (w.regularEnd !== cur.regularSeasonEnd || w.playoffLo !== cur.playoffWeeks[0] || w.playoffHi !== cur.playoffWeeks[1]) {
        C.setLeagueWeeks({regularSeasonEnd: w.regularEnd, playoffWeeks: [w.playoffLo, w.playoffHi]});
      }
      if (w.optimize !== C.getOptimizeFor()) C.setOptimizeFor(w.optimize);
      if (w.content !== C.getContentWeek()) C.setContentWeek(w.content === w.build ? null : w.content);
    } catch (error) {
      return error.message || "Those season weeks are not valid.";
    }
    return "";
  }
  // JEG-537 (GL-24): Advanced, collapsed at the bottom of Your league. The engine does the math
  // (getLineupSettings / setLineupSettings); v2 only collects the three inputs.
  const hasAdvanced = () => typeof C.getLineupSettings === "function" && typeof C.setLineupSettings === "function";
  function advancedState(defaults) {
    if (!hasAdvanced()) return null;
    const src = defaults ? C.getLineupSettingsDefaults() : C.getLineupSettings();
    return {injuryHistory: src.injuryHistory, projectionConfidence: src.projectionConfidence, benchShareOverride: src.benchShareOverride};
  }
  function applyAdvanced(adv) {
    if (!adv) return "";
    const cur = advancedState(false);
    const changed = {};
    ["injuryHistory", "projectionConfidence", "benchShareOverride"].forEach(key => { if (adv[key] !== cur[key]) changed[key] = adv[key]; });
    if (!Object.keys(changed).length) return "";
    try { C.setLineupSettings(changed); } catch (error) { return error.message || "Those advanced settings are not valid."; }
    return "";
  }
  // The reader's league settings are kept in this browser, like their rosters (ddf.v2.workspaces). One record holds what
  // the engine has: scoring, teams, roster slots, season weeks, advanced, position shares. A record equal to the site
  // defaults is not kept, so a reader who never changed anything keeps getting the current defaults. A shared link's
  // settings apply for the visit and are not saved until the reader changes something themselves.
  const LEAGUE_SAVE_KEY = "ddf.v2.league-settings";
  const SHARE_POSITIONS = ["QB", "RB", "WR", "TE"];
  // source: "default" | "saved" | "link"; notes: what a saved record could not carry over; storage: "ok" | "unavailable" | "full".
  const leagueInputs = {source: "default", savedAt: null, notes: [], storage: "ok"};
  let leagueDefaultSnapshot = "";
  function leagueSnapshot() {
    const st = C.getState();
    const snap = {v: 1, scoring: st.scoring, teams: st.teams, roster: {...C.getRosterShape()}};
    const w = seasonWeeksState(false);
    if (w) snap.weeks = {build: w.build, content: w.content, regularEnd: w.regularEnd, playoffLo: w.playoffLo, playoffHi: w.playoffHi, optimize: w.optimize};
    const adv = advancedState(false);
    if (adv) snap.adv = adv;
    // Shares only when the reader changed them (the same rule as a shared link): the engine's defaults move with the league.
    const shares = C.getPositionWeights ? C.getPositionWeights() : null;
    const defaults = C.getDefaultPositionWeights ? C.getDefaultPositionWeights() : null;
    if (shares && defaults && SHARE_POSITIONS.some(pos => Math.abs(Number(shares[pos]) - Number(defaults[pos])) > 5e-4)) {
      snap.shares = Object.fromEntries(SHARE_POSITIONS.map(pos => [pos, Number(Number(shares[pos]).toFixed(4))]));
    }
    return snap;
  }
  function announceInputs() {
    try { document.dispatchEvent(new CustomEvent("ddf:inputs-changed")); } catch (error) { /* a listener must not stop the page */ }
  }
  function saveLeagueSettings() {
    let text = "";
    try { text = JSON.stringify(leagueSnapshot()); } catch (error) { return; }
    const isDefault = text === leagueDefaultSnapshot;
    leagueInputs.notes = [];
    try {
      if (isDefault) localStorage.removeItem(LEAGUE_SAVE_KEY);
      else localStorage.setItem(LEAGUE_SAVE_KEY, JSON.stringify({...JSON.parse(text), savedAt: Date.now()}));
      leagueInputs.storage = "ok";
    } catch (error) {
      leagueInputs.storage = error && (error.name === "QuotaExceededError" || error.code === 22 || error.code === 1014) ? "full" : "unavailable";
    }
    leagueInputs.source = isDefault ? "default" : "saved";
    leagueInputs.savedAt = isDefault ? null : Date.now();
    announceInputs();
  }
  // Called once, before the first view renders and after the defaults were read. Each part is applied on its own, so one
  // setting the engine no longer accepts (a source or league shape that changed) does not lose the others.
  function restoreLeagueSettings() {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(LEAGUE_SAVE_KEY) || "null"); }
    catch (error) { leagueInputs.storage = "unavailable"; return; }
    if (!saved || saved.v !== 1) return;
    const notes = [];
    const attempt = (label, fn) => { try { fn(); } catch (error) { notes.push(`${label} could not be restored (${(error && error.message) || "not accepted"}).`); } };
    attempt("Scoring", () => { if (saved.scoring && saved.scoring !== C.getState().scoring) C.setScoring(saved.scoring); });
    attempt("Team count", () => { if (Number.isInteger(saved.teams) && saved.teams !== C.getState().teams) C.setTeams(saved.teams); });
    attempt("Roster slots", () => {
      const shape = C.getRosterShape();
      ROSTER_SLOTS.forEach(([key]) => {
        const want = saved.roster && saved.roster[key];
        if (Number.isInteger(want) && key in shape && want !== C.getRosterShape()[key]) C.setRosterSpot(key, want);
      });
    });
    attempt("Season weeks", () => {
      const now = seasonWeeksState(false);
      if (!now || !saved.weeks) return;
      // A saved "count from week N" belongs to the build it was made on; on a newer build the current week is used.
      const sameBuild = saved.weeks.build === now.build;
      if (!sameBuild && saved.weeks.content !== saved.weeks.build) notes.push("Your saved season week was reset: the projections moved to a newer week.");
      const error = applySeasonWeeks({build: now.build, content: sameBuild ? saved.weeks.content : now.build, regularEnd: saved.weeks.regularEnd,
        playoffLo: saved.weeks.playoffLo, playoffHi: saved.weeks.playoffHi, optimize: saved.weeks.optimize});
      if (error) throw new Error(error);
    });
    attempt("Advanced settings", () => {
      if (!saved.adv || !hasAdvanced()) return;
      const error = applyAdvanced(saved.adv);
      if (error) throw new Error(error);
    });
    // Shares last: a league change resets them to that league's defaults.
    attempt("Position shares", () => {
      const s = saved.shares;
      if (!s || !C.setPositionWeights || !SHARE_POSITIONS.every(pos => Number.isFinite(s[pos]))) return;
      const result = C.setPositionWeights(s);
      if (result && !result.ok) throw new Error("outside the allowed range");
    });
    leagueInputs.source = "saved";
    leagueInputs.savedAt = Number(saved.savedAt) || null;
    leagueInputs.notes = notes;
  }

  // JEG-1020 (Jeremy, 2026-10-24: "Don't require hitting accept or save when league settings are changed"): every control
  // here applies as it changes. Rapid taps coalesce into one recompute (LEAGUE_DEBOUNCE_MS); the recompute runs off the
  // input handler; an invalid intermediate state is refused by the engine, the last valid result stays and one inline line
  // says why. Done only closes the panel. Undo changes returns to the settings the panel opened with.
  const LEAGUE_DEBOUNCE_MS = 150;
  const LEAGUE_SLOW_MS = 250;     // a recompute this slow shows "Updating" before it starts (the previous one predicts it)
  function announceLive(text) {
    const node = $("v2LeagueLive");
    if (!node) return;
    node.textContent = "";
    setTimeout(() => { node.textContent = text; }, 50);
  }
  function openLeague() {
    const s = C.getState();
    const draft = {scoring: s.scoring, teams: s.teams, roster: {...C.getRosterShape()}, weeks: seasonWeeksState(false),
      adv: advancedState(false), advOpen: false};
    const opened = JSON.parse(JSON.stringify(draft));
    let timer = 0;
    let lastMs = 0;
    let queue = () => {};
    openPanel($("v2EditLeague"), "Your league", "One league setup for charts, tables and trades.", pop => {
      const body = panelBody(pop);
      const content = document.createElement("div");
      body.appendChild(content);
      function render() {
        content.replaceChildren();
        eyebrow(content, "Scoring");
        content.appendChild(segmented("Scoring", [["standard", "Standard"], ["half_ppr", "Half PPR"], ["ppr", "Full PPR"]],
          draft.scoring, v => { draft.scoring = v; queue(); }));
        eyebrow(content, "Teams");
        content.appendChild(segmented("Teams", [8, 10, 12, 14].map(v => [v, String(v)]), draft.teams, v => { draft.teams = v; queue(); }));
        eyebrow(content, "Starting roster");
        ROSTER_SLOTS.forEach(([key, label, min, max]) => {
          const line = document.createElement("div");
          line.className = "v2-pstep";
          const name = document.createElement("span");
          name.id = `v2Step${key}`;
          name.textContent = label;
          const stepper = document.createElement("div");
          stepper.className = "v2-stepper";
          const value = document.createElement("output");
          value.setAttribute("aria-labelledby", name.id);
          value.textContent = String(draft.roster[key]);
          const mk = (text, delta, aria) => {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = text;
            b.setAttribute("aria-label", `${aria} ${label}`);
            b.disabled = delta < 0 ? draft.roster[key] <= min : draft.roster[key] >= max;
            b.addEventListener("click", () => {
              draft.roster[key] = Math.max(min, Math.min(max, draft.roster[key] + delta));
              render();
              queue();
              const again = content.querySelector(`[aria-label="${aria} ${label}"]`);
              const other = content.querySelector(`[aria-label="${aria === "Fewer" ? "More" : "Fewer"} ${label}"]`);
              if (again && !again.disabled) again.focus(); else if (other && !other.disabled) other.focus();   // at a limit, focus stays on the stepper
            });
            return b;
          };
          stepper.append(mk("−", -1, "Fewer"), value, mk("+", 1, "More"));
          line.append(name, stepper);
          content.appendChild(line);
        });
        const note = document.createElement("p");
        note.className = "v2-meta";
        note.textContent = "SUPERFLEX is a QB-eligible slot filled after the dedicated slots. K and DEF are roster slots only (set them to 0 if your league has none); they have no values here. Bench slots: real leagues roster about this many players, and the value of bench players at each position follows how many players real leagues roster there. Position weights and the bench-share readout live in Position weights.";
        content.appendChild(note);
        if (draft.weeks) renderSeasonWeeks();
        if (draft.adv) renderAdvanced();
      }
      // JEG-537: injury history, projection confidence and the bench-share override. All off the defaults only
      // when the reader changes them; the override is off by default and shows the old 1-30% slider when on.
      function renderAdvanced() {
        const adv = draft.adv;
        const details = document.createElement("details");
        details.className = "v2-padv";
        details.open = draft.advOpen;
        details.addEventListener("toggle", () => { draft.advOpen = details.open; });
        const summary = document.createElement("summary");
        summary.textContent = "Advanced";
        details.appendChild(summary);
        eyebrow(details, "Injury history");
        details.appendChild(segmented("Injury history", [["recent", "Recent seasons"], ["all", "All seasons equally"]],
          adv.injuryHistory, v => { adv.injuryHistory = v; queue(); }));
        eyebrow(details, "Projection confidence");
        details.appendChild(segmented("Projection confidence", [[1.5, "Less"], [1, "As measured"], [0.5, "More"]],
          adv.projectionConfidence, v => { adv.projectionConfidence = v; queue(); }));
        const confNote = document.createElement("p");
        confNote.className = "v2-meta";
        confNote.textContent = "How much to trust the projections: Less widens the range of outcomes, More narrows it.";
        details.appendChild(confNote);
        eyebrow(details, "Bench-share override");
        const toggle = document.createElement("label");
        toggle.className = "v2-check";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.id = "v2BenchOverride";
        box.checked = adv.benchShareOverride !== null;
        const text = document.createElement("span");
        text.textContent = "Set the bench share myself";
        toggle.append(box, text);
        details.appendChild(toggle);
        const detail = document.createElement("p");
        detail.className = "v2-meta";
        detail.textContent = "Off by default: the bench share is worked out from your league settings.";
        details.appendChild(detail);
        if (adv.benchShareOverride !== null) {
          const line = document.createElement("div");
          line.className = "v2-pbench";
          const out = document.createElement("output");
          out.className = "v2-pbig";
          out.htmlFor = "v2BenchSlider";
          out.textContent = `${(adv.benchShareOverride * 100).toFixed(1)}%`;
          const slider = document.createElement("input");
          slider.type = "range";
          slider.id = "v2BenchSlider";
          slider.setAttribute("aria-label", "Bench share override");
          slider.min = "0.01"; slider.max = "0.30"; slider.step = "0.005";
          slider.value = String(adv.benchShareOverride);
          slider.addEventListener("input", () => { adv.benchShareOverride = Number(slider.value); out.textContent = `${(adv.benchShareOverride * 100).toFixed(1)}%`; queue(); });
          line.append(slider, out);
          details.appendChild(line);
        }
        box.addEventListener("change", () => {
          if (box.checked) {
            const readout = C.getBenchShareReadout ? C.getBenchShareReadout() : null;
            const start = readout && Number.isFinite(readout.overall) ? readout.overall : 0.1;
            adv.benchShareOverride = Math.min(0.30, Math.max(0.01, Math.round(start * 200) / 200));
          } else {
            adv.benchShareOverride = null;
          }
          draft.advOpen = true;
          render();
          const again = content.querySelector("#v2BenchOverride");
          if (again) again.focus();
          queue();
        });
        content.appendChild(details);
      }
      // JEG-527 / GL-24: the season weeks the value counts and what to optimize for. The engine
      // does the math (window, byes, drift, playoff-week injury rate); v2 only collects the inputs.
      function renderSeasonWeeks() {
        const w = draft.weeks;
        eyebrow(content, "Season weeks");
        const stepLine = (id, label, key, min, max, after) => {
          const line = document.createElement("div");
          line.className = "v2-pstep";
          const name = document.createElement("span");
          name.id = id;
          name.textContent = label;
          const stepper = document.createElement("div");
          stepper.className = "v2-stepper";
          const value = document.createElement("output");
          value.setAttribute("aria-labelledby", name.id);
          value.textContent = String(w[key]);
          const mk = (text, delta, aria) => {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = text;
            b.setAttribute("aria-label", `${aria} ${label}`);
            b.disabled = delta < 0 ? w[key] <= min : w[key] >= max;
            b.addEventListener("click", () => {
              w[key] = Math.max(min, Math.min(max, w[key] + delta));
              if (after) after();
              render();
              const again = content.querySelector(`[aria-label="${aria} ${label}"]`);
              const other = content.querySelector(`[aria-label="${aria === "Fewer" ? "More" : "Fewer"} ${label}"]`);
              if (again && !again.disabled) again.focus(); else if (other && !other.disabled) other.focus();   // at a limit, focus stays on the stepper
              queue();
            });
            return b;
          };
          stepper.append(mk("−", -1, "Earlier"), value, mk("+", 1, "Later"));
          line.append(name, stepper);
          content.appendChild(line);
        };
        stepLine("v2StepContentWeek", "Data through week", "content", 1, 17);
        stepLine("v2StepRegularEnd", "Last regular-season week", "regularEnd", 1, 17, () => {
          if (w.playoffLo <= w.regularEnd) w.playoffLo = w.regularEnd + 1;
          if (w.playoffHi < w.playoffLo) w.playoffHi = w.playoffLo;
        });
        stepLine("v2StepPlayoffLo", "First playoff week", "playoffLo", w.regularEnd + 1, 18, () => {
          if (w.playoffHi < w.playoffLo) w.playoffHi = w.playoffLo;
        });
        stepLine("v2StepPlayoffHi", "Last playoff week", "playoffHi", w.playoffLo, 18);
        eyebrow(content, "Optimize for");
        // JEG-1119: the Playoffs option is hidden (not reviewed, likely not working). A league already saved on it
        // still shows it, so that reader can see the setting and switch away.
        const optimizeOptions = [["season", "Whole season"], ["regular", "Regular season"]];
        if (w.optimize === "playoffs") optimizeOptions.push(["playoffs", "Playoffs"]);
        content.appendChild(segmented("Optimize for", optimizeOptions, w.optimize, v => { w.optimize = v; queue(); }));
        const lo =w.optimize === "playoffs" ? Math.max(w.playoffLo, w.content + 1) : w.content + 1;
        const hi = w.optimize === "regular" ? w.regularEnd : w.playoffHi;
        const weeksNote = document.createElement("p");
        weeksNote.className = "v2-meta";
        weeksNote.dataset.seasonWeeksNote = "";
        weeksNote.textContent = hi >= lo
          ? `Counts weeks ${lo} to ${hi}. ${w.content === w.build ? "" : `The projections are still the build's (week ${w.build}); only the weeks counted move. `}Week 18 is never counted.`
          : "No weeks are left in this window, so there is nothing to count for bench players.";
        content.appendChild(weeksNote);
      }
      render();
      const msg = document.createElement("p");
      msg.className = "v2-meta v2-league-msg";
      msg.dataset.leagueMsg = "";
      const issue = document.createElement("p");
      issue.className = "v2-league-issue";
      issue.dataset.leagueIssue = "";
      issue.setAttribute("role", "alert");
      issue.hidden = true;
      const showMsg = text => { msg.textContent = text; };
      const showIssue = text => { issue.textContent = text; issue.hidden = !text; };
      const undo = document.createElement("button");
      undo.type = "button";
      undo.className = "v2-btn v2-preset";
      undo.textContent = "Undo changes";
      undo.dataset.leagueUndo = "";
      undo.disabled = true;
      const sameAsOpened = () => JSON.stringify([draft.scoring, draft.teams, draft.roster, draft.weeks, draft.adv])
        === JSON.stringify([opened.scoring, opened.teams, opened.roster, opened.weeks, opened.adv]);
      // The engine holds some values to a range (a roster slot to its stepper bounds, the bench-share override to the
      // league's feasible range): the panel shows what is in force, and says so when it moved a value.
      function syncDraftFromEngine(notes) {
        const shape = C.getRosterShape();
        const was = JSON.stringify([draft.roster, draft.adv]);
        ROSTER_SLOTS.forEach(([key]) => { draft.roster[key] = shape[key]; });
        if (draft.adv) {
          const now = advancedState(false);
          if (now.benchShareOverride !== draft.adv.benchShareOverride && draft.adv.benchShareOverride !== null) {
            notes.push(now.benchShareOverride === null ? "The bench-share override was cleared for this league."
              : `The bench-share override was held to ${(now.benchShareOverride * 100).toFixed(1)}% for this league.`);
          }
          draft.adv = now;
        }
        if (JSON.stringify([draft.roster, draft.adv]) === was) return;   // nothing moved: leave the controls (and focus) alone
        const held = document.activeElement;
        const label = held && held.getAttribute ? held.getAttribute("aria-label") || held.id : "";
        render();
        const again = label && [...content.querySelectorAll("button, input")].find(n => (n.getAttribute("aria-label") || n.id) === label);
        if (again) again.focus();
      }
      function commit() {
        clearTimeout(timer);
        timer = 0;
        const t0 = performance.now();
        const cur = C.getState();   // the engine's own state: view.state is stale on tabs that do not collect()
        const shape = C.getRosterShape();
        let error = "";
        let notes = [];
        try {
          notes = leagueChange(() => {
            if (draft.scoring !== cur.scoring) C.setScoring(draft.scoring);
            if (draft.teams !== cur.teams) C.setTeams(draft.teams);
            ROSTER_SLOTS.forEach(([key]) => { if (draft.roster[key] !== shape[key]) C.setRosterSpot(key, draft.roster[key]); });
            if (draft.weeks) error = applySeasonWeeks(draft.weeks);
            if (!error && draft.adv) error = applyAdvanced(draft.adv);
          }) || [];
        } catch (caught) {
          error = (caught && caught.message) || "Those settings could not be applied.";
        }
        lastMs = performance.now() - t0;
        (window.__leagueApplyLog = window.__leagueApplyLog || []).push(Math.round(lastMs));
        saveLeagueSettings();
        showMsg("");
        if (error) {
          showIssue(`Not applied: ${error} The results still show the last valid settings.`);
        } else {
          showIssue("");
          const held = [];
          syncDraftFromEngine(held);
          notes = notes.concat(held);
          if (held.length) { showMsg(held.join(" ")); }
          announceLive(["Results updated for the new league settings.", ...notes].join(" "));
        }
        undo.disabled = sameAsOpened();
      }
      // The input handler only records the draft and starts the timer; the recompute runs from the timer.
      queue = () => {
        undo.disabled = false;
        clearTimeout(timer);
        if (lastMs >= LEAGUE_SLOW_MS * 0.8) showMsg("Updating…");
        timer = setTimeout(() => setTimeout(commit, 0), LEAGUE_DEBOUNCE_MS);
      };
      popoverCloseHook = () => { if (timer) commit(); };
      undo.addEventListener("click", () => {
        draft.scoring = opened.scoring;
        draft.teams = opened.teams;
        draft.roster = {...opened.roster};
        draft.weeks = opened.weeks && {...opened.weeks};
        draft.adv = opened.adv && {...opened.adv};
        render();
        commit();
      });
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "v2-btn v2-preset";
      reset.textContent = "Reset defaults";
      reset.dataset.leagueReset = "";
      reset.addEventListener("click", () => {
        if (!leagueDefaults) return;
        draft.scoring = leagueDefaults.scoring;
        draft.teams = leagueDefaults.teams;
        draft.roster = {...leagueDefaults.roster};
        if (draft.weeks) draft.weeks = seasonWeeksState(true);
        if (draft.adv) draft.adv = advancedState(true);
        render();
        commit();
      });
      const tools = document.createElement("div");
      tools.className = "v2-league-tools";
      tools.append(reset, undo, msg, issue);
      panelActions(pop, [["Done", true, closePopover, {"data-done": "league"}]], tools);
    });
  }

  // ---------- 11 Position weights ----------
  // JEG-537 (GL-23): the bench share is a readout worked out from the reader's settings (expected starts),
  // with one override, off by default (Advanced in Your league). benchReadoutText reads the engine's
  // getBenchShareReadout(); v2 does no math.
  const pctText = fraction => `${(fraction * 100).toFixed(1)}%`;
  function benchReadoutText(readout) {
    if (!readout || readout.error) return {text: "Bench share not available: the values are not built yet", override: false, missing: true};
    if (readout.override && Number.isFinite(readout.overrideValue)) {
      return {text: `Bench share: ${pctText(readout.overrideValue)} (your override)`, short: `${pctText(readout.overrideValue)} (your override)`, override: true, missing: false};
    }
    const parts = ["QB", "RB", "WR", "TE"].map(pos => `${pos} ${Number.isFinite(readout[pos]) ? pctText(readout[pos]) : "—"}`);
    return {text: `Bench share this week: ${parts.join(", ")}, from your league settings`, short: parts.join(" · "), override: false, missing: false};
  }
  const BENCH_INFO = "The bench share is how much of each position's value sits with bench players. It comes from how often bench players actually reach a lineup in your league setup: byes, injuries and how deep your bench is.";
  function openWeights(event) {
    // JEG-1119: Position weights sits in the ⋯ menu; with the menu closed the panel anchors (and returns focus) to ⋯.
    // JEG-1134: on a phone with the context row closed ⋯ is not shown either, so it anchors to the button that opened it.
    const opener = event && event.currentTarget instanceof Element ? event.currentTarget : null;
    const anchor = [$("v2Weights"), $("v2ContextMore"), opener].find(b => b && b.offsetParent) || $("v2ContextMore");
    openPanel(anchor, "Position weights", "Applies across tabs", pop => {
      const body = panelBody(pop);
      eyebrow(body, "Bench share");
      const readoutBox = document.createElement("div");
      readoutBox.className = "v2-pbenchread";
      const readout = document.createElement("p");
      readout.className = "v2-pbig-text";
      readout.dataset.benchReadout = "";
      const info = document.createElement("p");
      info.className = "v2-meta";
      info.textContent = BENCH_INFO;
      const resetLink = document.createElement("button");
      resetLink.type = "button";
      resetLink.className = "v2-link";
      resetLink.dataset.benchOverrideReset = "";
      resetLink.textContent = "Reset to the league's bench share";
      resetLink.addEventListener("click", () => {
        if (C.setBenchShareOverride) C.setBenchShareOverride(null);
        refresh();
        saveLeagueSettings();
        syncReadout();
        announceLeagueChange("bench");
      });
      readoutBox.append(readout, resetLink, info);
      body.appendChild(readoutBox);
      const syncReadout = () => {
        const shown = benchReadoutText(C.getBenchShareReadout ? C.getBenchShareReadout() : null);
        readout.textContent = shown.text;
        resetLink.hidden = !shown.override;
      };
      syncReadout();
      // Frame 11 position shares (JEG-452 engine API). The reader edits any shares; on Apply the
      // engine sets exactly those and splits the rest in proportion (setPositionWeights), so v2
      // never rebalances them itself.
      eyebrow(body, "Position shares of total value");
      const shares = document.createElement("p");
      shares.className = "v2-meta";
      shares.textContent = "Shares total 100%. Shares you leave alone split the rest in proportion. Changes apply as you make them.";
      body.appendChild(shares);
      const weights = C.getPositionWeights();
      const shareBounds = C.getPositionWeightBounds ? C.getPositionWeightBounds() : null;
      const edited = {};
      let resetShares = false;
      const inputs = {};
      const lastValid = {};
      const bars = {};
      const nows = {};
      const openedWeights = {...weights};
      let timer = 0;
      let lastMs = 0;
      let queue = () => {};   // JEG-1020: set below; a valid share starts the same debounce as Your league
      const shareMsg = document.createElement("p");
      shareMsg.className = "v2-meta v2-share-msg";
      shareMsg.dataset.shareMessage = "";
      shareMsg.setAttribute("role", "alert");
      shareMsg.hidden = true;
      body.appendChild(shareMsg);
      ["QB", "RB", "WR", "TE"].forEach(pos => {
        const line = document.createElement("div");
        line.className = "v2-pshare";
        const v = Number(weights[pos]);
        const label = document.createElement("label");
        label.htmlFor = `v2Share${pos}`;
        label.textContent = pos;
        const bar = document.createElement("span");
        bar.className = "v2-pshare-bar";
        bar.setAttribute("aria-hidden", "true");
        bar.innerHTML = `<span style="width:${Number.isFinite(v) ? Math.min(100, v * 100) : 0}%"></span>`;
        const field = document.createElement("span");
        field.className = "v2-pshare-field";
        const input = document.createElement("input");
        input.type = "number";
        input.id = `v2Share${pos}`;
        input.step = "0.1";
        const [lo, hi] = shareBounds && shareBounds[pos] ? shareBounds[pos] : [0, 1];
        input.min = (lo * 100).toFixed(1);
        input.max = (hi * 100).toFixed(1);
        input.value = Number.isFinite(v) ? (v * 100).toFixed(1) : "";
        input.disabled = !shareBounds;
        // JEG-834: an out-of-range or empty share is never applied. The last valid value stays in
        // `edited` (or the current engine share), a message says the allowed range, and the box
        // snaps back to that value when the reader leaves it.
        lastValid[pos] = Number.isFinite(v) ? Number((v * 100).toFixed(1)) : null;
        input.addEventListener("input", () => {
          const n = Number(input.value);
          const ok = input.value.trim() !== "" && Number.isFinite(n) && n >= lo * 100 - 1e-9 && n <= hi * 100 + 1e-9;
          if (ok) {
            edited[pos] = n / 100;
            lastValid[pos] = n;
            input.removeAttribute("aria-invalid");
            shareMsg.hidden = true;
            shareMsg.textContent = "";
            resetShares = false;
            queue();
          } else {
            input.setAttribute("aria-invalid", "true");
            shareMsg.hidden = false;
            shareMsg.textContent = `${pos} share must be between ${+(lo * 100).toFixed(1)}% and ${+(hi * 100).toFixed(1)}%. Keeping ${lastValid[pos] === null ? "the current value" : `${lastValid[pos].toFixed(1)}%`}.`;
          }
        });
        input.addEventListener("change", () => {
          if (input.getAttribute("aria-invalid") === "true" && lastValid[pos] !== null) {
            input.value = lastValid[pos].toFixed(1);
            input.removeAttribute("aria-invalid");
          }
        });
        inputs[pos] = input;
        bars[pos] = bar;
        const now = document.createElement("span");
        now.className = "v2-meta";
        now.dataset.weight = pos;
        now.textContent = Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—";
        nows[pos] = now;
        field.append(input, document.createTextNode("% "));
        line.append(label, bar, field, now);
        body.appendChild(line);
      });
      const msg = document.createElement("p");
      msg.className = "v2-meta v2-league-msg";
      msg.dataset.leagueMsg = "";
      const undo = document.createElement("button");
      undo.type = "button";
      undo.className = "v2-btn v2-preset";
      undo.textContent = "Undo changes";
      undo.dataset.weightsUndo = "";
      undo.disabled = true;
      // What the engine holds now goes back into the boxes (the shares you did not edit were rebalanced there).
      function showEngineShares() {
        const now = C.getPositionWeights();
        ["QB", "RB", "WR", "TE"].forEach(pos => {
          const v = Number(now[pos]);
          if (!Number.isFinite(v)) return;
          nows[pos].textContent = `${(v * 100).toFixed(1)}%`;
          bars[pos].firstElementChild.style.width = `${Math.min(100, v * 100)}%`;
          if (document.activeElement !== inputs[pos]) inputs[pos].value = (v * 100).toFixed(1);
          lastValid[pos] = Number((v * 100).toFixed(1));
        });
        syncReadout();
      }
      function commit() {
        clearTimeout(timer);
        timer = 0;
        const t0 = performance.now();
        let note = "";
        let notes = [];
        try {
          if (resetShares && C.resetPositionWeights) C.resetPositionWeights();
          else if (Object.keys(edited).length && C.setPositionWeights) {
            const result = C.setPositionWeights(edited);
            if (result && result.ok && result.clamped) note = "Some position shares were held to their allowed range.";
            else if (result && !result.ok) note = "Position shares were not changed. The results still show the last valid shares.";
          }
          try { refresh(); } catch (error) { console.warn("Refresh after a weights change failed:", error); }
          notes = announceLeagueChange("weights");
        } catch (caught) {
          note = `Not applied: ${(caught && caught.message) || "those shares could not be applied."} The results still show the last valid shares.`;
        }
        Object.keys(edited).forEach(pos => delete edited[pos]);
        resetShares = false;
        saveLeagueSettings();
        lastMs = performance.now() - t0;
        (window.__leagueApplyLog = window.__leagueApplyLog || []).push(Math.round(lastMs));
        msg.textContent = note;
        showEngineShares();
        announceLive(["Results updated for the new league settings.", ...notes].join(" "));
        undo.disabled = JSON.stringify(C.getPositionWeights()) === JSON.stringify(openedWeights);
      }
      queue = () => {
        undo.disabled = false;
        clearTimeout(timer);
        if (lastMs >= LEAGUE_SLOW_MS * 0.8) msg.textContent = "Updating…";
        timer = setTimeout(() => setTimeout(commit, 0), LEAGUE_DEBOUNCE_MS);
      };
      popoverCloseHook = () => { if (timer) commit(); };
      undo.addEventListener("click", () => {
        Object.keys(edited).forEach(pos => delete edited[pos]);
        const defaults = C.getDefaultPositionWeights ? C.getDefaultPositionWeights() : null;
        const isDefault = defaults && ["QB", "RB", "WR", "TE"].every(pos => Math.abs(Number(defaults[pos]) - Number(openedWeights[pos])) < 1e-9);
        if (isDefault) resetShares = true; else Object.assign(edited, openedWeights);
        shareMsg.hidden = true;
        commit();
      });
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "v2-btn v2-preset";
      reset.textContent = "Reset defaults";
      reset.dataset.weightsReset = "";
      reset.addEventListener("click", () => {
        Object.keys(edited).forEach(pos => delete edited[pos]);
        resetShares = true;
        Object.values(inputs).forEach(input => input.removeAttribute("aria-invalid"));
        shareMsg.hidden = true;
        commit();
      });
      const tools = document.createElement("div");
      tools.className = "v2-league-tools";
      tools.append(reset, undo, msg);
      panelActions(pop, [["Done", true, closePopover, {"data-done": "weights"}]], tools);
    });
  }

  // ---------- 10 Source freshness (JEG-463: root sources only) ----------
  // One row per publisher. Pipeline health (import, fixture rebuild) is folded into that
  // source's status from assets/reference-freshness.json; users never see pipeline rows.
  let pipeline = null;          // reference-freshness items by key, once loaded
  let pipelineLoading = null;
  function loadPipeline() {
    if (pipeline || pipelineLoading) return pipelineLoading;
    pipelineLoading = fetch("assets/reference-freshness.json")
      .then(r => (r.ok ? r.json() : null))
      .catch(() => null)
      .then(doc => {
        pipeline = Object.fromEntries(((doc && doc.items) || []).filter(item => item && item.key).map(item => [item.key, item]));
        divergence = doc && doc.source_divergence && typeof doc.source_divergence === "object" ? doc.source_divergence : {};
        if (C && view) refresh();   // the chips arrive after the first draw
        return pipeline;
      });
    return pipelineLoading;
  }
  const dayOf = text => (/^\d{4}-\d{2}-\d{2}/.test(String(text || "")) ? String(text).slice(0, 10) : "");
  // JEG-806: "as of <date>" from the fixture's built_at, so the reader knows
  // how old the numbers are. Formats as "Oct 19" (no year: always current season).
  function dataAsOfLabel() {
    const snap = window.TradeValueProductData?.getSnapshot?.();
    const iso = dayOf(snap?.built_at);
    if (!iso) return null;
    try {
      return new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", timeZone: "UTC"}).format(new Date(`${iso}T00:00:00Z`));
    } catch (e) { return iso; }
  }
  function rootFreshness() {
    const pubs = Object.keys(PUBLISHERS).filter(pub => view.info.some(item => sourceMeta(item.key).publisher === pub));
    return pubs.map(pub => {
      const items = view.info.filter(item => sourceMeta(item.key).publisher === pub);
      const base = items.find(item => item.key === pub) || items[0];
      const name = PUBLISHER_NAMES[pub] || pub;
      const p = pipeline || {};
      const own = p[`comparison.source.${pub}`];
      const imp = p[`source_import.${pub}`];
      const failingStep = [imp, own, p["source_import.checked_at"], p["comparison.built_at"]].find(item => item && item.freshness_ok === false);
      const paused = items.some(item => item.paused);
      if (failingStep || paused) {
        const since = dayOf(imp && imp.value) || dayOf(own && own.value);
        return {pub, name, week: base?.week, status: "stuck",
          text: "Not updating", reason: `We couldn't refresh ${name}${since ? ` since ${since}` : ""}.`};
      }
      // JEG-675: "showing Week N" is only true of a source the page shows. A held source is unavailable (no values,
      // no columns), so its pipeline weeks_behind no longer reads "Prior week" (it said so for CBS while held).
      const shown = items.some(item => item.available);
      // JEG-721: a source whose series are all unavailable and excluded for a hold reason is "Held",
      // not "Current". The header must not claim "all sources current" when held sources are hidden.
      const held = !shown && items.every(item => !item.available)
        && items.some(item => item.excludedReason && /held/i.test(item.excludedReason));
      if (held) {
        return {pub, name, week: base?.week, status: "held", text: "Held",
          reason: `${name} is temporarily held for a data check.`};
      }
      const prior = (shown && own && Number(own.weeks_behind) > 0) || items.some(item => item.available && item.stale);
      if (prior) {
        const isChart = items.some(item => sourceMeta(item.key).method === "indexed");
        const noun = isChart ? "chart" : "projections";
        return {pub, name, week: base?.week, status: "prior", text: "Prior week",
          reason: view.refWeek && base?.week
            ? `${name} has not posted its Week ${view.refWeek} ${noun} yet; this page shows its Week ${base.week} ${noun}.` : ""};
      }
      // Fail closed: Current only when this source's own rows say freshness_ok === true. A missing
      // or unreadable file, or a missing row, is "Freshness unknown", never a green tick.
      const confirmed = Boolean(own && imp && own.freshness_ok === true && imp.freshness_ok === true);
      if (!confirmed) {
        return {pub, name, week: base?.week, status: "unknown", text: "Freshness unknown",
          reason: pipeline ? `We couldn't confirm when ${name} last updated.` : `Checking when ${name} last updated.`};
      }
      return {pub, name, week: base?.week, status: "current", text: "Current", reason: ""};
    });
  }
  function openFreshness() {
    openPanel($("v2Freshness"), "Source freshness", view.refWeek ? `Week ${view.refWeek} board · each source's own week` : "Each source's own week", pop => {
      const body = panelBody(pop);
      const table = document.createElement("table");
      table.className = "v2-ptable";
      table.innerHTML = "<thead><tr><th scope=\"col\">Source</th><th scope=\"col\">Published</th><th scope=\"col\">Status</th></tr></thead>";
      const tbody = document.createElement("tbody");
      rootFreshness().forEach(r => {
        const tr = document.createElement("tr");
        tr.dataset.source = r.pub;
        tr.dataset.status = r.status;
        const name = document.createElement("th");
        name.scope = "row";
        name.innerHTML = `<span style="color:${pubColor(r.pub)}" aria-hidden="true">${PUBLISHERS[r.pub]?.symbol || ""}</span> `;
        name.append(document.createTextNode(r.name));
        const week = document.createElement("td");
        week.textContent = r.week ? `Week ${r.week}` : "—";
        const status = document.createElement("td");
        status.className = r.status === "stuck" ? "is-bad" : r.status === "current" ? "is-ok" : "is-older";
        status.textContent = `${{stuck: "⚠ ", prior: "⚠ ", unknown: "? ", current: "✓ ", held: "⏸ "}[r.status] || ""}${r.text}`;
        if (r.reason) {
          const why = document.createElement("span");
          why.className = "th-sub";
          why.textContent = r.reason;
          status.appendChild(why);
        }
        tr.append(name, week, status);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      const wrap = document.createElement("div");
      wrap.className = "v2-ptable-wrap";
      wrap.appendChild(table);
      body.appendChild(wrap);
      const manage = document.createElement("button");
      manage.type = "button";
      manage.className = "v2-btn v2-btn-soft";
      manage.textContent = "Customize values";
      manage.addEventListener("click", () => openSources($("v2EditSources")));
      panelActions(pop, [["Close", false, closePopover]], manage);
    });
  }

  // ---------- 24 Value range ----------
  function openRange() {
    const key = view.rankKey;
    const item = view.infoByKey[key];
    const values = C.getRows().map(row => row.values[key]).filter(Number.isFinite);
    const lo = values.length ? Math.floor(Math.min(...values)) : 0;
    const hi = values.length ? Math.ceil(Math.max(...values)) : 100;
    openPanel($("v2Show"), "Value range", `Basis ${sourceMeta(key).short}${item?.week ? ` · Week ${item.week}` : ""}`, pop => {
      const body = panelBody(pop);
      const lead = document.createElement("p");
      lead.textContent = "Keep players with values between";
      body.appendChild(lead);
      const row = document.createElement("div");
      row.className = "row2";
      const mk = (text, value) => {
        const label = document.createElement("label");
        label.textContent = text;
        const input = document.createElement("input");
        input.type = "number"; input.step = "0.1"; input.min = "0";
        input.value = value === null ? "" : String(value);
        label.appendChild(input);
        row.appendChild(label);
        return input;
      };
      const minI = mk("Minimum", state.range.min);
      const maxI = mk("Maximum", state.range.max);
      body.appendChild(row);
      // Two handles over the basis series' own spread; they mirror the number fields.
      const dual = document.createElement("div");
      dual.className = "v2-dual";
      const mkSlider = (aria, value) => {
        const s = document.createElement("input");
        s.type = "range"; s.min = String(lo); s.max = String(hi); s.step = "0.1";
        s.value = String(value);
        s.setAttribute("aria-label", aria);
        dual.appendChild(s);
        return s;
      };
      const minS = mkSlider("Minimum value", state.range.min ?? lo);
      const maxS = mkSlider("Maximum value", state.range.max ?? hi);
      minS.addEventListener("input", () => { if (Number(minS.value) > Number(maxS.value)) minS.value = maxS.value; minI.value = minS.value; });
      maxS.addEventListener("input", () => { if (Number(maxS.value) < Number(minS.value)) maxS.value = minS.value; maxI.value = maxS.value; });
      minI.addEventListener("input", () => { if (minI.value !== "") minS.value = minI.value; });
      maxI.addEventListener("input", () => { if (maxI.value !== "") maxS.value = maxI.value; });
      body.appendChild(dual);
      const err = document.createElement("p");
      err.className = "v2-meta";
      err.textContent = "Inclusive. Blank = open ended. Missing values are excluded with a visible count.";
      body.appendChild(err);
      panelActions(pop, [
        ["Clear range", false, () => { setRange({min: null, max: null}); closePopover(); }],
        ["Apply", true, () => {
          const min = minI.value === "" ? null : Number(minI.value);
          const max = maxI.value === "" ? null : Number(maxI.value);
          if (min !== null && max !== null && min > max) {
            err.textContent = "Minimum is above maximum. Swap them or clear one.";
            err.classList.add("v2-perror");
            return;
          }
          closePopover();
          setRange({min, max});
        }, {"data-apply": "range"}]
      ]);
    });
  }

  // ---------- JEG-475 "More": exact From / To ranks ----------
  function setExpanded(id, open) { $(id).setAttribute("aria-expanded", String(open)); }
  function openMore() {
    const button = $("v2More");
    if (!$("v2Popover").hidden && popoverAnchor === button) { closePopover(); return; }
    openPopover(button, pop => {
      pop.classList.remove("is-panel");
      pop.setAttribute("aria-label", "Exact ranks");
      pop.setAttribute("aria-modal", "false");
      pop.removeAttribute("aria-labelledby");
      const h = document.createElement("h2");
      h.textContent = "Exact ranks";
      pop.appendChild(h);
      const lead = document.createElement("p");
      lead.className = "v2-meta";
      lead.textContent = `Show players ranked between (1–${view.rows.length}). Arrow keys on the rank brush move one rank.`;
      pop.appendChild(lead);
      const row = document.createElement("div");
      row.className = "row2";
      const mk = (text, id, value) => {
        const label = document.createElement("label");
        label.textContent = text;
        const input = document.createElement("input");
        input.type = "number"; input.id = id; input.min = "1"; input.max = String(view.rows.length); input.step = "1";
        input.inputMode = "numeric";
        input.value = String(value);
        label.appendChild(input);
        row.appendChild(label);
        return input;
      };
      const from = mk("From", "v2FromRank", state.window[0]);
      const to = mk("To", "v2ToRank", state.window[1]);
      pop.appendChild(row);
      const onBounds = () => {
        const n = view.rows.length;
        let lo = Math.round(Number(from.value));
        let hi = Math.round(Number(to.value));
        if (!Number.isFinite(lo) || !Number.isFinite(hi) || from.value === "" || to.value === "") return;
        lo = Math.max(1, Math.min(n, lo));
        hi = Math.max(1, Math.min(n, hi));
        if (lo > hi) [lo, hi] = [hi, lo];
        setWindow([lo, hi]);
      };
      from.addEventListener("change", onBounds);
      to.addEventListener("change", onBounds);
      const done = document.createElement("div");
      done.className = "actions";
      const doneBtn = document.createElement("button");
      doneBtn.type = "button";
      doneBtn.className = "v2-btn";
      doneBtn.textContent = "Done";
      doneBtn.addEventListener("click", closePopover);
      done.appendChild(doneBtn);
      pop.appendChild(done);
    });
    setExpanded("v2More", true);
  }

  // ---------- JEG-473 "Columns": hide method groups (and Pos / Team / Tier) ----------
  function openColumns() {
    const button = $("v2Columns");
    if (!$("v2Popover").hidden && popoverAnchor === button) { closePopover(); return; }
    openPopover(button, pop => {
      pop.classList.remove("is-panel");
      pop.setAttribute("aria-label", "Table columns");
      pop.setAttribute("aria-modal", "false");
      pop.removeAttribute("aria-labelledby");
      const h = document.createElement("h2");
      h.textContent = "Table columns";
      pop.appendChild(h);
      const present = new Set(view.plotKeys.concat(view.vorpKeys).map(tableGroup));
      if (view.plotKeys.filter(key => sourceMeta(key).method === "dda").length >= 2) present.add("spread");
      const box = (label, checked, attrs, onChange) => {
        const wrap = document.createElement("label");
        wrap.className = "v2-check v2-pcheck";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = checked;
        Object.entries(attrs).forEach(([k, v]) => { input.dataset[k] = v; });
        input.addEventListener("change", () => { onChange(input.checked); renderTable(); });
        wrap.append(input, document.createTextNode(` ${label}`));
        pop.appendChild(wrap);
      };
      eyebrow(pop, "Value groups");
      TABLE_GROUPS.filter(([g]) => present.has(g)).forEach(([g, label]) => {
        box(g === "spread" ? "Spread of our values" : label, !state.hiddenGroups.has(g), {group: g}, on => {
          if (on) state.hiddenGroups.delete(g); else state.hiddenGroups.add(g);
        });
      });
      const note = document.createElement("p");
      note.className = "v2-meta";
      note.textContent = `The ranking series (${sourceMeta(view.rankKey).short}) always shows.`;
      pop.appendChild(note);
      eyebrow(pop, "Player details");
      [["pos", "Position"], ["team", "Team"], ["tier", "Tier"]].forEach(([id, label]) => {
        box(label, state.metaCols[id] !== false, {meta: id}, on => { state.metaCols = {...state.metaCols, [id]: on}; });
      });
      const done = document.createElement("div");
      done.className = "actions";
      const doneBtn = document.createElement("button");
      doneBtn.type = "button";
      doneBtn.className = "v2-btn";
      doneBtn.textContent = "Done";
      doneBtn.addEventListener("click", closePopover);
      done.appendChild(doneBtn);
      pop.appendChild(done);
    });
    setExpanded("v2Columns", true);
  }

  // ---------- trade targets (frames 03 / 04) ----------
  // Every number here is read from the engine's rows; the one piece of
  // arithmetic (chart value − our value) lives in targets.js.
  //
  // Review fixes (JEG-456/458/459/461/464): both lists show at once (side by
  // side from 1024 px, stacked below), each collapsed to its top 5 with its own
  // "Show all"; every available chart is compared, and a chart still on an
  // earlier week carries a "Wk N" badge; chart values are labeled as rescaled.
  const TARGETS_TOP = 5;
  const TARGETS_PAGE = 25;
  const TARGET_SIDES = ["sell", "buy"];
  const TARGET_IDS = {
    sell: {section: "v2TSell", table: "v2TTable", cards: "v2TCards", meta: "v2TSellMeta", empty: "v2TSellEmpty", more: "v2TSellMore", less: "v2TSellLess"},
    buy: {section: "v2TBuy", table: "v2TBuyTable", cards: "v2TBuyCards", meta: "v2TBuyMeta", empty: "v2TBuyEmpty", more: "v2TBuyMore", less: "v2TBuyLess"}
  };
  // ours: which series is "our value" (DDF Value by default, JEG-455). Module state, so the choice
  // survives switching tabs, and remembered on this device like the DDF selection (ddf.v2.targets).
  // shown / expanded are per list: each list opens and collapses on its own.
  const TARGETS_SAVE_KEY = "ddf.v2.targets";
  function loadTargetsOurs() {
    try {
      const saved = JSON.parse(localStorage.getItem(TARGETS_SAVE_KEY) || "null");
      return saved && saved.v === 1 && typeof saved.ours === "string" ? ddfPickKey(saved.ours) : null;
    } catch (error) { return null; }
  }
  function saveTargetsOurs(ours) {
    try { localStorage.setItem(TARGETS_SAVE_KEY, JSON.stringify({v: 1, ours})); }
    catch (error) { /* storage unavailable: the choice lasts this visit only */ }
  }
  const T = {search: "", chart: "all", ours: loadTargetsOurs(),
    shown: {sell: TARGETS_TOP, buy: TARGETS_TOP}, expanded: {sell: new Set(), buy: new Set()}};
  let targetsView = null;

  // Shared (any tab may use these). JEG-459: a published source that has not
  // posted the current week yet is shown on its latest week with a small
  // "Wk N" badge in the older-week colour; its reason is the badge's tooltip
  // and accessible name. A current-week source gets no badge (null).
  function priorWeekInfo(key, item, refWeek) {
    if (!item || !item.stale) return null;
    const name = PUBLISHER_NAMES[key] || key;
    const week = Number.isFinite(item.week) ? item.week : null;
    const short = week ? `Week ${week}` : "Earlier week";
    const label = week && Number.isFinite(refWeek) && refWeek !== week
      ? `${name} has not posted its Week ${refWeek} chart yet; this page shows its Week ${week} chart.`
      : `${name} has not posted this week's chart yet; this page shows ${week ? `its Week ${week} chart` : "an earlier chart"}.`;
    return {short, label, week};
  }
  function priorWeekBadge(key, item, refWeek) {
    const info = priorWeekInfo(key, item, refWeek);
    if (!info) return null;
    const badge = document.createElement("span");
    badge.className = "v2-prior-badge";
    badge.dataset.priorWeek = key;
    badge.title = info.label;
    badge.setAttribute("role", "img");
    badge.setAttribute("aria-label", info.label);
    badge.textContent = info.short;
    return badge;
  }

  // Shared ⓘ (JEG-458): why trade chart values are "rescaled". A 44 px
  // target that opens a small popover (Esc or a click outside closes it); it
  // never reaches a row or column-header handler behind it.
  const INDEXED_INFO_DEFAULT = "Each source's trade-value estimate, rescaled to our point scale for your league. Its ranking order is unchanged.";
  const INDEXED_INFO = INDEXED_INFO_DEFAULT;
  // JEG-490: our names, defined once and used wherever they are shown (the "On the chart" row, Risers,
  // Customize, the disagreement card, the deal read, How values work). Plain words, no numbers.
  // JEG-863 / JEG-1073: two names. DDF Value is the Adjusted trade charts averaged (Jeremy, 2026-10-25); the trade
  // chart average is the existing four rescaled chart inputs, including FantasyCalc, averaged. The projections
  // version is the alternate, named for the deal read's production check.
  const NAME_DEFS = [
    ["DDF Value", "What a player is worth in your league: rooted in the trade charts, then adjusted for position weight and your league's rosters."],
    ["Trade chart average", "The mean of the selected, available rescaled chart inputs with complete values for a comparison. Trade readouts need at least three complete inputs. FantasyCalc is eligible alongside USA Today, FantasyPros and CBS. It is an estimate, not a record of what a trade will pay."]];
  // The deal read's nets (DEAL_NETS) by the name they define themselves with. Since JEG-1073 the projections net is
  // the alternate version, not DDF Value; the net itself is trade.js's.
  const PROJECTIONS_DEF = ["DDF Value (projections)", "The alternate: the projection sources, equal weight, averaged for your league."];
  const DEAL_NET_DEF = {value: NAME_DEFS[0], market: NAME_DEFS[1], projections: PROJECTIONS_DEF};
  const EDGE_DEF = "The edge: buy below DDF Value and sell above it. It is best when DDF Value says you win and the market says you lose.";
  const INFO_SPECS = {
    indexed: {kind: "indexed", what: "rescaled", title: "Rescaled values", lines: [INDEXED_INFO]},   // syncBasisLabels rewrites the line
    names: {kind: "names", what: "our names", title: "Our names", lines: NAME_DEFS.map(([name, text]) => [name, text]).concat([["", EDGE_DEF]])}
  };
  function namesInfoButton(context) { return indexedInfoButton(context, INFO_SPECS.names); }
  function indexedInfoButton(context, spec = INFO_SPECS.indexed) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "v2-info";
    button.dataset.info = spec.kind;
    button.setAttribute("aria-label", `What ${spec.what} ${spec.kind === "names" ? "mean" : "means"}${context ? ` (${context})` : ""}`);
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    const glyph = document.createElement("span");
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = "ⓘ";
    button.appendChild(glyph);
    ["keydown", "keyup"].forEach(type => button.addEventListener(type, event => {
      if (event.key === "Enter" || event.key === " ") event.stopPropagation();
    }));
    // JEG-501: on hover-capable pointers the popover opens after a short
    // delay and stays while the pointer is on the button or the popover (a
    // grace period lets it cross the gap). A click pins it; touch, click,
    // keyboard and Esc behave as before.
    const canHover = event => event.pointerType === "mouse" && window.matchMedia && window.matchMedia("(hover: hover)").matches;
    const showInfo = fromHover => {
      closePopover(true);
      openPopover(button, pop => {
        pop.classList.remove("is-panel");
        pop.classList.add("v2-info-pop");
        pop.setAttribute("aria-modal", "false");
        pop.setAttribute("aria-labelledby", "v2InfoTitle");
        const h = document.createElement("h2");
        h.id = "v2InfoTitle";
        h.textContent = spec.title;
        const text = document.createElement("div");
        text.className = "v2-info-text";
        spec.lines.forEach(line => {
          const p = document.createElement("p");
          if (Array.isArray(line)) {
            if (line[0]) { const b = document.createElement("b"); b.textContent = line[0]; p.append(b, document.createTextNode(` ${line[1]}`)); }
            else p.textContent = line[1];
          } else p.textContent = line;
          text.appendChild(p);
        });
        const foot = document.createElement("div");
        foot.className = "v2-info-foot";
        const link = document.createElement("a");
        link.className = "v2-link";
        link.href = "v2/#writing/how-values";
        link.textContent = "How values work";
        link.addEventListener("click", () => closePopover());
        const close = document.createElement("button");
        close.type = "button";
        close.className = "v2-btn";
        close.textContent = "Close";
        close.addEventListener("click", closePopover);
        foot.append(link, close);
        pop.append(h, text, foot);
      });
      button.setAttribute("aria-expanded", "true");
      hoverOpened = fromHover;
      const link = $("v2Popover").querySelector("a");
      if (link && !fromHover) link.focus();
    };
    let openTimer = null;
    let closeTimer = null;
    const popOpenForButton = () => popoverAnchor === button && !$("v2Popover").hidden;
    const cancelTimers = () => { clearTimeout(openTimer); clearTimeout(closeTimer); };
    const scheduleHoverClose = () => {
      cancelTimers();
      closeTimer = setTimeout(() => { if (popOpenForButton() && hoverOpened) closePopover(true); }, 250);
    };
    button.addEventListener("pointerenter", event => {
      if (!canHover(event)) return;
      cancelTimers();
      hoverHold = {cancel: () => clearTimeout(closeTimer), schedule: scheduleHoverClose};
      if (popOpenForButton()) return;
      openTimer = setTimeout(() => { if (!popOpenForButton()) showInfo(true); }, 200);
    });
    button.addEventListener("pointerleave", event => {
      if (!canHover(event)) return;
      clearTimeout(openTimer);
      if (popOpenForButton() && hoverOpened) scheduleHoverClose();
    });
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      clearTimeout(openTimer);
      if (popOpenForButton()) {
        if (hoverOpened) { hoverOpened = false; clearTimeout(closeTimer); return; }
        closePopover();
        return;
      }
      closePopover();
      showInfo(false);
    });
    return button;
  }

  const fmtGap = gap => {
    if (!Number.isFinite(gap)) return "—";
    const text = Math.abs(gap).toFixed(1);
    if (text === "0.0") return "0.0";
    return `${gap > 0 ? "+" : "−"}${text}`;
  };

  const targetBadge = key => priorWeekBadge(key, targetsView.infoByKey[key], targetsView.refWeek);

  function collectTargets() {
    const TT = window.TradeValueTargets;
    const info = sourceInfoWithFreshness();
    const infoByKey = Object.fromEntries(info.map(item => [item.key, item]));
    const mine = new Set(pageKeys("targets"));
    const choices = TT.ourChoices(info);
    const ourKey = TT.OUR_KEYS.includes(T.ours) ? T.ours : TT.OUR_KEY;
    const ours = infoByKey[ourKey];
    const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
    // JEG-806: same data-week fix as the main view.
    const refWeek = freshness?.first_load_reference_week || C.getReferenceWeek();
    // The published series are on the trade-value point scale only in the
    // engine's Indexed view; any other view would pair unlike units.
    const engineView = window.TradeValueCurveDiagnostics?.viewMode;
    // JEG-498: only the charts ticked in this page's Customize are compared; a chart left out is not "skipped".
    // JEG-851: a single chart is now selectable; "all" compares every enabled chart.
    // JEG-868: a chart cannot be compared against itself; the pick falls back to "all" before the lists are
    // built (not only when the controls redraw), so no render ever compares against nothing.
    if (T.chart !== "all" && T.chart === ourKey) T.chart = "all";
    const picked = T.chart !== "all" ? T.chart : null;
    const compared = TT.chartsToCompare(info.filter(item => !TT.CHART_KEYS.includes(item.key) || mine.has(item.key)), {only: picked});
    // JEG-868: when our value is itself a trade chart, "All trade charts" means the OTHER charts. The engine
    // already drops our chart from the compared set (effectiveCharts), so `used` must match it: a column the
    // engine did not price has no cell, and reading it threw mid-render and left the previous lists on the page.
    const ownChart = TT.CHART_KEYS.includes(ourKey) ? ourKey : null;
    const used = compared.used.filter(key => key !== ownChart);
    const skipped = compared.skipped;
    const prior = compared.prior.filter(key => key !== ownChart);
    const needle = T.search.trim().toLowerCase();
    const rows = C.getRows();
    rows.forEach((row, index) => { row.rank = index + 1; });
    const searched = needle ? window.TradeValueNameSearch.filter(rows, T.search) : rows;
    // Fails closed: an unavailable choice is never swapped for another series.
    const blocked = !ours || !ours.available ? `Our value (${TT.OUR_NAMES[ourKey]}) is not available for this league right now.`
      : engineView && engineView !== "indexed" ? "Trade charts are not on the trade-value point scale in this view, so no gaps are shown."
      : null;
    // JEG-833: ranks are computed over every row; a name search only filters what is listed (opts.keep).
    const kept = needle ? new Set(searched) : null;
    const result = blocked ? {ours: ourKey, sell: [], buy: [], compared: 0, omittedNoOurs: 0, atWaiverCells: 0, belowSellFloor: 0, scaleOnly: 0, scaleOnlyNames: [], leftOut: 0, leftOutNames: [], thinSource: 0, thinSourceNames: []}
      : TT.buildTargets(rows, used, {ours: ourKey, keep: kept ? row => kept.has(row) : null});
    // Why players were left out: the engine's reasons, most common first (display only).
    const omittedReasons = new Map();
    if (!blocked) {
      searched.filter(row => !Number.isFinite(row.values?.[ourKey])).forEach(row => {
        const reason = missingReason(ourKey, row);
        omittedReasons.set(reason, (omittedReasons.get(reason) || 0) + 1);
      });
    }
    targetsView = {...result, ours: ourKey, choices, used, skipped, prior: prior || [], info, infoByKey, refWeek, blocked,
      searchMiss: Boolean(needle) && !searched.length,   // JEG-911: the search matched no name at all
      position: C.getState().position, tierScope: {rows, pos: C.getState().position, engineOrder: true},
      omittedReasons: [...omittedReasons].sort((a, b) => b[1] - a[1])};
  }

  function renderTargetControls() {
    const TT = window.TradeValueTargets;
    const select = $("v2TChart");
    select.replaceChildren();
    const all = document.createElement("option");
    all.value = "all";
    // JEG-868: with a trade chart as Our value, "all" compares it against the other charts, and says so.
    all.textContent = TT.CHART_KEYS.includes(targetsView.ours) ? "All other trade charts" : "All trade charts";
    select.appendChild(all);
    const mineCharts = new Set(pageKeys("targets"));
    TT.CHART_KEYS.filter(key => mineCharts.has(key)).forEach(key => {
      const item = targetsView.infoByKey[key];
      const option = document.createElement("option");
      option.value = key;
      const missing = !item || !item.available;
      // JEG-851: a single chart is selectable; disable only when unavailable or same as our value.
      const sameAsOurs = TT.CHART_KEYS.includes(targetsView.ours) && key === targetsView.ours;
      option.disabled = missing || sameAsOurs;
      const prior = missing ? null : priorWeekInfo(key, item, targetsView.refWeek);
      option.textContent = `${PUBLISHERS[key].symbol} ${PUBLISHER_NAMES[key]}${missing ? " — not available" : sameAsOurs ? " — same as Our value" : `${prior ? ` · ${prior.short} (prior week)` : ""}`}`;
      if (prior) {
        option.dataset.priorWeek = key;
        option.title = prior.label;
      }
      select.appendChild(option);
    });
    // JEG-851: reset to "all" if the selected chart is not available or same as our value.
    const sameChartAsOurs = TT.CHART_KEYS.includes(targetsView.ours) && T.chart === targetsView.ours;
    if (T.chart !== "all" && (!mineCharts.has(T.chart) || sameChartAsOurs)) T.chart = "all";
    select.value = T.chart;
    // The picked chart's own badge sits beside the caption (an <option> cannot hold one).
    const slot = $("v2TChartBadge");
    slot.replaceChildren();
    if (T.chart !== "all") {
      const badge = targetBadge(T.chart);
      if (badge) slot.appendChild(badge);
    }
    const oursSelect = $("v2TOurs");
    oursSelect.replaceChildren();
    targetsView.choices.forEach(choice => {
      if (ddfPickKey(choice.key) !== choice.key) return;   // JEG-863: the hidden duplicate DDF id
      const option = document.createElement("option");
      option.value = choice.key;
      // JEG-851: disable a chart key when it's the same as the single compared chart.
      const sameAsChart = TT.CHART_KEYS.includes(choice.key) && T.chart === choice.key;
      option.disabled = !choice.available || sameAsChart;
      option.textContent = `${sourceMeta(choice.key).symbol} ${TT.OUR_NAMES[choice.key]}${!choice.available ? ` — ${choice.reason}` : sameAsChart ? " — same as Compare against" : ""}`;
      oursSelect.appendChild(option);
    });
    oursSelect.value = targetsView.ours;
    $("v2TPosition").value = targetsView.position;
  }

  // DDF Value's "from N sources" (row.ddfCount), the sub-text under our value.
  function ddfCountNode(row, key = DDF_KEY) {
    const entry = ddfEntry(row, key);
    const count = key === DDF_KEY ? row.ddfCount : entry && entry.count;
    const sources = key === DDF_KEY ? row.ddfSources : entry && entry.sources;
    if (isLowConfidence(row, key)) {
      const node = lowConfidenceNode(row, key);
      node.classList.add("why", "t-count");
      node.dataset.ddfCount = String(Number.isFinite(count) ? count : 1);
      return node;
    }
    if (!Number.isFinite(count)) return null;
    const node = document.createElement("span");
    node.className = "why t-count";
    node.dataset.ddfCount = String(count);
    node.textContent = `from ${count} source${count === 1 ? "" : "s"}`;
    if (Array.isArray(sources) && sources.length) { node.title = sources.map(seriesName).join(", "); describe(node, `From ${node.title}`); }
    return node;
  }
  // Our value: the number (with DDF Value's source count), or "—" with the engine's reason.
  function oursValue(cell, p) {
    if (!Number.isFinite(p.ours)) {
      cell.appendChild(missingNode(missingReason(targetsView.ours, p.row), "no value"));
      return;
    }
    cell.appendChild(document.createTextNode(fmt(p.ours)));
    // JEG-1059: the badge next to the value the reader set.
    if (targetsView.ours === DDF_KEY) appendOverrideFlag(cell, p.row);
    if (isDdfKey(targetsView.ours)) {
      const count = ddfCountNode(p.row, targetsView.ours);
      if (count) cell.appendChild(count);
    }
  }

  // JEG-504: the market average of the compared charts, beside our value. Equal to one
  // decimal: a note instead of a duplicate number. Otherwise the average with its count
  // ("avg of 4", plus "1 left out" for a chart that does not price the player) and
  // our value minus the average, with a symbol (▲ ours is higher, ▼ lower) and a sign.
  function marketValue(cell, p) {
    const m = p.market;
    cell.dataset.market = "";
    if (m.value === null) {
      cell.appendChild(missingNode("No compared chart prices this player", "no chart value"));
      return;
    }
    // JEG-851: in single-chart mode, say the chart's name, not "market consensus" / "median of N".
    const sc = targetsView.singleChart;
    const scLabel = sc ? (PUBLISHER_NAMES[sc] || sc) : null;
    if (m.equal) {
      cell.dataset.marketEqual = "";
      const note = document.createElement("span");
      note.className = "why t-equal";
      note.textContent = sc ? `= ${scLabel}` : "= market consensus";
      note.title = sc
        ? `${scLabel}'s rescaled value is ${fmt(m.value)}, the same as our value.`
        : `The middle value of the ${m.count} compared chart${m.count === 1 ? "" : "s"} is ${fmt(m.value)}, the same as our value.`;
      describe(note, note.title);
      cell.appendChild(note);
      return;
    }
    cell.appendChild(document.createTextNode(fmt(m.value)));
    const count = document.createElement("span");
    count.className = "why t-count";
    count.dataset.marketCount = String(m.count);
    count.textContent = sc ? scLabel : `middle of ${m.count} chart${m.count === 1 ? "" : "s"}${m.left ? ` · ${m.left} left out` : ""}`;
    if (m.left) describe(count, count.title = `${m.left} compared chart${m.left === 1 ? " has" : "s have"} no value for this player and ${m.left === 1 ? "is" : "are"} left out.`);
    const diff = document.createElement("span");
    diff.className = "why t-diff";
    diff.dataset.marketDiff = m.diff.toFixed(1);
    // JEG-833: said in words (ours is above / below the consensus), not as a signed number that contradicts the gap.
    describe(diff, diff.title = "Market consensus minus our value: the same difference and sign as the Gap");
    // JEG-977: the same sign as the Gap column (market minus ours): "+3.3" means the market is 3.3 above our value.
    diff.textContent = fmtGap(-m.diff);
    cell.append(diff, count);
  }

  // JEG-457: hover, focus or tap a chart value on Trade targets and see where it comes from, starting with the number
  // as the publisher prints it so it can be matched against the page. native and factor come from the engine's own
  // derivation (getPublishedMath), never recomputed here; indexed = native x factor is the engine's, so the
  // lines add up to the cell (rounded to one decimal for points, three for the factor).
  let mathTipOwner = null;
  let mathTipOpenedAt = 0;
  const fmtTotal = n => n.toLocaleString("en-US", {maximumFractionDigits: 0});
  function mathTipLines(p, chart, cell) {
    const name = PUBLISHER_NAMES[chart] || chart;
    const item = (targetsView && targetsView.infoByKey[chart]) || (view && view.infoByKey && view.infoByKey[chart]);
    const week = item && item.week ? `, Week ${item.week}` : "";
    const lines = [];
    const math = C.getPublishedMath ? C.getPublishedMath(p.row.player_key, chart) : null;
    if (cell.value === null) return {head: `${name}${week}`, lines: [[cell.reason || `Not on ${name}'s chart`, ""]], plain: true};
    const estimated = estimatedReason(p.row, chart);
    if (!math || math.native === null || math.factor === null) {
      return {head: `${name}${week}`, plain: true, lines: [[estimated ? `Estimated: ${estimated}` : "The engine has no published number to show for this value.", ""],
        ["= rescaled value", fmt(cell.value)]].concat(cell.gap !== null && Number.isFinite(p.ours) ? [["− our value", fmt(p.ours)], ["= gap", fmtGap(cell.gap)]] : [])};
    }
    lines.push([`${name}${week} (original)`, String(math.native)]);
    const totalsNote = math.anchorTotal !== null && math.chartTotal !== null
      ? `${fmtTotal(math.anchorTotal)} (anchor total) ÷ ${fmtTotal(math.chartTotal)} (${name} total)` : "";
    lines.push(["× rescale factor", math.factor.toFixed(3), totalsNote]);
    lines.push(["= rescaled value", fmt(cell.value)]);
    if (cell.gap !== null && Number.isFinite(p.ours)) {
      lines.push(["− our value", fmt(p.ours)]);
      lines.push(["= gap", fmtGap(cell.gap)]);
    } else if (cell.atWaiver) {
      lines.push(["At this chart's waiver line for your league", ""]);
    }
    return {head: null, lines, native: true};
  }
  function showMathTip(owner, p, chart, cell) {
    const tip = $("v2MathTip");
    const info = mathTipLines(p, chart, cell);
    tip.replaceChildren();
    if (info.head) { const h = document.createElement("div"); h.className = "v2-meta"; h.textContent = info.head; tip.appendChild(h); }
    info.lines.forEach(([label, value, note], index) => {
      const row = document.createElement("div");
      row.className = "row";
      const l = document.createElement("span");
      l.textContent = label;
      row.appendChild(l);
      if (value !== "") {
        const v = document.createElement("span");
        v.className = "val";
        if (info.native && index === 0) v.classList.add("is-published");
        v.textContent = value;
        row.appendChild(v);
      }
      tip.appendChild(row);
      if (note) { const n = document.createElement("div"); n.className = "v2-meta v2-tip-note"; n.textContent = note; tip.appendChild(n); }
    });
    const url = sourceUrl(chart, p.row.pos);
    if (url) {
      const a = document.createElement("a");
      a.className = "v2-srclink";
      a.href = url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = `Open ${PUBLISHER_NAMES[chart]} chart ↗`;
      const foot = document.createElement("div");
      foot.className = "v2-meta";
      foot.appendChild(a);
      tip.appendChild(foot);
    }
    tip.hidden = false;
    tip.style.pointerEvents = url ? "auto" : "none";
    const rect = owner.getBoundingClientRect();
    const width = tip.offsetWidth;
    tip.style.left = `${Math.max(8, Math.min(window.innerWidth - width - 8, rect.left))}px`;
    const below = rect.bottom + 8;
    tip.style.top = `${below + tip.offsetHeight > window.innerHeight ? Math.max(8, rect.top - tip.offsetHeight - 8) : below}px`;
    mathTipOwner = owner;
    mathTipOpenedAt = Date.now();
  }
  function hideMathTip() {
    $("v2MathTip").hidden = true;
    mathTipOwner = null;
  }
  // The tip keeps open while the pointer is on it (its link), so the closing waits a beat.
  let mathTipTimer = null;
  function attachPublishedMath(owner, p, chart, cell) {
    owner.tabIndex = 0;
    owner.classList.add("has-math");
    owner.dataset.mathFor = chart;
    owner.setAttribute("aria-describedby", "v2MathTip");
    let openedAt = 0;
    const open = () => { clearTimeout(mathTipTimer); openedAt = Date.now(); showMathTip(owner, p, chart, cell); };
    const close = () => { clearTimeout(mathTipTimer); mathTipTimer = setTimeout(hideMathTip, 150); };
    owner.addEventListener("mouseenter", open);
    owner.addEventListener("mouseleave", close);
    owner.addEventListener("focus", open);
    owner.addEventListener("blur", close);
    owner.addEventListener("click", event => {
      if (event.target.closest("a")) return;
      event.stopPropagation();
      // A tap focuses (which opens it) and then clicks: a click just after opening keeps it open; a later one closes.
      if (mathTipOwner === owner && !$("v2MathTip").hidden && Date.now() - openedAt > 400) hideMathTip(); else open();
    });
    owner.addEventListener("keydown", event => {
      if (event.key === "Escape") hideMathTip();
      if (event.key === "Enter" || event.key === " ") event.stopPropagation();
    });
  }

  function gapNode(cell, tag) {
    const node = document.createElement(tag || "span");
    node.className = `delta gap ${cell.gap > 0 ? "up" : cell.gap < 0 ? "down" : ""}`;
    node.textContent = fmtGap(cell.gap);
    return node;
  }

  function missingNode(reason, short) {
    const span = document.createElement("span");
    span.className = "missing";
    span.title = reason;
    span.textContent = "—";
    const why = document.createElement("span");
    why.className = "why";
    why.textContent = short || reason;
    span.appendChild(why);
    return span;
  }

  // A chart value at or below that chart's waiver line: shown, but no gap.
  function waiverNode(reason) {
    const span = document.createElement("span");
    span.className = "why at-waiver";
    span.title = reason;
    span.textContent = "waiver line";
    return span;
  }

  // JEG-677: the row's gap is the consensus gap (median of the charts - our value); "N of M charts agree"
  // and one dot per chart (above / below our value) say how solid it is.
  // JEG-833: Buy shows the gap at the charts' rank (targets.js rankGap) and both ranks; each side shows the score it is
  // ranked by (gap x value at stake), so the displayed order follows the displayed numbers.
  const targetBest = (side, p) => side === "buy"
    ? {gap: p.market.rankGap, score: p.market.buyScore, ranks: {market: p.market.marketRank, ours: p.market.ourRank, oursAtRank: p.market.oursAtRank},
      agree: p.market.agree, of: p.market.of, dots: p.market.dots}
    : {gap: p.market.gap, score: p.market.score, ranks: null, agree: p.market.agree, of: p.market.of, dots: p.market.dots};
  // The ranking measure under the gap: "score 49" (gap x the smaller of our value and the consensus), and for Buy
  // where the charts rank the player against where we do.
  // full: the phone card (no fold) also prints "RB8→RB5" (the charts rank him RB8, we rank him RB5); the table keeps
  // the run to "score 32.1" so the top 5 stay above the JEG-675 fold, with the ranks in the tooltip and data attributes.
  function scoreNode(side, p, b, cls, full) {
    const node = document.createElement("span");
    node.className = cls || "why t-score";
    node.dataset.score = Number.isFinite(b.score) ? b.score.toFixed(1) : "";
    const stake = Math.min(p.ours, p.market.value);
    node.title = `Ranked by the gap times the value at stake: ${Math.abs(b.gap).toFixed(1)} × ${fmt(stake)} (the smaller of our value and the consensus) = ${b.score.toFixed(1)}`;
    let text = `score ${full ? b.score.toFixed(1) : Math.round(b.score)}`;   // the table rounds: width is what wraps names
    if (side === "buy" && b.ranks) {
      node.dataset.marketRank = String(b.ranks.market);
      node.dataset.ourRank = String(b.ranks.ours);
      const ranks = `${p.row.pos}${b.ranks.market}→${p.row.pos}${b.ranks.ours}`;
      if (full) text = `${ranks} · ${text}`;
      node.title = `${ranks}: the charts rank him ${p.row.pos}${b.ranks.market}, we rank him ${p.row.pos}${b.ranks.ours}; our ${p.row.pos}${b.ranks.market} is worth ${fmt(b.ranks.oursAtRank)} to us, ${fmt(p.ours)} minus that is the gap. ` + node.title;
    }
    node.textContent = text;
    describe(node, node.title);
    return node;
  }
  function agreeNode(b, cls) {
    const who = document.createElement("span");
    who.className = cls || "th-sub t-who";
    who.dataset.agree = String(b.agree);
    who.dataset.of = String(b.of);
    const dots = document.createElement("span");
    dots.className = "t-dots";
    b.dots.forEach(dot => {
      const d = document.createElement("span");
      d.className = `t-dot ${dot.side}`;
      d.dataset.chart = dot.chart;
      d.dataset.dot = dot.side;
      d.dataset.value = String(dot.value);
      d.title = `${PUBLISHER_NAMES[dot.chart]} (rescaled) ${fmt(dot.value)}: ${dot.side === "above" ? "above" : dot.side === "below" ? "below" : "level with"} our value`;
      d.textContent = "●";
      d.setAttribute("role", "img");
      d.setAttribute("aria-label", d.title);
      dots.appendChild(d);
    });
    who.append(document.createTextNode(`${b.agree} of ${b.of} charts agree `), dots);
    return who;
  }

  // One chart's value for a player as a labeled run: "◆ USAT [Wk 4] 17.4 +9.8".
  // Used by the phone cards and by an expanded row in the two-column layout.
  function chartValueSpan(p, key, withNative) {
    const cell = p.cells[key];
    const span = document.createElement("span");
    span.dataset.chart = key;
    const label = document.createElement("span");
    label.className = "lbl";
    label.title = PUBLISHER_NAMES[key];
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.style.color = pubColor(key);
    sym.textContent = `${PUBLISHERS[key].symbol} `;
    label.append(sym, sourceLink(key, PUBLISHERS[key].label, p.row.pos));
    span.appendChild(label);
    const badge = targetBadge(key);
    if (badge) span.appendChild(badge);
    if (cell.value === null) {
      span.appendChild(missingNode(cell.reason, "no value"));
      return span;
    }
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = fmt(cell.value);
    span.appendChild(val);
    attachPublishedMath(val, p, key, cell);
    span.appendChild(cell.atWaiver ? waiverNode(cell.reason) : gapNode(cell));
    appendLowConfidence(span, p.row, key);   // "≈ estimated" when the engine filled it in
    const rank = withNative && typeof C.getNativeRank === "function" ? C.getNativeRank(p.row.player_key, key) : null;
    if (Number.isFinite(rank)) {
      const native = document.createElement("span");
      native.className = "t-native";
      native.dataset.nativeRank = String(rank);
      native.title = `${PUBLISHER_NAMES[key]}'s own rank for this player, before indexing`;
      native.textContent = `#${rank} on ${PUBLISHER_NAMES[key]}`;
      span.appendChild(native);
    }
    return span;
  }

  function renderTargetTable(side, list) {
    const ids = TARGET_IDS[side];
    const table = $(ids.table);
    table.replaceChildren();
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const head = (text, cls, sub, key, info) => {
      const th = document.createElement("th");
      th.scope = "col";
      if (cls) th.className = cls;
      const line = document.createElement("span");
      line.className = "th-line";
      if (key) {
        const sym = document.createElement("span");
        sym.className = "v2-sym";
        sym.style.color = pubColor(key);
        sym.setAttribute("aria-hidden", "true");
        sym.textContent = `${PUBLISHERS[key].symbol} `;
        line.appendChild(sym);
      }
      line.append(key ? sourceLink(key, text) : document.createTextNode(text));
      if (info) line.appendChild(indexedInfoButton(text));
      th.appendChild(line);
      if (sub) {
        const s = document.createElement("span");
        s.className = "th-sub";
        if (typeof sub === "string") s.textContent = sub;
        else s.append(...sub);
        th.appendChild(s);
      }
      if (key) th.dataset.chart = key;
      hr.appendChild(th);
      return th;
    };
    head("Player", "player");
    head("Our value", "num is-rank", window.TradeValueTargets.OUR_SHORT[targetsView.ours]);
    head("Market consensus", "num t-avg", "middle value of the compared charts");
    targetsView.used.forEach(key => {
      // JEG-458: "Wk 5 · rescaled"; a chart on an earlier week shows its badge in place of the week.
      const item = targetsView.infoByKey[key];
      const week = targetBadge(key) || document.createTextNode(item && item.week ? `Week ${item.week}` : "");
      const sub = [week, document.createTextNode(`${week.textContent ? " · " : ""}rescaled`)];
      const flag = divergenceChip(key);
      if (flag) sub.push(document.createTextNode(" "), flag);
      head(PUBLISHER_NAMES[key] || key, "num t-chart", sub, key, true);
    });
    // JEG-833: Buy's gap is our value at the charts' rank minus our value (a pure rescale gives 0).
    if (side === "sell") head("Gap vs consensus", "num t-best", "market pays more", null, true);
    else head("Gap at chart rank", "num t-best", "charts rank lower", null, true);   // as short as Sell's: no extra header line (JEG-675 fold)
    const expandHead = head("", "t-expand");
    const sr = document.createElement("span");
    sr.className = "v2-sr";
    sr.textContent = "Each chart";
    expandHead.appendChild(sr);
    thead.appendChild(hr);
    const columns = hr.children.length;
    const tbody = document.createElement("tbody");
    list.slice(0, T.shown[side]).forEach(p => {
      const key = String(p.row.player_key);
      const tr = document.createElement("tr");
      tr.dataset.playerKey = key;
      makeOpenable(tr, () => openDrawer(p.row, "targets"));
      const td = (cls, text) => {
        const cell = document.createElement("td");
        if (cls) cell.className = cls;
        if (text !== undefined) cell.textContent = text;
        tr.appendChild(cell);
        return cell;
      };
      const name = td("player");
      name.appendChild(nameSpan(p.row));
      appendEspnZero(name, p.row);
      const sub = document.createElement("span");
      sub.className = "player-sub";
      sub.textContent = `${p.row.pos} · ${p.row.team || "Free agent"}`;
      appendFlags(sub, p.row, ` · ${tierText(p.row, targetsView.ours, targetsView.tierScope)}`);   // JEG-892: bye week before the tier
      name.appendChild(subWithTag(sub, p.row));   // beside the sub-line: no taller row (JEG-470)
      const ours = td("num is-rank");
      ours.dataset.ours = "";
      oursValue(ours, p);
      marketValue(td("num t-avg"), p);
      targetsView.used.forEach(chart => {
        const cell = p.cells[chart];
        const c = td("num t-chart");
        c.dataset.chart = chart;
        if (cell.value === null) {
          c.appendChild(missingNode(cell.reason, "no value"));
        } else if (cell.atWaiver) {
          c.append(document.createTextNode(fmt(cell.value)));
          c.appendChild(waiverNode(cell.reason));
        } else {
          c.append(document.createTextNode(fmt(cell.value)));
          c.appendChild(gapNode(cell));
        }
        if (cell.value !== null) appendLowConfidence(c, p.row, chart);   // "≈ estimated"
        attachPublishedMath(c, p, chart, cell);
      });
      const b = targetBest(side, p);
      const bc = td(`num best ${b.gap > 0 ? "up" : "down"}`);
      bc.dataset.best = "consensus";
      bc.append(document.createTextNode(fmtGap(b.gap)));
      bc.appendChild(scoreNode(side, p, b));
      bc.appendChild(agreeNode(b));
      // Two-column layout (≥1024 px) hides the per-chart cells; this opens them under the row.
      const open = T.expanded[side].has(key);
      const ec = td("t-expand");
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "v2-texpand";
      toggle.dataset.expand = key;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", `Each chart's value for ${p.row.name}`);
      const glyph = document.createElement("span");
      glyph.setAttribute("aria-hidden", "true");
      glyph.textContent = open ? "▴" : "▾";
      toggle.appendChild(glyph);
      toggle.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") event.stopPropagation(); });
      toggle.addEventListener("click", event => {
        event.stopPropagation();
        if (T.expanded[side].has(key)) T.expanded[side].delete(key);
        else T.expanded[side].add(key);
        renderTargetTable(side, list);
        const again = $(ids.table).querySelector(`[data-expand="${CSS.escape(key)}"]`);
        if (again) again.focus();
      });
      ec.appendChild(toggle);
      tbody.appendChild(tr);
      if (open) {
        const detail = document.createElement("tr");
        detail.className = "t-detail";
        detail.dataset.detailFor = key;
        const cell = document.createElement("td");
        cell.colSpan = columns;
        const line = document.createElement("div");
        line.className = "vals";
        targetsView.used.forEach(chart => line.appendChild(chartValueSpan(p, chart, true)));
        cell.appendChild(line);
        detail.appendChild(cell);
        tbody.appendChild(detail);
      }
    });
    table.append(thead, tbody);
    rove(table, ":scope > tbody > tr[data-player-key]");
  }

  function renderTargetCards(side, list) {
    const ol = $(TARGET_IDS[side].cards);
    ol.replaceChildren();
    list.slice(0, T.shown[side]).forEach(p => {
      const li = document.createElement("li");
      li.dataset.playerKey = String(p.row.player_key);
      makeOpenable(li, () => openDrawer(p.row, "targets"));
      const top = document.createElement("div");
      top.className = "top";
      const who = document.createElement("div");
      const name = document.createElement("b");
      name.textContent = p.row.name;
      appendEspnZero(name, p.row);
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = `${p.row.pos} · ${p.row.team || "Free agent"}`;
      appendFlags(sub, p.row, ` · ${tierText(p.row, targetsView.ours, targetsView.tierScope)}`);   // JEG-892: bye week before the tier
      who.append(name, subWithTag(sub, p.row));   // beside the sub-line: no taller row (JEG-470)
      const b = targetBest(side, p);
      const big = document.createElement("div");
      big.className = `big ${b.gap > 0 ? "up" : "down"}`;
      big.dataset.best = "consensus";
      big.append(document.createTextNode(fmtGap(b.gap)));
      big.appendChild(scoreNode(side, p, b, "v2-meta t-score", true));
      big.appendChild(agreeNode(b, "v2-meta t-who"));
      top.append(who, big);
      const line = document.createElement("div");
      line.className = "vals";
      const ours = document.createElement("span");
      ours.className = "ours";
      ours.dataset.ours = "";
      ours.append(document.createTextNode("Ours "));
      oursValue(ours, p);
      line.appendChild(ours);
      const avg = document.createElement("span");
      avg.className = "avg";
      if (!p.market.equal) avg.append(document.createTextNode("Consensus "));
      marketValue(avg, p);
      line.appendChild(avg);
      targetsView.used.forEach(key => line.appendChild(chartValueSpan(p, key)));
      li.append(top, line);
      ol.appendChild(li);
    });
    rove(ol, "li[data-player-key]");
  }

  // JEG-461: each list opens on its top 5; "Show all N" then pages of 25; "Show top 5" collapses.
  function renderTargetFoot(side, list) {
    const ids = TARGET_IDS[side];
    const more = $(ids.more);
    const less = $(ids.less);
    const shown = Math.min(T.shown[side], list.length);
    const label = text => {
      const arrow = document.createElement("span");
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = " ▾";
      more.replaceChildren(document.createTextNode(text), arrow);
    };
    more.hidden = list.length <= shown;
    less.hidden = T.shown[side] <= TARGETS_TOP || list.length <= TARGETS_TOP;
    // JEG-910: "Show all N" only when the first page (TARGETS_PAGE) does reveal all N; otherwise the label counts.
    if (T.shown[side] <= TARGETS_TOP) label(list.length <= TARGETS_PAGE ? `Show all ${list.length} ${side} targets` : `Show more (${shown} of ${list.length})`);
    else label(`Show more (${shown} of ${list.length})`);
    more.setAttribute("aria-controls", `${ids.table} ${ids.cards}`);
  }

  // JEG-911: a search that matches no name says so (with Clear search), never a list's own "no player…" copy.
  function renderNoMatch(empty, query, inputId) {
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "v2-link";
    clear.textContent = "Clear search";
    clear.addEventListener("click", () => {
      const input = $(inputId);
      input.value = "";
      input.dispatchEvent(new Event("input", {bubbles: true}));
      input.focus();
    });
    empty.replaceChildren(document.createTextNode(`No player matches “${query.trim()}”. `), clear);
  }

  // JEG-888: "N trade charts" from the compared set, singular when one.
  const tradeChartCount = n => `${n} trade chart${n === 1 ? "" : "s"}`;

  function renderTargets() {
    collect();
    collectTargets();
    renderHeader();
    renderUnpriced("v2TUnpriced", T.search);
    renderTargetControls();
    const blocked = targetsView.blocked;
    const noCharts = !targetsView.used.length;
    // JEG-851: single-chart mode changes text throughout.
    const sc = targetsView.singleChart;
    const scName = sc ? (PUBLISHER_NAMES[sc] || sc) : null;
    // JEG-868: with a trade chart as Our value, the compared charts are "the other charts".
    const oursIsChart = window.TradeValueTargets.CHART_KEYS.includes(targetsView.ours);
    const chartsWord = oursIsChart ? "the other charts" : "the charts";
    // JEG-888: the intro counts the charts this view actually compares (held and skipped charts, and our own
    // chart, are not in `used`), so it never says "four" in a three-chart week.
    const introCount = targetsView.used.length;
    const introCharts = !introCount ? "the trade charts" : sc ? `${tradeChartCount(1)} (${scName})` : tradeChartCount(introCount);
    $("v2TIntro").textContent = `We check ${introCharts} against our values for your league, two ways: potential mispricing, player by player, and the positions the market overpays for, position by position. Sell what they overpay for; buy what they undervalue.`;
    let renderError = null;
    TARGET_SIDES.forEach(side => {
      const ids = TARGET_IDS[side];
      const list = targetsView[side];
      // JEG-869: the heading names the one chart when one is compared ("against one chart: <name>"),
      // and the sub-line leads with the same phrase, so the copy never claims a market of 2+ charts.
      const title = $(ids.section === "v2TSell" ? "v2TSellTitle" : "v2TBuyTitle");
      const arrow = title.querySelector("[aria-hidden]") || document.createElement("span");
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = side === "sell" ? "▲" : "▼";
      title.replaceChildren(arrow, document.createTextNode(sc
        ? (side === "sell" ? ` Sell: ${scName} pays more than we would` : ` Buy: ${scName} pays less than we would`)
        : (side === "sell" ? ` Sell: ${chartsWord} pay more than we would` : ` Buy: ${chartsWord} pay less than we would`)));
      // JEG-868: a list is never left showing the previous selection. If rendering throws, that list is
      // cleared and says so; the error is rethrown after both lists are handled so it stays visible.
      try {
        renderTargetTable(side, list);
        renderTargetCards(side, list);
        renderTargetFoot(side, list);
      } catch (error) {
        $(ids.table).replaceChildren();
        $(ids.cards).replaceChildren();
        $(ids.more).hidden = true;
        $(ids.less).hidden = true;
        $(ids.table).hidden = true;
        const empty = $(ids.empty);
        empty.hidden = false;
        empty.textContent = `This list could not be built for this selection (${error && error.message ? error.message : error}).`;
        $(ids.meta).textContent = "—";
        renderError = renderError || error;
        return;
      }
      const empty = $(ids.empty);
      empty.hidden = !(blocked || noCharts || !list.length);
      if (!blocked && !noCharts && targetsView.searchMiss) renderNoMatch(empty, T.search, "v2TSearch");
      else empty.textContent = blocked || (noCharts
        ? "No trade chart is available to compare for this selection."
        : sc
          ? (side === "sell" ? `No player ${scName} values above our value for this selection.`
            : `No player ${scName} ranks ${window.TradeValueTargets.BUY_RANK_MARGIN.toFixed(1)} points or more below where we rank him for this selection.`)
          : (side === "sell" ? `No player has a market consensus above our value, backed by 2 or more of ${chartsWord}, for this selection.`
            : `No player ${chartsWord} rank ${window.TradeValueTargets.BUY_RANK_MARGIN.toFixed(1)} points or more below where we rank him, backed by 2 or more charts, for this selection.`));
      $(ids.table).hidden = !list.length;
      // JEG-820 / JEG-833: each list is ranked by the gap it shows times the value at stake (the score on every row).
      // JEG-851: single-chart mode uses chart-specific language, not "most charts".
      const actionCopy = sc
        ? (side === "sell" ? `Against one chart: ${scName}. ${scName} pays more than our value.` : `Against one chart: ${scName}. ${scName} ranks them lower than we do.`)
        : (side === "sell" ? `Offer them: most of ${chartsWord} pay more than our value.` : `Ask for them: ${chartsWord} rank them lower than we do.`);
      $(ids.meta).textContent = blocked ? "—" : `${list.length} players · ranked by gap × value at stake, biggest score first. ${actionCopy}`;
    });
    const notes = [];
    // JEG-833: players the charts price below our value but rank where we do are the scale, not a mispricing.
    if (targetsView.scaleOnly && !blocked) {
      const n = targetsView.scaleOnly;
      const names = targetsView.scaleOnlyNames.join(", ");
      notes.push(`${n} player${n === 1 ? "" : "s"} the charts price below our value ${n === 1 ? "is" : "are"} not a Buy: the charts rank ${n === 1 ? "him" : "them"} where we do, so the gap is our steeper scale, not a mispricing${names ? ` (${names}${n > 5 ? " ..." : ""})` : ""}.`);
    }
    // JEG-842: otherwise-listed players that are out (ESPN zero) or rest on an estimated chart value are not recommended.
    if (targetsView.leftOut && !blocked) {
      const n = targetsView.leftOut;
      notes.push(`${n} player${n === 1 ? "" : "s"} left out: out this week or estimated (${targetsView.leftOutNames.join(", ")}${n > 5 ? " ..." : ""}). A player ESPN has at 0, or a chart value filled in from other charts, is not a basis to trade on.`);
    }
    // JEG-1186 (Jeremy, 2026-10-27: "Suppress"): a DDF Value backed by fewer than 2 sources gets no Buy/Sell call.
    if (targetsView.thinSource && !blocked) {
      const n = targetsView.thinSource;
      notes.push(`${n} player${n === 1 ? "" : "s"} left off Buy and Sell: only 1 source backs ${n === 1 ? "his" : "their"} DDF Value (${targetsView.thinSourceNames.join(", ")}${n > 5 ? " ..." : ""}). A Buy or Sell call needs at least 2.`);
    }
    // JEG-820: the players the charts pay for but we value under the Sell floor are drop candidates, not trade chips.
    if (targetsView.belowSellFloor && !blocked) {
      const n = targetsView.belowSellFloor;
      notes.push(`${n} player${n === 1 ? "" : "s"} the charts pay more for than we do ${n === 1 ? "is" : "are"} left off Sell: we value ${n === 1 ? "him" : "them"} under ${window.TradeValueTargets.SELL_FLOOR.toFixed(1)}, a drop or hold, not a trade chip.`);
    }
    // JEG-820 / JEG-807: a listed player whose DDF Value rests on one source gets an honest note, no verdict language.
    if (!blocked && isDdfKey(targetsView.ours)) {
      const listed = targetsView.sell.concat(targetsView.buy);
      const thin = listed.filter(p => isLowConfidence(p.row, targetsView.ours)).length;
      if (thin) notes.push(`${sourceMeta(targetsView.ours).label} rests on one source for ${thin} of the ${listed.length} listed player${listed.length === 1 ? "" : "s"} (◐): read those gaps as leads to check, not verdicts.`);
    }
    if (targetsView.skipped.length) {
      notes.push(`Not compared: ${targetsView.skipped.map(s => `${PUBLISHER_NAMES[s.key]}, ${s.reason}`).join("; ")}.`);
    }
    if (targetsView.omittedNoOurs) {
      const why = targetsView.omittedReasons.map(([reason, n]) => `${reason} (${n})`).join("; ");
      notes.push(`${targetsView.omittedNoOurs} player${targetsView.omittedNoOurs === 1 ? "" : "s"} left out: we have no ${isDdfKey(targetsView.ours) ? sourceMeta(targetsView.ours).label : `${window.TradeValueTargets.OUR_SHORT[targetsView.ours]} value`} for them${why ? `. Why: ${why}` : ""}.`);
    }
    if (targetsView.atWaiverCells && !blocked) {
      notes.push("A chart value of 0.0 is at that chart's waiver line for your league: never a buy, no gap.");
    }
    // JEG-609: a compared chart that disagrees with the others more than usual, said once above the lists
    // (the per-chart columns are folded away in the two-column layout). It never removes the chart.
    const flags = $("v2TDivergence");
    flags.replaceChildren();
    targetsView.used.forEach(key => {
      const chip = divergenceChip(key);
      if (!chip) return;
      const line = document.createElement("span");
      line.className = "v2-tdiv-item";
      // JEG-1042 (Jeremy, 2026-10-24: chips side by side): chip + source name on one line; the explanation is the
      // chip's hover text and accessible name, so each linked chip keeps its own 44 px target.
      line.append(chip, document.createTextNode(` ${PUBLISHER_NAMES[chip.dataset.divergence] || chip.dataset.divergence}`));
      flags.appendChild(line);
    });
    flags.hidden = !flags.childNodes.length;
    const note = $("v2TNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
    // The footnote follows the picked series: DDF Value is built from the chosen inputs; a projection
    // series is that publisher's projections with our Data Driven Adjustments.
    const chartLink = $("v2TChartLink");
    chartLink.replaceChildren();
    if (T.chart !== "all" && sourceUrl(T.chart)) {
      const link = sourceLink(T.chart, `Open ${PUBLISHER_NAMES[T.chart]} chart ↗`);
      link.classList.add("v2-srclink-open");
      chartLink.appendChild(link);
    }
    // JEG-1073: DDF Value is the Adjusted trade charts averaged; the projections version is the alternate.
    $("v2TOursNote").textContent = isDdfKey(targetsView.ours)
      ? `${targetsView.ours === DDF_KEY ? "DDF Value" : sourceMeta(targetsView.ours).label}, ${targetsView.ours === DDF_KEY ? basisPhrase() : "rooted in projected points, averaged for your league"}`
      : `${window.TradeValueTargets.OUR_NAMES[targetsView.ours]}${window.TradeValueTargets.CHART_KEYS.includes(targetsView.ours) ? " (rescaled)" : " with Data Driven Adjustments"}`;
    // JEG-851: rewrite the footnote lead-in for single-chart mode.
    const footEl = $("v2TFootnote");
    const oursSpan = $("v2TOursNote");
    const priorSpan = $("v2TPriorNote");
    if (sc) {
      // Rebuild: "Gap = <chart>'s rescaled value − our value ... against one chart: <name>."
      footEl.textContent = "";
      footEl.append(
        document.createTextNode(`Gap = ${scName}'s rescaled value − our value for the same player, both in your league's trade-value points. Our value is `),
        oursSpan,
        document.createTextNode(`; the chart is rescaled to the same point scale. Against one chart: ${scName}. `),
        priorSpan,
        document.createTextNode("Value above waivers is a different unit and is never mixed in. Every value is above your league's waiver line, so 0.0 means at or below it: such a player is never a buy target. A missing value shows —, never zero."));
    } else if (footEl.firstChild && footEl.firstChild.nodeType === 3 && !footEl.firstChild.textContent.startsWith("Gap = market consensus")) {
      // Restore the multi-chart footnote if previously in single-chart mode.
      footEl.textContent = "";
      footEl.append(
        document.createTextNode("Gap = market consensus (the middle value of the compared charts; the Trade chart average is their mean) − our value for the same player, both in your league's trade-value points. Our value is "),
        oursSpan,
        document.createTextNode("; each trade chart is rescaled to the same point scale. A player is listed only when 2 or more charts price him and most of them sit on the same side of our value. "),
        priorSpan,
        document.createTextNode("Value above waivers is a different unit and is never mixed in. Every value is above your league's waiver line, so 0.0 means at or below it: such a player is never a buy target. A missing value shows —, never zero."));
    }
    // Footnote: each compared chart that is still on an earlier week, with its badge.
    const priorNote = priorSpan;
    priorNote.replaceChildren();
    targetsView.prior.filter(key => targetsView.used.includes(key)).forEach(key => {
      const badge = targetBadge(key);
      if (!badge) return;
      priorNote.append(document.createTextNode(`${priorWeekInfo(key, targetsView.infoByKey[key], targetsView.refWeek).label} `));
    });
    renderWeightCheck();
    if (renderError) throw renderError;   // JEG-868: shown as an empty state above; still an error, not hidden
  }

  // ---------- Check 2: potential positional weight inflation (JEG-476, JEG-489) ----------
  // All numbers come from TradeValueTargets.weightCheck over the engine's rows (DDF Value against the
  // consensus and each chart, grouped by position and by DDF starter / bench tier). Nothing is computed here.
  const WEIGHT_SIGNAL_TEXT = {sell: ["▲", "Sell this group"], buy: ["▼", "Buy this group"], fair: ["●", "Fairly priced"]};
  const WEIGHT_TIER_TEXT = {starter: "Starters", bench: "Bench"};
  const weightOpen = new Set();
  const fmtPct = gap => {
    if (!Number.isFinite(gap)) return "—";
    const text = Math.abs(gap * 100).toFixed(0);
    return text === "0" ? "0%" : `${gap > 0 ? "+" : "−"}${text}%`;
  };
  const weightGroupName = group => group.tier ? `${group.pos} ${WEIGHT_TIER_TEXT[group.tier].toLowerCase()}` : group.pos;
  const weightHeat = gap => {
    if (!Number.isFinite(gap)) return "";
    const size = Math.abs(gap);
    const step = size >= 0.20 ? 3 : size >= 0.10 ? 2 : size >= 0.05 ? 1 : 0;
    return step ? ` h-${gap > 0 ? "up" : "down"}-${step}` : "";
  };

  function weightHeadline(result) {
    const h = result.headline;
    const pct = g => `${Math.abs(g.consensus.gap * 100).toFixed(0)}%`;
    if (!h.over && !h.under) return "No group of 8 or more players is priced differently from DDF Value by the consensus.";
    const parts = [];
    if (h.over) parts.push(`the consensus prices ${weightGroupName(h.over)} ${pct(h.over)} above DDF Value (${h.over.consensus.n} players)`);
    if (h.under) parts.push(`${h.over ? "and " : "the consensus prices "}${weightGroupName(h.under)} ${pct(h.under)} below it (${h.under.consensus.n} players)`);
    const lead = h.over && h.under ? "Biggest pricing gap between two groups: " : "Largest group gap: ";
    return `${lead}${parts.join(" ")}.`;
  }

  function signalChip(signal) {
    const chip = document.createElement("span");
    chip.className = `v2-wsignal is-${signal}`;
    chip.dataset.signal = signal;
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = `${WEIGHT_SIGNAL_TEXT[signal][0]} `;
    chip.append(sym, document.createTextNode(WEIGHT_SIGNAL_TEXT[signal][1]));
    return chip;
  }

  function renderWeightCheck() {
    const TT = window.TradeValueTargets;
    const table = $("v2WeightTable");
    const empty = $("v2WeightEmpty");
    const headline = $("v2WeightHeadline");
    table.replaceChildren();
    const ours = targetsView.infoByKey[DDF_KEY];
    const reason = !ours || !ours.available ? "DDF Value is not available for this league right now."
      : targetsView.blocked ? targetsView.blocked
      : !targetsView.used.length ? "No trade chart is available to compare for this selection." : null;
    empty.hidden = !reason;
    empty.textContent = reason || "";
    table.parentElement.hidden = Boolean(reason);
    if (reason) { headline.textContent = ""; return; }
    const charts = targetsView.used;
    const result = TT.weightCheck(C.getAllRows(), charts, {ours: DDF_KEY});
    headline.textContent = weightHeadline(result);
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const th = (text, cls) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      if (cls) cell.className = cls;
      cell.textContent = text;
      hr.appendChild(cell);
      return cell;
    };
    th("Group", "player");
    th("Players", "num");
    th("Consensus gap", "num");
    th("Signal");
    charts.forEach(key => { const cell = th(PUBLISHER_NAMES[key] || key, "num t-chart"); cell.dataset.chart = key; });
    const expand = th("", "t-expand");
    const sr = document.createElement("span");
    sr.className = "v2-sr";
    sr.textContent = "Players";
    expand.appendChild(sr);
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    result.groups.forEach(group => {
      const tr = document.createElement("tr");
      tr.dataset.group = group.key;
      tr.className = group.tier ? "is-tier" : "is-pos";
      const td = (cls, text) => {
        const cell = document.createElement("td");
        if (cls) cell.className = cls;
        if (text !== undefined) cell.textContent = text;
        tr.appendChild(cell);
        return cell;
      };
      td("player", group.tier ? WEIGHT_TIER_TEXT[group.tier] : group.pos);
      td("num", String(group.n));
      const gapCell = td(`num w-gap${weightHeat(group.consensus.gap)}`, group.consensus.gap === null ? "—" : fmtPct(group.consensus.gap));
      gapCell.dataset.gap = group.consensus.gap === null ? "" : String(group.consensus.gap);
      if (group.consensus.gap === null) gapCell.title = group.n ? `Only ${group.n} player${group.n === 1 ? "" : "s"} in this group are priced by both sides; at least ${TT.WEIGHT_MIN_SHOW} are needed.` : "No players in this group are priced by both sides.";
      const signalCell = td("w-signal");
      if (group.consensus.signal) signalCell.appendChild(signalChip(group.consensus.signal));
      charts.forEach(chart => {
        const cell = group.cells[chart];
        const c = td(`num t-chart w-gap${weightHeat(cell.gap)}`, cell.gap === null ? "—" : fmtPct(cell.gap));
        c.dataset.chart = chart;
        if (cell.gap !== null) c.dataset.gap = String(cell.gap);
      });
      const open = weightOpen.has(group.key);
      const ec = td("t-expand");
      if (group.n) {
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "v2-texpand";
        toggle.dataset.weightExpand = group.key;
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", `Players in ${weightGroupName(group)}`);
        const glyph = document.createElement("span");
        glyph.setAttribute("aria-hidden", "true");
        glyph.textContent = open ? "▴" : "▾";
        toggle.appendChild(glyph);
        toggle.addEventListener("click", () => {
          if (weightOpen.has(group.key)) weightOpen.delete(group.key); else weightOpen.add(group.key);
          renderWeightCheck();
          const again = table.querySelector(`[data-weight-expand="${CSS.escape(group.key)}"]`);
          if (again) again.focus();
        });
        ec.appendChild(toggle);
      }
      tbody.appendChild(tr);
      if (open) {
        const detail = document.createElement("tr");
        detail.className = "t-detail w-detail";
        detail.dataset.detailFor = group.key;
        const cell = document.createElement("td");
        cell.colSpan = hr.children.length;
        const wrap = document.createElement("div");
        wrap.className = "v2-table-wrap";
        const inner = document.createElement("table");
        inner.className = "v2-table v2-wplayers";
        const ih = document.createElement("tr");
        ["Player", "DDF Value", "Consensus", "Gap"].concat(charts.map(key => PUBLISHER_NAMES[key] || key)).forEach((label, index) => {
          const h = document.createElement("th");
          h.scope = "col";
          h.className = index ? "num" : "player";
          h.textContent = label;
          ih.appendChild(h);
        });
        const ibody = document.createElement("tbody");
        result.playersOf(group).forEach(p => {
          const row = document.createElement("tr");
          row.dataset.playerKey = String(p.row.player_key);
          const cells = [p.row.name, fmt(p.ours), fmt(p.market), fmtGap(p.gap)].concat(charts.map(key => fmt(p.charts[key])));
          cells.forEach((text, index) => {
            const c = document.createElement("td");
            c.className = index ? "num" : "player";
            c.textContent = text;
            row.appendChild(c);
          });
          makeOpenable(row, () => openDrawer(p.row, "targets"));
          ibody.appendChild(row);
        });
        const head = document.createElement("thead");
        head.appendChild(ih);
        inner.append(head, ibody);
        rove(inner, ":scope > tbody > tr[data-player-key]");
        wrap.appendChild(inner);
        cell.appendChild(wrap);
        detail.appendChild(cell);
        tbody.appendChild(detail);
      }
    });
    table.append(thead, tbody);
  }

  function bindTargets() {
    let timer = null;
    const resetLists = () => {
      T.shown = {sell: TARGETS_TOP, buy: TARGETS_TOP};
      T.expanded = {sell: new Set(), buy: new Set()};
    };
    $("v2TSearch").addEventListener("input", event => {
      clearTimeout(timer);
      timer = setTimeout(() => { T.search = event.target.value; resetLists(); renderTargets(); }, 120);
    });
    $("v2TPosition").addEventListener("change", event => { C.setPosition(event.target.value); resetLists(); renderTargets(); });
    $("v2TChart").addEventListener("change", event => { T.chart = event.target.value; resetLists(); renderTargets(); });
    $("v2NamesInfoSlot").replaceWith(namesInfoButton("On the chart"));
    $("v2RNamesInfoSlot").replaceWith(namesInfoButton("Change"));
    $("v2RDisagreeInfoSlot").replaceWith(namesInfoButton("Mixed signals"));
    $("v2TOurs").addEventListener("change", event => {
      T.ours = event.target.value;
      saveTargetsOurs(T.ours);
      resetLists();
      renderTargets();
    });
    $("v2TChartInfoSlot").replaceWith(indexedInfoButton("Compare against"));
    TARGET_SIDES.forEach(side => {
      const ids = TARGET_IDS[side];
      // Keep focus on a control that is still on screen after the list redraws.
      const refocus = () => ($(ids.more).hidden ? $(ids.less) : $(ids.more)).focus();
      $(ids.more).addEventListener("click", () => {
        T.shown[side] = T.shown[side] <= TARGETS_TOP ? TARGETS_PAGE : T.shown[side] + TARGETS_PAGE;
        renderTargets();
        refocus();
      });
      $(ids.less).addEventListener("click", () => {
        T.shown[side] = TARGETS_TOP;
        T.expanded[side] = new Set();
        renderTargets();
        const section = $(ids.section);
        if (section.getBoundingClientRect().top < 0) section.scrollIntoView({block: "start"});
        refocus();
      });
    });
  }

  // ---------- Compare a trade (frames 07 / 08, 24) ----------
  // Each row is one exact series: sum(receive) − sum(give) in that series'
  // values (app/v2/trade.js). No blended score (frame 22); the verdict reads one
  // series (JEG-469). The sides are v2 module state, so they survive switching tabs.
  // give/receive: [{key, name}]. example: the keys "Try a sample trade" loaded, while the trade is still exactly that
  // sample (JEG-1190). undo: the sides before the last Clear.
  const TR = {give: [], receive: [], shown: null, open: new Set(), example: null, undo: null};
  // Compare's team choice is view state. The saved league remains the source of truth;
  // trying a trade never moves players between its stored rosters.
  const compareTeams = {mineId: null, theirId: null, mineChosen: false, theirChosen: false, editing: false, snapshot: null, carriedSwapped: false};
  function endCompareEdit() {
    compareTeams.snapshot = null;
    compareTeams.editing = false;
  }
  // JEG-1259: a trade that arrived with its own context (tc=, TradeValueTradeContext): its rosters, deal, settings, value
  // basis, sources and bench level. While it is pending Compare prices exactly those rosters, or holds and says why;
  // it never substitutes this reader's saved teams and never writes them. Choosing a team ends it.
  let carriedTrade = null;    // {text, transfer} from the address
  let compareCarried = null;  // receive()'s result for this render
  function receiveCarried() {
    if (!carriedTrade) return null;
    const TC = window.TradeValueTradeContext;
    const held = detail => ({status: "hold", reasons: [{code: "context-unreadable", where: "transfer", detail}]});
    if (!TC) return held("this page cannot read a carried trade");
    if (!carriedTrade.transfer) return held("the trade context in this link could not be read");
    const t = carriedTrade.transfer;
    const keys = TC.pricingKeys({mine: t.mine && t.mine.roster, theirs: t.theirs && t.theirs.roster, deal: t.deal});
    const common = TC.commonFromPage({leagueQuery: leagueLinkParts().join("&"),
      valueContext: window.DDFOverrides && window.DDFOverrides.snapshotContext ? window.DDFOverrides.snapshotContext() : null,
      sources: TC.sourcesFromEngine(C.getSourceInfo())});
    try {
      // Compare prices the modeled bench on this build; a trade priced at another level is held, never repriced here.
      return TC.receive(t, {route: "compare", common, pricing: TC.modeledPricing(C, keys), ws: window.TradeValueWorkspace?.store?.get() || null});
    } catch (error) { return held("the trade context in this link could not be read"); }
  }
  function carriedHoldText(result) {
    const why = result.reasons.map(r => r.detail).filter(Boolean).slice(0, 3).join("; ");
    return `This trade arrived with its own rosters and values, but this page would price it differently (${why}). Lineup changes are held; choose teams above to price it with this page's settings.`;
  }
  let compareView = null;
  // JEG-467 (Jeremy, 2026-10-08): the verdict is by DDF Value. Whenever DDF Value is shown and
  // available it decides the verdict, whatever "Player values shown" picks; the picker drives the
  // side cards' values and totals. With DDF Value not shown, the verdict reads the picked series.
  let verdictSeries = null;
  const verdictKey = () => verdictSeries;
  // Compare tiers: rank by the verdict series over every priced player, against the All-positions zones.
  let compareTierRows = null;
  function compareTierScope() {
    if (!compareTierRows) compareTierRows = C.getAllRows();
    return {rows: compareTierRows, pos: "ALL", engineOrder: false};
  }
  let exampleCache = null;   // {signature, pick}: the sample trade "Try a sample trade" loads
  const SIDE_IDS = {give: {search: "v2GiveSearch", results: "v2GiveResults", list: "v2GivePlayers", total: "v2GiveTotal"},
    receive: {search: "v2GetSearch", results: "v2GetResults", list: "v2GetPlayers", total: "v2GetTotal"}};
  const SIDE_NAME = {give: "You give", receive: "You receive"};

  function compareRosterContext() {
    const store = window.TradeValueWorkspace?.store;
    const ws = store?.get();
    if (!ws) return {teams: [], mine: null, theirs: null, ready: false};
    const teams = ws.teams || [];
    if (compareCarried && compareCarried.status === "hold") {
      // Held: no team is shown as chosen, so nothing reads as priced on this reader's saved rosters.
      Object.assign(compareTeams, {mineId: null, theirId: null, mineChosen: false, theirChosen: false});
      return {teams, mine: null, theirs: null, ready: false, held: compareCarried};
    }
    if (compareCarried && compareCarried.status === "ok") {
      // The carried rosters are authoritative; a saved team they exactly match keeps its option in the pickers.
      const shown = (team, side) => ({id: team.id || `carried-${side}`, name: team.name || (side === "mine" ? "Your team (from the link)" : "Their team (from the link)"),
        entries: team.roster.map(e => ({...e})), carried: true});
      const sides = [compareCarried.context.teams.mine, compareCarried.context.teams.theirs];
      if (compareTeams.carriedSwapped) sides.reverse();   // Swap exchanges the carried rosters too
      const mine = shown(sides[0], "mine");
      const theirs = shown(sides[1], "theirs");
      compareTeams.mineId = mine.id;
      compareTeams.theirId = theirs.id;
      const list = teams.map(t => (t.id === mine.id ? mine : t.id === theirs.id ? theirs : t));
      [mine, theirs].forEach(t => { if (!list.includes(t)) list.push(t); });
      return {teams: list, mine, theirs, ready: Boolean(mine.entries.length && theirs.entries.length), carried: compareCarried.context};
    }
    if (!compareTeams.mineChosen && !compareTeams.mineId) compareTeams.mineId = ws.myTeamId || null;
    if (!compareTeams.theirChosen && !compareTeams.theirId)
      compareTeams.theirId = teams.find(t => t.id !== compareTeams.mineId && t.entries.length)?.id || null;
    if (compareTeams.mineId && !teams.some(t => t.id === compareTeams.mineId)) { compareTeams.mineId = ws.myTeamId || null; compareTeams.mineChosen = false; }
    if ((compareTeams.theirId && !teams.some(t => t.id === compareTeams.theirId)) || (compareTeams.theirId && compareTeams.theirId === compareTeams.mineId)) {
      compareTeams.theirId = teams.find(t => t.id !== compareTeams.mineId && t.entries.length)?.id || null;
      compareTeams.theirChosen = false;
    }
    const mine = teams.find(t => t.id === compareTeams.mineId) || null;
    const theirs = teams.find(t => t.id === compareTeams.theirId) || null;
    const ready = Boolean(mine?.entries.length && theirs?.entries.length && mine.id !== theirs.id);
    return {teams, mine, theirs, ready};
  }

  function compareRosterRows(team) {
    return (team?.entries || []).map(e => compareView.rowsByKey.get(e.key)).filter(Boolean);
  }

  function compareRosterMembership(ctx) {
    const own = new Set((ctx.mine?.entries || []).map(e => e.key));
    const other = new Set((ctx.theirs?.entries || []).map(e => e.key));
    return TR.give.every(p => own.has(p.key)) && TR.receive.every(p => other.has(p.key));
  }

  function renderCompareRosterPicker() {
    const card = $("v2CRosters");
    const host = $("v2CRostersBody");
    const ctx = compareRosterContext();
    const options = (selected, side) => {
      const select = document.createElement("select");
      select.id = side === "give" ? "v2CMyTeam" : "v2CTheirTeam";
      select.setAttribute("aria-label", side === "give" ? "Your team" : "Their team");
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Choose a team";
      select.appendChild(blank);
      ctx.teams.forEach(team => {
        const option = document.createElement("option");
        option.value = team.id;
        option.textContent = `${team.name} (${team.entries.length})`;
        option.disabled = team.id === (side === "give" ? compareTeams.theirId : compareTeams.mineId);
        select.appendChild(option);
      });
      select.value = selected || "";
      select.addEventListener("change", () => {
        if (carriedTrade) {
          // Choosing a team ends the carried trade; the other side keeps the roster it showed only if it is a saved team.
          const keep = id => (id && ctx.teams.some(t => t.id === id && !String(id).startsWith("carried-")) ? id : null);
          compareTeams.mineId = keep(compareTeams.mineId);
          compareTeams.theirId = keep(compareTeams.theirId);
          compareTeams.mineChosen = Boolean(compareTeams.mineId);
          compareTeams.theirChosen = Boolean(compareTeams.theirId);
          carriedTrade = null;
          compareCarried = null;
          compareTeams.carriedSwapped = false;
        }
        if (side === "give") { compareTeams.mineId = select.value || null; compareTeams.mineChosen = true; }
        else { compareTeams.theirId = select.value || null; compareTeams.theirChosen = true; }
        TR.example = null;
        renderCompare();
        $(select.id).focus();
      });
      return select;
    };
    const field = (label, select) => {
      const node = document.createElement("label");
      node.className = "v2-croster-field";
      const title = document.createElement("span");
      title.textContent = label;
      node.append(title, select);
      return node;
    };
    const intro = document.createElement("p");
    intro.className = "v2-meta";
    intro.textContent = "Choose two loaded rosters, then add or remove players to test a trade. Your saved rosters stay as they are.";
    const controls = document.createElement("div");
    controls.className = "v2-croster-controls";
    controls.append(field("Your team", options(compareTeams.mineId, "give")), field("Their team", options(compareTeams.theirId, "receive")));
    const actions = document.createElement("div");
    actions.className = "v2-croster-actions";
    if (ctx.ready) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "v2-link";
      edit.id = "v2CEditRosters";
      edit.textContent = compareTeams.editing ? "Back to trade" : "Edit players from rosters";
      edit.setAttribute("aria-expanded", String(compareTeams.editing));
      edit.setAttribute("aria-controls", "v2CRosterLists");
      edit.addEventListener("click", () => {
        if (!compareTeams.editing) compareTeams.snapshot = {give: TR.give.slice(), receive: TR.receive.slice(), example: TR.example,
          undo: TR.undo, mineId: compareTeams.mineId, theirId: compareTeams.theirId,
          mineChosen: compareTeams.mineChosen, theirChosen: compareTeams.theirChosen, carriedSwapped: compareTeams.carriedSwapped,
          carriedTrade};   // JEG-1285: Cancel brings back a carried trade that a team choice ended
        else compareTeams.snapshot = null;
        compareTeams.editing = !compareTeams.editing;
        renderCompare();
        $("v2CEditRosters")?.focus();
      });
      actions.appendChild(edit);
      if (compareTeams.editing && compareTeams.snapshot) {
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "v2-link";
        cancel.id = "v2CCancelRosterEdit";
        cancel.textContent = "Cancel edits";
        cancel.addEventListener("click", () => {
          ({give: TR.give, receive: TR.receive, example: TR.example, undo: TR.undo} = compareTeams.snapshot);
          ({mineId: compareTeams.mineId, theirId: compareTeams.theirId,
            mineChosen: compareTeams.mineChosen, theirChosen: compareTeams.theirChosen, carriedSwapped: compareTeams.carriedSwapped} = compareTeams.snapshot);
          carriedTrade = compareTeams.snapshot.carriedTrade || null;
          compareCarried = null;
          endCompareEdit();
          renderCompare();
          $("v2CEditRosters")?.focus();
        });
        actions.appendChild(cancel);
      }
    }
    const status = document.createElement("p");
    status.className = "v2-meta";
    status.id = "v2CRosterStatus";
    status.setAttribute("role", "status");
    status.textContent = ctx.held ? carriedHoldText(ctx.held)
      : !ctx.ready ? "Add two rosters in Your league to see lineup and roster fit here."
      : !compareRosterMembership(ctx) ? "This trade includes players outside the selected rosters. Choose players from those rosters to see lineup changes."
      : "Select players from either roster below. Values and lineups update after each change.";
    const lists = document.createElement("div");
    lists.className = "v2-croster-lists";
    lists.id = "v2CRosterLists";
    lists.hidden = !compareTeams.editing;
    if (ctx.ready) [["give", ctx.mine], ["receive", ctx.theirs]].forEach(([side, team]) => {
      const section = document.createElement("section");
      section.setAttribute("aria-label", `${team.name} roster`);
      const heading = document.createElement("h3");
      heading.textContent = `${team.name} · ${side === "give" ? "You give" : "You receive"}`;
      const list = document.createElement("ul");
      list.className = "v2-croster-list";
      team.entries.forEach(entry => {
        const row = compareView.rowsByKey.get(entry.key);
        const selected = TR[side].some(p => p.key === entry.key);
        const onOther = TR[side === "give" ? "receive" : "give"].some(p => p.key === entry.key);
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.playerKey = entry.key;
        button.setAttribute("aria-pressed", String(selected));
        button.setAttribute("aria-label", `${selected ? "Remove" : "Add"} ${entry.name} ${side === "give" ? "from You give" : "to You receive"}`);
        button.disabled = !row || onOther;
        const name = document.createElement("span");
        name.textContent = `${selected ? "✓ " : "+ "}${entry.name} · ${entry.pos || row?.pos || "?"}`;
        const value = document.createElement("span");
        const n = row?.values?.[TR.shown];
        value.textContent = row ? (Number.isFinite(n) ? fmt(n) : "no value") : "not in values";
        button.append(name, value);
        button.addEventListener("click", () => {
          if (selected) TR[side] = TR[side].filter(p => p.key !== entry.key);
          else {
            if (isUntouchedExample()) { TR.give = []; TR.receive = []; }
            TR[side] = TR[side].concat({key: entry.key, name: row.name});
          }
          TR.example = null;
          TR.undo = null;
          renderCompare();
          host.querySelector(`.v2-croster-list button[data-player-key="${CSS.escape(entry.key)}"]`)?.focus();
        });
        li.appendChild(button);
        list.appendChild(li);
      });
      section.append(heading, list);
      lists.appendChild(section);
    });
    host.replaceChildren(intro, controls, actions, status, lists);
    card.hidden = !ctx.teams.length && !ctx.held;
  }

  function compareConstructionInput() {
    const ctx = compareRosterContext();
    if (ctx.held) return {reason: carriedHoldText(ctx.held), held: true};
    if (!ctx.ready) return {reason: "Add both rosters in Your league to see starters, bench and open spots."};
    if (!compareRosterMembership(ctx)) return {reason: "Choose trade players from the selected rosters to see lineup changes."};
    if (!compareView.ready) return {reason: "Add a player to both sides to see how each roster changes."};
    if (compareView.giveRows.concat(compareView.receiveRows).some(row => !Number.isFinite(row.values?.[DDF_KEY])))
      return {reason: "A traded player has no DDF Value this week; lineup values cannot be judged."};
    const unresolved = [ctx.mine, ctx.theirs].flatMap(team => team.entries.filter(entry =>
      !["K", "DEF"].includes(entry.pos) && !compareView.rowsByKey.has(entry.key)));
    if (unresolved.length) return {reason: `${unresolved.length} roster player${unresolved.length === 1 ? " is" : "s are"} missing from this week's values; lineup fit cannot be judged.`};
    const F = window.TradeValueFinder;
    const shape = C.getRosterShape();
    const key = DDF_KEY;
    const mine = F.rosterImpact(compareRosterRows(ctx.mine), compareView.giveRows, compareView.receiveRows, shape, key);
    const theirs = F.rosterImpact(compareRosterRows(ctx.theirs), compareView.receiveRows, compareView.giveRows, shape, key);
    return {ctx, shape, key, mine, theirs};
  }

  function renderCompareConstruction() {
    const card = $("v2CConstruction");
    const host = $("v2CConstructionBody");
    const input = compareConstructionInput();
    host.replaceChildren();
    // JEG-1259 / JEG-1240: the bench level that priced these lineups (Compare prices the modeled bench on this build).
    card.dataset.benchLevel = compareCarried && compareCarried.status === "ok" ? compareCarried.context.pricing.mode : "modeled";
    card.dataset.carried = compareCarried ? compareCarried.status : "none";
    if (input.reason) {
      const note = document.createElement("p");
      note.className = "v2-meta";
      note.textContent = input.reason;
      host.appendChild(note);
      card.dataset.ready = "false";
      return;
    }
    card.dataset.ready = "true";
    const L = window.TradeValueLineupComparison;
    if (!L?.renderTable) {
      const note = document.createElement("p");
      note.className = "v2-meta";
      note.textContent = "Lineup display is unavailable.";
      host.appendChild(note);
      card.dataset.ready = "false";
      return;
    }
    const panels = document.createElement("div");
    panels.className = "v2-cconstruction-panels";
    [[input.ctx.mine, input.mine], [input.ctx.theirs, input.theirs]].forEach(([team, impact]) => {
      const panel = document.createElement("section");
      panel.setAttribute("aria-label", `${team.name} lineup before and after`);
      const heading = document.createElement("h3");
      heading.textContent = team.name;
      panel.appendChild(heading);
      panel.appendChild(L.renderTable(impact, input.shape, input.key, `${team.name}: best starting lineup in DDF Value`));
      const note = document.createElement("p");
      note.className = "v2-meta";
      const spots = impact.spotsOpened;
      const spotsText = spots > 0 ? ` Opens ${spots} roster/bench spot${spots === 1 ? "" : "s"}.`
        : spots < 0 ? ` Uses ${-spots} roster/bench spot${spots === -1 ? "" : "s"}.` : " Roster spots unchanged.";
      const empty = (picked) => Object.entries(picked.empty || {}).filter(([, count]) => count > 0)
        .map(([slot, count]) => `${slot} ${count}`).join(", ") || "none";
      note.textContent = `Empty starting slots: ${empty(impact.before)} before, ${empty(impact.after)} after.${spotsText}`;
      panel.appendChild(note);
      panels.appendChild(panel);
    });
    host.appendChild(panels);
  }

  function seriesName(key) {
    const meta = sourceMeta(key);
    return isDdfKey(key) ? meta.label : plainSeries(meta.publisher, meta.method);
  }

  function collectCompare() {
    compareTierRows = null;
    compareCarried = receiveCarried();
    const rowsByKey = new Map(C.getAllRows().map(row => [String(row.player_key), row]));
    // A player the engine no longer has a row for stays listed, missing in every series.
    const resolve = list => list.map(p => rowsByKey.get(p.key) || {player_key: p.key, name: p.name, values: {}, unpriced: true});
    const usable = keys => keys.filter(key => view.infoByKey[key]?.available);
    // JEG-498: Compare reads its own Customize list, not Player values' (the engine prices every visible series).
    const mine = pageKeys("compare").filter(key => view.infoByKey[key]);
    const mineOrdered = orderSeries(mine, view.rankKey);
    let pointKeys = usable(mineOrdered.filter(key => sourceMeta(key).method !== "vorp"));
    const vorpKeys = usable(mineOrdered.filter(key => sourceMeta(key).method === "vorp"));
    const unavailable = mine.filter(key => !view.infoByKey[key]?.available);
    // "Player values shown": one exact series; DDF Value unless picked, then the ranking series.
    // The charts alias is the same visible DDF Value (JEG-1073); offer each distinct series once.
    const ddfOffered = DDF_PICK_KEYS.filter(key => view.infoByKey[key]?.available && !pointKeys.includes(key));
    const shownChoices = pointKeys.concat(vorpKeys);
    if (!shownChoices.includes(TR.shown) && !ddfOffered.includes(TR.shown)) {
      TR.shown = [DDF_KEY, view.rankKey].find(key => shownChoices.includes(key)) || shownChoices[0] || null;
    }
    // A picked version that is not shown joins the series the trade is read in.
    if (ddfOffered.includes(TR.shown)) pointKeys = pointKeys.concat(TR.shown);
    shownChoices.splice(0, shownChoices.length, ...pointKeys.concat(ddfOffered.filter(key => !pointKeys.includes(key)), vorpKeys));
    verdictSeries = pointKeys.includes(DDF_KEY) ? DDF_KEY : TR.shown;
    const TC = window.TradeValueTrade;
    // JEG-1190 (Jeremy, 2026-10-28, "A"): Compare starts empty. The sample trade is loaded only by "Try a sample trade",
    // as a real trade the reader can edit; it is marked Example until they change it.
    const example = isUntouchedExample();
    const giveRows = resolve(TR.give);
    const receiveRows = resolve(TR.receive);
    // JEG-1285: a held carried trade shows its players but no number or claim priced on this page.
    const held = compareCarried && compareCarried.status === "hold" ? compareCarried : null;
    const ready = !held && giveRows.length > 0 && receiveRows.length > 0;
    const points = ready ? TC.compareTrade(giveRows, receiveRows, pointKeys).rows : [];
    const vorp = ready ? TC.compareTrade(giveRows, receiveRows, vorpKeys).rows : [];
    const metaFor = key => ({...sourceMeta(key), week: view.infoByKey[key]?.week ?? null});
    // JEG-505: the Deal read counts the published value charts: the as-published (rescaled) series.
    const chartKeys = pointKeys.filter(key => sourceMeta(key).method === "indexed" && window.TradeValueTargets.CHART_KEYS.includes(key));
    // JEG-468: one waterfall per row; trade-value rows share one scale, each VORP vs waivers
    // series keeps its own (those scales are not comparable).
    const falls = keys => (ready ? keys.map(key => TC.waterfall(giveRows, receiveRows, key)) : []);
    const pointFalls = falls(pointKeys);
    const deal = ready ? TC.dealRead(giveRows, receiveRows, chartKeys) : null;
    compareView = {rowsByKey, giveRows, receiveRows, ready, example: Boolean(example), pointKeys, vorpKeys, unavailable, shownChoices,
      points, story: ready ? TC.tradeStory(points, metaFor) : {kind: null},
      verdict: ready ? TC.tradeVerdict(points.concat(vorp), verdictKey()) : {kind: null, key: verdictKey()},
      deal,
      totals: TR.shown && !held ? {give: TC.sideTotal(giveRows, TR.shown), receive: TC.sideTotal(receiveRows, TR.shown)} : null,
      held, vorp, falls: {points: pointFalls, vorp: falls(vorpKeys)}, scale: TC.waterfallScale(pointFalls)};
  }

  // True while the sides are exactly the sample "Try a sample trade" loaded; any change drops the Example mark for good.
  function isUntouchedExample() {
    const ex = TR.example;
    const same = (list, keys) => list.length === keys.length && list.every(p => keys.includes(p.key));
    if (ex && same(TR.give, ex.give) && same(TR.receive, ex.receive)) return true;
    TR.example = null;
    return false;
  }

  // The example trade, recomputed only when the series or the values change.
  function exampleTrade(pointKeys) {
    const key = verdictKey();
    const rows = C.getAllRows();
    const keys = pointKeys.concat(key);
    const signature = `${keys.join(",")}|${rows.length}|${rows.reduce((acc, r) => acc + keys.reduce((a, k) => a + (Number.isFinite(r.values[k]) ? r.values[k] : 0.123), 0), 0)}`;
    if (!exampleCache || exampleCache.signature !== signature) {
      exampleCache = {signature, pick: window.TradeValueTrade.pickExample(rows, pointKeys, key)};
    }
    return exampleCache.pick;
  }

  function sourceCell(td, key) {
    const meta = sourceMeta(key);
    const item = view.infoByKey[key];
    const sym = document.createElement("span");
    sym.className = "v2-sym";
    sym.style.color = meta.color;
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = `${meta.symbol} `;
    td.appendChild(sym);
    td.append(sourceLink(key, seriesName(key)));
    const sub = document.createElement("span");
    sub.className = "th-sub";
    // TT-06 (contract v1.2): a chart a week behind shows the shared "Wk N" badge in its row.
    if (item?.stale) sub.append(weekBadge(key), document.createTextNode(" older week"));
    else sub.textContent = item?.week ? `Week ${item.week}` : "week unknown";
    appendDivergence(sub, key, {noLink: true});   // JEG-1048: the 44 px row has no room for a 44 px link under the name; Customize keeps the link (JEG-1193)
    td.appendChild(document.createElement("br"));
    td.appendChild(sub);
  }

  function netLabel(net) {
    const text = fmtGap(net);
    if (text === "0.0") return {text, cls: "", label: "= even by this source"};
    return net > 0 ? {text, cls: "up", label: "▲ you receive more by this source"}
      : {text, cls: "down", label: "▼ you give more by this source"};
  }

  // Frame 24 "Expanded result": every player's value in this series, each side's total, then the net.
  function breakdownRow(result, columns) {
    const tr = document.createElement("tr");
    tr.className = "v2-cbreak";
    tr.dataset.breakdown = result.key;
    const td = document.createElement("td");
    td.colSpan = columns;
    const grid = document.createElement("div");
    grid.className = "v2-cbreak-grid";
    [["give", compareView.giveRows, result.give], ["receive", compareView.receiveRows, result.receive]].forEach(([side, rows, total]) => {
      const col = document.createElement("div");
      const h = document.createElement("p");
      h.className = "v2-meta";
      h.textContent = SIDE_NAME[side];
      col.appendChild(h);
      rows.forEach(row => {
        const v = row.values ? row.values[result.key] : null;
        const line = document.createElement("p");
        line.dataset.playerKey = String(row.player_key);
        line.append(document.createTextNode(`${row.name} `));
        if (Number.isFinite(v)) {
          const b = document.createElement("b");
          b.textContent = fmt(v);
          line.appendChild(b);
          appendLowConfidence(line, row, result.key);
          // JEG-1059: the badge next to the value the reader set.
          if (result.key === DDF_KEY) appendOverrideFlag(line, row);
        } else {
          line.appendChild(missingNode(missingReason(result.key, row), "no value"));
        }
        col.appendChild(line);
      });
      const t = document.createElement("p");
      t.className = "v2-cbreak-total";
      t.textContent = total === null ? "Total: incomplete" : `Total ${fmt(total)}`;
      col.appendChild(t);
      grid.appendChild(col);
    });
    const sum = document.createElement("p");
    sum.className = `v2-cbreak-net ${result.net === null ? "" : netLabel(result.net).cls}`;
    sum.textContent = result.net === null
      ? "Receive − give: incomplete. A missing value is never counted as zero."
      : `Receive − give = ${fmtGap(result.net)} ${sourceMeta(result.key).method === "vorp" ? "value above waivers points" : "trade-value points"}`;
    td.append(grid, sum);
    tr.appendChild(td);
    return tr;
  }

  // JEG-468: short names for the step labels; a shared last name gets an initial.
  function shortNames(rows) {
    const suffix = /^(jr\.?|sr\.?|ii|iii|iv|v)$/i;
    const last = row => {
      const parts = String(row.name || "").split(/\s+/).filter(Boolean);
      while (parts.length > 1 && suffix.test(parts[parts.length - 1])) parts.pop();
      return {first: parts[0] || "", last: parts[parts.length - 1] || String(row.name || "Player")};
    };
    const names = rows.map(last);
    const count = new Map();
    names.forEach(n => count.set(n.last, (count.get(n.last) || 0) + 1));
    return new Map(rows.map((row, i) => [String(row.player_key),
      count.get(names[i].last) > 1 && names[i].first !== names[i].last ? `${names[i].first.charAt(0)}. ${names[i].last}` : names[i].last]));
  }

  // JEG-468 waterfall: 0 → a step down per player given → a step up per player received →
  // a landing bar from 0 to the net. Three lanes (give, receive, result) on the table's
  // scale. Each step is focusable, with a text alternative and the shared tooltip.
  function renderWaterfall(cell, fall, scale) {
    const name = seriesName(fall.key);
    const span = scale.hi - scale.lo;
    const x = v => Math.max(0, Math.min(100, ((v - scale.lo) / span) * 100));
    const short = shortNames(compareView.giveRows.concat(compareView.receiveRows));
    const box = document.createElement("div");
    box.className = "v2-wf";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", `${name}, step by step from 0`);
    box.dataset.lo = String(scale.lo);
    box.dataset.hi = String(scale.hi);
    const zero = document.createElement("span");
    zero.className = "v2-wf-zero";
    zero.setAttribute("aria-hidden", "true");
    zero.style.left = `${x(0)}%`;
    box.appendChild(zero);
    const lanes = {};
    ["give", "receive", "net"].forEach(lane => {
      const div = document.createElement("div");
      div.className = "v2-wf-lane";
      div.dataset.lane = lane;
      lanes[lane] = div;
      box.appendChild(div);
    });
    const runningText = step => (step.partial ? `running ${fmtGap(step.running)} so far, row incomplete` : `running ${fmtGap(step.running)}`);
    fall.steps.forEach(step => {
      const who = short.get(String(step.row.player_key)) || step.row.name;
      const verb = step.side === "give" ? "Give" : "Receive";
      const el = document.createElement("span");
      el.className = `v2-wf-step ${step.side}${step.missing ? " is-missing" : ""}`;
      el.tabIndex = -1;   // JEG-899: not a tab stop (the numbers are in the table below); a pointer still focuses it
      el.setAttribute("role", "img");
      el.dataset.playerKey = String(step.row.player_key);
      el.dataset.side = step.side;
      if (step.missing) {
        const reason = `No ${name} value for ${step.row.name}`;
        const w = 14;
        const at = x(step.start);
        const left = step.side === "give" ? Math.max(0, at - w) : Math.min(at, 100 - w);
        el.style.left = `${left}%`;
        el.style.width = `${w}%`;
        el.dataset.missing = "true";
        el.setAttribute("aria-label", `${verb} ${who}: no value. ${reason}; this row is incomplete and has no result`);
        const label = document.createElement("span");
        label.className = "v2-wf-label";
        label.setAttribute("aria-hidden", "true");
        label.textContent = `— ${who}`;
        el.appendChild(label);
        el._tip = {title: step.row.name, lines: [name, `${verb}: — no value`, reason, "Row incomplete: a missing value is never counted as zero"]};
      } else {
        const from = Math.min(x(step.start), x(step.end));
        const width = Math.abs(x(step.end) - x(step.start));
        el.style.left = `${from}%`;
        el.style.width = `${width}%`;
        el.dataset.value = fmtGap(step.delta);
        el.dataset.running = fmtGap(step.running);
        el.setAttribute("aria-label", `${verb} ${who} ${fmtGap(step.delta)}, ${runningText(step)}`);
        const label = document.createElement("span");
        label.className = "v2-wf-label";
        label.setAttribute("aria-hidden", "true");
        label.textContent = width >= 16 ? `${who} ${fmtGap(step.delta)}` : width >= 7 ? fmtGap(step.delta) : "";
        el.appendChild(label);
        el._tip = {title: step.row.name, lines: [name, `${verb} ${fmtGap(step.delta)}`, runningText(step).replace(/^running/, "Running total")]};
      }
      lanes[step.side].appendChild(el);
    });
    // A dashed link where the give steps end and the receive steps start.
    const turn = fall.steps.filter(st => st.side === "give").pop();
    if (turn) {
      const link = document.createElement("span");
      link.className = "v2-wf-link";
      link.setAttribute("aria-hidden", "true");
      link.style.left = `${x(turn.end)}%`;
      box.appendChild(link);
    }
    if (fall.complete) {
      const n = netLabel(fall.net);
      const land = document.createElement("span");
      land.className = `v2-wf-land ${n.cls}`;
      land.tabIndex = -1;   // JEG-899
      land.setAttribute("role", "img");
      land.dataset.net = n.text;
      land.setAttribute("aria-label", `Result ${n.text}: ${n.label.replace(/^[▲▼=] /, "")}`);
      const a = x(0);
      const b = x(fall.net);
      land.style.left = `${Math.min(a, b)}%`;
      land.style.width = `${Math.abs(b - a)}%`;
      land._tip = {title: `${name}: Receive − give`, lines: [`${fmt(fall.receive)} receive − ${fmt(fall.give)} give`, `= ${n.text}`, n.label]};
      const tag = document.createElement("span");
      tag.className = `v2-wf-net ${n.cls}`;
      tag.setAttribute("aria-hidden", "true");
      tag.textContent = `${n.cls === "up" ? "▲" : n.cls === "down" ? "▼" : "="} ${n.text}`;
      // Beside the bar's far end, or on the other side of 0 when the end is near the edge.
      if (fall.net >= 0) {
        if (b < 84) tag.style.left = `calc(${b}% + 6px)`;
        else tag.style.right = `calc(${100 - a}% + 6px)`;
      } else if (b > 16) tag.style.right = `calc(${100 - b}% + 6px)`;
      else tag.style.left = `calc(${a}% + 6px)`;
      lanes.net.append(land, tag);
    } else {
      const none = document.createElement("span");
      none.className = "v2-wf-none";
      none.textContent = "No result: a value is missing";
      lanes.net.appendChild(none);
    }
    cell.appendChild(box);
  }

  function showStepTip(el) {
    const tip = $("v2Tip");
    if (!el || !el._tip) { tip.hidden = true; return; }
    tip.replaceChildren();
    const h = document.createElement("h3");
    h.textContent = el._tip.title;
    tip.appendChild(h);
    el._tip.lines.forEach((text, i) => {
      const line = document.createElement(i === 0 ? "span" : "div");
      line.className = i === 0 ? "v2-meta" : "row";
      line.textContent = text;
      tip.appendChild(line);
    });
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    const tipBox = tip.getBoundingClientRect();
    const left = Math.min(box.left, window.innerWidth - tipBox.width - 8);
    let top = box.bottom + 8;
    if (top + tipBox.height > window.innerHeight - 8) top = box.top - tipBox.height - 8;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  }

  function renderCompareTable(table, keys, rows, falls, sharedScale) {
    table.replaceChildren();
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    [["Source", "player"], ["Give", "num"], ["Receive", "num"], ["From 0: give ↓ · receive ↑ · result", "bar"], ["Receive − give", "num"]].forEach(([text, cls]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.className = cls;
      th.textContent = text;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    const fallByKey = new Map((falls || []).map(f => [f.key, f]));
    rows.forEach(result => {
      const tr = document.createElement("tr");
      tr.dataset.source = result.key;
      if (result.key === view.rankKey) tr.className = "is-rank";
      const source = document.createElement("td");
      source.className = "player";
      sourceCell(source, result.key);
      // JEG-467: the series the verdict reads is marked in words, not only by its tint.
      if (result.key === verdictKey()) {
        tr.classList.add("is-verdict");
        const tag = document.createElement("span");
        tag.className = "v2-cverdict-tag";
        tag.textContent = "★ Decides the verdict";
        source.insertBefore(tag, source.querySelector(".th-sub"));
      }
      const open = TR.open.has(result.key);
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "v2-link v2-cexpand";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Hide players ▴" : "Show players ▾";
      toggle.addEventListener("click", () => {
        if (TR.open.has(result.key)) TR.open.delete(result.key);
        else TR.open.add(result.key);
        renderCompare();
        const again = document.querySelector(`#${table.id} tr[data-source="${result.key}"] .v2-cexpand`);
        if (again) again.focus();
      });
      source.appendChild(toggle);
      tr.appendChild(source);
      const cell = (label, name, cls) => {
        const td = document.createElement("td");
        td.className = cls || "num";
        td.dataset.label = label;
        td.dataset.col = name;
        tr.appendChild(td);
        return td;
      };
      const give = cell("Give", "give");
      const get = cell("Receive", "receive");
      const bar = cell("", "bar", "bar");
      const net = cell("Receive − give", "net");
      if (result.net === null) {
        const names = result.missing.map(m => m.row.name || "a player");
        const reason = `No ${seriesName(result.key)} value for ${names.join(", ")}`;
        [give, get].forEach(td => {
          const dash = document.createElement("span");
          dash.className = "missing";
          dash.title = reason;
          dash.textContent = "—";
          td.appendChild(dash);
        });
        const node = missingNode(reason, `Incomplete: ${reason.charAt(0).toLowerCase()}${reason.slice(1)}`);
        net.appendChild(node);
      } else {
        give.textContent = fmt(result.give);
        get.textContent = fmt(result.receive);
        const n = netLabel(result.net);
        net.append(document.createTextNode(n.text));
        const why = document.createElement("span");
        why.className = `delta ${n.cls}`;
        why.textContent = n.label;
        net.appendChild(why);
      }
      // JEG-468: incomplete rows draw their steps too (hatched "no value"), but no landing.
      const fall = fallByKey.get(result.key);
      if (fall) renderWaterfall(bar, fall, sharedScale || window.TradeValueTrade.waterfallScale([fall]));
      tbody.appendChild(tr);
      if (open) tbody.appendChild(breakdownRow(result, 5));
    });
    table.append(thead, tbody);
  }

  function renderSidePlayers(side) {
    const list = $(SIDE_IDS[side].list);
    list.replaceChildren();
    const rows = side === "give" ? compareView.giveRows : compareView.receiveRows;
    const shown = TR.shown;
    rows.forEach(row => {
      const li = document.createElement("li");
      li.dataset.playerKey = String(row.player_key);
      const who = document.createElement("div");
      const name = document.createElement(row.unpriced ? "b" : "button");
      if (!row.unpriced) {
        name.type = "button";
        name.className = "v2-trade-name";
        name.setAttribute("aria-label", `${row.name}: player details`);
        name.addEventListener("click", () => openDrawer(row, "compare"));
      }
      name.textContent = row.name;
      appendEspnZero(name, row);
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      if (row.unpriced) sub.textContent = "No value in any source for this league";
      else {
        sub.textContent = `${row.pos} · ${row.team || "Free agent"}`;
        appendFlags(sub, row, compareView.held ? "" : ` · ${tierText(row, verdictKey(), compareTierScope())}`);   // JEG-892: bye week before the tier
      }
      who.append(name, sub);
      const value = document.createElement("span");
      value.className = "v2-trade-value";
      value.dataset.source = shown || "";
      const v = shown && row.values ? row.values[shown] : null;
      if (compareView.held) {
        value.textContent = "held";
        value.dataset.held = "true";
      } else if (Number.isFinite(v)) {
        value.textContent = fmt(v);
        appendLowConfidence(value, row, shown);
        // JEG-1059: the badge next to the value the reader set.
        if (shown === DDF_KEY) appendOverrideFlag(value, row);
      } else value.appendChild(missingNode(shown ? missingReason(shown, row) : `No value for ${row.name}`, "no value"));
      if (compareView.example) li.classList.add("is-example");
      // JEG-1190: "Remove" in words, as on Find a trade and Waivers; sample players are removable too.
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "v2-link v2-remove";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", `Remove ${row.name}`);
      remove.addEventListener("click", () => {
        TR[side] = TR[side].filter(p => p.key !== String(row.player_key));
        TR.undo = null;
        renderCompare();
        $(SIDE_IDS[side].search).focus();
      });
      li.append(who, value, remove);
      list.appendChild(li);
    });
    if (!rows.length) {
      const li = document.createElement("li");
      li.className = "v2-meta is-empty";
      li.textContent = "Search and add a player.";
      list.appendChild(li);
    }
    // Frame 07: "<series> total" at the foot of each side.
    const total = $(SIDE_IDS[side].total);
    const t = compareView.totals && compareView.totals[side];
    total.hidden = !rows.length || !t;
    total.replaceChildren();
    if (rows.length && t) {
      const label = document.createElement("span");
      label.className = "v2-meta";
      label.textContent = `${seriesName(t.key)} total`;
      const value = document.createElement("b");
      value.dataset.total = side;
      if (t.total === null) {
        value.appendChild(missingNode(`No ${seriesName(t.key)} value for ${t.missing.map(r => r.name).join(", ")}`, "incomplete"));
      } else {
        value.textContent = fmt(t.total);
      }
      total.append(label, value);
    }
  }

  function searchMatches(needle, allowed) {
    const rankKey = view.rankKey;
    const value = row => (Number.isFinite(row.values[rankKey]) ? row.values[rankKey] : -Infinity);
    const byValue = [...compareView.rowsByKey.values()].filter(row => !allowed || allowed.has(String(row.player_key)))
      .sort((a, b) => value(b) - value(a) || String(a.name).localeCompare(String(b.name)));
    // Exact and prefix matches first, then by value; a typo-tolerant fallback when nothing matches.
    return window.TradeValueNameSearch.search(byValue, needle).slice(0, 8);
  }

  function addToSide(side, row) {
    const roster = compareRosterContext();
    if (roster.ready && !(side === "give" ? roster.mine : roster.theirs).entries.some(e => e.key === String(row.player_key))) {
      $("v2CRosterStatus").textContent = `${row.name} is not on the selected ${side === "give" ? "your" : "their"} roster.`;
      return;
    }
    // JEG-1190: a player of the reader's own replaces an untouched sample trade instead of joining it.
    if (isUntouchedExample()) { TR.give = []; TR.receive = []; TR.example = null; TR.open.clear(); }
    TR.undo = null;
    TR[side] = TR[side].concat({key: String(row.player_key), name: row.name});
    const input = $(SIDE_IDS[side].search);
    input.value = "";
    $(SIDE_IDS[side].results).hidden = true;
    renderCompare();
    input.focus();
  }

  // Frame 24 / 18: results show position, team and the ranking series' value; a player
  // already on the trade stays listed as "✓ Added" (disabled) instead of vanishing.
  function renderSearch(side) {
    const input = $(SIDE_IDS[side].search);
    const results = $(SIDE_IDS[side].results);
    const raw = input.value.trim();
    const needle = raw.toLowerCase();
    results.replaceChildren();
    if (!needle || !compareView) { results.hidden = true; return []; }
    const where = new Map(["give", "receive"].flatMap(s => TR[s].map(p => [p.key, s])));
    const roster = compareRosterContext();
    const allowed = roster.ready ? new Set((side === "give" ? roster.mine : roster.theirs).entries.map(e => e.key)) : null;
    const matches = searchMatches(needle, allowed);
    const addable = [];
    matches.forEach(row => {
      const key = String(row.player_key);
      const on = where.get(key);
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.playerKey = key;
      const name = document.createElement("b");
      name.textContent = row.name;
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      const v = row.values[view.rankKey];
      sub.textContent = ` ${row.pos} · ${row.team || "Free agent"} · ${sourceMeta(view.rankKey).short} ${Number.isFinite(v) ? fmt(v) : "—"}`;
      button.append(name, sub);
      if (on) {
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
        const added = document.createElement("span");
        added.className = "v2-added";
        added.textContent = on === side ? "✓ Added" : `✓ On ${SIDE_NAME[on]}`;
        button.appendChild(added);
      } else {
        button.addEventListener("click", () => addToSide(side, row));
        addable.push(row);
      }
      li.appendChild(button);
      results.appendChild(li);
    });
    // JEG-502: players no source prices, after the priced ones. Shown, never added to a trade.
    const unpriced = unpricedMatches(raw).slice(0, Math.max(0, 8 - matches.length));
    unpriced.forEach(row => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.disabled = true;
      button.setAttribute("aria-disabled", "true");
      button.dataset.playerKey = String(row.player_key);
      button.dataset.unpriced = "";
      const name = document.createElement("b");
      name.textContent = row.name;
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = ` ${row.pos} · DDF Value ${unpricedValue(row)}`;
      const why = document.createElement("span");
      why.className = "v2-meta v2-unpriced-why";
      why.textContent = `○ Not valued: ${unpricedReason(row)}`;
      button.append(name, sub, why);
      li.appendChild(button);
      results.appendChild(li);
    });
    if (!matches.length && !unpriced.length) {
      const li = document.createElement("li");
      li.className = "v2-meta is-empty";
      li.append(document.createTextNode(`No player matches “${raw}”. `));
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "v2-link";
      clear.textContent = "Clear search";
      clear.addEventListener("click", () => { input.value = ""; results.hidden = true; input.focus(); });
      li.appendChild(clear);
      results.appendChild(li);
    }
    results.hidden = false;
    return addable;
  }

  // "A, B and C" (or "A, B or C") from series keys, in plain words.
  function listSeries(keys, joiner) {
    const names = keys.map(seriesName);
    if (names.length <= 1) return names.join("");
    return `${names.slice(0, -1).join(", ")} ${joiner || "and"} ${names[names.length - 1]}`;
  }

  // Frame 22 #15: copy names the publisher, methods and signed nets from data.
  function renderStory() {
    const box = $("v2CStory");
    const s = compareView.story;
    // JEG-487: the rule-based deal read replaces "The sources split." (a split is what the read explains).
    box.hidden = !s.kind || s.kind === "single" || s.kind === "split";
    // Folded into the verdict card (JEG-469): open for a same-publisher contrast, which the
    // verdict does not say; otherwise one click away. A reader's own toggle is kept.
    if (box.dataset.story !== (s.kind || "")) box.open = s.kind === "contrast";
    box.dataset.story = s.kind || "";
    if (box.hidden) return;
    const title = $("v2CStoryTitle");
    const text = $("v2CStoryText");
    if (s.kind === "contrast") {
      const name = PUBLISHER_NAMES[s.publisher] || s.publisher;
      title.textContent = "Same publisher. Different result.";
      text.textContent = `${name}: the rescaled chart shows ${fmtGap(s.indexed.net)}; Data Driven Adjustments show ${fmtGap(s.dda.net)}. `
        + "Your league's adjustments reverse the direction. Compare the same publisher before comparing across sources.";
    } else if (s.kind === "agree") {
      const all = listSeries(s.upKeys.concat(s.downKeys, s.evenKeys));
      title.textContent = "Every complete source points the same way.";
      text.textContent = s.up ? `You receive more value than you give by every complete source: ${all}.`
        : s.down ? `You give more value than you receive by every complete source: ${all}.`
          : `The trade is even by every complete source: ${all}.`;
    } else if (s.kind === "split") {
      // Name the series on each side (Jeremy, 2026-10-08), then who is likeliest to say yes.
      title.textContent = "The sources split.";
      const parts = [];
      if (s.up) parts.push(`You receive more by ${listSeries(s.upKeys)}.`);
      if (s.down) parts.push(`You give more by ${listSeries(s.downKeys)}.`);
      if (s.even) parts.push(`Even by ${listSeries(s.evenKeys)}.`);
      if (s.down) parts.push(`A manager who trades off ${listSeries(s.downKeys, "or")} is the likeliest to accept.`);
      text.textContent = parts.join(" ");
    } else {
      title.textContent = "No complete source yet.";
      text.textContent = "Every selected source is missing a value for at least one player, so no row has a result. See each row for who is missing.";
    }
  }

  // JEG-487 deal read (CT-08): three nets with their questions, the fixed 9-cell grid with the current cell
  // outlined, and one production sentence. Everything is read from compareView.deal (trade.js dealRead).
  const DEAL_NETS = [
    ["value", "DDF Value", "Are you getting real value?"],
    ["market", "Trade chart average", "Does the market think you are winning?"],
    ["projections", "DDF Value (projections)", "Is the value backed by projected production?"]];
  const DEAL_SIDE_WORD = {win: "You win", even: "Even", lose: "You lose"};
  function renderDeal() {
    const box = $("v2CDeal");
    const deal = compareView.deal;
    box.hidden = !deal;
    if (!deal) {
      // JEG-823: clear stale deal-read content when a side is empty (defense in depth, cf. JEG-808).
      $("v2CDealRead").textContent = "";
      $("v2CDealText").textContent = "";
      $("v2CDealNets").replaceChildren();
      $("v2CDealGrid").replaceChildren();
      $("v2CDealProduction").textContent = "";
      return;
    }
    const TC = window.TradeValueTrade;
    const dealTitle = deal.kind === "read"
      // JEG-841: avoid doubled label when the title already contains the action (an empty action leaves the title alone).
      ? (deal.title.toLowerCase().includes(deal.action.toLowerCase()) ? deal.title : `${deal.title}: ${deal.action}`)
      : "";
    $("v2CDealRead").textContent = dealTitle;
    $("v2CDealRead").hidden = deal.kind !== "read";
    $("v2CDealText").textContent = deal.text;
    const nets = $("v2CDealNets");
    nets.replaceChildren();
    DEAL_NETS.forEach(([id, name, question]) => {
      const n = deal[id];
      const li = document.createElement("li");
      li.dataset.net = id;
      const label = document.createElement("span");
      label.className = "v2-deal-name";
      label.textContent = name;
      const info = document.createElement("button");
      info.type = "button";
      info.className = "v2-info";
      info.setAttribute("aria-label", `What ${name} tells you`);
      info.setAttribute("aria-expanded", "false");
      const glyph = document.createElement("span");
      glyph.setAttribute("aria-hidden", "true");
      glyph.textContent = "ⓘ";
      info.appendChild(glyph);
      const def = document.createElement("span");
      def.className = "v2-deal-def v2-meta";
      def.hidden = true;
      def.textContent = `${(DEAL_NET_DEF[id] || NAME_DEFS.find(([n]) => n === name))[1]} ${question}`;
      info.addEventListener("click", () => { def.hidden = !def.hidden; info.setAttribute("aria-expanded", String(!def.hidden)); });
      const value = document.createElement("b");
      value.className = "v2-deal-net";
      value.dataset.side = n.side || "";
      // JEG-832: show "not enough charts" when the market card has too few compared charts.
      // JEG-886: when the per-chart rows do not support the average's side, say so instead of the side word.
      value.textContent = n.net === null ? (n.tooFew ? "Not enough charts" : "—")
        : n.split ? `${fmtGap(n.net)} · Charts split (${fmtGap(n.charts.min)} to ${fmtGap(n.charts.max)})` : `${fmtGap(n.net)} · ${DEAL_SIDE_WORD[n.side]}`;
      if (n.net === null) value.title = n.tooFew ? `${n.chartCount} of ${n.minCharts} compared charts needed` : "At least one player has no value in this series";
      li.append(label, info, value, def);
      nets.appendChild(li);
    });
    const grid = $("v2CDealGrid");
    grid.replaceChildren();
    const head = document.createElement("thead");
    const hr = document.createElement("tr");
    const corner = document.createElement("th");
    corner.scope = "col";
    corner.innerHTML = `<span class="v2-sr">DDF Value (rows) against Trade chart average (columns)</span>`;
    hr.appendChild(corner);
    TC.DEAL_SIDES.forEach(m => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = `Charts: ${DEAL_SIDE_WORD[m].toLowerCase()}`;
      hr.appendChild(th);
    });
    head.appendChild(hr);
    const body = document.createElement("tbody");
    TC.DEAL_SIDES.forEach(v => {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.scope = "row";
      th.textContent = `DDF Value: ${DEAL_SIDE_WORD[v].toLowerCase()}`;
      tr.appendChild(th);
      TC.DEAL_SIDES.forEach(m => {
        const td = document.createElement("td");
        const cell = TC.DEAL_READS[`${v}|${m}`];
        td.dataset.cell = `${v}|${m}`;
        td.textContent = cell.title;
        td.title = cell.text;
        if (deal.kind === "read" && deal.cell === `${v}|${m}`) {
          td.classList.add("is-current");
          td.setAttribute("aria-current", "true");
        }
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    grid.append(head, body);
    const production = $("v2CDealProduction");
    production.textContent = deal.production || "";
    production.hidden = !deal.production;
  }

  // JEG-469 verdict (Jeremy, 2026-10-08): "Primary thing that matters is that DDF thinks you
  // win, and it can be better if the other sources DON'T agree." One series decides (verdictKey);
  // the complete series that see it the other way are named as the selling point.
  function verdictCopy() {
    const v = compareView.verdict;
    const key = v.key || verdictKey();
    const name = key ? seriesName(key) : "";
    const thinks = keys => (keys.length === 1 ? "thinks" : "think");
    if (!key) return {kind: "none", title: "No verdict yet", text: "Pick a series in Player values shown."};
    // JEG-1190: the empty start, in the approved copy (PMM doc 3.3, "Check a trade (empty)").
    if (!TR.give.length && !TR.receive.length) return {kind: "none", title: "Who's on the table?", text: "Add players to each side and we'll call it."};
    if (compareView.held) return {kind: "none", title: "No verdict while this trade is held", text: carriedHoldText(compareView.held)};
    if (!compareView.ready || !v.kind) {
      return {kind: "none", title: "No verdict yet", text: `Add a player to both sides. The verdict reads ${name}, then names the sources that see it the other way.`};
    }
    const notCounted = v.incompleteKeys.length
      ? ` Not counted, a value is missing: ${listSeries(v.incompleteKeys)}.` : "";
    if (v.kind === "incomplete") {
      const names = v.missing.map(m => m.row.name || "a player").join(", ");
      return {kind: v.kind, title: `${name}: no verdict yet`,
        text: `No ${name} value for ${names}, so this series cannot score the trade (a missing value is never counted as zero). `
          + (isDdfKey(key) ? "Each source's own result is in the table below." : "Pick another series in Player values shown.")};
    }
    const net = fmtGap(v.net);
    if (v.kind === "win") {
      let text;
      if (v.againstKeys.length) {
        text = `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you lose this trade. A manager who trades off ${listSeries(v.againstKeys, "or")} is the likeliest to accept.`;
        if (v.evenKeys.length) text += ` Even by ${listSeries(v.evenKeys)}.`;
      } else if (!v.others) {
        text = "No other complete source to compare with yet.";
      } else if (v.allAgree) {
        text = `Every source agrees you win: ${listSeries(v.agreeKeys)}. They will see it too, so expect pushback.`;
      } else {
        text = `No source thinks you lose. ${v.agreeKeys.length ? `${listSeries(v.agreeKeys)} also ${thinks(v.agreeKeys)} you win; ` : ""}even by ${listSeries(v.evenKeys)}.`;
      }
      return {kind: v.kind, sym: "▲", title: `${name}: you win by ${net}`, text: text + notCounted};
    }
    if (v.kind === "lose") {
      const text = v.againstKeys.length
        ? `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you win, but ${name} has you giving more value than you get. Rework the offer before you send it.`
        : !v.others ? "No other complete source to compare with yet."
          : `Every complete source agrees you lose: ${listSeries(v.agreeKeys.concat(v.evenKeys))}.`;
      return {kind: v.kind, sym: "▼", title: `${name}: you lose by ${net}`, text: text + notCounted};
    }
    const parts = [];
    if (v.upKeys.length) parts.push(`${listSeries(v.upKeys)} ${thinks(v.upKeys)} you win.`);
    if (v.downKeys.length) parts.push(`${listSeries(v.downKeys)} ${thinks(v.downKeys)} you lose.`);
    if (!parts.length) parts.push(v.others ? "Every complete source calls it even too." : "No other complete source to compare with yet.");
    return {kind: v.kind, sym: "=", title: `${name}: an even trade, 0.0`, text: parts.join(" ") + notCounted};
  }

  function renderVerdict() {
    const copy = verdictCopy();
    const card = $("v2CVerdict");
    card.dataset.verdict = copy.kind;
    card.classList.toggle("is-example", compareView.example);
    $("v2CVerdictEyebrow").textContent = compareView.example ? "Example · Verdict" : "Verdict";
    const title = $("v2CVerdictTitle");
    title.replaceChildren();
    if (copy.sym) {
      const sym = document.createElement("span");
      sym.className = "v2-cverdict-sym";
      sym.setAttribute("aria-hidden", "true");
      sym.textContent = `${copy.sym} `;
      title.appendChild(sym);
    }
    title.append(document.createTextNode(copy.title));
    $("v2CVerdictText").textContent = copy.text;
    // JEG-468/469: the verdict series' own waterfall, on the table's shared scale, above the fold.
    const holder = $("v2CVerdictFall");
    holder.querySelectorAll(".v2-wf").forEach(node => node.remove());
    const key = verdictKey();
    const isPoint = compareView.pointKeys.includes(key);
    const fall = (isPoint ? compareView.falls.points : compareView.falls.vorp).find(f => f.key === key);
    holder.hidden = !compareView.ready || !fall;
    if (fall) {
      $("v2CVerdictFallNote").textContent = "From 0: down by each player you give, up by each you receive, then the result"
        + (isPoint ? " · same scale as the table below." : " · this series' own scale.");
      renderWaterfall(holder, fall, isPoint ? compareView.scale : window.TradeValueTrade.waterfallScale([fall]));
    }
    // Phone: once both sides have a player, the verdict headline stays at the bottom.
    const bar = $("v2CVerdictBar");
    const barWrap = $("v2CVerdictBarWrap");
    barWrap.dataset.verdict = copy.kind;
    bar.textContent = `${copy.sym ? `${copy.sym} ` : ""}${copy.title}`;
    bar.setAttribute("aria-label", `${copy.title}. Show the verdict`);
    TR.barWanted = compareView.ready && !compareView.example && copy.kind !== "none";
    syncVerdictBar();
  }

  function syncVerdictBar() {
    const bar = $("v2CVerdictBarWrap");
    const show = Boolean(TR.barWanted) && isNarrow() && !TR.verdictInView && currentView() === "compare";
    bar.hidden = !show;
    $("v2Compare").classList.toggle("has-verdict-bar", Boolean(TR.barWanted) && isNarrow());
  }

  function renderShownPicker() {
    const entries = compareView.shownChoices.map(key => ({key, reason: null}))
      .concat(compareView.unavailable.map(key => ({key, reason: unavailableReason(view.infoByKey[key])})));
    renderSeriesPicker($("v2CShown"), entries, TR.shown);
  }

  function renderCompare() {
    collect();
    collectCompare();
    renderHeader();
    renderShownPicker();
    renderSidePlayers("give");
    renderSidePlayers("receive");
    renderCompareRosterPicker();
    renderCompareConstruction();
    const ready = compareView.ready;
    renderVerdict();
    $("v2CExample").hidden = !compareView.example;
    const empty = !TR.give.length && !TR.receive.length;
    $("v2CStart").hidden = !empty;
    $("v2CTryExample").disabled = !verdictKey();
    $("v2Compare").classList.toggle("has-trade", Boolean(TR.give.length || TR.receive.length));
    $("v2Compare").classList.toggle("is-example", compareView.example);
    $("v2CEmpty").hidden = ready && compareView.pointKeys.length > 0;
    $("v2CEmpty").textContent = compareView.held ? "No result while this trade is held; the verdict says why."
      : !ready ? "No result until both sides have at least one player."
      : "No trade-value source is selected. Use Edit sources to pick one.";
    const table = $("v2CTable");
    table.hidden = !ready || !compareView.pointKeys.length;
    renderCompareTable(table, compareView.pointKeys, compareView.points, compareView.falls.points, compareView.scale);
    $("v2CVorpCard").hidden = !ready || !compareView.vorpKeys.length;
    renderCompareTable($("v2CVorpTable"), compareView.vorpKeys, compareView.vorp, compareView.falls.vorp, null);
    renderStory();
    renderDeal();
    const notes = [];
    if (compareView.unavailable.length) {
      notes.push(`Not compared: ${compareView.unavailable.map(key => sourceMeta(key).short).join(", ")}, not available for this league.`);
    }
    const note = $("v2CNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
    const count = compareView.giveRows.length + compareView.receiveRows.length;
    const sc = compareView.scale;
    $("v2CMeta").textContent = ready
      ? `${compareView.example ? "Example trade · " : ""}Receive − give · ${compareView.pointKeys.length} source${compareView.pointKeys.length === 1 ? "" : "s"} · trade-value points. `
        + `Every row's steps share one scale, ${fmt(sc.lo)} to ${fmt(sc.hi)}.`
      : compareView.held ? "Held: no values are shown until this trade can be priced the same way here."
      : "Receive − give, one row per source, once both sides have a player.";
    // JEG-1190: the sample trade is a real trade, so Clear, Swap and Share work on it too. Each side has its own Clear,
    // and Undo puts back what the last Clear took.
    $("v2CClear").hidden = !count;
    $("v2CSwap").hidden = !count;
    $("v2CShare").hidden = !ready;
    $("v2CShare2").hidden = !ready;   // JEG-894: the phone verdict bar's copy
    $("v2GiveClear").hidden = !TR.give.length;
    $("v2GetClear").hidden = !TR.receive.length;
    $("v2CUndo").hidden = !TR.undo;
    if (!ready) $("v2CShareNote").hidden = true;
    syncTradeHash();
  }

  // Shareable trade: the sides live in the hash, so a copied link opens the same trade.
  // A shared trade also carries the sender's scoring and roster (Jeremy, 2026-10-08: the receiver
  // is assumed to be in the same league). JEG-1026: and the team count (links written before it have none: the reader's stays).
  const LINK_ROSTER = [["QB", "QB"], ["RB", "RB"], ["WR", "WR"], ["TE", "TE"], ["FLEX", "FLEX"], ["SUPERFLEX", "SF"], ["BENCH", "BN"]];
  const LINK_SCORING = ["standard", "half_ppr", "ppr"];
  // The league settings a shared link carries (scoring, roster, position shares, season weeks, advanced); JEG-1022: the
  // Waivers link carries the same ones.
  function leagueLinkParts() {
    const parts = [];
    const shape = C.getRosterShape();
    parts.push(`scoring=${C.getState().scoring}`);
    parts.push(`teams=${C.getState().teams}`);   // JEG-1026: the team count travels too (it priced the sender's league)
    parts.push(`roster=${LINK_ROSTER.map(([key, code]) => `${code}${shape[key] || 0}`).join(".")}`);
    // Position shares only when the sender changed them (back end: encode when not default).
    const shares = C.getPositionWeights();
    const defaults = C.getDefaultPositionWeights ? C.getDefaultPositionWeights() : null;
    const custom = defaults && ["QB", "RB", "WR", "TE"].some(pos => Math.abs(Number(shares[pos]) - Number(defaults[pos])) > 5e-4);
    if (custom) parts.push(`shares=${["QB", "RB", "WR", "TE"].map(pos => `${pos}${Number(shares[pos]).toFixed(3)}`).join("_")}`);
    // JEG-527: season weeks only when they differ from the defaults (a default link stays short).
    const w = seasonWeeksState(false);
    const d = w && seasonWeeksState(true);
    if (w) {
      if (w.regularEnd !== d.regularEnd) parts.push(`regend=${w.regularEnd}`);
      if (w.playoffLo !== d.playoffLo || w.playoffHi !== d.playoffHi) parts.push(`playoffs=${w.playoffLo}-${w.playoffHi}`);
      if (w.optimize !== d.optimize) parts.push(`optimize=${w.optimize}`);
      if (w.content !== w.build) parts.push(`week=${w.content}`);
    }
    // JEG-1178: a week the reader picked travels with the link (wk=); the default week stays out of it.
    const weekState = C.getWeekState ? C.getWeekState() : null;
    if (weekState && weekState.selected && Number.isInteger(weekState.week)) parts.push(`wk=${weekState.week}`);
    // JEG-537: the advanced settings, only when they differ from the defaults (bso: 3 decimals; absent = off).
    const adv = advancedState(false);
    const advDefaults = adv && advancedState(true);
    if (adv) {
      if (adv.injuryHistory !== advDefaults.injuryHistory) parts.push(`inj=${adv.injuryHistory}`);
      if (adv.projectionConfidence !== advDefaults.projectionConfidence) parts.push(`conf=${adv.projectionConfidence}`);
      if (adv.benchShareOverride !== null) parts.push(`bso=${Number(adv.benchShareOverride).toFixed(3)}`);
    }
    return parts;
  }
  function tradeHash() {
    const keys = side => TR[side].map(p => encodeURIComponent(p.key)).join(",");
    const parts = [];
    if (TR.give.length) parts.push(`give=${keys("give")}`);
    if (TR.receive.length) parts.push(`get=${keys("receive")}`);
    if (parts.length) {
      parts.push(...leagueLinkParts());
      // JEG-1044: the reader's value basis and player overrides travel with the link (absent = ours / none).
      // Past the budget the player overrides drop out and the sender is told to use Export.
      const ov = window.DDFOverrides && window.DDFOverrides.shareParams ? window.DDFOverrides.shareParams() : null;
      shareDroppedOverrides = false;
      if (ov && ov.basis) parts.push(`basis=${ov.basis}`);
      if (ov && ov.ov) {
        if (parts.join("&").length + ov.ov.length + 4 > 1800) shareDroppedOverrides = true;
        else parts.push(`ov=${ov.ov}`);
      }
    }
    // JEG-1259: a pending carried trade stays in the address (reload and share keep it), with this visit's deal.
    if (carriedTrade) parts.push(`tc=${carriedTradeText()}`);
    return `#compare-trade${parts.length ? `?${parts.join("&")}` : ""}`;
  }
  let shareDroppedOverrides = false;
  function carriedTradeText() {
    const TC = window.TradeValueTradeContext;
    if (!TC || !compareCarried || compareCarried.status !== "ok") return carriedTrade.text;
    const deal = {give: TR.give.map(p => p.key).filter(Boolean), get: TR.receive.map(p => p.key).filter(Boolean)};
    const teams = compareCarried.context.teams;
    const patch = compareTeams.carriedSwapped ? {deal, mine: teams.theirs, theirs: teams.mine} : {deal};
    try { return TC.encodeTransfer(TC.toTransfer(TC.withChanges(compareCarried.context, patch))); }
    catch (error) { return carriedTrade.text; }
  }
  // Apply a link's scoring and roster when they differ from the reader's; say so.
  function applyLinkLeague(params) {
    const scoring = params.get("scoring");
    const roster = {};
    String(params.get("roster") || "").split(".").forEach(part => {
      const m = /^([A-Z]+)(\d+)$/.exec(part);
      const slot = m && LINK_ROSTER.find(([, code]) => code === m[1]);
      if (slot) roster[slot[0]] = Number(m[2]);
    });
    const shape = C.getRosterShape();
    const scoringChange = LINK_SCORING.includes(scoring) && scoring !== C.getState().scoring;
    const rosterChange = Object.entries(roster).filter(([key, value]) => key in shape && shape[key] !== value);
    // JEG-1026: a link's team count (8, 10, 12 or 14, the engine's own choices); anything else is ignored.
    const teams = Number(params.get("teams"));
    const teamsChange = [8, 10, 12, 14].includes(teams) && teams !== C.getState().teams;
    // JEG-537: advanced settings. A link that carries a league carries all three (missing ones mean the defaults).
    // Old links: bench=0.150 (the old default) means no override; any other bench= without bso= is the sender's override.
    let advChange = null;
    if (params.has("scoring") && hasAdvanced()) {
      const now = advancedState(false);
      const def = advancedState(true);
      const inj = params.get("inj");
      const conf = Number(params.get("conf"));
      let bso = params.has("bso") ? Number(params.get("bso")) : null;
      if (!params.has("bso") && params.has("bench")) {
        const old = Number(params.get("bench"));
        bso = Number.isFinite(old) && Math.abs(old - 0.15) > 5e-4 ? old : null;
      }
      const want = {injuryHistory: ["recent", "all"].includes(inj) ? inj : def.injuryHistory,
        projectionConfidence: [0.5, 1, 1.5].includes(conf) ? conf : def.projectionConfidence,
        benchShareOverride: Number.isFinite(bso) && bso !== null ? Math.min(0.30, Math.max(0.01, bso)) : null};
      if (JSON.stringify(want) !== JSON.stringify(now)) advChange = want;
    }
    const shares = {};
    String(params.get("shares") || "").split("_").forEach(part => {
      const m = /^(QB|RB|WR|TE)(\d*\.?\d+)$/.exec(part);
      if (m) shares[m[1]] = Number(m[2]);
    });
    const sharesGiven = Object.keys(shares).length === 4 && Boolean(C.setPositionWeights);
    // JEG-527: a link that carries a league also carries its season weeks; missing ones mean the defaults.
    const wkNow = params.has("scoring") ? seasonWeeksState(false) : null;
    let weeksChange = null;
    if (wkNow) {
      const wkDef = seasonWeeksState(true);
      const po = /^(\d+)-(\d+)$/.exec(params.get("playoffs") || "");
      const optimize = params.get("optimize") || wkDef.optimize;
      const week = params.has("week") ? Number(params.get("week")) : wkDef.build;
      const want = {build: wkDef.build, content: Number.isInteger(week) ? week : wkDef.build,
        regularEnd: params.has("regend") && Number.isInteger(Number(params.get("regend"))) ? Number(params.get("regend")) : wkDef.regularEnd,
        playoffLo: po ? Number(po[1]) : wkDef.playoffLo, playoffHi: po ? Number(po[2]) : wkDef.playoffHi,
        optimize: ["season", "regular", "playoffs"].includes(optimize) ? optimize : wkDef.optimize};
      if (JSON.stringify(want) !== JSON.stringify(wkNow)) weeksChange = want;
    }
    // JEG-1178: the week the sender picked. A week outside this league's transition falls back to the default.
    const linkWeek = params.has("wk") && Number.isInteger(Number(params.get("wk"))) ? Number(params.get("wk")) : null;
    const weekNow = C.getWeekState ? C.getWeekState() : null;
    const wkChange = linkWeek !== null && Boolean(C.setWeek) && (!weekNow || linkWeek !== weekNow.week || !weekNow.selected);
    if (!scoringChange && !teamsChange && !rosterChange.length && !advChange && !sharesGiven && !weeksChange && !wkChange) return;
    leagueInputs.source = "link";
    leagueInputs.notes = [];
    if (weeksChange) {
      const error = applySeasonWeeks(weeksChange);
      if (error) console.warn("Link season weeks ignored:", error);
    }
    if (scoringChange || teamsChange || rosterChange.length) {
      leagueChange(() => {
        if (scoringChange) C.setScoring(scoring);
        if (teamsChange) C.setTeams(teams);
        rosterChange.forEach(([key, value]) => C.setRosterSpot(key, value));
      });
    }
    // The link's week is read after the league: the setting decides which weeks exist.
    if (wkChange) { C.setWeek(linkWeek, false); rememberWeek(); refresh(); }
    // The link's advanced settings are the sender's choice, set after the league.
    if (advChange) {
      const error = applyAdvanced(advChange);
      if (error) console.warn("Link advanced settings ignored:", error);
      refresh();
    }
    // Shares last: a league change resets them to that league's defaults. A rejected set keeps them.
    if (sharesGiven) { C.setPositionWeights(shares, false); refresh(); }
    // JEG-1020: Find a trade reads the link's settings too. JEG-1380: a week-only link moves its results to that week.
    if (weeksChange || advChange || sharesGiven) announceLeagueChange("link");
    else if (wkChange) announceLeagueChange("week");
    announceInputs();
    const earlier = $("v2Status").hidden ? "" : ` ${$("v2Status").textContent}`;
    const linkBench = benchReadoutText(C.getBenchShareReadout ? C.getBenchShareReadout() : null);
    setStatus(`Opened with the link's league settings: ${$("v2LeagueName").textContent}, ${$("v2RosterLine").textContent}, `
      + `bench ${linkBench.missing ? "not available yet" : linkBench.short}.${earlier}`);
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => setStatus(""), 8000);
  }
  // JEG-1026: the three routes a DDF state's `view` can name (docs/design/llm-site-state.md), and the link parameters that
  // only the shared-state reader (ddf-assist.js) handles: a Find a trade link's rosters, a Trade targets link's player.
  const STATE_ROUTES = ["#compare-trade", "#trade-targets", "#find-trade"];
  const STATE_VIEW_ROUTE = {compare: "#compare-trade", targets: "#trade-targets", finder: "#find-trade"};
  function readTradeHash() {
    let [base, query] = location.hash.split("?");
    if (!query || !STATE_ROUTES.includes(base) && base !== "#waivers") return;
    let params = new URLSearchParams(query);
    // A link whose `view` names another of the three routes opens that route (the address says so, Back still works).
    const named = STATE_VIEW_ROUTE[params.get("view")];
    if (named && STATE_ROUTES.includes(base) && named !== base) {
      base = named;
      try { history.replaceState(history.state, "", location.pathname + location.search + base + "?" + query); } catch (error) { /* the state below still applies */ }
    }
    if (base === "#compare-trade") {
      endCompareEdit();
      const text = params.get("tc");
      carriedTrade = text ? {text, transfer: window.TradeValueTradeContext ? window.TradeValueTradeContext.decodeTransfer(text) : null} : null;
      compareCarried = null;
      compareTeams.carriedSwapped = false;
    }
    // JEG-894: a Find a trade search link (#find-trade?mine=..&theirs=..&size=..&km=..&kt=..) is the finder's own: it
    // sets the package size and the lineup ticks and runs the search, once the shared link path below has put the rosters in.
    // Apply value context before the shared reader resolves rows and starts the finder.
    if (base === "#find-trade" && window.DDFOverrides && window.DDFOverrides.applyLink) window.DDFOverrides.applyLink(params);
    if (base === "#find-trade" && window.TradeValueFinder && window.TradeValueFinder.applyHash) window.TradeValueFinder.applyHash(params);
    if (base !== "#compare-trade" && base !== "#waivers") {   // Find a trade and Trade targets links
      if (window.DDFAssist) window.DDFAssist.applyLink(query);
      return;
    }
    if (base === "#compare-trade" && (params.has("mine") || params.has("theirs") || params.has("target")) && window.DDFAssist) {
      window.DDFAssist.applyLink(query);   // a state with more than the trade: the codec reads all of it
      return;
    }
    // A name-only player (n:Ja'Marr%20Chase) is the codec's form. The shared reader resolves it;
    // the key reader below would show the encoded token as a missing player id.
    if (base === "#compare-trade" && window.DDFAssist && /(^|,)n:/i.test(`${params.get("give") || ""},${params.get("get") || ""}`)) {
      window.DDFAssist.applyLink(query);
      return;
    }
    if (base === "#waivers") { applyLinkLeague(params); return; }   // JEG-1022: the Waivers tab reads its own players from the link
    const rowsByKey = new Map(C.getAllRows().map(row => [String(row.player_key), row]));
    const seen = new Set();
    const read = name => (params.get(name) || "").split(",").map(token => {
      let k = token.trim();
      try { k = decodeURIComponent(k); } catch (error) { /* the token was already plain text */ }
      k = k.trim();
      if (!k || seen.has(k)) return null;
      seen.add(k);
      // Fallback when the shared reader is not on the page: show the name, not "n:Ghost%20Player".
      if (k.startsWith("n:")) {
        let playerName = k.slice(2);
        try { playerName = decodeURIComponent(playerName); } catch (error) { /* already decoded */ }
        return {key: "", name: playerName};
      }
      return {key: k, name: rowsByKey.get(k)?.name || `Player ${k}`};
    }).filter(Boolean);
    TR.give = read("give");
    TR.receive = read("get");
    applyLinkLeague(params);
    // JEG-1044: a link's basis and player overrides apply for this visit, with a banner and a one-click way back.
    if (window.DDFOverrides && window.DDFOverrides.applyLink) window.DDFOverrides.applyLink(params);
  }
  function syncTradeHash() {
    if (currentView() !== "compare") return;
    const want = tradeHash();
    if (location.hash !== want) history.replaceState(null, "", want);
  }
  async function copyTradeLink(button) {
    const url = location.href;
    const note = $("v2CShareNote");
    note.hidden = false;
    // JEG-894: "Copied" feedback on the button itself (on a phone the sticky bar sits far from the note).
    if (button) {
      if (!button.dataset.copyLabel) button.dataset.copyLabel = button.textContent;
      button.textContent = "Copied";
      clearTimeout(button.copyTimer);
      button.copyTimer = setTimeout(() => { button.textContent = button.dataset.copyLabel; }, 2000);
    }
    // JEG-1044: say what else the link carries, and when the player overrides did not fit.
    const carries = /[?&]basis=/.test(url) || /[?&]ov=/.test(url)
      ? " Your value basis and player overrides are in the link too; the reader can switch back to the default DDF Value in one click." : "";
    const dropped = shareDroppedOverrides && window.DDFOverrides ? ` ${window.DDFOverrides.dropOverridesNote()}` : "";
    try {
      await navigator.clipboard.writeText(url);
      note.textContent = "✓ Link copied. It opens this trade with your scoring, team count, roster, bench share and position shares."
        + carries + dropped;
    } catch (error) {
      note.textContent = `Copy this link: ${url}${dropped}`;
    }
  }

  function bindCompare() {
    window.TradeValueWorkspace?.store?.onChange(() => {
      if (currentView() === "compare") renderCompare();
    });
    $("v2CShare").addEventListener("click", () => copyTradeLink($("v2CShare")));
    $("v2CShare2").addEventListener("click", () => copyTradeLink($("v2CShare2")));
    // JEG-468: hover / focus tooltip for every waterfall step.
    const compare = $("v2Compare");
    const stepOf = event => event.target.closest && event.target.closest(".v2-wf-step, .v2-wf-land");
    compare.addEventListener("mouseover", event => { const el = stepOf(event); if (el) showStepTip(el); });
    compare.addEventListener("mouseout", event => { if (stepOf(event)) $("v2Tip").hidden = true; });
    compare.addEventListener("focusin", event => { const el = stepOf(event); if (el) showStepTip(el); });
    compare.addEventListener("focusout", event => { if (stepOf(event)) $("v2Tip").hidden = true; });
    compare.addEventListener("keydown", event => { if (event.key === "Escape" && stepOf(event)) $("v2Tip").hidden = true; });
    $("v2CTryExample").addEventListener("click", () => {
      const sample = compareView && verdictKey() ? exampleTrade(compareView.pointKeys) : null;
      if (!sample) return;
      const pick = list => list.map(row => ({key: String(row.player_key), name: row.name}));
      TR.give = pick(sample.give);
      TR.receive = pick(sample.receive);
      TR.example = {give: TR.give.map(p => p.key), receive: TR.receive.map(p => p.key)};
      TR.undo = null;
      renderCompare();
      $("v2GiveSearch").focus();
    });
    $("v2CVerdictBar").addEventListener("click", () => {
      const card = $("v2CVerdict");
      card.scrollIntoView({block: "center"});
      card.setAttribute("tabindex", "-1");
      card.focus({preventScroll: true});
    });
    if (window.IntersectionObserver) {
      new IntersectionObserver(entries => {
        TR.verdictInView = entries[entries.length - 1].isIntersecting;
        syncVerdictBar();
      }).observe($("v2CVerdict"));
    }
    if (narrowQuery && narrowQuery.addEventListener) narrowQuery.addEventListener("change", syncVerdictBar);
    ["give", "receive"].forEach(side => {
      const input = $(SIDE_IDS[side].search);
      window.TradeValueNameSearch.combobox(input, $(SIDE_IDS[side].results));   // JEG-900
      input.addEventListener("input", () => renderSearch(side));
      input.addEventListener("keydown", event => {
        if (event.key === "Enter") {
          event.preventDefault();
          const first = renderSearch(side)[0];
          if (first) addToSide(side, first);
        } else if (event.key === "Escape") {
          $(SIDE_IDS[side].results).hidden = true;
        }
      });
    });
    // JEG-1190: Clear trade, Clear side (each side) and Undo. Undo restores the sides as they were before the last Clear.
    const clearSides = sides => {
      TR.undo = {give: TR.give, receive: TR.receive, example: TR.example};
      sides.forEach(side => { TR[side] = []; });
      if (sides.length === 2) TR.open.clear();
      renderCompare();
      $(SIDE_IDS[sides[0]].search).focus();
    };
    $("v2CClear").addEventListener("click", () => clearSides(["give", "receive"]));
    $("v2GiveClear").addEventListener("click", () => clearSides(["give"]));
    $("v2GetClear").addEventListener("click", () => clearSides(["receive"]));
    $("v2CUndo").addEventListener("click", () => {
      if (!TR.undo) return;
      ({give: TR.give, receive: TR.receive, example: TR.example} = TR.undo);
      TR.undo = null;
      renderCompare();
      $("v2CClear").focus();
    });
    $("v2CSwap").addEventListener("click", () => {
      [TR.give, TR.receive] = [TR.receive, TR.give];
      [compareTeams.mineId, compareTeams.theirId] = [compareTeams.theirId, compareTeams.mineId];
      if (carriedTrade) compareTeams.carriedSwapped = !compareTeams.carriedSwapped;
      TR.undo = null;
      renderCompare();
    });
    // JEG-914: a disabled (held or unavailable) option is never applied, however the change arrives; the picker
    // stays on the series whose numbers the side lists show.
    $("v2CShown").addEventListener("change", event => {
      const picked = event.target.value;
      if (compareView && !compareView.shownChoices.includes(picked)) { renderShownPicker(); return; }
      TR.shown = picked;
      renderCompare();
    });
  }

  // ---------- How values work (frames 15 / 16) ----------
  // Explains the three views (docs/methodology.md, "The Three Views"). It adds no
  // numbers: the league line and the source lists come straight from the engine.
  function renderHow() {
    collect();
    renderHeader();
    $("v2HowLeague").textContent = $("v2LeagueName").textContent;
    $("v2HowRoster").textContent = $("v2RosterLine").textContent;
    const weights = C.getPositionWeights();
    $("v2HowWeights").textContent = ["QB", "RB", "WR", "TE"]
      .map(pos => `${pos} ${Number.isFinite(Number(weights[pos])) ? `${(Number(weights[pos]) * 100).toFixed(1)}%` : "—"}`).join(" · ");
    const benchRead = benchReadoutText(C.getBenchShareReadout ? C.getBenchShareReadout() : null);
    $("v2HowBench").textContent = benchRead.missing ? "—" : benchRead.short;
    $("v2HowBenchNote").hidden = true;
    $("v2HowBenchNote").textContent = "";
    let estimatedExplained = false;
    document.querySelectorAll("#v2How [data-sources]").forEach(list => {
      const method = list.dataset.sources;
      list.replaceChildren();
      view.info.filter(item => sourceMeta(item.key).method === method).forEach(item => {
        const meta = sourceMeta(item.key);
        const li = document.createElement("li");
        li.dataset.source = item.key;
        li.dataset.available = String(Boolean(item.available));
        const sym = document.createElement("span");
        sym.className = "v2-sym";
        sym.style.color = meta.color;
        sym.setAttribute("aria-hidden", "true");
        sym.textContent = `${meta.symbol} `;
        li.append(sym, document.createTextNode(PUBLISHER_NAMES[meta.publisher] || meta.label));
        const why = document.createElement("span");
        why.className = `v2-meta${item.stale ? " is-older" : ""}`;
        why.textContent = !item.available
          ? (item.paused ? " — waiting on fresh inputs" : " — not available for this league")
          : item.stale ? " · older week" : "";
        // V2-WAIVER-COVERAGE: a short chart's waiver line is extrapolated; say so here too.
        // JEG-541: the note is the engine's own text (it carries the engine's counts of estimated
        // players), so it sits in its own data-engine node, like the league card.
        if (item.available && item.waiverNote) {
          const note = document.createElement("span");
          note.dataset.engine = "waiver-note";
          note.textContent = ` · ${item.waiverNote}`;
          why.appendChild(note);
          // JEG-822: say once what "estimated" means (plain words, no numbers).
          if (!estimatedExplained && /estimated players/.test(item.waiverNote)) {
            estimatedExplained = true;
            const gloss = document.createElement("span");
            gloss.dataset.gloss = "estimated";
            gloss.textContent = " (estimated players are ones a chart does not list; we fill in a value for them from the other charts)";
            why.appendChild(gloss);
          }
        }
        if (why.textContent) li.appendChild(why);
        list.appendChild(li);
      });
    });
  }

  // ---------- Risers & fallers (frames 05 / 06) ----------
  // One exact series at a time: Δ = later week − earlier week, both recomputed by
  // the engine at the current setting (app/v2/movers.js does the subtraction).
  // The served pair uses the engine's rows for "now" and getPriorWeek for the week
  // before; an earlier pair (frame 19 #05: the N−1 → N control) uses getWeekValues
  // for both weeks. A series with no prior week is listed disabled with the reason.
  const RISERS_PAGE = 10;
  const R = {series: null, week: null, search: "", shown: {rise: RISERS_PAGE, fall: RISERS_PAGE}};
  let risersView = null;
  const weeksCache = new Map();   // series -> getHistoryWeeks result (the saved weeks do not change)
  const pairCache = new Map();    // "series:week" -> {prior, after} for an earlier week pair

  // Risers copy names each series in the JEG-474 group vocabulary.
  const priorLabel = key => groupSeriesName(key);
  // JEG-465: Risers & fallers opens on the DDF Value whenever the engine has its prior week.
  const RISERS_DEFAULT = DDF_KEY;

  // Week pairs the engine can price for a series: every saved week whose week before is
  // also saved, up to the week served now. Latest first.
  function weekPairs(key) {
    const info = weeksCache.get(key);
    if (!info || !Number.isInteger(info.servedWeek)) return [];
    const saved = new Set(info.weeks);
    return info.weeks.filter(week => week <= info.servedWeek && saved.has(week - 1)).reverse();
  }

  function loadPair(key, week) {
    const id = `${key}:${week}`;
    const stamp = priorStamp;
    return Promise.all([C.getWeekValues(key, week), C.getWeekValues(key, week - 1)])
      .catch(error => [{available: false, reason: error.message}, {available: false, reason: error.message}])
      .then(([after, before]) => {
        if (stamp !== priorStamp) return;
        const available = after.available && before.available;
        pairCache.set(id, {after, prior: {available, reason: available ? null : (after.available ? before.reason : after.reason),
          values: before.values, currentWeek: week, priorWeek: week - 1}});
      });
  }

  function renderRisers() {
    collect();
    renderHeader();
    renderUnpriced("v2RUnpriced", R.search);
    const M = window.TradeValueMovers;
    const loading = text => {
      $("v2RMeta").textContent = text;
      ["v2RRise", "v2RFall"].forEach(id => $(id).replaceChildren());
    };
    const missing = M.SERIES.filter(key => !priorCache.has(key));
    if (missing.length) {
      loading("Recomputing last week for your league…");
      priorsFor(M.SERIES).then(() => { if (currentView() === "risers") renderRisers(); });
      return;
    }
    // JEG-906: a held (hidden) source is never a basis for movement. Its prior week reads as unavailable with the
    // same reason the other pickers give (heldReason / unavailableReason, one rule), so the option is disabled and
    // a saved pick of it shows the held notice, never deltas built on held values. An amber (lagging) source is
    // available and stays offered, labelled by its week.
    const choices = M.SERIES.map(key => {
      const item = view.infoByKey[key];
      const prior = item && !item.available ? {available: false, reason: unavailableReason(item)} : priorCache.get(key);
      return {key, prior};
    });
    const offered = key => choices.some(c => c.key === key && !(view.infoByKey[key] && !view.infoByKey[key].available));
    if (!R.series || !offered(R.series)) {
      // JEG-498: the page opens on the first series ticked in its Customize (DDF Value by default) that has a prior week.
      const mineSeries = new Set(pageKeys("risers"));
      const ticked = choices.filter(c => mineSeries.has(c.key));
      R.series = (ticked.find(c => c.prior.available) || choices.find(c => c.key === RISERS_DEFAULT && c.prior.available)
        || choices.find(c => c.prior.available) || choices[0]).key;
    }
    renderSeriesPicker($("v2RSeries"), choices.filter(({key}) => ddfPickKey(key) === key).map(({key, prior}) => ({key,
      reason: prior.available ? null : view.infoByKey[key] && !view.infoByKey[key].available ? prior.reason
        : `no prior week: ${prior.reason || "not saved"}`})), R.series);
    $("v2RPosition").value = view.state.position;
    const servedPrior = priorCache.get(R.series);
    if (servedPrior.available && !weeksCache.has(R.series)) {
      loading("Reading the saved weeks…");
      Promise.resolve().then(() => C.getHistoryWeeks(R.series))
        .catch(error => ({servedWeek: null, weeks: [], reason: error.message}))
        .then(info => { weeksCache.set(R.series, info); if (currentView() === "risers") renderRisers(); });
      return;
    }
    // DDF Value: only the served pair is offered. The engine prices it over the same inputs on both
    // sides; two getWeekValues calls could average different inputs (Back-end requests).
    const pairs = servedPrior.available && !isDdfKey(R.series) ? weekPairs(R.series) : [];
    if (!pairs.includes(R.week)) R.week = servedPrior.available ? servedPrior.currentWeek : null;
    const weeks = $("v2RWeeks");
    weeks.replaceChildren();
    (pairs.length ? pairs : [R.week]).forEach(week => {
      const option = document.createElement("option");
      option.value = String(week);
      option.textContent = Number.isInteger(week) ? `Week ${week - 1} → Week ${week}` : "No week pair";
      weeks.appendChild(option);
    });
    weeks.value = String(R.week);
    weeks.disabled = pairs.length < 2;
    let prior = servedPrior;
    let source = C.getRows();
    if (servedPrior.available && R.week !== servedPrior.currentWeek) {
      const pair = pairCache.get(`${R.series}:${R.week}`);
      if (!pair) {
        loading(`Recomputing Weeks ${R.week - 1} and ${R.week} for your league…`);
        loadPair(R.series, R.week).then(() => { if (currentView() === "risers") renderRisers(); });
        return;
      }
      prior = pair.prior;
      const later = pair.after.values || {};
      source = source.map(row => ({...row, values: {...row.values, [R.series]: later[String(row.player_key)] ?? null}}));
    }
    // JEG-861: the page's one name matcher (reversed names, suffixes, typos), never a plain "contains".
    const needle = R.search.trim();
    const rows = needle ? window.TradeValueNameSearch.filter(source, needle) : source;
    risersView = M.buildMovers(rows, R.series, prior);
    risersView.searchMiss = Boolean(needle) && !rows.length;   // JEG-911: the search matched no name at all
    const label = priorLabel(R.series);
    const v = risersView;
    const group = seriesGroup(R.series);
    // DDF Value: both weeks average the same inputs, so say how many of them have the prior week.
    // JEG-807: count the sources the blend reads (`series`), not the pipeline pool (`inputs`, held ones included).
    const blendSeries = Array.isArray(prior.series) ? prior.series : prior.inputs;
    const ddfInputs = group === "ddf" && Array.isArray(prior.sources) && Array.isArray(blendSeries)
      ? ` · ${prior.sources.filter(key => blendSeries.includes(key)).length} of ${blendSeries.length} sources have a prior week` : "";
    $("v2RMeta").textContent = v.available
      ? `${label}${ddfInputs} · Change = Week ${v.currentWeek} − Week ${v.priorWeek}, both priced for your league. `
        + (group === "ddf" ? "A riser is worth more in a trade than last week; a faller is worth less."
          : group === "proj" ? "A projection moving is a change in that source's outlook."
            : "A riser now costs more from a manager who trades off this chart; a faller costs less.")
      : `No change to show for ${label}: ${v.reason}.`;
    // One bar scale for both lists, so a bar's length means the same number of points on either side.
    const shownItems = v.risers.slice(0, R.shown.rise).concat(v.fallers.slice(0, R.shown.fall));
    const scale = shownItems.reduce((max, item) => Math.max(max, Math.abs(item.delta)), 0);
    renderMoverList("rise", v.risers, scale);
    renderMoverList("fall", v.fallers, scale);
    $("v2RScale").textContent = scale > 0
      ? `Bars share a scale of ${scale.toFixed(1)} value points (the largest change shown). Missing history shows a dash: never a zero change.`
      : "Missing history shows a dash: never a zero change.";
    const notes = [];
    if (v.noPrior) notes.push(`${v.noPrior} player${v.noPrior === 1 ? "" : "s"} left out: not priced by ${label} in Week ${v.priorWeek}, so no change.`);
    if (v.noCurrent) notes.push(`${v.noCurrent} without a Week ${v.currentWeek} ${label} value.`);
    if (v.unchanged) notes.push(`${v.unchanged} unchanged (0.0).`);
    const unavailable = choices.filter(c => !c.prior.available);
    renderDisagreements(M, needle ? window.TradeValueNameSearch.filter(C.getRows(), needle) : C.getRows());
    if (group === "ddf" && Array.isArray(prior.dropped) && prior.dropped.length) {
      notes.push(`Left out of both weeks of this DDF Value change: ${prior.dropped.map(d => `${groupSeriesName(d.source)} (${d.reason})`).join("; ")}.`);
    }
    // JEG-1178: during a week transition a source that has not published this week is not in the blend, so it has no
    // change to show; each source in it is compared with its own previous week.
    const weekModel = group === "ddf" ? weekPickModel() : null;
    if (weekModel && weekModel.transition && weekModel.missing.length) {
      notes.push(`Skipped: ${nameList(weekModel.missing)} (not yet on Week ${weekModel.week}). Each source is compared with its own previous week.`);
    }
    const heldOut = unavailable.filter(c => view.infoByKey[c.key] && !view.infoByKey[c.key].available);
    const noPriorOut = unavailable.filter(c => !heldOut.includes(c));
    if (heldOut.length) notes.push(`Not offered: ${heldOut.map(c => `${priorLabel(c.key)} (${c.prior.reason})`).join("; ")}.`);
    if (noPriorOut.length) notes.push(`No prior week: ${noPriorOut.map(c => `${priorLabel(c.key)} (${c.prior.reason})`).join("; ")}.`);
    const note = $("v2RNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
  }

  // JEG-488 (RF-02): the two lists where Δ DDF Value and Δ DDF Value (projections) disagree (JEG-1073 names). Always the served
  // week pair for those two series (the Movement picker and the week pair above do not apply).
  const DISAGREE_SHOWN = 10;
  function renderDisagreements(M, rows) {
    const priorM = priorCache.get("ddf_value_charts");
    const priorP = priorCache.get("ddf_value_projections");
    const d = M.buildDisagreements(rows, priorM, priorP);
    const lists = [["market", "v2RMkt", "v2RMktEmpty"], ["projections", "v2RProj", "v2RProjEmpty"]];
    $("v2RDisagreeMeta").textContent = d.available
      ? `Week ${d.priorWeek} → Week ${d.currentWeek}, both priced for your league, like for like: a source without a saved prior week is left out of both weeks. `
        + `One moved ${M.MOVE} points or more and the other ${M.QUIET.toFixed(1)} or less, so one of the two is wrong. ${d.compared} players compared.`
      : `No comparison yet: ${d.reason}.`;
    lists.forEach(([kind, listId, emptyId]) => {
      const ol = $(listId);
      ol.replaceChildren();
      const list = d[kind];
      list.slice(0, DISAGREE_SHOWN).forEach(item => {
        const row = item.row;
        const li = document.createElement("li");
        li.dataset.playerKey = String(row.player_key);
        li.dataset.moved = item.moved;
        makeOpenable(li, () => openDrawer(row));
        const top = document.createElement("div");
        top.className = "m-top";
        const who = document.createElement("div");
        const name = document.createElement("b");
        name.textContent = row.name;
        const sub = document.createElement("span");
        sub.className = "v2-meta";
        sub.textContent = `${row.pos} · ${row.team || "Free agent"}`;
        who.append(name, sub);
        const big = document.createElement("div");
        big.className = `big ${item.direction === "up" ? "up" : "down"}`;
        big.dataset.col = "moved";
        const lead = item.moved === "market" ? item.market : item.projections;
        big.textContent = `${item.direction === "up" ? "▲" : "▼"} ${fmtGap(lead.delta)}`;
        top.append(who, big);
        const vals = document.createElement("div");
        vals.className = "v2-meta m-vals";
        const part = (label, delta, col) => {
          const span = document.createElement("span");
          span.dataset.col = col;
          span.textContent = `${label} ${fmtGap(delta)}`;
          return span;
        };
        vals.append(part("DDF Value", item.market.delta, "market"), document.createTextNode(" · "),
          part("DDF Value (projections)", item.projections.delta, "projections"));
        const read = document.createElement("div");
        read.className = "v2-dread";
        read.dataset.col = "read";
        read.textContent = item.read;
        li.append(top, vals, read);
        ol.appendChild(li);
      });
      rove(ol, "li[data-player-key]");
      const empty = $(emptyId);
      empty.hidden = list.length > 0;
      if (d.available && !rows.length && R.search.trim()) renderNoMatch(empty, R.search, "v2RSearch");
      else empty.textContent = d.available ? "No player moved this way this week." : "—";
      if (list.length > DISAGREE_SHOWN) {
        const more = document.createElement("li");
        more.className = "v2-meta v2-dmore";
        more.textContent = `${list.length - DISAGREE_SHOWN} more not shown`;
        ol.appendChild(more);
      }
    });
  }

  function renderMoverList(side, list, scale) {
    const ids = side === "rise" ? {list: "v2RRise", empty: "v2RRiseEmpty", more: "v2RRiseMore"}
      : {list: "v2RFall", empty: "v2RFallEmpty", more: "v2RFallMore"};
    const ol = $(ids.list);
    ol.replaceChildren();
    const v = risersView;
    list.slice(0, R.shown[side]).forEach(item => {
      const row = item.row;
      const li = document.createElement("li");
      li.dataset.playerKey = String(row.player_key);
      makeOpenable(li, () => openDrawer(row));
      const top = document.createElement("div");
      top.className = "m-top";
      const who = document.createElement("div");
      const name = document.createElement("b");
      name.textContent = row.name;
      appendEspnZero(name, row);
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = `${row.pos} · ${row.team || "Free agent"}`;
      who.append(name, sub);
      const big = document.createElement("div");
      big.className = `big ${item.delta > 0 ? "up" : "down"}`;
      big.dataset.col = "delta";
      big.textContent = `${item.delta > 0 ? "▲" : "▼"} ${fmtGap(item.delta)}`;
      top.append(who, big);
      const bottom = document.createElement("div");
      bottom.className = "m-bottom";
      const vals = document.createElement("span");
      vals.className = "v2-meta m-vals";
      vals.title = `Week ${v.priorWeek} → Week ${v.currentWeek}`;
      const before = document.createElement("span");
      before.dataset.col = "before";
      before.textContent = fmt(item.before);
      const now = document.createElement("span");
      now.dataset.col = "now";
      now.textContent = fmt(item.current);
      vals.append(before, document.createTextNode(" → "), now);
      const bar = document.createElement("span");
      bar.className = `m-bar ${item.delta > 0 ? "up" : "down"}`;
      bar.setAttribute("aria-hidden", "true");
      const fill = document.createElement("span");
      fill.style.width = `${scale > 0 ? Math.min(100, (Math.abs(item.delta) / scale) * 100) : 0}%`;
      bar.appendChild(fill);
      bottom.append(vals, bar);
      li.append(top, bottom);
      ol.appendChild(li);
    });
    rove(ol, "li[data-player-key]");
    const empty = $(ids.empty);
    empty.hidden = v.available && list.length > 0;
    if (v.available && v.searchMiss) renderNoMatch(empty, R.search, "v2RSearch");
    else empty.textContent = !v.available ? "No change to show for this source: see the note above."
      : `No player ${side === "rise" ? "rose" : "fell"} in ${priorLabel(R.series)} for this selection.`;
    const more = $(ids.more);
    more.hidden = list.length <= R.shown[side];
    more.textContent = `Show more ${side === "rise" ? "risers" : "fallers"} (${Math.min(R.shown[side], list.length)} of ${list.length})`;
  }

  function bindRisers() {
    let timer = null;
    const reset = () => { R.shown = {rise: RISERS_PAGE, fall: RISERS_PAGE}; };
    $("v2RSearch").addEventListener("input", event => {
      clearTimeout(timer);
      timer = setTimeout(() => { R.search = event.target.value; reset(); renderRisers(); }, 120);
    });
    $("v2RPosition").addEventListener("change", event => { C.setPosition(event.target.value); reset(); renderRisers(); });
    $("v2RSeries").addEventListener("change", event => { R.series = event.target.value; R.week = null; reset(); renderRisers(); });
    $("v2RWeeks").addEventListener("change", event => { R.week = Number(event.target.value); reset(); renderRisers(); });
    $("v2RRiseMore").addEventListener("click", () => { R.shown.rise += RISERS_PAGE; renderRisers(); });
    $("v2RFallMore").addEventListener("click", () => { R.shown.fall += RISERS_PAGE; renderRisers(); });
  }

  // ---------- routing ----------
  // A hash may carry a query (a shared trade: #compare-trade?give=1,2&get=3).
  // JEG-855: Manifesto, How values work and Research are sections of one Writing tab. The old routes
  // (#manifesto, #how-values, #research, #research/<slug>) still work: hashBase() reads them as their Writing
  // route, and canonicalizeHash() rewrites the address in place (replaceState, so Back skips the old route).
  const LEGACY_ROUTES = {"#manifesto": "#writing/manifesto", "#how-values": "#writing/how-values", "#research": "#writing/research"};
  LEGACY_ROUTES["#values-auditing/value-pie"] = "#values-auditing/health-check";   // JEG-1011: the Value pie tab is now the Health check
  const canonicalBase = base => LEGACY_ROUTES[base] || (base.startsWith("#research/") ? "#writing/" + base.slice(1) : base);
  const hashBase = () => canonicalBase(location.hash.split("?")[0]);
  // JEG-913: a hash no route claims (viewFor() gives null) lands on the default route and the address says so
  // (replaceState, so Back still works); its query goes with it. An empty hash is the landing page, not unknown.
  const DEFAULT_ROUTE = "#player-values";   // JEG-1106: new visitors land on the value chart (Jeremy, 2026-10-25)
  function canonicalizeHash() {
    const [base, ...query] = location.hash.split("?");
    // JEG-1094: a league share link (#find-trade?workspace=) now belongs to the league-wide screen.
    const legacy = base === "#find-trade" && /^workspace=/.test(query[0] || "") ? "#find-league" : canonicalBase(base);
    const unknown = base !== "" && viewFor(legacy) === null;
    const next = unknown ? DEFAULT_ROUTE : legacy;
    if (next === base) return;
    try { history.replaceState(history.state, "", location.pathname + location.search + next + (query.length && !unknown ? "?" + query.join("?") : "")); }
    catch (error) { /* the route still works through hashBase() */ }
  }
  // The Writing section on show: "manifesto" (also #writing alone and any unknown section), "how-values" or "research".
  const writingSection = () => {
    if (currentView() !== "writing") return "";
    const base = hashBase();
    return base === "#writing/how-values" ? "how-values" : (base === "#writing/research" || base.startsWith("#writing/research/")) ? "research" : "manifesto";
  };
  // The route table: the view a (canonical) hash base names, or null when no route claims it (JEG-913).
  const viewFor = base => (base === "#trade-targets" ? "targets"
    : base === "#risers-fallers" ? "risers"
    : base === "#compare-trade" ? "compare"
    : base === "#find-trade" ? "find"
    : base === "#find-league" ? "league"
    : base === "#waivers" ? "waivers"
    : base === "#value-overrides" ? "overrides"
    : (base === "#writing" || base.startsWith("#writing/")) ? "writing"
    : (base === "#values-auditing" || base.startsWith("#values-auditing/")) ? "audit"
    : base === "#player-values" ? "values" : null);
  const currentView = () => viewFor(hashBase()) || "values";   // landing: the value chart (Jeremy, 2026-10-25, JEG-1106; was Trade targets, 2026-10-08)

  // JEG-898: the page title names the view (and Writing / Values auditing section), plus the modal dialog when one is open.
  const BASE_TITLE = document.title;
  const VIEW_TITLES = {values: "Player values", targets: "Trade targets", risers: "Risers & fallers", compare: "Compare a trade", find: "Find a trade: your team", league: "Find a trade: league-wide", waivers: "Waivers", overrides: "Overrides"};
  const WRITING_TITLES = {"manifesto": "Manifesto", "how-values": "How values work", "research": "Research"};
  function syncTitle() {
    const v = currentView();
    const parts = [];
    const text = id => ($(id) && $(id).textContent || "").trim();
    if (!$("v2Expand").hidden) parts.push(text("v2ExpandTitle"));
    else if (!$("v2Drawer").hidden) parts.push(text("v2DrawerTitle"));
    else if (!$("v2Popover").hidden && $("v2Popover").querySelector("#v2PanelTitle")) parts.push(text("v2PanelTitle"));
    if (v === "writing") parts.push(WRITING_TITLES[writingSection()], "Writing");
    else if (v === "audit") {
      const slug = hashBase().startsWith("#values-auditing/") ? decodeURIComponent(hashBase().slice("#values-auditing/".length)) : "";
      if (slug) parts.push(slug.replace(/-/g, " ").replace(/^./, c => c.toUpperCase()));
      parts.push("Values auditing");
    } else parts.push(VIEW_TITLES[v]);
    document.title = parts.filter(Boolean).concat(BASE_TITLE).join(" \u00b7 ");
  }

  function applyRoute() {
    syncBasisLabels();
    const v = currentView();
    $("v2Main").hidden = v !== "values";
    $("v2Targets").hidden = v !== "targets";
    $("v2Compare").hidden = v !== "compare";
    $("v2Risers").hidden = v !== "risers";
    $("v2FindTrade").hidden = v !== "find";
    $("v2FindLeague").hidden = v !== "league";
    $("v2Waivers").hidden = v !== "waivers";   // JEG-1022
    $("v2How").hidden = writingSection() !== "how-values";
    $("v2Audit").hidden = v !== "audit";
    if ($("v2Overrides")) $("v2Overrides").hidden = v !== "overrides";   // JEG-1035
    applyStatic();
    // Context row hides on writing-only pages (manifesto, research) — handled by applyStatic().
    // JEG-498: every page with values has its own Customize. The finders read fixed sources (DDF Value and the trade
    // charts), so they, Waivers, Overrides and Values auditing show no "On the chart" basis and no Customize.
    const noShowing = v === "audit" || v === "find" || v === "league" || v === "waivers" || v === "overrides";
    $("v2EditSources").hidden = noShowing;
    document.querySelector(".v2-ctx-basis").classList.toggle("is-off", noShowing);
    // JEG-1106: the menu has one entry per page, and Writing / Values auditing list their sections, so the entry
    // on show is picked by its key ("values", "writing/research", "audit/single-source"), not by the view alone.
    const navKey = v === "writing" ? "writing/" + writingSection()
      : v === "audit" ? "audit/" + (hashBase().startsWith("#values-auditing/single-source") ? "single-source" : "health-check") : v;
    let navLabel = "";
    document.querySelectorAll(".v2-tab[data-key]").forEach(tab => {
      const on = tab.dataset.key === navKey;
      tab.classList.toggle("is-active", on);
      if (on) { tab.setAttribute("aria-current", "page"); navLabel = tab.textContent.trim(); }
      else tab.removeAttribute("aria-current");
    });
    $("v2NavCurrent").textContent = navLabel;
    closePopover();
    if (expanded && v !== "values") closeExpanded(true);
    $("v2Tip").hidden = true;
    refresh();
    syncTitle();
  }

  // ---------- wiring ----------
  function refreshValues() {
    collect();
    renderHeader();
    renderFilterChips();
    renderUnpriced("v2Unpriced", state.search);
    renderEmpty();
    renderNotice();
    renderTable();
    renderCharts();
  }

  // Frame 18: filters that leave no player say which filter did it.
  function renderEmpty() {
    const empty = !view.visible.length;
    $("v2Empty").hidden = !empty;
    $("v2Plot").hidden = empty && expanded !== "chart";   // the expanded chart keeps its brushes to widen again
    $("v2Chart").hidden = empty;
    $("v2TableCard").hidden = empty;
    if (!empty) return;
    const why = [];
    if (state.search.trim()) {
      why.push($("v2Unpriced").hidden ? `no player name matches “${state.search.trim()}”`
        : `no valued player name matches “${state.search.trim()}” (those with no value are listed above)`);
    }
    if (state.range.min !== null || state.range.max !== null) {
      why.push(`no ${sourceMeta(view.rankKey).short} value is in ${state.range.min ?? "…"}–${state.range.max ?? "…"}`);
    }
    if (view.state.position !== "ALL") why.push(`the position filter is ${view.state.position}`);
    if (view.rows.length && state.windowPreset !== SHOW_DEFAULT) why.push(`Show is set to ${$("v2Show").selectedOptions[0]?.textContent || state.windowPreset}`);
    const paused = !why.length && view.rankKey && isDdfKey(view.rankKey) ? ddfNoInputsReason(view.rankKey) : "";
    $("v2EmptyText").textContent = why.length ? `With these filters, ${why.join("; ")}.`
      : paused ? `${paused}, so ${sourceMeta(view.rankKey).short} shows — for every player. Search for a player to see why.`
        : "No player is priced for this selection.";
    const active = {search: Boolean(state.search.trim()), range: state.range.min !== null || state.range.max !== null,
      position: view.state.position !== "ALL"};
    document.querySelectorAll("#v2EmptyActions [data-clear]").forEach(button => { button.hidden = !active[button.dataset.clear]; });
    $("v2EmptyClear").hidden = Object.values(active).filter(Boolean).length < 2;
  }

  // Frame 18: "Only one comparable series" and "No current-week sources".
  function renderNotice() {
    const keys = view.plotKeys.filter(key => view.infoByKey[key]?.available);
    let text = "";
    if (keys.length && keys.every(key => view.infoByKey[key]?.stale)) {
      text = "No current-week values are selected. The values shown are from an older week and are labeled; choose a current-week source to compare.";
    } else if (keys.length === 1) {
      text = `Only one series is selected (${sourceMeta(keys[0]).short}). Choose another source to see where the sources disagree.`;
    }
    if (text !== noticeDismissedText) { noticeDismissedText = ""; }
    $("v2Notice").hidden = !text || noticeDismissedText === text;
    $("v2NoticeText").textContent = text;
  }
  let noticeDismissedText = "";

  // Settings popovers and shared-state changes call this; it redraws whichever tab is showing.
  // JEG-1044: the words that depend on the reader's basis (Overrides tab). With our methodology every string is the
  // one it always was; with another basis a "Rescaled" value says which basis it is rescaled to, and DDF Value says
  // it is not ours, so a reader is never misled about what a number means.
  const OURS_DEFAULT = "rooted in the trade charts, then adjusted for position weight and your league's rosters";
  function currentBasis() { return C && C.getBasis ? C.getBasis() : null; }
  function basisPhrase() {
    const b = currentBasis();
    if (!b || b.isDefault) return OURS_DEFAULT;
    return b.mode === "single" ? `${b.label} alone (your basis, not the default DDF Value)`
      : `${b.label} (your basis, not the default DDF Value), averaged for your league`;
  }
  function syncBasisLabels() {
    const b = currentBasis();
    const custom = Boolean(b && !b.isDefault);
    const to = custom ? ` (to ${b.label})` : "";
    RESCALED_TO = custom ? ` to ${b.label}` : "";
    SHORT_METHOD.indexed = `Market${to}`;
    PLAIN_METHOD.indexed = `Market${to}`;
    METHOD_COLUMNS[1][1] = `Market${to}`;
    METHOD_FULL.indexed = `Market${to}`;
    const pub = SERIES_GROUPS.find(g => g.id === "pub");
    pub.title = custom ? `Published charts (rescaled${to})` : "Published charts";
    pub.note = custom ? `Published trade-value opinions. Rescaled series use ${b.label}'s point scale for your league (your basis); adjusted series follow their own label.`
      : "Published trade-value opinions. Rescaled series use our point scale for your league; adjusted series follow their own label.";
    const observed = SERIES_GROUPS.find(g => g.id === "observed");
    observed.title = custom ? `Observed-trade estimates (rescaled${to})` : "Observed-trade estimates";
    observed.note = custom ? `Algorithmic estimates from completed trades. Rescaled series use ${b.label}'s point scale for your league (your basis); adjusted series follow their own label.`
      : "Algorithmic estimates from completed trades. Rescaled series use our point scale for your league; adjusted series follow their own label.";
    SERIES_GROUPS.find(g => g.id === "ddf").note = custom ? `DDF Value for each player, following your basis: ${basisPhrase()}.`
      : "DDF Value for each player: rooted in the trade charts, then adjusted for position weight and your league's rosters.";
    DDF_ROW_TIPS.ddf_value = custom ? `Your basis, not ours: ${basisPhrase()}. Change it on Overrides.` : `DDF Value: ${OURS_DEFAULT}.`;
    INFO_SPECS.indexed.lines = [custom ? `Each publisher's trade values, rescaled to ${b.label}'s point scale for your league (your basis, not the default DDF Value). Their ranking order is unchanged.` : INDEXED_INFO_DEFAULT];
    NAME_DEFS[0][1] = custom ? `Your estimate of what a player is worth, following your basis: ${basisPhrase()}.`
      : `What a player is worth in your league: ${OURS_DEFAULT}.`;
    INFO_SPECS.names.lines = NAME_DEFS.map(([name, text]) => [name, text]).concat([["", EDGE_DEF]]);
    document.querySelectorAll("[data-basis-ours]").forEach(node => { node.textContent = basisPhrase(); });
    const cap = $("v2TChartCaption");
    if (cap && cap.firstChild && cap.firstChild.nodeType === 3) cap.firstChild.nodeValue = custom ? `Rescaled to ${b.label}'s point scale ` : "Rescaled to our point scale ";
  }
  function refresh() {
    syncBasisLabels();
    if (currentView() === "targets") renderTargets();
    else if (currentView() === "risers") renderRisers();
    else if (currentView() === "compare") renderCompare();
    else if (writingSection() === "how-values") renderHow();
    else if (currentView() === "audit") renderAudit();
    else if (currentView() === "waivers") { collect(); renderHeader(); if (window.TradeValueWaivers && window.TradeValueWaivers.activate) window.TradeValueWaivers.activate(); }   // JEG-1022
    else if (currentView() === "overrides") { collect(); renderHeader(); if (window.DDFOverrides) window.DDFOverrides.render(); }   // JEG-1035
    else if (currentView() === "writing" || currentView() === "find" || currentView() === "league") { collect(); renderHeader(); }   // text only; the nav freshness still updates
    else refreshValues();
  }

  // Values auditing (JEG-847): #values-auditing/<slug> picks a sub-tab; an unknown slug shows the first.
  // Each sub-tab fills its own mount through DDFAudit (audit-pie.js, audit-source.js).
  function renderAudit() {
    collect(); renderHeader();
    // JEG-1044: the checks here were set on our methodology. Under another basis, say so.
    const basisNote = $("v2AuditBasisNote");
    const basis = currentBasis();
    if (basisNote) {
      basisNote.hidden = !basis || basis.isDefault;
      basisNote.textContent = basisNote.hidden ? "" : `Values are shown for your custom basis (${basis.label}). Diagnostics may differ from the default DDF Value, and the thresholds on these pages were set on the default DDF Value.`;
    }
    const slugs = window.DDFAudit ? window.DDFAudit.slugs : ["health-check", "single-source"];
    const asked = decodeURIComponent(hashBase().slice("#values-auditing/".length));
    const slug = hashBase().startsWith("#values-auditing/") && slugs.includes(asked) ? asked : slugs[0];
    document.querySelectorAll("#v2Audit .v2-audit-panel").forEach(node => { node.hidden = node.dataset.audit !== slug; });
    document.querySelectorAll("#v2AuditTabs .v2-subtab").forEach(tab => {
      if (tab.dataset.audit === slug) tab.setAttribute("aria-current", "page"); else tab.removeAttribute("aria-current");
    });
    const panel = document.querySelector('#v2Audit .v2-audit-panel[data-audit="' + slug + '"] .audit-root');
    if (window.DDFAudit && panel) window.DDFAudit.render(slug, panel, {slug, engine: C});
  }

  // Brushes and drags redraw once per frame.
  let valuesFrame = 0;
  function scheduleValues() {
    if (valuesFrame) return;
    valuesFrame = requestAnimationFrame(() => { valuesFrame = 0; if (currentView() === "values") refreshValues(); });
  }
  // JEG-483: the Show preset in force before a zoom or brush, so Reset zoom can return to it.
  function rememberPreset() {
    if (state.windowPreset !== "custom") state.zoomFrom = state.windowPreset;
  }
  // A Show preset (toolbar or the expanded chart's quick chips) ends any zoom.
  function applyPreset(preset) {
    state.windowPreset = preset;
    state.zoomFrom = null;
    state.rankZoom = false;
    state.window = null;
    state.shown = PAGE_SIZE;
  }
  // A brush, zoom or exact ranks: Show becomes "Custom lo–hi".
  function setWindow(win) {
    rememberPreset();
    state.window = win;
    state.windowPreset = "custom";
    state.rankZoom = true;
    state.shown = PAGE_SIZE;
    scheduleValues();
  }
  // The value range (Y brush or "Set exact values") composes with the rank window; Show reads Custom.
  // Clearing it while the rank window was never zoomed returns Show to the remembered preset.
  function setRange(range) {
    const on = range.min !== null || range.max !== null;
    if (on) rememberPreset();
    state.range = range;
    if (on) state.windowPreset = "custom";
    else if (state.windowPreset === "custom" && !state.rankZoom) applyPreset(state.zoomFrom || SHOW_DEFAULT);
    state.shown = PAGE_SIZE;
    scheduleValues();
  }
  // JEG-483 Reset zoom: undoes the zoom only (rank window and value range), back to the Show preset
  // from before it. Search, position, sort, Δ and Rank by stay.
  function resetZoom() {
    state.range = {min: null, max: null};
    applyPreset(state.zoomFrom || SHOW_DEFAULT);
    refresh();
  }
  // Clears the rank window only; a value range stays.
  function clearRankZoom() {
    state.rankZoom = false;
    state.window = null;
    if (!view || !view.rangeOn) applyPreset(state.zoomFrom || SHOW_DEFAULT);
    state.shown = PAGE_SIZE;
    refresh();
  }

  // JEG-483: a chip per active filter next to the toolbar; each ✕ clears exactly that filter.
  const trimNum = v => (Number.isInteger(v) ? String(v) : v.toFixed(1));
  function filterChips() {
    const chips = [];
    if (view.rangeOn) {
      const lo = state.range.min ?? view.yScale.lo;
      const hi = state.range.max ?? view.yScale.hi;
      chips.push({id: "range", text: `Value ${trimNum(lo)}–${trimNum(hi)}`, clear: () => setRange({min: null, max: null})});
    }
    if (state.windowPreset === "custom" && state.rankZoom) {
      chips.push({id: "ranks", text: `Ranks ${state.window[0]}–${state.window[1]}`, clear: clearRankZoom});
    }
    if (state.search.trim()) {
      chips.push({id: "search", text: `Search: ${state.search.trim()}`, clear: () => {
        state.search = ""; $("v2Search").value = ""; state.shown = PAGE_SIZE; refresh();
      }});
    }
    if (view.state.position !== "ALL") {
      chips.push({id: "position", text: `Position: ${view.state.position}`, clear: () => { C.setPosition("ALL"); refresh(); }});
    }
    return chips;
  }
  function renderFilterChips() {
    const box = $("v2FilterChips");
    const chips = filterChips();
    box.replaceChildren();
    chips.forEach(chip => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "v2-fchip";
      b.dataset.chip = chip.id;
      b.setAttribute("aria-label", `Clear filter ${chip.text}`);
      b.append(document.createTextNode(`${chip.text} `));
      const x = document.createElement("span");
      x.setAttribute("aria-hidden", "true");
      x.textContent = "✕";
      b.appendChild(x);
      b.addEventListener("click", () => {
        chip.clear();
        // Keep the keyboard near the chips: the first one left, else the search box.
        requestAnimationFrame(() => (box.querySelector("button") || $("v2Search")).focus());
      });
      box.appendChild(b);
    });
    box.hidden = !chips.length;
    // Reset zoom shows only while a zoom or brush has made Show Custom.
    $("v2ResetZoom").hidden = state.windowPreset !== "custom";
    document.querySelectorAll("#v2ExpandTools [data-xshow]").forEach(b => {
      const on = b.dataset.xshow === state.windowPreset;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    $("v2AxisZoom").setAttribute("aria-pressed", String(state.axisZoom));
    $("v2AxisZoom").textContent = `Y axis fits the value range · ${state.axisZoom ? "On" : "Off"}`;
  }

  // ---------- JEG-483 expanded chart / table ----------
  // The live plot (or table box) moves into one overlay and back, so ids, listeners and state stay single:
  // a brush in the expanded chart is the toolbar's brush. Desktop: a large panel over a scrim; below 768 px
  // full screen, as the settings panels are.
  let expandOpener = null;
  let expandHome = null;   // {node, placeholder}
  function openExpanded(kind, opener) {
    if (expanded) closeExpanded(true);
    closePopover();
    $("v2Tip").hidden = true;
    const node = kind === "chart" ? $("v2Plot") : $("v2TableWrap");
    expandOpener = opener || (kind === "chart" ? $("v2ExpandChart") : $("v2ExpandTable"));
    const placeholder = document.createElement("div");
    placeholder.className = "v2-expand-placeholder";
    placeholder.style.height = `${node.offsetHeight}px`;
    node.before(placeholder);
    expandHome = {node, placeholder};
    expanded = kind;
    const overlay = $("v2Expand");
    overlay.dataset.kind = kind;
    $("v2ExpandTitle").textContent = kind === "chart" ? "Trade value by player rank" : "All selected values";
    $("v2ExpandMeta").textContent = kind === "chart" ? "Drag either brush or pick a range; the table and the toolbar follow." : "";
    $("v2ExpandTools").hidden = kind !== "chart";
    $("v2ExpandBody").appendChild(node);
    overlay.hidden = false;
    document.body.classList.add("v2-expand-open");
    expandOpener.setAttribute("aria-expanded", "true");
    if (kind === "chart") renderCharts(); else renderTable();
    syncRotateHint();
    $("v2ExpandClose").focus();
  }
  // Phone full screen: a portrait phone gets a dismissible "rotate to landscape" prompt (no orientation lock: iOS Safari has none).
  // Dismissing it holds for the session; turning the phone sideways hides it too.
  let rotateDismissed = false;
  const rotateQuery = window.matchMedia ? window.matchMedia("(max-width: 767px) and (orientation: portrait)") : null;
  function rotateWasDismissed() {
    try { return sessionStorage.getItem("v2RotateHint") === "1" || rotateDismissed; } catch (error) { return rotateDismissed; }
  }
  function syncRotateHint() {
    const show = expanded === "chart" && Boolean(rotateQuery && rotateQuery.matches) && !rotateWasDismissed();
    $("v2RotateHint").hidden = !show;
  }
  function closeExpanded(silent) {
    if (!expanded) return;
    const kind = expanded;
    expanded = null;
    const {node, placeholder} = expandHome;
    placeholder.replaceWith(node);
    expandHome = null;
    $("v2Expand").hidden = true;
    document.body.classList.remove("v2-expand-open");
    $("v2Tip").hidden = true;
    $("v2RotateHint").hidden = true;
    if (currentView() === "values" && view) { if (kind === "chart") renderCharts(); else renderTable(); }
    const opener = expandOpener;
    expandOpener = null;
    if (opener) {
      opener.setAttribute("aria-expanded", "false");
      if (!silent) opener.focus();
    }
  }

  // JEG-475: one Reset for search, position, Show, value range, sort and Δ. Rank by, sources,
  // columns and league settings are selections, not filters, and stay.
  function resetValues() {
    state.search = ""; $("v2Search").value = "";
    state.range = {min: null, max: null};
    state.windowPreset = SHOW_DEFAULT; state.window = null;
    state.zoomFrom = null; state.rankZoom = false;
    state.sort = null; state.shown = PAGE_SIZE; state.delta = false;
    if (view && view.state.position !== "ALL") C.setPosition("ALL");
    if (view && view.infoByKey[DDF_KEY] && C.getRankSource() !== DDF_KEY) C.setLockOrder(DDF_KEY);
    refresh();
  }

  function bind() {
    let searchTimer = null;
    $("v2Search").addEventListener("input", event => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { state.search = event.target.value; state.shown = PAGE_SIZE; refresh(); }, 120);
    });
    $("v2Position").addEventListener("change", event => { C.setPosition(event.target.value); refresh(); });
    // JEG-926: search (and, in the expanded chart, position) on the graph itself: the same state, the same handlers.
    $("v2PlotSearch").addEventListener("input", event => {
      $("v2Search").value = event.target.value;
      $("v2Search").dispatchEvent(new Event("input", {bubbles: true}));
    });
    $("v2PlotPosition").addEventListener("change", event => {
      $("v2Position").value = event.target.value;
      $("v2Position").dispatchEvent(new Event("change", {bubbles: true}));
    });
    $("v2RankBy").addEventListener("change", event => { C.setLockOrder(event.target.value); state.sort = null; saveSelection(); refresh(); });
    $("v2DeltaBtn").addEventListener("click", () => {
      state.delta = !state.delta;
      refresh();
      if (state.delta) priorsFor(view.plotKeys.concat(view.vorpKeys)).then(() => { if (state.delta) refresh(); });
    });
    $("v2Show").addEventListener("change", event => {
      if (event.target.value === "custom") return;
      // JEG-926: "Set exact values…" is an item in this menu; it opens the value-range dialog and leaves Show as it was.
      if (event.target.value === "exact") { event.target.value = state.windowPreset; openRange(); return; }
      applyPreset(event.target.value);
      refresh();
    });
    // JEG-483: Reset zoom, expanded chart / table and their controls.
    $("v2ResetZoom").addEventListener("click", () => { resetZoom(); requestAnimationFrame(() => $("v2ZoomIn").focus()); });
    $("v2ExpandChart").addEventListener("click", () => openExpanded("chart"));
    $("v2FullScreen").addEventListener("click", () => { $("v2FullScreen").setAttribute("aria-expanded", "true"); openExpanded("chart", $("v2FullScreen")); });
    $("v2RotateDismiss").addEventListener("click", () => {
      rotateDismissed = true;
      try { sessionStorage.setItem("v2RotateHint", "1"); } catch (error) { /* held in memory above */ }
      syncRotateHint();
      $("v2ExpandClose").focus();
    });
    if (rotateQuery) (rotateQuery.addEventListener ? rotateQuery.addEventListener("change", syncRotateHint) : rotateQuery.addListener(syncRotateHint));
    // JEG-477: expand / contract the inline chart height (laptop default <-> tall).
    $("v2ChartSize").addEventListener("click", () => {
      const tall = $("v2Main").dataset.chartSize !== "tall";
      if (tall) $("v2Main").dataset.chartSize = "tall"; else delete $("v2Main").dataset.chartSize;
      const label = tall ? "Make chart shorter" : "Make chart taller";
      $("v2ChartSize").setAttribute("aria-pressed", String(tall));
      $("v2ChartSize").setAttribute("aria-label", label);
      $("v2ChartSize").title = label;
      renderCharts();
    });
    $("v2ExpandTable").addEventListener("click", () => openExpanded("table"));
    $("v2ExpandClose").addEventListener("click", () => closeExpanded());
    $("v2Expand").addEventListener("mousedown", event => { if (event.target === $("v2Expand")) closeExpanded(); });
    document.querySelectorAll("#v2ExpandTools [data-xshow]").forEach(button => {
      button.addEventListener("click", () => { applyPreset(button.dataset.xshow); refresh(); });
    });
    $("v2AxisZoom").addEventListener("click", () => { state.axisZoom = !state.axisZoom; refresh(); });
    $("v2More").addEventListener("click", openMore);
    $("v2Columns").addEventListener("click", openColumns);
    $("v2Reset").addEventListener("click", resetValues);
    $("v2EmptyClear").addEventListener("click", resetValues);
    $("v2NoticeBtn").addEventListener("click", event => openSources(event.currentTarget));
    $("v2NoticeClose").addEventListener("click", () => { noticeDismissedText = $("v2NoticeText").textContent; $("v2Notice").hidden = true; });
    document.querySelectorAll("#v2EmptyActions [data-clear]").forEach(button => {
      button.addEventListener("click", () => {
        const what = button.dataset.clear;
        if (what === "search") { state.search = ""; $("v2Search").value = ""; }
        if (what === "range") { setRange({min: null, max: null}); return; }
        if (what === "position") C.setPosition("ALL");
        state.shown = PAGE_SIZE;
        refresh();
      });
    });
    $("v2EditSources").addEventListener("click", event => openSources(event.currentTarget));
    $("v2EditLeague").addEventListener("click", openLeague);
    // JEG-1119: the context row's ⋯ menu (Position weights, Copy / Paste for ChatGPT/Claude).
    const setContextMenu = open => {
      $("v2ContextMenu").hidden = !open;
      $("v2ContextMore").setAttribute("aria-expanded", String(open));
    };
    $("v2ContextMore").addEventListener("click", () => {
      const open = $("v2ContextMenu").hidden;
      setContextMenu(open);
      if (open) { const first = [...$("v2ContextMenu").querySelectorAll("button")].find(b => b.offsetParent); if (first) first.focus(); }
    });
    // Capture phase: the menu closes before the item's own handler runs, so Position weights anchors to ⋯.
    $("v2ContextMenu").addEventListener("click", event => { if (event.target.closest("button")) setContextMenu(false); }, true);
    $("v2ContextMenu").addEventListener("keydown", event => {
      if (event.key === "Escape") { setContextMenu(false); $("v2ContextMore").focus(); }
    });
    document.addEventListener("click", event => {
      if (!$("v2ContextMenu").hidden && !event.target.closest(".v2-ctx-menuwrap")) setContextMenu(false);
    });
    // JEG-1134: the phone summary line opens and closes the rest of the context row (CSS renders it below 768 px only).
    // Leaving the phone layout closes it, so the open state never shows on a wider screen.
    {
      const summary = $("v2ContextSummary");
      const setSummary = open => {
        summary.setAttribute("aria-expanded", String(open));
        $("v2Context").classList.toggle("is-open", open);
        if (!open) setContextMenu(false);
      };
      summary.addEventListener("click", () => setSummary(summary.getAttribute("aria-expanded") !== "true"));
      window.matchMedia("(max-width: 767px)").addEventListener("change", event => { if (!event.matches) setSummary(false); });
    }
    $("v2Weights").addEventListener("click", openWeights);
    $("v2WeekSelect").addEventListener("change", event => {   // JEG-1178
      C.setWeek(Number(event.target.value));
      rememberWeek();
      refresh();
      announceLeagueChange("week");   // JEG-1380: Find a trade re-runs its results on the new week's values
    });
    $("v2Freshness").addEventListener("click", openFreshness);
    $("v2HowWeightsBtn").addEventListener("click", openWeights);
    // JEG-953: phone hamburger menu. The toggle only shows below the phone breakpoint (CSS); the menu is the same
    // nav element. It closes on selection, Escape (focus returns to the button) and a tap outside.
    {
      const header = document.querySelector(".v2-nav");
      const toggle = $("v2NavToggle");
      const setNav = (open, returnFocus) => {
        header.classList.toggle("is-open", open);
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.setAttribute("aria-label", open ? "Close menu" : "Menu");
        if (open) (document.querySelector(".v2-tab.is-active") || document.querySelector(".v2-tab")).focus();
        else if (returnFocus) toggle.focus();
      };
      toggle.addEventListener("click", () => setNav(!header.classList.contains("is-open"), true));
      $("v2Tabs").addEventListener("click", event => {
        const item = event.target.closest(".v2-tab");
        if (item && header.classList.contains("is-open")) setNav(false, false);
        if (item && item.dataset.action === "customize") openSources(toggle);   // Settings > Customize opens the sources dialog
      });
      // Arrow keys move through the entries (Home / End jump); Down on the closed button opens the menu.
      header.addEventListener("keydown", event => {
        const open = header.classList.contains("is-open");
        if (event.key === "ArrowDown" && !open && document.activeElement === toggle) { event.preventDefault(); setNav(true, false); return; }
        if (!open || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        const items = [...document.querySelectorAll("#v2Tabs .v2-tab")];
        const at = items.indexOf(document.activeElement);
        const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
          : event.key === "ArrowDown" ? (at + 1) % items.length : (at <= 0 ? items.length - 1 : at - 1);
        event.preventDefault();
        items[next].focus();
      });
      document.addEventListener("keydown", event => {
        if (event.key === "Escape" && header.classList.contains("is-open")) setNav(false, true);
      });
      document.addEventListener("pointerdown", event => {
        if (header.classList.contains("is-open") && !header.contains(event.target)) setNav(false, false);
      });
      window.addEventListener("hashchange", () => { if (header.classList.contains("is-open")) setNav(false, false); });
      // Leaving the phone layout (rotation, resize) must not leave the state open.
      window.matchMedia("(min-width: 768px) and (min-height: 501px), (min-width: 933px)").addEventListener("change", event => {
        if (event.matches && header.classList.contains("is-open")) setNav(false, false);
      });
    }
    // Season-value notice in the top bar (JEG-1023). Dismissed state lasts for the browser session; if storage is
    // blocked it lasts until reload. The notice stays in the markup either way, so it is read once, not announced per route.
    {
      const KEY = "v2.seasonNoticeDismissed";
      const header = document.querySelector(".v2-nav");
      const notice = $("v2SeasonNote");
      const more = $("v2SeasonNoteMore");
      const detail = $("v2SeasonNoteDetail");
      let dismissedInMemory = false;
      const wasDismissed = () => { try { return sessionStorage.getItem(KEY) === "1"; } catch (error) { return dismissedInMemory; } };
      const setDetail = open => {
        detail.hidden = !open;
        more.setAttribute("aria-expanded", open ? "true" : "false");
        more.textContent = open ? "Less" : "More";
      };
      const applyShown = () => {
        const shown = !wasDismissed();
        notice.hidden = !shown;
        header.classList.toggle("has-notice", shown);
        if (!shown) setDetail(false);
      };
      applyShown();
      more.addEventListener("click", () => setDetail(detail.hidden));
      $("v2SeasonNoteClose").addEventListener("click", () => {
        dismissedInMemory = true;
        try { sessionStorage.setItem(KEY, "1"); } catch (error) { /* in-memory flag above */ }
        applyShown();
        const main = [...document.querySelectorAll("main.v2-main")].find(m => !m.hidden) || $("v2Writing");
        if (main) { main.tabIndex = -1; main.focus(); }
      });
      document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !detail.hidden) { setDetail(false); more.focus(); }
      });
      document.addEventListener("pointerdown", event => { if (!detail.hidden && !notice.contains(event.target)) setDetail(false); });
    }
    $("v2HowWeightsExplainerBtn").addEventListener("click", event => {
      const button = event.currentTarget;
      const open = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(open));
      $("v2HowWeightsExplainerBody").hidden = !open;
    });
    // Skip link: a button, because a #fragment would change the hash route.
    $("v2Skip").addEventListener("click", () => {
      const main = [...document.querySelectorAll("main.v2-main")].find(m => !m.hidden);
      if (!main) return;
      main.tabIndex = -1;
      main.focus();
    });
    $("v2ShowMore").addEventListener("click", () => { state.shown += PAGE_SIZE; renderTable(); });
    // X rank brush: dragging sets Show to "Custom lo–hi" (JEG-475).
    const onBrush = () => {
      let lo = Number($("v2BrushLo").value);
      let hi = Number($("v2BrushHi").value);
      if (lo > hi) [lo, hi] = [hi, lo];
      setWindow([lo, hi]);
    };
    $("v2BrushLo").addEventListener("input", onBrush);
    $("v2BrushHi").addEventListener("input", onBrush);
    // Y value brush (JEG-472): live filter on the ranking series; the ends of the track mean open ended.
    const onYBrush = event => {
      const {lo: ylo, hi: yhi} = view.yScale;
      let lo = Number($("v2YBrushLo").value);
      let hi = Number($("v2YBrushHi").value);
      if (lo > hi) {
        if (event.target.id === "v2YBrushLo") lo = hi; else hi = lo;
        event.target.value = String(event.target.id === "v2YBrushLo" ? lo : hi);
      }
      setRange({min: lo <= ylo ? null : lo, max: hi >= yhi ? null : hi});
    };
    ["v2YBrushLo", "v2YBrushHi"].forEach(id => {
      $(id).addEventListener("input", onYBrush);
      // PageUp / PageDown jump a tenth of the scale; arrows step 0.5 (native).
      $(id).addEventListener("keydown", event => {
        if (event.key !== "PageUp" && event.key !== "PageDown") return;
        event.preventDefault();
        const input = event.currentTarget;
        const {lo: ylo, hi: yhi} = view.yScale;
        const jump = Math.max(0.5, Math.round((yhi - ylo) / 10 * 2) / 2);
        input.value = String(Math.max(ylo, Math.min(yhi, Number(input.value) + (event.key === "PageUp" ? jump : -jump))));
        onYBrush({target: input});
      });
    });
    const zoom = factor => {
      const n = view.rows.length;
      const [lo, hi] = state.window;
      const center = state.hoverIndex !== null && view.visible[state.hoverIndex] ? view.visible[state.hoverIndex].rank : (lo + hi) / 2;
      const span = Math.max(5, Math.min(n, Math.round((hi - lo + 1) * factor)));
      let nlo = Math.round(center - span / 2);
      nlo = Math.max(1, Math.min(n - span + 1, nlo));
      setWindow([nlo, Math.min(n, nlo + span - 1)]);
    };
    // JEG-503 (PV-06): grab the fill between a brush's two handles to move both ends together; the
    // width never changes. Shift+arrow on the fill is the keyboard equivalent (one rank / 0.5 value).
    const dragRange = (fillId, trackId, axis) => {
      const fill = $(fillId);
      fill.tabIndex = 0;
      fill.setAttribute("role", "group");
      fill.setAttribute("aria-label", axis === "x" ? "Move the whole rank range (Shift plus arrow keys)" : "Move the whole value range (Shift plus arrow keys)");
      const read = () => axis === "x"
        ? {lo: state.window[0], hi: state.window[1], min: 1, max: Math.max(1, view.rows.length), unit: 1}
        : {lo: Math.max(view.yScale.lo, state.range.min ?? view.yScale.lo), hi: Math.min(view.yScale.hi, state.range.max ?? view.yScale.hi),
          min: view.yScale.lo, max: view.yScale.hi, unit: 0.5};
      const apply = (start, delta) => {
        const width = start.hi - start.lo;
        let lo = start.lo + delta;
        lo = Math.max(start.min, Math.min(start.max - width, lo));
        const hi = lo + width;
        if (axis === "x") setWindow([Math.round(lo), Math.round(hi)]);
        else setRange({min: lo <= start.min ? null : lo, max: hi >= start.max ? null : hi});
      };
      let drag = null;
      fill.addEventListener("pointerdown", event => {
        if (event.button !== 0) return;
        const track = $(trackId).getBoundingClientRect();
        const start = read();
        if (!(start.max > start.min) || start.hi - start.lo >= start.max - start.min) return;   // the whole span: nothing to move
        const span = axis === "x" ? track.width : track.height;
        drag = {start, origin: axis === "x" ? event.clientX : event.clientY, perPx: (start.max - start.min) / Math.max(1, span)};
        fill.setPointerCapture(event.pointerId);
        fill.classList.add("is-dragging");
        event.preventDefault();
      });
      fill.addEventListener("pointermove", event => {
        if (!drag) return;
        const px = (axis === "x" ? event.clientX : event.clientY) - drag.origin;
        const raw = (axis === "x" ? px : -px) * drag.perPx;
        apply(drag.start, Math.round(raw / drag.start.unit) * drag.start.unit);
      });
      const end = event => {
        if (!drag) return;
        drag = null;
        fill.classList.remove("is-dragging");
        if (fill.hasPointerCapture(event.pointerId)) fill.releasePointerCapture(event.pointerId);
      };
      fill.addEventListener("pointerup", end);
      fill.addEventListener("pointercancel", end);
      fill.addEventListener("keydown", event => {
        if (!event.shiftKey) return;
        const step = {ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1}[event.key];
        if (!step) return;
        event.preventDefault();
        const start = read();
        apply(start, step * start.unit);
      });
    };
    dragRange("v2BrushFill", "v2Brush", "x");
    dragRange("v2YBrushFill", "v2YBrush", "y");
    // JEG-503 (PV-07): a legend entry turns that series' line and table column off and on.
    ["v2Legend", "v2ExpandLegend"].forEach(id => $(id).addEventListener("click", event => {
      const item = event.target.closest(".v2-legend-item");
      if (!item || item.disabled) return;
      const key = item.dataset.series;
      if (state.hiddenSeries.has(key)) state.hiddenSeries.delete(key); else state.hiddenSeries.add(key);
      refreshValues();
    }));
    $("v2ZoomIn").addEventListener("click", () => zoom(0.5));
    $("v2ZoomOut").addEventListener("click", () => zoom(2));
    bindChart("v2Chart", () => mainChart);
    bindChart("v2VorpChart", () => vorpChart);
    bindChartKeys();
    $("v2Scrim").addEventListener("click", () => { if (panelOpen) closePopover(); else closeDrawer(); });
    document.addEventListener("keydown", event => {
      if (event.key === "Tab") {
        const box = !$("v2Popover").hidden && panelOpen ? $("v2Popover") : !$("v2Drawer").hidden ? $("v2Drawer")
          : expanded ? $("v2Expand") : null;
        if (!box) return;
        const items = [...box.querySelectorAll("button, a[href], input, select, [tabindex='0']")]
          .filter(n => !n.disabled && n.offsetParent !== null);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (!box.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
        else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        return;
      }
      if (event.key !== "Escape") return;
      if (!$("v2Popover").hidden) closePopover();
      else if (!$("v2Drawer").hidden) closeDrawer();
      else if (expanded) closeExpanded();
    });
    $("v2Popover").addEventListener("pointerenter", () => { if (hoverOpened && hoverHold) hoverHold.cancel(); });
    $("v2Popover").addEventListener("pointerleave", () => { if (hoverOpened && hoverHold) hoverHold.schedule(); });
    document.addEventListener("pointerdown", event => {
      if (touchInspecting && event.pointerType !== "mouse" && !event.composedPath().some(node => node.id === "v2Chart" || node.id === "v2VorpChart")) clearTouchInspect();   // the path as dispatched: the hover dots under the finger are redrawn first
    });
    document.addEventListener("mousedown", event => {
      const pop = $("v2Popover");
      if (pop.hidden || pop.contains(event.target) || (popoverAnchor && popoverAnchor.contains(event.target))) return;
      closePopover();
    });
    let resizeTimer = null;
    // A scroll closes the tip, except the small one a tap or focus itself causes just after opening it.
    window.addEventListener("scroll", () => { if (Date.now() - mathTipOpenedAt > 500) hideMathTip(); }, true);
    document.addEventListener("keydown", event => { if (event.key === "Escape") hideMathTip(); });
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { if (currentView() === "values") renderCharts(); }, 100);
    });
    window.addEventListener("hashchange", () => { canonicalizeHash(); readTradeHash(); applyRoute(); });
    // Dialogs open and close by toggling `hidden`; the title follows them.
    if (window.MutationObserver) {
      const titleWatch = new MutationObserver(syncTitle);
      ["v2Popover", "v2Drawer", "v2Expand"].forEach(id => titleWatch.observe($(id), {attributes: true, attributeFilter: ["hidden"]}));
    }
    if (darkQuery && darkQuery.addEventListener) darkQuery.addEventListener("change", () => { if (C) refresh(); });
    if (narrowQuery && narrowQuery.addEventListener) narrowQuery.addEventListener("change", () => { if (C) refresh(); });
    if (metaWideQuery && metaWideQuery.addEventListener) metaWideQuery.addEventListener("change", () => { if (C && currentView() === "values") renderTable(); });
    bindTargets();
    bindCompare();
    window.addEventListener("trade-value-shared-change", () => { if (C) refresh(); });
    // New rows (league, weights, sources): every prior-week recompute is stale.
    window.addEventListener("trade-value-rows-change", () => {
      unpricedCache.clear();
      priorCache.clear();
      pairCache.clear();
      priorStamp += 1;
      if (!C) return;
      if (currentView() === "risers") renderRisers();
      else if (state.delta && currentView() === "values") {
        refresh();
        priorsFor(view.plotKeys.concat(view.vorpKeys)).then(() => { if (state.delta) refresh(); });
      }
    });
    bindRisers();
  }

  // JEG-1026: what ddf-assist.js (Copy link, state links) may read and change on this page.
  // A narrow set of hooks, so the assist code never reaches into this file's state.
  function attachAssist() {
    if (!window.DDFAssist) return;
    const VIEW_NAME = {compare: "compare", targets: "targets", find: "finder"};
    window.DDFAssist.attach({
      engine: C,
      view: () => VIEW_NAME[currentView()] || "",
      leagueQuery: () => leagueLinkParts().join("&"),
      applyLinkLeague,
      leagueText: () => `${$("v2LeagueName").textContent}, ${$("v2RosterLine").textContent}`,
      sources: () => C.getActiveSources(),
      getTrade: () => ({give: TR.give.map(p => ({...p})), get: TR.receive.map(p => ({...p}))}),
      setTrade: (give, get) => { endCompareEdit(); TR.give = give; TR.receive = get; if (currentView() === "compare") renderCompare(); },
      getTarget: () => T.search,
      setTarget: name => {
        T.search = name;
        $("v2TSearch").value = name;
        T.shown = {sell: TARGETS_TOP, buy: TARGETS_TOP};
        T.expanded = {sell: new Set(), buy: new Set()};
        if (currentView() === "targets") renderTargets();
      },
      // Show the route and re-render it (the same hash does not fire hashchange).
      go: route => {
        if (location.hash.split("?")[0] === route) { applyRoute(); return; }
        location.hash = route;
      },
      say: (text, ms) => {
        setStatus(text);
        clearTimeout(statusTimer);
        statusTimer = setTimeout(() => setStatus(""), ms || 8000);
      },
    });
  }

  async function start() {
    document.body.classList.add("v2");
    canonicalizeHash();
    bindManifesto();
    try {
      C = await waitForEngine();
    } catch (error) {
      showFailure(error.message);
      return;
    }
    // JEG-1035: saved value overrides apply before the first view renders, so every tab shows them from the start.
    if (window.DDFOverrides) window.DDFOverrides.boot(C);
    leagueDefaults = {scoring: C.getState().scoring, teams: C.getState().teams, roster: {...C.getRosterShape()}};
    try { leagueDefaultSnapshot = JSON.stringify(leagueSnapshot()); } catch (error) { leagueDefaultSnapshot = ""; }
    restoreLeagueSettings();
    restoreWeek();   // JEG-1178: the week picked earlier in this session; a link's wk= overrides it below
    applyStartSelection();
    loadPipeline();
    loadSourcePages();
    bind();
    setStatus("");
    attachAssist();   // JEG-1026: before the link is read, which may carry a whole DDF state
    readTradeHash();   // may set a status: a shared link's league settings were applied
    $("v2State").hidden = true;
    applyRoute();
    window.TradeValueV2 = {state, view: () => view, targets: () => targetsView, targetState: T,
      compare: () => compareView, tradeState: TR,
      // JEG-1022: the Waivers link carries the same league settings as a shared trade.
      leagueQuery: () => leagueLinkParts().join("&"), applyLinkLeague,
      // Where the league settings in force came from, for the status strip at the top (inputs-status.js).
      leagueInputs: () => ({...leagueInputs, notes: leagueInputs.notes.slice(), label: $("v2LeagueName").textContent}),
      // JEG-483: the drawn main chart (keys, rows, scale) and which view is expanded.
      chart: () => mainChart, expanded: () => expanded,
      weekPick: weekPickModel,
      risers: () => risersView, risersState: R, priors: () => Object.fromEntries(priorCache),
      // JEG-872: the one source name map (symbol + label) the audit tabs read, so every tab says the same names.
      publishers: () => PUBLISHERS,
      // The shown series, DDF Value included (it has no engine toggle); setShown is what Customize's Done does.
      shown: () => ddfShownList().concat(C.getActiveSources()),
      setShown: keys => { applyShown(keys); refresh(); },
      // JEG-498: the other pages' Customize lists (what their Done saves).
      pageKeys, setPageKeys: (page, keys) => { savePageKeys(page, keys); refresh(); }};
    announceInputs();   // after the object above: the status strip reads TradeValueV2.leagueInputs()
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
