// Trade Value v2 — Compare a trade (Figma frames 07 / 08).
//
// Pure functions, no DOM: given the engine's own rows (TradeValueCurveControls
// .getAllRows()) for the players on each side and the series to compare, give
// one row per series:
//
//   net = sum(receive) − sum(give)        for that exact series only
//
// Frame 22 rule: each row is one exact series (publisher × method); there is no
// blended score across series. The verdict (JEG-469) reads ONE series and only
// names which other complete series point the other way. A player with
// no value in a series makes that series' row incomplete: no sums, no net,
// "—" plus a reason, never a 0 standing in for the missing value. A real 0
// (at or below that series' waiver line) is a value and counts.
(function (root) {
  "use strict";

  const finite = value => typeof value === "number" && Number.isFinite(value);
  // JEG-912: a rounding residue never shows a sign ("-0.0" is "+0.0").
  const fmtNet = n => { const text = n.toFixed(1); return text === "-0.0" ? "+0.0" : (n >= 0 ? "+" : "") + text; };

  // giveRows / receiveRows: the engine rows of the players on each side (a
  // player the engine has no row for comes in with empty values, so it is
  // missing everywhere). series: series keys to compare, in display order.
  function compareTrade(giveRows, receiveRows, series) {
    const rows = series.map(key => {
      const missing = [];
      let giveSum = 0;
      let receiveSum = 0;
      giveRows.forEach(row => {
        const value = row.values ? row.values[key] : null;
        if (finite(value)) giveSum += value;
        else missing.push({row, side: "give"});
      });
      receiveRows.forEach(row => {
        const value = row.values ? row.values[key] : null;
        if (finite(value)) receiveSum += value;
        else missing.push({row, side: "receive"});
      });
      if (missing.length) return {key, give: null, receive: null, net: null, missing};
      return {key, give: giveSum, receive: receiveSum, net: receiveSum - giveSum, missing};
    });
    return {rows};
  }

  // One side's total in one series (frame 07: "<series> total" under each side).
  // Any player without a value makes the total incomplete: null plus who is missing.
  function sideTotal(rows, key) {
    const missing = rows.filter(row => !finite(row.values ? row.values[key] : null));
    if (!rows.length || missing.length) return {key, total: null, missing};
    return {key, total: rows.reduce((sum, row) => sum + row.values[key], 0), missing};
  }

  // Frame 22 #15, the trade story, read only from complete rows (no new numbers):
  //   contrast  one publisher's DDA and Indexed nets point opposite ways (same week);
  //   agree     every complete row points the same way;
  //   split     complete rows point different ways (different publishers);
  //   incomplete no row is complete.
  // A net that shows as 0.0 points neither way. meta(key) -> {publisher, method, week}.
  function tradeStory(rows, meta) {
    const complete = rows.filter(row => row.net !== null);
    if (!rows.length) return {kind: null};
    if (!complete.length) return {kind: "incomplete"};
    const sign = row => (Math.abs(row.net) < 0.05 ? 0 : row.net > 0 ? 1 : -1);
    const byPublisher = new Map();
    complete.forEach(row => {
      const m = meta(row.key);
      if (m.method === "vorp") return;
      if (!byPublisher.has(m.publisher)) byPublisher.set(m.publisher, {});
      byPublisher.get(m.publisher)[m.method] = {row, week: m.week};
    });
    for (const [publisher, pair] of byPublisher) {
      if (!pair.dda || !pair.indexed || pair.dda.week !== pair.indexed.week) continue;
      const a = sign(pair.dda.row);
      const b = sign(pair.indexed.row);
      if (a && b && a !== b) return {kind: "contrast", publisher, dda: pair.dda.row, indexed: pair.indexed.row};
    }
    // Which series point which way, so the copy can name them (Jeremy, 2026-10-08).
    const keysWhere = want => complete.filter(row => sign(row) === want).map(row => row.key);
    const upKeys = keysWhere(1);
    const downKeys = keysWhere(-1);
    const evenKeys = keysWhere(0);
    const up = upKeys.length;
    const down = downKeys.length;
    const even = evenKeys.length;
    const counts = {up, down, even, total: complete.length, upKeys, downKeys, evenKeys};
    if (complete.length < 2) return {kind: "single", ...counts};
    if ((up && !down && !even) || (down && !up && !even) || (even && !up && !down)) return {kind: "agree", ...counts};
    return {kind: "split", ...counts};
  }

  const signOf = net => (Math.abs(net) < 0.05 ? 0 : net > 0 ? 1 : -1);   // 0.0 as shown points neither way

  // JEG-468 waterfall for one series: the same sums as compareTrade, shown as steps.
  // 0 → one step down per player given (largest first) → one step up per player
  // received (largest first). A player without a value is a "missing" step that
  // moves nothing; every step after it is a partial running total, and the row
  // has no net (no landing). lo / hi: the cumulative extent, 0 included.
  function waterfall(giveRows, receiveRows, key) {
    const valueOf = row => (row.values ? row.values[key] : null);
    const ordered = rows => {
      const priced = rows.map((row, i) => ({row, i, value: valueOf(row)})).filter(s => finite(s.value));
      priced.sort((a, b) => b.value - a.value || a.i - b.i);
      return {priced, missing: rows.filter(row => !finite(valueOf(row)))};
    };
    const steps = [];
    let running = 0;
    let partial = false;
    [["give", giveRows, -1], ["receive", receiveRows, 1]].forEach(([side, rows, dir]) => {
      const {priced, missing} = ordered(rows);
      priced.forEach(({row, value}) => {
        const start = running;
        running += dir * value;
        steps.push({side, row, value, delta: dir * value, start, end: running, running, partial, missing: false});
      });
      missing.forEach(row => {
        partial = true;
        steps.push({side, row, value: null, delta: null, start: running, end: running, running: null, partial, missing: true});
      });
    });
    const sums = compareTrade(giveRows, receiveRows, [key]).rows[0];
    const marks = [0].concat(...steps.map(s => [s.start, s.end]), sums.net === null ? [] : [sums.net]);
    return {key, steps, give: sums.give, receive: sums.receive, net: sums.net, complete: sums.net !== null,
      lo: Math.min(...marks), hi: Math.max(...marks)};
  }

  // One shared scale for a table of waterfalls: the largest cumulative extent across rows.
  function waterfallScale(waterfalls) {
    const lo = Math.min(0, ...waterfalls.map(w => w.lo));
    const hi = Math.max(0, ...waterfalls.map(w => w.hi));
    return {lo, hi: hi > lo ? hi : lo + 1};
  }

  // JEG-469 verdict (Jeremy, 2026-10-08): one series decides win / lose; the other
  // complete series that see it the other way are the selling point. Incomplete
  // rows never count. rows: compareTrade rows; key: the verdict series.
  function tradeVerdict(rows, key) {
    const head = rows.find(row => row.key === key);
    if (!head) return {kind: null, key};
    const others = rows.filter(row => row.key !== key);
    const complete = others.filter(row => row.net !== null);
    const incompleteKeys = others.filter(row => row.net === null).map(row => row.key);
    const keysWhere = want => complete.filter(row => signOf(row.net) === want).map(row => row.key);
    const base = {key, upKeys: keysWhere(1), downKeys: keysWhere(-1), evenKeys: keysWhere(0), incompleteKeys, others: complete.length};
    if (head.net === null) return {kind: "incomplete", net: null, missing: head.missing, againstKeys: [], agreeKeys: [], ...base};
    const s = signOf(head.net);
    const kind = s > 0 ? "win" : s < 0 ? "lose" : "even";
    const againstKeys = s > 0 ? base.downKeys : s < 0 ? base.upKeys : [];
    const agreeKeys = s > 0 ? base.upKeys : s < 0 ? base.downKeys : base.evenKeys;
    return {kind, net: head.net, againstKeys, agreeKeys, missing: [],
      allAgree: complete.length > 0 && agreeKeys.length === complete.length, ...base};
  }

  // JEG-505 headline (contract CT-02). Two plain answers with a confidence level:
  //   propose: "Should you propose or accept?" by DDF Value (JEG-841, JEG-863: DDF Value = projections).
  //            Yes when both say you win and the DDF margin is 5%+ of the value traded;
  //            confidence from the projections margin (High when projections also 5%+, Low when even).
  //            Unclear when they split or the margin is under 5%.
  //            The chart agreement count stays in the reasons for honesty ("0 of N agree").
  //   accept:  "Will they accept?" from the published value charts (chartKeys): the share of complete
  //            charts on which the other manager wins or breaks even (our net <= 0, as shown).
  //            Likely at two thirds or more, Unlikely at one third or less, otherwise Toss-up.
  // The level is High / Medium / Low here; the page names it for what it measures (JEG-895, v2.js
  // LEVEL_LABELS: "Our value: strong / moderate / weak", "Charts agree: strongly / mostly / weakly"):
  //   propose  High when margin 5%+, Medium when DDF Value agrees but margin
  //            under 5%, Low when DDF Value is even or missing;
  //   accept   agreement: >= 75% of charts on the answer's side = High, >= 60% = Medium, else Low;
  //   few sources fewer than 3 complete sources caps at Medium;
  //   charts   propose "High" needs 3 or more trade charts on the answer's side, else Medium (JEG-950);
  //   data     a low-confidence (one-source) DDF Value in the trade lowers the propose line one level.
  const THIN_MARGIN = 0.05;
  const MIN_CHARTS_FOR_HIGH = 3;
  const LEVELS = ["Low", "Medium", "High"];
  const lowered = level => LEVELS[Math.max(0, LEVELS.indexOf(level) - 1)];
  const capped = (level, cap) => LEVELS[Math.min(LEVELS.indexOf(level), LEVELS.indexOf(cap))];
  function tradeHeadlines(rows, key, ctx) {
    const head = rows.find(row => row.key === key);
    const traded = head && head.net !== null ? head.give + head.receive : null;
    const thinFlag = traded !== null && (traded <= 0 || Math.abs(head.net) < THIN_MARGIN * traded);
    const margin = traded > 0 ? Math.abs(head.net) / traded : null;
    const levelFor = share => (share >= 0.75 ? "High" : share >= 0.6 ? "Medium" : "Low");
    // Chart agreement count (kept for honesty reasons and the sub-line, not for the answer).
    const v = tradeVerdict(rows, key);
    const chartSet = new Set((ctx && ctx.chartKeys) || []);
    const chartAgree = v.agreeKeys ? v.agreeKeys.filter(k => chartSet.has(k)).length : 0;
    const chartTotal = v.others != null ? rows.filter(row => chartSet.has(row.key) && row.net !== null).length : 0;
    // Line 1: should you propose or accept (JEG-841: decided by DDF Value).
    const deal = ctx && ctx.deal;
    let propose;
    if (!head || v.kind === null || v.kind === "incomplete") {
      propose = {answer: null, confidence: null, reasons: []};
    } else if (!deal || deal.kind !== "read") {
      // No complete deal read (projections or market missing): fall back to Unclear.
      const reasons = ["not enough data for a deal read"];
      propose = {answer: "Unclear", confidence: "Low", agree: chartAgree, of: chartTotal, margin, reasons};
    } else {
      const reasons = [];
      const vSide = deal.value.side;    // "win" | "lose" | "even"
      const pSide = deal.projections && deal.projections.net !== null ? deal.projections.side : null;
      const pNet = deal.projections && deal.projections.net !== null ? deal.projections.net : null;
      const pTraded = deal.projections && deal.projections.give !== null ? deal.projections.give + deal.projections.receive : null;
      const pMargin = pTraded > 0 && pNet !== null ? Math.abs(pNet) / pTraded : null;
      let answer, level;
      if (vSide === "win" && pSide === "win" && !thinFlag) {
        // DDF Value says you win, margin 5%+.
        answer = "Yes";
        level = pMargin !== null && pMargin >= THIN_MARGIN ? "High" : pSide === "win" ? "Medium" : "Low";
        reasons.push(`DDF Value agrees (${fmtNet(pNet)})`);
      } else if (vSide === "lose" && pSide === "lose" && !thinFlag) {
        answer = "No";
        level = pMargin !== null && pMargin >= THIN_MARGIN ? "High" : pSide === "lose" ? "Medium" : "Low";
        reasons.push(`DDF Value agrees (${fmtNet(pNet)})`);
      } else {
        answer = "Unclear";
        level = "Low";
        if (thinFlag) reasons.push("the margin is under 5% of the value traded");
        if (pSide === null) reasons.push("DDF Value cannot score this trade");
        // JEG-863 + JEG-930: DDF Value = projections (JEG-804), so pSide !== vSide is dead; kept as defensive else.
        else reasons.push(`DDF Value agrees (${fmtNet(pNet)})`);
      }
      if (ctx && ctx.lowConfidence) { level = lowered(level); reasons.push("a one-source DDF Value is in this trade"); }
      // JEG-950 (Jeremy, 2026-10-23 and 2026-10-25): 3+ trade charts on the answer's side keep the level,
      // 2 cap it at Medium, 1 or none cap it at Low. No extra reason line:
      // the "N of M charts agree" reason line says why (keeps Compare's height).
      if (answer === "Yes" || answer === "No") {
        if (chartAgree < MIN_CHARTS_FOR_HIGH - 1) level = capped(level, "Low");
        else if (chartAgree < MIN_CHARTS_FOR_HIGH) level = capped(level, "Medium");
      }
      // Honesty: always show the chart agreement count (rendered as its own line, JEG-895).
      reasons.push(`${chartAgree} of ${chartTotal} charts agree`);
      propose = {answer, confidence: level, agree: chartAgree, of: chartTotal, margin, reasons};
    }
    // Line 2: will they accept, from the published charts.
    const charts = rows.filter(row => chartSet.has(row.key) && row.net !== null);
    let accept;
    if (!charts.length) {
      accept = {answer: null, confidence: null, reasons: []};
    } else {
      const yes = charts.filter(row => signOf(row.net) <= 0).length;
      const share = yes / charts.length;
      const answer = share >= 2 / 3 ? "Likely" : share <= 1 / 3 ? "Unlikely" : "Toss-up";
      const same = answer === "Likely" ? yes : answer === "Unlikely" ? charts.length - yes : Math.max(yes, charts.length - yes);
      const agreement = same / charts.length;
      let level = levelFor(agreement);
      const reasons = [`${yes} of ${charts.length} charts have the other manager winning or even`];
      if (charts.length < 3) { level = capped(level, "Medium"); reasons.push("fewer than 3 charts"); }
      if (thinFlag) { level = "Low"; reasons.push("the margin is under 5% of the value traded"); }
      accept = {answer, confidence: level, yes, of: charts.length, reasons};
    }
    return {propose, accept};
  }

  // JEG-469 empty state: a sample 2-for-2 from the top `pool` players (by the verdict
  // series) that every series prices. Prefers a trade the verdict series calls a win
  // that the most other series call a loss (the page's point), then the smallest win.
  // Deterministic for the same rows. Returns {give, receive} rows or null.
  function pickExample(rows, keys, key, pool = 12) {
    const all = keys.includes(key) ? keys : keys.concat(key);
    const top = rows.filter(row => row.values && all.every(k => finite(row.values[k])))
      .sort((a, b) => b.values[key] - a.values[key] || String(a.player_key).localeCompare(String(b.player_key)))
      .slice(0, pool);
    if (top.length < 4) return null;
    let best = null;
    for (let a = 0; a < top.length; a++) for (let b = a + 1; b < top.length; b++) {
      for (let c = 0; c < top.length; c++) for (let d = c + 1; d < top.length; d++) {
        if (c === a || c === b || d === a || d === b) continue;
        const give = [top[a], top[b]];
        const receive = [top[c], top[d]];
        const v = tradeVerdict(compareTrade(give, receive, all).rows, key);
        if (v.kind !== "win" || v.net < 1) continue;
        const score = [v.againstKeys.length, -v.net];
        if (!best || score[0] > best.score[0] || (score[0] === best.score[0] && score[1] > best.score[1])) best = {give, receive, score};
      }
    }
    return best ? {give: best.give, receive: best.receive} : {give: [top[1], top[3]], receive: [top[0], top[2]]};
  }

  // ---------- JEG-487 deal read (contract CT-08) ----------
  // Three nets, each answering one question:
  //   V  DDF Value net              (ddf_value)             are you getting real value?
  //   M  Trade chart average net    (mean of compared chart rows)  does the market think you are winning?
  //   P  DDF Value (projections) net (ddf_value_projections) is the value backed by projected production?
  // JEG-832: M is the plain mean of the per-chart rescaled nets (the same rows Compare shows), NOT
  // the DDF Value · trade charts blend (which equals DDF Value when projections are held). When fewer
  // than MIN_DEAL_CHARTS charts price every player the market card says "not enough charts".
  // Side of a net: win when it is at least max(1, 3% of the average side total of that series), lose when it
  // is at most the negative of that, otherwise even. The read is a fixed 9-cell table on (V, M): a manager who
  // trades off the market sees M's loss as their win, so V win with M lose is the arbitrage; V lose with M win
  // is the trap. P is a one-sentence production check against V. Deterministic: no model, no blending.
  const DEAL_KEYS = {value: "ddf_value", market: "ddf_value_charts", projections: "ddf_value_projections"};
  const MIN_DEAL_CHARTS = 3;
  const DEAL_SIDES = ["win", "even", "lose"];
  const DEAL_READS = {
    "win|win": {title: "Win, but a hard sell", action: "Propose, expect pushback",
      text: "DDF Value says you come out ahead and the trade charts agree, so the other manager will likely see a loss."},
    "win|even": {title: "Value win at a fair market price", action: "Propose it",
      text: "DDF Value says you come out ahead and the trade charts call it fair, so the other manager has little reason to refuse."},
    // JEG-950 (Jeremy, 2026-10-26): the title is the verdict; the live read's text is the real market gap
    // (marketGapText, below). The static text stays for the 3x3 grid, where there is no single net to show.
    "win|lose": {title: "DDF Value likes it. The market doesn't.", action: "",
      text: "DDF Value says you come out ahead while the trade charts say you lose, so the other manager will likely see it as their win."},
    "even|win": {title: "Even on value, a hard sell", action: "Counter for more",
      text: "DDF Value calls it even but the trade charts say you win, so the other manager will likely see a loss."},
    "even|even": {title: "A fair trade", action: "Your call",
      text: "DDF Value and the trade charts both call it even."},
    "even|lose": {title: "Even on value, an easy sell", action: "Fine to propose",
      text: "DDF Value calls it even while the trade charts say you lose, so the other manager will likely see a win for them."},
    "lose|win": {title: "Trap", action: "Pass",
      text: "The trade charts say you win but DDF Value says you lose: it looks good at market prices, not on value."},
    "lose|even": {title: "An overpay", action: "Pass or counter",
      text: "DDF Value says you lose and the trade charts call it fair."},
    "lose|lose": {title: "A loss on both", action: "Pass",
      text: "DDF Value and the trade charts both say you lose."}
  };
  const sideOf = (net, give, receive) => {
    const threshold = Math.max(1, 0.03 * ((give + receive) / 2));
    return {side: net >= threshold ? "win" : net <= -threshold ? "lose" : "even", threshold};
  };
  // JEG-886: the Deal read must not contradict "Will they accept?" (tradeHeadlines), which counts the
  // charts on which the other manager wins or breaks even (net <= 0 as shown). Each market column's copy
  // assumes one answer to that question: charts win for you -> Unlikely; charts even or lose -> Likely.
  // An average can hide the per-chart disagreement (+0.5, -7.2, +9.1 average to +0.8 "even" while only
  // 1 of 3 charts has the other manager winning). When the count the headline uses does not match the
  // column's assumption, the read names the split instead of the cell copy. The cell itself (the grid
  // outline and the card's side) stays the average's: only the title, action and text change.
  const DEAL_SPLIT_ACCEPT = {win: "Unlikely", even: "Likely", lose: "Likely"};
  const acceptAnswer = (yes, of) => (yes / of >= 2 / 3 ? "Likely" : yes / of <= 1 / 3 ? "Unlikely" : "Toss-up");
  const SPLIT_READS = {
    win: {title: "Value win, but the trade charts split", action: "Propose it"},
    even: {title: "Even on value, and the trade charts split", action: "Your call"},
    lose: {title: "A loss on value, and the trade charts split", action: "Pass or counter"}
  };
  const fmtSigned = n => (Math.abs(n) < 0.05 ? "0.0" : (n < 0 ? "−" : "+") + Math.abs(n).toFixed(1));   // the minus sign the cards use
  function splitRead(vSide, charts) {
    const said = {win: "DDF Value says you come out ahead", even: "DDF Value calls it even", lose: "DDF Value says you lose"}[vSide];
    const range = charts.min < 0 && charts.max > 0
      ? `disagree with each other by ${(charts.max - charts.min).toFixed(1)} points (${fmtSigned(charts.min)} to ${fmtSigned(charts.max)})`
      : `call it close (${fmtSigned(charts.min)} to ${fmtSigned(charts.max)})`;
    return {...SPLIT_READS[vSide],
      text: `${said}, but the trade charts ${range}: ${charts.yes} of ${charts.of} have the other manager winning or even, so acceptance is uncertain.`};
  }
  // JEG-950 (Jeremy, 2026-10-26): the win|lose sub-line shows the real computed market gap, so the number
  // and the direction word always come from the market net, never hard-coded: "ahead" or "behind", "even"
  // at exactly zero. On the win|lose cell the market always has you behind, and that gap is why the other
  // manager is likely to accept, so the line says so instead of advising to close it (Jeremy, 2026-10-28:
  // the old "down ... Close the gap to land it." read like advice to give up more). One decimal.
  const marketGapWord = net => (net > 0 ? "ahead" : net < 0 ? "behind" : "even");
  const marketGapText = net => (net === 0 ? "The trade charts call it even."
    : net > 0 ? `The trade charts have you ${Math.abs(net).toFixed(1)} points ahead.`
      : `The trade charts have you ${Math.abs(net).toFixed(1)} points behind, so the other manager will likely see it as their win.`);
  // One production sentence: P's side against V's side.
  // JEG-1073: DDF Value is the trade charts again and the projections version is the alternate, so p !== v is a
  // live case (it was dead between JEG-804 and JEG-1073): the sentence says how the two differ.
  const PRODUCTION_SAYS = {win: "you come out ahead", even: "it is even", lose: "you lose"};
  function productionCheck(p, v) {
    if (p === v) return p === "win" ? "Projected production backs the value: DDF Value (projections) also says you come out ahead."
      : p === "lose" ? "Projected production backs the value: DDF Value (projections) also says you lose." : "Projected production backs the value: DDF Value (projections) also calls it even.";
    return `Projected production does not back the value: DDF Value says ${PRODUCTION_SAYS[v]}, but DDF Value (projections) says ${PRODUCTION_SAYS[p]}.`;
  }
  // JEG-832: chartKeys are the compared chart series (e.g. ["usatoday","fantasycalc","fantasypros"]).
  // The market net is the mean of each complete chart row's net, not the DDF blend.
  function dealRead(giveRows, receiveRows, chartKeys) {
    const vp = compareTrade(giveRows, receiveRows, [DEAL_KEYS.value, DEAL_KEYS.projections]).rows;
    const [v, p] = vp;
    const net = row => (row.net === null ? {net: null, give: null, receive: null, side: null, threshold: null, missing: row.missing}
      : {net: row.net, give: row.give, receive: row.receive, ...sideOf(row.net, row.give, row.receive), missing: []});
    // JEG-832: compute M from the mean of the per-chart rescaled nets.
    const chartRows = chartKeys && chartKeys.length ? compareTrade(giveRows, receiveRows, chartKeys).rows : [];
    const completeCharts = chartRows.filter(row => row.net !== null);
    let market;
    if (completeCharts.length < MIN_DEAL_CHARTS) {
      market = {net: null, give: null, receive: null, side: null, threshold: null, missing: [],
        chartCount: completeCharts.length, minCharts: MIN_DEAL_CHARTS, tooFew: true};
    } else {
      const avgNet = completeCharts.reduce((s, r) => s + r.net, 0) / completeCharts.length;
      const avgGive = completeCharts.reduce((s, r) => s + r.give, 0) / completeCharts.length;
      const avgRec = completeCharts.reduce((s, r) => s + r.receive, 0) / completeCharts.length;
      market = {net: avgNet, give: avgGive, receive: avgRec, ...sideOf(avgNet, avgGive, avgRec), missing: [],
        chartCount: completeCharts.length};
      // JEG-886: the same per-chart count "Will they accept?" uses, and the range the average hides.
      const nets = completeCharts.map(row => row.net);
      const yes = completeCharts.filter(row => signOf(row.net) <= 0).length;
      market.charts = {yes, of: completeCharts.length, accept: acceptAnswer(yes, completeCharts.length),
        min: Math.min(...nets), max: Math.max(...nets)};
      market.split = market.charts.accept !== DEAL_SPLIT_ACCEPT[market.side];
    }
    const out = {value: net(v), market, projections: net(p)};
    if (out.value.net === null) {
      return {kind: "incomplete", ...out, text: "No deal read yet: DDF Value has no value for at least one player in the trade."};
    }
    if (market.tooFew) {
      return {kind: "incomplete", ...out, text: `Not enough compared charts to read the market (${market.chartCount} of ${MIN_DEAL_CHARTS} needed).`};
    }
    const cellKey = `${out.value.side}|${out.market.side}`;
    const cell = market.split ? splitRead(out.value.side, market.charts) : DEAL_READS[cellKey];
    // JEG-950: on the win|lose cell the live read shows the market gap instead of the static grid explanation.
    const text = !market.split && cellKey === "win|lose" ? marketGapText(market.net) : cell.text;
    return {kind: "read", ...out, cell: cellKey, title: cell.title, action: cell.action, text,
      production: out.projections.net === null ? null : productionCheck(out.projections.side, out.value.side)};
  }

  // ---------- JEG-1191 rotating examples ----------
  // "Try a sample trade" becomes a short list of real trades, each judged by today's Deal read (dealRead): this
  // only chooses which trades to load, it adds no evaluation rule. The pool is the top EXAMPLE_POOL players by
  // DDF Value that DDF Value, DDF Value (projections) and every compared chart price; trades run 1-for-1 up to
  // 2-for-2. Candidates are ranked fewest players first, then by the slot's score, then by player keys, so the
  // same data always gives the same list. No player appears in two examples.
  const EXAMPLE_POOL = 36;
  const EXAMPLE_COUNT = 3;
  const SHAPES_BY_SIZE = [[2, [[1, 1]]], [3, [[1, 2], [2, 1]]], [4, [[2, 2]]]];
  function subsets(n, size) {
    const out = [];
    for (let a = 0; a < n; a++) {
      if (size === 1) out.push([a]);
      else for (let b = a + 1; b < n; b++) out.push([a, b]);
    }
    return out;
  }
  // slots: [{test(deal) -> score | null}]. select(lists) -> picks or null, where lists[i] is slot i's candidates,
  // ranked. Tiers are added smallest first and the walk stops at the first tier where select fills.
  function rankExamples(rows, chartKeys, slots, select, pool = EXAMPLE_POOL) {
    const need = [DEAL_KEYS.value, DEAL_KEYS.projections].concat(chartKeys || []);
    if (!chartKeys || chartKeys.length < MIN_DEAL_CHARTS) return [];
    const top = rows.filter(row => row.values && need.every(k => finite(row.values[k])))
      .sort((a, b) => b.values[DEAL_KEYS.value] - a.values[DEAL_KEYS.value] || String(a.player_key).localeCompare(String(b.player_key)))
      .slice(0, pool);
    const ddf = top.map(row => row.values[DEAL_KEYS.value]);
    const lists = slots.map(() => []);
    const tie = c => c.give.concat(c.receive).map(row => String(row.player_key)).join(",");
    for (const [size, shapes] of SHAPES_BY_SIZE) {
      for (const [g, r] of shapes) {
        const gives = subsets(top.length, g);
        const gets = subsets(top.length, r);
        for (const gi of gives) for (const ri of gets) {
          if (ri.some(i => gi.includes(i))) continue;
          // DDF Value must move by at least a point for any read to be a win or a loss (sideOf's floor).
          const vNet = ri.reduce((s, i) => s + ddf[i], 0) - gi.reduce((s, i) => s + ddf[i], 0);
          if (Math.abs(vNet) < 1) continue;
          const give = gi.map(i => top[i]);
          const receive = ri.map(i => top[i]);
          const deal = dealRead(give, receive, chartKeys);
          if (deal.kind !== "read") continue;
          slots.forEach((slot, i) => {
            const score = slot.test(deal);
            if (score !== null && score !== undefined) lists[i].push({give, receive, deal, size, score, slot: i});
          });
        }
      }
      lists.forEach(list => list.sort((a, b) => a.size - b.size || b.score - a.score || tie(a).localeCompare(tie(b))));
      const picks = select(lists);
      if (picks) return picks;
    }
    return select(lists, true) || [];
  }
  const keysOf = c => c.give.concat(c.receive).map(row => row.player_key);
  const disjoint = (c, used) => keysOf(c).every(k => !used.has(k));
  // JEG-1191 path A (Jeremy's pick, 2026-10-30): trades the market misses. Only the Deal read's arbitrage cell,
  // "DDF Value likes it. The market doesn't." (win|lose, the charts not split, so "Will they accept?" is
  // Likely), ranked by the DDF Value gain. Returns up to EXAMPLE_COUNT {give, receive, deal}; fewer than
  // EXAMPLE_COUNT means the page falls back to pickExample. isMarketMiss is the same test on any Deal read, so the
  // page's Example line can say so only while the current read still qualifies.
  const isMarketMiss = deal => Boolean(deal && deal.kind === "read" && deal.cell === "win|lose" && !deal.market.split);
  function pickMarketMisses(rows, chartKeys, count = EXAMPLE_COUNT, pool = EXAMPLE_POOL) {
    const slots = [{test: deal => (isMarketMiss(deal) ? deal.value.net : null)}];
    const select = (lists, last) => {
      const used = new Set();
      const picks = [];
      for (const c of lists[0]) {
        if (picks.length >= count) break;
        if (!disjoint(c, used)) continue;
        keysOf(c).forEach(k => used.add(k));
        picks.push({give: c.give, receive: c.receive, deal: c.deal});
      }
      return picks.length >= count || last ? picks : null;
    };
    return rankExamples(rows, chartKeys, slots, select, pool);
  }

  const api = {compareTrade, sideTotal, tradeStory, waterfall, waterfallScale, tradeVerdict, tradeHeadlines, THIN_MARGIN, pickExample,
    pickMarketMisses, isMarketMiss, EXAMPLE_COUNT, EXAMPLE_POOL,
    dealRead, DEAL_READS, DEAL_SIDES, DEAL_KEYS, MIN_DEAL_CHARTS, DEAL_SPLIT_ACCEPT, SPLIT_READS,
    marketGapWord, marketGapText};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTrade = api;
})(typeof window !== "undefined" ? window : globalThis);
