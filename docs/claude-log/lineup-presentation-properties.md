## 2026-10-29 - JEG-1270 lineup presentation property guards

Contract: add seeded property coverage for `app/v2/lineup-comparison.js` `buildRows` (read-only) under input
permutation, duplicate display names, SUPERFLEX, frozen inputs and unpriced players, and prove that name-as-key,
rerank and dropped-slot mutants fail a named property. No module, engine, math, default, Makefile, workflow or
coverage change. Base: main `430791c4`.

New files only: `tests/test_lineup_presentation_properties.py`,
`tests/fixtures/lineup-presentation-properties.json`, this log.

How it works: the real `finder.js` `rosterImpact` picks before/after lineups from 4 seeds x 60 generated rosters
plus 3 hand cases (243 cases). Each case runs in finder order, 4 after-only shuffles and 4 both-side shuffles
(2187 `buildRows` calls), every input deep-frozen. All expectations are derived from the inputs; no totals are
pinned.

### Verified (check named)
- Real module holds every property, zero failures, zero skips:
  `python3 -m unittest tests.test_lineup_presentation_properties -v` -> 4 tests OK, about 2.4 s, offline.
  - `frozen`: no throw on deep-frozen before/after/shape, snapshot (NaN/undefined/Infinity spelled out) unchanged.
  - `slot-ids:<slot>`: after and before rows hold the exact selected keys as a multiset, slot by slot, SUPERFLEX
    and Bench included; row count at least the shape count.
  - `identity`: every row player is the caller's own object.
  - `survivor-row`: a key selected in the same slot on both sides sits in its before row with `changed: false`.
  - `permutation`: after-only shuffles give the same survivor pairing as finder order.
  - `duplicate-names` / `changed-by-key`: different keys with one display name read as changed; nothing collapses.
  - `unpriced`: null, missing, NaN, Infinity, numeric-string and no-values players stay on the bench, never start,
    and `renderTable` (minimal DOM stub) prints "no value" and "—", never 0.0.
- Corpus is not vacuous (`test_corpus_exercises_each_property`): 2079 SUPERFLEX starter checks, 808 same-name
  different-key rows, 16553 survivors whose rank moved, 414 unpriced arrivals on the bench, 906 rendered unpriced
  cells. The 3 hand cases pass alone too (`test_hand_cases_alone_hold`).
- Mutants, each one exact edit of a temp copy (`test_mutants_fail_a_specific_property`; anchor must match once):
  - name-as-key (`id` reads `name`) -> fails `duplicate-names` (4244), also `slot-ids:*`, `survivor-row`, `unpriced`.
  - rerank-after (survivor matching removed, rows follow after rank) -> fails `survivor-row` (16553), `permutation`.
  - drop-slot (`ORDER` without SUPERFLEX) -> fails `slot-ids:SUPERFLEX` (4869), `survivor-row`.
  - zero-fill (unpriced value read as 0, extra) -> fails `unpriced` (1812).
- Existing `tests/test_jeg1216_lineup.py` still passes on this branch (module untouched).

### Claimed, not confirmed
- Observation for the JEG-1216 owner, not patched here: `align` drops an after row whose `player_key` is null or
  missing (a keyless arriving WR renders as an empty cell). No app code was found that builds keyless rows, so it
  may be unreachable. The corpus always carries keys and does not pin this.
- CI wiring is left to the Codex CI coordinator; this file is not yet in any suite list.
