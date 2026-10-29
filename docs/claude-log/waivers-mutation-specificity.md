## 2026-10-29 - JEG-1279 Waivers render mutations: a kill must be the mutant's own check

Ticket JEG-1279 (parent JEG-1022), branch `claude/waivers-mutation-specificity`, base `origin/main` 430791c4. New files only:
`tests/test_waivers_mutation_specificity.py`, `tests/fixtures/waivers-mutation-specificity.json`, this log.

### The false green
`tests/test_waivers_render.py::test_guard_fails_on_broken_builds` serves eight broken copies of `app/v2/waivers.js` /
`waivers.css` and counts a mutant as caught when `run_checks` returns any error, or raises anything (`except Exception`, which the
test turns into one error line). So each of these reads as a kill:

- no browser: `_render_env.unavailable` raises `unittest.SkipTest` locally (an `Exception`) and `RuntimeError` under
  `RENDER_TESTS_REQUIRED=1`; both become a nonempty error list. With no browser at all, the guard passes all eight.
- a navigation or readiness timeout (`playwright TimeoutError`);
- a page error from something else on the page;
- any failed check that is not the one the mutant breaks.

### What the new module does
`run_checks` is imported from the suite unchanged; nothing in the suite, `waivers.js`/`.css` or `tests/_render_env.py` is edited.
A mutant counts as killed only when the clean baseline returned `[]` first, its anchor occurs exactly once in the production
source, `run_checks` returned a list (any exception is a harness failure), its designated diagnostic fired at every width the
fixture names, and every other line is a consequence the fixture lists for that mutant with a reason. A page error line is always
a harness failure, whatever a pattern says. After the eight mutants, the original files served through the same override route
must pass (restored control).

The fixture's eight mutants are compared with the suite's `broken` table, read from its source with `ast` (not imported, not
run), so a mutant added, renamed or re-anchored in the suite fails this module by name until the fixture follows.

### Result at main 430791c4 (Chromium, 1366x768 and 390x844, as the suite's guard runs)

| Suite mutant | This module | Designated diagnostic (consequences allowed) |
|---|---|---|
| no headline text | killed | `headline reads 'Values are still loading. ...'` at both widths (the empty-tab headline check reads the same placeholder) |
| no card layout | killed | `[390] phone layout: table True cards True` (the table's sideways scroll and its 32 px header buttons at 390) |
| no aria-sort | **harness: TimeoutError** | intended `[1366] aria-sort after one click: []`; never reached |
| dashes sorted first | killed | `[1366] DDF Value descending/ascending, dashes last: [None, ...]` |
| settings listener removed | killed | `the league-settings event did not redraw the tab` at both widths |
| no grid role | killed | `[1366] table role None labelled by v2WaiversHeadline` |
| remove buttons 20 px tall | killed | `[390] controls under 44 px ...` listing only the Remove buttons at 20 px |
| no verdict text | **harness: ValueError** | intended `verdict cells [...]`; appended, then lost |
| variant: no aria-sort, whole statement | killed | `[1366] aria-sort after one click: []` (and the ascending check's aria-sort) |

The suite's own guard calls all eight caught.

The two harness kills, filed as JEG-1282 for the suite's owner:

- **no aria-sort.** The anchor removes only the statement after `if (S.sort.key === col.id)` (`app/v2/waivers.js:718`). That `if`
  then guards the `if (col.sort) {...}` block that builds the header buttons, so the DDF Value click waits 30 s and raises.
  aria-sort is never checked.
- **no verdict text.** `check()` appends `verdict cells [...]`, then ranks the verdicts with `order.index(v)`, which raises on the
  empty cell. Any verdict outside the six names does the same, so no verdict-text mutant can return its diagnostic until that
  line skips unknown verdicts.

The fixture records both as `expect: harness`, with the exact exception type and message. When JEG-1282 lands, the mirror test
fails by name and both entries must change to `killed`.

### Injected harness failures (real harness, real Chromium), none killed

Each is also called caught by the old rule.

- **Browser unavailable.** `CHROMIUM_PATH` points at a text file. This gives `RuntimeError` under `RENDER_TESTS_REQUIRED=1` and
  `SkipTest` without it.
- **Navigation timeout.** `waivers.js` polls the page every 100 ms, so `page.goto(networkidle)` raises Playwright `TimeoutError`.
- **Unrelated page error.** A timer throws on top of "settings listener removed". The run is harness, and the same run without
  the page-error lines is a kill.
- **Unrelated diagnostic.** "no headline text" and "no grid role" are applied together and judged as "no headline text". The grid
  line is the stray, and without it the run is a kill.

### Commands and results
Verified (2026-10-29, macOS, Python 3.12, Playwright 1.63 driving Google Chrome; base 430791c4):

- `CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" RENDER_TESTS_REQUIRED=1 python -m unittest -v tests.test_waivers_mutation_specificity`:
  24 tests OK, 0 skipped, 320 s. That is 18 offline tests and 6 Chromium tests (the baseline, the mutants plus the restored
  control, and the four injections).
- `RENDER_TESTS_REQUIRED=1 python -m unittest -v tests.test_waivers_render`, unchanged: 2 tests OK, 211 s. Its guard calls all
  eight caught, including the two harness kills above.
- Ad hoc, not committed: a fixture anchor with one extra space fails
  `test_every_fixture_anchor_applies_once_to_the_production_source` (`StaleAnchor: ... occurs 0 times`) and
  `test_fixture_mirrors_the_suite_mutation_table`.
- The hashes of `waivers.js`, `waivers.css`, the suite, `_render_env.py` and the fixture are the same before and after the
  mutant run (asserted in the test).

Assumed: the result on CI's bundled Chromium matches, since nothing in the classification depends on the browser build.

### Proposed wiring (Codex owns the Makefile; not edited here)
In `test-unit-modules`, after `python3 -m unittest tests.test_waivers_render`:

    python3 -m unittest -v tests.test_waivers_mutation_specificity

It takes about five minutes in Chromium. The `-v` log prints one `MUTANT <verdict> legacy=<caught|missed>` line per mutant. The
offline classes need no browser and could also go in `test-core`:

    python3 -m unittest tests.test_waivers_mutation_specificity.ClassifierOfflineTests tests.test_waivers_mutation_specificity.AnchorOfflineTests tests.test_waivers_mutation_specificity.FixtureOfflineTests

### Limitations
- Run locally on macOS with Google Chrome (`CHROMIUM_PATH`, also needed by the sync's values-explainer step). CI's Playwright
  1.49.1 bundled Chromium was not run, because the module is not wired yet.
- The designated patterns pin the wording of `check()`'s diagnostics. A reworded diagnostic fails this module by name, which is
  intended.
- The verdict-text behaviour has no clean kill until JEG-1282 changes the suite.
- The navigation-timeout injection runs at 1366 only, to keep it to one 30 s timeout.
- `_render_env.ensure_built()` regenerates `app/` and `dist/` in the checkout, as the suite does. None of that output is
  committed here.
- A passing local fixture says nothing about the live site.
