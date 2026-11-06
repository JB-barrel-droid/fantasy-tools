// JEG-1420: isolated reader for waiver-board 0.1.x and opt-in local 0.2.x swaps.
// The caller loads/validates the built artifact and owns routing/settings.
// No engine, roster, network, clock or persistence access in this renderer.
(function (root) {
  "use strict";

  const SOURCE_NAMES = {
    values: "DDF Value", values_prior: "Previous DDF Value", points: "Weekly points",
    status: "Player status", bye: "Byes", rostered_pct: "Rostered %", kickoff: "Kickoff",
    vegas: "Vegas", "experts.ecr_weekly": "Weekly ECR"
  };
  const SCORINGS = {standard: "Standard", half_ppr: "Half PPR", ppr: "PPR"};
  const words = value => String(value == null ? "unavailable" : value).replace(/_/g, " ");
  const number = value => typeof value === "number" && Number.isFinite(value);
  const reason = value => typeof value === "string" && !!value.trim();
  const playerKey = value => Number.isSafeInteger(value) && value >= 0;

  // Shape checks for display only. The caller validates/replays the artifact;
  // roster decisions, gain calculation and row order belong to its producer.
  function supportedSwaps(board) {
    const swaps = board.swaps;
    if (!swaps) return false;
    if (/^0\.1\./.test(board.schema_version)) {
      return swaps.available === false && reason(swaps.missing_reason) &&
        !Object.hasOwn(swaps, "rows");
    }
    const request = swaps.request, policy = request && request.gain_policy;
    if (typeof swaps.available !== "boolean" || !Array.isArray(swaps.rows) ||
        !Array.isArray(swaps.unresolved_wire_keys) || !swaps.unresolved_wire_keys.every(playerKey) ||
        !request || !request.setting ||
        !["scoring", "teams", "superflex"].every(key => request.setting[key] === board.setting[key]) ||
        !policy || !number(policy.minimum) || !["gt", "gte"].includes(policy.comparison)) return false;
    if (!swaps.available) return reason(swaps.missing_reason) && swaps.rows.length === 0;
    if (swaps.missing_reason !== null || !board.sources.values.enabled) return false;
    const priced = key => board.players.some(row => row.player_key === key && number(row.value.ddf_value));
    return swaps.rows.every(row => row && playerKey(row.add) && priced(row.add) &&
      (row.drop === null || (playerKey(row.drop) && priced(row.drop))) && number(row.gain));
  }

  function supported(board) {
    return !!(board && board.schema === "waiver-board" && /^0\.[12]\.\d+$/.test(board.schema_version) &&
      Number.isInteger(board.board_week) && Number.isInteger(board.season) &&
      board.setting && SCORINGS[board.setting.scoring] && Number.isInteger(board.setting.teams) &&
      [0, 1].includes(board.setting.superflex) && board.sources && Array.isArray(board.players) &&
      Array.isArray(board.unresolved) && board.sections && board.sections.available === false &&
      reason(board.sections.missing_reason) &&
      ["values", "values_prior", "points", "status", "bye"].every(key => board.sources[key]) &&
      board.players.every(row => row && row.value && row.this_week && row.value.missing_reason && row.this_week.missing_reason) &&
      supportedSwaps(board));
  }

  // Work on a copy. Weekly context is deliberately absent from this comparison.
  function orderedPlayers(players) {
    return players.slice().sort((a, b) => {
      const av = a.value.ddf_value, bv = b.value.ddf_value;
      if (number(av) !== number(bv)) return number(av) ? -1 : 1;
      if (number(av) && av !== bv) return bv - av;
      return a.player_key - b.player_key;
    });
  }

  function render(host, board, options) {
    if (!host || !host.ownerDocument) throw new TypeError("A host element is required");
    const doc = host.ownerDocument;
    const make = (tag, className, text) => {
      const el = doc.createElement(tag);
      if (className) el.className = className;
      if (text != null) el.textContent = String(text);
      return el;
    };
    const view = make("section", "ddf-waiver-board");
    view.setAttribute("aria-label", "Waiver board");
    host.replaceChildren(view);
    if (!supported(board)) {
      const error = make("p", "wb-error", "Waiver board unavailable: expected a supported waiver-board 0.1.x or 0.2.x artifact. Reload a supported built board.");
      error.setAttribute("role", "alert");
      view.append(error);
      return view;
    }

    const head = make("header", "wb-header");
    const title = make("div");
    title.append(make("h2", "", `Week ${board.board_week} waiver board`), make("p", "wb-meta", `${board.season} · Built ${board.built_at}`));
    const setting = `${SCORINGS[board.setting.scoring]} · ${board.setting.teams} teams · ${board.setting.superflex ? "Superflex" : "1QB"}`;
    const settings = make(options && typeof options.onSettings === "function" ? "button" : "p", "wb-settings", setting);
    if (settings.tagName === "BUTTON") {
      settings.type = "button";
      settings.setAttribute("aria-label", `Edit league settings: ${setting}`);
      settings.addEventListener("click", () => options.onSettings({...board.setting}));
    }
    head.append(title, settings);
    view.append(head);

    const sources = make("details", "wb-sources");
    sources.open = !!(doc.defaultView && doc.defaultView.matchMedia("(min-width: 651px)").matches);
    const entries = Object.entries(board.sources);
    const off = entries.filter(([, source]) => !source.enabled).length;
    const current = entries.filter(([, source]) => source.enabled && source.freshness === "current").length;
    sources.append(make("summary", "", `Sources · ${current} of ${entries.length} current · ${off} off`));
    const strip = make("div", "wb-source-strip");
    entries.forEach(([key, source]) => {
      const item = make("details", `wb-source${source.enabled ? "" : " wb-disabled"}`);
      item.dataset.source = key;
      item.dataset.enabled = String(!!source.enabled);
      item.dataset.label = source.label;
      const summary = make("summary");
      summary.append(make("strong", "", SOURCE_NAMES[key] || words(key)), make("span", "", `${words(source.freshness)} · ${words(source.label)} · ${words(source.availability)}`));
      item.append(summary);
      const provenance = [source.source, source.content_season, source.content_week == null ? null : `week ${source.content_week}`, source.content_vintage].filter(value => value != null).join(" · ");
      if (provenance) item.append(make("p", "", provenance));
      if (!source.enabled) item.append(make("p", "wb-disabled-reason", source.disabled_reason));
      strip.append(item);
    });
    sources.append(strip);
    view.append(sources);

    function unavailable(titleText, state, className) {
      const section = make("section", `wb-unavailable ${className}`);
      section.append(make("h3", "", titleText), make("p", "", state.missing_reason));
      return section;
    }
    view.append(unavailable("Sections", board.sections, "wb-sections"));

    const table = make("table", "wb-table");
    table.append(make("caption", "", "Players · DDF Value, highest first"));
    const thead = make("thead");
    const columns = make("tr");
    ["Player", "DDF Value", "Change", "This week"].forEach((label, index) => {
      const th = make("th", index === 3 ? "wb-week" : "", label);
      th.scope = index === 3 ? "colgroup" : "col";
      if (index === 3) th.colSpan = 3;
      columns.append(th);
    });
    thead.append(columns);
    table.append(thead);
    const tbody = make("tbody");

    // Disabled-source reasons take precedence, even if a bad caller left a value.
    function field(lane, key, sourceKey, label, format) {
      const cell = make("td", `wb-field${lane === "week" ? " wb-week" : ""}`);
      cell.dataset.field = key;
      cell.dataset.label = label;
      cell.append(make("span", "wb-field-label", label));
      const source = board.sources[sourceKey];
      const data = lane === "week" ? this.this_week : this.value;
      const value = data[key];
      const missing = !source.enabled || value == null || (typeof value === "number" && !number(value));
      if (missing) {
        cell.classList.add("wb-disabled");
        const details = make("details", "wb-missing");
        const summary = make("summary", "", "Unavailable");
        summary.setAttribute("aria-label", `${label} unavailable for ${this.name}; show reason`);
        details.append(summary, make("p", "", !source.enabled ? source.disabled_reason : data.missing_reason[key]));
        cell.append(details);
      } else {
        cell.append(make("span", "wb-field-value", format ? format(value) : value));
      }
      return cell;
    }

    orderedPlayers(board.players).forEach(player => {
      const row = make("tr", "wb-player");
      row.dataset.playerKey = player.player_key;
      const name = make("th", "wb-player-name");
      name.scope = "row";
      name.append(make("span", "", player.name), make("small", "", `${player.position} · ${player.team == null ? "Team unavailable" : player.team}`));
      row.append(name,
        field.call(player, "value", "ddf_value", "values", "DDF Value"),
        field.call(player, "value", "change", "values_prior", "Change", value => value > 0 ? `+${value}` : String(value)));
      const points = field.call(player, "week", "points", "points", "Points");
      points.prepend(make("span", "wb-week-label", "This week"));
      const pointsSource = make("small", "wb-points-source", board.sources.points.source || "Source unavailable");
      pointsSource.title = board.points_leg;
      points.append(pointsSource);
      const status = field.call(player, "week", "status", "status", "Status");
      // Injury and practice are separate optional fields; missing never means healthy.
      const statusNotes = make("details", "wb-status-notes");
      statusNotes.append(make("summary", "", "Injury / practice"));
      ["injury_status", "practice_participation"].forEach(key => {
        const source = board.sources.status;
        const value = player.this_week[key];
        const text = !source.enabled ? source.disabled_reason : value == null ? player.this_week.missing_reason[key] : value;
        statusNotes.append(make("p", "", `${words(key)}: ${text}`));
      });
      status.append(statusNotes);
      row.append(points, status,
        field.call(player, "week", "bye_week", "bye", "Bye", value => player.this_week.on_bye === true ? `This week (${value})` : `Week ${value}`));
      tbody.append(row);
    });
    table.append(tbody);
    view.append(table);
    if (!board.players.length) view.append(make("p", "wb-empty", "No players in this board."));
    const swaps = board.swaps;
    const swapPanel = swaps.available ? make("section", "wb-swap-panel wb-swaps") : unavailable("Your swaps", swaps, "wb-swaps");
    if (swaps.available) {
      swapPanel.append(make("h3", "", "Your swaps"));
      const policy = swaps.request.gain_policy;
      swapPanel.append(make("p", "wb-swap-policy", `DDF Value gain ${policy.comparison === "gt" ? ">" : "≥"} ${policy.minimum}`));
      const list = make("ol", "wb-swap-list");
      swaps.rows.forEach(swap => {
        const item = make("li", "wb-swap");
        item.dataset.add = swap.add;
        item.dataset.drop = swap.drop == null ? "" : swap.drop;
        const fields = make("dl");
        [["Add", swap.add, "add"], ["Drop", swap.drop, "drop"]].forEach(([label, key, field]) => {
          const group = make("div", `wb-swap-${field}`);
          const value = make("dd");
          const player = key === null ? null : board.players.find(row => row.player_key === key);
          if (player) {
            value.append(make("span", "", player.name), make("small", "", `${player.position} · ${player.team == null ? "Team unavailable" : player.team}`));
          } else value.textContent = "Open roster slot";
          group.append(make("dt", "", label), value);
          fields.append(group);
        });
        const gain = make("div", "wb-swap-gain");
        gain.append(make("dt", "", "DDF Value gain"), make("dd", "", swap.gain > 0 ? `+${swap.gain}` : String(swap.gain)));
        fields.append(gain);
        item.append(fields);
        list.append(item);
      });
      swapPanel.append(swaps.rows.length ? list : make("p", "wb-swaps-empty", "No swaps in this board."));
    }
    if (swaps.unresolved_wire_keys && swaps.unresolved_wire_keys.length) {
      const unresolved = make("details", "wb-unresolved-wire");
      unresolved.append(make("summary", "", `Unresolved wire players (${swaps.unresolved_wire_keys.length})`));
      const list = make("ul");
      swaps.unresolved_wire_keys.forEach(key => list.append(make("li", "", `Player key ${key}`)));
      unresolved.append(list);
      swapPanel.append(unresolved);
    }
    view.append(swapPanel);
    if (board.unresolved.length) {
      const unresolved = make("details", "wb-unresolved");
      unresolved.append(make("summary", "", `Unresolved players (${board.unresolved.length})`));
      const list = make("ul");
      board.unresolved.forEach(row => list.append(make("li", "", `${row.name}: ${row.unresolved_reason}`)));
      unresolved.append(list);
      view.append(unresolved);
    }
    return view;
  }

  const api = {render, orderedPlayers};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.TradeValueWaiverBoardView = api;
})(typeof window !== "undefined" ? window : globalThis);
