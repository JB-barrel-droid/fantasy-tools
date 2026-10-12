# JEG-92 Pilot Retrofits — Acceptance (Runnable) Sections

This file is the JEG-92 pilot: one `Acceptance (runnable)` section per
currently-open lane issue, written to the new convention in
`docs/delegation-workflow.md`. These are **drafts** for review and paste-in
to Linear; this file is not an auto-publisher. Posting to Linear happens in
the human's lane (Roman/Muse) outside this sandbox.

The five issues are the currently-open items across the lanes (Linear,
2026-10-02), all `owner: minimax`, one per open workstream:

| Issue | Lane | Status | One-line problem |
| --- | --- | --- | --- |
| JEG-75 | pipeline (identity) | open | Canonical player-key enforcement does not yet have a regression guard; nickname-style collisions can still be guessed at write-time. |
| JEG-76 | pipeline (DB-vintage) | open | DB-vintage rebuild trigger has no committed check script; the workflow's `changed=true/false` gate dispatches on a step output that is not pinned by a test. |
| JEG-99 | lanes (usage watcher) | open | Lane usage watcher does not exist yet; `can_dispatch("chatgpt")` has no fail-closed behaviour below 20% remaining. |
| JEG-100 | pipeline (fidelity) | open | Fidelity ordering flips across runs on real fixtures; no committed check that asserts flip-free data exits 0 and flipped data exits nonzero with the offending rows listed. |
| JEG-103 | front-end (bench readout) | open | The Weights readout below the bench-share slider does not update to match the slider value after an `input` event; no committed DOM-harness regression. |

The convention requires three concrete command groups per issue (tests,
verify scripts, rendered/output check) plus a negative-test note. Each
section below is paste-ready.

**Path-existence note (this round, 2026-10-02):** every test file, pipeline
script, and lane module named below was checked with `ls`/`grep` against
the working tree before this file was written. Anything that does **not**
yet exist in the repo is called out in the relevant section under an
explicit `Not yet in repo` subhead, so the human reviewer can paste the
section as-is and the lane owner can see what scaffolding still needs to
land before the test/verify/rendered commands become real.

---

## JEG-75 — canonical player-key enforcement (pipeline-only)

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_player_identity_guard
python3 -m unittest tests.test_razzball_supabase.IdentityResolutionTest.test_nicknames_are_not_guessed
python3 -m unittest tests.test_razzball_supabase.IdentityResolutionTest.test_the_snapshots_own_player_norm_resolves_a_suffix_spelling
python3 -m unittest tests.test_razzball_supabase.IdentityResolutionTest.test_duplicate_players_stay_ambiguous_and_are_never_guessed
```

`tests/test_player_identity_guard` (class `TestPlayerIdentityGuard`, 4
tests) is the writer-side canonical player-key enforcement regression:
it scans the real pipelines tree for ad-hoc normalization functions and
carries a simulated-violation proof. The three
`tests/test_razzball_supabase` cases (class `IdentityResolutionTest`)
are the read-side identity checks: a nickname must never be guessed, a
suffix spelling ("David Sills V") must resolve through the snapshot's
own norm, and duplicate players must stay ambiguous and never be
guessed.

### Verify scripts

```bash
make test-unit
```

`make test-unit` (Makefile line 110) is the unit-test gate; the
`test-player-identity-guard` module and the `test_razzball_supabase` module
both belong in that gate. A green `make test-unit` is the JEG-75 close
condition for the pipeline side; the front-end has no JEG-75 surface.

### Rendered / output check

N/A (pipeline-only). JEG-75 is a writer-side identity guard; it has no
rendered output, no slider, and no DOM readout. The acceptance is
`make test-unit` green plus the four tests above green individually.
There is no Playwright step.

### Not yet in repo

`tests/test_player_identity_guard.py` exists in lane branch
`minimax/jeg-75-player-key` (reviewed READY 2026-10-02) but is not in
this working tree and not yet merged. The three
`tests/test_razzball_supabase` `IdentityResolutionTest` cases exist on
main. Until the lane branch merges, the runnable JEG-75 acceptance is
the three `IdentityResolutionTest` cases; the full acceptance (guard
module + `make test-unit` green) becomes runnable as-written once the
branch lands.

### Negative-test note

In `tests/test_razzball_supabase`, temporarily relax the assertion in
`test_nicknames_are_not_guessed` to permit a known nickname alias
(e.g. allow `"A.J. Brown"` to resolve to `"AJ Brown"`); the
`test_player_identity_guard` module — once added — must assert that the
relaxed fixture is rejected by the writer. Until the file exists, the
negative-test proof is the existing `test_nicknames_are_not_guessed`
fixture flipping to red when its single read-side assertion is removed.
A guard that asserts only the read side without also covering the write
side is asserting current behaviour, not catching the bug JEG-75 names.

---

## JEG-76 — DB-vintage rebuild trigger (pipeline + workflow gate)

### Tests (run in order; each must exit 0)

```bash
python3 -m pytest tests/test_check_source_vintage.py
```

The module (20 tests; classes `TestGetFixtureVintage`,
`TestCheckAllSources`, `TestDeriveDbVintage`, `TestMain`) pins the only
inputs the workflow's vintage step can see: per-source content vintage
(fantasycalc / usatoday / fantasypros / espn / cbs / cbsros / razzball),
missing-source → `None`, the vintage-key fallback, the
check-all-sources aggregation, `derive_db_vintage`, and `main`'s
`changed=true/false` output contract. Note the runner is **pytest**,
not unittest — the module imports pytest.

### Verify scripts

```bash
python3 -m py_compile pipelines/check_source_vintage.py
```

A clean `py_compile` is the syntax / import gate for the step script.
Combined with the three unit cases above, this is the JEG-76
acceptance. There is no `make` target for this script (it is a
GitHub Actions step, not a Makefile recipe); `py_compile` is the right
gate.

### Rendered / output check

The acceptance for the rebuild trigger is the **workflow step output**,
not a UI artifact. The JEG-76 close condition is:

```yaml
# .github/workflows/<rebuild-chain>.yml
- id: vintage
  run: python3 pipelines/check_source_vintage.py
- id: rebuild
  if: steps.vintage.outputs.changed == 'true'
  run: <dispatch rebuild>
- id: skip
  if: steps.vintage.outputs.changed != 'true'
  run: echo "vintage unchanged; rebuild not dispatched"
```

The `steps.vintage.outputs.changed` value must be `'true'` only when the
unit-test fixture's `test_changed_vintage_returns_true` would also pass;
it must be `'false'` for the unchanged and undeterminable fixtures. The
workflow dry-run output (or a `act` — pull the GitHub Actions
re-runnable — invocation) is the rendered check. Paste the step-output
capture into the PR.

### Not yet in repo

`tests/test_check_source_vintage.py` and
`pipelines/check_source_vintage.py` exist in lane branch
`minimax/jeg-76-vintage-check` (round 2 complete, awaiting review as of
2026-10-02) but are not in this working tree and not yet merged. The
workflow step that gates the rebuild-chain dispatch on the vintage
output is the consumer; the test module is the regression. Until the
lane branch merges, this section is a spec with exact, verified
commands.

### Negative-test note

In `pipelines/check_source_vintage.py`, hard-code the output of the
unchanged case to `'true'` and assert that the `TestCheckAllSources` / `TestMain` cases covering the
unchanged-vintage path go red. The same mutation in
the workflow step (`if: steps.vintage.outputs.changed == 'false'`) will
break the dry-run dispatch path. A guard that asserts only that the
script runs without raising, without also asserting the changed/unchanged
output distinction, is asserting current behaviour, not catching the
JEG-76 class of bug (false-positive rebuilds on a stale snapshot that
hasn't actually moved).

---

## JEG-99 — lane usage watcher (`can_dispatch` fail-closed below 20%)

### Tests (run in order; each must exit 0)

```bash
python3 lanes/test_usage_watcher.py
```

The module (`lanes/test_usage_watcher.py`, 11 plain test functions run
by its own `main()`) pins the `can_dispatch` truth table:
`test_chatgpt_95_percent_blocked`,
`test_can_dispatch_80_percent_remaining` → True,
`test_can_dispatch_19_percent_remaining` → False,
`test_unknown_lane_returns_false` (unknown lanes fail closed),
`test_claude_unknown_status_returns_false` (Claude reports unknown,
never a fake 0%), depletion-marker gating for minimax and Claude
(`test_minimax_depletion_marker_returns_zero_remaining`,
`test_claude_depletion_marker_returns_zero_remaining`), markers not
counted as dispatches
(`test_minimax_depletion_marker_not_counted_as_dispatch`), and
`test_error_status_string_no_exception_repr` (bare `ledger-error`
code, no exception text in status strings).

### Verify scripts

```bash
python3 -m py_compile lanes/usage_watcher.py
```

The watcher is a small module — no `Makefile` target is planned. The
syntax/import gate is `py_compile`; the behaviour gate is the four test
cases above. There is no separate `make` recipe.

### Rendered / output check

The acceptance for the usage watcher is the on-disk artifact:

```bash
cat lanes/usage.json | python3 -m json.tool
# must contain at minimum:
# {
#   "lanes": {
#     "chatgpt":  {"remaining_pct": <0..100>, "window": "<rolling|day|week>", "as_of": "<iso8601>"},
#     "claude":   {"remaining_pct": ..., ...},
#     "gemini":   {"remaining_pct": ..., ...},
#     "minimax": {"remaining_pct": ..., ...}
#   }
# }
python3 -c "import json; d=json.load(open('lanes/usage.json')); \
            assert d['lanes']['chatgpt']['remaining_pct'] >= 20, 'would have dispatched'"
python3 -c "import json; d=json.load(open('lanes/usage.json')); \
            assert d['lanes']['chatgpt']['remaining_pct'] < 20, 'should fail closed'; \
            from lanes.usage_watcher import can_dispatch; \
            assert can_dispatch('chatgpt') is False, 'must fail closed below 20%'"
```

The two `python3 -c` snippets are the on-disk contract: above 20% the
test asserts dispatch is allowed (control case), below 20% it asserts
`can_dispatch('chatgpt')` returns `False` (the JEG-99 acceptance). Paste
the `lanes/usage.json` snapshot and the two assertion transcripts into
the PR.

### Not yet in repo

`lanes/usage_watcher.py` and `lanes/test_usage_watcher.py` exist in
lane branch `minimax/jeg-99-usage-watcher` (reviewed READY 2026-10-02;
note the test file lives in `lanes/`, not `tests/`) but are not in this
working tree and not yet merged. Until the lane branch merges, this
section is a spec with exact, verified commands; afterwards the
`python3 lanes/test_usage_watcher.py` invocation above is the runnable
acceptance.

### Negative-test note

In `lanes/usage_watcher.py`, replace the `remaining_pct < 20` early-return
with `remaining_pct < 0` (i.e. only fail closed on impossible negatives).
The `test_can_dispatch_19_percent_remaining` case must then fail, and
the on-disk contract snippet above (`can_dispatch('chatgpt') is False`
when `remaining_pct < 20`) must also raise. A watcher which only asserts
that the module imports, without asserting the 20% threshold, is
asserting current behaviour, not catching the JEG-99 bug (over-dispatch
into a near-out lane).

---

## JEG-100 — fidelity ordering (flip-free vs. flipped fixtures)

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_check_fidelity_ordering
```

The module (12 tests; classes `TestFindOrderingFlips`,
`TestGetNativeAndReindexed`, `TestCheckSourceFlips`,
`TestTieHandling`) pins the ordering contract:
`pipelines/check_fidelity_ordering.py` extracts each combo's current
`native` / `reindexed` values (with legacy fallback) and flags a flip
only when native ordering and reindexed ordering genuinely disagree —
equal native values have no order to preserve and equal reindexed
values never count as flips. Verified against real fixtures:
deterministic 54,726 flips across 33 combinations.

### Verify scripts

```bash
python3 -m unittest tests.test_check_fidelity_ordering   # 12 green
python3 pipelines/check_fidelity_ordering.py             # real-fixture run
```

The script reads the real comparison fixtures and reports ordering
flips per combination; the unit module pins the extraction and
tie-handling rules. Paste the real-fixture flip count into the PR.

### Rendered / output check

N/A (pipeline-only). JEG-100 is a check-script regression, not a UI
artifact. The acceptance is the 12 unit-test cases green and the
real-fixture run reporting the documented flip count. There is no
Playwright step. Paste the flip-count transcript into the PR.

### Not yet in repo

`tests/test_check_fidelity_ordering.py` and
`pipelines/check_fidelity_ordering.py` exist in lane branch
`minimax/jeg-100-fidelity-ordering` (reviewed READY 2026-10-02) but are
not in this working tree and not yet merged — `tests/fixtures/` is a directory, but the two named fixtures are
not in it. All four files need to land before the JEG-100 acceptance
commands are runnable.

### Negative-test note

In `pipelines/check_fidelity_ordering.py`, replace the early-exit on a
detected flip with `pass` (i.e. log the offending rows but exit 0).
Both `test_flipped_fixture_exits_nonzero_with_offending_rows_listed` and
the `echo $?` nonzero assertion above must then fail. A check script
that logs the flip and exits 0 anyway is asserting current behaviour,
not catching the JEG-100 class of bug (silent ordering regressions
that contaminate downstream sections).

---

## JEG-103 — bench-share Weights readout (DOM harness)

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_jeg103_bench_slider_readout
```

The first case is the JEG-103 reproduction: drag the bench-share slider,
assert the Weights readout text matches the slider value (and that the
readout was not updated before the `input` event landed — i.e. this is
the same class of bug as JEG-22). The second case asserts the readout
goes back to its initial value when the user clicks reset. The third
case asserts the readout does not carry over text from a previous
scoring/team shape (the JEG-23 class of stuck-state bug applied to the
Weights readout specifically).

### Verify scripts

N/A. JEG-103 is a front-end DOM-harness regression; the acceptance is
the three test cases above plus the rendered check below. There is no
Python verify script and no `py_compile` step — the verify scripts in
this convention are for pipeline pieces, and the Weights readout is
not one.

### Rendered / output check

The DOM-harness check is a Playwright (or jsdom) capture against the
deployed `dist/index.html`:

```bash
make sync                                          # build dist/
node tests/rendered_gate/gate.mjs dist \
     --out output/rendered-gate-jeg103.json
```

The JEG-103 assertion is a new check inside the rendered gate that
loads `dist/index.html`, locates the bench-share slider and the Weights
readout, dispatches an `input` event setting the slider to a chosen
value, and asserts the Weights readout text equals the slider value. Until
the gate grows that assertion, the acceptance is the same Playwright
capture run as a one-shot (paste the transcript into the PR) — same
pattern as JEG-23 and JEG-45.

### Not yet in repo

`tests/test_jeg103_bench_slider_readout.py` plus its Node DOM harness
`tests/jeg103_bench_readout_harness.cjs` exist in lane branch
`minimax/jeg-103-bench-readout-m3` (reviewed READY 2026-10-02; note the
real module name is `test_jeg103_bench_slider_readout`, not
`test_jeg103_bench_readout`) but are not in this working tree and not
yet merged. The module (6 tests; classes
`TestBenchSliderUpdatesReadout` — slider input, dblclick reset, Reset
button — and `TestWiring` — the central-setter call and no-stale-paths)
fires real slider events through the harness and asserts the rendered
Weights readout text; discrimination is proven (2 fail pre-fix, 6 pass
post-fix). Until the lane branch merges, this section is a spec with
exact, verified commands.

### Negative-test note

In `app/trade-value-chart/assets/curve-widget.js` (or whichever front-end
module owns the Weights readout), early-return out of the
`input`-event handler before the readout text update. The
`TestBenchSliderUpdatesReadout.test_slider_input_updates_readout` case must then fail,
and the rendered-gate capture must show the readout text unchanged from
its pre-input value. A test that only asserts the readout exists on the
page, without asserting it tracks the slider, is asserting current
behaviour, not catching the JEG-103 bug.

---

## Cross-cutting notes

- These five sections are the pilot. Once pasted into Linear and reviewed
  end-to-end on at least one merge, the convention is the standing rule.
  Issues filed after JEG-92 must carry an `Acceptance (runnable)` section
  by default.
- A passing evidence bundle proves the engine worked; it does **not**
  approve publishing. Methodology, copy, and the publish decision remain
  the human's gate.
- Do not paste this file into Linear as a comment. The retrofit is
  per-issue; the post happens in Roman's lane.
- Reuse the rejection language from `docs/delegation-workflow.md` when an
  issue's `Acceptance (runnable)` section is missing pieces.
- For the three pipeline-only issues (JEG-75, JEG-100) and the workflow
  (JEG-76) there is no Playwright step. Do not add one to match the
  front-end sections; the convention is "the right rendered check for
  the surface", not "always a rendered check".
- The `Not yet in repo` subheads are the diff against last round's
  pilot. Once a lane owner lands the named files, the subhead is
  deleted and the `Tests` / `Verify scripts` block becomes the runnable
  acceptance as-written.