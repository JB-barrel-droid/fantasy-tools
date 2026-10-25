// test_v2_name_format.js — unit table for app/v2/name-format.js (JEG-947). Run: node tests/test_v2_name_format.js
"use strict";
const path = require("path");
const assert = require("assert");
const ROOT = path.resolve(__dirname, "..");
const F = require(path.join(ROOT, "app", "v2", "name-format.js"));

// [input, pos, expected]
const TABLE = [
  ["Kyle Pitts", "TE", "Pitts, Kyle"],
  ["Marvin Harrison Jr.", "WR", "Harrison Jr., Marvin"],
  ["Aaron Jones Sr.", "RB", "Jones Sr., Aaron"],
  ["Gardner Minshew II", "QB", "Minshew II, Gardner"],
  ["Kenneth Walker III", "RB", "Walker III, Kenneth"],
  ["Some Person IV", "WR", "Person IV, Some"],
  ["Some Person V", "WR", "Person V, Some"],
  ["Amon-Ra St. Brown", "WR", "St. Brown, Amon-Ra"],
  ["Equanimeous St. Brown", "WR", "St. Brown, Equanimeous"],
  ["Jacob De Jesus", "WR", "De Jesus, Jacob"],
  ["Mitch Van Vooren", "TE", "Van Vooren, Mitch"],
  ["Van Jefferson", "WR", "Jefferson, Van"],                    // "Van" is the first name here
  ["Jaxon Smith-Njigba", "WR", "Smith-Njigba, Jaxon"],
  ["Gardner-Douglas Test", "WR", "Test, Gardner-Douglas"],
  ["Some Gardner-Douglas", "WR", "Gardner-Douglas, Some"],
  ["Dont'e Thornton Jr.", "WR", "Thornton Jr., Dont'e"],
  ["Aidan O'Connell", "QB", "O'Connell, Aidan"],
  ["Tre' McKitty", "TE", "McKitty, Tre'"],
  ["A.J. Brown", "WR", "Brown, A.J."],
  ["Odell Beckham Jr", "WR", "Beckham Jr, Odell"],              // suffix without a dot
  ["  Kyle   Pitts ", "TE", "Pitts, Kyle"],                      // stray spacing
  // Unchanged: no first name, defenses and teams, already formatted.
  ["Cher", "WR", "Cher"],
  ["Buffalo Bills", "DST", "Buffalo Bills"],
  ["San Francisco 49ers", "D/ST", "San Francisco 49ers"],
  ["Bills D/ST", "DEF", "Bills D/ST"],
  ["Chris Jr.", "WR", "Chris Jr."],
  ["Harrison Jr., Marvin", "WR", "Harrison Jr., Marvin"],
  ["", "WR", ""],
  [null, "WR", ""],
];

for (const [input, pos, expected] of TABLE) {
  assert.strictEqual(F.lastFirst(input, pos), expected, `lastFirst(${JSON.stringify(input)}, ${pos})`);
}

// Negative proof: with suffix handling removed the suffix rows must fail, so the table above does catch that bug.
const SUFFIX_ROWS = TABLE.filter(([n]) => /\b(Jr\.?|Sr\.?|II|III|IV|V)$/.test(String(n)) && !String(n).includes(",") && String(n).split(" ").length >= 3);
assert.ok(SUFFIX_ROWS.length >= 6, "suffix rows present");
const SRC = require("fs").readFileSync(path.join(ROOT, "app", "v2", "name-format.js"), "utf8");
const broken = SRC.replace(/var SUFFIX_RE = [^;]+;/, "var SUFFIX_RE = /^$/;");
assert.notStrictEqual(broken, SRC, "mutation applied");
const mod = {exports: {}};
new Function("module", "globalThis", broken)(mod, undefined);
const failing = SUFFIX_ROWS.filter(([n, p, e]) => mod.exports.lastFirst(n, p) !== e);
assert.strictEqual(failing.length, SUFFIX_ROWS.length, "every suffix row fails when suffix handling is removed");

// Same for the multi-word last-name particles.
const brokenP = SRC.replace(/var PARTICLE_RE = [^;]+;/, "var PARTICLE_RE = /^$/;");
const modP = {exports: {}};
new Function("module", "globalThis", brokenP)(modP, undefined);
assert.notStrictEqual(modP.exports.lastFirst("Amon-Ra St. Brown", "WR"), "St. Brown, Amon-Ra");

console.log(`ok: ${TABLE.length} name cases, suffix and particle negatives`);
