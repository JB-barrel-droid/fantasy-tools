// JEG-1263: checks for the Simplified site view logic (app/v2/simplified-site.js). Pure Node, no browser.
// Usage: node tests/simplified_site_harness.cjs <modules dir>. Prints {check: true | "why it failed"} as JSON.
"use strict";

const fs = require("fs");
const path = require("path");

const dir = path.resolve(process.argv[2] || path.join(__dirname, "..", "app", "v2"));
const S = require(path.join(dir, "simplified-site.js"));
const O = require(path.join(dir, "opportunities.js"));
const FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "simplified-site", "synthetic-answer.json"), "utf8"));
// The full dashboard's capture cell format (league.js), read from its source so the comparison is against the page itself.
const leagueSrc = fs.readFileSync(path.join(dir, "league.js"), "utf8");
const signedSrc = (leagueSrc.match(/const signed = (n => [^\n]+);\n/) || [])[1];
// eslint-disable-next-line no-eval
const dashboardSigned = signedSrc ? eval(signedSrc) : null;

const clone = x => JSON.parse(JSON.stringify(x));
const freeze = x => { if (x && typeof x === "object") { Object.values(x).forEach(freeze); Object.freeze(x); } return x; };
const ctx = edit => { const c = clone(FIXTURE); if (edit) edit(c); return freeze(c); };
function eq(a, b, what) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${what}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`); }
function ok(v, what) { if (!v) throw new Error(what); }
const withheld = vm => vm.answer === null && vm.more.length === 0 && vm.stretch.length === 0 && vm.detail === null;

const checks = {
  test_name_and_route_are_exact() {
    eq(S.NAME, "Simplified site", "section name");
    eq(S.ROUTE, "#simplified-site", "route");
    eq(S.viewModel(ctx(), null).name, "Simplified site", "view name");
  },
  test_route_contract() {
    eq(S.parseRoute("#simplified-site"), {detail: null}, "section");
    eq(S.parseRoute("#simplified-site?from=menu"), {detail: null}, "query ignored");
    const id = "t3|syn-wr-2,syn-te-4|syn-rb-7";
    eq(S.parseRoute(S.routeFor(id)), {detail: id}, "detail round trip");
    ok(!/[|,]/.test(S.routeFor(id)), "detail id is encoded in the address");
    eq(S.routeFor(null), "#simplified-site", "no id is the section");
    eq(S.parseRoute("#simplified-site/trade/"), {detail: null}, "empty detail is the section");
    eq(S.parseRoute("#simplified-site/trade/%E0%A4%A"), {detail: null}, "a malformed id falls back to the section");
    eq(S.parseRoute("#find-league"), null, "another route");
    eq(S.parseRoute("#simplified-sitex"), null, "a prefix is not the route");
    eq(S.parseRoute(""), null, "landing");
  },
  test_answer_leads_with_the_top_idea() {
    const vm = S.viewModel(ctx(), null);
    eq(vm.state, "answer", "state");
    eq(vm.answer.id, FIXTURE.ideas.recommendations[0].id, "answer is the first recommendation");
    eq(vm.answer.offer, "Offer RB Alpha to Synthetic Team B for WR India.", "offer sentence");
    eq(vm.answer.why, FIXTURE.ideas.recommendations[0].why[0], "concise why is the first why line");
    eq(vm.more.map(x => x.rank), [2, 3], "the rest follow, ranked");
    eq(vm.stretch.map(x => x.id), [FIXTURE.ideas.stretch[0].id], "stretch offers kept separate");
    ok(vm.stretch.every(x => x.stretch) && !vm.answer.stretch, "stretch flag");
  },
  test_order_is_the_given_ranking() {
    const vm = S.viewModel(ctx(c => c.ideas.recommendations.reverse()), null);
    eq([vm.answer.id].concat(vm.more.map(x => x.id)), FIXTURE.ideas.recommendations.map(r => r.id).reverse(), "no re-ranking");
  },
  test_values_match_dashboard() {
    ok(dashboardSigned, "league.js capture format not found");
    const vm = S.viewModel(ctx(), null);
    const shown = [vm.answer].concat(vm.more, vm.stretch);
    const recs = FIXTURE.ideas.recommendations.concat(FIXTURE.ideas.stretch);
    recs.forEach((rec, i) => {
      const x = shown[i];
      eq(x.gainText, dashboardSigned(rec.ourGain), `gain shown as the Trade opportunities capture cell (${rec.id})`);
      eq(x.gainText, O.fmt(rec.ourGain), `gain shown with opportunities.js fmt (${rec.id})`);
      eq(x.likelihood, rec.likelihood, "likelihood words passed through");
      eq(x.give, rec.give.map(p => p.name).join(" + "), "give names");
      eq(x.receive, rec.receive.map(p => p.name).join(" + "), "receive names");
      eq(x.whyAll, rec.why, "why lines passed through");
      eq(x.fitWord, rec.fit ? O.FIT_WORD[rec.fit] : null, "fit word from opportunities.js");
    });
    eq(shown.map(x => x.gainText), ["+4.2", "+3.0", "+0.1", "+6.5"], "fixture gains as displayed");
  },
  test_context_not_mutated() {
    // Not frozen, so an in-place change shows in the comparison; two stretch offers, so reordering one shows too.
    const c = clone(FIXTURE);
    c.ideas.stretch.push({...clone(c.ideas.stretch[0]), id: "t6|syn-wr-6|syn-wr-13", opponent: "Synthetic Team F"});
    const before = JSON.stringify(c);
    S.viewModel(c, null);
    eq(JSON.stringify(c), before, "context unchanged by the section");
    S.viewModel(c, {detail: FIXTURE.ideas.recommendations[1].id});
    eq(JSON.stringify(c), before, "context unchanged by a detail view");
    S.viewModel(ctx(), {detail: FIXTURE.ideas.stretch[0].id});   // and a frozen context reads without throwing
  },
  test_loading_and_error() {
    eq(S.viewModel(freeze({status: "loading"}), null).state, "loading", "loading");
    const err = S.viewModel(freeze({status: "error", error: "timeout"}), null);
    eq(err.state, "error", "error");
    ok(/timeout/.test(err.text) && withheld(err), "error text and nothing shown");
    eq(S.viewModel(null, null).state, "error", "no context is an error, not an answer");
    eq(S.viewModel(freeze({}), null).state, "error", "unknown status is an error");
  },
  test_empty_without_league_or_team() {
    const none = S.viewModel(ctx(c => { c.league = null; }), null);
    eq(none.state, "empty", "no league");
    ok(withheld(none), "no league withholds");
    const noTeam = S.viewModel(ctx(c => { c.league.myTeam = null; }), null);
    eq(noTeam.state, "empty", "no team of yours");
    ok(withheld(noTeam), "no team withholds");
  },
  test_incomplete_withholds() {
    const cases = {
      missing: c => { c.missing = [{key: "context", text: "League not carried."}]; },
      noIdeas: c => { c.ideas = null; },
      noHorizon: c => { delete c.basis.horizon; },
      nanGain: c => { c.ideas.recommendations[1].ourGain = null; },
      noLikelihood: c => { c.ideas.recommendations[2].likelihood = ""; },
      unknownBand: c => { c.ideas.recommendations[0].band = "certain"; },
      unnamedPlayer: c => { c.ideas.stretch[0].receive[0].name = ""; },
      emptySide: c => { c.ideas.recommendations[0].give = []; }
    };
    Object.entries(cases).forEach(([name, edit]) => {
      const vm = S.viewModel(ctx(edit), null);
      eq(vm.state, "incomplete", name);
      ok(withheld(vm) && vm.reasons.length > 0, `${name}: withheld with a reason`);
    });
    eq(S.viewModel(ctx(cases.missing), null).reasons, ["League not carried."], "missing text shown as given");
  },
  test_weekly_never_blended() {
    const weekly = S.viewModel(ctx(c => { c.basis.horizon = "weekly"; }), null);
    eq(weekly.state, "incomplete", "weekly basis withheld");
    ok(withheld(weekly) && weekly.reasons.some(r => /Weekly/.test(r)), "weekly reason");
    const mixed = S.viewModel(ctx(c => { c.ideas.recommendations[1].horizon = "weekly"; }), null);
    eq(mixed.state, "incomplete", "one weekly idea in a rest-of-season list withholds the answer");
    ok(withheld(mixed), "mixed withheld");
    eq(S.viewModel(ctx(c => { c.ideas.recommendations[1].horizon = "ros"; }), null).state, "answer", "a rest-of-season label is fine");
  },
  test_no_qualifying_result() {
    const vm = S.viewModel(ctx(c => { c.ideas.recommendations = []; }), null);
    eq(vm.state, "none", "none");
    ok(vm.answer === null && vm.more.length === 0, "no answer made up");
    eq(vm.stretch.length, 1, "stretch offers still listed, in their own section");
    eq(vm.counts, "Read from 41 trade opportunities. Left out: 6 trades with managers marked won't trade; 29 trades that aren't a gain for you; 1 trade too far below even for them; 1 trade with nothing to judge their side by.", "counts line");
    eq(S.viewModel(ctx(c => { c.ideas = {recommendations: [], stretch: [], counts: {considered: 0}}; }), null).counts, "There were no trade opportunities to read.", "nothing considered");
  },
  test_detail_view() {
    const id = FIXTURE.ideas.recommendations[1].id;
    const vm = S.viewModel(ctx(), {detail: id});
    eq(vm.detail && vm.detail.id, id, "detail found");
    eq(vm.detail.sources, ["Trade chart average (published)"], "provenance kept in the detail");
    eq(vm.detail.fallback, "nothing marked", "uncertainty kept in the detail");
    const stretch = S.viewModel(ctx(), {detail: FIXTURE.ideas.stretch[0].id});
    ok(stretch.detail && stretch.detail.stretch, "stretch detail reachable");
    const gone = S.viewModel(ctx(), {detail: "t9|nobody|nothing"});
    ok(gone.detail === null && gone.detailGone && gone.state === "answer", "an unknown trade id says so and shows the current answer");
    const held = S.viewModel(ctx(c => { c.missing = [{key: "x", text: "x"}]; }), {detail: id});
    ok(held.detail === null && withheld(held), "a deep link cannot open a withheld trade");
  },
  test_fixture_labelled() {
    const vm = S.viewModel(ctx(), null);
    eq(vm.fixture, {kind: "synthetic", label: FIXTURE.fixture.label}, "fixture label");
    eq(S.viewModel(ctx(c => { delete c.fixture; }), null).fixture, null, "a live context carries no fixture label");
  },
  test_live_adapter_withholds_until_gates() {
    const ws = freeze({name: "Synthetic League", myTeamId: "a", teams: [{id: "a", name: "Synthetic Team A", entries: []}, {id: "b", name: "Synthetic Team B", entries: []}]});
    const writes = [];
    const store = {get: () => ws, replace: () => writes.push("replace"), set: () => writes.push("set"), update: () => writes.push("update")};
    const ideas = freeze(clone(FIXTURE.ideas));
    const root = gates => ({TradeValueWorkspace: {store}, TradeValueTradeIdeas: {compute: () => ideas}, TradeValueSimplifiedGates: gates});
    const closed = S.viewModel(S.liveContext(root(undefined)), null);
    eq(closed.state, "incomplete", "gates closed: withheld");
    eq(closed.reasons.length, 3, "one reason per gate");
    eq(S.GATES.map(g => g[1]), ["JEG-1259", "JEG-1260", "JEG-1249"], "the three gates");
    eq(S.viewModel(S.liveContext(root({context: true, readout: true})), null).state, "incomplete", "two of three gates is still withheld");
    const open = S.viewModel(S.liveContext(root({context: true, readout: true, lineup: true})), null);
    eq(open.state, "answer", "all gates open: the answer");
    eq(open.fixture, null, "live answer is not labelled a fixture");
    eq(open.league, "Synthetic League", "league name read");
    eq(writes, [], "the adapter never writes the workspace");
    const noCard = S.viewModel(S.liveContext({TradeValueWorkspace: {store}, TradeValueSimplifiedGates: {context: true, readout: true, lineup: true}}), null);
    eq(noCard.state, "incomplete", "no Trade ideas card: withheld");
    eq(S.liveContext({}).status, "loading", "no workspace yet: loading");
    eq(S.viewModel(S.liveContext({TradeValueWorkspace: {store: {get: () => { throw new Error("bad state"); }}}}), null).state, "error", "store error is an error");
  },
  test_live_adapter_no_league() {
    const store = {get: () => freeze({name: "My league", myTeamId: null, teams: []})};
    eq(S.viewModel(S.liveContext({TradeValueWorkspace: {store}}), null).state, "empty", "empty workspace");
    const noMine = {get: () => freeze({name: "L", myTeamId: null, teams: [{id: "a", name: "A", entries: []}]})};
    eq(S.viewModel(S.liveContext({TradeValueWorkspace: {store: noMine}}), null).state, "empty", "no team marked yours");
  }
};

const out = {};
Object.entries(checks).forEach(([name, fn]) => {
  try { fn(); out[name] = true; } catch (error) { out[name] = String(error && error.message || error); }
});
process.stdout.write(JSON.stringify(out, null, 1));
