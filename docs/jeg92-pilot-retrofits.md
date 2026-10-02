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
python3 -m unittest tests.test_razzball_supabase.TestRazzballNicknamesAndIdentity.test_nicknames_are_not_guessed
python3 -m unittest tests.test_razzball_supabase.TestRazzballNicknamesAndIdentity.test_position_narrows_same_named_players
python3 -m unittest tests.test_razzball_supabase.TestRazzballNicknamesAndIdentity.test_typographic_apostrophe_matches_the_straight_apostrophe_name
```

`tests/test_player_identity_guard` is the canonical player-key enforcement
regression. The three `tests/test_razzball_supabase` cases (the
`test_nicknames_are_not_guessed` family at lines 143–161 of that file) are
the read-side identity checks: a nickname must never be guessed, a position
must narrow same-named players, and a typographic apostrophe must match the
straight-apostrophe form without a side-table alias.

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

`tests/test_player_identity_guard` does not exist in the working tree as
of 2026-10-02 (`ls tests/test_player_identity_guard*` returns nothing).
The three `test_razzball_supabase` cases at lines 143, 157, and 161 of
`tests/test_razzball_supabase.py` do exist and are the read-side guard;
the dedicated `test_player_identity_guard` module covering the
writer-side canonical-key enforcement is the piece that still needs to
land. Until it does, the JEG-75 acceptance is the three existing
`test_razzball_supabase` identity cases plus the writer-side test once it
is added.

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
python3 -m unittest tests.test_check_source_vintage.TestSourceVintageChanged.test_changed_vintage_returns_true
python3 -m unittest tests.test_check_source_vintage.TestSourceVintageUnchanged.test_unchanged_vintage_returns_false
python3 -m unittest tests.test_check_source_vintage.TestSourceVintageUndeterminable.test_undeterminable_vintage_returns_sentinel
```

The three cases are the only inputs the workflow's
`source_vintage_changed` step can see: a vintage that did move
(`changed=true`), a vintage that did not (`changed=false`), and a vintage
that cannot be determined from the available snapshot pair
(`undeterminable` → the workflow must fail closed rather than dispatch a
rebuild).

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

`tests/test_check_source_vintage.py` does not exist in the working tree
as of 2026-10-02 (`ls tests/test_check_source_vintage*` returns
nothing). `pipelines/check_source_vintage.py` does not exist either
(`ls pipelines/check_source_vintage.py` returns nothing). Both files
need to land before the JEG-76 acceptance commands are real. The
workflow step that gates the rebuild-chain dispatch on
`steps.vintage.outputs.changed` is the same step the test module drives;
the test module is the regression, the workflow step is the consumer.

### Negative-test note

In `pipelines/check_source_vintage.py`, hard-code the output of the
unchanged case to `'true'` and assert that the unit test
`test_unchanged_vintage_returns_false` goes red. The same mutation in
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
python3 -m unittest tests.test_usage_watcher.TestCanDispatch.test_chatgpt_above_20_percent_returns_true
python3 -m unittest tests.test_usage_watcher.TestCanDispatch.test_chatgpt_below_20_percent_returns_false
python3 -m unittest tests.test_usage_watcher.TestCanDispatch.test_other_lanes_use_independent_bars
python3 -m unittest tests.test_usage_watcher.TestUsageJsonShape.test_usage_json_has_per_lane_bars
```

The first three cases are the `can_dispatch("chatgpt")` truth table: above
20% remaining returns `True`, below returns `False`, and other lanes
(`claude`, `gemini`, `minimax`) read from their own bars and are not
coupled to the chatgpt bar. The fourth case pins the on-disk schema
(`lanes/usage.json`) so a future re-shape of the file trips the test
rather than silently shipping.

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

`lanes/` does not exist in the working tree as of 2026-10-02 (`ls lanes/`
returns nothing). That means `lanes/usage_watcher.py`,
`lanes/usage.json`, and any `tests/test_usage_watcher*` module do not
yet exist either. The JEG-99 acceptance commands are real once the lane
directory and the four files it owns land; until then, this section is
a spec for the lane owner, not a runnable acceptance. The
negative-test note below describes what the eventual test must prove.

### Negative-test note

In `lanes/usage_watcher.py`, replace the `remaining_pct < 20` early-return
with `remaining_pct < 0` (i.e. only fail closed on impossible negatives).
The `test_chatgpt_below_20_percent_returns_false` case must then fail, and
the on-disk contract snippet above (`can_dispatch('chatgpt') is False`
when `remaining_pct < 20`) must also raise. A watcher which only asserts
that the module imports, without asserting the 20% threshold, is
asserting current behaviour, not catching the JEG-99 bug (over-dispatch
into a near-out lane).

---

## JEG-100 — fidelity ordering (flip-free vs. flipped fixtures)

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_check_fidelity_ordering.TestFlipFree.test_flip_free_fixture_exits_zero
python3 -m unittest tests.test_check_fidelity_ordering.TestFlipped.test_flipped_fixture_exits_nonzero_with_offending_rows_listed
python3 -m unittest tests.test_check_fidelity_ordering.TestRealFixtures.test_real_snapshots_match_the_documented_ordering
```

The first two cases pin the script's exit-code contract on synthetic
fixtures (a fixture with no ordering flips exits 0; a fixture with a
known flip exits nonzero and lists the offending rows on stderr). The
third case is the regression against the real snapshots the pipeline
actually runs over.

### Verify scripts

```bash
python3 pipelines/check_fidelity_ordering.py --fixture tests/fixtures/fidelity_ordering_flip_free.json
echo $?    # must be 0
python3 pipelines/check_fidelity_ordering.py --fixture tests/fixtures/fidelity_ordering_one_flip.json
echo $?    # must be nonzero; offending rows must appear on stderr
```

The script must read a JSON fixture (a list of `{source, player_key,
fidelity_rank, observed_at}` rows), decide whether any later
`observed_at` has a worse `fidelity_rank` than an earlier one for the
same `(source, player_key)`, and exit accordingly. The flip-free case
exits 0; the one-flip case exits nonzero and prints the offending
`(source, player_key)` pair on stderr.

### Rendered / output check

N/A (pipeline-only). JEG-100 is a check-script regression, not a UI
artifact. The acceptance is the three unit-test cases green and the two
`--fixture` invocations above returning the right exit codes. There is
no Playwright step. Paste the two `echo $?` transcripts into the PR.

### Not yet in repo

`tests/test_check_fidelity_ordering.py` does not exist in the working
tree as of 2026-10-02 (`ls tests/test_check_fidelity_ordering*` returns
nothing). `pipelines/check_fidelity_ordering.py` does not exist either.
The flip-free and one-flip fixtures (`tests/fixtures/fidelity_ordering_flip_free.json`
and `tests/fixtures/fidelity_ordering_one_flip.json`) also do not exist
yet — `tests/fixtures/` is a directory, but the two named fixtures are
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
python3 -m unittest tests.test_jeg103_bench_readout.TestWeightsReadout.test_readout_matches_slider_after_input_event
python3 -m unittest tests.test_jeg103_bench_readout.TestWeightsReadout.test_readout_resets_to_initial_on_reset
python3 -m unittest tests.test_jeg103_bench_readout.TestWeightsReadout.test_readout_does_not_show_stale_text_from_previous_shape
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

`tests/test_jeg103_bench_readout.py` does not exist in the working tree
as of 2026-10-02 (`ls tests/test_jeg103_bench_readout*` returns
nothing). The rendered gate at `tests/rendered_gate/gate.mjs` does
exist (it is the same gate JEG-22, JEG-23, JEG-45, and JEG-17 use), but
it does not yet carry the JEG-103 Weights-readout assertion. Both
scaffolds need to land before the JEG-103 acceptance commands are real;
until then, the section is a spec.

### Negative-test note

In `app/trade-value-chart/assets/curve-widget.js` (or whichever front-end
module owns the Weights readout), early-return out of the
`input`-event handler before the readout text update. The
`test_readout_matches_slider_after_input_event` case must then fail,
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