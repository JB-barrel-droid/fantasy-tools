// Trade Value v2 — manager-aware trade recommendations (JEG-1217 stage 3). Pure; no DOM.
//
// Takes the Trade opportunities rows (opportunities.js: already searched and priced, roster-checked where a fit could be
// judged) and the manager profiles (manager-profiles.js), and returns two lists: recommendations and stretch offers. Nothing
// here changes a value, a fit or the Trade opportunities table. Each idea carries its row's roster warnings for both teams
// (not judged, partial roster, construction issues) next to the likelihood; they are words, not a filter, and force fits
// stay in (Codex review 9e681c74, JEG-1255).
//
// Decisions (Jeremy, 2026-10-29, JEG-1217; picks log):
//   * Appeal (pick A): the other manager's gain is a blend of the anchors the reader marked for them, "a lot" counting double
//     "somewhat"; "doesn't care" and "not sure" do not count. A manager with nothing usable marked stays on the market view.
//     Big names and the ticked boxes (likes rookies, win-now, rarely trades...) have no data, so they change the words only.
//   * Ranking: by the reader's own gain (DDF Value received minus given), not a blend. Each trade shows how likely the other
//     manager may take it, in words; "a manager could just work down the list until a trade is accepted".
//   * Likelihood (pick A): their gain as a share of what they send, in DDF Value. Likely at +10% or more; Possible from -10%
//     up to +10% (both in recommendations); Long shot from -25% up to -10% (stretch offers); worse is not shown. Words, not a
//     percent: the reader's own read of the manager, not a prediction. These bands apply here only (JEG-1125 is untouched).
// Picks made here (Claude, picks log, reversible):
//   * Draft capital = the preseason FantasyPros draft rank at the player's position (row.preseason_ecr_rank, positional; no
//     overall rank is invented), priced as today's DDF Value of the player now at that rank at that position. A player with no
//     preseason rank leaves the draft view unavailable for that trade, never zero.
//   * Rankings have no feed yet (JEG-1198), so that anchor is unavailable and falls back like an unmarked one.
//   * A trade is "a win for you" when its DDF Value gain shows as more than 0.0 and your own fit is not force (total rises and
//     starters hold, opportunities.js ourFitOf).
(function (root) {
  "use strict";

  const OUR_KEY = "ddf_value";
  const WEIGHT = {strong: 2, some: 1};
  const BANDS = {likely: 0.10, possible: -0.10, longShot: -0.25};
  const EPS = 1e-9;   // so exactly +10%, -10% and -25% land in the band the decision names, whatever the float rounding
  const NUMERIC = ["market", "draft", "rankings"];
  const LABEL = {likely: "Likely", possible: "Possible", longShot: "Long shot"};
  const SOURCES = {
    market: {label: "Trade chart average", status: "published"},
    draft: {label: "Preseason FantasyPros draft rankings", status: "published, preseason (not your league's own draft; does not change with scoring)"},
    rankings: {label: "Player rankings", status: "unavailable (no rankings feed yet)"}
  };
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const shown = n => Math.round(n * 10) / 10;
  const sum = (list, fn) => list.reduce((n, r) => (n === null ? null : (v => (finite(v) ? n + v : null))(fn(r))), 0);
  const ddf = r => (r && r.values ? r.values[OUR_KEY] : null);

  // Today's DDF Value at each position's rank: {pos: [value of rank 1, rank 2, ...]}. Built from every engine row.
  function draftCurve(allRows) {
    const byPos = {};
    (allRows || []).forEach(r => {
      if (!r || !finite(ddf(r))) return;
      (byPos[r.pos] = byPos[r.pos] || []).push(ddf(r));
    });
    Object.keys(byPos).forEach(pos => byPos[pos].sort((a, b) => b - a));
    return byPos;
  }
  function draftValue(row, curve) {
    const rank = row && row.preseason_ecr_rank;
    if (!Number.isInteger(rank) || rank < 1) return null;
    const list = curve[row.pos];
    return list && rank <= list.length ? list[rank - 1] : null;
  }

  // The other manager's gain in each view, for one trade. They receive what you give and send what you get.
  function anchorGains(opp, curve) {
    const draftGive = sum(opp.give, r => draftValue(r, curve));
    const draftRecv = sum(opp.receive, r => draftValue(r, curve));
    return {
      market: finite(opp.chartEdge) ? opp.chartEdge : null,
      draft: draftGive !== null && draftRecv !== null ? draftGive - draftRecv : null,
      rankings: null
    };
  }

  // The blended appeal for this manager. Returns {gain, basis: [{anchor, weight, gain}], fallback: reason|null}.
  function appeal(profile, gains) {
    const marked = NUMERIC.filter(a => WEIGHT[profile.anchors[a]]);
    const usable = marked.filter(a => finite(gains[a]));
    if (usable.length) {
      const total = usable.reduce((n, a) => n + WEIGHT[profile.anchors[a]], 0);
      const gain = usable.reduce((n, a) => n + WEIGHT[profile.anchors[a]] * gains[a], 0) / total;
      return {gain, basis: usable.map(a => ({anchor: a, weight: WEIGHT[profile.anchors[a]], gain: gains[a]})),
        fallback: null, missing: marked.filter(a => !finite(gains[a]))};
    }
    const reason = marked.length ? "no data for what you marked" : "nothing marked";
    return finite(gains.market) ? {gain: gains.market, basis: [{anchor: "market", weight: 1, gain: gains.market}], fallback: reason, missing: marked}
      : {gain: null, basis: [], fallback: reason, missing: marked.concat(["market"])};
  }

  // Share of what they send (DDF Value) -> band. null when there is no number to judge.
  function band(gain, sent) {
    if (!finite(gain) || !finite(sent) || sent <= 0) return {band: null, share: null};
    const share = gain / sent;
    const b = share >= BANDS.likely - EPS ? "likely" : share >= BANDS.possible - EPS ? "possible" : share >= BANDS.longShot - EPS ? "longShot" : "hidden";
    return {band: b, share};
  }

  const ANCHOR_WORDS = {market: "the trade charts", draft: "preseason draft rankings", rankings: "player rankings"};
  const TAG_WORDS = {rookies: "like rookies", picks: "want draft picks", winNow: "are win-now", rebuilding: "are rebuilding",
    slowReply: "are slow to reply", rarelyTrades: "rarely trade"};
  const tagWords = tags => (list => (list.length <= 1 ? list.join("") : `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`))(tags.map(tag => TAG_WORDS[tag]).filter(Boolean));
  const signed = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1));
  // Words for the row: why it may appeal, what stays unmodeled, and (for a stretch) which belief has to hold.
  function explain(profile, a, gains, b) {
    const lines = [];
    if (a.fallback) lines.push(`Judged on the trade charts (${a.fallback}): they come out ${signed(gains.market)}.`);
    else a.basis.forEach(x => lines.push(`By ${ANCHOR_WORDS[x.anchor]}, which you said they weigh ${profile.anchors[x.anchor] === "strong" ? "a lot" : "somewhat"}, they come out ${signed(x.gain)}.`));
    if (!a.fallback && a.missing.length) lines.push(`No data yet for ${a.missing.map(m => ANCHOR_WORDS[m]).join(" or ")}.`);
    if (!a.basis.some(x => x.anchor === "market") && finite(gains.market)) lines.push(`The trade charts say ${signed(gains.market)} for them.`);
    if (profile.anchors.names === "some" || profile.anchors.names === "strong") lines.push("You said they like big names; weigh the names in this deal yourself.");
    if (profile.tags.length) lines.push(`You ticked that they ${tagWords(profile.tags)}; weigh that yourself.`);
    // Kept from an earlier build (manager-profiles.js): the same words it showed, never a number.
    if (profile.anchors.subjective === "some" || profile.anchors.subjective === "strong") lines.push(profile.note ? `Your note: ${profile.note}` : "You marked other leanings; weigh those yourself.");
    if (b === "longShot") {
      const best = a.basis.slice().sort((x, y) => y.gain - x.gain)[0];
      lines.push(best && best.gain < 0 ? "They lose on every view you marked, so this needs them to value these players more than any of those views do."
        : `This needs them to lean on ${best ? ANCHOR_WORDS[best.anchor] : "the trade charts"} more than you marked.`);
    }
    if (profile.confidence === "low") lines.push("You marked this profile as a guess.");
    return lines;
  }

  // The row's roster warnings, per team: {ours: [words], theirs: [words]}; both empty when every check ran and passed.
  // ours.label "partial" means construction failed for one or both teams; the row keeps only their side's result, so ours
  // comes from fullFit(row) (opportunities.js) when it is given. Without it, ours says it could not be told apart.
  const issuesText = c => (c.issues || []).join("; ") || "issue";
  function health(row, fullFit) {
    const ours = [];
    const theirs = [];
    if (!row.ours) {
      ours.push("roster fit not judged");
      theirs.push("roster fit not judged");
    } else {
      const their = row.theirs && row.theirs.construction;
      if (!their) theirs.push("roster construction not judged");
      else if (!their.ok) theirs.push(`roster construction: ${issuesText(their)}`);
      if (row.ours.label === "partial") {
        let mine = null;
        try { mine = fullFit ? (fullFit(row) || {}).myConstruction || null : null; } catch (error) { mine = null; }
        if (mine) { if (!mine.ok) ours.push(`roster construction: ${issuesText(mine)}`); }
        else ours.push(their && !their.ok ? "roster construction not checked apart from theirs" : "roster construction issue");
      }
    }
    if (row.partial) theirs.push("partial roster");
    return {ours, theirs};
  }

  // Win for the reader: DDF gain shows above 0.0 and our own fit is not force.
  const isWin = row => finite(row.edge) && shown(row.edge) > 0 && !(row.ours && row.ours.label === "force");
  const order = (x, y) => y.ourGain - x.ourGain || (y.share - x.share) || (x.id < y.id ? -1 : x.id > y.id ? 1 : 0);

  // opts: {rows (opportunities rows), book, ws, allRows, profiles (manager-profiles.js API), fullFit (optional, opportunities.js)}.
  // Returns {recommendations, stretch, counts: {considered, excluded, notWin, noAppeal, hidden}}.
  function build(opts) {
    const P = opts.profiles;
    const eligible = new Map(P.eligibleOpponents(opts.book, opts.ws).map(r => [r.teamId, r]));
    const curve = draftCurve(opts.allRows);
    const out = {recommendations: [], stretch: [], counts: {considered: 0, excluded: 0, notWin: 0, noAppeal: 0, hidden: 0}};
    (opts.rows || []).forEach(row => {
      out.counts.considered += 1;
      const who = eligible.get(String(row.opponentId));
      if (!who) { out.counts.excluded += 1; return; }
      if (!isWin(row)) { out.counts.notWin += 1; return; }
      const gains = anchorGains(row, curve);
      const a = appeal(who.profile, gains);
      const sent = sum(row.receive, ddf);
      const judged = band(a.gain, sent);
      if (!judged.band) { out.counts.noAppeal += 1; return; }
      if (judged.band === "hidden") { out.counts.hidden += 1; return; }
      const rec = {id: row.id, opponentId: row.opponentId, opponent: who.name, give: row.give, receive: row.receive, ourGain: row.edge,
        theirGain: a.gain, share: judged.share, band: judged.band, likelihood: LABEL[judged.band], basis: a.basis, fallback: a.fallback,
        gains, fit: row.overall || null, health: health(row, opts.fullFit), why: explain(who.profile, a, gains, judged.band),
        sources: a.basis.map(x => ({anchor: x.anchor, ...SOURCES[x.anchor]}))};
      (judged.band === "longShot" ? out.stretch : out.recommendations).push(rec);
    });
    out.recommendations.sort(order);
    out.stretch.sort(order);
    return out;
  }

  // Everything the Trade ideas card shows for one idea, as text. manager-recs-ui.js draws exactly this and redraws when it
  // changes, so a rename, a value-only update or a new warning can never leave a stale row on screen.
  const names = list => list.map(p => p.name).join(" + ") || "nobody";
  const gainText = n => `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(1)}`;
  function view(rec) {
    const sides = [];
    if (rec.health.ours.length) sides.push(`Your side: ${rec.health.ours.join("; ")}.`);
    if (rec.health.theirs.length) sides.push(`${rec.opponent}'s side: ${rec.health.theirs.join("; ")}.`);
    const sources = rec.sources.map(s => `${s.label} (${s.status})`).join("; ");
    return {id: rec.id, band: rec.band, opponent: rec.opponent, likelihood: rec.likelihood, gain: `You gain ${gainText(rec.ourGain)}`,
      give: `You give ${names(rec.give)}.`, receive: `You get ${names(rec.receive)}.`, health: sides.length ? `Roster check: ${sides.join(" ")}` : "",
      why: rec.why.slice(), sources: `Your gain is in DDF Value. Their side judged on: ${sources || "nothing available"}.`};
  }

  const api = {OUR_KEY, WEIGHT, BANDS, LABEL, SOURCES, draftCurve, draftValue, anchorGains, appeal, band, explain, health, isWin, build, view};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueManagerRecs = api;
})(typeof window !== "undefined" ? window : globalThis);
