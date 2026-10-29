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

### JEG-1296 (correction child of the independent Claude review): the fixture follows JEG-1282 (#1149)

#1149 fixes both suite defects: the aria-sort mutant removes the whole statement, check() ranks only known verdicts, and the
guard names each mutant's own check instead of catching exceptions. Once it is on main this branch merges main, and then:

- **no aria-sort:** #1149's whole-statement find, `expect: killed`. It takes the variant's designation and its ordered consequence
  (`DDF Value ascending, dashes last: [] [...]`, values ascending with dashes last). The variant is dropped.
- **no verdict text:** `expect: killed`. The designation is now every verdict cell empty. The three checks that read the same
  verdict text are its consequences, each pinned to the empty verdict:
  - the defense row at 1366 and 390: every value cell still a dash, `'verdict': ''`, and the not-evaluated reason;
  - the Verdict header sort at 1366;
  - the phone card banner at 390, which is the same `verdictTag` (`waivers.js:709`).
- Each entry keeps a `note` on how it failed at 430791c4.

Result with #1149 merged: all eight are killed by their own check. Table above is history.

Failing before, passing after (2026-10-29, local Google Chrome, `RENDER_TESTS_REQUIRED=1`). Before the fix, #1149 (87b4f7b4) is
merged into e094d6aa:
- Offline, old fixture: 1 failure, `test_fixture_mirrors_the_suite_mutation_table (mutation='no aria-sort')`. The suite's `find`
  is the whole statement; the fixture still holds the call alone.
- Offline, new fixture: 21 OK. The new `test_verdict_text_consequences_are_pinned_to_the_empty_verdict` fails on the old
  fixture (no consequences, so the observed run is harness) and passes now. A non-empty verdict cell, a priced or given-a-verdict
  defense row, a changed reason, a non-DEF row or a card-banner line at 1366 all stay out of `killed`.
- Chromium, `python -m unittest -v tests.test_waivers_mutation_specificity`: 27 OK, 0 skipped, 268 s. All eight mutants are
  `killed`, the restored control passes and the four injected failures are still `harness`.

On the branch after #1149 merged (squash 99be687d): `origin/main` f57040e8 merged in normally as d9e087de, then the two
prepared commits applied unchanged.
- Before them, the offline classes fail once: the same mirror-test failure on "no aria-sort".
- After them: 21 offline OK and `tests.test_run_suite` OK. Chromium with `RENDER_TESTS_REQUIRED=1`: 27 OK, 0 skipped, 273 s,
  with all eight killed, the restored control passing and the four injections still `harness`.
- `tests.test_render_sweep_coverage` lists the same five unwired render modules on main and on this branch.

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
  24 tests OK, 0 skipped, 320 s, on b962c417. That is 18 offline tests and 6 Chromium tests (the baseline, the mutants plus the
  restored control, and the four injections). After the Codex round-1 fix: 26 OK (20 offline, 6 Chromium), 0 skipped, 309 s,
  with the same verdict for every mutant.
- `RENDER_TESTS_REQUIRED=1 python -m unittest -v tests.test_waivers_render`, unchanged: 2 tests OK, 211 s. Its guard calls all
  eight caught, including the two harness kills above.
- Ad hoc, not committed: a fixture anchor with one extra space fails
  `test_every_fixture_anchor_applies_once_to_the_production_source` (`StaleAnchor: ... occurs 0 times`) and
  `test_fixture_mirrors_the_suite_mutation_table`.
- The hashes of `waivers.js`, `waivers.css`, the suite, `_render_env.py` and the fixture are the same before and after the
  mutant run (asserted in the test).

Assumed: the result on CI's bundled Chromium matches, since nothing in the classification depends on the browser build.

### Codex review, round 1 (PR #1144, two P2 findings on b962c417), both fixed on this branch
- **The card-layout consequence accepted any unclassed button.** Search-result buttons have no id or class either
  (`waivers.js:614`), so `"button#. 'Saquon Barkley · RB' 100x20"` passed as part of the table showing on phones. The pattern
  now lists only the seven sortable header labels at the 32 px `min-height` of `thead th button`, in proper list form. The
  Remove-button designation gets the same list form.
- **The aria-sort variant's sort consequence accepted unsorted numbers.** `DDF Value ascending, dashes last: [] [3.0, 1.0, 2.0,
  None]` counted as a consequence of the missing aria-sort. An entry can now name a `values` order. The classifier
  `literal_eval`s the `(?P<values>...)` group and requires real numbers in that order, with at least one dash on the named side.
  The variant's consequence requires ascending with dashes last. "dashes sorted first" now requires dashes first with the
  numbers correctly sorted, so a second broken sort on top of it is a harness failure.

Failing before, passing after:
- `FixtureOfflineTests.test_card_layout_consequence_lists_only_the_header_sort_buttons` and
  `test_sort_consequence_and_designations_need_a_correctly_ordered_payload` are new. They failed on b962c417 (10 sub-cases
  `killed` where `harness` is wanted, including both of Codex's examples) and pass after the fix. The observed Chromium lines
  are still `killed`.

### Wiring (coordinator, 2026-10-29 20:17 UTC: "Codex is out, so the CI wiring doesn't wait on Codex. Add the proposed test-unit-modules line on the same branch as part of the JEG-1296 correction.")
`test-unit-modules` now runs, right after `python3 -m unittest tests.test_waivers_render`:

    python3 -m unittest -v tests.test_waivers_mutation_specificity

It takes about five minutes in Chromium. The log prints one `MUTANT <verdict> legacy=<caught|missed>` line per mutant (stderr).
`tests.test_run_suite` passes with the line. `tests.test_render_sweep_coverage` shows the same five unwired render modules as
main, which this does not change (the module has no `render` in its name). Not wired into `test-core`; the offline classes need
no browser and could go there:

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
