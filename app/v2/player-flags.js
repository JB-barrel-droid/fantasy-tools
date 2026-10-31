// Trade Value v2: bye week on player rows in Compare a trade, Find a trade and Trade targets (JEG-892, path A: byes only).
//
// Pure rules plus one DOM helper; node can require this file (tests/test_player_flags.py).
//   teamCode(team)               -> the bye table's code ("JAC" -> "JAX", "LAR" -> "LA", "WSH" -> "WAS", "LVR" -> "LV")
//   byeOf(team, byes, week)      -> {team, week, state: "done" | "now" | "ahead"} or null
//   byeText(bye)                 -> "Bye 11" | "Bye 6 (done)" | "Bye this week (9)" | ""
//   sourceText(season)           -> the provenance line shown on hover
//   node(row)                    -> a " · Bye 11" span for a row's sub-line, or null (browser only)
//
// Byes are published data: window.TradeValueByes (nfl-byes.js, built from data/inputs/nfl_byes_2026.json, the season's
// NFL schedule, the same table the pipelines use). A free agent (no team), or a team the table does not have, gets no
// bye, never a guess. "done" and "this week" need the calendar week (source freshness current_content_week); without
// it a row shows the bye week alone, so the page never claims a week it cannot back.
(function (root) {
  "use strict";

  const ALIASES = {JAC: "JAX", LAR: "LA", WSH: "WAS", LVR: "LV"};
  const teamCode = team => {
    const code = String(team == null ? "" : team).trim().toUpperCase();
    return ALIASES[code] || code;
  };

  function byeOf(team, byes, week) {
    const code = teamCode(team);
    if (!code || !byes || !Number.isInteger(byes[code])) return null;
    const bye = byes[code];
    const state = !Number.isInteger(week) ? "ahead" : bye < week ? "done" : bye === week ? "now" : "ahead";
    return {team: code, week: bye, state};
  }

  function byeText(bye) {
    if (!bye) return "";
    if (bye.state === "done") return `Bye ${bye.week} (done)`;
    if (bye.state === "now") return `Bye this week (${bye.week})`;
    return `Bye ${bye.week}`;
  }

  const sourceText = season => `Bye week: ${Number.isInteger(season) ? `${season} ` : ""}NFL schedule (published, fixed for the season).`;

  // The calendar week, or null when source freshness has not loaded (it throws before init).
  function currentWeek() {
    try {
      const f = root.TradeValueProductData && root.TradeValueProductData.getSourceFreshness ? root.TradeValueProductData.getSourceFreshness() : null;
      const week = f ? Number(f.current_content_week) : NaN;
      return Number.isInteger(week) ? week : null;
    } catch (e) {
      return null;
    }
  }

  function node(row) {
    if (!row || !root.document) return null;
    const table = root.TradeValueByes;
    const bye = byeOf(row.team, table && table.byes, currentWeek());
    if (!bye) return null;
    const span = root.document.createElement("span");
    span.className = "v2-bye";
    span.dataset.bye = String(bye.week);
    span.dataset.byeState = bye.state;
    span.title = sourceText(table.season);
    span.textContent = ` · ${byeText(bye)}`;
    return span;
  }

  const api = {ALIASES, teamCode, byeOf, byeText, sourceText, currentWeek, node};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.DDFPlayerFlags = api;
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
