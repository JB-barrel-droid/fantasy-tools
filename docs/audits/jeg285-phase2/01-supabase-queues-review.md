# JEG-285 Phase 2 — Supabase Queues documentation review

**Date:** 2026-10-03 (fills the coverage gap left by the 10:55 CDT Supabase docs pass,
which covered Cron, Edge Functions, Database Webhooks, and pg_net but not Queues)
**Status:** research input only — no schema proposal, no implementation decision.
Jeremy's Option C direction (00-target-architecture-decision.md) is unchanged.

## What Supabase Queues is

Supabase Queues is the managed `pgmq` (Postgres message queue) extension. Enable via
Dashboard → **Integrations → Queues**, or SQL `create extension if not exists pgmq;`
(available on Postgres 15.6.1.143+). Each queue creates two tables in the `pgmq`
schema: `pgmq.q_<queue_name>` (active messages) and `pgmq.a_<queue_name>` (archived
messages). Queue types: **Basic** (durable logged tables — recommended), **Unlogged**
(faster, data lost on crash), **Partitioned** (marked "coming soon" in the docs).

Sources: official Supabase Queues quickstart
(supabase/supabase repo, `apps/docs/content/guides/queues/quickstart.mdx`);
community production notes corroborate the mechanics.

## The API surface

- `pgmq.send(queue, msg [, delay])` / `pgmq.send_batch(queue, msgs)` — enqueue,
  optional delayed visibility.
- `pgmq.read(queue, vt, qty [, poll_timeout_s])` — read up to `qty` messages; each
  becomes invisible to other readers for `vt` seconds (visibility timeout).
- `pgmq.pop(queue)` — atomic read + delete (no retry needed).
- `pgmq.delete(queue, msg_id)` / `pgmq.archive(queue, msg_id)` — completion paths;
  archive keeps the message in `pgmq.a_<queue>` for audit.
- `pgmq.set_vt(...)`, `pgmq.metrics(queue)` — extend visibility, inspect depth.

Key fields on every read: `msg_id`, `read_ct` (increments on every read — a free
retry counter), `enqueued_at`, `vt`, `message` (jsonb). Newer pgmq adds `last_read_at`
and `headers`; confirm the bundled pgmq version on the live project before relying
on them.

## Delivery semantics — what you get and what you don't

- **At-least-once delivery.** If a worker crashes or forgets to delete/archive, the
  visibility timeout expires and the message simply becomes visible again. Nothing
  "fails" — the message comes back.
- **Retries are implicit, not scheduled.** There is no built-in backoff schedule or
  retry policy object; the worker implements retry policy itself (e.g. route
  messages with `read_ct > N` to a dead-letter queue — the DLQ pattern is
  worker-implemented, not a pgmq primitive).
- **No built-in consumer.** Supabase does not poll the queue for you. Something must
  drive it: a pg_cron job invoking an Edge Function, pg_cron + pg_net HTTP POST
  (e.g. to a GitHub `repository_dispatch` / `workflow_dispatch` endpoint), a DB
  trigger + pg_net wake, or an external long-lived worker.
- **Work visibility is native.** Queue depth, per-message `read_ct`, and the archive
  table are all plain SQL — the same connector path Muse.ai uses for everything
  else reads them. The Dashboard also has a Queues page. PostgREST exposure of the
  `pgmq` schema is optional.

## Verdict for the Phase 2 design

Queues fill the **"durable dispatch / retries / work visibility"** role named in the
JEG-285 ticket, with one clarification: they do **not** replace scheduling
(pg_cron still owns the schedule) or compute (GitHub Actions still owns the heavy
Python). Their value-add over pg_cron-alone is **durability of the handoff**: a
pg_cron tick that fails to trigger the chain is lost; a queued dispatch message
persists until a consumer deletes/archives it, with at-least-once retry and an
audit trail in the archive table.

Concrete fits under approved Option C:

| Use | Why Queues (not just pg_cron/pg_net) |
|---|---|
| Chain-run dispatch (`source-vintage-check` → rebuild chain) | The trigger survives a failed dispatch attempt; `read_ct` shows stuck triggers; archive proves what ran. |
| Failure-notification jobs | Durable alert queue behind the best-effort DB webhook — an undelivered webhook is retried from the queue instead of lost. |
| Drift-check / live-page-synthetic jobs | Small jobs enqueue uniformly; one poller pattern serves all of them. |
| Shadow-mode cutover | Old and new trigger paths consume the same queue during validation; compare before cutting over. |

What Queues can **not** do: run the 3–10 min Python chain (no compute of its own),
guarantee webhook delivery (that guarantee comes from the queue + consumer, not
from the webhook primitive), or provide scheduled retries/DLQ out of the box.

## Residual unknowns

- No documented per-queue throughput or concurrency cap was found in the quickstart;
  treat "no cap" as unverified, not proven.
- Partitioned queues are "coming soon" — do not design around them.
- Confirm the pgmq version on the live Supabase project before using `last_read_at`
  / `headers` or `poll_timeout_s` in any design.

## Constraints (unchanged, still binding)

- The `001_pipeline_write_audit_repair.sql` audit-table migration still requires
  **Jeremy's explicit approval** before any cutover work — this review does not
  approve or run it.
- The failure-notification webhook target (Slack vs Discord) is still **Jeremy's
  call**.
- No queue, migration, Edge Function, or cron job is created by this document.
