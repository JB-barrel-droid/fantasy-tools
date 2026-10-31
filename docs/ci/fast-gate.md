# Fast gate (JEG-1451)

[Draft PR #1260](https://github.com/JB-barrel-droid/fantasy-tools/pull/1260)
implements [JEG-1451](https://linear.app/jegabee/issue/JEG-1451). Stacked on #1255;
retarget to main after it merges. Claude review remains pending.

The check is informational until Jeremy's PSpice changes required checks.
Existing preview/Pages gates, nightly full suite and daily render sweep stay
unchanged. This work changes no repository settings.

## Routing after review corrections

`config/fast_gate.json` owns ordered path rules and runnable argv commands.
Full-risk rules and discovered shared dependencies precede narrow ownership.
Selections across paths are unioned; full coverage retains touched fast shards.

| Changed paths | Coverage plus always-on smoke |
| --- | --- |
| Engine/value math, config, fixtures, shared harnesses, `.github/**`, Makefile, mapper/scanner/history tools and their tests | Full: validate-base, core-1 through core-5, full-unit |
| `baseline_reds*`, `baseline_runtime/**`, `baseline_gate.sh`, `ci_pr_gate.py` | Full |
| Any pipeline module imported by another project module, including tests | Full, discovered from imports rather than a hand-maintained list |
| Test files imported by other tests | Full before considering their own shard |
| Explicitly mapped page files | Every test entry point referring to their path or basename, plus callers of shared Python/Node helpers |
| Other `app/v2/**`, including shell, shared modules, nav/UX/a11y surfaces; `build_v2_page.py` | Full |
| Isolated pipeline/CLI producer with a matching test and no discovered importers | Pipeline integration/source guards plus its paired test |
| Connector code and listed Node helpers | Connector; consumed page modules also select connector checks |
| Test-read documents and structured docs such as OpenAPI/registry data | Full |
| Unreferenced `docs/claude-log/**` records | Smoke only |
| Other Markdown/docs, unknown paths, empty diff | Full |

## Source inventory and completeness checks

`pipelines/fast_gate_dependencies.py` reads project source without executing
imports. It indexes literal file paths/basenames (including split `Path`
expressions), Python qualified/relative/sys.path-style imports, literal dynamic
imports and file-based loader references. Test references propagate through
Python and Node helpers to executable Python test files and existing Makefile
Node entry points and standalone Node test files. Environments, node_modules, hidden directories and symlinks
are excluded from the scan.

The checked-in page lists are built from this inventory, preserving the
previous checks. Python lists use pytest so both unittest classes and pytest
functions execute, including complete render/mutation modules. A smoke test
fails when any discovered page reader is absent; a negative test removes the
Waivers render file and proves the guard reports it. Helpers without any
selected executable reader also fail the guard. Standalone Node tests,
including test_v2_extract_players.js, are discovered outside the Makefile. A synthetic newly added
reader proves the inventory is not a frozen hand list.

`test_read_paths` records the discovered documents. A test requires an exact
match with the current inventory. Runtime discovery also forces full coverage
for test-read records even if an older manifest would otherwise allow smoke.
The default docs-only exemption is limited to unreferenced session logs.

Regenerate after changing readers:

```sh
python3 -m pipelines.fast_gate_dependencies --refresh
```

Current page test entry counts (some shared checks appear in several shards):

| Shard | Test entry files |
| --- | --- |
| fe-values | 33 |
| fe-compare | 42 |
| fe-finder | 107 |
| fe-targets | 26 |
| fe-waivers | 14 |
| fe-league | 92 |
| fe-settings | 7 |

## Git planning and base retargeting

The mapper uses merge-base git diffs with rename detection disabled, so old
and new paths both participate. It uses no changed-files API. The workflow
runs on `edited` as well as normal PR lifecycle events, so retargeting a
stacked base starts a new plan from the event's base SHA. Every state check
also compares live base ref and SHA to the event snapshot; a stale head or base
cannot pass. Tests keep the head fixed, change each base field and demonstrate
that retargeting changes a docs-only diff into a full engine selection.

Smoke runs for drafts and docs. Heavy jobs defer on draft/stale state, and the
aggregate reports failure rather than a false green. Missing outputs and any
failed, cancelled or unexpectedly skipped shard fail aggregation. Baseline
attribution preserves failures. No assertions or registry entries are relaxed.

## Thirty-PR replay

[The replay](fast-gate-replay.md) reuses the same 30 merged PR file lists captured
from first-parent git history on main at `c267aa71ef1d445670516b1858e0f9dfe5a48f93`.
No API supplied these lists. Tests recapture pinned history when available,
feed every list through the mapper and check saved expected selections.

After the review fixes: **28 full, 1 connector-only plus smoke, 1 combined
Find a trade/Waivers/League selection plus smoke, 0 smoke-only**. The former
24-full split is superseded. The table expands every full selection and any
additional touched shards. The two documented follow-up audits (#1192 → #1222,
#1156 → #1220) still skip no broken area; an intentionally broken mapper flags
both. This is an audit of documented links, not proof of every possible defect.

## Timing and validation limits

The earlier 6–15 minute narrow-shard estimates described incomplete test lists
and are withdrawn. Complete page-reader coverage is substantially larger and
needs new CI measurements. The existing 15-minute narrow-job timeout fails
closed; no claim is made that the expanded shards meet the target. Full/base
jobs retain their 30-minute budget and full-unit retains 120 minutes.

Prior whole-job CI receipts remain useful context, not measurements of these
new lists. Read via GraphQL without REST on 2026-10-31:

- [Preview 41165867588](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/41165867588):
  build 6m16s; core 1–5: 21m45s, 15m14s, 17m26s, 22m08s, 13m51s.
- [Main 41167789392](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/41167789392):
  build 6m32s; core 1–5: 16m45s, 12m40s, 18m08s, 18m16s, 13m37s.

The original build ran `make validate` once and stopped on the documented,
unseeded finder keyboard `'' != 'beta'` assertion. It also passed the six
contract render tests. Per the review-fix instruction, neither heavy check is
rerun here. The fixes are verified with source-inventory, routing, retarget,
workflow, replay and syntax checks. Full render execution, independent review,
new CI timing and enabling required checks remain outside this correction run.
