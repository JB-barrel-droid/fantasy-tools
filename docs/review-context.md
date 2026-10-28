# Review context

A routine review starts with AGENTS.md, HANDOFF.md's Resume here, the current
PR body, current diff and its Linear brief. Then read only the referenced
method/spec/runbook and tests relevant to that diff. Do not load all logs,
old handoffs, closed PRs or every issue comment by default.

## One current brief

PR bodies give the concrete before/after behavior, targeted validation,
unverified checks and remaining blocker/approval. Keep them roughly 100–200
words; link detailed measurements, logs and decisions instead of pasting
them. Mark a notes-only draft as unimplemented. Label historical results with
their head/date; they are not current-head CI evidence.

Settled decisions replace questions in the body. Preserve explicit holds and
deployment boundaries. Never turn a failed or unrun check into “passed.”
When a review finding is fixed, retain its evidence and point to the fix;
do not resolve a substantive concern merely because its line became outdated.

## Read discussions selectively

List comment metadata first. Read unresolved review findings and the latest
head-matching build report. Collapsed/minimized comments and linked
measurement tables are on-demand evidence, not part of the default review.
GraphQL can request isMinimized and body together; filter minimized entries
before sending bodies to a review model. REST/connector fetches may return
collapsed bodies too, so UI minimization alone does not reduce API context.

The preview workflow already updates its single <!-- preview-build -->
comment. Keep that current report visible; inspect the aggregate preview
check and its shards as well as v2-render. It reports validate-base, not a
claim that all validation already passed.

## Update rather than append

Use only Bug, Feature and Improvement labels for Trade Value Chart. Model
capability follows the task scope; decisions/holds belong in status and brief,
not another label taxonomy.

Keep one current status summary per workstream; update it when state changes.
Do not add “still waiting,” repeated failed merge attempts, copied test logs
or ownership-routing memos. Put durable decisions into the ticket/PR brief
and detailed measurements into linked evidence.

Close confirmed superseded drafts with a replacement link while retaining
their branches/history. Collapse only superseded or resolved discussion,
with the substantive outcome captured first. Do not hide active findings,
delete approvals, rewrite review verdicts or remove the latest CI evidence.
