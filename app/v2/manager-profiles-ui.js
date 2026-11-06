// Trade Value v2 — Managers card on Find a trade (JEG-1217 stage 1): describe how each league-mate values players.
//
// A card between Team summary and Trade opportunities. For every team except yours: a "Won't trade" switch and, under
// Describe, how much the manager leans on each anchor (manager-profiles.js), how sure you are, and a few fixed boxes to
// tick (Likes rookies, Win-now, Rarely trades...). No free text, and every manager starts with nothing set. Saved
// on this device as you change it, with Download / Load of a profiles file; the toolbar says when the browser won't save
// (blocked or full) so nothing is lost silently. A note or "Other preferences" level saved by an earlier build is shown
// read-only as kept, never dropped. Nothing here changes a value, a fit or the opportunities ranking; Trade ideas
// (manager-recs-ui.js) reads them.
//
// Mounts itself once the Your league card exists (league.js) and follows the shared league store (workspace.js), so
// league.js is not edited. Profiles of removed teams are dropped on the next load, not at once, so Undo of a removal
// brings the team back with its profile.
(function (root) {
  "use strict";
  if (typeof document === "undefined") return;
  const M = root.TradeValueManagerProfiles;
  const W = root.TradeValueWorkspace;
  if (!M || !W || !M.store || !W.store) return;
  const profiles = M.store;
  const league = W.store;
  const $ = id => document.getElementById(id);

  const LEVEL_TEXT = {unknown: "Not sure", none: "Doesn't care", some: "Somewhat", strong: "A lot"};
  const CONFIDENCE_TEXT = {unknown: "Not set", low: "A guess", medium: "Fairly sure", high: "Sure"};
  const ANCHOR_HELP = {draft: "Values players by where they were drafted", market: "Goes by trade value charts and market prices",
    rankings: "Goes by player rankings", names: "Wants well-known players"};
  const UI = {open: new Set(), status: "", mounted: false};
  const SAVE_TEXT = {idle: "", saving: "Saving…", saved: "Saved on this device.",
    unavailable: "Not saved: this browser isn't letting the page save. Download profiles to keep them.",
    full: "Not saved: this browser's storage is full. Download profiles to keep them."};

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (v === false || v === null || v === undefined) return; if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v); });
    node.append(...kids.filter(k => k !== null && k !== undefined && k !== false));
    return node;
  }
  const lower = text => text.charAt(0).toLowerCase() + text.slice(1);
  const listJoin = items => (items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`);

  // One line on how the reader described this manager. Words only: no score.
  function summaryText(row) {
    const d = row.description;
    if (d.excluded) return "Won't trade: left out of trade ideas.";
    const name = a => lower(M.ANCHOR_LABELS[a]);
    const ticked = d.tags.map(tag => M.TAG_LABELS[tag]);
    const kept = d.legacy.note || d.legacy.subjective ? " Earlier note kept." : "";
    let text;
    if (d.kind === "unknown" && ticked.length) return `${listJoin(ticked)}.${kept}`;
    if (d.kind === "unknown" && kept) return kept.trim();
    if (d.kind === "unknown") text = "Not described yet.";
    // "None" only when all are marked doesn't care; otherwise name the ones that are, the rest are still not set.
    else if (d.kind === "none" && !d.unknownAnchors.length) text = "None of the usual anchors.";
    else if (d.kind === "none") text = `Doesn't care about ${listJoin(M.ANCHORS.filter(a => !d.unknownAnchors.includes(a)).map(name))}; the rest not set.`;
    else if (d.kind === "single") text = `Leans on ${name(d.active[0])}${d.strong.length ? " a lot" : ""}.`;
    else text = `Mixed: ${listJoin(d.active.map(a => name(a) + (d.strong.includes(a) ? " (a lot)" : "")))}.`;
    if (d.kind !== "unknown" && d.confidence !== "unknown") text += ` ${CONFIDENCE_TEXT[d.confidence]}.`;
    if (ticked.length) text += ` ${listJoin(ticked)}.`;
    return text + kept;
  }

  const ws = () => league.get();
  const rowFor = teamId => M.roster(profiles.get(), ws()).find(r => r.teamId === teamId);
  function edit(teamId, fn) {
    profiles.update(book => fn(book, ws(), teamId), "edit");
    const row = rowFor(teamId);
    const line = row && $(`v2MgSummary-${cssId(teamId)}`);
    if (line) line.textContent = summaryText(row);
    renderCount();
  }
  const cssId = id => String(id).replace(/[^A-Za-z0-9_-]/g, "_");

  function select(id, label, options, value, onChange) {
    const s = el("select", {id, class: "v2-mg-select"});
    options.forEach(([v, text]) => { const o = el("option", {value: v, text}); if (v === value) o.selected = true; s.append(o); });
    s.addEventListener("change", () => onChange(s.value));
    return el("label", {class: "v2-mg-field", for: id}, el("span", {class: "v2-mg-field-name", text: label}), s);
  }

  function teamItem(row) {
    const key = cssId(row.teamId);
    const p = row.profile;
    const won = el("input", {type: "checkbox", id: `v2MgExcl-${key}`, class: "v2-mg-excl"});
    won.checked = p.excluded;
    won.addEventListener("change", () => edit(row.teamId, (b, w, id) => M.ops.setExcluded(b, w, id, won.checked)));
    const anchors = el("fieldset", {class: "v2-mg-anchors"}, el("legend", {text: `How much does ${row.name} lean on each?`}),
      ...M.ANCHORS.map(a => {
        const field = select(`v2MgA-${a}-${key}`, M.ANCHOR_LABELS[a], M.LEVELS.map(l => [l, LEVEL_TEXT[l]]), p.anchors[a],
          v => edit(row.teamId, (b, w, id) => M.ops.setAnchor(b, w, id, a, v)));
        field.title = ANCHOR_HELP[a];
        return field;
      }));
    const confidence = select(`v2MgConf-${key}`, "How sure are you?", M.CONFIDENCE.map(c => [c, CONFIDENCE_TEXT[c]]), p.confidence,
      v => edit(row.teamId, (b, w, id) => M.ops.setConfidence(b, w, id, v)));
    const tags = el("fieldset", {class: "v2-mg-tags"}, el("legend", {text: "Anything else that fits?"}),
      ...M.TAGS.map(tag => {
        const id = `v2MgT-${tag}-${key}`;
        const box = el("input", {type: "checkbox", id, class: "v2-mg-tag"});
        box.checked = p.tags.includes(tag);
        box.addEventListener("change", () => edit(row.teamId, (b, w, teamId) => M.ops.setTag(b, w, teamId, tag, box.checked)));
        return el("label", {class: "v2-mg-tag-label", for: id}, box, el("span", {text: M.TAG_LABELS[tag]}));
      }));
    // Kept from an earlier build: read-only, cleared only with the whole profile.
    const legacy = M.legacyOf(p);
    const kept = legacy.note || legacy.subjective ? el("div", {class: "v2-mg-kept"},
      el("p", {class: "v2-meta", text: "Kept from an earlier note:"}),
      legacy.subjective ? el("p", {class: "v2-mg-kept-line", text: `Other preferences: ${LEVEL_TEXT[legacy.subjective]}`}) : null,
      legacy.note ? el("p", {class: "v2-mg-kept-line", text: legacy.note}) : null) : null;
    const reset = el("button", {type: "button", class: "v2-btn v2-mg-reset", text: "Clear this profile"});
    reset.addEventListener("click", () => {
      profiles.update(book => M.ops.reset(book, ws(), row.teamId), "reset");
      render();
      const again = $(`v2MgDescribe-${key}`);
      if (again) again.querySelector("summary").focus();
    });
    const describe = el("details", {class: "v2-mg-describe", id: `v2MgDescribe-${key}`, open: UI.open.has(row.teamId)},
      el("summary", {text: "Describe"}),
      el("div", {class: "v2-mg-body"}, anchors, confidence, tags, kept, reset));
    describe.addEventListener("toggle", () => { if (describe.open) UI.open.add(row.teamId); else UI.open.delete(row.teamId); });
    return el("li", {class: "v2-mg-team", "data-team-id": row.teamId},
      el("div", {class: "v2-mg-head"},
        el("b", {class: "v2-mg-name", text: row.name}),
        el("span", {class: "v2-meta v2-mg-summary", id: `v2MgSummary-${key}`, text: summaryText(row)}),
        el("label", {class: "v2-mg-excl-label", for: `v2MgExcl-${key}`}, won, el("span", {text: "Won't trade"}))),
      describe);
  }

  function renderCount() {
    const node = $("v2MgCount");
    if (!node) return;
    const rows = M.roster(profiles.get(), ws()).filter(r => !r.mine);
    const out = rows.filter(r => r.profile.excluded).length;
    const described = rows.filter(r => r.description.kind !== "unknown" || r.description.tags.length || r.description.legacy.note || r.description.legacy.subjective).length;
    node.textContent = rows.length ? `${described} of ${rows.length} described${out ? `, ${out} won't trade` : ""}` : "";
  }
  function renderStatus() {
    const node = $("v2MgStatus");
    if (node) node.textContent = UI.status;
  }
  function renderSave() {
    const node = $("v2MgSave");
    if (!node) return;
    const state = profiles.status();
    node.textContent = SAVE_TEXT[state] || "";
    node.classList.toggle("is-unsaved", state === "unavailable" || state === "full");
  }
  function render() {
    const card = $("v2LgManagers");
    if (!card) return;
    const rows = M.roster(profiles.get(), ws());
    const others = rows.filter(r => !r.mine);
    card.hidden = others.length === 0;
    const mine = rows.find(r => r.mine);
    $("v2MgMine").textContent = mine ? `${mine.name} is your team, so it isn't listed.` : "Mark your team with the star in Your league; it won't be listed here.";
    $("v2MgTeams").replaceChildren(...others.map(teamItem));
    renderCount();
    renderStatus();
  }

  function download() {
    const blob = new Blob([M.exportJson(profiles.get(), ws())], {type: "application/json"});
    const a = el("a", {href: URL.createObjectURL(blob), download: "manager-profiles.json"});
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function load(file) {
    const reader = new FileReader();
    reader.onload = () => {
      const out = M.importJson(profiles.get(), ws(), String(reader.result || ""));
      if (out.error) UI.status = out.error;
      else {
        if (out.book !== profiles.get()) profiles.update(() => out.book, "import");
        UI.status = `Loaded ${out.matched} ${out.matched === 1 ? "profile" : "profiles"}.` + (out.unmatched.length ? ` Not matched to a team here: ${listJoin(out.unmatched)}.` : "");
      }
      render();
    };
    reader.onerror = () => { UI.status = "That file could not be read."; renderStatus(); };
    reader.readAsText(file);
  }

  function build() {
    const file = el("input", {type: "file", accept: "application/json,.json", id: "v2MgFile", class: "v2-sr", tabindex: "-1"});
    file.addEventListener("change", () => { if (file.files && file.files[0]) load(file.files[0]); file.value = ""; });
    const down = el("button", {type: "button", class: "v2-btn", id: "v2MgDownload", text: "Download profiles"});
    down.addEventListener("click", download);
    const up = el("button", {type: "button", class: "v2-btn", id: "v2MgLoad", text: "Load profiles"});
    up.addEventListener("click", () => file.click());
    return el("section", {class: "v2-card v2-mg", id: "v2LgManagers", "aria-labelledby": "v2MgTitle", hidden: true},
      el("div", {class: "v2-card-head"}, el("div", {},
        el("h2", {id: "v2MgTitle", text: "Managers"}),
        el("p", {class: "v2-meta", text: "How you think each manager values players, and who won't trade. These are your own read on them, not facts about the manager. They shape Trade ideas below; they don't change values, fits or Trade opportunities."}))),
      el("div", {class: "v2-ctoolbar v2-mg-toolbar"}, el("b", {id: "v2MgCount"}), down, up, file,
        el("span", {class: "v2-meta v2-mg-save", id: "v2MgSave", role: "status", "aria-live": "polite"}),
        el("span", {class: "v2-meta", id: "v2MgStatus", role: "status", "aria-live": "polite"})),
      el("p", {class: "v2-meta", id: "v2MgMine"}),
      el("ul", {class: "v2-mg-teams", id: "v2MgTeams"}));
  }

  function mount() {
    if (UI.mounted) return true;
    const summary = $("v2LgSummary");
    if (!summary || !summary.parentNode) return false;
    summary.parentNode.insertBefore(build(), summary.nextSibling);
    UI.mounted = true;
    const status = profiles.loadStatus();
    if (status === "corrupt" || status === "version") UI.status = "Saved manager profiles could not be read. You can describe the managers again.";
    // Profiles of teams no longer in the league go now, at load; during the visit they wait so Undo can bring them back.
    const out = M.ops.reconcile(profiles.get(), ws());
    if (out.dropped.length) profiles.update(() => out.book, "reconcile");
    league.onChange(() => render());
    profiles.onChange((_, change) => { if (change.reason === "other-tab") render(); });
    profiles.onStatus(renderSave);
    render();
    renderSave();
    return true;
  }
  function start() {
    if (mount()) return;
    let tries = 0;
    const timer = setInterval(() => { tries += 1; if (mount() || tries > 120) clearInterval(timer); }, 250);
  }
  root.TradeValueManagersCard = {render, summaryText};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof window !== "undefined" ? window : globalThis);
