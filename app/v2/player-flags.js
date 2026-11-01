// Trade Value v2: bye week and injury status on player rows in Compare a trade, Find a trade and Trade targets
// (JEG-892, path B: byes plus a dated Sleeper status chip).
//
// Pure rules plus one DOM helper; node can require this file (tests/test_player_flags.py).
//   teamCode(team)               -> the bye table's code ("JAC" -> "JAX", "LAR" -> "LA", "WSH" -> "WAS", "LVR" -> "LV")
//   byeOf(team, byes, week)      -> {team, week, state: "done" | "now" | "ahead"} or null
//   byeText(bye)                 -> "Bye 11" | "Bye 6 (done)" | "Bye this week (9)" | ""
//   sourceText(season)           -> the provenance line shown on hover
//   statusChip(row, freshness)   -> {status, short, title} or null
//   node(row)                    -> a " · Bye 11 Q" span for a row's sub-line, or null (browser only)
//
// Byes are published data: window.TradeValueByes (nfl-byes.js, built from data/inputs/nfl_byes_2026.json, the season's
// NFL schedule, the same table the pipelines use). A free agent (no team), or a team the table does not have, gets no
// bye, never a guess. "done" and "this week" need the calendar week (source freshness current_content_week); without
// it a row shows the bye week alone, so the page never claims a week it cannot back.
//
// Injury status is Sleeper's, as of the identity base the bake read (window.TradeValueStatus, player-status.js), under
// the Waivers tab's own rule (TradeValueWaivers.statusFreshness / statusOf, JEG-1312): shown only when the copy is
// dated and at most 6 days old. A stale or undated copy shows no chip on any row and says why on the bye's hover. A
// chip only for a player on an NFL team; no chip means no status in the source, never "healthy".
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

  const SHORT = {Questionable: "Q", Doubtful: "D", Out: "Out", IR: "IR", PUP: "PUP", Sus: "Susp"};
  // freshness: TradeValueWaivers.statusFreshness(...). The rule that hides a stale copy is the Waivers tab's, not a copy.
  function statusChip(row, freshness) {
    const W = root.TradeValueWaivers;
    if (!row || !teamCode(row.team) || !W || !W.statusOf) return null;
    const status = W.statusOf(row, freshness);
    return status ? {status, short: SHORT[status] || status, title: `${status}: ${freshness.label}`} : null;
  }
  function freshnessNow() {
    const W = root.TradeValueWaivers;
    return W && W.statusFreshness ? W.statusFreshness(root.TradeValueStatus || null, Date.now()) : null;
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
    const doc = root.document;
    const table = root.TradeValueByes;
    const bye = byeOf(row.team, table && table.byes, currentWeek());
    const freshness = freshnessNow();
    const chip = statusChip(row, freshness);
    if (!bye && !chip) return null;
    const span = doc.createElement("span");
    span.className = "v2-bye";
    const notes = [];
    if (bye) {
      span.dataset.bye = String(bye.week);
      span.dataset.byeState = bye.state;
      span.textContent = ` · ${byeText(bye)}`;
      notes.push(sourceText(table.season));
    }
    if (freshness && !freshness.shown && teamCode(row.team)) notes.push(freshness.text);
    if (chip) {
      const tag = doc.createElement("span");
      tag.className = "v2-inj-chip";
      tag.dataset.status = chip.status;
      tag.title = chip.title;
      tag.setAttribute("aria-label", chip.title);
      tag.textContent = chip.short;
      span.appendChild(tag);
    }
    span.title = notes.join(" ");
    return span;
  }

  const api = {ALIASES, SHORT, teamCode, byeOf, byeText, statusChip, sourceText, currentWeek, node};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.DDFPlayerFlags = api;
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
