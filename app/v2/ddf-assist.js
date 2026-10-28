// JEG-1026: the site side of the LLM <-> site round trip (spec: docs/design/llm-site-state.md).
//
//   * "Copy link" (JEG-1101): the current view's site link on the clipboard. The link is the whole hand-off: the DDF MCP tool's
//     read_state decodes the same query (league settings, rosters, trade, target), so there is no separate code to paste.
//     Jeremy, 2026-10-26: "We should focus on copying the site link to llms and having them decode whats in it, as opposed to
//     code from a link".
//   * Links: #find-trade?mine=..&theirs=.. and #trade-targets?target=.. (and any route with `view`) open with the rosters and
//     the player, through the same apply path.
//
// The page (v2.js) hands this file a narrow set of hooks in attach(); nothing here reaches into the page's state. The codec is
// ddf-state.js (DDFState), shared with the MCP function, so the site and the tools read and write one format.
(function (root) {
  "use strict";

  const ROUTES = {compare: "#compare-trade", targets: "#trade-targets", finder: "#find-trade"};
  const VIEW_NAMES = {compare: "Compare a trade", targets: "Trade targets", finder: "Find a trade"};
  const $ = id => document.getElementById(id);
  let H = null;   // the page's hooks
  const codec = () => root.DDFState;
  const finder = () => root.TradeValueFinder;

  const normName = name => (finder() && finder().normName ? finder().normName(name) : String(name || "").toLowerCase().trim());
  const isKey = key => /^\d{1,9}$/.test(String(key));
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const listText = names => names.join(", ");

  // ---------- state out ----------
  // Engine rows by key and by normalised name (a name two players share maps to both: never guessed).
  function rowIndex() {
    const rows = H.engine.getAllRows();
    const byKey = new Map();
    const byName = new Map();
    rows.forEach(row => {
      byKey.set(String(row.player_key), row);
      if (!row.name) return;
      const n = normName(row.name);
      if (!byName.has(n)) byName.set(n, []);
      byName.get(n).push(row);
    });
    return {byKey, byName};
  }
  // Players for the state: a numeric engine key travels as the key (with the name, which a chat reads); anything else
  // (a defense or kicker the engine does not price) is left out and counted.
  function outList(list, skipped) {
    const out = [];
    list.forEach(p => {
      if (!isKey(p.key)) { skipped.count += 1; return; }
      out.push({key: String(p.key), name: p.name});
    });
    return out;
  }
  function buildState() {
    const skipped = {count: 0};
    const work = {};
    const view = H.view();
    if (view) work.view = view;
    const trade = H.getTrade();
    if (trade.give.length) work.give = outList(trade.give, skipped);
    if (trade.get.length) work.get = outList(trade.get, skipped);
    const ui = finder() && finder().ui;
    if (ui) {
      const mine = ui.getMine();
      const theirs = ui.getTheirs();
      if (mine.length) work.mine = outList(mine, skipped);
      if (theirs.length) work.theirs = outList(theirs, skipped);
    }
    const search = String(H.getTarget() || "").trim();
    if (search) {
      const hits = rowIndex().byName.get(normName(search)) || [];
      if (hits.length === 1) work.target = {key: String(hits[0].player_key), name: hits[0].name};
    }
    const raw = {v: codec().VERSION, work, sources: H.sources()};
    const league = (codec().decodeQuery(H.leagueQuery()).state || {}).league;
    if (league) raw.league = league;
    const capped = ["give", "get", "mine", "theirs"].filter(name => work[name] && work[name].length > 40);
    const normalized = codec().normalize(raw);
    return {state: normalized.state, skipped: skipped.count, capped};
  }
  function siteLink(state) {
    const route = ROUTES[state.work && state.work.view] || "#trade-targets";
    return location.href.split("#")[0] + route + "?" + codec().encodeQuery(state);
  }
  function linkText() {
    const built = buildState();
    if (!built.state) return null;
    return {text: siteLink(built.state), built};
  }

  // ---------- state in ----------
  function resolveOne(entry, index) {
    if (entry.key !== undefined && index.byKey.has(String(entry.key))) return {row: index.byKey.get(String(entry.key))};
    const name = entry.name;
    if (name) {
      const hits = index.byName.get(normName(name)) || [];
      if (hits.length === 1) return {row: hits[0]};
      return {why: hits.length ? `${name} (more than one player has this name)` : `${name} (not in the values)`};
    }
    return {why: `player ${entry.key} (not in the values)`};
  }
  // Entries -> engine rows, de-duplicated; unresolved names are reported, never guessed.
  function resolveList(list, index, unresolved) {
    const seen = new Set();
    const rows = [];
    (list || []).forEach(entry => {
      const got = resolveOne(entry, index);
      if (!got.row) { unresolved.push(got.why); return; }
      const key = String(got.row.player_key);
      if (seen.has(key)) return;
      seen.add(key);
      rows.push(got.row);
    });
    return rows;
  }

  // Apply a decoded state (from a link) to the page. Returns {applied: [sentence], ignored: [sentence], view}.
  function applyState(state, warnings) {
    const applied = [];
    const ignored = (warnings || []).slice();
    if (!state) return {applied, ignored, view: ""};
    if (state.league) {
      const before = H.leagueQuery();
      H.applyLinkLeague(new URLSearchParams(codec().encodeQuery({league: state.league})));
      applied.push(H.leagueQuery() === before ? `League settings already matched (${H.leagueText()}).` : `League set to ${H.leagueText()}.`);
    }
    const work = state.work || {};
    const index = rowIndex();
    const unresolved = [];
    if (work.give || work.get) {
      const pick = rows => rows.map(row => ({key: String(row.player_key), name: row.name}));
      const give = pick(resolveList(work.give, index, unresolved));
      const get = pick(resolveList(work.get, index, unresolved));
      // A player on both sides of a trade is on neither: keep the give side's.
      const giveKeys = new Set(give.map(p => p.key));
      const getOnly = get.filter(p => !giveKeys.has(p.key));
      if (getOnly.length !== get.length) ignored.push("A player listed on both sides of the trade stays on the give side only.");
      H.setTrade(give, getOnly);
      applied.push(`Compare a trade: you give ${plural(give.length, "player")}, you get ${plural(getOnly.length, "player")}.`);
    }
    if ((work.mine || work.theirs) && finder() && finder().ui && finder().ui.setSides) {
      const shape = row => ({key: String(row.player_key), name: row.name, pos: row.pos, team: row.team});
      const mine = resolveList(work.mine, index, unresolved).map(shape);
      const theirs = resolveList(work.theirs, index, unresolved).map(shape);
      const done = finder().ui.setSides(mine, theirs);
      if (done.bothSides.length) ignored.push(`On both rosters, kept on yours only: ${listText(done.bothSides)}.`);
      applied.push(`Find a trade: your roster ${plural(mine.length, "player")}, their roster ${plural(theirs.length - done.bothSides.length, "player")}. Undo on that page puts back what was there.`);
    }
    if (work.target) {
      const rows = resolveList([work.target], index, unresolved);
      if (rows.length) { H.setTarget(rows[0].name); applied.push(`Trade target: ${rows[0].name}.`); }
    }
    if (unresolved.length) ignored.push(`Not matched, left out: ${listText(unresolved)}.`);
    if (state.sources || state.asOf) ignored.push("The sources and date in the state are advisory; this page keeps the ones it shows.");
    // Where to look: the state's own view, else the tab its contents belong to.
    const view = work.view || (work.mine || work.theirs ? "finder" : work.target ? "targets" : work.give || work.get ? "compare" : "");
    return {applied, ignored, view};
  }

  // ---------- the report ----------
  function show(report, origin) {
    const box = $("v2AssistNote");
    if (!box) return;
    box.replaceChildren();
    const add = (label, items) => {
      if (!items.length) return;
      const p = document.createElement("p");
      const b = document.createElement("strong");
      b.textContent = label;
      p.append(b, " " + items.join(" "));
      box.append(p);
    };
    if (report.applied.length) add("Applied.", report.applied);
    else add("Nothing applied.", ["No usable DDF state was found."]);
    add(report.applied.length ? "Ignored." : "Why.", report.ignored);
    box.hidden = false;
    box.dataset.origin = origin;
    const where = report.view ? ` Showing ${VIEW_NAMES[report.view]}.` : "";
    const lead = report.applied.length ? `Opened with the shared state.${where}` : "No usable state found.";
    H.say(`${lead}${report.ignored.length ? ` ${plural(report.ignored.length, "note")} below the page.` : ""}`, 9000);
  }

  function applyFrom(result, origin) {
    const report = applyState(result.state, result.warnings);
    show(report, origin);
    return report;
  }
  // A link's query (find-trade / trade-targets / any route with `view`).
  function applyLink(query) {
    if (!H || !codec()) return null;
    return applyFrom(codec().decodeQuery(query), "link");
  }

  // ---------- controls ----------
  async function copy() {
    const note = $("v2AssistNote");
    const built = linkText();
    note.hidden = false;
    note.replaceChildren();
    const say = text => { const p = document.createElement("p"); p.textContent = text; note.append(p); };
    if (!built) { say("There is nothing to copy yet."); return; }
    const s = built.built.state;
    const parts = [s.league ? H.leagueText() : ""];
    const w = s.work || {};
    if (w.give || w.get) parts.push(`a trade (${(w.give || []).length} for ${(w.get || []).length})`);
    if (w.mine || w.theirs) parts.push(`both rosters on Find a trade`);
    if (w.target) parts.push(`the target ${w.target.name}`);
    const what = parts.filter(Boolean).join(", ");
    const extra = (built.built.skipped ? ` ${plural(built.built.skipped, "defense or kicker")} left out: the site gives them no value.` : "")
      + (built.built.capped.length ? " Lists are cut to 40 players." : "");
    try {
      await navigator.clipboard.writeText(built.text);
      say(`✓ Copied the link: ${what}.${extra}`);
    } catch (error) {
      // No clipboard permission: show the text, selected, to copy by hand.
      const area = document.createElement("textarea");
      area.className = "v2-assist-text";
      area.readOnly = true;
      area.value = built.text;
      area.setAttribute("aria-label", "Link to copy");
      say(`Copy this link: ${what}.${extra}`);
      note.append(area);
      area.focus();
      area.select();
    }
    H.say("Copied the link.", 4000);
  }

  function bind() {
    const copyButton = $("v2AssistCopy");
    if (!copyButton) return;
    copyButton.hidden = false;
    const hint = $("v2AssistCopyHint");
    if (hint) hint.hidden = false;
    copyButton.addEventListener("click", copy);
  }

  function attach(hooks) {
    H = hooks;
    if (!codec()) return;   // the codec did not load: the controls stay hidden, the footer line still shows
    bind();
  }

  root.DDFAssist = {attach, applyLink, applyState, buildState, linkText};
})(typeof window !== "undefined" ? window : globalThis);
