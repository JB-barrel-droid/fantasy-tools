/* Build a Trade: the offer message options, chosen by the shape of the offer (JEG-1559).

   Pure functions, no DOM and no value math: the page (build-trade.js) passes the players with the engine's numbers,
   the trade checks it already ran (TradeValueFinder.tradeFit) and the reference chart claim it already built from
   published chart values. Rules every message follows: no site name, no team-name greeting ("Hi!" only), a chart
   claim only when that chart's published numbers support it, and the numbers quoted are the chart's own.

   DDFOffer.shape(input)   -> the offer's shape (sizes, positions, value balance, roster facts)
   DDFOffer.options(input) -> {shape, options:[{id, label, hint, text}], preselect}

   input = {
     give, get:   [{n, pos, ddf, an, starter}]  the players you send / receive; an = Analyst charts value;
                  starter = true/false on their current team's lineup (league mode), null when unknown
     league:      true when the partner's roster is known (My league)
     fit:         null | {usStarter, themStarter, themNeed:[pos]}  from tradeFit (starter changes, positions the
                  partner moves toward its expected depth)
     claim:       null | {k, status:'helps'|'even', text}  the effective reference chart (picked, else best) when it
                  supports the pitch
     pickedClaim: null | the same, only when the reader picked that chart (other pitches cite only a picked chart)
     shopText:    the shop message tail (the picked chart's number for your players), '' when none
     partner:     null | {pct, shown, band, label}  the partner's roster change from DDFOpportunity.rosterImprovementPct
                  (JEG-1558, bands 'better' | 'unchanged' | 'slightly_worse' | 'clearly_worse' | 'unsized'); never
                  computed here. sender: the same for your roster (shown on the page only, not in the message).
     rationale:   null | {text}  JEG-1561 SLOT: the natural-fit rationale line from the shared explanation module
                  (Workspace agent). Appended to the value option when present; this file never computes it.
   } */
(function (root) {
  'use strict';
  const finite = v => typeof v === 'number' && isFinite(v);
  const EVEN_BAND = 0.10;      // within 10% of the larger side reads as near even (the verdict's "slight edge" band)
  const NEAR_ZERO = 1.0;       // an Analyst charts value under 1.0 carries no trade value: named as an add-in
  const SHOW_NET = 0.05;       // a starter change that shows as 0.0 is no change

  const joinNames = list => list.length < 3 ? (list.join(' and ') || 'No players') : list.slice(0, -1).join(', ') + ' and ' + list[list.length - 1];
  const names = side => side.map(p => p.n);
  const sum = (side, key) => side.reduce((t, p) => t === null || !finite(p[key]) ? null : t + p[key], 0);
  const posList = side => [...new Set(side.map(p => p.pos).filter(Boolean))];

  /* Which side a value view favours: 'you' (you receive more), 'they', 'even' (near even), or null (a player has no value). */
  function balance(give, get, key) {
    const g = sum(give, key), r = sum(get, key);
    if (g === null || r === null || !give.length || !get.length) return {side: null, give: g, get: r, net: null};
    const net = r - g, big = Math.max(g, r) || 1;
    return {side: Math.abs(net) / big <= EVEN_BAND ? 'even' : net > 0 ? 'you' : 'they', give: g, get: r, net};
  }

  function shape(input) {
    const give = input.give || [], get = input.get || [];
    const nz = p => finite(p.an) && p.an < NEAR_ZERO;
    const split = list => { const add = list.filter(nz); return add.length && add.length < list.length ? {core: list.filter(p => !nz(p)), add} : {core: list, add: []}; };
    const G = split(give), R = split(get);
    const gc = G.core.length, rc = R.core.length;
    const size = !get.length ? 'shop' : gc === rc ? (gc === 1 ? 'one-for-one' : 'even-count') : gc > rc ? 'consolidate' : 'depth';
    const gp = posList(give), rp = posList(get);
    const samePos = gp.length === 1 && rp.length === 1 && gp[0] === rp[0];
    const fit = input.league && input.fit ? input.fit : null;
    // The partner moves toward its expected depth at a position you send (tradeFit towardAt): you fill its need.
    const fills = fit && Array.isArray(fit.themNeed) ? fit.themNeed.filter(pos => gp.includes(pos)) : [];
    // Their bench player(s) for a trade that improves their starting lineup.
    const benchForStarter = Boolean(fit && get.length && get.every(p => p.starter === false) && finite(fit.themStarter) && fit.themStarter > SHOW_NET);
    return {
      size, giveCount: give.length, getCount: get.length, coreGive: gc, coreGet: rc, addIns: {give: G.add, get: R.add},
      uneven: G.add.length > 0 || R.add.length > 0, core: {give: G.core, get: R.core},
      samePos, givePos: gp, getPos: rp,
      analyst: balance(give, get, 'an'), ddf: balance(give, get, 'ddf'),
      fills, benchForStarter, league: Boolean(input.league),
      rosterLabels: [input.sender, input.partner].filter(x => x && x.label).map(x => x.label)
    };
  }

  /* The one-line description of the shape shown above the options. */
  function describe(s) {
    if (s.size === 'shop') return `Shopping ${s.giveCount === 1 ? 'one player' : s.giveCount + ' players'} · no player asked for yet`;
    const parts = [`${s.giveCount}-for-${s.getCount}` + (s.size === 'consolidate' ? ' (you consolidate)' : s.size === 'depth' ? ' (you add depth)' : '')];
    if (s.uneven) parts.push('with an add-in');
    parts.push(s.samePos ? `same position (${s.givePos[0]})` : `${s.givePos.join('/') || '?'} for ${s.getPos.join('/') || '?'}`);
    const word = b => b.side === 'even' ? 'near even' : b.side === 'you' ? 'you gain' : b.side === 'they' ? 'they gain' : 'not every player listed';
    parts.push(`Analyst charts: ${word(s.analyst)}`);
    parts.push(`DDF Value: ${word(s.ddf)}`);
    if (s.fills.length) parts.push(`fills their ${s.fills.join('/')} need`);
    if (s.benchForStarter) parts.push('their bench for a lineup upgrade');
    if (s.rosterLabels) s.rosterLabels.forEach(l => parts.push(l));
    return parts.join(' · ');
  }

  function options(input) {
    const s = shape(input), give = input.give || [], get = input.get || [];
    const gAll = joinNames(names(give)), rAll = joinNames(names(get));
    const out = [];
    const add = (id, label, hint, text) => out.push({id, label, hint, text});
    if (s.size === 'shop') {
      add('shop', 'Shop a player', 'Ask what they would give', `Hi! I'm looking to move ${gAll}. Is there someone on your roster you'd part with for ${give.length > 1 ? 'them' : 'him'}?${input.shopText || ''}`);
      return {shape: s, summary: describe(s), options: out, preselect: 'shop'};
    }
    const addNote = a => `${joinNames(names(a))} as ${a.length > 1 ? 'add-ins' : 'an add-in'}`;
    const giveText = joinNames(names(s.core.give)) + (s.addIns.give.length ? ` (plus ${addNote(s.addIns.give)})` : '');
    const getText = joinNames(names(s.core.get)) + (s.addIns.get.length ? `, plus ${addNote(s.addIns.get)}` : '');
    const tag = `${s.coreGive}-for-${s.coreGet}` + (s.coreGive === s.coreGet ? ' with an add-in' : '');
    const terms = s.uneven ? `Would you do a ${tag}? I'd send ${giveText} for ${getText}.` : `Would you trade ${rAll} for ${gAll}?`;
    const bench = s.benchForStarter ? ` ${rAll} ${get.length > 1 ? 'are' : 'is'} on your bench right now, and this improves your starting lineup.` : '';
    const picked = input.pickedClaim ? ' ' + input.pickedClaim.text : '';

    add('opener', 'Short opener', 'Just the offer', `Hi! ${terms}${bench}`);
    const why = input.rationale && input.rationale.text ? ' ' + input.rationale.text : '';   // JEG-1561 slot
    // The partner's roster change, stated plainly from the JEG-1558 band (never a promise that they will accept, and a
    // clear loss is never called marginal: that band gets the counter-ready ask instead).
    const pb = input.partner && finite(input.partner.shown) ? input.partner : null;
    const mag = pb ? Math.abs(pb.shown).toFixed(1) : '';
    const rosterLine = !pb ? '' : pb.band === 'better' ? ` It makes your roster about ${mag}% better.`
      : pb.band === 'unchanged' ? ` It barely changes your roster (about ${mag}%).`
      : pb.band === 'slightly_worse' ? ` It costs your roster only about ${mag}%, so it's close.` : '';
    if (input.claim) add('value', 'Offer with the numbers', 'Cites a public trade chart', `Hi! ${terms} ${input.claim.text}${why}${rosterLine}${bench} Let me know what you think.`);
    if (s.size === 'consolidate') add('consolidate', 'Consolidation pitch', 'You send more players', `Hi! ${terms} I'd rather have fewer, better players in my lineup, and you'd get useful depth.${rosterLine}${picked}`);
    if (s.size === 'depth') add('depth', 'Depth pitch', 'You ask for more players', `Hi! ${terms} I'm looking for depth, and you'd get the stronger player in one spot.${rosterLine}${picked}`);
    if (s.fills.length) {
      const at = s.fills[0], who = joinNames(give.filter(p => p.pos === at).map(p => p.n));
      add('need', 'Fills their need', `Their roster is thin at ${at}`, `Hi! You look thin at ${at}, and ${who} would help there. ${terms}${rosterLine}${picked}`);
    }
    const clearLoss = Boolean(pb && pb.band === 'clearly_worse');
    if (s.analyst.side === 'you' || clearLoss) {
      add('ask', 'Counter-ready ask', s.analyst.side === 'you' ? 'The charts favor you: leave room' : 'A clear loss for their roster: ask what works', `Hi! I'm interested in ${rAll}. I could start with ${gAll}, and I'm open to adjusting it. What would make it work for you?`);
    }
    const preselect = s.analyst.side === 'you' || clearLoss ? 'ask' : input.claim ? 'value' : s.fills.length ? 'need' : 'opener';
    return {shape: s, summary: describe(s), options: out, preselect};
  }

  const api = {shape, options, describe, EVEN_BAND, NEAR_ZERO};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.DDF = root.DDF || {}, root.DDFOffer = api);
})(typeof window !== 'undefined' ? window : globalThis);
