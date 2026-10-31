# Fast gate (JEG-1451)

`fast-gate` is an **informational** PR check. It reports failure normally, but
this PR does not change GitHub required checks. Jeremy's PSpice decision owns
enabling it in branch protection. Existing preview and Pages checks remain;
the nightly full suite and daily render sweep are unchanged. This rollout
therefore measures selective coverage before changing the merge contract.

The spec is [JEG-1451](https://linear.app/jegabee/issue/JEG-1451).
Stacked on #1255; retarget to main after it merges. Claude review is pending.

## Mapping

`config/fast_gate.json` owns commands and ordered path rules. Across files,
selections are unioned. Full coverage also keeps every touched fast shard,
including page renders outside the nightly list. Additive dependency rules
also select connector tests
for page modules loaded by the hosted connector. Full-risk rules take
precedence, then whole-module
test ownership, build-input rules, documentation, and first matching page or
pipeline rule. Unmapped paths and an empty diff run full coverage. File moves
include both paths (`git diff --no-renames`); deleted paths still classify.

| Changed paths | Selected coverage, plus always-on smoke |
| --- | --- |
| Engine assets under `app/trade-value-chart/`, Python value/spec references, pipeline math and shared libraries, `get-values/`, configuration, fixtures, unowned/shared test harnesses, `tools/` | Full: `validate-base`, existing core shards 1–5, `test-unit` |
| `.github/**`, `Makefile`, mapping, mapper/history tool or its tests/replay inputs | Full |
| `pipelines/**`, `scripts/**` with a matching `tests/test_<stem>.py` | Pipelines: hermetic integration, source/identity guards drawn from core, and the producer's own tests (pytest supports both test styles) |
| Producer without that matching test | Full |
| `app/v2/values-fieldnotes.*`, movers, source views, name search, `app/values-explainer/**` | Player values |
| `app/v2/trade.js`, `trade-readout.js`, `compare-evidence-view.*` | Compare |
| `app/v2/finder.js`, opponent inclusion, discovery controls | Find a trade |
| `app/v2/targets.js`, `target-answer-card.*` | Targets |
| `app/v2/waivers.*` | Waivers (including Clear/Undo focus and offline mutation checks) |
| `app/v2/league.js`, lineup comparison, league status, roster helpers, team summary | League |
| `app/v2/settings-fieldnotes.*` | Settings/navigation |
| Other `app/v2/**` (shared shell, state, styling), `build_v2_page.py` | All seven front-end shards |
| `supabase/functions/mcp/**`, `app/llm/**` | Connector (offline tool checks and page parity); value computation under `get-values/` uses full coverage |
| Test module explicitly run in a shard, or a listed Node helper run by the connector wrapper | Its owning shard(s); class-only ownership or unknown test/harness paths use full coverage |
| Markdown, `docs/**`, `runbooks/**`, with no runtime-input rule | Smoke only; no test shards |

Build-consumed documents (methodology, math review, feature contract, Manifesto
mirror, AI-use instructions, and `app/llm/skill/SKILL.md`) do not get the docs-only
shortcut. The connector consumes the page's finder, trade, movers, audit,
state-codec and
value-link modules, so those paths select both consumers. A test reads the
connector's module references and checks the mapping covers them.
The exact globs and runnable test lists are in the JSON, rather than
duplicated in workflow shell commands.

The small smoke set tests the mapper, replay and known-follow-up audit,
baseline attribution, exact core-shard coverage, workflow script paths and
existing CI speedup safeguards. The workflow uses a full git checkout and the
event's base/head SHAs, not a changed-files API. Invalid history/diffs fail the
plan; they cannot produce a green empty selection.

## Execution and failure behavior

Smoke runs for docs and drafts too. Existing `ci_pr_gate` checks current PR
head/draft state before heavy work and at aggregation. A deferred draft gets
a red informational `fast-gate`, never a false green. A current ready docs-only
PR can pass with smoke and an intentionally skipped shard matrix. Missing
outputs, failed/cancelled/skipped required shards and stale PRs fail aggregation.

Narrow jobs have a 15-minute budget; full core/base jobs have 30 minutes and
the full unit job has 120. A timeout is a failure, not a fallback success.
Build-dependent shards install pinned Playwright plus Node 22, build the test
surfaces and require render execution. Baseline-red attribution wraps test
commands and preserves nonzero statuses; there is no allowlist or
`continue-on-error` in the new check. Full coverage includes every touched fast shard as well as the existing
`make validate` components plus the nightly `make test-unit` list. The separate
daily render list remains the backstop for render modules outside that suite.

## Proof and replay

```sh
python3 -m unittest -v tests.test_fast_gate
python3 -m pipelines.fast_gate run --shard smoke
python3 -m pipelines.fast_gate_history
actionlint .github/workflows/fast-gate.yml
```

Three explicit samples pin docs-only → smoke, Waivers → smoke + Waivers,
engine → full. Tests also cover unions, shared pages, runtime Markdown, unknown
paths, malformed paths, producer pairing, rename/merge-base behavior, pytest
collection failures, baseline failure propagation and actual aggregate-shell
success/failure combinations.

[The 30-PR replay](fast-gate-replay.md) uses the file lists captured in
`tests/fast_gate_history.json` from main at
`c267aa71ef1d445670516b1858e0f9dfe5a48f93`. It includes squash commits and
first-parent merges, excluding automation commits without a PR number.
The test feeds all 30 lists through the mapper, checks their saved expected
selections and recaptures the file lists from pinned git history when present.
Regenerate input deliberately with:

```sh
python3 -m pipelines.fast_gate_history --capture /tmp/fast-gate-history.json
```

Result: **24 full, 3 smoke-only, 2 smoke + connector, 1 smoke + Waivers**. Recent PRs commonly edited
Makefile/CI, math, shared fixtures or uncovered tests. This conservative sample
does not establish a median CI speedup or meet a measured sub-15-minute SLO.

Two documented follow-ups were traced to originals in this window: #1192 →
#1222 (stale comparison player keys after a duplicate merge) and #1156 → #1220
(connector current/prior included-source pairing). Neither would skip the
broken area. A deliberately broken mapper makes both audit rows flag a miss.
#1200 → #1231 was also inspected: its log explicitly says #1200 had already
fixed both tools, so it is recorded as coverage/text follow-up, not an escaped
compare-trade defect. This audit is limited to documented links inspected in
git, not a claim to discover every later defect or unpublished fix.

## Timing evidence and estimates

Read via GraphQL check receipts on 2026-10-31; no REST calls or log downloads.
These are whole-job times including setup, not per-test measurements.

- [PR #1242 preview run 41165867588](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/41165867588):
  build 6m16s; core 1–5: 21m45s, 15m14s, 17m26s, 22m08s, 13m51s.
- [Main run 41167789392](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/41167789392):
  build 6m32s; core 1–5: 16m45s, 12m40s, 18m08s, 18m16s, 13m37s.
- Separate #1242 settings render job: 1m46s
  ([41165867545](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/41165867545));
  offline Waivers mutation job: 18s
  ([41165867553](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/41165867553));
  v2 render job: 24m03s
  ([41165867583](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/41165867583)).

| New shard | Initial whole-job estimate | Evidence/limit |
| --- | --- | --- |
| Smoke/docs-only | <1 min of execution, plus runner startup | Clean local venv: smoke completes in seconds; CI timing unmeasured |
| Pipelines | 6–12 min | Integration + selected source guards + paired test; producer cost varies |
| Player values | 7–12 min | Five modules, one render module; build/setup cost not separately available |
| Compare | 7–12 min | Six modules, one render module |
| Find a trade | 8–15 min | Seven modules including saved-team render; known baseline red may report failure |
| Targets | 8–15 min | Three modules including two renders |
| Waivers | 7–12 min | Pure/offline checks plus one focus render; full mutation render stays in nightly |
| League | 8–15 min | Six modules including problems render |
| Settings/navigation | 8–15 min | Four modules including navigation renders; isolated settings CI above is only a partial proxy |
| Connector | 8–15 min | Seven modules including page parity; Node 22 and browser build required |
| Full base/core | Base roughly 6–10 min; core 13–23 min each | Recent whole-job receipts above; engine exceptions exceed narrow budget |
| Full unit | Up to 120 min; no recent completed duration obtained | Existing nightly timeout; not represented as a measured speedup |

Narrow estimates are planning ranges, not observations from the new workflow.
The selected matrix runs in parallel, so wall time follows the slowest selected
job plus planning/aggregation and queue time. Queue delays, cold downloads and
heavy paired tests can exceed the 15-minute target; check real receipts before
Jeremy changes required checks. The existing slow preview still runs during
this informational rollout.

## Build validation outcome

The local `make validate` run on the requested a6a7698d base stopped in
`tests.test_v2_finder_saved_team_render.FinderSavedTeamRenderTest.test_keyboard_mobile_and_overlap_guard`:
`selected` was `''`, expected `'beta'` (line 415). The finder and test are
unchanged by this PR. #1255's baseline documentation records this signature on
JEG-1394/JEG-1450 but leaves it unseeded pending a confirmed owner/main SHA.
The wrapper reports **new red**, and the gate remains red. The Find a trade
shard includes this complete render module; the mapper does not avoid it.
No assertions or registry entries were relaxed. The full unit suite was not
run locally. Independent review and a green gate remain pending.

The separate required-render contract check passed all six tests, including
broken-build discrimination (892s locally). The clean smoke set passed 56 tests,
workflow guards passed 24, and the paired puller pytest path passed 16.
