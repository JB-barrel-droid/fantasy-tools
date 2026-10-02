# Production Verified Rule

**Rule: Done = production-verified**

## Definition

A ticket whose diff touches a workflow file (`.github/workflows/*.yml`) remains in "Done" status only when `pipelines/production_verify.py` reports `verified` state for that workflow.

## Rationale

Workflow changes affect production data pipelines and dashboard data. A green CI run only proves the workflow syntax is valid — it does not prove the workflow actually executed successfully against production systems (Supabase tables, external APIs).

## Process

1. When a workflow file is modified, the ticket remains in "Done" only after:
   - The workflow runs successfully in production (GitHub Actions shows green status)
   - The corresponding Supabase table row count and vintage match the local snapshot

2. Run the verifier manually or wait for the 30-minute heartbeat:
   ```bash
   python3 pipelines/production_verify.py
   ```

3. Check `output/production-verify.json` for the workflow's state field:
   - `verified` — ticket can stay in Done
   - `never_run` — workflow has not run since merge
   - `run_failed` — last run did not succeed
   - `mismatch` — run succeeded but table doesn't match snapshot

## Ticket Template

The Linear ticket template references this rule. See the template for the exact wording.

## Scope

This rule applies only to tickets that modify files in `.github/workflows/`. Other tickets follow the standard Done criteria.
