// Trade Value v2 — Trade ideas card on Find a trade (JEG-1217 stage 3): Trade opportunities re-read through the Managers card.
//
// A card between Managers and Trade opportunities. Recommendations: the trades that are a gain for you, ranked by your gain,
// each with how likely the other manager may take it (Likely or Possible, in words), the row's roster check for both teams
// when one is missing or failed, and why. Stretch offers: long shots, in their own section below. The math is
// manager-recs.js; this file only draws it. Nothing here changes a value, a fit or the Trade opportunities table.
//
// Mounts itself once the Managers card exists (manager-profiles-ui.js) and redraws when Trade opportunities redraws, when a
// profile changes and when the league changes, so league.js is not edited.
(function (root) {
  "use strict";
  if (typeof document === "undefined") return;
  const R = root.TradeValueManagerRecs;
  const M = root.TradeValueManagerProfiles;
  const W = root.TradeValueWorkspace;
  if (!R || !M || !W || !M.store || !W.store) return;
  const $ = id => document.getElementById(id);
  const PAGE = 10;
  const UI = {mounted: false, shown: PAGE, timer: null, last: null};

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (v === false || v === null || v === undefined) return; if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v); });
    node.append(...kids.filter(k => k !== null && k !== undefined && k !== false));
    return node;
  }
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || `${one}s`)}`;
  // Our own construction check for a "partial" row, recomputed once per row object (opportunities.js fullFit).
  const fits = new WeakMap();
  function fullFit(row) {
    const O = root.TradeValueOpportunities;
    if (!O || !O.fullFit) return null;
    if (!fits.has(row)) fits.set(row, O.fullFit(row));
    return fits.get(row);
  }

  function compute() {
    const L = root.TradeValueLeague;
    const C = root.TradeValueCurveControls;
    const result = L && L.ui && L.ui.result;
    if (!result || !C || !C.getAllRows) return null;
    return R.build({rows: result.rows, book: M.store.get(), ws: W.store.get(), allRows: C.getAllRows(), profiles: M, fullFit});
  }

  // v is R.view(rec): every shown string comes from there, so the redraw check below sees all of it.
  function item(v, i, stretch) {
    const key = `${stretch ? "s" : "r"}${i}`;
    return el("li", {class: "v2-mi-item", "data-trade-id": v.id, "data-band": v.band, "data-health": v.health ? "warn" : "ok"},
      el("div", {class: "v2-mi-head"},
        el("b", {class: "v2-mi-opp", text: v.opponent}),
        el("span", {class: `v2-mi-band is-${v.band}`, text: v.likelihood}),
        el("span", {class: "v2-mi-gain", text: v.gain})),
      v.health ? el("p", {class: "v2-meta v2-mi-health", text: v.health}) : null,
      el("p", {class: "v2-mi-deal"}, el("span", {text: v.give}), " ", el("span", {text: v.receive})),
      el("details", {class: "v2-mi-why", id: `v2MiWhy-${key}`},
        el("summary", {text: "Why"}),
        el("ul", {class: "v2-mi-lines"}, ...v.why.map(line => el("li", {text: line}))),
        el("p", {class: "v2-meta v2-mi-sources", text: v.sources})));
  }

  function countsText(out) {
    const c = out.counts;
    const left = [];
    if (c.excluded) left.push(`${plural(c.excluded, "trade")} with managers marked won't trade`);
    if (c.notWin) left.push(`${plural(c.notWin, "trade")} that ${c.notWin === 1 ? "isn't" : "aren't"} a gain for you`);
    if (c.hidden) left.push(`${plural(c.hidden, "trade")} too far below even for them`);
    if (c.noAppeal) left.push(`${plural(c.noAppeal, "trade")} with nothing to judge their side by`);
    return `From ${plural(c.considered, "trade opportunity", "trade opportunities")}.${left.length ? ` Left out: ${left.join("; ")}.` : ""}`;
  }

  function render() {
    UI.timer = null;
    const card = $("v2LgIdeas");
    if (!card) return;
    const managers = $("v2LgManagers");
    const opps = $("v2LgOpps");
    const out = compute();
    card.hidden = !managers || managers.hidden || !opps || opps.hidden || !out;
    const list = $("v2MiList");
    const stretch = $("v2MiStretch");
    // Cleared while hidden, so the same results draw again when the card comes back.
    if (card.hidden) { list.replaceChildren(); stretch.replaceChildren(); stretch.hidden = true; UI.last = null; return; }
    const recs = out.recommendations.map(R.view);
    const longShots = out.stretch.map(R.view);
    const sig = JSON.stringify([recs, longShots, out.counts, UI.shown]);
    if (sig === UI.last) return;   // Trade opportunities redraws often (sorting, filters); the ideas only redraw when what they show changes.
    UI.last = sig;
    $("v2MiCount").textContent = `${plural(out.recommendations.length, "idea")}${out.stretch.length ? `, ${plural(out.stretch.length, "stretch offer")}` : ""}`;
    $("v2MiFrom").textContent = countsText(out);
    if (!recs.length) list.replaceChildren(el("li", {class: "v2-meta v2-mi-empty", id: "v2MiEmpty",
      text: out.counts.considered ? "No trade ideas yet: none of the trade opportunities is a gain for you that these managers may take." : "No trade opportunities to read yet."}));
    else list.replaceChildren(...recs.slice(0, UI.shown).map((r, i) => item(r, i, false)));
    const more = $("v2MiMore");
    more.hidden = recs.length <= UI.shown;
    more.textContent = `Show all ${recs.length}`;
    stretch.hidden = !out.stretch.length;
    stretch.replaceChildren(...(out.stretch.length ? [
      el("summary", {text: `Stretch offers (${out.stretch.length})`}),
      el("p", {class: "v2-meta", text: "Long shots: by your read of the manager they come out 10% to 25% behind on what they send. Each one says which belief has to hold."}),
      el("ol", {class: "v2-mi-list"}, ...longShots.map((v, i) => item(v, i, true)))] : []));
  }
  // Redraws are batched: Trade opportunities, the profiles and the league can all change in one tick.
  const schedule = () => { if (UI.timer === null) UI.timer = setTimeout(render, 30); };

  function build() {
    const more = el("button", {type: "button", class: "v2-btn", id: "v2MiMore", hidden: true});
    more.addEventListener("click", () => { UI.shown = Infinity; render(); });
    return el("section", {class: "v2-card v2-mi", id: "v2LgIdeas", "aria-labelledby": "v2MiTitle", hidden: true},
      el("div", {class: "v2-card-head"}, el("div", {},
        el("h2", {id: "v2MiTitle", text: "Trade ideas"}),
        el("p", {class: "v2-meta", text: "Trades that are a gain for you, best first. Work down the list until one is accepted. How likely is your own read of each manager from the Managers card, not a prediction."}))),
      el("div", {class: "v2-ctoolbar v2-mi-toolbar"}, el("b", {id: "v2MiCount"}), el("span", {class: "v2-meta", id: "v2MiFrom", role: "status", "aria-live": "polite"})),
      el("ol", {class: "v2-mi-list", id: "v2MiList"}),
      more,
      el("details", {class: "v2-mi-stretch", id: "v2MiStretch", hidden: true}));
  }

  function mount() {
    if (UI.mounted) return true;
    const managers = $("v2LgManagers");
    const body = $("v2LgOppsBody");
    if (!managers || !managers.parentNode || !body) return false;
    managers.parentNode.insertBefore(build(), managers.nextSibling);
    UI.mounted = true;
    new MutationObserver(schedule).observe(body, {childList: true, subtree: true});
    const opps = $("v2LgOpps");
    if (opps) new MutationObserver(schedule).observe(opps, {attributes: true, attributeFilter: ["hidden"]});
    new MutationObserver(schedule).observe(managers, {attributes: true, attributeFilter: ["hidden"]});
    M.store.onChange(() => schedule());
    W.store.onChange(() => { UI.shown = PAGE; schedule(); });
    render();
    return true;
  }
  function start() {
    if (mount()) return;
    let tries = 0;
    const timer = setInterval(() => { tries += 1; if (mount() || tries > 120) clearInterval(timer); }, 250);
  }
  root.TradeValueTradeIdeas = {render, compute};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof window !== "undefined" ? window : globalThis);
