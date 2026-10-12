# JEG-200 — Lineage monitor freshness vs. served chart values

**Lane:** minimax (M3)
**Branch:** `minimax/jeg-200-brief`
**Type:** Implementation brief (draft only — no code, no Linear write)
**Parent:** JEG-200 (Backlog → In Progress on dispatch)
**Sub-ticket:** JEG-202 [Brief] (Todo → In Progress on dispatch)
**Hard boundary:** monitor plumbing only. No value computation changes, no methodology edits, no new scheduled cadence without cost justification.

---

## 1. Problem

The monitoring dashboard's `dist/modules/source-value-lineage.json` is the
machine-readable record of what the chart says each source publishes, built
from the fixture plus a live-page scrape. On 2026-10-02 that artifact
(`generated_at` = `2026-10-02T12:45:09.640835+00:00`, `dist/modules/source-value-lineage.json:2`)
contradicts the served chart fixture
(`built_at` = `2026-10-02T21:21:44.892028+00:00`, `data/fixtures/current/comparison-sources-data.json`)
on the same players: the lineage shows USA Today's JSN `chart_value` 37.28
while the served fixture shows JSN 55.0, and a rank flip on Ceedee Lamb
(55.0 in lineage vs 46.4 in fixture). A live `translate_source('usatoday')`
re-run at ~18:35 CDT confirms the fixture is correct (JSN native 73.0 →
vorp 70.0 → translated 55.0, monotonic). A monitor that contradicts the
product it watches is worse than one that says "stale" — and today, the
lineage silently ships a wrong window that the user can see from the
fixture commits at 07:55 / 08:03 CDT, then was corrected at 08:50 CDT, and
the lineage now preserves the pre-correction state.

## 2. Background

### What exists today

The lineage artifact is produced by
`pipelines/build_source_value_lineage.py` (902 lines total) and consumed
by the source-fidelity monitor on the dashboard. The relevant internals:

- **`build_source_entry()`** at
  `pipelines/build_source_value_lineage.py:485` builds one source's
  `top25` block from the fixture's combo data, snapshot natives
  (`load_snapshot_natives()` at `:131`), and live-page values
  (`load_live_page_values()` at `:54`). Each row carries `chart_value`
  (what renders), `native`, `indexed`, `reweighted`, `implied_vorp`,
  `vorp_replacement_level`, and `ddf_rebuilt` — the three-step
  VORP round-trip is JEG-107.
- **`_compute_vorp_chain_for_source()`** at
  `pipelines/build_source_value_lineage.py:293` calls
  `unified.translate_source()` for published sources
  (`_PUBLISHED_VORP_SOURCES` at `:282`) and computes native / implied_vorp
  / ddf_rebuilt per player, keyed by normalized name.
- **`require_snapshot_natives()`** at
  `pipelines/build_source_value_lineage.py:426` is the fail-closed
  guard: if `data/raw/sources/{fantasypros,usatoday,fantasycalc}/...
  /snapshot.json` are absent, it `raise SystemExit(...)` at `:441-444`.
  This is intentional: the snapshots are gitignored and therefore absent
  in CI (see `SNAPSHOT_PATHS` at `:117-121`), and a degraded builder
  used to silently fall back to the *transformed* combo natives
  (`native` in the fixture is post-translation, not raw scrape), which
  poisoned the live-vs-native comparison (0/25 matches in the
  2026-10-01 incident called out at `:432-435`).
- **Output write** at
  `pipelines/build_source_value_lineage.py:891-893`:
  `os.makedirs(...)` then `json.dump` to
  `dist/modules/source-value-lineage.json`. Top-level `generated_at` is
  taken from the fixture's `generated_at` / `built_at` at `:831`, which
  means the lineage artifact inherits the fixture's clock, not the
  builder's wall-clock at the moment of write.

The VORP refresh that updates the fixture lives in
`pipelines/rebuild_comparison_chain.py`:

- **`run_vorp_refresh()`** at
  `pipelines/rebuild_comparison_chain.py:658` is Stage 9 (JEG-70). It
  runs `pipelines/refresh_vorp_translation.py --check-only` first; if
  grains are stale, it re-runs the translator (`-689`). It is
  **fail-safe, not fail-closed** (`:667-668`): a refresh failure logs
  and never halts the chain.
- **Wiring** at
  `pipelines/rebuild_comparison_chain.py:818-833`: after Stages 7 (fit)
  and 8 (adjusted fixture sections), `run_vorp_refresh(nfl_week, ...)`
  runs with the same fixture inputs. It writes the refreshed fixture
  through the normal promotion path (`run_source()` → `run_fit()` →
  `run_adjusted_sections()` at `:753-816`), so by the time the chain
  exits, the fixture carries the new VORP grains.

The lineage rebuild on the deploy path is the
`pages.yml` step at
`.github/workflows/pages.yml:36-38`:

```
- name: Rebuild source value lineage
  run: python3 pipelines/build_source_value_lineage.py
  continue-on-error: true
```

This step runs **after** `make validate` (`:35`) and **before** the
rendered gate (`:43-60`). It has `continue-on-error: true` because, in
CI, `require_snapshot_natives()` raises `SystemExit` (gitignored
snapshots are absent on the runner), the builder does not write the
file, and the committed artifact from a prior *local* run ships
untouched. That is the documented, intentional behaviour — the comment
chain at `build_source_value_lineage.py:432-435` calls it out, and the
fallback "preserve the committed artifact" is the desired outcome when
the build cannot be reproduced.

### The exact staleness mechanism

1. **2026-10-02 16:21 CDT** — the 6-hourly
   `pipelines/rebuild_comparison_chain.py` run completes Stages 1-8
   successfully, then Stage 9 (`run_vorp_refresh()` at `:658`) detects
   stale grains and refreshes. The chain writes a new fixture to
   `data/fixtures/current/comparison-sources-data.json` with
   `built_at = 2026-10-02T21:21:44.892028+00:00`. JSN's translated value
   flips from 37.28 to 55.0; Lamb's from 55.0 to 46.4.
2. **2026-10-02 17:40-17:48 CDT** — pushes to `main` fire
   `pages.yml`. The "Rebuild source value lineage" step runs the
   builder in CI; `require_snapshot_natives()` raises `SystemExit` at
   `build_source_value_lineage.py:441`; `continue-on-error: true`
   swallows the failure; the committed `dist/modules/source-value-lineage.json`
   (with `generated_at = 2026-10-02T12:45:09.640835+00:00`,
   `source_built_at` for `usatoday` at
   `dist/modules/source-value-lineage.json:3015` = `2026-10-02T12:44:52Z`)
   ships untouched.
3. **2026-10-02 ~18:35 CDT** — local `translate_source('usatoday')`
   confirms the fixture: JSN native 73.0 → implied_vorp 70.0 →
   translated 55.0, monotonic. The lineage artifact disagrees.
4. **Today** — the lineage block at
   `dist/modules/source-value-lineage.json:3008` shows usatoday with
   `source_built_at` predating the fixture by ~8.5 hours and top-25 rows
   whose `chart_value` field contradicts the fixture's `reindexed` /
   adjusted reindexed for the same players. The monitor renders those
   rows as if current.

### What this is *not*

- It is not a VORP-translation bug. `translate_source()` returns the
  correct value locally; the fixture is correct.
- It is not a fixture-promotion bug. Stage 9 wrote the right fixture.
- It is not a Pages-build bug. `pages.yml` ran and shipped the deploy.

It is a **freshness-coordination gap**: the lineage artifact is rebuilt
only on deploy, but the lineage contents are derived from inputs that
change inside `rebuild_comparison_chain.py` (Stage 9) — and the rebuild
path fails-closed by design, so the artifact can only be regenerated
where snapshots exist (locally), not where the deploy runs (CI).

## 3. Scope

### In scope

- Coordination between Stage 9 (VORP refresh in
  `pipelines/rebuild_comparison_chain.py:658`) and the lineage
  rebuild at `pipelines/build_source_value_lineage.py:816`.
- Detection / surfacing of lineage staleness on the dashboard:
  comparing lineage `generated_at` (or per-source `source_built_at`)
  against fixture `built_at`.
- A regression test that fails when the served lineage artifact is
  older than the fixture it describes.
- The fixture-only merge path
  (`merge_fixture_only()` at
  `pipelines/build_source_value_lineage.py:788`) is already designed
  for this case (no raw snapshots, no live scrape, no degraded write)
  and may be reused as-is or extended — read-only consideration here,
  not a contract change.

### Explicitly out of scope

- Any change to `translate_source()` /
  `pipelines/vorp_translation/unified.py`. The translate logic is
  correct; this ticket is about *serving* what it computes.
- Any change to the VORP refresh itself
  (`pipelines/refresh_vorp_translation.py`,
  `run_vorp_refresh()` at `:658`). Stage 9 works; the lineage simply
  does not pick up its output.
- Any methodology, value, or chart-rendering change. No edits to
  `app/trade-value-chart/`, `dist/assets/`,
  `pipelines/rebuild_comparison_chain.py` Stage 7 (fit), or Stage 8
  (adjusted sections).
- Any edit to `dist/modules/source-value-lineage.json` itself other
  than what the rebuild produces. The artifact is generated; hand
  edits are out of contract (see `merge-charter.md` / standing
  constraints on generated artifacts).
- A new scheduled workflow / cron job. Standing rule: scheduled work
  lives in GitHub Actions, and Jeremy audits background compute spend.
  Any new cadence must come with a cost justification in the brief
  (Section 7).
- Credentials, browser automation, vision/OCR, Mac-only files, or
  merge / push / deploy actions. Out of the worker blocklist.

## 4. Acceptance criteria

Each criterion is testable. "Verified by" names the check that proves
it; no criterion is left to assertion-by-current-behaviour.

1. **Served-lineage freshness vs fixture, primary axis.** After any
   successful Stage 9 VORP refresh, the lineage artifact's top-level
   `generated_at` (or the lineage `usatoday.source_built_at` for the
   affected source) is `>= fixture built_at`. *Verified by:* a unit
   test that calls the rebuild entry point with a fixture whose
   `built_at` is later than the existing lineage `generated_at`, runs
   the rebuild, and asserts the new `generated_at` advances past the
   fixture's `built_at`. **OR** the lineage artifact carries an
   explicit staleness badge (see criterion 2) with the lag.
2. **Staleness badge, fallback axis.** When the lineage cannot be
   rebuilt (CI snapshot absence, builder raises at
   `build_source_value_lineage.py:441`), the served artifact carries a
   top-level field — e.g. `stale_relative_to_fixture: true` and
   `lag_seconds` — derived from
   `datetime.fromisoformat(fixture_built_at) - datetime.fromisoformat(lineage_generated_at)`.
   The badge is **explicit**, **non-degrading**, and **never silent**
   (no `null` publish, no zeroed field). *Verified by:* a unit test
   that runs the rebuild with a missing snapshot (raising
   `SystemExit`), loads the resulting artifact, and asserts the badge
   fields are present and the lag is positive.
3. **Regression test: served lineage is not older than the fixture it
   describes.** A new test in `tests/` reads
   `dist/modules/source-value-lineage.json` and
   `data/fixtures/current/comparison-sources-data.json`, computes the
   lag, and fails if `lineage.generated_at < fixture.built_at` AND no
   staleness badge is present. *Verified by:* `python -m pytest
   tests/test_lineage_freshness.py` exits non-zero against the current
   pre-fix `main` (negative-test: simulate the bug by writing a stale
   lineage and a newer fixture into a temp dir, run the test, assert
   it fails). The test must pass against a rebuilt artifact.
4. **USA Today JSN / Lamb lineage matches the chart.** After the fix,
   `dist/modules/source-value-lineage.json` `sources.usatoday.top25`
   shows `chart_value` for "justin jefferson" equal to the fixture's
   reindexed / adjusted-reindexed value for the same combo (currently
   55.0), and "ceedee lamb" at 46.4. *Verified by:* a unit test that
   loads both files, normalises the two players via
   `canonical_players.norm_player_name`, and asserts equality within
   0.01. Against the current pre-fix artifact, the test fails
   (negative-control).
5. **The CI snapshot-absence path stays fail-closed.** The lineage
   step in `.github/workflows/pages.yml:36-38` continues to use
   `continue-on-error: true` *only* when the builder raises; it never
   produces a degraded write. *Verified by:* `make validate` exits 0
   and a new test in `tests/test_pages_workflow_matches.py` asserts
   that `require_snapshot_natives()` is still called and still raises
   `SystemExit` on missing snapshots — not downgraded to a warning.
6. **`make validate` is green** after the fix. The existing unit-test
   suite (whatever is wired into `make validate` today) plus the new
   freshness regression test all pass. *Verified by:* running
   `make validate` from the worktree root.
7. **Freshness is content-vintage, never pull-time.** The lineage's
   `generated_at` continues to reflect the *fixture* vintage (current
   behaviour at `build_source_value_lineage.py:831`), not the wall
   clock at builder invocation. *Verified by:* a unit test that
   inspects the top-level field name and asserts it equals the
   fixture's `built_at` after a rebuild, not the builder's `now()`.

## 5. Relevant files

| Path | Why it matters |
|---|---|
| `pipelines/build_source_value_lineage.py` | Builder. `main()` at `:816`, `require_snapshot_natives()` fail-closed at `:426-444`, `_compute_vorp_chain_for_source()` at `:293`, `build_source_entry()` at `:485`, `merge_fixture_only()` at `:788`, output write at `:891-893`. |
| `pipelines/rebuild_comparison_chain.py` | Stage 9 VORP refresh. `run_vorp_refresh()` at `:658`, Stage 9 block at `:818-833`. This is where the fixture updates without the lineage. |
| `.github/workflows/pages.yml` | Deploy step. "Rebuild source value lineage" at `:36-38` with `continue-on-error: true`. Fails-soft in CI because snapshots are gitignored. |
| `dist/modules/source-value-lineage.json` | Current served artifact. Top-level `generated_at = 2026-10-02T12:45:09.640835+00:00` at `:2`; `live_scraped_at = 2026-10-02T20:37:56.099103Z` at `:3`; usatoday `source_built_at = 2026-10-02T12:44:52Z` at `:3015`. |
| `data/fixtures/current/comparison-sources-data.json` | Fixture. `built_at = 2026-10-02T21:21:44.892028+00:00` (grep). |
| `pipelines/refresh_vorp_translation.py` | Stage 9 worker. Called by `run_vorp_refresh()` at `rebuild_comparison_chain.py:685`. Read for context, not for editing. |
| `pipelines/vorp_translation/unified.py` | `translate_source()` called by `_compute_vorp_chain_for_source()` at `build_source_value_lineage.py:307-310`. Read for context; out of scope. |
| `tests/test_preview_workflow_matches_pages.py` | Existing pattern for workflow-shape regression tests (JEG-133). Reference for new freshness / staleness tests. |
| `docs/claude-log.md` | Session log. Add an entry per standing rule when work ships. |
| `docs/risk-register.md` | Standing issue list. Update if the freshness-coordination gap is durable. |

## 6. Test plan

### New tests (must exist after the fix; negative-tested against the pre-fix artifact)

1. **`tests/test_lineage_freshness.py::test_served_lineage_not_older_than_fixture`**
   — loads `dist/modules/source-value-lineage.json` and
   `data/fixtures/current/comparison-sources-data.json`, parses both
   timestamps, asserts `lineage.generated_at >= fixture.built_at` OR an
   explicit badge. Negative control: copy the current pre-fix lineage into
   a tempdir alongside a fixture with `built_at` 1 hour later; assert
   the test fails.
2. **`tests/test_lineage_freshness.py::test_usatoday_jsn_lamb_matches_fixture`**
   — asserts `sources.usatoday.top25` "justin jefferson" `chart_value`
   equals the fixture's reindexed / adjusted-reindexed for the same
   player within 0.01, and the same for "ceedee lamb". Negative
   control: runs against the current pre-fix artifact; asserts failure.
3. **`tests/test_lineage_freshness.py::test_staleness_badge_present_when_rebuild_raises`**
   — invokes the rebuild entry point with missing
   `data/raw/sources/*/snapshot.json`, captures the resulting artifact,
   asserts the top-level staleness fields are populated and the lag is
   positive.
4. **`tests/test_lineage_freshness.py::test_generated_at_is_fixture_vintage_not_wall_clock`**
   — patches `datetime.now` to return a value 10 minutes after the
   fixture's `built_at`, runs the builder, asserts the output's
   `generated_at` equals the fixture's `built_at`, not the patched now.

### Tests that must still pass (existing surface)

- **`make validate`** from the worktree root — the gate the deploy
  itself runs.
- **`tests/test_preview_workflow_matches_pages.py`** — existing
  workflow-shape regressions; new freshness tests slot into the same
  pattern.
- All tests currently wired into `make validate` (the local
  gate). Any new test must be wired in alongside.
- Any lineage-card tests already covering JEG-107 (VORP round-trip)
  and JEG-98 / JEG-106 (adjusted legs, parent-leg semantics).

### Verification commands

- `make validate` — primary gate.
- `python -m pytest tests/test_lineage_freshness.py -v` — targeted
  freshness regressions.
- Manual `git status` check after the commit: must show only the new
  test file(s) and any minimal builder change (or none, if the
  coordination is achieved by an existing entry point).

## 7. Constraints

### Standing rules that apply (verbatim from the working agreements)

- **Commit and push by default after validation.** Final direction
  decided by Roman on review; this brief does not authorise a push.
- **Every regression guard must prove it catches the bug it names.**
  Negative-tested against a simulated broken state.
- **Never display unvalidated values. Never publish on a known flaw.**
  If `make validate` is red, stop. The lineage staleness is exactly
  the "monitor that contradicts the product" pattern the rule calls
  out.
- **Do not adjust tests to go green.** If a test fails, the default
  assumption is the code is wrong.
- **`make sync` is the single publish path.** No `dist/static`,
  `dist/server`, `space.json`, or `deploy.sh` re-adds.
- **Do not touch `~/Projects/"fantasy tools"`** beyond the
  `Claude outputs/` folder.

### Hard rules for this ticket

- **Fail-closed on missing inputs, never a degraded write.** The
  lineage step in CI must continue to raise (snapshot absence ⇒
  `SystemExit` at `build_source_value_lineage.py:441`) rather than
  silently publish nulls or zeroed fields. The fix must not relax
  that.
- **Freshness = content vintage, never pull time.** `generated_at`
  remains the fixture's `built_at`, not the builder's wall clock.
- **Names resolve through the canonical naming table.** Use
  `canonical_players.norm_player_name` for the JSN / Lamb joins; do
  not hard-code slug mappings.
- **No new scheduled cadence without cost justification.** Standing
  project rule (Jeremy audits background compute spend like spend).
  If the chosen direction (see below) needs a new cron / workflow
  schedule, the brief must add a Section 8 cost note: estimated
  minutes per run × runs per week × runner cost, and a "what this
  replaces or amortises against" line.
- **A monitor that contradicts the product is worse than a monitor
  that says "stale".** The fix must guarantee that when the lineage
  artifact cannot be rebuilt, the served file carries an explicit,
  non-silent staleness signal. Silent stale data is the bug; the fix
  is honest staleness, not perfect freshness.

### Worker blocklist

- No credentials, no tokens, no secrets of any kind in the diff.
- No browser automation, no vision / OCR.
- No Mac-only files, no platform-specific paths.
- No `git merge`, no `git push`, no deploy action.
- **Linear CLI is unavailable in this sandbox.** Do not attempt to
  call it; do not invent ticket IDs.

---

## Candidate directions (presented neutrally)

| Direction | What it is | Cost / risk |
|---|---|---|
| **A. Rebuild inside `rebuild_comparison_chain.py` right after Stage 9.** Same run, same inputs, same fixture vintage. Either call `build_source_value_lineage.py --merge` (the existing fixture-only merge path at `build_source_value_lineage.py:788`) or a new Stage 10 that runs the full builder locally where snapshots exist. | Uses the existing merge entry point; no new scheduling; freshness tracks the fixture 1:1. | Adds a stage to the chain; must remain fail-safe (Stage 9 is already fail-safe at `rebuild_comparison_chain.py:667-668`); must not write a degraded artifact if the lineage builder raises. |
| **B. Keep deploy-path rebuild but badge staleness on the monitor.** Add a top-level `stale_relative_to_fixture` + `lag_seconds` field computed from `fixture.built_at - lineage.generated_at`. The dashboard renders an explicit "STALE — lag Xh Ym" badge instead of contradicting rows. | Smallest blast radius; preserves the existing fail-closed CI path; no new compute. | Still ships a stale artifact; only the dashboard layer changes. The monitor's *contents* remain wrong; the badge only surfaces it. **The user's stated standing rule ("a monitor that contradicts the product is worse than a monitor that says 'stale'") means this direction is the floor, not the ceiling.** |
| **C. Move the lineage rebuild to its own scheduled cadence decoupled from deploy.** | Decouples lineage freshness from deploys; predictable interval. | New cron / workflow = new compute spend. Standing rule requires cost justification (Section 8 note). CI snapshot-absence constraint still applies — the schedule must either vendor the needed snapshots (storage + privacy review) or stay fail-closed with the same staleness badge as B. |

### RECOMMENDATION

**A + B combined.** A is the fix (Stage 10 in
`pipelines/rebuild_comparison_chain.py` runs `python3
pipelines/build_source_value_lineage.py` locally where snapshots exist,
writing the fresh artifact; if the builder raises, the existing
fail-closed path leaves the committed file alone and B's badge surfaces
the lag). B is the floor (the staleness badge is the honest signal
when the builder cannot run). C is rejected on cost — it adds a new
schedule without amortising against existing compute, and standing
rules require a cost note we do not have justification for.

Direction is decided by Roman on review; this brief presents the
options neutrally.

---

## Result contract

- **What I read:** `pipelines/build_source_value_lineage.py`
  (full file, 902 lines), `pipelines/rebuild_comparison_chain.py`
  (Stage 9 region, lines 655-855), `.github/workflows/pages.yml` (full
  file, 67 lines), `dist/modules/source-value-lineage.json` (top-level
  metadata + usatoday section at lines 1-30 and 3008-3108),
  `data/fixtures/current/comparison-sources-data.json` (top-level
  timestamps).
- **What I wrote:** `docs/briefs-draft/JEG-200-lineage-freshness.md`
  (this file).
- **What remains unverified:** the exact `fixture_built_at` /
  `lineage_generated_at` lag against the *current* pre-fix artifact is
  read from disk and matches the problem statement, but I did not
  re-run `translate_source('usatoday')`; the 18:35 CDT confirmation in
  the problem statement is the source of truth for the live monotonic
  check.
- **Commit SHA:** `d29632a526db268eeba5711d68e71881f88ea6a8`
  (commit message: `JEG-200: draft implementation brief (minimax M3)`,
  branch `minimax/jeg-200-brief`, ahead of `origin/main` by 1 commit;
  not pushed — push is out of scope for the brief-draft sub-ticket and
  pending Roman review of the recommended direction).