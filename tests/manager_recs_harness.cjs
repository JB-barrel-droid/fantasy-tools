// Unit checks for manager-aware recommendations (JEG-1217 stage 3). Pure Node, no browser.
//   node manager_recs_harness.cjs <dir with manager-recs.js, manager-profiles.js, workspace.js and opportunities.js>
// Prints {ran, failures}. tests/test_jeg1217_manager_recs.py runs it on the real modules and on broken copies.
"use strict";
const path = require("path");
const assert = require("assert");

const dir = path.resolve(process.argv[2]);
const R = require(path.join(dir, "manager-recs.js"));
const M = require(path.join(dir, "manager-profiles.js"));
const W = require(path.join(dir, "workspace.js"));
const O = require(path.join(dir, "opportunities.js"));
// "Our fit" labels exactly as Trade opportunities makes them (opportunities.js ourFitOf), so a renamed label fails here.
const OURS = {
  works: O.ourFitOf({natural: {us: {ok: true}}}).label,
  rosterIssue: O.ourFitOf({natural: {us: {ok: false, value: true, construction: false}}}).label,
  fails: O.ourFitOf({natural: {us: {ok: false, value: false}}, us: {down: true}}).label
};

const ran = [];
const failures = [];
function check(name, fn) {
  ran.push(name);
  try { fn(); } catch (error) { failures.push({name, message: String(error && error.message || error).slice(0, 400)}); }
}
const close = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, `${msg || ""} ${a} != ${b}`);

// A player row: values in the current view plus the positional preseason rank (the canonical players carry it).
const P = (key, pos, ddf, rank) => ({player_key: key, name: `P${key}`, pos, values: {ddf_value: ddf}, preseason_ecr_rank: rank === undefined ? null : rank});
// Today's RB values, best first: rank 1 = 40, rank 2 = 30, rank 3 = 20, rank 4 = 10.
const ALL = [P(1, "RB", 40), P(2, "RB", 30), P(3, "RB", 20), P(4, "RB", 10), P(5, "WR", 25), P(6, "WR", 15)];
// An opportunities row: give = what you give (they receive), receive = what you get (they send). chartEdge = their market gain.
function opp(id, opponentId, give, receive, edge, chartEdge, extra) {
  return {id, opponentId, opponent: opponentId, give, receive, edge, chartEdge, ours: {label: OURS.works}, overall: "natural", ...(extra || {})};
}
function league() {
  let ws = W.newWorkspace({id: "lg"});
  ["Mine", "A", "B", "C"].forEach((n, i) => { ws = W.ops.addTeam(ws, n, {id: `t${i}`}); });
  return W.ops.setMyTeam(ws, "t0");
}
const run = (rows, book) => R.build({rows, book: book || M.emptyBook(), ws: league(), allRows: ALL, profiles: M});

check("test_draft_curve_positional", () => {
  const curve = R.draftCurve(ALL);
  assert.deepStrictEqual(curve.RB, [40, 30, 20, 10]);
  assert.strictEqual(R.draftValue(P(9, "RB", 5, 2), curve), 30, "rank 2 RB is priced as today's RB2");
  assert.strictEqual(R.draftValue(P(9, "RB", 5, null), curve), null, "no preseason rank is unavailable, not zero");
  assert.strictEqual(R.draftValue(P(9, "RB", 5, 9), curve), null, "a rank past the list is unavailable");
  assert.strictEqual(R.draftValue(P(9, "TE", 5, 1), curve), null);
});

check("test_unmarked_manager_uses_market", () => {
  const out = run([opp("x", "t1", [P(11, "RB", 20, 1)], [P(12, "RB", 18, 3)], 2, 3)]);
  assert.strictEqual(out.recommendations.length, 1);
  const rec = out.recommendations[0];
  assert.strictEqual(rec.theirGain, 3);
  assert.strictEqual(rec.fallback, "nothing marked");
  assert.deepStrictEqual(rec.basis.map(b => b.anchor), ["market"]);
});

check("test_blend_strong_counts_double", () => {
  // Market says they lose 2; draft says they gain 6 (they get an RB1 = 40, send an RB3 = 20 ... see below).
  let book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "draft", "strong", 1);
  book = M.ops.setAnchor(book, league(), "t1", "market", "some", 1);
  // give RB rank 2 (30) + nothing, receive RB rank 3 (20) and RB rank 4 (10)? keep it simple: draft gain = 30 - 24? use direct values:
  const gains = {market: -2, draft: 6, rankings: null};
  const a = R.appeal(M.get(book, league(), "t1"), gains);
  close(a.gain, (2 * 6 + 1 * -2) / 3, "the worked example: +3.3");
  assert.strictEqual(a.fallback, null);
});

check("test_doesnt_care_and_unknown_do_not_count", () => {
  let book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "draft", "strong", 1);
  book = M.ops.setAnchor(book, league(), "t1", "market", "none", 1);
  const a = R.appeal(M.get(book, league(), "t1"), {market: -50, draft: 4, rankings: null});
  assert.strictEqual(a.gain, 4);
  assert.deepStrictEqual(a.basis.map(b => b.anchor), ["draft"]);
});

check("test_names_and_other_change_words_only", () => {
  const ws = league();
  let book = M.ops.setAnchor(M.emptyBook(), ws, "t1", "names", "strong", 1);
  book = M.ops.setTag(book, ws, "t1", "rookies", true, 1);
  book = M.ops.setTag(book, ws, "t1", "rarelyTrades", true, 1);
  const row = opp("x", "t1", [P(11, "RB", 20)], [P(12, "RB", 18)], 2, 3);
  const plain = run([row]).recommendations[0];
  const marked = run([row], book).recommendations[0];
  assert.strictEqual(marked.theirGain, plain.theirGain, "no number for big names or other leanings");
  assert.strictEqual(marked.fallback, "nothing marked");
  assert.ok(marked.why.some(l => l.includes("big names")));
  assert.ok(marked.why.some(l => l.includes("they like rookies and rarely trade")), "ticked boxes named in the words");
  assert.strictEqual(marked.band, plain.band, "ticked boxes never move the likelihood");
});

check("test_rankings_unavailable_falls_back", () => {
  const book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "rankings", "strong", 1);
  const rec = run([opp("x", "t1", [P(11, "RB", 20)], [P(12, "RB", 18)], 2, 3)], book).recommendations[0];
  assert.strictEqual(rec.fallback, "no data for what you marked");
  assert.strictEqual(rec.theirGain, 3);
});

check("test_missing_draft_rank_falls_back", () => {
  const book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "draft", "strong", 1);
  const rows = [opp("x", "t1", [P(11, "RB", 20, null)], [P(12, "RB", 18, 3)], 2, 3)];
  const rec = run(rows, book).recommendations[0];
  assert.strictEqual(rec.gains.draft, null);
  assert.strictEqual(rec.fallback, "no data for what you marked");
  // With draft and market both marked, the missing draft drops out and is named.
  const both = M.ops.setAnchor(book, league(), "t1", "market", "some", 1);
  const r2 = run(rows, both).recommendations[0];
  assert.deepStrictEqual(r2.basis.map(b => b.anchor), ["market"]);
  assert.ok(r2.why.some(l => l.includes("No data yet for preseason draft rankings")));
});

check("test_draft_gain_from_ranks", () => {
  const book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "draft", "strong", 1);
  // They receive a preseason RB1 (priced 40) and send a preseason RB3 (priced 20): +20 by draft.
  const rec = run([opp("x", "t1", [P(11, "RB", 15, 1)], [P(12, "RB", 25, 3)], 10, -8)], book).recommendations[0];
  assert.strictEqual(rec.gains.draft, 20);
  assert.strictEqual(rec.theirGain, 20);
  assert.strictEqual(rec.band, "likely");
});

// Engine rows (curve-widget.js) carry no preseason rank; the card passes the canonical players' ranks in by player_key.
check("test_draft_ranks_from_canonical_players", () => {
  const book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "draft", "strong", 1);
  const engine = (key, pos, ddf) => ({player_key: key, name: `P${key}`, pos, values: {ddf_value: ddf}});
  const rows = () => [opp("x", "t1", [engine(11, "RB", 15)], [engine(12, "RB", 25)], 10, -8)];
  const bare = run(rows(), book).recommendations;
  assert.strictEqual(bare.length, 0, "without ranks the draft view has no data and the market view says long shot or worse");
  const ranks = new Map([[11, 1], [12, 3]]);
  const out = R.build({rows: rows(), book, ws: league(), allRows: ALL, profiles: M, ranks});
  const rec = out.recommendations[0];
  assert.ok(rec, "with the canonical ranks the draft view is used");
  assert.strictEqual(rec.gains.draft, 20);
  assert.deepStrictEqual(rec.basis.map(b => b.anchor), ["draft"]);
  assert.strictEqual(rec.fallback, null);
  // A rank on the row itself still wins over the map.
  assert.strictEqual(R.draftValue(P(9, "RB", 5, 2), R.draftCurve(ALL), new Map([[9, 4]])), 30);
});

check("test_band_boundaries", () => {
  // Share of what they send (DDF Value). Exactly +10% is Likely, exactly -10% Possible, exactly -25% Long shot.
  assert.strictEqual(R.band(4, 40).band, "likely");
  assert.strictEqual(R.band(3.999, 40).band, "possible");
  assert.strictEqual(R.band(0, 40).band, "possible");
  assert.strictEqual(R.band(-4, 40).band, "possible");
  assert.strictEqual(R.band(-4.001, 40).band, "longShot");
  assert.strictEqual(R.band(-10, 40).band, "longShot");
  assert.strictEqual(R.band(-10.001, 40).band, "hidden");
  assert.strictEqual(R.band(0.1 * 3, 3).band, "likely", "float rounding at the boundary");
  assert.strictEqual(R.band(5, 0).band, null, "nothing sent: no judgment");
  assert.strictEqual(R.band(null, 40).band, null);
});

check("test_rank_by_our_gain_not_appeal", () => {
  const rows = [
    opp("a", "t1", [P(11, "RB", 20)], [P(12, "RB", 28)], 8, 1),    // you +8, they +1 of 28 (3.6%): Possible
    opp("b", "t2", [P(13, "RB", 20)], [P(14, "RB", 24)], 4, 4),    // you +4, they +4 of 24 (16.7%): Likely
    opp("c", "t3", [P(15, "RB", 20)], [P(16, "RB", 26)], 6, 3)     // you +6, they +3 of 26 (11.5%): Likely
  ];
  const out = run(rows);
  assert.deepStrictEqual(out.recommendations.map(r => r.id), ["a", "c", "b"]);
  assert.deepStrictEqual(out.recommendations.map(r => r.likelihood), ["Possible", "Likely", "Likely"]);
});

check("test_stretch_section", () => {
  const rows = [
    opp("main", "t1", [P(11, "RB", 20)], [P(12, "RB", 22)], 2, 0),
    opp("long", "t2", [P(13, "RB", 20)], [P(14, "RB", 40)], 20, -6),     // -15% of 40: Long shot
    opp("gone", "t3", [P(15, "RB", 20)], [P(16, "RB", 40)], 20, -12)     // -30%: not shown
  ];
  const out = run(rows);
  assert.deepStrictEqual(out.recommendations.map(r => r.id), ["main"]);
  assert.deepStrictEqual(out.stretch.map(r => r.id), ["long"]);
  assert.strictEqual(out.counts.hidden, 1);
  assert.ok(out.stretch[0].why.some(l => l.includes("needs them")), out.stretch[0].why.join(" | "));
});

check("test_excluded_and_my_team_left_out", () => {
  const ws = league();
  const book = M.ops.setExcluded(M.emptyBook(), ws, "t2", true, 1);
  const rows = [opp("a", "t1", [P(11, "RB", 20)], [P(12, "RB", 22)], 2, 1), opp("b", "t2", [P(13, "RB", 20)], [P(14, "RB", 22)], 2, 1),
    opp("c", "t0", [P(15, "RB", 20)], [P(16, "RB", 22)], 2, 1)];
  const out = run(rows, book);
  assert.deepStrictEqual(out.recommendations.map(r => r.id), ["a"]);
  assert.strictEqual(out.counts.excluded, 2);
});

check("test_only_your_wins", () => {
  const rows = [
    opp("tiny", "t1", [P(11, "RB", 20)], [P(12, "RB", 20.04)], 0.04, 0),          // shows as 0.0: not a win
    opp("fails", "t1", [P(13, "RB", 20)], [P(14, "RB", 25)], 5, 0, {ours: {label: OURS.fails}, overall: "force"}),
    opp("ok", "t1", [P(15, "RB", 20)], [P(16, "RB", 20.05)], 0.05, 0),
    // Force only because of their side: still yours to offer.
    opp("theirForce", "t1", [P(17, "RB", 20)], [P(18, "RB", 21)], 1, 0, {overall: "force"}),
    opp("rosterIssue", "t1", [P(19, "RB", 20)], [P(20, "RB", 21)], 1, 0, {ours: {label: OURS.rosterIssue}, overall: "force"})
  ];
  const out = run(rows);
  assert.deepStrictEqual(out.recommendations.map(r => r.id).sort(), ["ok", "rosterIssue", "theirForce"]);
  assert.strictEqual(out.counts.notWin, 2);
});

check("test_no_appeal_number_is_counted_not_shown", () => {
  const out = run([opp("x", "t1", [P(11, "RB", 20)], [P(12, "RB", 22)], 2, null)]);
  assert.strictEqual(out.recommendations.length + out.stretch.length, 0);
  assert.strictEqual(out.counts.noAppeal, 1);
});

check("test_values_untouched", () => {
  const row = opp("x", "t1", [P(11, "RB", 20, 1)], [P(12, "RB", 22, 2)], 2, 1);
  const before = JSON.stringify(row);
  const allBefore = JSON.stringify(ALL);
  run([row], M.ops.setAnchor(M.emptyBook(), league(), "t1", "draft", "strong", 1));
  assert.strictEqual(JSON.stringify(row), before);
  assert.strictEqual(JSON.stringify(ALL), allBefore);
});

check("test_sources_labelled", () => {
  const book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "draft", "strong", 1);
  const rec = run([opp("x", "t1", [P(11, "RB", 15, 1)], [P(12, "RB", 25, 3)], 10, -8)], book).recommendations[0];
  assert.deepStrictEqual(rec.sources.map(s => s.anchor), ["draft"]);
  assert.ok(rec.sources[0].status.includes("preseason"));
  assert.ok(R.SOURCES.rankings.status.startsWith("unavailable"));
});

// Roster checks from Trade opportunities travel with each idea, for both teams; they are shown, never a filter (9e681c74).
const theirsOk = {label: "neutral", construction: {ok: true, issues: []}};
check("test_health_warnings_both_sides", () => {
  const give = () => [P(11, "RB", 20)];
  const recv = () => [P(12, "RB", 22)];
  const rows = [
    opp("clean", "t1", give(), recv(), 2, 1, {theirs: theirsOk}),
    opp("unjudged", "t1", give(), recv(), 2, 1, {ours: null, theirs: null, overall: null}),
    opp("theirBad", "t2", give(), recv(), 2, 1, {theirs: {label: "neutral", construction: {ok: false, issues: ["empty starting slot: RB"]}}, overall: "force"}),
    opp("ourBad", "t2", give(), recv(), 2, 1, {ours: {label: OURS.rosterIssue}, theirs: theirsOk, overall: "force"}),
    opp("theirPartial", "t3", give(), recv(), 2, 1, {theirs: theirsOk, partial: true}),
    opp("theirNotJudged", "t3", give(), recv(), 2, 1, {theirs: {label: "neutral", construction: null}})
  ];
  const out = run(rows);
  const by = Object.fromEntries(out.recommendations.map(r => [r.id, r.health]));
  assert.deepStrictEqual(Object.keys(by).sort(), rows.map(r => r.id).sort(), "no health filter: every row is still an idea");
  assert.deepStrictEqual(by.clean, {ours: [], theirs: []});
  assert.deepStrictEqual(by.unjudged, {ours: ["roster fit not judged"], theirs: ["roster fit not judged"]});
  assert.deepStrictEqual(by.theirBad, {ours: [], theirs: ["roster construction: empty starting slot: RB"]});
  assert.deepStrictEqual(by.ourBad, {ours: ["roster construction issue"], theirs: []});
  assert.deepStrictEqual(by.theirPartial, {ours: [], theirs: ["partial roster"]});
  assert.deepStrictEqual(by.theirNotJudged, {ours: [], theirs: ["roster construction not judged"]});
  // With the full fit, our own construction result is read directly.
  const fullFit = row => ({myConstruction: row.id === "theirBad" ? {ok: true, issues: []} : {ok: false, issues: ["bench promoted to starter: P11"]}});
  const withFit = R.build({rows, book: M.emptyBook(), ws: league(), allRows: ALL, profiles: M, fullFit});
  const h = Object.fromEntries(withFit.recommendations.map(r => [r.id, r.health]));
  assert.deepStrictEqual(h.theirBad.ours, [], "our construction passed");
  assert.deepStrictEqual(h.ourBad.ours, ["roster construction: bench promoted to starter: P11"]);
  assert.deepStrictEqual(h.clean.ours, [], "full fit is only read for a construction failure");
  // Shown next to the likelihood, naming the side.
  const v = R.view(out.recommendations.find(r => r.id === "theirBad"));
  assert.ok(v.health.startsWith("Roster check:"), v.health);
  assert.ok(v.health.includes("B's side: roster construction: empty starting slot: RB."), v.health);
  assert.ok(!v.health.includes("Your side"), v.health);
  assert.ok(R.view(out.recommendations.find(r => r.id === "ourBad")).health.includes("Your side: roster construction issue."));
  assert.strictEqual(R.view(out.recommendations.find(r => r.id === "clean")).health, "");
  // A stretch offer carries its warnings too.
  const long = run([opp("long", "t1", give(), [P(14, "RB", 40)], 20, -6, {ours: null, overall: null})]);
  assert.deepStrictEqual(long.stretch[0].health.ours, ["roster fit not judged"]);
});

check("test_view_shows_every_displayed_field", () => {
  const ws = league();
  const row = opp("x", "t1", [P(11, "RB", 20)], [P(12, "RB", 22)], 2, 1, {theirs: theirsOk});
  const build = (w, r) => R.build({rows: [r], book: M.emptyBook(), ws: w, allRows: ALL, profiles: M}).recommendations[0];
  const base = R.view(build(ws, row));
  assert.strictEqual(base.opponent, "A");
  assert.strictEqual(base.gain, "You gain +2.0");
  assert.strictEqual(base.give, "You give P11.");
  assert.strictEqual(base.receive, "You get P12.");
  assert.ok(base.sources.includes("Trade chart average"));
  // Rename: same ids, bands and why; the view changes.
  const renamed = R.view(build(W.ops.renameTeam(ws, "t1", "Renamed"), row));
  assert.strictEqual(renamed.opponent, "Renamed");
  assert.deepStrictEqual([renamed.id, renamed.band, renamed.why], [base.id, base.band, base.why]);
  assert.notStrictEqual(JSON.stringify(renamed), JSON.stringify(base));
  // Value-only: same order, id and band; our gain moves.
  const bumped = R.view(build(ws, {...row, edge: 2.3}));
  assert.deepStrictEqual([bumped.id, bumped.band], [base.id, base.band]);
  assert.strictEqual(bumped.gain, "You gain +2.3");
  // A player renamed in the deal (same key) changes the view.
  const player = R.view(build(ws, {...row, receive: [{...P(12, "RB", 22), name: "New name"}]}));
  assert.strictEqual(player.receive, "You get New name.");
});

check("test_force_fit_candidates_kept", () => {
  // Overall Force fit (their side), our side natural: still a gain for you, so it stays an idea.
  const out = run([opp("f", "t1", [P(11, "RB", 20)], [P(12, "RB", 22)], 2, 1, {overall: "force"})]);
  assert.deepStrictEqual(out.recommendations.map(r => r.id), ["f"]);
});

check("test_legacy_note_in_why", () => {
  // A profile saved by the earlier build keeps its words (manager-profiles.js keeps note and anchors.subjective).
  const ws = league();
  const text = JSON.stringify({v: 1, leagues: {lg: {t1: {anchors: {subjective: "strong"}, note: "loves rookies"}}}});
  const book = M.parseStored(text).book;
  const row = opp("x", "t1", [P(11, "RB", 20)], [P(12, "RB", 22)], 2, 3);
  const plain = run([row]).recommendations[0];
  const rec = R.build({rows: [row], book, ws, allRows: ALL, profiles: M}).recommendations[0];
  assert.ok(rec.why.includes("Your note: loves rookies"), rec.why.join(" | "));
  assert.strictEqual(rec.theirGain, plain.theirGain, "a kept note never changes a number");
  assert.strictEqual(rec.band, plain.band);
  // Earlier users could leave a note without selecting an Other preferences strength.
  for (const subjective of [undefined, "unknown", "none", "some", "strong"]) {
    const saved = M.parseStored(JSON.stringify({v: 1, leagues: {lg: {t1: {
      anchors: {subjective}, note: "kept note without a strength"
    }}}})).book;
    const idea = R.build({rows: [row], book: saved, ws, allRows: ALL, profiles: M}).recommendations[0];
    assert.ok(idea.why.includes("Your note: kept note without a strength"), `note missing at ${subjective}`);
    assert.strictEqual(idea.theirGain, plain.theirGain);
    assert.strictEqual(idea.band, plain.band);
  }
});

process.stdout.write(JSON.stringify({ran, failures}));
