// Overrides tab: the value basis (JEG-1044) and per-player value overrides (JEG-1035).
//
// JEG-1044 (Jeremy, 2026-10-24): "if someone wants to use the toolset tied to fantasycalc or any other trade source,
// or blended, with their weights and values, there is a way to do that. We default to our methodology but allow
// users to move away from it." The basis section (top of the tab) picks what DDF Value means everywhere: our
// methodology (the four trade charts, adjusted, equal weight; JEG-1073), any one source, or a blend with whole-percent
// weights over any subset. The engine applies it live: TradeValueCurveControls.setBasis(config). Player overrides
// are global: they stay when the basis changes. The old Customize "DDF blend" tab is gone; its saved choice is
// carried over here once.
//
// JEG-1035 (Jeremy, 2026-10-24): "select a player and say their ddf is actually a different value. Make it
// interactive so it opens a graph and as you drag the selector it shows the players that player is comparable to.
// Make it have a default filter for same position ... adjust as many players as we want to and have it permeate
// through the full dashboard."
//
// The engine owns the math: TradeValueCurveControls.setBasis(config) and setValueOverrides({player_key: value})
// change DDF Value on the rows, and every view reads rows. This module only picks the basis and the values (search,
// a graph with a draggable value line, the players nearest that value) and keeps them in the browser
// (localStorage).
//
// Contract: window.DDFOverrides = {boot(engine), render(), count(), all(), basis(), shareParams(), applyLink(params)}.
//   boot(engine)  v2.js calls it once the engine is ready, before the first view renders, so the saved basis and
//                 overrides apply everywhere from the first paint.
//   render()      v2.js calls it when the Overrides tab shows; idempotent.
//   shareParams() the basis and overrides as share-link parameters ({basis, ov, dropped}).
//   applyLink(p)  reads them back for the recipient (URLSearchParams). They apply in memory for the visit and are
//                 never saved until the recipient changes something on this tab.
(function (root) {
  "use strict";

  const SAVE_KEY = "ddf-v2-value-overrides";
  // The retired Customize "DDF blend" tab kept its choice inside the selection record (v2.js SAVE_KEY).
  const LEGACY_SELECTION_KEY = "ddf.v2.selection";
  // A shared link's settings live for the visit only: sessionStorage survives the page reloads some tab clicks
  // cause, and is gone when the tab closes. Never localStorage.
  const LINK_KEY = "ddf-v2-link-state";
  const POSITIONS = ["QB", "RB", "WR", "TE"];
  const NEAR = 4;   // comparable players shown above and below the chosen value
  const BASIS_SOURCES = [
    ["espn", "ESPN"], ["cbsros", "CBS rest of season"], ["razzball", "Razzball"],
    ["fantasycalc", "FantasyCalc"], ["usatoday", "USA Today"], ["fantasypros", "FantasyPros"], ["cbs", "CBS trade chart"]];
  const BASIS_KEYS = BASIS_SOURCES.map(item => item[0]);
  const SINGLE_ORDER = ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn", "cbsros", "razzball"];
  // JEG-1073 (Jeremy, 2026-10-25): our methodology is the four trade charts' Adjusted values, equal weight; the
  // projections are the alternate. The legacy DDF blend tab (JEG-1044) chose among the projections.
  const DEFAULT_SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs"];
  const LEGACY_PROJECTIONS = ["espn", "cbsros", "razzball"];
  const labelOf = key => (BASIS_SOURCES.find(item => item[0] === key) || [key, key])[1];
  const LINK_BUDGET = 1800;   // characters of share-link hash; past this the link drops the player overrides
  const PACK_AFTER = 6;       // more overrides than this are packed in the link

  const S = {engine: null, values: {}, names: {}, selected: null, draft: null, scope: "pos", query: "", dragging: false,
    // JEG-1044: mode is what the picker shows (default | single | blend). blend holds every source's tick and
    // weight, so a source can be ticked off and on again without losing its weight.
    mode: "default", single: "fantasycalc", blend: null, session: false, notice: null, undo: null, linkSig: null,
    linkNote: null, applyTimer: null, exportHint: false, importNote: ""};

  const $ = id => document.getElementById(id);
  const finite = v => typeof v === "number" && Number.isFinite(v);
  const fmt = v => (finite(v) ? (Math.abs(v) < 0.05 ? "0.0" : v.toFixed(1).replace("-", "−")) : "—");
  const signed = v => (finite(v) ? (Math.abs(v) < 0.05 ? "0.0" : (v > 0 ? "+" : "−") + Math.abs(v).toFixed(1)) : "—");
  const round1 = v => Math.round(v * 10) / 10;
  // JEG-1058: an override is either an absolute value (a number) or an adjustment
  // to the pipeline's own value ({type: "adjustment", delta}). The fixed-pie scale
  // caps what an override can say (spec 3.6).
  const OVERRIDE_MIN = 0;
  const OVERRIDE_MAX = 100;
  const isAdjustment = entry => !!(entry && typeof entry === "object" && entry.type === "adjustment");
  // JEG-1058: every override that arrives from outside the editor (a share
  // link, an import, a saved record) is put on the scale the editor shows: an
  // absolute value between 0 and 100, an adjustment within the scale's span.
  // The value it produces is the same either way, because the result is
  // capped anyway; the adjustment is capped so it always fits a packed link.
  const clampOverrideValue = v => round1(Math.min(OVERRIDE_MAX, Math.max(OVERRIDE_MIN, v)));
  const clampOverrideDelta = d => round1(Math.min(OVERRIDE_MAX, Math.max(-OVERRIDE_MAX, d)));
  function normalizeEntry(entry) {
    if (isAdjustment(entry)) {
      const delta = Number(entry.delta);
      if (!Number.isFinite(delta) || delta === 0) return null;
      return {type: "adjustment", delta: clampOverrideDelta(delta)};
    }
    if (!finite(entry) || entry < OVERRIDE_MIN) return null;
    return clampOverrideValue(entry);
  }
  function el(tag, attrs, kids) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    });
    (kids || []).forEach(kid => kid !== null && kid !== undefined && node.append(kid));
    return node;
  }
  const SVG_NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, text) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ---------- the basis the picker holds ----------
  function blankBlend() {
    const out = {};
    BASIS_KEYS.forEach(key => { out[key] = {on: DEFAULT_SOURCES.includes(key), w: 25}; });
    return out;
  }
  S.blend = blankBlend();
  const clampWeight = v => Math.min(100, Math.max(1, Math.round(Number(v) || 1)));
  // A saved or linked record -> the picker's state. Unknown sources are dropped; a record with nothing usable reads
  // as our methodology. Returns the sources it dropped.
  function setBasisState(rec) {
    const dropped = [];
    S.mode = "default";
    S.blend = blankBlend();
    if (!rec || typeof rec !== "object" || !rec.mode || rec.mode === "default") return dropped;
    if (rec.mode === "single") {
      if (BASIS_KEYS.includes(rec.source)) { S.mode = "single"; S.single = rec.source; }
      else if (rec.source) dropped.push(String(rec.source));
      return dropped;
    }
    if (rec.mode === "blend") {
      const named = Array.isArray(rec.sources) ? rec.sources : Object.keys(rec.weights || {});
      const blend = blankBlend();
      BASIS_KEYS.forEach(key => { blend[key].on = false; });
      named.forEach(key => {
        if (!BASIS_KEYS.includes(key)) { dropped.push(String(key)); return; }
        const w = rec.weights && rec.weights[key] !== undefined ? rec.weights[key] : 1;
        blend[key] = {on: true, w: clampWeight(w)};
      });
      if (BASIS_KEYS.some(key => blend[key].on)) { S.mode = "blend"; S.blend = blend; }
    }
    return dropped;
  }
  // The picker's state -> the record that is saved, exported and sent to the engine.
  function basisRecord() {
    if (S.mode === "single") return {mode: "single", source: S.single};
    if (S.mode === "blend") {
      const on = BASIS_KEYS.filter(key => S.blend[key].on);
      return {mode: "blend", sources: on, weights: Object.fromEntries(on.map(key => [key, S.blend[key].w]))};
    }
    return {mode: "default"};
  }
  const engineBasis = () => (S.mode === "default" ? null : basisRecord());
  const basisInfo = () => (S.engine && S.engine.getBasis ? S.engine.getBasis() : null);

  // ---------- storage ----------
  // v1 (JEG-1035): {values, names}. v2 (JEG-1044): adds basis. A v1 record reads as our methodology; the retired
  // Customize DDF blend choice (ddf.v2.selection.inputs) is carried over once when no v2 basis exists.
  // JEG-1058: a value is an absolute number or an adjustment {type: "adjustment", delta}.
  // Anything that arrives from outside the editor is put on the scale first.
  function readOverride(entry) {
    return normalizeEntry(entry);
  }
  function load() {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "null"); } catch (error) { /* private mode or bad JSON: start empty */ }
    if (saved && (saved.v === 1 || saved.v === 2) && saved.values && typeof saved.values === "object") {
      S.values = {};
      Object.entries(saved.values).forEach(([k, v]) => { const entry = readOverride(v); if (entry !== null) S.values[k] = entry; });
      S.names = saved.names && typeof saved.names === "object" ? saved.names : {};
    }
    if (saved && saved.v === 2 && saved.basis) setBasisState(saved.basis);
    else migrateLegacyBlend();
  }
  function saveLinkState(extra) {
    try {
      if (!S.session) { sessionStorage.removeItem(LINK_KEY); return; }
      sessionStorage.setItem(LINK_KEY, JSON.stringify({sig: S.linkSig, note: S.linkNote, ...extra}));
    } catch (error) { /* private mode: the link's settings last until the page reloads */ }
  }
  function restoreLinkState() {
    let rec = null;
    try { rec = JSON.parse(sessionStorage.getItem(LINK_KEY) || "null"); } catch (error) { return; }
    if (!rec || typeof rec !== "object") return;
    S.session = true;
    S.linkSig = rec.sig || null;
    S.linkNote = rec.note || null;
    S.linkExtra = {basis: rec.basis || null, values: rec.values || null, ours: Boolean(rec.ours)};
    if (rec.ours) { setBasisState(null); S.values = {}; S.names = {}; return; }
    if (rec.basis) setBasisState(rec.basis);
    if (rec.values) Object.entries(rec.values).forEach(([key, v]) => { const entry = normalizeEntry(v); if (entry !== null) S.values[key] = entry; });
  }
  function save() {
    if (S.session) return;   // a shared link's settings stay in memory until the reader changes something
    try { localStorage.setItem(SAVE_KEY, JSON.stringify({v: 2, basis: basisRecord(), values: S.values, names: S.names})); }
    catch (error) { /* the settings still apply for this visit */ }
  }
  function migrateLegacyBlend() {
    let record = null;
    try { record = JSON.parse(localStorage.getItem(LEGACY_SELECTION_KEY) || "null"); } catch (error) { return; }
    const inputs = record && Array.isArray(record.inputs) ? record.inputs.filter(key => LEGACY_PROJECTIONS.includes(key)) : [];
    if (!inputs.length) return;
    // The old default (every projection ticked) is gone with JEG-1073; any projections they ticked carry over as
    // the same equal-weight average of what was ticked.
    if (inputs.length) {
      setBasisState({mode: "blend", sources: inputs, weights: Object.fromEntries(inputs.map(key => [key, 1]))});
      S.notice = "The DDF blend control has moved to the Overrides tab, with more options. Your previous selection has been carried over.";
    }
    try {
      record.inputs = null;
      localStorage.setItem(LEGACY_SELECTION_KEY, JSON.stringify(record));
    } catch (error) { /* the carried-over basis still applies */ }
    save();
  }

  // ---------- engine ----------
  const rows = () => (S.engine ? S.engine.getAllRows() : []);
  const rowOf = key => {
    const hit = rows().find(r => String(r.player_key) === String(key));
    if (hit) return hit;
    const found = S.engine && S.engine.searchPlayers ? S.engine.searchPlayers(S.names[key] || "", {limit: 20}) : [];
    return found.find(r => String(r.player_key) === String(key)) || null;
  };
  // The model's DDF Value for a row, before any player override (under the current basis).
  const modelValue = row => (row ? (finite(row.ddfPipelineValue) ? row.ddfPipelineValue : (row.valueOverride === null || row.valueOverride === undefined ? row.values.ddf_value : null)) : null);
  // The pipeline's own value for a player: 0 when no source prices him, so an
  // adjustment then says what he is worth, not what he is worth more than.
  const pipelineValue = row => (row && finite(row.ddfPipelineValue) ? row.ddfPipelineValue : 0);
  // JEG-1058: what an override means for a player: the absolute value, or the
  // pipeline's value plus the adjustment, clamped to the fixed-pie scale.
  function effectiveValue(row, entry) {
    if (entry === null || entry === undefined) return null;
    if (isAdjustment(entry)) {
      const delta = Number(entry.delta);
      if (!Number.isFinite(delta)) return null;
      return Math.min(OVERRIDE_MAX, Math.max(OVERRIDE_MIN, pipelineValue(row) + delta));
    }
    return finite(entry) ? clampOverrideValue(entry) : null;
  }
  // JEG-1059: the badge that marks a value the reader set, next to the value itself.
  // The wording is the spec's: "You set this player's value to 58.0 (was 53.0 from
  // DDF Value). Reset on the Overrides tab." A player no source prices has no DDF Value to
  // compare with, so the "(was ...)" clause is left out rather than filled with a dash.
  function flag(row) {
    if (!row || row.valueOverride === null || row.valueOverride === undefined) return null;
    const base = modelValue(row);
    const text = finite(base)
      ? `You set this player's value to ${fmt(row.valueOverride)} (was ${fmt(base)} from DDF Value). Reset on the Overrides tab.`
      : `You set this player's value to ${fmt(row.valueOverride)}. Reset on the Overrides tab.`;
    const adjustment = row.valueOverrideSpec && row.valueOverrideSpec.type === "adjustment";
    return el("span", {class: "v2-ov-flag", title: text, tabindex: "0", role: "img", "aria-label": text,
      text: adjustment ? "±" : "✎"});
  }
  // Find a trade (and anything else listening) re-runs when the values under it change.
  function announce(reason) {
    try { document.dispatchEvent(new CustomEvent("ddf:league-settings-changed", {detail: {reason, notes: []}})); }
    catch (error) { console.warn("Overrides listener failed:", error); }
  }
  function push(reason) {
    if (!S.engine || typeof S.engine.setValueOverrides !== "function") return;
    S.session = S.session && reason === "link";
    if (!S.session) saveLinkState();
    S.engine.setValueOverrides(S.values);
    save();
    syncBar();
    if (reason) announce(reason);
  }
  function setOverride(key, entry, name) {
    const normalized = entry === null || entry === undefined ? null : normalizeEntry(entry);
    if (normalized === null) { delete S.values[key]; delete S.names[key]; }
    else S.values[key] = normalized;
    if (name) S.names[key] = name;
    if (entry === null || entry === undefined) delete S.names[key];
    push("overrides");
  }
  // Send the picker's basis to the engine (live: no Save). publish=false is the boot path.
  function applyBasis(publish) {
    if (!S.engine || typeof S.engine.setBasis !== "function") return null;
    clearTimeout(S.applyTimer);
    S.applyTimer = null;
    const sig = JSON.stringify(engineBasis());
    if (publish !== false && sig === S.applied) return null;   // nothing changed since the last apply
    S.applied = sig;
    const result = S.engine.setBasis(engineBasis(), publish !== false);
    if (result && result.ok === false) { setBasisState(null); S.applied = JSON.stringify(null); S.engine.setBasis(null, publish !== false); }
    if (publish !== false) { S.session = false; saveLinkState(); save(); syncBar(); announce("sources"); refreshPlayerSection(); }
    return result;
  }
  const scheduleApply = () => { clearTimeout(S.applyTimer); S.applyTimer = setTimeout(() => applyBasis(true), 100); };
  const flushApply = () => { if (S.applyTimer) applyBasis(true); };


  function snapshot() { return {basis: basisRecord(), values: {...S.values}, names: {...S.names}}; }
  function resetAll() {
    S.undo = snapshot();
    S.session = false;
    setBasisState(null);
    S.values = {};
    S.names = {};
    S.selected = null;
    S.draft = null;
    if (S.engine) { S.engine.setBasis(null, true); S.engine.setValueOverrides({}); }
    save();
    syncBar();
    announce("sources");
    render();
  }
  function undoReset() {
    const snap = S.undo;
    if (!snap) return;
    S.undo = null;
    setBasisState(snap.basis);
    S.values = {...snap.values};
    S.names = {...snap.names};
    if (S.engine) { S.engine.setBasis(engineBasis(), true); S.engine.setValueOverrides(S.values); }
    save();
    syncBar();
    announce("sources");
    render();
  }

  // ---------- the bar under the header (every view) ----------
  // "Overrides active: ..." with a one-click reset, a shared link's banner, and the one-time carry-over notice.
  // The indicator sits in the league row (no extra height on any tab); banners get their own strip under the header.
  function barHost() {
    let bar = $("v2OvBar");
    if (bar) return bar;
    const inner = document.querySelector(".v2-context-inner");   // JEG-1119: the context row replaced the league bar
    if (!inner) return null;
    bar = el("div", {id: "v2OvBar", class: "v2-ov-bar", hidden: true});
    inner.insertBefore(bar, $("v2EditSources"));
    return bar;
  }
  function bannerHost() {
    let box = $("v2OvBanners");
    if (box) return box;
    const header = document.querySelector(".v2-nav");
    if (!header || !header.parentNode) return null;
    box = el("div", {id: "v2OvBanners", class: "v2-ov-banners", hidden: true});
    header.parentNode.insertBefore(box, header.nextSibling);
    return box;
  }
  function activeText() {
    const info = basisInfo();
    const n = Object.keys(S.values).length;
    const parts = [];
    if (info && !info.isDefault) parts.push(info.shortLabel);
    if (n) parts.push(`${n} player override${n === 1 ? "" : "s"}`);
    if (!parts.length) return "";
    let text = `Overrides active: ${parts.join(" + ")}`;
    if (info && info.fellBackToDefault) text += ". None of those sources is available this week, so our methodology is used";
    return text;
  }
  function syncBar() {
    const bar = barHost();
    const banners = bannerHost();
    if (!bar || !banners) return;
    const text = activeText();
    const line = [];
    if (text) {
      line.push(el("a", {id: "v2OverrideBadge", class: "v2-ov-badge", href: "v2/#value-overrides", role: "status", "aria-live": "polite",
          title: "Your basis and player values replace our methodology on every tab. Open Overrides to change them.", text}),
        el("button", {type: "button", class: "v2-btn v2-btn-quiet v2-ov-reset", id: "v2OvResetAll", text: "Reset all",
          "aria-label": "Reset to our methodology: clear the custom basis and every player override", onclick: resetAll}));
    } else if (S.undo) {
      line.push(el("span", {class: "v2-ov-bar-msg", role: "status", "aria-live": "polite", text: "Back to our methodology."}),
        el("button", {type: "button", class: "v2-btn v2-btn-quiet v2-ov-reset", id: "v2OvUndo", text: "Undo", onclick: undoReset}));
    }
    bar.replaceChildren(...line);
    bar.hidden = !line.length;
    const notes = [];
    if (S.linkNote) {
      notes.push(el("div", {class: "v2-ov-banner", id: "v2OvLinkBanner", role: "region", "aria-label": "Shared link settings"}, [
        el("div", {class: "v2-wrap v2-ov-banner-in"}, [
          el("span", {text: S.linkNote}),
          el("button", {type: "button", class: "v2-btn v2-btn-primary", id: "v2OvUseOurs", text: "Use our methodology", onclick: useOurs}),
          el("button", {type: "button", class: "v2-btn v2-btn-quiet", id: "v2OvKeepLink", text: "Keep these settings",
            onclick: () => { S.linkNote = null; saveLinkState(S.linkExtra || {}); syncBar(); }})])]));
    }
    if (S.notice) {
      notes.push(el("div", {class: "v2-ov-banner", id: "v2OvNotice", role: "status"}, [
        el("div", {class: "v2-wrap v2-ov-banner-in"}, [
          el("span", {text: S.notice}),
          el("button", {type: "button", class: "v2-btn v2-btn-quiet", id: "v2OvNoticeOk", text: "Got it",
            onclick: () => { S.notice = null; syncBar(); }})])]));
    }
    banners.replaceChildren(...notes);
    banners.hidden = !notes.length;
  }
  // Compat for callers of the JEG-1035 name.
  const syncBadge = syncBar;

  // ---------- the basis picker ----------
  const PRESETS = [{id: "default", text: "Our methodology"}]
    .concat(SINGLE_ORDER.map(key => ({id: `single:${key}`, text: labelOf(key), key})))
    .concat([{id: "blend", text: "Custom blend"}]);
  const presetId = () => (S.mode === "single" ? `single:${S.single}` : S.mode);
  const isUsable = key => {
    const info = basisInfo();
    const state = info && info.sourceStates ? info.sourceStates.find(item => item.key === key) : null;
    return !state || state.usable;
  };
  // Whole percents that sum to 100 over the ticked, usable sources (the engine's own rule, shown live).
  function percents() {
    const on = BASIS_KEYS.filter(key => S.blend[key].on && isUsable(key));
    const total = on.reduce((sum, key) => sum + S.blend[key].w, 0);
    const exact = on.map(key => [key, 100 * S.blend[key].w / total]);
    const out = Object.fromEntries(exact.map(([key, v]) => [key, Math.floor(v)]));
    let left = 100 - Object.values(out).reduce((a, b) => a + b, 0);
    exact.slice().sort((a, b) => (b[1] - Math.floor(b[1])) - (a[1] - Math.floor(a[1]))).forEach(([key]) => {
      if (left > 0) { out[key] += 1; left -= 1; }
    });
    return out;
  }
  function summaryText() {
    const info = basisInfo();
    if (S.mode === "default") return "DDF Value = our methodology: the trade charts FantasyCalc, USA Today, FantasyPros and CBS, adjusted to your league, equal weight.";
    if (S.mode === "single") return `DDF Value = ${labelOf(S.single)} only: that source's value for your league, on the same point scale as every source.`;
    const pct = percents();
    const label = BASIS_KEYS.filter(key => pct[key] !== undefined).map(key => `${pct[key]}% ${labelOf(key)}`).join(" + ");
    return `DDF Value = ${label || (info && info.label) || "your blend"}, averaged for your league.`;
  }
  function updateSummary() {
    const box = $("v2OvSummary");
    if (!box) return;
    const info = basisInfo();
    box.replaceChildren(el("p", {id: "v2OvSummaryText", tabindex: "-1", text: summaryText()}));
    if (S.mode !== "default" && info && info.isDefault) {
      box.append(el("p", {class: "v2-meta", text: "These weights are the same as our methodology, so no value changes. Change a weight or add a source to move away from it."}));
    } else if (S.mode !== "default") {
      const label = info ? info.label : "your basis";
      box.append(el("p", {class: "v2-meta", text: `You are not using our methodology. Rescaled trade charts follow this basis (shown as “Rescaled (to ${label})”). The trade chart average, the market side, does not change.`}));
      if (info && info.fellBackToDefault) {
        box.append(el("p", {class: "v2-ov-warn", role: "alert", text: "None of the sources you chose is available this week, so our methodology is used until one returns."}));
      }
    }
  }

  function renderBlendEditor() {
    const box = $("v2OvBlend");
    if (!box) return;
    box.replaceChildren();
    box.hidden = S.mode !== "blend";
    if (S.mode !== "blend") return;
    const pct = percents();
    const ticked = BASIS_KEYS.filter(key => S.blend[key].on && isUsable(key));
    const info = basisInfo();
    const stateOf = key => (info && info.sourceStates ? info.sourceStates.find(item => item.key === key) : null);
    const paintPercents = () => {
      const now = percents();
      BASIS_KEYS.forEach(key => {
        const out = box.querySelector(`[data-pct="${key}"]`);
        if (out) out.textContent = now[key] !== undefined ? `${now[key]}% of the blend` : (S.blend[key].on ? "paused" : "not used");
      });
      updateSummary();
    };
    box.append(el("p", {class: "v2-meta", text: "Tick the sources to blend and set each one's weight (whole numbers, 1 to 100). Only the proportions matter: 60 and 40 is the same blend as 3 and 2."}));
    const list = el("div", {class: "v2-ov-wlist"});
    BASIS_SOURCES.forEach(([key, label]) => {
      const st = stateOf(key);
      const paused = st && !st.usable;
      const last = S.blend[key].on && ticked.length === 1 && ticked[0] === key;
      const check = el("input", {type: "checkbox", id: `v2OvOn-${key}`, "data-source": key, "aria-label": `Include ${label}`,
        checked: S.blend[key].on || null, disabled: paused || last || null});
      const range = el("input", {type: "range", min: "1", max: "100", step: "1", value: String(S.blend[key].w), id: `v2OvW-${key}`,
        "data-weight": key, "aria-label": `${label} weight`, "aria-valuemin": "1", "aria-valuemax": "100",
        "aria-valuenow": String(S.blend[key].w), disabled: !S.blend[key].on || paused || null});
      const num = el("input", {type: "number", min: "1", max: "100", step: "1", value: String(S.blend[key].w), class: "v2-ov-wnum",
        "data-weight-num": key, "aria-label": `${label} weight, whole number`, disabled: !S.blend[key].on || paused || null});
      const out = el("span", {class: "v2-ov-wpct", "data-pct": key, "aria-hidden": "true"});
      const setWeight = value => {
        S.blend[key].w = clampWeight(value);
        range.value = String(S.blend[key].w);
        range.setAttribute("aria-valuenow", String(S.blend[key].w));
        num.value = String(S.blend[key].w);
        paintPercents();
        scheduleApply();
      };
      range.addEventListener("input", () => setWeight(range.value));
      range.addEventListener("change", flushApply);
      num.addEventListener("change", () => { setWeight(num.value); flushApply(); });
      check.addEventListener("change", () => {
        S.blend[key].on = check.checked;
        if (!BASIS_KEYS.some(k => S.blend[k].on)) S.blend[key].on = true;
        applyBasis(true);
        renderBlendEditor();
        const again = $(`v2OvOn-${key}`);
        if (again) again.focus();
      });
      list.append(el("div", {class: `v2-ov-wrow${paused ? " is-paused" : ""}`, "data-source-row": key}, [
        el("label", {class: "v2-ov-wname", for: `v2OvOn-${key}`}, [document.createTextNode(label)]),
        check, range, num, out,
        paused ? el("span", {class: "v2-meta v2-ov-wnote", text: "Paused this week; its weight waits"})
          : last ? el("span", {class: "v2-meta v2-ov-wnote", text: "Last source stays on"}) : null]));
    });
    box.append(list);
    paintPercents();
  }

  function renderBasis(box) {
    if (!box) return;
    box.replaceChildren();
    const group = el("div", {class: "v2-ov-presets", role: "radiogroup", "aria-label": "Value basis", id: "v2OvPresets"});
    const buttons = PRESETS.map(preset => {
      const usable = !preset.key || isUsable(preset.key);
      const button = el("button", {type: "button", role: "radio", class: "v2-select v2-ov-preset", "data-preset": preset.id,
        "aria-checked": "false", "aria-disabled": usable ? null : "true", title: usable ? null : "Paused this week",
        text: preset.text});
      return button;
    });
    const paint = () => buttons.forEach(button => {
      const on = button.dataset.preset === presetId();
      button.setAttribute("aria-checked", String(on));
      button.setAttribute("aria-pressed", String(on));
      button.tabIndex = on ? 0 : -1;
      button.classList.toggle("is-on", on);
    });
    function choose(id, how) {
      const preset = PRESETS.find(item => item.id === id);
      if (!preset || (preset.key && !isUsable(preset.key))) return;
      if (id === "default") S.mode = "default";
      else if (id === "blend") S.mode = "blend";
      else { S.mode = "single"; S.single = preset.key; }
      paint();
      applyBasis(true);
      renderBlendEditor();
      if (how === "arrow") { const again = group.querySelector(`[data-preset="${id}"]`); if (again) again.focus(); }
      else if (id === "blend") { const first = box.querySelector("[data-weight]:not([disabled])"); if (first) first.focus(); }
      else { const text = $("v2OvSummaryText"); if (text) text.focus(); }
    }
    buttons.forEach((button, index) => {
      button.addEventListener("click", () => choose(button.dataset.preset, "click"));
      button.addEventListener("keydown", event => {
        const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
        if (!step) return;
        event.preventDefault();
        for (let n = 1; n <= buttons.length; n += 1) {
          const next = buttons[(index + step * n + buttons.length * n) % buttons.length];
          const preset = PRESETS.find(item => item.id === next.dataset.preset);
          if (!preset.key || isUsable(preset.key)) { choose(next.dataset.preset, "arrow"); return; }
        }
      });
      group.append(button);
    });
    paint();
    S.repaintBasis = () => {
      buttons.forEach(button => {
        const preset = PRESETS.find(item => item.id === button.dataset.preset);
        const usable = !preset.key || isUsable(preset.key);
        button.setAttribute("aria-disabled", usable ? "false" : "true");
        if (usable) button.removeAttribute("aria-disabled");
      });
      paint();
      const blendBox = $("v2OvBlend");
      const editing = blendBox && blendBox.contains(document.activeElement);
      if (!editing) renderBlendEditor();
      updateSummary();
    };
    box.append(
      el("div", {class: "v2-card-head"}, [el("h2", {id: "v2OvBasisTitle", text: "Value basis"})]),
      el("p", {class: "v2-meta", text: "What “our value” means on every tab. The default is our methodology: the four trade charts, adjusted to your league, equal weight. Pick one source, or blend any sources with your own weights. It applies right away; your player values below stay."}),
      group,
      el("div", {id: "v2OvBlend", class: "v2-ov-blend", hidden: true}),
      el("div", {id: "v2OvSummary", class: "v2-ov-summary", role: "status", "aria-live": "polite"}),
      el("p", {class: "v2-meta"}, [document.createTextNode("Position shares and the bench share also shape every value. "),
        el("button", {type: "button", class: "v2-ov-link", id: "v2OvOpenWeights", text: "Open Position weights",
          onclick: () => { const open = $("v2Weights"); if (open) open.click(); }})]));
    renderBlendEditor();
    updateSummary();
  }
  // After a basis change the player editor and list show values under the new basis.
  function refreshPlayerSection() {
    const editor = $("v2OvEditor");
    if (editor && S.selected && !editor.hidden) { S.draft = null; renderEditor(editor); }
    renderList($("v2OvList"));
  }

  // ---------- export / import ----------
  function exportDoc() {
    const rec = basisRecord();
    return {v: 2, basis: rec.mode === "default" ? {mode: "default"} : rec,
      overrides: Object.keys(S.values).map(key => {
        const row = rowOf(key);
        const base = {player_key: key, name: row ? row.name : (S.names[key] || ""), pos: row ? row.pos : ""};
        const entry = S.values[key];
        // JEG-1058: an adjustment exports its delta, an absolute value its value.
        if (isAdjustment(entry)) return {...base, type: "adjustment", delta: entry.delta};
        return {...base, type: "absolute", value: entry};
      })};
  }
  function exportFile() {
    S.exportHint = false;
    const blob = new Blob([JSON.stringify(exportDoc(), null, 2) + "\n"], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const link = el("a", {href: url, download: "ddf-overrides.json"});
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    renderList($("v2OvList"));
  }
  // Apply an exported document. Unknown players and sources are skipped and named. Returns the sentence to show.
  function importDoc(doc) {
    if (!doc || typeof doc !== "object" || ![1, 2].includes(doc.v) || (!Array.isArray(doc.overrides) && !doc.basis)) {
      return "That file is not an overrides export, so nothing was changed.";
    }
    const notes = [];
    if (doc.basis) {
      const dropped = setBasisState(doc.basis);
      if (dropped.length) notes.push(`Left out sources this build does not have: ${dropped.join(", ")}.`);
    }
    const values = {};
    const names = {};
    let skipped = 0;
    (Array.isArray(doc.overrides) ? doc.overrides : []).forEach(item => {
      const key = String(item && item.player_key);
      const row = rowOf(key);
      // JEG-1058: an adjustment carries a delta, an absolute value a value.
      const entry = item && item.type === "adjustment"
        ? normalizeEntry({type: "adjustment", delta: item.delta})
        : (item && (item.type === "absolute" || item.type === undefined)
          ? normalizeEntry(Number(item.value)) : null);
      if (!row || entry === null) { skipped += 1; return; }
      values[key] = entry;
      names[key] = item.name || row.name || "";
    });
    if (skipped) notes.push(`Skipped ${skipped} override${skipped === 1 ? "" : "s"} for players this build does not know or values it cannot use.`);
    S.values = values;
    S.names = names;
    S.session = false;
    if (S.engine) { S.engine.setBasis(engineBasis(), true); }
    S.applied = JSON.stringify(engineBasis());
    push("sources");
    return `Imported ${Object.keys(values).length} player override${Object.keys(values).length === 1 ? "" : "s"}${doc.basis ? " and the value basis" : ""}. ${notes.join(" ")}`.trim();
  }
  function pickImportFile() {
    const input = el("input", {type: "file", accept: "application/json,.json", hidden: true, id: "v2OvImportFile"});
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      input.remove();
      if (!file) return;
      file.text().then(text => {
        let doc = null;
        try { doc = JSON.parse(text); } catch (error) { /* reported below */ }
        S.importNote = importDoc(doc);
        render();
      });
    });
    document.body.append(input);
    input.click();
  }

  // ---------- share links ----------
  // basis=fantasycalc | basis=blend:espn.60_razzball.40 (absent = ours). ov=2227:58.0,1110:42.5 for a few players;
  // ov=z:<base64url> beyond PACK_AFTER (3 bytes of player key + 2 bytes of tenths per override, about half the
  // characters). Old links without either work unchanged.
  // JEG-1058: an adjustment travels as ov=2227:+5 (a signed delta). The packed form
  // gains a type byte (ov=z2:) when any override is an adjustment; ov=z: stays the
  // original absolute-only layout, so links made before this change still read.
  const b64 = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unb64 = text => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), ch => ch.charCodeAt(0));
  function packOverrides(map) {
    const bytes = [];
    Object.keys(map).forEach(key => {
      const k = Number(key);
      const tenths = Math.round(map[key] * 10);
      if (!Number.isInteger(k) || k < 0 || k > 0xFFFFFF || tenths < 0 || tenths > 0xFFFF) return;
      bytes.push((k >> 16) & 255, (k >> 8) & 255, k & 255, (tenths >> 8) & 255, tenths & 255);
    });
    return b64(bytes);
  }
  function unpackOverrides(text) {
    const bytes = unb64(text);
    const out = {};
    for (let i = 0; i + 4 < bytes.length; i += 5) {
      const entry = normalizeEntry(((bytes[i + 3] << 8) | bytes[i + 4]) / 10);
      if (entry !== null) out[String((bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2])] = entry;
    }
    return out;
  }
  // The packed form that carries the kind: 3 bytes of player key, 1 byte of type
  // (0 absolute, 1 adjustment) and 2 bytes of tenths (signed, so a delta can be
  // negative).
  function packOverridesWithTypes(map) {
    const bytes = [];
    Object.keys(map).forEach(key => {
      const k = Number(key);
      const entry = map[key];
      const adjustment = isAdjustment(entry);
      const tenths = Math.round((adjustment ? Number(entry.delta) : Number(entry)) * 10);
      if (!Number.isInteger(k) || k < 0 || k > 0xFFFFFF) return;
      if (!Number.isFinite(tenths)) return;
      // The tenths are inside the two bytes they travel in: an override is on
      // the scale, so this is the same number, never a dropped player.
      const packed = Math.min(32767, Math.max(-32768, tenths));
      bytes.push((k >> 16) & 255, (k >> 8) & 255, k & 255, adjustment ? 1 : 0, (packed >> 8) & 255, packed & 255);
    });
    return b64(bytes);
  }
  function unpackOverridesWithTypes(text) {
    const bytes = unb64(text);
    const out = {};
    for (let i = 0; i + 5 < bytes.length; i += 6) {
      const key = String((bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2]);
      const raw = (bytes[i + 4] << 8) | bytes[i + 5];
      const tenths = raw >= 32768 ? raw - 65536 : raw;
      const value = tenths / 10;
      const entry = bytes[i + 3] === 1 ? normalizeEntry({type: "adjustment", delta: value}) : normalizeEntry(value);
      if (entry !== null) out[key] = entry;
    }
    return out;
  }
  // One override in a link: key:value for an absolute value, key:+5 for an adjustment.
  const ovParam = (key, entry) => (isAdjustment(entry)
    ? `${key}:${Number(entry.delta) >= 0 ? "+" : ""}${round1(Number(entry.delta))}`
    : `${key}:${entry}`);
  function shareParams() {
    const out = {basis: null, ov: null, dropped: false};
    const info = basisInfo();
    const rec = basisRecord();
    if (info && !info.isDefault) {
      if (info.mode === "single") out.basis = info.source;
      else out.basis = `blend:${info.sources.map(key => `${key}.${info.weights[key]}`).join("_")}`;
    } else if (rec.mode !== "default" && !info) {
      out.basis = rec.mode === "single" ? rec.source : `blend:${rec.sources.map(key => `${key}.${rec.weights[key]}`).join("_")}`;
    }
    const keys = Object.keys(S.values);
    if (keys.length) {
      const anyAdjustment = keys.some(key => isAdjustment(S.values[key]));
      if (anyAdjustment) out.ov = keys.length > PACK_AFTER ? `z2:${packOverridesWithTypes(S.values)}` : keys.map(key => ovParam(key, S.values[key])).join(",");
      else out.ov = keys.length > PACK_AFTER ? `z:${packOverrides(S.values)}` : keys.map(key => `${key}:${S.values[key]}`).join(",");
    }
    return out;
  }
  // The share-link text a recipient is told about; also what an over-long link falls back to.
  function dropOverridesNote() {
    S.exportHint = true;
    renderList($("v2OvList"));
    return "Your player overrides are too large for a link. Use Export on the Overrides tab to share them as a file.";
  }
  function parseBasisParam(text) {
    if (!text) return null;
    if (text.startsWith("blend:")) {
      const sources = [];
      const weights = {};
      text.slice(6).split("_").forEach(part => {
        const [key, w] = part.split(".");
        if (BASIS_KEYS.includes(key) && Number(w) >= 1) { sources.push(key); weights[key] = clampWeight(w); }
      });
      return sources.length ? {mode: "blend", sources, weights} : null;
    }
    return BASIS_KEYS.includes(text) ? {mode: "single", source: text} : null;
  }
  // JEG-1058: a value that starts with + or - is an adjustment (ov=2227:+5); a plain number is an absolute value.
  function parseOvParam(text) {
    if (!text) return null;
    let map = {};
    try {
      if (text.startsWith("z2:")) map = unpackOverridesWithTypes(text.slice(3));
      else if (text.startsWith("z:")) map = unpackOverrides(text.slice(2));
      else text.split(",").forEach(part => {
        const [key, v] = part.split(":");
        if (!/^\d+$/.test(key) || v === undefined || v === "") return;
        // A sign means an adjustment. A leading space is the "+" that a URL parser
        // turned into a space (URLSearchParams reads "+" as a space), so it is a sign too.
        if (/^[+-]/.test(v) || /^\s/.test(v)) {
          const delta = Number(v);
          const entry = normalizeEntry({type: "adjustment", delta});
          if (entry !== null) map[key] = entry;
        } else {
          const value = Number(v);
          const entry = normalizeEntry(value);
          if (entry !== null) map[key] = entry;
        }
      });
    } catch (error) { return null; }
    return Object.keys(map).length ? map : null;
  }
  // The recipient's side. In memory for the visit: the reader's own saved settings are not touched.
  function applyLink(params) {
    const basisText = params.get("basis");
    const ovText = params.get("ov");
    if (!basisText && !ovText) return false;
    const sig = `${basisText || ""}|${ovText || ""}`;
    if (sig === S.linkSig) return false;
    const basis = parseBasisParam(basisText);
    const overrides = parseOvParam(ovText);
    if (!basis && !overrides) return false;
    S.linkSig = sig;
    S.session = true;
    if (basis) setBasisState(basis);
    if (overrides) {
      Object.entries(overrides).forEach(([key, v]) => { const entry = normalizeEntry(v); if (entry !== null) S.values[key] = entry; });
      Object.keys(overrides).forEach(key => { const row = rowOf(key); if (row) S.names[key] = row.name; });
    }
    if (S.engine) {
      if (basis) S.engine.setBasis(engineBasis(), true);
      S.applied = JSON.stringify(engineBasis());
      S.engine.setValueOverrides(S.values);
    }
    const parts = [];
    const info = basisInfo();
    if (basis) parts.push(`a custom basis (${info ? info.label : "see Overrides"})`);
    if (overrides) parts.push(`${Object.keys(overrides).length} player override${Object.keys(overrides).length === 1 ? "" : "s"}`);
    S.linkNote = `This link uses ${parts.join(" and ")}. They apply for this visit only.`;
    S.linkExtra = {basis: basis || null, values: overrides || null};
    saveLinkState(S.linkExtra);
    syncBar();
    announce("sources");
    return true;
  }
  function useOurs() {
    S.linkNote = null;
    S.session = true;   // still this visit only: your own saved settings come back on the next visit
    S.linkExtra = {ours: true};
    saveLinkState(S.linkExtra);
    setBasisState(null);
    S.values = {};
    S.names = {};
    if (S.engine) { S.engine.setBasis(null, true); S.engine.setValueOverrides({}); }
    S.applied = JSON.stringify(null);
    syncBar();
    announce("sources");
    if ($("v2Overrides") && !$("v2Overrides").hidden) render();
  }

  // ---------- search ----------
  function renderSearch(box) {
    const input = el("input", {type: "search", id: "v2OvSearch", placeholder: "Search a player to override…", autocomplete: "off",
      "aria-label": "Search a player", value: S.query});
    const list = el("ul", {class: "v2-ov-results", id: "v2OvResults", role: "listbox", "aria-label": "Matching players"});
    const fill = () => {
      list.replaceChildren();
      const q = input.value.trim();
      S.query = input.value;
      if (!q || !S.engine) return;
      const hits = S.engine.searchPlayers(q, {limit: 8});
      if (!hits.length) { list.append(el("li", {class: "v2-ov-none", text: "No player matches."})); return; }
      hits.forEach(row => {
        const v = row.values.ddf_value;
        list.append(el("li", {role: "option"}, [el("button", {type: "button", class: "v2-ov-hit",
          onclick: () => { select(row.player_key, row.name); }}, [
          el("span", {class: "v2-ov-hit-name", text: row.name}),
          el("span", {class: "v2-ov-hit-meta", text: `${row.pos}${row.team ? " · " + row.team : ""} · DDF ${fmt(v)}${S.values[row.player_key] !== undefined ? " (yours)" : ""}`})])]));
      });
    };
    input.addEventListener("input", fill);
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") { const first = list.querySelector("button"); if (first) first.click(); }
    });
    box.append(el("h2", {id: "v2OvPlayersTitle", text: "Player values"}),
      el("p", {class: "v2-meta", text: "Think a player is worth more or less? Set your own value. It replaces DDF Value on every tab, on any basis."}),
      el("label", {class: "v2-search v2-ov-search"}, [input]), list);
    fill();
  }
  function select(key, name) {
    S.selected = String(key);
    S.draft = null;
    S.draftType = "absolute";   // JEG-1058: a new player opens on an absolute value
    S.draftDelta = null;
    S.query = "";
    render();
    const editor = $("v2OvEditor");
    if (editor && editor.scrollIntoView) editor.scrollIntoView({block: "nearest"});
  }

  // ---------- editor: graph + comparables ----------
  // The pool the chosen value is compared against: every other priced player (same position by default), at the
  // values the dashboard shows now (other overrides included).
  function pool(row) {
    return rows().filter(r => String(r.player_key) !== String(row.player_key) && finite(r.values.ddf_value) && r.values.ddf_value > 0
      && (S.scope === "all" || r.pos === row.pos))
      .sort((a, b) => b.values.ddf_value - a.values.ddf_value || a.name.localeCompare(b.name));
  }
  const rankAt = (list, value) => list.filter(r => r.values.ddf_value > value).length + 1;
  const scopeLabel = row => (S.scope === "all" ? "overall" : row.pos);

  function renderEditor(box) {
    const row = S.selected ? rowOf(S.selected) : null;
    box.replaceChildren();
    box.hidden = !row;
    if (!row) return;
    const model = modelValue(row);
    const saved = S.values[S.selected];
    const base = pipelineValue(row);   // the pipeline's own value; 0 when no source prices him
    const clampValue = v => round1(Math.min(OVERRIDE_MAX, Math.max(OVERRIDE_MIN, v)));
    if (S.draft === null) {
      // JEG-1058: an override is an absolute value or an adjustment. The editor opens in the kind it was set.
      S.draftType = "absolute";
      if (saved !== undefined && isAdjustment(saved)) {
        S.draftType = "adjustment";
        S.draftDelta = round1(Number(saved.delta));
        S.draft = clampValue(base + S.draftDelta);
      } else if (saved !== undefined) {
        S.draft = saved;
      } else {
        S.draft = finite(model) ? model : 0;
      }
    }
    if (S.draftType === "adjustment") {
      if (S.draftDelta === null || S.draftDelta === undefined) S.draftDelta = round1(S.draft - base);
      S.draft = clampValue(base + S.draftDelta);
    }
    const list = pool(row);
    const top = list.length ? list[0].values.ddf_value : 0;
    let yMax = 0;
    let step = 1;
    // The chart grows to fit the value being edited (a big adjustment can sit above the field).
    const scale = value => {
      const peak = Math.max(10, top, finite(model) ? model : 0, value) * 1.08;
      step = [2, 5, 10, 20, 25, 50, 100].find(st => peak / st <= 6) || 200;
      yMax = Math.ceil(peak / step) * step;
    };
    scale(S.draft);

    // Head: who, model value, your value.
    const numberInput = el("input", {type: "number", id: "v2OvNumber", min: "0", max: "100", step: "0.1",
      value: fmt(S.draftType === "adjustment" ? S.draftDelta : S.draft), "aria-label": `Your value for ${row.name}`});
    const typeLabel = el("span", {class: "v2-ov-type-label", text: S.draftType === "adjustment" ? "Adjustment" : "Your value"});
    // JEG-1058: the kind of the override. Absolute by default; an adjustment adds to (or takes off) the
    // pipeline's own value.
    const typeButtons = ["absolute", "adjustment"].map(kind =>
      el("button", {type: "button", class: "v2-select", "data-ov-type": kind, "aria-pressed": String(S.draftType === kind),
        text: kind === "absolute" ? "Value" : "Adjust", onclick: () => switchType(kind)}));
    const typeToggle = el("div", {class: "v2-ov-type", role: "group", "aria-label": "Override type"}, typeButtons);
    const head = el("div", {class: "v2-ov-head"}, [
      el("div", {}, [
        el("h2", {id: "v2OvName", text: row.name}),
        el("p", {class: "v2-meta", text: `${row.pos}${row.team ? " · " + row.team : ""} · DDF Value ${fmt(model)}${finite(model) ? ` (${row.pos}${rankAt(pool({...row, pos: row.pos}).filter(r => r.pos === row.pos), model)})` : ""}`})]),
      el("div", {class: "v2-ov-yours"}, [el("label", {class: "v2-ov-yours-label"}, [typeLabel, numberInput]), typeToggle])]);

    // Scope toggle (same position by default).
    const scope = el("div", {class: "v2-ov-scope", role: "group", "aria-label": "Compare against"}, [
      ["pos", `Same position (${row.pos})`], ["all", "All positions"]].map(([key, label]) =>
      el("button", {type: "button", class: "v2-select", "aria-pressed": String(S.scope === key),
        onclick: () => { S.scope = key; renderEditor(box); }}, [document.createTextNode(label)])));

    // Graph.
    const W = 720, H = 300, L = 44, R = 16, T = 14, B = 30;
    const n = Math.max(list.length, 1);
    const x = rank => L + (rank - 1) / Math.max(n - 1, 1) * (W - L - R);
    const y = v => T + (1 - v / yMax) * (H - T - B);
    const chart = svg("svg", {viewBox: `0 0 ${W} ${H}`, class: "v2-ov-chart", role: "img", id: "v2OvChart",
      "aria-label": `DDF Value by ${scopeLabel(row)} rank, with a draggable line for ${row.name}'s value`});
    const axis = svg("g", {});
    chart.append(axis);
    chart.append(svg("text", {x: (L + W - R) / 2, y: H - 6, class: "v2-ov-axis", "text-anchor": "middle"}, `${scopeLabel(row) === "overall" ? "Overall" : row.pos} rank by DDF Value`));
    const dots = svg("g", {});
    list.forEach((r, i) => dots.append(svg("circle", {cx: x(i + 1), cy: y(r.values.ddf_value), r: 3, class: "v2-ov-dot", "data-key": r.player_key},
    )));
    chart.append(dots);
    const modelLine = finite(model) ? svg("line", {x1: L, x2: W - R, class: "v2-ov-model"}) : null;
    const modelLabel = finite(model) ? svg("text", {x: W - R, class: "v2-ov-model-label", "text-anchor": "end"}, `DDF Value ${fmt(model)}`) : null;
    if (modelLine) chart.append(modelLine, modelLabel);
    const line = svg("line", {x1: L, x2: W - R, class: "v2-ov-line"});
    const handle = svg("circle", {r: 7, class: "v2-ov-handle"});
    const tag = svg("text", {class: "v2-ov-tag"});
    chart.append(line, handle, tag);

    // Range slider: the keyboard and screen-reader way to drag.
    const range = el("input", {type: "range", id: "v2OvRange", min: "0", max: String(yMax), step: "0.1", value: String(S.draft),
      "aria-label": `Drag ${row.name}'s value`});

    const near = el("div", {class: "v2-ov-near", "aria-live": "polite"});

    function draw(value) {
      S.draft = clampValue(value);
      scale(S.draft);
      axis.replaceChildren();
      for (let v = 0; v <= yMax + 1e-9; v += step) {
        axis.append(svg("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), class: "v2-ov-grid"}));
        axis.append(svg("text", {x: L - 6, y: y(v) + 4, class: "v2-ov-axis", "text-anchor": "end"}, String(v)));
      }
      if (modelLine) {
        modelLine.setAttribute("y1", y(model)); modelLine.setAttribute("y2", y(model));
        modelLabel.setAttribute("y", y(model) - 5);
      }
      const rank = rankAt(list, S.draft);
      line.setAttribute("y1", y(S.draft)); line.setAttribute("y2", y(S.draft));
      handle.setAttribute("cx", x(Math.min(rank, n))); handle.setAttribute("cy", y(S.draft));
      const tx = Math.min(Math.max(x(Math.min(rank, n)) + 12, L + 4), W - R - 150);
      tag.setAttribute("x", tx); tag.setAttribute("y", Math.max(y(S.draft) - 10, T + 10));
      tag.textContent = `${fmt(S.draft)} · ${scopeLabel(row) === "overall" ? "#" : row.pos}${rank}`;
      if (document.activeElement !== numberInput) numberInput.value = fmt(S.draftType === "adjustment" ? S.draftDelta : S.draft);
      range.max = String(yMax);
      range.value = String(S.draft);
      // Comparable players: the NEAR above and NEAR below where this value lands.
      const at = rank - 1;
      const above = list.slice(Math.max(0, at - NEAR), at);
      const below = list.slice(at, at + NEAR);
      const keys = new Set(above.concat(below).map(r => String(r.player_key)));
      dots.querySelectorAll("circle").forEach(c => c.classList.toggle("is-near", keys.has(c.dataset.key)));
      near.replaceChildren(
        el("h3", {text: `At ${fmt(S.draft)}, ${row.name} ranks ${scopeLabel(row) === "overall" ? "#" : row.pos}${rank}${finite(model) ? ` (DDF Value: ${scopeLabel(row) === "overall" ? "#" : row.pos}${rankAt(list, model)})` : ""}. Comparable players:`}),
        compTable(above, below, row));
    }
    function compTable(above, below, row) {
      const tbl = el("table", {class: "v2-table v2-ov-table"});
      tbl.append(el("thead", {}, [el("tr", {}, ["Player", "Pos", "Team", "Value", "vs yours"].map((h, i) =>
        el("th", {scope: "col", class: i >= 3 ? "num" : null, text: h})))]));
      const body = el("tbody");
      const add = r => body.append(el("tr", {}, [
        el("td", {}, [el("button", {type: "button", class: "v2-ov-link", text: r.name, title: `Override ${r.name} instead`,
          onclick: () => select(r.player_key, r.name)}),
          r.valueOverride !== null && r.valueOverride !== undefined ? el("span", {class: "v2-ov-mark", text: " yours"}) : null]),
        el("td", {text: r.pos}), el("td", {text: r.team || ""}),
        el("td", {class: "num", text: fmt(r.values.ddf_value)}),
        el("td", {class: "num", text: signed(r.values.ddf_value - S.draft)})]));
      above.forEach(add);
      body.append(el("tr", {class: "v2-ov-self"}, [el("td", {text: `${row.name} (your value)`}), el("td", {text: row.pos}),
        el("td", {text: row.team || ""}), el("td", {class: "num", text: fmt(S.draft)}), el("td", {class: "num", text: ""})]));
      below.forEach(add);
      tbl.append(body);
      return tbl;
    }

    // Drag on the graph: anywhere in the plot moves the line; release applies it.
    const valueAt = event => {
      const box = chart.getBoundingClientRect();
      const py = (event.clientY - box.top) / box.height * H;
      return (1 - (py - T) / (H - T - B)) * yMax;
    };
    chart.addEventListener("pointerdown", event => {
      S.dragging = true;
      if (chart.setPointerCapture) chart.setPointerCapture(event.pointerId);
      dragTo(valueAt(event));
      event.preventDefault();
    });
    chart.addEventListener("pointermove", event => { if (S.dragging) dragTo(valueAt(event)); });
    const release = () => { if (!S.dragging) return; S.dragging = false; commit(); };
    chart.addEventListener("pointerup", release);
    chart.addEventListener("pointercancel", release);
    range.addEventListener("input", () => dragTo(Number(range.value)));
    range.addEventListener("change", commit);
    numberInput.addEventListener("change", () => {
      const v = Number(numberInput.value);
      if (!finite(v)) return;
      // JEG-1058: in adjustment mode the input holds the delta, so it adds to the DDF Value.
      if (S.draftType === "adjustment") { S.draftDelta = clampOverrideDelta(v); draw(base + S.draftDelta); }
      else draw(v);
      commit();
    });
    // Dragging sets the value itself; in adjustment mode that is the delta away from the DDF Value.
    function dragTo(value) {
      const v = clampValue(value);
      if (S.draftType === "adjustment") S.draftDelta = round1(v - base);
      draw(v);
    }

    function commit() {
      // Settling back on the model's own value is no override.
      if (S.draftType === "adjustment") {
        const effective = clampValue(base + S.draftDelta);
        if (!finite(S.draftDelta) || Math.abs(S.draftDelta) < 0.05) setOverride(S.selected, null);
        else if (finite(model) && Math.abs(effective - model) < 0.05) setOverride(S.selected, null);
        else setOverride(S.selected, {type: "adjustment", delta: S.draftDelta}, row.name);
      } else if (finite(model) && Math.abs(S.draft - model) < 0.05) {
        setOverride(S.selected, null);
      } else {
        setOverride(S.selected, S.draft, row.name);
      }
      renderList($("v2OvList"));
      actions.querySelector("[data-ov-reset]").hidden = S.values[S.selected] === undefined;
    }

    const actions = el("div", {class: "v2-ov-actions"}, [
      el("button", {type: "button", class: "v2-btn", "data-ov-reset": true, hidden: saved === undefined || null,
        text: `Reset to DDF Value (${fmt(model)})`, onclick: () => { setOverride(S.selected, null); S.draft = null; render(); }}),
      el("button", {type: "button", class: "v2-btn v2-btn-quiet", text: "Close", onclick: () => { S.selected = null; S.draft = null; render(); }})]);

    // JEG-1058: the kind of the override. Switching keeps the value the same (an adjustment starts at the
    // difference from the DDF Value) and stores it in the new kind.
    const helpText = el("p", {class: "v2-meta"});
    function paintType() {
      typeButtons.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.ovType === S.draftType)));
      typeLabel.textContent = S.draftType === "adjustment" ? "Adjustment" : "Your value";
      numberInput.min = S.draftType === "adjustment" ? "-100" : "0";
      numberInput.max = "100";
      numberInput.setAttribute("aria-label", S.draftType === "adjustment"
        ? `Adjustment to ${row.name}'s DDF Value` : `Your value for ${row.name}`);
      helpText.textContent = S.draftType === "adjustment"
        ? `An adjustment adds to (or takes off) the DDF Value of ${fmt(base)}. The result is capped between 0 and 100.`
        : "Drag the line on the graph (or the slider) to set his value. It applies when you let go, on every tab.";
    }
    function switchType(kind) {
      if (kind === S.draftType) return;
      if (kind === "adjustment") {
        S.draftDelta = round1(S.draft - base);
        S.draftType = "adjustment";
      } else {
        S.draftType = "absolute";
        S.draft = clampValue(base + (finite(S.draftDelta) ? S.draftDelta : 0));
      }
      paintType();
      draw(S.draft);
      commit();
    }

    box.append(head, scope, el("div", {class: "v2-ov-plot"}, [chart, el("label", {class: "v2-ov-range"}, [range])]),
      helpText, near, actions);
    paintType();
    draw(S.draft);
  }

  // ---------- list of overrides ----------
  function renderList(box) {
    if (!box) return;
    box.replaceChildren();
    const keys = Object.keys(S.values);
    box.append(el("div", {class: "v2-card-head"}, [el("h2", {id: "v2OvListTitle", text: `Your player overrides (${keys.length})`}),
      el("div", {class: "v2-ov-tools"}, [
        el("button", {type: "button", id: "v2OvExport", class: `v2-btn v2-btn-quiet${S.exportHint ? " is-hint" : ""}`, text: "Export", onclick: exportFile,
          title: "Download your value basis and player overrides as a file"}),
        el("button", {type: "button", id: "v2OvImport", class: "v2-btn v2-btn-quiet", text: "Import", onclick: pickImportFile,
          title: "Load a file you exported before"}),
        keys.length ? el("button", {type: "button", class: "v2-btn v2-btn-quiet", text: "Remove all",
          onclick: () => { S.values = {}; S.names = {}; push("overrides"); render(); }}) : null])]));
    if (S.importNote) box.append(el("p", {class: "v2-meta", id: "v2OvImportNote", role: "status", text: S.importNote}));
    if (!keys.length) {
      box.append(el("p", {class: "v2-meta", text: "None yet. Pick a player above and drag his value; every tab then uses your value in place of DDF Value."}));
      return;
    }
    const tbl = el("table", {class: "v2-table v2-ov-table", "aria-labelledby": "v2OvListTitle"});
    tbl.append(el("thead", {}, [el("tr", {}, ["Player", "Pos", "DDF Value", "Your value", "Change", ""].map((h, i) =>
      el("th", {scope: "col", class: i >= 2 && i <= 4 ? "num" : null, text: h})))]));
    const body = el("tbody");
    keys.map(key => ({key, row: rowOf(key)}))
      .map(item => ({...item, effective: effectiveValue(item.row, S.values[item.key])}))
      .sort((a, b) => (b.effective || 0) - (a.effective || 0))
      .forEach(({key, row, effective}) => {
        const model = modelValue(row);
        const yours = el("td", {class: "num v2-ov-yours-cell"}, [el("span", {text: fmt(effective)})]);
        // JEG-1059: the badge that says the reader set this value.
        const badge = flag(row);
        if (badge) yours.append(badge);
        body.append(el("tr", {class: key === S.selected ? "is-selected" : null}, [
          el("td", {}, [el("button", {type: "button", class: "v2-ov-link", text: row ? row.name : (S.names[key] || `Player ${key}`), onclick: () => select(key, row && row.name)})]),
          el("td", {text: row ? row.pos : ""}),
          el("td", {class: "num", text: fmt(model)}),
          yours,
          el("td", {class: "num", text: finite(model) && finite(effective) ? signed(effective - model) : "—"}),
          el("td", {}, [el("button", {type: "button", class: "v2-ov-link", text: "Remove", "aria-label": `Remove override for ${row ? row.name : key}`,
            onclick: () => { setOverride(key, null); if (key === S.selected) S.draft = null; render(); }})])]));
      });
    tbl.append(body);
    box.append(el("div", {class: "v2-table-wrap"}, [tbl]));
  }

  // ---------- page ----------
  function render() {
    const page = $("v2Overrides");
    if (!page) return;
    // The picker is built once and repainted: the engine's own change events call render() while a reader is
    // dragging a slider or arrowing through the presets, and rebuilding it would drop focus and the drag.
    const basisBox = $("v2OvBasis");
    if (basisBox && $("v2OvPresets") && basisBox.contains($("v2OvPresets"))) S.repaintBasis && S.repaintBasis();
    else renderBasis(basisBox);
    const search = $("v2OvSearchBox");
    if (search) { search.replaceChildren(); renderSearch(search); }
    const editor = $("v2OvEditor");
    if (editor) renderEditor(editor);
    renderList($("v2OvList"));
    syncBar();
  }

  function boot(engine) {
    S.engine = engine;
    load();
    restoreLinkState();
    // The saved basis applies before the first view renders (no publish: nothing is drawn yet).
    if (S.mode !== "default") applyBasis(false);
    S.applied = JSON.stringify(engineBasis());
    if (Object.keys(S.values).length) {
      S.engine.setValueOverrides(S.values);
    }
    syncBar();
    // Anything else that sets the basis (a script, a link) moves the indicator too.
    window.addEventListener("trade-value-shared-change", () => syncBar());
  }

  root.DDFOverrides = {boot, render, count: () => Object.keys(S.values).length, all: () => ({...S.values}),
    basis: () => basisRecord(), shareParams, applyLink, dropOverridesNote, flag, state: S};
})(window);
