# JEG-1484: keep operational status out of code main

Status: current-main integration and ownership-check repair implemented in #1303;
the delivery separation below is a concrete follow-up proposal, not activated.
No operational branch, producer redirect, deployment, schedule, permission or
release-window activation was performed.

## Recovery and current candidate

The restored environment retained ticket head `a5133a06` and its test-generated
working-tree output, but not the original `/tmp/jeg1484-validate.log`, kernel
processes or an exit receipt. The old full validation result is **unknown**.
The last recorded observation was 662 completed cases and no terminal result;
it is not a pass. Prior generated output was preserved under
`/workspace/scratch/jeg1484-resume-20261105/` before restoration to the ticket
head. No other writer's work was discarded.

Main `94600b901f3bf4dd4313df8655c0c74da938c8ae` was merged normally into the
existing ticket branch as `ecb39e6b`. Its diff contained operational reports and
input refreshes, with no conflict against the ticket implementation. Other
branches, value logic, #1304 integration and JEG-1485 scratch remain untouched.

The ownership-only CI check now pins the registry Git blob rather than requiring
main's entire commit identity to stand still while membership is read. A bot
status commit cannot invalidate unchanged membership. Registry changes, missing
registry evidence and read errors still block. Both reads of **actual merge
preflight** (`--pr` / `--batch`) still require the exact pinned main SHA. A
membership receipt explicitly says `ownership_only`; it is never merge approval.
The new regression failed before this change in all three drift scenarios.

181 focused tests passed after integration and repair. The complete author gate
will use the existing non-publishing `preview.yml` manual workflow on the pushed
exact ticket head: validate-base plus all five exhaustive shards, as enforced by
the coverage/parity tests. No local duplicate broad suite is needed. Manual
verification is named `preview-manual` and cannot satisfy the required PR check;
normal exact-head PR CI and independent review remain release gates. Logs and
receipts for this resumed work are stored in workspace scratch, not ephemeral
`/tmp`. The old run is not retried or relabeled successful.

## Why skipping Pages does not stop main churn

`health-artifacts.yml` publishes health/checkpoints, waits for served arrival,
records observations, then publishes monitoring summary and ops status. Simply
combining the three commits would change that observation ordering or delay a
new red summary when an ops build fails. Simply retaining workflow artifacts
would freeze the served readers. A skipped Pages run must not become a new
`site_deploy` success; #1303 retains that distinction.

The fidelity JSON is also an input to `pipelines/fidelity_hold.py`, not just a
monitor card. That input can change which values are shown. Moving its writer
without moving and verifying the rebuild consumer risks stale holds or an
unintended release of a hold. A producer-only patch is therefore insufficient.

## Exact repository-native delivery mechanism proposed

Use one data-only `operational-status` branch in this same public repository.
Code, actual input/fixture publication, the batch registry and all application
CI continue on `main`. Operational reports go to the data branch and never need
an application build or Pages deployment to become readable.

Publish immutable per-run report bundles and a small per-producer pointer in one
atomic Git commit. The bundle records producer workflow/run/attempt, producing
code SHA, content hashes, original report timestamps and outcomes. It must never
assert that diagnostic freshness is application publication freshness. Keep old
snapshots in Git history; no branch deletion, force push or retention deletion.
Allow only the explicit JSON report inventory, with schema and size limits; no
workflows, scripts, app assets, fixtures or arbitrary paths on this branch.

Use the existing environment-scoped App's `contents: write`, on an isolated
Ubuntu publisher job with the existing `main-writer` environment. No new token,
secret, permission, service or schedule is required. Serialize publisher jobs
with one GitHub Actions concurrency group across producers, with cancellation
off. Fetch the current data tip and make one ordinary fast-forward push attempt.
If it rejects or delivery is uncertain, retain the bundle artifact, expose the
failure and reconcile the remote result; do not retry automatically or replay
stale output. Other producer pointers must remain unchanged.

A shared reader resolves the per-producer pointer, fetches its immutable bundle
and verifies hashes/schema before supplying a report. Pin that bundle once per
page/job so several cards cannot mix report generations. Browser reads use public
raw GitHub HTTPS, with no credentials. A read-only probe of the existing public
`ops-status.json` at `94600b90` returned HTTP 200 and `Access-Control-Allow-Origin:
*`; cache lifetime was 300 seconds. This verifies the existing delivery primitive,
not a new status branch. Cache delay must still be measured during cutover.

Unreadable/missing/malformed/hash-mismatched/stale data is unavailable or red,
never a silent fallback to a fresh-looking old main/Pages copy. Keep the report's
own timestamps; never restamp stale output. A producer failure must remain a
failure even when its diagnostic bundle is successfully delivered.

| Writer / reader | Required coordinated change |
| --- | --- |
| `health-artifacts.yml` | Deliver health/checkpoints first; the existing served watch must verify their actual new-source arrival before observations and later summary/ops production. Later reports use the same data branch. Retain all current error and freshness gates. |
| `fidelity-pulse.yml` | Read its previous report from a pinned bundle, deliver a complete new report, retain hold-triggered rebuild dispatch and alerts. Delivery does not claim a successful value publication. |
| `rebuild-chain.yml` | Failure diagnostics and GitHub Actions reports go to the data branch even when zero-priced-row validation fails. Real data/fixture publication remains on main behind all existing gates. Coordinate this block with #1284/#1265 rather than duplicating their work. |
| `source-vintage-check.yml` | Its operational code-hash cache is data-branch state, not a code-main commit. Preserve real refresh dispatch rules. |
| `modules/status.html`, `modules/dashboard.html` | Resolve operational feeds through the verified public reader; keep actual published application/build reads on Pages. Mark unknown/stale reports honestly. |
| `health_artifacts_watch.py` | Fetch through the same reader, preserve timestamp-age rules and this-run arrival expectations, and record real served outcomes. No false no-op deploy observation. |
| Rebuild/health/fidelity input setup | Materialize verified pinned reports into the existing ephemeral `output/`/local report paths before current consumers run. Record the snapshot input identity. Missing fidelity evidence must not silently clear holds. |
| JEG-1485 observation/receipt owners | Agree bundle publication/input provenance separately from diagnostic timestamps. Do not overwrite published last-good/build identity with candidate or report labels. |

## Cutover and acceptance

1. Land a reviewed publisher/reader contract with synthetic, network-failure,
   stale-data, wrong-hash, concurrent-pointer and forbidden-path regressions.
   Coordinate all owned writer/consumer paths first. Do not change math or
   publication receipts to make the transport work.
2. Under release approval, publish one baseline data-branch bundle while legacy
   served delivery remains available. Verify payload hashes, real timestamps,
   provenance, App scope, fast-forward behavior and errors. No schedule change.
3. Deploy the status readers and verified job input setup under their normal
   gates, then verify the existing served watch against the new transport.
   Test 404/denial, malformed/stale payloads and failure reports: these must stay
   red/unknown and never clear a hold or mark a deployment successful.
4. Only after reader/watch acceptance, remove each legacy **status-only** main
   publication path with its owner. Keep actual data publication and full app
   validation unchanged. No partial producer cutover that silently freezes a
   reader is acceptable.
5. Observe at least two health cycles, one full fidelity report and one failed
   chain: status advances at the new endpoint with correct arrival evidence,
   no operational-only main commits, no Pages rebuild/deploy, no false
   `site_deploy` recovery, and unchanged validated application/value outputs.
   Retain a reviewed rollback path; do not activate or rollback by force push.

This spans existing writer ownership, served readers and fidelity input/provenance
contracts. It is beyond #1303's narrow classifier/batch gate and requires a
coordinated follow-up scope and live acceptance. #1303 reduces Pages work and
incidental ownership-CI invalidation; **it does not yet stop operational writers
from advancing main**. Do not close the durable-separation outcome on that claim.
The release lead's separately approved 15-minute pause test remains separate.


## Combined-head risk correction

A review finding showed that preflight classified only the source members;
a standard docs member plus an integration-only hot file could therefore bypass
the deterministic combined risk floor. Preflight now applies the real risk floor
to the integration PR, requires its risk label to match the batch, includes both
names of renames, and constrains the integration file inventory to the member
union plus the integration manifest. Missing member paths also block. Content
inside permitted files still requires independent exact-head combined review;
no patch-equivalence or branch-protection enforcement is claimed.

Six new tests use the real risk classifier for both source and combined diffs,
with only already-satisfied CI/review/ancestry evidence stubbed. Before correction
they produced eight failure subcases. After correction, the 187-test focused suite
passed. Cases include an integration-only hot/config/value file, weakened tests
inside a member path, mixed review labels, unrelated low-risk paths, missing member
paths and renamed hot files. Existing manual full runs on the prior candidate
remain running unchanged; their results cannot be relabeled as checks of this
corrective head. No duplicate broad run or metadata retry is part of this fix.
