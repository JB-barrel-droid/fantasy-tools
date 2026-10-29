// Roster provenance transitions (JEG-1241, under JEG-1188). Pure and dependency-free so node can unit-test it
// (tests/node/roster_provenance_transitions.cjs) and the browser can load it. Nothing here touches the DOM or storage.
//
// A team's provenance says what a source showed about its roster, kept beside its entries (current occupancy):
//   {unresolved: int >= 0 | null,   pasted valued players not matched or not added yet; null = unknown (older saves)
//    observedAt: ms | null,         when a source roster was read (a replacing paste); never a local edit
//    editedAt:   ms | null,         the last local change of any kind
//    coverage:   COVERAGE value,    what that source showed it covered, from evidence the parser already reports
//    settled:    [key]}             unresolved items reconciled since the last observation (each counts once)
//
// Every transition returns a frozen record and never mutates its input; a no-op returns the input record itself.
// This module decides no freshness window, completeness threshold, reserve rule or value: staleness, team count,
// starter minimum and duplicate owners stay with the existing ValueModel.leagueCompleteness, and inferenceBlockers()
// only adds provenance reasons on top of the reasons that check returns.
//
//   DDFRosterProvenance.normalize(raw) -> provenance
//   DDFRosterProvenance.coverageFrom({benchIncluded?, wholeRoster?}) -> COVERAGE value
//   DDFRosterProvenance.replaceFromSource(p, {now, unresolved?, coverage?}) -> provenance
//   DDFRosterProvenance.appendFromSource(p, {now, added, missed, rejected}) -> provenance
//   DDFRosterProvenance.reconcile(p, {now, key, accepted}) -> provenance
//   DDFRosterProvenance.localEdit(p, {now}) -> provenance
//   DDFRosterProvenance.clear(p, {now}) -> provenance
//   DDFRosterProvenance.freshnessTime(p) -> ms | null
//   DDFRosterProvenance.inferenceBlockers({teams: [{id, provenance}], existingReasons?}) -> [reason]
(function (root) {
  "use strict";

  // Labels describe what the source showed, never what a platform can do. bench_omitted / bench_shown come from the
  // parser's own benchIncluded flag (matchup pages). whole_roster needs the caller to attest that the source listed
  // every roster seat, empty and reserve ones included; no parser path attests that today (JEG-1131: no platform fetch).
  var COVERAGE = {UNKNOWN: "unknown", BENCH_OMITTED: "bench_omitted", BENCH_SHOWN: "bench_shown", WHOLE_ROSTER: "whole_roster"};
  var COVERAGE_VALUES = [COVERAGE.UNKNOWN, COVERAGE.BENCH_OMITTED, COVERAGE.BENCH_SHOWN, COVERAGE.WHOLE_ROSTER];
  var REASONS = ["unresolved_unknown", "unresolved", "not_source_observed", "coverage_unproven"];

  function count(n) { return typeof n === "number" && Number.isInteger(n) && n >= 0 ? n : null; }
  function time(t) { return typeof t === "number" && isFinite(t) && t > 0 ? t : null; }
  function nonNegative(n) { return typeof n === "number" && Number.isInteger(n) && n > 0 ? n : 0; }
  function coverageOf(c) { return COVERAGE_VALUES.indexOf(c) !== -1 ? c : COVERAGE.UNKNOWN; }

  function make(unresolved, observedAt, editedAt, coverage, settled) {
    return Object.freeze({unresolved: unresolved, observedAt: observedAt, editedAt: editedAt, coverage: coverage,
      settled: Object.freeze(settled.slice())});
  }

  // Stored fields to a provenance record. A rosterAt saved by a JEG-1188 build was refreshed on every local edit,
  // so it can only stand for editedAt, never for a source observation.
  function normalize(raw) {
    var r = raw && typeof raw === "object" ? raw : {};
    var settled = Array.isArray(r.settled) ? r.settled.map(String).filter(function (k, i, a) { return k && a.indexOf(k) === i; }) : [];
    return make(count(r.unresolved), time(r.observedAt), time(r.editedAt) || time(r.rosterAt), coverageOf(r.coverage), settled);
  }

  function coverageFrom(evidence) {
    var e = evidence && typeof evidence === "object" ? evidence : {};
    if (e.benchIncluded === false) return COVERAGE.BENCH_OMITTED;
    if (e.wholeRoster === true) return COVERAGE.WHOLE_ROSTER;
    if (e.benchIncluded === true) return COVERAGE.BENCH_SHOWN;
    return COVERAGE.UNKNOWN;
  }

  // A paste that replaces the team's roster: a new source observation. An unmatched count the caller doesn't know
  // stays unknown rather than becoming zero.
  function replaceFromSource(p, args) {
    var a = args || {};
    var now = time(a.now);
    return make(count(a.unresolved), now, now, coverageOf(a.coverage), []);
  }

  // A paste added onto the roster. It shows only part of the roster, so it is not an observation: observedAt and
  // coverage stay. An unknown count stays unknown; a paste that adds nothing and leaves nothing out changes nothing.
  function appendFromSource(p, args) {
    var cur = normalize(p);
    var a = args || {};
    var added = nonNegative(a.added), left = nonNegative(a.missed) + nonNegative(a.rejected);
    if (!added && !left) return p;
    var unresolved = cur.unresolved === null ? null : cur.unresolved + left;
    return make(unresolved, cur.observedAt, time(a.now) || cur.editedAt, cur.coverage, cur.settled);
  }

  // The person settles one item the paste left out ("Yes, add", or a search add of that pasted line). Only a
  // successful placement counts, and each key counts once.
  function reconcile(p, args) {
    var cur = normalize(p);
    var a = args || {};
    var key = a.key === undefined || a.key === null ? "" : String(a.key);
    if (a.accepted !== true || !key || cur.settled.indexOf(key) !== -1) return p;
    var unresolved = cur.unresolved === null ? null : Math.max(0, cur.unresolved - 1);
    return make(unresolved, cur.observedAt, time(a.now) || cur.editedAt, cur.coverage, cur.settled.concat([key]));
  }

  // Any other local change (remove, move, a search add that settles nothing): edit time only.
  function localEdit(p, args) {
    var cur = normalize(p);
    var now = time((args || {}).now);
    if (now === null || now === cur.editedAt) return p;
    return make(cur.unresolved, cur.observedAt, now, cur.coverage, cur.settled);
  }

  // The team is emptied: nothing pending, and no source observation describes it any more.
  function clear(p, args) {
    var cur = normalize(p);
    return make(0, null, time((args || {}).now) || cur.editedAt, COVERAGE.UNKNOWN, []);
  }

  function freshnessTime(p) { return normalize(p).observedAt; }

  // Reasons the omitted players may not be read as free agents: the existing check's reasons, then provenance's.
  function inferenceBlockers(input) {
    var i = input || {};
    var found = {};
    var teams = i.teams || [];
    if (!teams.length) found.not_source_observed = true;   // no team, so nothing was observed
    teams.forEach(function (t) {
      var cur = normalize(t && t.provenance);
      if (cur.unresolved === null) found.unresolved_unknown = true;
      else if (cur.unresolved > 0) found.unresolved = true;
      if (cur.observedAt === null) found.not_source_observed = true;
      if (cur.coverage !== COVERAGE.WHOLE_ROSTER) found.coverage_unproven = true;
    });
    var out = [];
    (i.existingReasons || []).forEach(function (r) { if (out.indexOf(String(r)) === -1) out.push(String(r)); });
    REASONS.forEach(function (r) { if (found[r] && out.indexOf(r) === -1) out.push(r); });
    return out;
  }

  var api = {COVERAGE: Object.freeze(COVERAGE), REASONS: Object.freeze(REASONS.slice()), normalize: normalize,
    coverageFrom: coverageFrom, replaceFromSource: replaceFromSource, appendFromSource: appendFromSource,
    reconcile: reconcile, localEdit: localEdit, clear: clear, freshnessTime: freshnessTime, inferenceBlockers: inferenceBlockers};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.DDFRosterProvenance = api;
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
