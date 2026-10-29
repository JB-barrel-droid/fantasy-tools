## 2026-10-29 - JEG-1241 roster provenance transitions (under JEG-1188)

Contract: a pure helper and regression table for the roster-provenance defects Codex found on #1105 (302d7ee9), so a
partial, unmatched, locally edited or stale roster is never read as "every omitted player is a free agent". New files
only. #1105 keeps all workspace.js / league.js / value-model.js wiring; nothing here is loaded by the page yet.

Files: `app/v2/roster-provenance-transitions.js` (global `DDFRosterProvenance`), `tests/node/roster_provenance_transitions.cjs`,
`tests/test_roster_provenance_transitions.py`, `tests/fixtures/roster_provenance/transitions.json`.

### Verified (check named)
- `node tests/node/roster_provenance_transitions.cjs`: 37 table rows pass (19 transitions, 8 coverage, 10 blocker rows);
  every input is deep-frozen and the module runs in strict mode, so any write to an input throws; results are frozen;
  start records compare byte-equal after the run.
- Same runner: 21 one-line source mutants, each reintroducing one defect, are each caught by at least one row, and each
  mutation point must occur exactly once in the source. Includes the three from the #1105 review: append turning an
  unknown count into a known one (`league.js:223`), a no-op paste refreshing the roster time (`workspace.js:133`), and a
  rejected "Yes, add" still decrementing (`league.js:256`).
- `python3 -m unittest tests.test_roster_provenance_transitions`: 4 tests pass (runner, table well-formed, acceptance
  rows present, module has no DOM/storage/clock).
- Blocker rows B01/B02: the same starters-only rosters pass with whole-roster coverage (a legitimately empty bench) and
  are blocked with `coverage_unproven` when the source omitted its bench, though team count and starter minimum both pass.
  Each blocker row also passes with its players removed, so occupancy does not change the verdict.

### Claimed, not confirmed
- The wiring below is a proposal to the #1105 owner (sent 2026-10-29); no page code uses the helper, and no render or
  `make validate` run covers it. The new test is not in any Makefile list (Makefile is off-limits until the handshake).
- No parser path attests `whole_roster` today (JEG-1131: no platform fetch). If #1105 adds `coverage_unproven` as a hard
  gate, every league stays on the modeled bench until a source can attest every seat. That is a decision for #1105 and
  Codex, not this helper.

### Integration contract for #1105 (the owner's hunks, the owner's call)
- Keep a `provenance` record per team beside `entries`, from `DDFRosterProvenance.normalize(storedTeam)`.
  A stored `rosterAt` maps to `editedAt` only.
- Replacing paste (`place(..., replace=true)`, team paste, `pasteWholeLeague`): `replaceFromSource(p, {now, unresolved,
  coverage: coverageFrom(res)})`; pass `unresolved` only when the paste's own count is known.
- Append (`place(..., replace=false)` with `missed`): `appendFromSource(p, {now, added: added.length, missed,
  rejected: onOther.length})`. Nothing added and nothing left out returns `p` unchanged: skip the store update.
- "Yes, add" and "Search to add" for a pasted line: call `reconcile(p, {now, key, accepted})` after `place()` with
  `accepted = r.added.length > 0`, and `key` = the pasted source line, not `resolvedOne()` before placing.
- Other edits: `localEdit`; `clearTeam`: `clear`; share-link import: `normalize({unresolved})` with no `observedAt`.
- `leagueCompleteness`: pass `loadedAt: freshnessTime(p)`, so stale/no_timestamp keep the existing window. Then
  `inferenceBlockers({teams, existingReasons: check.reasons})`; read omitted players as free agents only when it is empty.
- Tests to add on the #1105 side: an integration case per bullet above against the league page store, with exact
  before/after counts and both timestamps (the table rows T01-T03, T09-T10, T14 give the expected values).
