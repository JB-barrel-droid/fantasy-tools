#!/usr/bin/env node
/**
 * JEG-242: independent second-language parity check for the three-view preview.
 *
 * Reads the vorp-views-preview.json payload and re-derives the Indexed display
 * map with independent JS arithmetic: indexed[k] === native[k] * 70 / peak.
 * Also verifies vorp/adj maps are finite-nonnegative, that indexed-excluded
 * sources carry an explicit reason (never a silent gap), and that publisher
 * native keys are a subset of VORP/Adjusted when AVG backstops missing players
 * (genuine 0.0 kept, absent stays absent).
 *
 * The Python preview builder does the primary derivation; this script must
 * agree with it exactly. Any disagreement names the failing check.
 *
 * Usage: node preview/check_preview_parity.js <vorp-views-preview.json>
 */
"use strict";

const fs = require("fs");

const DISPLAY_MAX = 70;
const RELTOL = 1e-9;

function fail(msg) {
  console.error(`PARITY FAILED: ${msg}`);
  process.exit(1);
}

function main() {
  const path = process.argv[2];
  if (!path) fail("usage: check_preview_parity.js <vorp-views-preview.json>");
  const payload = JSON.parse(fs.readFileSync(path, "utf8"));
  if (payload.schema !== "vorp-views-preview-v1") {
    fail(`expected schema vorp-views-preview-v1, got ${payload.schema}`);
  }
  const peak = payload.provisional_maximum;
  if (!Number.isFinite(peak) || peak <= 0) fail(`bad provisional_maximum ${peak}`);
  if (!payload.batch_scale || Math.abs(payload.batch_scale - DISPLAY_MAX / peak) > 1e-12) {
    fail(`batch_scale ${payload.batch_scale} != 70/provisional_maximum`);
  }
  const natives = payload.native_maps;
  if (!natives || typeof natives !== "object") fail("preview payload lacks native_maps");

  const views = payload.views;
  for (const view of ["indexed", "vorp", "adj_values"]) {
    if (!views[view] || typeof views[view] !== "object") fail(`view ${view} missing`);
  }

  for (const src of Object.keys(natives)) {
    const nativeMap = natives[src];
    const indexed = views.indexed[src];
    const vorp = views.vorp[src];
    const adj = views.adj_values[src];
    if (!vorp || typeof vorp !== "object") fail(`${src}: vorp map missing`);
    if (!adj || typeof adj !== "object") fail(`${src}: adj_values map missing`);

    const nativeKeys = Object.keys(nativeMap).sort().join(",");
    const vorpKeys = Object.keys(vorp).sort().join(",");
    const adjKeys = Object.keys(adj).sort().join(",");
    if (vorpKeys !== adjKeys) {
      fail(`${src}: vorp/adj_values keys differ (dropped/invented players)`);
    }
    if (Object.keys(nativeMap).length > 0) {
      const vorpSet = new Set(Object.keys(vorp));
      const adjSet = new Set(Object.keys(adj));
      for (const k of Object.keys(nativeMap)) {
        if (!vorpSet.has(k) || !adjSet.has(k)) {
          fail(`${src}: native key ${k} missing from VORP/Adjusted`);
        }
      }
    } else if (vorpKeys === "") {
      fail(`${src}: vorp/adj_values maps are empty`);
    }
    for (const [mapName, m] of [["vorp", vorp], ["adj_values", adj]]) {
      for (const [k, v] of Object.entries(m)) {
        if (!Number.isFinite(v) || v < 0) fail(`${src}.${mapName}[${k}] = ${v} (not finite/nonnegative)`);
      }
    }
    // Genuine zeros must survive into every view map.
    const zeroKeys = Object.entries(nativeMap).filter(([, v]) => v === 0).map(([k]) => k);
    for (const zk of zeroKeys) {
      if (!(zk in indexed) || !(zk in vorp) || !(zk in adj)) {
        fail(`${src}: genuine zero player ${zk} dropped from a view map`);
      }
    }

    if (Object.keys(nativeMap).length > 0) {
      if (!indexed || indexed.unavailable) {
        fail(`${src}: has native trade values but indexed is marked unavailable`);
      }
      if (Object.keys(indexed).sort().join(",") !== nativeKeys) {
        fail(`${src}: indexed keys differ from native key set`);
      }
      for (const [k, nv] of Object.entries(nativeMap)) {
        const expected = (nv * DISPLAY_MAX) / peak;
        const got = indexed[k];
        const tol = RELTOL * Math.max(1, Math.abs(expected));
        if (!Number.isFinite(got) || Math.abs(got - expected) > tol) {
          fail(`${src}: indexed[${k}] = ${got}, expected native*70/peak = ${expected}`);
        }
      }
    } else {
      const reason = indexed && indexed.unavailable;
      if (!reason || typeof reason !== "string" || reason.length < 10) {
        fail(`${src}: no native trade values but indexed lacks an explicit unavailable reason`);
      }
    }
  }
  console.log(`PARITY OK: ${Object.keys(natives).length} sources, common peak ${peak}`);
}

main();
