# docs/ index

The durable docs live here as Markdown in GitHub (JEG-596 decision, Jeremy, 2026-10-12). This page is the map: naming rules first, then one line per doc. When you add, move or retire a doc, update this page in the same PR.

## Naming conventions

- One folder per topic once a topic has 3 or more files (`health/`, `audits/`, `contract/`, `planning/`, `design/`, `decisions/`). Single standing pages stay at the top level.
- File names are lowercase kebab-case: `topic-subject.md`. Exceptions kept for history: `MODULES.md`, `QA_FRAMEWORKS.md`, `SUPABASE_WRITER_AUDIT.md`, `TRADE_DASHBOARD_QA_ROUND1.md` (rename when next edited).
- Ticket-bound write-ups carry the ticket id as a prefix: `jeg-123-short-subject.md`. They are records, not maintained pages.
- Session logs go in `claude-log/YYYY-MM-DD-slug.md`, one file per PR. `claude-log.md` is frozen (old entries only).
- Every page opens with a title, then a one-paragraph purpose, then a status or "Last updated" line when it can go stale.
- Every page needs one line in this index. Superseded or finished docs move to `archive/` (repo root) with a dated README; nothing is deleted.
- Mark each doc below as Maintained, Record (dated, not maintained) or Proposal.

## Product and method

| Doc | Status | What it is |
|---|---|---|
| [manifesto.md](manifesto.md) | Maintained | Jeremy's reasoning for the project (market, fundamental, portfolio value); scope features against it. |
| [manifesto-mirror.md](manifesto-mirror.md) | Maintained | Mirror of the manifesto Google Doc. |
| [methodology.md](methodology.md) | Maintained | Required methodology entrypoint: how values are computed. |
| [math-review-agenda.md](math-review-agenda.md) | Maintained | Queue of math and logic questions for the coordinated full review (JEG-450). |
| [fidelity-tolerances.md](fidelity-tolerances.md) | Maintained | Tolerances and hold rules for the fidelity pulse. |
| [league-settings-inventory.md](league-settings-inventory.md) | Maintained | Inventory of league settings the backend saves and uses. |
| [decisions.md](decisions.md) | Maintained | Durable record of time-boxed decisions and their outcomes. |
| [decisions/drafts/fantasypros-half12-drift.md](decisions/drafts/fantasypros-half12-drift.md) | Record | Draft decision on FantasyPros half-PPR 12-team drift. |
| [risk-register.md](risk-register.md) | Maintained | Open and fixed correctness risks, one row per GAP id. |
| [feature-contract.md](feature-contract.md) | Maintained | Front-end feature contract with numbered IDs (GL-xx etc.). |
| [kdst-group-contract.md](kdst-group-contract.md) | Record | K/DST group definitions, units and source availability (JEG-211). |
| [kdst-source-audit.md](kdst-source-audit.md) | Record | K/DST source diagnosis, evidence from 2026-10-01 (JEG-19). |
| [player-scenario-regression-tests.md](player-scenario-regression-tests.md) | Maintained | Football-question scenarios used as regression tests on current players. |
| [QA_FRAMEWORKS.md](QA_FRAMEWORKS.md) | Maintained | Systematic QA frameworks for whole dimensions of the dashboard. |

## Architecture and data

| Doc | Status | What it is |
|---|---|---|
| [architecture-current.md](architecture-current.md) | Maintained | Current state: every file the site reads, the job that writes it, pg_cron schedule, what Supabase is for (JEG-599). |
| [architecture-target.md](architecture-target.md) | Proposal | Target architecture (JEG-341-A). |
| [modular-pipeline.md](modular-pipeline.md) | Maintained | Modular pipeline stages and their contracts. |
| [pipeline-rules.md](pipeline-rules.md) | Maintained | Standing rules for every pipeline stage. |
| [MODULES.md](MODULES.md) | Maintained | One instruction, one lane module rules. |
| [planning/](planning/) | Record | Consolidation layer scope, its Codex review, and the JEG-302 monitor cleanup scope. |
| [contract/](contract/) | Maintained | Front-end read contract v1, FE dependency inventory, v3 backend requirements (JEG-327). |
| [design/vorp-reweight.md](design/vorp-reweight.md) | Record | Eight-group VORP reweight design (JEG-209/231), with `reweight_example.py` and a desktop mockup PNG. |
| [product/jeg-303-dashboard-ideas.md](product/jeg-303-dashboard-ideas.md) | Record | Dashboard idea scoping (JEG-303). |
| [v2-design-notes.md](v2-design-notes.md) | Maintained | Notes on the v2 front end design. |
| [fixture-transition-proposal.md](fixture-transition-proposal.md) | Record | Decision to pause stale adjusted curves, staged 2026-09-22. |

## Supabase

| Doc | Status | What it is |
|---|---|---|
| [supabase-naming-conventions.md](supabase-naming-conventions.md) | Maintained | Naming rules for tables, views and functions. |
| [supabase-source-mapping.md](supabase-source-mapping.md) | Maintained | How scraped references map into Supabase. |
| [SUPABASE_WRITER_AUDIT.md](SUPABASE_WRITER_AUDIT.md) | Record | Audit of Supabase writers' missing safeguards. |
| [supabase-tables.md](supabase-tables.md) | Maintained | Every public table and view, who writes it, who reads it, and whether it is live or legacy (JEG-600). |
| [import-health-schema.md](import-health-schema.md) | Maintained | Import health tables (each section states its status). |

## Operations, process and agents

| Doc | Status | What it is |
|---|---|---|
| [preview-deploys.md](preview-deploys.md) | Maintained | Preview deploy design and phase 1 status. |
| [watchdog.md](watchdog.md) | Maintained | Every source-pulling job, who schedules it, and what watches it. |
| [guard-harness.md](guard-harness.md) | Maintained | Node harness for the browser curve-widget guard math. |
| [wiring-through-process.md](wiring-through-process.md) | Maintained | Standing rule: a fix is not done until wired to the live path. |
| [week-coding-rules.md](week-coding-rules.md) | Maintained | Rules for codifying page elements (headline etc.) to the dataset. |
| [engineering-notes.md](engineering-notes.md) | Maintained | Dated incident and design notes moved out of AGENTS.md. |
| [delegation-workflow.md](delegation-workflow.md) | Maintained | Tiers and how work is delegated to agents. |
| [agent-brief-template.md](agent-brief-template.md) | Maintained | Template for subagent briefs. |
| [director_operating_model.md](director_operating_model.md) | Record | Operating model for the lead session. |
| [merge-charter.md](merge-charter.md) | Record | Pre-authorized auto-merge tiers for lane PRs. |
| [health/](health/) | Record | Health program (JEG-78): best-practices standard, per-lane assessments, gap analysis, doc-vs-code tests, production-verified rule. |
| [../runbooks/](../runbooks/) | Maintained | Runbooks: consolidated values loader, weekly dashboard freshness. |

## History and evidence (not maintained)

| Doc | Status | What it is |
|---|---|---|
| [claude-log/](claude-log/) | Record | One log file per PR, since 2026-10-07; see its README. |
| [audits/](audits/) | Record | Ticket audits: JEG-183 pipeline review, JEG-208 dashboard and monitor views, JEG-221 to JEG-243 guard/imputation/batch audits with their JSON oracles, JEG-285 scheduler inventory (phase 1) and pg_cron migration specs (phase 2), JEG-292 caption rank investigation. |
| [../archive/](../archive/) | Record | Archived material by date; see its README. `2026-10-12-docs/` holds the frozen claude-log.md, JEG-92 pilot, QA round 1, migration plan/status, ChatGPT batch prompt and draft briefs (JEG-605). |

## Tracker

The documentation-store work is tracked under JEG-583 in Linear. The remaining consolidation (methodology rewrite, architecture collapse, runbooks, archiving history) is JEG-597 to JEG-605.
