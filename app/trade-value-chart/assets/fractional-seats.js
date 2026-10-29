/**
 * Fractional flex and bench seats (JEG-1334, part of JEG-1333).
 *
 * Decision: Jeremy, 2026-10-29, "Go with B" (JEG-1286; docs/decisions.md
 * "JEG-1286: fractional flex and bench seats (option B)").
 *
 * JS twin of pipelines/lib/fractional_seats.py; tests/test_fractional_seats.py
 * holds the two equal to 1e-12. Each flex and bench candidate holds
 * Phi((score - tau) / sigma) of a seat, tau set so the shares add up to the
 * seats; the fractional counts become a weighted mix of whole allocations.
 * sigma = 0 gives today's single allocation. Nothing calls this yet
 * (JEG-1335 wires it into vpAllocate).
 *
 * The bench discount is the caller's: benchDiscount(starters, teams) returns
 * disc(pos, k), so its one definition stays with the bench rule (JEG-556).
 *
 * PURE: no module state, no DOM.
 */
(function (root) {
  "use strict";

  var POSITIONS = ["QB", "RB", "WR", "TE"];
  var PRUNE = 1e-3;
  var BISECT = 200;

  // erf to double precision (same series as esErf in value-model.js).
  function erf(x) {
    if (x === 0) return 0;
    var ax = Math.abs(x);
    if (ax >= 6) return x > 0 ? 1 : -1;
    var term = ax, sum = ax, x2 = ax * ax;
    for (var n = 1; n < 500; n += 1) {
      term *= 2 * x2 / (2 * n + 1);
      sum += term;
      if (term < sum * 1e-17) break;
    }
    var r = 2 / Math.sqrt(Math.PI) * Math.exp(-x2) * sum;
    if (r > 1) r = 1;
    return x > 0 ? r : -r;
  }

  function phi(z) { return 0.5 * (1 + erf(z / Math.SQRT2)); }

  function addTo(out, p, v) { out[p] = (out[p] || 0) + v; }

  // items: [[pos, score, sigma]] in tie-break order. Returns {pos: seats}.
  function softSelect(items, n) {
    var out = {};
    n = Math.trunc(n);
    if (n <= 0 || !items.length) return out;
    var i;
    if (n >= items.length) {
      for (i = 0; i < items.length; i += 1) addTo(out, items[i][0], 1);
      return out;
    }
    var allZero = true, anyZero = false, gmax = -Infinity, smin = Infinity, smax = -Infinity;
    for (i = 0; i < items.length; i += 1) {
      var g = +items[i][2], s = +items[i][1];
      if (g > 0) allZero = false; else anyZero = true;
      if (g > gmax) gmax = g;
      if (s < smin) smin = s;
      if (s > smax) smax = s;
    }
    if (allZero) {
      var ranked = items.map(function (_x, j) { return j; });
      ranked.sort(function (a, b) {
        var d = (+items[b][1]) - (+items[a][1]);
        return d !== 0 ? d : a - b;
      });
      for (i = 0; i < n; i += 1) addTo(out, items[ranked[i]][0], 1);
      return out;
    }
    if (anyZero) throw new Error("softSelect: sigma must be all zero or all positive");
    var lo = smin - 50 * gmax - 1, hi = smax + 50 * gmax + 1, tau, tot;
    for (var it = 0; it < BISECT; it += 1) {
      tau = 0.5 * (lo + hi);
      tot = 0;
      for (i = 0; i < items.length; i += 1) tot += phi((+items[i][1] - tau) / (+items[i][2]));
      if (tot > n) lo = tau; else hi = tau;
    }
    tau = 0.5 * (lo + hi);
    for (i = 0; i < items.length; i += 1) addTo(out, items[i][0], phi((+items[i][1] - tau) / (+items[i][2])));
    tot = 0;
    var keys = Object.keys(out);
    // Sum in insertion order, as Python does.
    for (i = 0; i < keys.length; i += 1) tot += out[keys[i]];
    if (tot <= 0) return out;
    var scaled = {};
    for (i = 0; i < keys.length; i += 1) scaled[keys[i]] = out[keys[i]] * n / tot;
    return scaled;
  }

  // Fractional counts (summing to a whole number) to [[weight, counts]].
  function decompose(frac, positions) {
    positions = positions || POSITIONS;
    var fl = {}, f = {}, tot = 0, p, j;
    positions.forEach(function (q) {
      var v = +(frac[q] || 0);
      fl[q] = Math.floor(v + 1e-12);
      f[q] = Math.max(0, v - fl[q]);
    });
    for (j = 0; j < positions.length; j += 1) tot += f[positions[j]];
    var k = Math.floor(tot + 0.5);
    if (k === 0) return [[1, Object.assign({}, fl)]];
    var scale = k / tot, ends = {}, c = 0;
    for (j = 0; j < positions.length; j += 1) {
      p = positions[j];
      ends[p] = [c, c + f[p] * scale];
      c += f[p] * scale;
    }
    var set = {0: 0, 1: 1};
    positions.forEach(function (q) { set[ends[q][0] % 1] = ends[q][0] % 1; set[ends[q][1] % 1] = ends[q][1] % 1; });
    var pts = Object.keys(set).map(function (key) { return set[key]; }).sort(function (a, b) { return a - b; });
    var got = {}, order = [];
    for (j = 0; j + 1 < pts.length; j += 1) {
      var u0 = pts[j], u1 = pts[j + 1];
      if (u1 - u0 < 1e-12) continue;
      var u = 0.5 * (u0 + u1), sel = Object.assign({}, fl);
      positions.forEach(function (q) {
        var a = ends[q][0], b = ends[q][1];
        for (var m = 0; m < k; m += 1) {
          if (a <= u + m && u + m < b) { sel[q] += 1; break; }
        }
      });
      var key = positions.map(function (q) { return sel[q]; }).join(",");
      if (!(key in got)) { got[key] = 0; order.push(key); }
      got[key] += u1 - u0;
    }
    return order.map(function (key) {
      var parts = key.split(",").map(Number), counts = {};
      positions.forEach(function (q, idx) { counts[q] = parts[idx]; });
      return [got[key], counts];
    });
  }

  function hardBench(remaining, score, totalBench, disc, positions, posRank) {
    var counts = {};
    positions.forEach(function (p) { counts[p] = 0; });
    for (var seat = 0; seat < Math.max(0, Math.trunc(totalBench)); seat += 1) {
      var best = -1e18, winner = null;
      for (var j = 0; j < positions.length; j += 1) {
        var p = positions[j], cands = remaining[p] || [], k = counts[p];
        if (k >= cands.length) continue;
        var eff = Math.max(0, +(score[cands[k]] || 0)) * disc(p, k);
        if (eff > best || (eff === best && winner !== null && posRank[p] < posRank[winner])) {
          best = eff; winner = p;
        }
      }
      if (winner === null || best <= 0) break;
      counts[winner] += 1;
    }
    return counts;
  }

  function cmpId(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  // VP-2.2 with fractional flex and bench seats: [[weight, allocation]].
  // opts: {teams, dedicated, superflex, flexEligible, flexSeats, benchSeats,
  //        order, score, sigma, benchDiscount, positions?, softBench?, prune?}
  function allocationMix(opts) {
    var positions = opts.positions || POSITIONS;
    var posRank = {};
    positions.forEach(function (p, j) { posRank[p] = j; });
    var t = Math.trunc(opts.teams), d = {}, sf = {};
    positions.forEach(function (p) {
      d[p] = Math.trunc((opts.dedicated || {})[p] || 0);
      sf[p] = Math.trunc((opts.superflex || {})[p] || 0);
    });
    var sigma = +opts.sigma, order = opts.order, score = opts.score;
    var softBench = opts.softBench !== false;
    var prune = opts.prune === undefined ? PRUNE : opts.prune;
    var fitems = [];
    positions.forEach(function (p) {
      if (opts.flexEligible.indexOf(p) < 0) return;
      (order[p] || []).forEach(function (id, idx) {
        if (idx >= d[p] + sf[p]) fitems.push([posRank[p], id, p]);
      });
    });
    fitems.sort(function (a, b) { return a[0] - b[0] || cmpId(a[1], b[1]); });
    var items = fitems.map(function (x) { return [x[2], +score[x[1]], sigma]; });
    var fxf = softSelect(items, Math.trunc(opts.flexSeats));
    var fxIn = {};
    positions.forEach(function (p) { fxIn[p] = fxf[p] || 0; });
    var out = [];
    decompose(fxIn, positions).forEach(function (fv) {
      var wv = fv[0], fx = fv[1], starters = {}, remaining = {};
      positions.forEach(function (p) {
        starters[p] = d[p] + sf[p] + fx[p];
        remaining[p] = (order[p] || []).slice(starters[p]);
      });
      var disc = opts.benchDiscount(starters, t), verts;
      if (!softBench || sigma <= 0) {
        verts = [[1, hardBench(remaining, score, opts.benchSeats, disc, positions, posRank)]];
      } else {
        var bitems = [];
        positions.forEach(function (p) {
          remaining[p].forEach(function (id, k) {
            var dk = +disc(p, k), eff = Math.max(0, +(score[id] || 0)) * dk;
            if (eff > 0 && dk > 0) bitems.push([p, eff, sigma * dk]);
          });
        });
        var nb = Math.min(Math.trunc(opts.benchSeats), bitems.length);
        var bf = softSelect(bitems, nb), bIn = {};
        positions.forEach(function (p) { bIn[p] = bf[p] || 0; });
        verts = decompose(bIn, positions);
      }
      verts.forEach(function (bv) {
        var a = {};
        positions.forEach(function (p) {
          var b = Math.trunc(bv[1][p] || 0);
          a[p] = {dedicated: d[p], superflex: sf[p], flex: fx[p], bench: b,
            starters: starters[p], rostered: starters[p] + b};
        });
        out.push([wv * bv[0], a]);
      });
    });
    var kept = out.filter(function (x) { return x[0] >= prune; });
    if (!kept.length) {
      kept = [out.reduce(function (m, x) { return x[0] > m[0] ? x : m; })];
    }
    var tot = 0;
    kept.forEach(function (x) { tot += x[0]; });
    return kept.map(function (x) { return [x[0] / tot, x[1]]; });
  }

  function expectedCounts(mix, positions) {
    positions = positions || POSITIONS;
    var fields = ["dedicated", "superflex", "flex", "bench", "starters", "rostered"], out = {};
    positions.forEach(function (p) {
      out[p] = {};
      fields.forEach(function (fname) {
        var s = 0;
        mix.forEach(function (x) { s += x[0] * x[1][p][fname]; });
        out[p][fname] = s;
      });
    });
    return out;
  }

  var api = {
    POSITIONS: POSITIONS,
    PRUNE: PRUNE,
    phi: phi,
    softSelect: softSelect,
    decompose: decompose,
    allocationMix: allocationMix,
    expectedCounts: expectedCounts
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FractionalSeats = api;
})(this);
