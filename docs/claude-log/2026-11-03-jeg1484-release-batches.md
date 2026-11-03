# JEG-1484 implementation evidence

Scope: narrow repository-native batch preflight and status-only Pages no-publication
path. Branch `codex/JEG-1484-release-batches`, based on main `66f78417`.
Ticket: https://linear.app/jegabee/issue/JEG-1484.

Ownership checked before edits: #1284 and #1265 own rebuild-chain.yml (untouched);
#1262 owns freshness/promotion; #1270 owns review queue and AGENTS/HANDOFF;
calculation and design branches untouched. This change adds new preflight/classifier
modules and modifies Pages, its deploy observation recorder, the merge runbook,
focused guard tests and their registration. No existing release window activated.

Implementation: see [release-batches runbook](../../runbooks/release-batches.md).
The main registry provides exclusive ownership; source membership cannot take the
ordinary preflight path. Combined release evidence pins main/source/combined heads,
requires actual complete CI and build artifacts plus independent review attestations,
and verifies prior publication/live artifact acceptance. The PR ownership check is
wired. External merge callers must invoke the preflight; GitHub branch protection
and saved external automation prompts are unchanged. No stronger enforcement claim
is made.

Pages checks accumulated unpublished changes against the last successful actual
deploy. Every uncertainty defaults to full validation. Only exact operational JSON
records can skip all publication. Health import/checkpoint records stay full because
the served-artifact watch requires their arrival. Status-only receipts explicitly
state live status remains at the last publication, and the deploy recorder creates
no false success observation. Existing producer artifacts/alerts remain available.

Validation before first commit: 155 focused tests pass across release preflight,
Pages classifier/range/mutation cases, deploy gates, preview parity, CI speedup,
exhaustive shard coverage, monitoring coverage and existing main-write guards.
All three modified/new workflows parse as YAML. New modules are registered once
in test-core and once in shard 5. Full `make validate` is the next local gate;
exact-head remote CI and independent high-risk review remain required before release.

Monitoring inventory repair is limited to the new release-batch check and two
already-present release-window/main-writer check workflows missing from the main
inventory. These are event/manual checks without schedules or production writes;
no monitoring checks or assertions were removed.

No merge, deployment, branch deletion, settings, Supabase or credential change.

Draft PR: https://github.com/datadrivenfootball/fantasy-tools/pull/1303.
Initial exact-head ownership and waiver-mutation checks passed. CI's cheap guards
found one additional legacy expectation in tests/test_draft_ci_workflows.py
that forbade all Pages job conditions. The correction pins the exact classifier
condition/dependency, retains draft-state independence, and invokes the new
negative-tested publication-boundary guard. This necessary one-test adjustment
must be retained when #1262 integrates its separate changes to that test file.
No freshness/promotion runtime files changed. Cheap draft guards and focused
batch/Pages/CI-speedup tests pass after correction. Full local validation continues
in its original single run; no duplicate broad gate was started.
