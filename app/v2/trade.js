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

  const api = {compareTrade, sideTotal, tradeStory, waterfall, waterfallScale, tradeVerdict, pickExample};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTrade = api;
})(typeof window !== "undefined" ? window : globalThis);
