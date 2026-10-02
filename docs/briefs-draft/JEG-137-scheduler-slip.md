# JEG-137 — R10: scheduler slip in every freshness limit

- Lane: minimax (M3)
- Branch: minimax/jeg-151-brief
- Parent: JEG-137 (health program, child of JEG-78)
- Audit anchor: JEG-83 section 6 R10
- Standard: PH-4 (`docs/health/best-practices.md:63`)
- Risk: GAP-046 (`docs/risk-register.md:61`)
- Decision: Jeremy's D4 — freshness limits follow the NFL week and each source's measured publication timing, not fixed day counts (`docs/health/best-practices.md:46`, DH-1)

## 1. Problem

Scheduled workflows on GitHub Actions routinely start up to about six hours after
their intended cron time. The freshness limits in `check_deadlines.py` and the
per-source cards in the trade-value chart are clocked only against the
publication window — they ignore how late the runner woke up. That produces two
opposite false verdicts on the same incident: a six-hour-late scheduled run is
flagged red as "missed window" (false red), and the same run is also treated
as fresh when it is actually six hours behind (false green, because the write
satisfied the publication window in isolation). Verified 2026-10-02:
ESPN cron 11:30 UTC ran at 17:26 and 16:45 UTC; FantasyCalc cron 11:45 UTC ran
at 17:29 and 16:50 UTC (`docs/risk-register.md:61`, GAP-046).

## 2. Background

What exists today:

- Per-source publication windows live in
  `pipelines/lib/publication_windows.py:43` (`PUBLICATION_SCHEDULES`). Each
  source has `grace_days`, `notes`, and a `measurement_provenance` block
  (lines 49–53, 64–69, 76–80, 87–91, 98–103, 109–114). These are R4's
  measured publication timing, used by `get_publication_status` at
  `pipelines/lib/publication_windows.py:119`.
- The deadline checker reads the same dict and converts `grace_days` to
  minutes inside `grace_window_minutes` at
  `pipelines/check_deadlines.py:104`. The function is intentionally the
  seam for R10 — it is the single place that turns a publication-window
  rule into a minutes budget (`pipelines/check_deadlines.py:107`, comment).
- The chain status artifact is
  `output/comparison-chain-status.json`. It currently carries `run_at`
  (line 2), `nfl_week`, `runner`, `sources`, and `success`. It does **not**
  carry the scheduled cron time or the actual start of the Actions run.
- The chain runs on `workflow_dispatch` only
  (`.github/workflows/rebuild-chain.yml:16`); it is dispatched by
  `source-vintage-check.yml` when DB content vintage differs from fixture
  vintage (`.github/workflows/rebuild-chain.yml:13-15`, JEG-76 comment).
  Both the dispatch time and the GitHub Actions run-start time are
  available to the workflow.
- The trade-value chart mirrors the same schedule in JS at
  `app/trade-value-chart/index.html:2249-2256` (`PUBLICATION_SCHEDULES`
  with `graceDays`) and renders badges via `vintageBadgeState` at
  `app/trade-value-chart/index.html:2263-2304`. The chart currently has
  no concept of slip — a six-hour-late scheduled run is invisible.
- PH-4 at `docs/health/best-practices.md:63` requires idempotent,
  content-keyed runs and forbids retrying review holds. This is unrelated
  to R10's grace math but is the health standard the freshness report
  must keep satisfying.

## 3. Scope

In scope:

- `pipelines/lib/publication_windows.py` carries two new per-source fields:
  `slip_observed_max_minutes` (the largest `started_at − cron_at`
  measured) and `slip_measured_at` (when that measurement was taken).
- The deadline checker (`pipelines/check_deadlines.py`, R2) reads both
  fields and adds `slip_observed_max_minutes` to the per-source grace
  window in `grace_window_minutes`
  (`pipelines/check_deadlines.py:104`).
- Each scheduled workflow records `started_at` (GitHub Actions run start)
  and `cron_at` (cron expression evaluated to intended fire time) in
  `output/comparison-chain-status.json` (currently only `run_at` at
  `output/comparison-chain-status.json:2`).
- A new helper reads the workflow's run history via the Actions API and
  writes the per-source slip measurement into the publication-window
  table.
- A source without measured slip uses a 6-hour default. The monitor card
  shows `slip: default 6h (unmeasured)`.
- A slip measurement older than 30 days is flagged for re-measurement.
  The monitor card shows `slip: stale measurement (>30d)`.
- The monitor's per-source card shows the slip-adjusted grace and the
  measured slip.

Explicitly out of scope:

- Fixing the scheduler itself (GitHub-side).
- A real-time schedule-missed alert. Per D3
  (`pipelines/check_deadlines.py:7-8`, comment), no alert recipient — no
  messages, no callbacks, no third-party integration. Slip is a number
  the deadline checker reads; it is not a notification.
- R4's measured publication timing. R4 measures publication cadence
  (`pipelines/lib/publication_windows.py:43`, `PUBLICATION_SCHEDULES`);
  R10 layers observed scheduler slip on top. The two are tracked
  separately.
- Changing the chain interval or scheduling cadence.

## 4. Acceptance criteria

Each is testable by running something.

1. `pipelines/lib/publication_windows.py:43` carries both
   `slip_observed_max_minutes` and `slip_measured_at` on every entry of
   `PUBLICATION_SCHEDULES`. Verifiable by reading the file and by
   importing it.
2. `pipelines/check_deadlines.py:104` (`grace_window_minutes`) returns
   `grace_days * 24 * 60 + slip_observed_max_minutes` for a source whose
   slip is measured. Verifiable by importing the function and asserting.
3. `output/comparison-chain-status.json` carries `started_at` and
   `cron_at` fields alongside the existing `run_at`
   (`output/comparison-chain-status.json:2`). Verifiable by reading the
   artifact after a chain run.
4. A simulated broken state A — a 6-hour-late scheduled run — is **not**
   flagged `red` by `determine_source_state`
   (`pipelines/check_deadlines.py:122`). Today's behaviour fails this
   (6 h > 24 h grace_window_minutes? no — the grace is per-day; the test
   is run against the publication-window end-of-day boundary plus the
   measured slip).
5. A simulated broken state B — a 24-hour-late run — **is** flagged
   `red` by `determine_source_state`
   (`pipelines/check_deadlines.py:122`) after the slip-adjusted grace is
   applied.
6. A source without `slip_observed_max_minutes` uses a 6-hour default.
   The monitor card label is `slip: default 6h (unmeasured)`. Verifiable
   by inspecting the rendered card and by unit test.
7. A `slip_measured_at` older than 30 days is flagged stale. The card
   label is `slip: stale measurement (>30d)`. Verifiable by date
   arithmetic in a unit test and by inspecting the card.
8. The per-source card on the trade-value chart
   (`app/trade-value-chart/index.html:2263`) shows the slip-adjusted
   grace and the measured slip.
9. `make validate` is green. This is the deploy gate; a red local run
   blocks publish.

## 5. Relevant files

- `pipelines/lib/publication_windows.py` — add
  `slip_observed_max_minutes` and `slip_measured_at` to each entry in
  `PUBLICATION_SCHEDULES` (`pipelines/lib/publication_windows.py:43`).
- `pipelines/check_deadlines.py` — extend `grace_window_minutes`
  (`pipelines/check_deadlines.py:104`) to add the measured slip;
  pass it into `determine_source_state`
  (`pipelines/check_deadlines.py:122`) for the verdict.
- `.github/workflows/rebuild-chain.yml` — record `started_at` (Actions
  run start) and `cron_at` (intended fire time) into the chain status
  (`.github/workflows/rebuild-chain.yml:16`, `workflow_dispatch`).
- `output/comparison-chain-status.json` — new fields `started_at` and
  `cron_at` alongside the existing `run_at`
  (`output/comparison-chain-status.json:2`).
- `app/trade-value-chart/index.html` — mirror the new fields and render
  slip-adjusted grace plus the measured slip on the per-source card
  (`app/trade-value-chart/index.html:2249-2256`,
  `app/trade-value-chart/index.html:2263-2304`).
- `pipelines/lifecycle/` (or new helper module under
  `pipelines/`) — new helper that reads Actions API run history and
  writes the per-source slip measurement. Out of scope here is what
  exactly the helper is named; pick a name that matches the codebase
  convention when implementing.
- `tests/` — new tests for criteria 1–7 below.

## 6. Test plan

New tests (each proves it catches the regression by failing against a
simulated broken state — see "Simulated broken state" columns below):

| # | Test | Simulated broken state | Expected outcome |
|---|------|------------------------|------------------|
| 1 | `publication_windows.py` carries `slip_observed_max_minutes` and `slip_measured_at` on every entry | Delete one field from one entry and import | Import assertion fails |
| 2 | `grace_window_minutes` adds measured slip to `grace_days * 24 * 60` | Set `slip_observed_max_minutes = 0` and re-run | Asserted minutes drop by the measured slip |
| 3 | `determine_source_state` does NOT flag a 6-hour-late run as `red` | Force `last_write` 6 h after `expected_by` with measured slip = 6 h, run against today's code (no slip) | Today's code returns `red`; R10 code returns `amber` |
| 4 | `determine_source_state` DOES flag a 24-hour-late run as `red` | Force `last_write` 24 h after `expected_by` with measured slip = 6 h | Returns `red` even with the slip adjustment |
| 5 | Unmeasured slip defaults to 6 h | Source entry with `slip_observed_max_minutes` absent | Default of 360 minutes applied; card label `slip: default 6h (unmeasured)` |
| 6 | Stale measurement (>30d) is flagged | `slip_measured_at` 31 days in the past | Card label `slip: stale measurement (>30d)` |
| 7 | `output/comparison-chain-status.json` carries `started_at` and `cron_at` | Strip both fields and re-run | Schema assertion fails |

Each test must be wired into `make validate`. The guard for criteria 3
and 4 is the regression guard that proves it catches the bug it names:

  - **State A** (6h-late): today's code path in `determine_source_state`
    (`pipelines/check_deadlines.py:235-243`) hits the
    `last_write <= grace_until` branch and returns `amber` only when the
    1-day grace (`pipelines/lib/publication_windows.py:46`) covers the
    slip. A 6-hour slip is within the 1-day grace today, so this test is
    the explicit cross-check that the R10 grace math matches a real
    observed slip (criterion 4 in the parent ticket). The negative test
    for state A is "run with `slip_observed_max_minutes = 0` and assert
    the verdict is still correct" — that proves the slip was the
    difference, not the publication-window math.
  - **State B** (24h-late): force `last_write` 24 h after `expected_by`
    with `slip_observed_max_minutes = 360`. The verdict must be `red`
    (`pipelines/check_deadlines.py:244-252`). The negative test for state
    B is "force 24 h with `slip_observed_max_minutes = 0` and assert
    `red`" — same answer, proving the red is from the slip budget being
    exceeded, not from some unrelated check.

Tests 3 and 4 must be shown to fail against the simulated broken state
**before** the R10 implementation is merged. That is the standing rule
that applies here: every regression guard ships with its negative test.

Existing tests that must still pass:

- All tests currently under `tests/` that exercise
  `pipelines/check_deadlines.py` (grace math, chain-state verdicts,
  week-boundary edges at `pipelines/check_deadlines.py:169`).
- All tests currently under `tests/` that exercise
  `pipelines/lib/publication_windows.py` (verified-vs-unverified
  schedule verdicts at `pipelines/lib/publication_windows.py:161-167`).
- The CBS no-verified-schedule test expectation
  (`docs/claude-log.md` entry for commit `973aaec`, JEG-179).
- `make validate` end to end.

## 7. Constraints

The worker is a bounded drafting-and-codegen lane, not a publishing lane.
The blocklist below is exhaustive for this ticket.

- **No credentials.** No Supabase service key, no GitHub PAT, no secrets
  in test fixtures, no real cron expressions evaluated against live
  state.
- **No browser.** No Playwright, no Puppeteer, no headless-Chrome
  installs, no visual regression captures.
- **No vision / OCR.** No image-diffing of the per-source card. Card
  verification is text and JSON inspection only.
- **No Mac-only files.** No `.DS_Store`, no `~/Library` paths, no
  macOS-specific shebangs.
- **No merge, no push, no deploy.** Worker commits the draft branch and
  stops. Promotion, merging to `main`, and `make sync` are out of scope.
- **Linear CLI is unavailable in the sandbox.** No `linear-cli` calls,
  no Linear API requests, no attempt to update JEG-137 from this lane.
- **Workers cannot run tests.** The worker writes the tests and the
  code; verification (running `make validate`, executing the regression
  guard against the simulated broken state, and publishing) happens
  outside the sandbox. Do not claim any test was run.
- **No methodology, no values, no copy decisions.** R10 is a
  measurement and grace-extension change. It does not alter the chart
  math, the VORP methodology, the scale, the curve, or the user-facing
  copy. The monitor card label text (`slip: default 6h (unmeasured)`,
  `slip: stale measurement (>30d)`) is a copy decision that must be
  confirmed before publish — the worker proposes these strings as
  candidates and the reviewer owns the final copy.
- **D3 holds.** Per `pipelines/check_deadlines.py:7-8`, no alert
  recipient. Slip is a number the deadline checker reads, not a
  notification.
- **PH-4 holds.** Per `docs/health/best-practices.md:63`, runs remain
  idempotent and content-keyed; review holds are never retried.
- **Brand and copy rules hold.** "Vegas" (never "the market");
  "Data Driven Football" only (no FantasyPros, Muse, or Meta branding);
  "value above waivers" only (never "VORP" in user-facing copy; the
  internal key `espn_vorp` is exempt).

---

*Brief drafted from a read-only inspection of the worktree at the
branch tip. No code was changed; no test was run. Verification (running
the regression guard against simulated broken states A and B, and
`make validate`) happens outside the sandbox.*