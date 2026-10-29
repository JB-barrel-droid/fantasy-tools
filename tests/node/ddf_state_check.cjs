// JEG-1025: DDF state codec. Run by tests/test_ddf_state.py.
const assert = require("node:assert/strict");
const S = require("../../app/v2/ddf-state.js");

const full = {
  v: 1,
  league: {scoring: "half_ppr", teams: 10, roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 1, BENCH: 6},
    shares: {QB: 0.2, RB: 0.35, WR: 0.35, TE: 0.1}, bso: 0.2, inj: "all", conf: 1.5,
    weeks: {regend: 14, playoffs: [15, 17], optimize: "regular", week: 7}},
  work: {view: "finder", give: [{key: "101", name: "A B"}], get: [{key: "202"}, {name: "Ja'Marr Chase"}],
    mine: [{key: "1"}, {key: "2"}], theirs: [{name: "Josh Allen"}], target: {key: "9"}},
  sources: ["espn", "fantasycalc"], asOf: "2026-10-24",
};

// Round trip through both encodings gives the same state (names beyond the first of a key entry are advisory).
for (const [label, enc, dec] of [
  ["query", s => S.encodeQuery(s), q => S.decodeQuery(q)],
  ["block", s => S.encodeBlock(s), t => S.decodeBlock(t)],
]) {
  const out = dec(enc(full));
  assert.deepEqual(out.warnings, [], label);
  const want = JSON.parse(JSON.stringify(full)); delete want.asOf;
  const got = JSON.parse(JSON.stringify(out.state)); delete got.asOf;
  if (label === "query") {
    // A key entry's name is not in the URL; everything else survives.
    want.work.give = [{key: "101"}];
    assert.deepEqual(got, want, label);
  } else assert.deepEqual(got, want, label);
}

// Old shared links still open. This is a real link shape from tradeHash().
let r = S.decodeQuery("give=12,34&get=56&scoring=ppr&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN6&bench=0.150");
assert.deepEqual(r.state.work.give, [{key: "12"}, {key: "34"}]);
assert.deepEqual(r.state.work.get, [{key: "56"}]);
assert.equal(r.state.league.scoring, "ppr");
assert.equal(r.state.league.roster.BENCH, 6);
assert.equal(r.state.league.bso, undefined, "bench=0.150 is the old default, no override");
r = S.decodeQuery("scoring=ppr&bench=0.200");
assert.equal(r.state.league.bso, 0.2);
r = S.decodeQuery("#" + "scoring=standard&bso=0.250&inj=recent&conf=1&regend=14&playoffs=15-17&optimize=season&week=7&shares=QB0.200_RB0.350_WR0.350_TE0.100");
assert.deepEqual(r.state.league.shares, {QB: 0.2, RB: 0.35, WR: 0.35, TE: 0.1});
assert.deepEqual(r.state.league.weeks, {regend: 14, playoffs: [15, 17], optimize: "season", week: 7});

// Bad league input drops the whole league, never half of it; the trade still comes through.
r = S.decodeQuery("give=1&get=2&scoring=ppr&teams=11");
assert.equal(r.state.league, undefined);
assert.deepEqual(r.state.work.give, [{key: "1"}]);
assert.match(r.warnings.join(" "), /teams must be/);
r = S.normalize({league: {scoring: "ppr", roster: {QB: 99}}});
assert.equal(r.state, null);
r = S.normalize({league: {scoring: "ppr", shares: {QB: 0.5, RB: 0.5, WR: 0.5, TE: 0.5}}});
assert.equal(r.state.league.shares, undefined);
assert.match(r.warnings.join(" "), /shares/);

// Unknown fields ignored, newer version warns, junk rejected, lists capped and deduped.
r = S.normalize({v: 7, league: {scoring: "ppr", mystery: 1}, extra: true});
assert.deepEqual(r.state.league, {scoring: "ppr"});
assert.match(r.warnings.join(" "), /newer/);
assert.equal(S.normalize("hi").state, null);
assert.equal(S.normalize({}).state, null);
r = S.normalize({work: {give: Array.from({length: 60}, (_, i) => ({key: String(i)})).concat([{key: "0"}])}});
assert.equal(r.state.work.give.length, 40);
r = S.normalize({work: {give: [{key: "x1"}, {name: ""}, 5, "Bijan Robinson"]}});
assert.deepEqual(r.state.work.give, [{key: "5"}, {name: "Bijan Robinson"}]);

// A block pasted inside chat prose, bare JSON, and a link in prose all decode.
const block = S.encodeBlock({league: {scoring: "ppr", teams: 12}, work: {mine: [{name: "Josh Allen"}]}}, {url: "https://x/#compare-trade?scoring=ppr"});
r = S.decodeBlock("Here is your state!\n\n" + block + "\n\nLet me know.");
assert.equal(r.state.league.teams, 12);
assert.deepEqual(r.state.work.mine, [{name: "Josh Allen"}]);
r = S.decodeBlock('{"league":{"scoring":"ppr"}}');
assert.equal(r.state.league.scoring, "ppr");
r = S.decodeBlock("Try https://site/#compare-trade?give=1&get=2&scoring=ppr&roster=QB1.RB2 now");
assert.deepEqual(r.state.work.give, [{key: "1"}]);
r = S.decodeBlock("nothing here");
assert.equal(r.state, null);
r = S.decodeBlock("```ddf-state\n{not json\n```");
assert.equal(r.state, null);

// Names with commas, spaces and unicode survive the URL. A space is encoded once (%20),
// not twice (%2520). A comma is encoded again so URLSearchParams does not split the name.
const spaced = S.encodeQuery({work: {get: [{name: "Ghost Player"}], theirs: [{name: "Amon-Ra St. Brown, Jr"}, {name: "José Ramírez"}]}});
assert.equal(spaced.includes("%2520"), false, spaced);
assert.match(spaced, /n:Ghost%20Player/);
assert.match(spaced, /%252C/);
r = S.decodeQuery(spaced);
assert.deepEqual(r.state.work.get, [{name: "Ghost Player"}]);
assert.deepEqual(r.state.work.theirs, [{name: "Amon-Ra St. Brown, Jr"}, {name: "José Ramírez"}]);
// An older link that encoded the space twice still decodes.
r = S.decodeQuery("get=n:Ghost%2520Player&v=1");
assert.deepEqual(r.state.work.get, [{name: "Ghost Player"}]);
console.log("ok");
