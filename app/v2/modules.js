// Trade Value v2 — every module card expands and collapses (JEG-500, contract GL-17 and GL-18).
//
// No engine, no values: this only changes how a card is laid out. Each card gets
//   * a chevron (44 px, aria-expanded) that collapses it to its title plus a one-line
//     summary read from what the card already says, so nothing gets lost;
//   * an expand control. Player values' chart and table already have one (JEG-483), so
//     theirs is reused; every other card spans its row at full height, with no inner scroll cap.
// The collapsed cards are remembered on this device (localStorage, one key, one entry per card).
(function () {
  "use strict";

  const SAVE_KEY = "ddf.v2.modules";
  const $ = id => document.getElementById(id);
  const text = id => { const el = $(id); return el ? el.textContent.replace(/\s+/g, " ").trim() : ""; };
  const count = selector => document.querySelectorAll(selector).length;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  // One entry per card, keyed by the id of its heading. summary() reads the page the reader sees;
  // expand names an existing expand control to reuse. A card whose summary is empty says "No data yet".
  const CARDS = [
    {title: "v2ChartTitle", name: "Chart", expand: "v2ExpandChart", summary: () => text("v2TableMeta")},
    {title: "v2TableTitle", name: "Table", expand: "v2ExpandTable", summary: () => text("v2TableMeta")},
    {title: "v2VorpTitle", name: "Value above waivers", summary: () => "How much better each player is than the best free pickup"},
    {title: "v2TSellTitle", name: "Sell", summary: () => `Sell: ${text("v2TSellMeta")}`},
    {title: "v2TBuyTitle", name: "Buy", summary: () => `Buy: ${text("v2TBuyMeta")}`},
    {title: "v2TCheck2Title", name: "Positions the market overpays for", summary: () => text("v2WeightHeadline")},
    {title: "v2RRiseTitle", name: "Rising",
      summary: () => `Rising: ${plural(count("#v2RRise li"), "player", "players")} shown`},
    {title: "v2RFallTitle", name: "Falling",
      summary: () => `Falling: ${plural(count("#v2RFall li"), "player", "players")} shown`},
    {title: "v2RMktTitle", name: "The charts moved first",
      summary: () => `The charts moved first: ${plural(count("#v2RMkt li[data-player-key]"), "player", "players")} shown`},
    {title: "v2RProjTitle", name: "The projections moved first",
      summary: () => `The projections moved first: ${plural(count("#v2RProj li[data-player-key]"), "player", "players")} shown`},
    {title: "v2GiveTitle", name: "You give", summary: () => sideSummary("You give", "v2GivePlayers", "v2GiveTotal")},
    {title: "v2GetTitle", name: "You receive", summary: () => sideSummary("You receive", "v2GetPlayers", "v2GetTotal")},
    {title: "v2CVerdictTitle", name: "Verdict", summary: () => text("v2CVerdictTitle")},
    {title: "v2CRostersTitle", name: "Loaded rosters", summary: () => text("v2CRosterStatus") || "Choose two loaded rosters"},
    {title: "v2CConstructionTitle", name: "Both rosters after this trade", summary: () => text("v2CConstructionBody") || "Add players on both sides"},
    {title: "v2CResultTitle", name: "Difference by source",
      summary: () => text("v2CMeta") || text("v2CEmpty")},
    {title: "v2FindTitle", name: "Find a trade",
      summary: () => "Trades you win that they'll still say yes to"},
    {title: "v2LgTitle", name: "Your league", summary: () => text("v2LgCount") || "Your league"},
    {title: "v2LgSummaryTitle", name: "Team summary", summary: () => text("v2LgSummaryHeadline") || "Roster, starter and bench value for every team"},
    {title: "v2LgOppsTitle", name: "Trade opportunities", summary: () => text("v2LgOppsHeadline") || "Your team against every other team"},
    {title: "v2CVorpTitle", name: "Value above waivers", summary: () => "How much better each player is than the best free pickup"},
  ];

  function sideSummary(label, listId, totalId) {
    const n = count(`#${listId} li`);
    if (!n) return `${label}: no players yet`;
    const total = text(totalId);
    return `${label}: ${plural(n, "player", "players")}${total ? ` · ${total}` : ""}`;
  }

  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "null");
      return saved && saved.v === 1 && saved.collapsed && typeof saved.collapsed === "object" ? saved.collapsed : {};
    } catch (e) { return {}; }
  }
  function save(collapsed) {
    try { localStorage.setItem(SAVE_KEY, JSON.stringify({v: 1, collapsed})); } catch (e) { /* private window: not remembered */ }
  }

  const collapsed = load();

  function build(spec) {
    const heading = $(spec.title);
    const card = heading && heading.closest(".v2-card");
    if (!card || card.dataset.module) return;
    const name = spec.name;
    card.dataset.module = spec.title;
    card.classList.add("v2-mod");

    card.firstElementChild.classList.add("v2-mod-head");
    const summary = document.createElement("p");
    summary.className = "v2-meta v2-mod-sum";
    summary.id = `${spec.title}Sum`;
    card.insertBefore(summary, card.children[1] || null);

    const controls = document.createElement("div");
    controls.className = "v2-mod-ctl";
    const expand = document.createElement("button");
    expand.type = "button";
    expand.className = "v2-mod-btn v2-mod-expand";
    if (spec.expand) {
      // Player values: the chart and the table already open full screen (JEG-483); reuse that.
      expand.textContent = "⤢";
      expand.setAttribute("aria-label", `Expand ${name.toLowerCase()} to full screen`);
      expand.setAttribute("aria-haspopup", "dialog");
      expand.addEventListener("click", () => { const real = $(spec.expand); if (real) real.click(); });
    } else {
      expand.textContent = "⤢";
      expand.setAttribute("aria-label", `Expand ${name} to full width`);
      expand.setAttribute("aria-pressed", "false");
      expand.addEventListener("click", () => {
        const on = card.dataset.xl !== "true";
        card.dataset.xl = String(on);
        expand.setAttribute("aria-pressed", String(on));
        expand.setAttribute("aria-label", on ? `Return ${name} to its normal size` : `Expand ${name} to full width`);
        window.dispatchEvent(new Event("resize"));
      });
    }
    const chevron = document.createElement("button");
    chevron.type = "button";
    chevron.className = "v2-mod-btn v2-mod-chevron";
    chevron.setAttribute("aria-controls", heading.id);
    chevron.innerHTML = '<span aria-hidden="true">▾</span>';
    controls.append(expand, chevron);
    card.prepend(controls);

    const refresh = () => {
      const closed = collapsed[spec.title] === true;
      card.dataset.collapsed = String(closed);
      chevron.setAttribute("aria-expanded", String(!closed));
      chevron.setAttribute("aria-label", closed ? `Expand ${name}` : `Collapse ${name}`);
      expand.hidden = closed;
      const line = closed ? spec.summary() || "No data yet" : "";
      if (summary.textContent !== line) summary.textContent = line;   // same text: no mutation, no loop
    };
    chevron.addEventListener("click", () => {
      if (collapsed[spec.title]) delete collapsed[spec.title];
      else collapsed[spec.title] = true;
      save(collapsed);
      refresh();
      // A chart drawn while its card was hidden has no width; ask the page to draw it again.
      window.dispatchEvent(new Event("resize"));
    });
    // The summary follows the card's own content while it is collapsed.
    new MutationObserver(() => { if (card.dataset.collapsed === "true") refresh(); })
      .observe(card, {subtree: true, childList: true, characterData: true});
    refresh();
  }

  function init() { CARDS.forEach(build); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
