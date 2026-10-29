## 2026-10-29 - JEG-1272 roster paste mutation proof

Contract: make the roster-paste discrimination claims executable. Copy the real
parser into a temp dir, apply three real mutations from a manifest to separate
copies, and show each broken copy fails the contract it names while the real
parser passes everything. A mutation that does not apply, or a mutant that only
crashes, fails the harness instead of counting as caught.

Base: main at 430791c4. Path note: the ticket names this file without the
`YYYY-MM-DD-` prefix that `docs/claude-log/README.md` asks for; the ticket's
path is kept because the ticket owns the paths for this lane.

### What was added

- `tests/test_roster_paste_mutation_proof.py`: the harness and its Node driver
  (written into the temp dir at run time, run with `node`, no network, no
  skips: a missing `node` fails the run).
- `tests/fixtures/roster-paste-mutations/manifest.json`: three contracts and
  three mutations. Each mutation is exact find/replace edits with an expected
  match count.
- Nothing else changed. `app/v2/roster-paste.js`, `tests/test_v2_roster_paste.js`
  and `tests/fixtures/roster_paste/` are read only.

| Mutation | What it breaks | Contract it must fail |
|---|---|---|
| `no_structural_team_pos` | ESPN team parser accepts a row on the name alone (`if (singleName && teamCode && posCode)` becomes `if (singleName)`) | `structural_team_pos` |
| `no_duplicate_suppression` | the four `seen[...]` duplicate returns in `matchCandidate` and the extractor's `seen[key]` skip are removed | `duplicate_suppression` |
| `no_ambiguous_refusal` | `matchCandidate` keeps the first of several hits; `disambiguate` returns `filtered[0]` when more than one is left | `ambiguous_refusal` |

Contract checks (each check runs even after an earlier one fails):

- `structural_team_pos`: the scrubbed ESPN team sample with an injected Bench
  row holding Odell Beckham Jr.'s exact doubled name and no team or position
  line still gives exactly the 15 real rows and no Beckham.
- `duplicate_suppression`: `matchCandidate` refuses a second Boswell with reason
  `duplicate`; the ESPN team sample with the Samaje Perine row pasted twice gives
  15 unique players; `Jaylin Noel WR HOU` on two plain-list lines gives one.
- `ambiguous_refusal`: two Josh Allens and no evidence: `matchCandidate` and
  `disambiguate` return no match, and a plain-list paste of "Josh Allen" matches
  nobody and reports the line as ambiguous.

### Verified (check named)

- `python3 -m unittest tests.test_roster_paste_mutation_proof -v`: 13 tests,
  OK, 0 skipped, about 0.2s locally (node v22.22.0, Python 3.13).
- `test_baseline_passes_every_contract`: the real parser passes all 7 checks.
- `test_every_check_of_the_named_contract_catches_its_mutant`: every check of
  each mutant's named contract fails with an AssertionError (1 of 1 structural,
  3 of 3 duplicate, 3 of 3 ambiguous).
- `test_mutants_leave_the_other_contracts_passing`: each mutant passes the two
  contracts it does not name, so every catch is the named contract's own.
- `test_unapplied_mutation_fails_the_harness`: a missing find text, a wrong
  expected count and a no-op edit each raise `MutationNotApplied`.
- `test_startup_error_is_not_detection` and `test_runtime_error_is_not_detection`:
  a syntax-broken copy reports `load: error` and a copy whose `parse()` throws a
  TypeError reports `error`; `assert_detected` rejects both.
- `test_real_files_untouched`: SHA-256 of the parser, the manifest and the
  sample read is the same before and after the run.
- Ad hoc, not committed: pointing the first edit's find text at a name that is
  not in the parser failed `test_each_mutation_applies` and the detection tests
  with "find text appears 0 times, expected 1"; replacing the ambiguous mutation
  with an equivalent rewrite (`(filtered.length === 1) ? ...`) failed
  `test_each_mutant_fails_its_named_contract` with `NotDetected`.
- `node tests/test_v2_roster_paste.js`: 41 passed, 0 failed (unchanged suite).

### Claimed, not confirmed

- The harness is not wired into `make test-unit` or any workflow; Codex owns
  that wiring. Proposed line for `test-unit-modules` in the Makefile:
  `python3 -m unittest tests.test_roster_paste_mutation_proof`.
- The mutations follow the parser's text at 430791c4. A later edit to those
  exact lines makes the harness fail with "find text appears 0 times", which is
  intended: update the manifest's find text, not the assertions.
