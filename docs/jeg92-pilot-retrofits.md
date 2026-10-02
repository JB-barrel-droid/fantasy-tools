# JEG-92 Pilot Retrofits — Acceptance (Runnable) Sections

This file is the JEG-92 pilot: one `Acceptance (runnable)` section per
currently-open lane issue, written to the new convention in
`docs/delegation-workflow.md`. These are **drafts** for review and paste-in
to Linear; this file is not an auto-publisher. Posting to Linear happens in
the human's lane (Roman/Muse) outside this sandbox.

The five issues are the currently-open items from the lane labels section
in `docs/delegation-workflow.md` (Linear, 2026-10-01), one from each lane
plus the most-active batches:

| Issue | Lane | Status | One-line problem |
| --- | --- | --- | --- |
| JEG-22 | owner:claude | todo (caption batch) | `#curveContext` does not refresh when the bench-share slider moves 15% → 25%; reproduction is in `docs/claude-log.md` 2026-10-01. |
| JEG-23 | owner:claude | in progress | After a scoring/team-shape change the table sometimes stays on the previous shape's rows until the next interaction. |
| JEG-45 | owner:chatgpt | open | The QA-003 lock-revert notice is appended to `#curve-status` then the element's `innerHTML` is overwritten in the same block; the notice never paints. |
| JEG-29 | owner:chatgpt | open | The old headless guard harnesses (`tests/curve_guard_harness.js`, `tests/scale_guard_harness.js`, `tests/ddf_live_reprice_pinned.js`, `tests/two_tier_harness.js`) load `curve-widget.js` against Node's globals, not a real `window`. Rebuild them against the current guard math with the simulation surface `node tools/guard_harness.mjs --simulate tier-mismatch --assert-bad` provides. |
| JEG-17 | owner:chatgpt | open | Full rendered production QA pass of the trade value chart: every one of the 12 scoring × league-size shapes plus the rendered gate, against the build tag from the latest `make sync`. |

The convention requires three concrete command groups per issue (tests,
verify scripts, rendered/output check) plus a negative-test note. Each
section below is paste-ready.

---

## JEG-22 — bench-share caption does not refresh

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_two_tier_frontend
python3 -m unittest tests.test_methodology_payload
python3 -m unittest tests.test_static_export
```

`tests.test_two_tier_frontend` covers `ValueModel.benchShareOf` and the
`#curveContext` rendering path; `tests.test_methodology_payload` pins the
`bench_share: 0.15` default in the published methodology JSON;
`tests.test_static_export` covers the bench-share copy that lands in the
deployed bundle.

### Verify scripts

```bash
python3 pipelines/check_naming_drift.py
```

A naming drift would silently change the bench-share label's role names,
which is the same failure class as the JEG-22 mislabel.

### Rendered / output check

```bash
node tests/rendered_gate/gate.mjs dist --out output/rendered-gate-jeg22.json
```

Must exit 0 with 0 uncaught page errors. The JEG-22 fix is a string update
in `#curveContext`; this command builds `dist/` via `make sync` first and
exercises every scoring × league-size shape, which is the only way to prove
the text actually repaints on slider input.

Additional one-shot check (matches the JEG-22 reproduction in
`docs/claude-log.md` 2026-10-01): a headless Playwright script that loads
`dist/index.html`, drags the bench-share slider from 15% to 25%, and reads
`#curveContext.textContent` — assert the slider value, the display share,
or whatever wording the human copy-decision lands on is reflected (no
stale text from the previous shape).

### Negative-test note

After mutating `app/trade-value-chart/assets/curve-widget.js` to skip the
bench-share text update path (return early before the `textContent`
assignment), `tests.test_two_tier_frontend` must fail on the assertion that
reads bench-share DOM after the slider event, and the rendered check's
Playwright capture must show the stale text. Without that mutation the
guard is asserting current behaviour, not catching the bug.

---

## JEG-23 — table sometimes stays on previous shape's rows

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_dashboard_firstok_unwrap
python3 -m unittest tests.test_dashboard_fleet_counts_sections
python3 -m unittest tests.test_dashboard_labels_no_hardcoded_week
python3 -m unittest tests.test_dashboard_loader_declarations
python3 -m unittest tests.test_dashboard_column_selection_preserved
python3 -m unittest tests.test_dashboard_scale_agreement
```

`tests.test_dashboard_*` cover the table renderer's reload path;
`tests.test_dashboard_firstok_unwrap` covers the first-OK section wrap
that the JEG-23 stuck-table bug actually lives behind.

### Rendered / output check

```bash
node tests/rendered_gate/gate.mjs dist --out output/rendered-gate-jeg23.json
```

The JEG-23 reproduction is interactional (scoring × team × source shape
clicks in a real browser). The 12-shape sweep in the rendered gate is not
yet wired to assert the table refresh, per `docs/claude-log.md` 2026-10-01
("Table-update (JEG-23) ... checks are deliberately not in this gate yet
(Muse scope)"). Until it is, the JEG-23 acceptance also requires the
following one-shot Playwright capture:

```python
# Shape sweep: scoring × teams × source (the interaction that reproduces)
# After each shape click, assert the first row's player_key changes iff
# the shape's source ranking differs. Bake into tests/test_table_refresh.py
# (new file when JEG-23 lands). Until then, paste the Playwright transcript
# into the PR description as the rendered check.
```

### Negative-test note

Reverting the `applyShared` early-return in
`app/trade-value-chart/assets/comparison-dashboard.js` (the same class of
fix that closed JEG-44) must cause the rendered check to log at least one
unrecovered stale-row, and `tests.test_dashboard_firstok_unwrap` must
fail on its stale-shape assertion. JEG-23 and JEG-44 share the
rebuildSourceMaps-before-init root cause, so a single mutation should
catch both.

---

## JEG-45 — QA-003 lock-revert notice is silent

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_lock_revert_notice_render
```

This is the Playwright test written when JEG-45 was filed. It boots a
local HTTP server on `app/trade-value-chart/`, drives `setScoring` /
`setTeams` / `setLockOrder` to force a revert, and asserts `.lock-revert-notice`
is visible with the right text, then auto-dismisses.

### Verify scripts

```bash
python3 pipelines/check_naming_drift.py
```

The notice copy names "USA Today" and "ESPN adjusted" by source key; a
naming drift would silently break the visible text. This is the same
class of guard as the JEG-22 bench-share path.

### Rendered / output check

```bash
node tests/rendered_gate/gate.mjs dist --out output/rendered-gate-jeg45.json
```

The lock-notice check is **not yet wired into the gate**; per
`docs/claude-log.md` 2026-10-01 ("Table-update (JEG-23) and lock-notice
(JEG-45) checks are deliberately not in this gate yet (Muse scope)"). The
acceptance is the `test_lock_revert_notice_render` run above plus, after
`make sync`, the same Playwright transcript against the built `dist/`
(rather than `app/`) so the rendered check matches what production
publishes. Paste the `dist/` transcript in the PR body alongside the
`app/` one until the gate grows a lock-notice assertion.

### Negative-test note

Re-introduce the bug: in `app/trade-value-chart/assets/curve-widget.js`,
make `syncCurveStatus()` overwrite `#curve-status.innerHTML` immediately
after `notifyLockRevert()` appends `.lock-revert-notice`. The Playwright
test must then fail at `page.wait_for_selector(".lock-revert-notice",
timeout=2000)` (the notice never becomes visible because it is overwritten
in the same tick). The pre-fix behaviour is the recorded JEG-45 defect,
not a fresh assertion.

---

## JEG-29 — rebuild the local guard harness against current guard math

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_guard_harness_recorded
python3 -m unittest tests.test_jeg68_starter_markup
python3 -m unittest tests.test_jeg69_direction_check
python3 -m unittest tests.test_anchor_scale_guard
```

`tests.test_guard_harness_recorded` is the canonical regression for the
harness surface. `tests.test_jeg68_starter_markup`,
`tests.test_jeg69_direction_check`, and `tests.test_anchor_scale_guard`
cover the guard math that the rebuilt harness drives.

### Verify scripts

```bash
node tools/guard_harness.mjs --assert-good
node tools/guard_harness.mjs --simulate tier-mismatch --assert-bad
```

These are the two `make guard-harness` calls. The first proves the
current `fixedPieIndexed` guard passes against the current fixture. The
second proves the harness catches a simulated JEG-5 tier-mismatch state —
this is the negative test the harness must demonstrate it can run.

### Rendered / output check

The harness is headless Node, not a UI artifact, so the rendered check is
the JSON output of the harness itself:

```bash
node tools/guard_harness.mjs --json > output/guard-harness-jeg29.json
node tools/guard_harness.mjs --simulate tier-mismatch --json > output/guard-harness-jeg29-simulated.json
```

Paste both JSON files into the PR description. The current-state file
must report `fixedPie.ok: true`; the simulated file must report the ESPN
check `ok: false` with `tierComparison.mismatches > 0`.

### Negative-test note

`node tools/guard_harness.mjs --simulate tier-mismatch --assert-bad` is the
negative test built into the harness; it injects the JEG-5 partition bug
into the live cells and requires the harness to fail the
`fixedPieIndexed` guard. A harness that reports `ok: true` against the
simulated state is asserting current behaviour, not catching the bug.
`tests.test_guard_harness_recorded` extends this by requiring the JEG-5
recorded totals match (within tolerance) so a regression in either the
fixture or the harness math trips the test.

---

## JEG-17 — full rendered production QA pass of the trade value chart

### Tests (run in order; each must exit 0)

```bash
python3 -m unittest tests.test_methodology_consistency
python3 -m unittest tests.test_methodology_payload
python3 -m unittest tests.test_static_export
python3 -m unittest tests.test_public_copy_no_vorp
```

The QA pass proves the published bytes are methodologically consistent
and the user-facing copy is on the right side of the brand/copy rules
(no `VORP`, no FantasyPros/Muse/Meta brand strings, no banned
"the market" phrase). These four tests gate all of that.

### Verify scripts

```bash
python3 pipelines/check_naming_drift.py
python3 pipelines/verify_import_health.py --nfl-week <CURRENT_NFL_WEEK>
```

Naming drift blocks validation by repo rule. `verify_import_health.py`
must report all sources `ok` (not `stale`, `missing`, or `failed`) before
any rendered QA is meaningful — a green gate against stale data is not a
QA pass.

### Rendered / output check

```bash
node tests/rendered_gate/gate.mjs dist --out output/rendered-gate-jeg17.json
python3 verify_live.py tv-$(git log -1 --format=%cI | sed 's/-//g; s/T/-/; s/://g; s/:00Z//' | cut -c1-15)-$(git rev-parse --short HEAD)
```

The rendered gate exercises the local `dist/`; `verify_live.py` exercises
the published GitHub Pages site. Both must exit 0. The build-tag argument
to `verify_live.py` is the actual tag of the production build the QA pass
is reviewing; format is `tv-YYYYMMDD-HHMM-<sha>` (see
`sync_dashboard_artifacts.py::build_tag`, lines 227-242). Paste the
`output/rendered-gate-jeg17.json` plus the `verify_live.py` transcript
into the PR description.

### Negative-test note

This is the QA pass itself, not a fix. The negative-test proof lives in
the rendered gate: every run injects a throw into a copy of `dist` and a
bad DDF pie readout, and requires the gate to catch both
(`tests/rendered_gate/gate.mjs` lines 14-16, 86-108). The
`output/rendered-gate-jeg17.json` must contain `selfTestCaught: true` for
both injected faults, otherwise the gate is asserting current behaviour,
not catching the bug it names. If `selfTestCaught` is `false` for either,
the QA pass is invalid and the PR cannot be approved.

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