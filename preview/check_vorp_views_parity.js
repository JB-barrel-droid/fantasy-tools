#!/usr/bin/env node
/**
 * JEG-242: independent second-language verification that the batch70 ->
 * comparison transformer output is exactly what the REVIEWED candidate
 * carries -- i.e. the transformer's vorp_views blocks are consumed data,
 * not dead keys.
 *
 * Reads the candidate and the TRANSFORMED comparison payload, and verifies
 * per as-published source:
 *  - sources[<comp>].vorp_views exists with schema "vorp-views-v1",
 *    scoring/teams matching the candidate manifest configuration, and
 *    batch_sha256 matching the candidate file's bytes.
 *  - every candidate (canonical-key -> value) entry in indexed/vorp/
 *    adj_values appears under its player_keys display name with the EXACT
 *    value; no extra names, no missing names (genuine 0.0 kept, absent
 *    stays absent).
 *  - no consumer-less _jeg242_batch70 keys anywhere in the payload.
 *
 * The Python transformer does the primary derivation; this script must
 * agree with it exactly. Any disagreement names the failing check.
 *
 * Usage: node preview/check_vorp_views_parity.js <candidate.json> <transformed-comparison.json>
 */
"use strict";

const fs = require("fs");
const crypto = require("crypto");

const SOURCE_MAP = {
  fantasycalc: "fantasycalc",
  usat: "usatoday",
  fantasypros: "fantasypros",
  cbs: "cbs",
};
const VIEW_KEYS = ["indexed", "vorp", "adj_values"];

function fail(msg) {
  console.error(`VORP-VIEWS PARITY FAILED: ${msg}`);
  process.exit(1);
}

function main() {
  const [candidatePath, comparisonPath] = process.argv.slice(2);
  if (!candidatePath || !comparisonPath) {
    fail("usage: check_vorp_views_parity.js <candidate.json> <transformed-comparison.json>");
  }
  const candidateBytes = fs.readFileSync(candidatePath);
  const candidate = JSON.parse(candidateBytes.toString("utf8"));
  const comparison = JSON.parse(fs.readFileSync(comparisonPath, "utf8"));

  if (candidate.schema !== "shared-batch70-views-v1") {
    fail(`expected candidate schema shared-batch70-views-v1, got ${candidate.schema}`);
  }
  const config = candidate.manifest && candidate.manifest.configuration;
  if (!config || typeof config.scoring !== "string" || typeof config.teams !== "number") {
    fail("candidate manifest lacks scoring/teams configuration");
  }
  const candidateSha = crypto.createHash("sha256").update(candidateBytes).digest("hex");

  const rawText = fs.readFileSync(comparisonPath, "utf8");
  if (rawText.includes("_jeg242_batch70")) {
    fail("transformed payload contains consumer-less _jeg242_batch70 keys");
  }

  const playerKeys = comparison.player_keys;
  if (!playerKeys || typeof playerKeys !== "object") fail("comparison lacks player_keys");
  const keyToName = new Map();
  for (const [name, key] of Object.entries(playerKeys)) {
    const n = Number(key);
    if (!Number.isInteger(n) || n <= 0) fail(`bad canonical key for ${name}`);
    if (keyToName.has(String(n))) fail(`duplicate canonical key ${n}`);
    keyToName.set(String(n), name);
  }

  const batchSources = candidate.sources;
  if (!batchSources || typeof batchSources !== "object") fail("candidate has no sources");
  const compSources = comparison.sources;
  if (!compSources || typeof compSources !== "object") fail("comparison has no sources");

  let checked = 0;
  for (const [pipeSrc, perView] of Object.entries(batchSources)) {
    const compSrc = SOURCE_MAP[pipeSrc];
    if (!compSrc) continue; // transformer skips unmapped sources with a reason; not our check
    const vv = compSources[compSrc] && compSources[compSrc].vorp_views;
    if (!vv) fail(`${compSrc}: vorp_views block missing (transformer did not wire it)`);
    if (vv.schema !== "vorp-views-v1") fail(`${compSrc}: schema ${vv.schema}`);
    if (vv.scoring !== config.scoring) fail(`${compSrc}: scoring ${vv.scoring} != ${config.scoring}`);
    if (vv.teams !== config.teams) fail(`${compSrc}: teams ${vv.teams} != ${config.teams}`);
    if (vv.batch_sha256 !== candidateSha) fail(`${compSrc}: batch_sha256 does not match candidate bytes`);
    for (const view of VIEW_KEYS) {
      const candView = perView[view];
      const outView = vv.views && vv.views[view];
      if (!candView || typeof candView !== "object") fail(`${compSrc}: candidate view ${view} missing`);
      if (!outView || typeof outView !== "object") fail(`${compSrc}: transformed view ${view} missing`);
      const candKeys = Object.keys(candView);
      const outKeys = Object.keys(outView);
      if (candKeys.length === 0) fail(`${compSrc}: candidate view ${view} is empty`);
      if (outKeys.length !== candKeys.length) {
        fail(`${compSrc}.${view}: key count ${outKeys.length} != candidate ${candKeys.length} (dropped/invented players)`);
      }
      for (const canonKey of candKeys) {
        const name = keyToName.get(String(canonKey));
        if (name === undefined) fail(`${compSrc}.${view}: canonical key ${canonKey} has no display name`);
        if (!Object.prototype.hasOwnProperty.call(outView, name)) {
          fail(`${compSrc}.${view}: display name ${name} missing from transformed view`);
        }
        // Exact equality: JSON round-trips doubles exactly; any deviation is tampering.
        if (outView[name] !== candView[canonKey]) {
          fail(`${compSrc}.${view}[${name}]: ${outView[name]} !== candidate ${candView[canonKey]}`);
        }
      }
      checked += 1;
    }
  }
  if (checked === 0) fail("no source views verified");
  console.log(`VORP-VIEWS PARITY OK: ${checked} view maps verified against candidate ${candidateSha.slice(0, 12)}...`);
}

main();
