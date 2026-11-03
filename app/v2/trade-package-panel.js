// JEG-1183: on-demand package panel. The league adapter supplies one completed
// search snapshot; invalidation immediately removes the old package and lineup.
// No workspace, storage, network or pricing reads occur here.
(function (root) {
  "use strict";
  const node = typeof module !== "undefined" && module.exports;
  const deps = () => node ? {
    F: require("./finder.js"), P: require("./trade-package-constraints.js"),
    S: require("./trade-package-search.js"), V: require("./package-composition-preview.js")
  } : {F: root.TradeValueFinder, P: root.TradePackageConstraints,
    S: root.TradeValuePackageSearch, V: root.TradeValuePackagePreview};
  const SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];

  // A real lineup adapter: recorded roster slots are never used as starting slots.
  function lineups(before, after, ctx) {
    const {F} = deps();
    const missing = [];
    const side = league => {
      const team = league.teams.find(t => String(t.id) === String(league.myTeamId));
      const rows = team.entries.map(e => ctx.rowsByKey.get(String(e.key))).filter(Boolean);
      const picked = F.pickStarters(rows, ctx.shape, F.OUR_KEY);
      picked.unvalued.filter(r => !F.isNotEvaluated(r)).forEach(r => missing.push(`No DDF Value for ${r.name || r.player_key}.`));
      const row = (r, slot) => ({key: r ? String(r.player_key) : null, name: r ? r.name : "Empty", slot});
      return {starters: SLOTS.flatMap(slot => Array.from({length: ctx.shape[slot] || 0},
        (_, i) => row(picked.slots[slot][i], slot))), bench: picked.bench.map(r => row(r, r.pos))};
    };
    return {before: side(before), after: side(after), missing: [...new Set(missing)]};
  }

  function mount(container) {
    const {P, S, V} = deps();
    const el = (tag, text, cls) => {
      const n = document.createElement(tag);
      if (text) n.textContent = text;
      if (cls) n.className = cls;
      return n;
    };
    container.classList.add("trade-package-panel");
    container.setAttribute("aria-label", "Trade package");
    const heading = el("h2", "Trade package");
    const note = el("p", "Choose the highest-ranked viable offer, re-check the remaining offers, and repeat. This greedy method may miss a better combination.");
    const status = el("p", "", "package-panel-status");
    status.setAttribute("role", "status");
    const build = el("button", "Build package", "v2-btn package-panel-build");
    build.type = "button";
    const result = el("div", "", "package-panel-result");
    container.replaceChildren(heading, note, status, build, result);
    let snapshot = null;
    const clear = () => { result.replaceChildren(); delete container.dataset.packageSize; };
    const update = next => {
      if (next === snapshot) return;
      snapshot = next;
      clear();
      const ready = Boolean(next && next.status === "ready");
      build.disabled = !ready;
      container.dataset.state = ready ? "ready" : next && next.status || "empty";
      status.textContent = ready ? "Build a package from the completed search of included opponents."
        : next && next.status === "pending" ? "Finding trades… The previous package has been cleared."
        : "Add your team and an included opponent to find trade opportunities.";
    };
    build.addEventListener("click", () => {
      if (!snapshot || snapshot.status !== "ready") return;
      clear();
      let selected;
      try { selected = S.selectPackage(snapshot.league, snapshot.candidates, snapshot.ctx); }
      catch (error) { selected = {ok: false, errors: [{message: "Package search could not run. Find trade opportunities again."}]}; }
      if (!selected.ok) {
        container.dataset.state = "unavailable";
        status.textContent = selected.errors.map(e => e.message || e.code).join(" ");
        return;
      }
      container.dataset.state = selected.status;
      container.dataset.packageSize = String(selected.trades.length);
      status.textContent = selected.trades.length
        ? `${selected.trades.length} trades selected. DDF Value gained across the trades: +${selected.edge.toFixed(1)}.`
        : "No viable package was found among the included opponents.";
      if (snapshot.capped) status.textContent += " Only the opponents included in the completed search were considered.";
      if (!selected.trades.length) return;
      result.append(el("p", "The final valued lineup uses your league's QB, RB, WR, TE, FLEX and SUPERFLEX slots. Kickers and defenses are not valued."));
      const box = el("div");
      result.append(box);
      V.render(box, V.viewModel({league: snapshot.league, trades: selected.trades, package: P,
        lineup: {lineups: (a, b) => lineups(a, b, snapshot.ctx)}}));
    });
    update({status: "empty"});
    return {update};
  }
  function mountBefore(target) {
    const box = document.createElement("section");
    box.id = "v2LgPackage";
    target.before(box);
    return {element: box, ...mount(box)};
  }
  const api = {lineups, mount, mountBefore};
  if (node) { module.exports = api; return; }
  root.TradeValuePackagePanel = api;
})(typeof window !== "undefined" ? window : globalThis);
