<!-- jeg-1464:first-readout -->
# First efficiency readout — Oct 30 and Oct 31, 2026

Measured in `JB-barrel-droid/fantasy-tools` using GitHub REST, captured Oct 31 at 19:43:25 UTC (14:43 CT). Oct 31 is partial.

| CT day | Merged | Median open → merge | P90 | 06:00–07:00 | 16:00–17:00 | Outside |
|---|---:|---:|---:|---:|---:|---:|
| Oct 30 | 50 | 6.73 h | 30.34 h | 0 | 1 | 49 |
| Oct 31, partial | 2 | 4.34 h | 7.26 h | 0 | 0 | 2 |

These one-hour merge bins describe timing, not approval receipts. The ticket names approval times but does not specify window width.

Baseline quoted in the spec: **442 merged, median 1.9 h, p90 19.4 h**. Independent recount: **442**, median **1.9168 h**, nearest-rank p90 **19.6667 h**. Exact recount window: `[2026-10-17T05:00:00Z, 2026-10-31T19:43:25.305067Z)`, CT calendar Oct 17 through capture. Count each merged PR once, all authors/base branches, filter `merged_at`; durations are `created_at` → `merged_at` elapsed hours, not ready-for-review. Median averages the central pair; p90 is sorted index `ceil(0.9*n)-1`. `out/baseline.json` records all 442 PR IDs. Original Muse cutoff/percentile algorithm is unconfirmed, and `scratch/rootcause/` is absent, so the 19.4 h quote has not been silently replaced or called reproduced.

Bridge observations, attributed by terminal-event date: Oct 30 **42 Claude** run IDs and **29 Codex** run IDs; Oct 31 **0 Claude** and **86 Codex** run IDs, including **10 failed events**. These are recorded journal run counts, not all starts or verified ticket completions. The retained 20 Oct 30 Claude result files record **194 turns** and **$14.4551 list-equivalent** dollars; resumes/earlier overwritten results are missing, so this is partial coverage, not spend and not the full JEG-1429 ledger. Numeric token counters and their coverage counts are in daily JSON. Other provider usage is unknown.

One fresh `get_bridge_activity` receipt: Claude **0 running**, Codex bridge **5 running**; queued counts were not supplied. Completion-only journals cannot reconstruct historical occupancy. Read-only CSVs preserve this distinction.

Mac samples at 19:43 UTC: **16 GiB total RAM**, about **12.23–12.31 GiB active+wired+compressed RAM**, pressure level **2** (warning), **10 logical CPUs**, load **3.67 / 4.40 / 4.40**, free disk **3,894,760–3,894,780 KiB** on `/System/Volumes/Data`. The tool stops below **3,670,016 KiB**, Jeremy's 3.5 GiB override. No Oct 30 capacity history was available.

Stage bottleneck ranking, CI/approval/merge-ready history, open conflicts and historical time behind main are **unknown in this first readout**. The full REST run stopped on HTTP 403: the local GitHub core allowance was exhausted (0/5000; reset 20:15:31 UTC). The explicit `--summary-only` run used REST search's separate allowance; it did not retry or fall back automatically. Full-mode code collects paginated timeline/review/exact-head CI receipts and sample-bounded behind-main intervals when those sources are available. Linear started-state exports, Duet asks and charter go-live evidence were unavailable. Coordinators must log one `{id,at}` per ask to `out/asks.jsonl`; charter items and intended metrics are listed with unknown go-live/effect instead of invented shipping claims.

Outputs: `/Users/botcomp/code/scratch/jeg1464/out/` (`2026-10-30.md/.json`, `2026-10-31.md/.json`, `daily.csv`, `baseline.json`, `capacity.csv`, `bridge-load.csv`, `activity.json`). Repo home: `docs/efficiency-scorecard/`. All collection is read-only; no model calls, settings changes, merge, deploy or schedule installation.

Coordinator daily run step: **06:00 America/Chicago, Nov 1–14**, reporting the previous complete CT day, with a final summary through Nov 13:

```sh
cd /Users/botcomp/code/scratch/jeg1464/wt && PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin /usr/bin/python3 scripts/efficiency_scorecard.py run --out /Users/botcomp/code/scratch/jeg1464/out --charter docs/efficiency-scorecard/charter.json --asks /Users/botcomp/code/scratch/jeg1464/out/asks.jsonl
```

The README supplies the exact cron entry and a separate five-minute sampler command; neither is installed. Seventeen fixture tests pass. `make validate` failed in the existing dashboard sync because the configured Playwright Chromium executable is absent; no browser was installed. The gate log and generated output are preserved under `out/`. Independent Claude review is pending; no passing review is claimed. Remaining blockers: full stage data after quota recovery, original baseline provenance, Linear/Duet/go-live inputs and independent review.
