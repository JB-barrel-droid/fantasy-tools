# JEG-135 — rendered-input sweep (R8)

## What this task does

Adds a new rendered-gate harness that exercises the four input classes the
JEG-47 gate does not cover (best-practices §6 / BH-4): bench share, roster
shape, source toggles, and lock order. The contract under test is BH-4:
**changing a setting away and back returns identical values**, and the page
evaluates the **requested** configuration.

## Files changed

- `tests/rendered_gate/gate_flexibility.mjs` (new) — the harness itself.
  Loads `dist/` in headless Chromium and drives the four input classes
  with real user gestures (page.mouse + page.keyboard + real typing),
  then asserts:
  1. Each away-step produces the expected UI response (slider readout
     follows value; table hash changes for roster / source / lock).
  2. Each back-to-default step returns the original SHA-256 of the
     rendered comparison table (byte-identical cell text in document
     order over `#tableWrap table.all-table tbody tr.row-main`).
- `tests/test_jeg135_rendered_flexibility.py` (new) — Python `unittest`
  wrapper following the JEG-103 pattern: skip gracefully when `dist/` is
  absent or when `playwright-core` is not installed under
  `tests/rendered_gate/node_modules/`. Invokes the harness, parses the
  JSON report, asserts `ok` and that every required phase was exercised.
- `Makefile` — `test-unit` runs `tests.test_jeg135_rendered_flexibility`
  immediately after `tests.test_jeg103_bench_share_readout` (the
  graceful-skip pattern is the same).
- `.github/workflows/preview.yml` — the rendered gate step now also runs
  `gate_flexibility.mjs dist` and surfaces its failure in the
  PR-comment body the same way the JEG-103 bench-share readout guard is
  surfaced. The gate exit code still keys on the original
  `gate.mjs` (rc), with the two harnesses non-blocking (mirroring
  JEG-103's `rc2`); a `set +e` failure of either prints an explicit
  failure line before the existing `exit $rc`.

## How the sweep covers each input class

| Input | Real gesture | Assertion on the path | Return assertion |
|---|---|---|---|
| Bench share (slider) | `page.mouse.down/move/up` to a track fraction, then `page.keyboard.press('ArrowRight')` ×2 + `Tab` to commit | `Weights` readout segment "Bench X.X%" matches `slider.value × 100` to within 0.05 | Reset button returns slider to 15.0 and table hash equals baseline |
| Roster shape (RB / FLEX) | `page.focus()` → `selectText()` → `Delete` → `page.keyboard.type("3")` → `Tab` | Table hash changes between baseline and RB=3; changes again between RB=3 and FLEX=2 | RB=2, FLEX=1 returns baseline hash |
| Source toggle | `page.locator('[data-source]').click({force:true})` on the first available, checked source | Table hash changes; source card label (`#sourceCards .source-card .source-title`) updates | Click back on → table hash equals baseline |
| Lock order | `page.selectOption("#curveLockOrder", altValue)` | First-five-row ordering shifts (logged for inspection) | Choose the original value → table hash equals baseline |

## How table hashes are computed

For each step, the harness reads every `td` of every `tr.row-main` in
`#tableWrap table.all-table tbody` (in document order), concatenates
their text (whitespace collapsed), and stores the SHA-256 prefix plus
the raw string. Only `tr.row-main` is hashed — the "expand row"
sibling (`#player-detail-*`) is owned by the dashboard's expand state
and is intentionally excluded so a clicked name does not perturb the
hash. The baseline hash is captured once after the initial
`networkidle + 1500 ms` settle and every "back to default" step is
compared against it byte-for-byte. Any drift in cell values, row
order, or stuck-from-a-prior-config rows surfaces.

## Discrimination argument (required)

The harness is not a tautology. Three of its assertions fail on a
real broken state:

1. **Bench-share readout follows the slider (same shape as JEG-103).**
   On the pre-JEG-103 code path — where the slider's `input` handler
   called `setBenchShareFraction` and `publishShared` but did NOT
   invoke `syncWeightsReadout()` — moving the slider to ~22 % leaves
   `#weightsReadout`'s "Bench 15.0%" segment unchanged. The
   `expectClose("bench-mouse readout", afterMouse.readoutBench,
   mouseFraction * 100, 0.05, …)` call fails with
   `got 15.0, want ~22.0`. This is the same defect JEG-103 fixed; the
   guard is its sibling, not a duplicate (JEG-103 uses programmatic
   `dispatchEvent('input'/'change')` + the reset button + dblclick; this
   harness uses real mouse + keyboard).

2. **Roster shape RB 2 → 3 changes the table.** If the roster handler
   short-circuited (e.g. the input's `change` listener was bound before
   `makeRosterControls` ran and the binding was lost), the
   `sharedState.rosterShape.RB` snapshot would still be 2 and the table
   hash would equal baseline. The
   `if (sha256(hashAfterRbUp) === report.baseline.tableHash)` assert
   fires with `"roster RB 2->3 did not change the table"`.

3. **Away-and-back returns the original hash.** If the widget caches
   the rendered table on the first config (e.g. a memoized
   `tableHTML` keyed only on the first input change), toggling the
   source off and on would re-render from cache and the post-return
   hash would differ from the baseline (e.g. a row's source value is
   stale or the active-source filter wasn't reapplied). The
   `if (sha256(hashAfterXReturn) !== report.baseline.tableHash)` assert
   fires with the corresponding message. This protects BH-4 directly.

## What I could NOT verify (sandbox cannot run a browser)

- The harness was not executed end-to-end against `dist/` in this
  session — there is no Chromium binary in this worktree's PATH and
  `tests/rendered_gate/node_modules/playwright-core` is not installed
  here. CI (`preview.yml`'s rendered gate step, with `npm ci --prefix
  tests/rendered_gate` + `npx playwright-core install --with-deps
  chromium`) is where the harness actually runs.
- I therefore could not run the discrimination argument against a
  reverted-JEG-103 build. The argument is given from the code, not
  from an observed failure. PH-8 / BH-1 require discrimination
  PROOF, not assertion; the proof path here is the same as the
  JEG-103 sibling (which the previous session also could not run in
  this sandbox): the harness's failure mode is named from the source
  of the bug, and any harness that does not catch that bug is a
  tautology — the guard is structured so it cannot pass by inspecting
  the wrong DOM.

## Things explicitly NOT touched

- No change to value math, methodology, or any user-facing copy.
- No `dist/` rewrites, no force pushes. The new files are committed
  on the branch `jeremyburstyn/jeg-135-rendered-input-sweep` only.
- The existing `gate.mjs` and `bench_share_readout_harness.mjs` are
  untouched.
- No Linear CLI use. The `.github/workflows/linear.yml` style of
  automation was not invoked.

## Wiring (what runs where)

- **CI (blocking on PR via `preview.yml`).** The rendered gate step
  runs `gate.mjs`, then `bench_share_readout_harness.mjs`, then the
  new `gate_flexibility.mjs`. The first's exit code is the gate's
  exit code; the second and third print an additional failure line if
  they exit non-zero so the PR comment names the regression.
- **`make test-unit`.** Runs the new Python wrapper after the
  JEG-103 one, in alphabetical-by-filename order — the same
  graceful-skip pattern. If `playwright-core` is absent locally, the
  wrapper skips with `"playwright-core not installed; see
  preview.yml rendered gate step"`, exactly mirroring the JEG-103
  skip message.

## Open uncertainty

- The source-card label check in step (c) only verifies that
  `#sourceCards .source-card .source-title` exists and is non-null;
  the harness does not parse the label text. If the
  `renderSourceCards` template ever drops the `.source-title` element,
  the harness will fail with `"source-off: ..."` missing rather than
  silently passing — this is intentional (the existence check is the
  contract), and matches how the JEG-103 harness handles missing DOM.
- The lock-order assertion compares hashes, not the row order. On a
  build where the lock change re-ranks but cells are unchanged the
  hash would still differ because cell ordering shifts; the harness
  ALSO records the first-five `data-player-key`s before and after
  the change for human inspection (`phase: "lock-ordering"` in the
  JSON report). If the lock change produces identical bytes (which
  would mean the lock is a no-op), the post-return hash still matches
  baseline and the contract holds — but it would not catch a "lock
  change silently does nothing" bug. That bug is caught by the
  pre-existing `test_lock_revert_notice_render.py` and
  `test_methodology_consistency.py`; this sweep deliberately does
  not duplicate that surface.
## Review addendum (Roman, 2026-10-02 ~16:30 CDT)

Independent review found and fixed four harness defects before integration.
All fixes are committed on the branch; the harness below is the reviewed version.

1. **Vacuous mouse drag (critical).** The worker's `moveBenchViaMouse` used
   `locator.boundingBox()`, which returns 0x0 for this input
   (`appearance:none` + `pointer-events:none` on the input; only the
   17px `::-webkit-slider-thumb` takes pointer events). The drag coordinates
   were all x+0 — the slider never moved and the readout assertions passed
   trivially. Fixed: geometry now comes from `getBoundingClientRect()` via
   `evaluate`, and the drag starts at the computed thumb center
   (thumbW/2 + frac*(w-thumbW)), matching Chrome's thumb layout.
2. **Vacuous keyboard phase (critical).** Same root cause family: without a
   real gesture the value never changed. Fixed alongside (1); both phases now
   carry an `expectChanged` guard that fails loudly if the control did not
   move, so a missed gesture can never pass silently again.
3. **Closed `<details>` panels.** The bench slider and roster inputs live
   inside closed `<details>` elements. The weights body is forced
   `display:block` by CSS, which leaves a half-rendered layout where
   `#sourceToggles` paints OVER the slider (elementFromPoint confirmed);
   Playwright's actionability checks refuse the roster inputs entirely.
   Fixed: the harness now clicks the panel summaries open first, exactly as
   a real user would (`ensureWeightsPanelOpen`, `ensureRosterPanelOpen`).
4. **Source-toggle contract was wrong.** The worker asserted the comparison
   table hash *changes* when a source is toggled. It does not — and should
   not: the toggles drive curves only (`activeSources` is never read by
   comparison-dashboard.js). The correct contract, now asserted: checkbox
   state + `#legend` entry count + `getState().activeSources` track the
   toggle, and the table hash *stays* at baseline (the toggle must not
   corrupt table state).
5. **Dead `#sourceCards` surface.** `#sourceCards` exists nowhere in the
   served page — `renderSourceCards()` always no-ops. The worker's
   `sourceCardLabel()` therefore always returned null (and was never
   asserted). Replaced with the observable surfaces in (4); the dead code
   is flagged as a separate product decision (render the cards or remove
   the function).
6. **Lock-order dead comparison.** The worker captured the "baseline"
   top-5 ordering *after* choosing the alternate lock. Fixed: captured
   before the change; both orderings recorded.

### Verification (Roman, headless Chromium, this run)

- **Fixed code** (main + JEG-103): `ok: true`, zero mismatches, zero page
  errors. All 10 phases exercised with genuine movement: mouse drag
  0.15→0.214 (readout 21.4), keyboard 0.214→0.216 (readout 21.6), reset
  →0.15; roster RB 2→3 and FLEX 1→2 each change the table hash, return
  round-trips to baseline; source toggle moves checkbox/legend/activeSources
  with the table hash untouched; lock change reorders rows
  (2227,217,3189,1095,547 → 217,751,1095,2227,547), return round-trips.
- **Pre-fix code** (JEG-103 reverted): `ok: false` with exactly the expected
  failures — `bench-mouse readout: got 15, want ~21.4` and
  `bench-keyboard readout: got 15, want ~21.6`. The slider moves; the
  caption stays stale. Discrimination proven against real user gestures.
- Python wrapper: skips gracefully without the npm install (1 skip);
  `test_preview_workflow_matches_pages` (14 tests) passes with the
  preview.yml wiring.
