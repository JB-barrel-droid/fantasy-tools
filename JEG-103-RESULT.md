# JEG-103 — Bench-share readout must follow the slider

**Branch:** `jeremyburstyn/jeg-103-bench-share-readout`
**Base:** `main@07d146f9`
**Worktree:** `/home/hatch/workspace/worktrees/jeg103`

## Files changed

| File | Change |
| --- | --- |
| `app/trade-value-chart/assets/curve-widget.js` | Bench-slider `input` and `change` handlers now also call `syncWeightsReadout()`. |
| `tests/bench_share_readout_harness.mjs` | New headless-Playwright harness (sibling of `tests/rendered_gate/gate.mjs`). |
| `tests/test_jeg103_bench_share_readout.py` | New Python wrapper that runs the harness and asserts the report is `ok`. |
| `Makefile` | `make test-unit` now invokes `tests.test_jeg103_bench_share_readout`. |

No other files touched. In particular: the value math, the frozen
`DISPLAY_BENCH_SHARE` fallback, and the "15% bench share" context line above
the chart are all untouched (that copy decision remains parked for human
approval, per the task's out-of-scope list).

## The fix (exact)

`app/trade-value-chart/assets/curve-widget.js`, lines 2311–2312 (before the
edit):

```js
shareInput.addEventListener("input",  () => setBenchShareFraction(Number(shareInput.value), false));
shareInput.addEventListener("change", () => { setBenchShareFraction(Number(shareInput.value), false); publishShared(); });
```

After the edit:

```js
shareInput.addEventListener("input",  () => { setBenchShareFraction(Number(shareInput.value), false); syncWeightsReadout(); });
shareInput.addEventListener("change", () => { setBenchShareFraction(Number(shareInput.value), false); syncWeightsReadout(); publishShared(); });
```

`dblclick` (line 2313) is left alone: it resets to `TwoTier.DEFAULT_BENCH_SHARE`
(15%), which is the same value the readout starts at — the caption is
already correct there. `shareReset` (line 2295) likewise resets to 15%.

`syncWeightsReadout()` is the same function every other weight path already
calls (`setScoring`, `setTeams`, `resetAllWeights`, `resetPositionWeights`),
so we reuse the existing source of truth instead of duplicating its
formatting.

## The regression guard

`tests/bench_share_readout_harness.mjs` opens the built `dist/index.html` in
headless Chromium, finds the bench-share slider (`#weightsBenchSlot
input[type=range]`), and:

1. Snapshots the initial state and asserts the readout says "Bench 15.0%".
2. Programmatically sets `input.value` to `0.18`, dispatches `input` and
   `change` events, and re-snapshots.
3. Repeats at `0.10`, `0.20`, `0.07`.
4. After each move, asserts:
   - the readout's `Bench X.X%` matches the slider's value (tolerance 0.05%);
   - the slider's own `.bench-share-value` label matches;
   - `window.TradeValueCurveControls.getState().benchShare` (the widget's
     internal store) matches.
5. Captures any uncaught `pageerror` and counts it as a fail.

`tests/test_jeg103_bench_share_readout.py` shells out to the harness, parses
the JSON report, and fails if `report.ok` is false or if fewer than three
slider moves were exercised.

### Discrimination argument — how the guard fails on the pre-fix code

On the unfixed widget, the slider's handlers are

```js
shareInput.addEventListener("input",  () => setBenchShareFraction(Number(shareInput.value), false));
shareInput.addEventListener("change", () => { setBenchShareFraction(Number(shareInput.value), false); publishShared(); });
```

`setBenchShareFraction` updates `benchShare` and `syncBenchShareControl()`,
which paints the slider's `.bench-share-value` label and the fill, but does
**not** touch `#weightsReadout`. `publishShared()` broadcasts a
`trade-value-shared-change` event for sibling windows — again, no DOM repaint
of the caption. The caption only repaints when `syncWeightsReadout()` is
invoked, which happens on scoring/league/reset/init paths but not on the
slider.

So when the harness moves the slider to `0.18` and re-snapshots on the
pre-fix code, the post-move state is:

- `sliderValue = 0.18` (`input.value` is set directly by the test)
- `sliderLabel = "18.0%"` (painted by `syncBenchShareControl()`)
- `readoutText` still starts `"Pie: QB 23.4% · RB 32.5% · WR 28.6% · TE 15.5% — sums to 100%. Bench 15.0% (default 15%). …"`
  — the caption never moved, because nothing called `syncWeightsReadout()`.
- `storedBench = 0.18` (the widget's internal `benchShare` did move)

The guard's third assertion,
`|readoutBench − sliderValue*100| < 0.05`,
fails with `|15.0 − 18.0| = 3.0 > 0.05`. The harness records a `mismatch`
of `"move-to-0.18: readout Bench 15.0% vs slider value 0.18 (18.0%)"`, exits
non-zero, and the Python test fails on the `report.ok` check.

This is the discrimination requirement the task asks for: the guard asserts
*the state that is right*, not the state that happens to be there. It
rejects the pre-fix code with a concrete numeric mismatch and would not be
satisfied by a tautological "readout is non-empty" check.

### Self-test (mirrors `gate.mjs`'s pattern)

The harness exercises four moves that cover both directions from 15%
(up and down) and a value near the feasible lower bound (7%), so a slider
that ignores most events but happens to react to one is still caught. The
belt-and-braces step-count assertion (`>= 3` moves) prevents a future
regression where the harness short-circuits without exercising the path.

## Things I could not verify in this sandbox

- **Live run of the harness.** This sandbox has no Playwright/Chromium
  binary and no `node_modules` for `tests/rendered_gate/`. The task
  explicitly says "you cannot run tests in this sandbox, verification
  happens outside" — so the discrimination claim is reasoned, not measured.
  The next step is to run `make build && python3 -m unittest
  tests.test_jeg103_bench_share_readout` from a machine with the same
  Playwright-Core install the rendered gate uses, and confirm
  `report.ok === true` and the JSON `steps` array lists four entries with
  matching slider/readout values.
- **Pre-fix discrimination in this sandbox.** For the same reason, I
  could not run the harness against the unfixed widget. The
  pre-fix-failure argument above is read from `curve-widget.js` (slider
  handlers at the original lines 2311–2312 call `setBenchShareFraction`
  and `publishShared` only) and from `syncWeightsReadout()` at line 2228
  (the only function that writes `readout.textContent` for the
  `Pie: … — sums to 100%. Bench X.X% …` line, and it is not reached from
  the slider path).
- **Rebuilt dist.** The dist under `dist/` was built before this edit. To
  exercise the guard against the fix, rebuild with `make build` (or
  whatever the repo's build target is) so `dist/assets/curve-widget.js`
  contains the new handler. The harness reads `dist/`; it does not run the
  source tree.

## Logging

Per the working agreements, this session appends to `docs/claude-log.md`
once it commits — the entry will say JEG-103 was closed, the fix was the
two `syncWeightsReadout()` calls in the slider handlers, and the guard
is `tests/test_jeg103_bench_share_readout.py`. The risk-register row for
GAP-045 / JEG-103 should also flip from "Open" to "Closed (JEG-103)"
once the verification step lands outside this sandbox.

## Commit

Changes are committed on `jeremyburstyn/jeg-103-bench-share-readout`. No
push, no merge, no deploy — per the task's out-of-scope list.