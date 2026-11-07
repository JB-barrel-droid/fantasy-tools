// JEG-1559: Build a Trade's offer message options, one row per offer shape (app/next/build-offer.js).
// Each row: the input, the option ids shown (in order), the preselected one, and exact texts / summary checks.
// Run: node tests/node/build_offer_check.cjs
'use strict';
const assert = require('assert');
const path = require('path');
const O = require(path.join(__dirname, '..', '..', 'app', 'next', 'build-offer.js'));

const P = (n, pos, ddf, an, starter = null) => ({n, pos, ddf, an, starter});
const allen = P('Josh Allen', 'QB', 40, 30), burrow = P('Joe Burrow', 'QB', 38, 29);
const gibbs = P('Jahmyr Gibbs', 'RB', 75, 54), cook = P('James Cook', 'RB', 54, 41), hall = P('Breece Hall', 'RB', 30, 25);
const chase = P("Ja'Marr Chase", 'WR', 57, 41), nacua = P('Puka Nacua', 'WR', 64, 47), london = P('Drake London', 'WR', 50, 42);
const bigsby = P('Tank Bigsby', 'RB', 8, 12);
const claim = {k: 'cbs', status: 'helps', text: "CBS Sports' trade chart shows you get about 8% more value than you give (it has it at 56.5 for 51.5)."};

const ROWS = [
  {name: '1-for-1 near even, no chart support', input: {give: [allen], get: [burrow]},
    ids: ['opener'], pre: 'opener',
    text: {opener: 'Hi! Would you trade Joe Burrow for Josh Allen?'},
    summary: ['1-for-1', 'same position (QB)', 'Analyst charts: near even', 'DDF Value: near even']},
  {name: '1-for-1 with a chart that supports it', input: {give: [gibbs], get: [nacua], claim},
    ids: ['opener', 'value'], pre: 'value',
    text: {value: `Hi! Would you trade Puka Nacua for Jahmyr Gibbs? ${claim.text} Let me know what you think.`},
    summary: ['RB for WR']},
  {name: '2-for-1 consolidation (you send more)', input: {give: [cook, hall], get: [gibbs], pickedClaim: claim, claim},
    ids: ['opener', 'value', 'consolidate'], pre: 'value',
    text: {consolidate: `Hi! Would you trade Jahmyr Gibbs for James Cook and Breece Hall? I'd rather have fewer, better players in my lineup, and you'd get useful depth. ${claim.text}`},
    summary: ['2-for-1 (you consolidate)']},
  {name: '1-for-2 depth (you ask for more)', input: {give: [gibbs], get: [cook, bigsby]},
    ids: ['opener', 'depth'], pre: 'opener',
    text: {depth: "Hi! Would you trade James Cook and Tank Bigsby for Jahmyr Gibbs? I'm looking for depth, and you'd get the stronger player in one spot."},
    summary: ['1-for-2 (you add depth)']},
  {name: '2-for-2 swap', input: {give: [gibbs, allen], get: [nacua, burrow]},
    ids: ['opener'], pre: 'opener', summary: ['2-for-2', 'RB/QB for WR/QB']},
  {name: 'lopsided in your favor by the analyst charts', input: {give: [hall], get: [gibbs]},
    ids: ['opener', 'ask'], pre: 'ask',
    text: {ask: "Hi! I'm interested in Jahmyr Gibbs. I could start with Breece Hall, and I'm open to adjusting it. What would make it work for you?"},
    summary: ['Analyst charts: you gain', 'DDF Value: you gain']},
  {name: 'lopsided in their favor: no counter-ready ask', input: {give: [gibbs], get: [hall]},
    ids: ['opener'], pre: 'opener', summary: ['Analyst charts: they gain']},
  {name: 'a near-zero add-in makes it uneven', input: {give: [chase, P('Bo Nix', 'QB', 0.2, 0.4)], get: [london]},
    ids: ['opener'], pre: 'opener',
    text: {opener: "Hi! Would you do a 1-for-1 with an add-in? I'd send Ja'Marr Chase (plus Bo Nix as an add-in) for Drake London."},
    summary: ['2-for-1', 'with an add-in']},
  {name: 'league: you fill their need', input: {league: true, give: [cook], get: [chase], fit: {usStarter: 1, themStarter: 1, themNeed: ['RB']}},
    ids: ['opener', 'need'], pre: 'need',
    text: {need: "Hi! You look thin at RB, and James Cook would help there. Would you trade Ja'Marr Chase for James Cook?"},
    summary: ['fills their RB need']},
  {name: 'league: their bench player for a lineup upgrade', input: {league: true, give: [allen], get: [P('Joe Burrow', 'QB', 38, 29, false)], fit: {usStarter: 0, themStarter: 3.2, themNeed: []}},
    ids: ['opener'], pre: 'opener',
    text: {opener: 'Hi! Would you trade Joe Burrow for Josh Allen? Joe Burrow is on your bench right now, and this improves your starting lineup.'},
    summary: ['their bench for a lineup upgrade']},
  {name: 'need is ignored outside a league (no roster data)', input: {give: [cook], get: [chase], fit: {usStarter: 1, themStarter: 1, themNeed: ['RB']}},
    ids: ['opener'], pre: 'opener'},
  {name: 'shop a player (nothing asked for)', input: {give: [gibbs], get: [], shopText: " By CBS Sports' trade chart he's about 56.5, so I'm looking for something close."},
    ids: ['shop'], pre: 'shop',
    text: {shop: "Hi! I'm looking to move Jahmyr Gibbs. Is there someone on your roster you'd part with for him? By CBS Sports' trade chart he's about 56.5, so I'm looking for something close."},
    summary: ['Shopping one player']},
  {name: 'band better: the pitch states it', input: {give: [gibbs], get: [nacua], claim, partner: {pct: 2.15, shown: 2.1, band: 'better', label: 'Their roster gets about 2.1% better'}},
    ids: ['opener', 'value'], pre: 'value',
    text: {value: `Hi! Would you trade Puka Nacua for Jahmyr Gibbs? ${claim.text} It makes your roster about 2.1% better. Let me know what you think.`},
    summary: ['Their roster gets about 2.1% better']},
  {name: 'band unchanged: barely changes', input: {give: [gibbs], get: [nacua], claim, partner: {pct: -0.42, shown: -0.4, band: 'unchanged'}},
    ids: ['opener', 'value'], pre: 'value',
    text: {value: `Hi! Would you trade Puka Nacua for Jahmyr Gibbs? ${claim.text} It barely changes your roster (about 0.4%). Let me know what you think.`}},
  {name: 'band slightly worse: small and honest, no promise', input: {give: [cook, hall], get: [gibbs], claim, pickedClaim: claim, partner: {pct: -1.84, shown: -1.8, band: 'slightly_worse'}},
    ids: ['opener', 'value', 'consolidate'], pre: 'value',
    text: {consolidate: `Hi! Would you trade Jahmyr Gibbs for James Cook and Breece Hall? I'd rather have fewer, better players in my lineup, and you'd get useful depth. It costs your roster only about 1.8%, so it's close. ${claim.text}`}},
  {name: 'band clearly worse: no marginal claim, counter-ready ask', input: {give: [allen], get: [burrow], partner: {pct: -5.3, shown: -5.3, band: 'clearly_worse'}},
    ids: ['opener', 'ask'], pre: 'ask',
    text: {opener: 'Hi! Would you trade Joe Burrow for Josh Allen?'}, absent: ['5.3%', 'close', 'only about'],
    hint: {ask: 'A clear loss for their roster: ask what works'}},
  {name: 'natural fit reason (DDFWhy) on the value option', input: {give: [cook], get: [chase], claim, rationale: {text: 'It fills your RB need.'}},
    ids: ['opener', 'value'], pre: 'value',
    text: {value: `Hi! Would you trade Ja'Marr Chase for James Cook? ${claim.text} It fills your RB need. Let me know what you think.`}},
  {name: 'band unsized: nothing said', input: {give: [gibbs], get: [nacua], claim, partner: {pct: null, shown: null, band: 'unsized'}},
    ids: ['opener', 'value'], pre: 'value',
    text: {value: `Hi! Would you trade Puka Nacua for Jahmyr Gibbs? ${claim.text} Let me know what you think.`}},
  {name: 'a player with no analyst value: balance unknown, no ask', input: {give: [P('Rookie One', 'WR', 5, null)], get: [hall]},
    ids: ['opener'], pre: 'opener', summary: ['Analyst charts: not every player listed']}
];

let failures = 0;
for (const row of ROWS) {
  try {
    const out = O.options(row.input);
    assert.deepStrictEqual(out.options.map(o => o.id), row.ids, 'option ids');
    assert.strictEqual(out.preselect, row.pre, 'preselect');
    assert.ok(out.options.some(o => o.id === out.preselect), 'preselect is shown');
    for (const [id, want] of Object.entries(row.text || {})) assert.strictEqual(out.options.find(o => o.id === id).text, want, `text of ${id}`);
    for (const [id, want] of Object.entries(row.hint || {})) assert.strictEqual(out.options.find(o => o.id === id).hint, want, `hint of ${id}`);
    for (const bad of row.absent || []) assert.ok(out.options.every(o => !o.text.includes(bad)), `no option says "${bad}"`);
    for (const part of row.summary || []) assert.ok(out.summary.includes(part), `summary has "${part}": ${out.summary}`);
    for (const o of out.options) {
      assert.ok(o.text.startsWith('Hi! '), `${o.id} opens with Hi!`);
      assert.ok(!/DDF|Data Driven/.test(o.text), `${o.id} names the site`);
      assert.ok(!/\b(choose|set up)\b/i.test(o.text + o.label + o.hint), `${o.id} wording`);
      assert.ok(o.label && o.hint, `${o.id} has a label and hint`);
      assert.ok(!/will accept|you'll accept|sure to|guarantee/i.test(o.text), `${o.id} promises acceptance`);
    }
    assert.ok(out.options.length <= 5, 'a small set');
    console.log(`ok  ${row.name}`);
  } catch (err) {
    failures += 1;
    console.log(`FAIL ${row.name}: ${err.message}`);
  }
}
if (failures) { console.log(`${failures} of ${ROWS.length} shapes failed`); process.exit(1); }
console.log(`build offer: ${ROWS.length} shapes ok`);
