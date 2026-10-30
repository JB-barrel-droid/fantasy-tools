# docs/ index

The durable docs live here as Markdown in GitHub (JEG-596 decision, Jeremy, 2026-10-12). This page is the map: naming rules first, then one line per doc. When you add, move or retire a doc, update this page in the same PR.

## Naming conventions

- One folder per topic once a topic has 3 or more files (`health/`, `audits/`, `contract/`, `planning/`, `design/`, `decisions/`). Single standing pages stay at the top level.
- File names are lowercase kebab-case: `topic-subject.md`. Exceptions kept for history: `MODULES.md`, `QA_FRAMEWORKS.md`, `SUPABASE_WRITER_AUDIT.md`, `TRADE_DASHBOARD_QA_ROUND1.md` (rename when next edited).
- Ticket-bound write-ups carry the ticket id as a prefix: `jeg-123-short-subject.md`. They are records, not maintained pages.
- Every session that changes anything writes a log in `claude-log/YYYY-MM-DD-slug.md`, one file per PR (required by `AGENTS.md`, Jeremy 2026-10-23). `archive/2026-10-12-docs/claude-log.md` is frozen (old entries only).
- Every page opens with a title, then a one-paragraph purpose, then a status or "Last updated" line when it can go stale.
- Every page needs one line in this index. Superseded or finished docs move to `archive/` (repo root) with a dated README; nothing is deleted.
- Staleness rule: a Maintained page names its owner ticket and a last-verified date; any Maintained page not verified in 30 days is stale and gets a refresh ticket (JEG-583).
- Owner and Verified columns (JEG-583): every Maintained row carries its owner ticket (`JEG-n`) and a last-verified date (`YYYY-MM-DD`). Use `unknown` when it is not known; never guess. Update Verified when you re-check a page against the code or data, not when you merely edit it. Records and proposals show `-`. `python3 scripts/doc_staleness.py` prints a non-blocking report of Maintained rows that are unknown or older than 30 days (also printed by `tests/test_doc_staleness.py` in `make test-unit`); it never fails the build.
- Mark each doc below as Maintained, Record (dated, not maintained) or Proposal.

## Product and method

| Doc | Status | Owner | Verified | What it is |
|---|---|---|---|---|
| [manifesto.md](manifesto.md) | Maintained | unknown | unknown | Jeremy's reasoning for the project (market, fundamental, portfolio value); scope features against it. |
| [manifesto-mirror.md](manifesto-mirror.md) | Maintained | unknown | unknown | Mirror of the manifesto Google Doc. |
| [methodology.md](methodology.md) | Maintained | JEG-597 | 2026-10-12 | Required methodology entrypoint: how values are computed. Opens with a step-to-code map checked 2026-10-12 (JEG-597) and a "Live and pending" status block (JEG-804 and JEG-787 are merged; JEG-930 merged; refreshed 2026-10-23, JEG-975). |
| [math-review-agenda.md](math-review-agenda.md) | Maintained | JEG-450 | 2026-10-12 | Queue of math and logic questions for the coordinated full review (JEG-450), with a closed-or-carried table for every item (JEG-597, 2026-10-12). |
| [fidelity-tolerances.md](fidelity-tolerances.md) | Maintained | unknown | unknown | Tolerances and hold rules for the fidelity pulse. |
| [league-settings-inventory.md](league-settings-inventory.md) | Maintained | unknown | unknown | Inventory of league settings the backend saves and uses. |
| [decisions.md](decisions.md) | Maintained | JEG-598 | 2026-10-22 | Durable record of time-boxed decisions and their outcomes; back-filled to 2026-10-12 (JEG-598). |
| [decisions/drafts/fantasypros-half12-drift.md](decisions/drafts/fantasypros-half12-drift.md) | Record | - | - | Draft decision on FantasyPros half-PPR 12-team drift. |
| [risk-register.md](risk-register.md) | Maintained | JEG-598 | 2026-10-22 | Open and fixed correctness risks, one row per GAP id, with a ticket index (JEG-598, 2026-10-12). |
| [research/](research/) | Record | - | - | Evidence behind opinionated choices: bench rule research, the roster convention audit, the QB bench-share artifact, research post 1 facts (JEG-604). |
| [feature-contract.md](feature-contract.md) | Maintained | unknown | unknown | Front-end feature contract with numbered IDs (GL-xx etc.); mirror of the Google Doc. |
| [contract/feature-contract-id-map.md](contract/feature-contract-id-map.md) | Maintained | JEG-602 | 2026-10-22 | Maps every contract ID to its check or ticket, lists the Doc edits that need Jeremy's Drive (JEG-602), and the lines the Doc needs for the 2026-10-22 merges with the tests that pin them (JEG-874). |
| [kdst-group-contract.md](kdst-group-contract.md) | Record | - | - | K/DST group definitions, units and source availability (JEG-211). |
| [kdst-source-audit.md](kdst-source-audit.md) | Record | - | - | K/DST source diagnosis, evidence from 2026-10-01 (JEG-19). |
| [math-review-questions-2026-10-12.md](math-review-questions-2026-10-12.md) | Record | - | - | Judgment calls left for Jeremy after the 2026-10-15 verification of the math review agenda (JEG-450). |
| [player-scenario-regression-tests.md](player-scenario-regression-tests.md) | Maintained | unknown | unknown | Football-question scenarios used as regression tests on current players. |
| [QA_FRAMEWORKS.md](QA_FRAMEWORKS.md) | Maintained | unknown | unknown | Systematic QA frameworks for whole dimensions of the dashboard. |
| [product/methodology-outline.md](product/methodology-outline.md) | Proposal | - | - | Draft page list for a reader-facing Methodology section under "Learn" (JEG-1105); which pages wait for JEG-1081. |
| [product/fit-label-glossary-draft.md](product/fit-label-glossary-draft.md) | Proposal | - | - | Draft plain definitions and numeric rules for Natural, Value, Market and Force fit, with code-vs-doc disagreements (JEG-1097). |
| [product/ddf-two-views-article-outline.md](product/ddf-two-views-article-outline.md) | Proposal | - | - | Outline of the Trade Charts vs Projections view pros-and-cons article, with the JEG-1073 numbers and what is still to measure (JEG-1102). |
| [product/jeg-1223-ai-onboarding-copy.md](product/jeg-1223-ai-onboarding-copy.md) | Proposal | - | 2026-10-29 | Draft homepage AI onboarding strings with a claim, evidence and limitation table for the DDF connector (JEG-1223, corrected in JEG-1252). |

## Architecture and data

| Doc | Status | Owner | Verified | What it is |
|---|---|---|---|---|
| [architecture-current.md](architecture-current.md) | Maintained | JEG-599 | 2026-10-12 | Current state: every file the site reads, the job that writes it, pg_cron schedule, what Supabase is for (JEG-599). |
| [architecture-target.md](architecture-target.md) | Proposal | - | - | Target architecture (JEG-341-A). |
| [modular-pipeline.md](modular-pipeline.md) | Maintained | unknown | unknown | Modular pipeline stages and their contracts. |
| [pipeline-rules.md](pipeline-rules.md) | Maintained | unknown | unknown | Standing rules for every pipeline stage. |
| [weekly-inputs-contract.md](weekly-inputs-contract.md) | Maintained | JEG-1227 | 2026-10-29 | Weekly-input artifact contract (`weekly-inputs` v1): fields, availability vs freshness, missing vs zero, weekly-only rule, versions and every validation code; validator `pipelines/lib/weekly_inputs_contract.py` (JEG-1227). |
| [MODULES.md](MODULES.md) | Maintained | unknown | unknown | One instruction, one lane module rules. |
| [planning/](planning/) | Record | - | - | Consolidation layer scope, its Codex review, and the JEG-302 monitor cleanup scope. |
| [contract/](contract/) | Maintained | JEG-327 | unknown | Front-end read contract v1, FE dependency inventory, v3 backend requirements (JEG-327). |
| [design/vorp-reweight.md](design/vorp-reweight.md) | Record | - | - | Eight-group VORP reweight design (JEG-209/231), with `reweight_example.py` and a desktop mockup PNG. |
| [design/fidelity-all-hold.md](design/fidelity-all-hold.md) | Record | JEG-799 | 2026-10-22 | Why a week boundary holds every source and fails the chain closed (GAP-FIDELITY-ALL-HOLD); options A/B/C with measured evidence, recommendation (a hold applies to the build it measured), decision for Jeremy. |
| [design/llm-site-state.md](design/llm-site-state.md) | Maintained | JEG-1025 | 2026-10-24 | The DDF state object and its two encodings (URL query, pasteable block) that move work between LLM chats and the site; reader rules and open gaps (JEG-1025, JEG-1024). |
| [specs/trade-page-parity.md](specs/trade-page-parity.md) | Proposal | JEG-1220 | 2026-10-29 | Parity matrix for Find a trade (your team, league-wide) and Compare on main, the shared TradeContext and readout contract, three reversible Claude picks for Jeremy, and twelve ordered slices with file ownership (JEG-1220). |
| [design/2026-10-direction.md](design/2026-10-direction.md) | Proposal | - | - | October 2026 proposal: paste-only launch, approved voice, and a Check a trade verdict with DDF Charted Value and DDF Projected Value beside the Market. Preview in `app/v2-concept/`. |
| [design/waiver-bench-churn-concept.md](design/waiver-bench-churn-concept.md) | Proposal | JEG-1196, JEG-1197 | 2026-10-29 | Waiver board and Bench Churn design concept: one shared waiver-board artifact, two views, values in DDF Value only with weekly data for timing; desktop/phone HTML mock beside it; data needs per panel and open questions for Jeremy. |
| [design/fieldnotes-components.md](design/fieldnotes-components.md) | Maintained | JEG-1137 | 2026-10-29 | The Fieldnotes foundation contract: the `?design=fieldnotes` flag, token roles, which existing classes change under the flag, the `ddf-fn-*` controls, rules for the lanes that consume them, and the acceptance tests. |
| [product/jeg-303-dashboard-ideas.md](product/jeg-303-dashboard-ideas.md) | Record | - | - | Dashboard idea scoping (JEG-303). |
| [v2-design-notes.md](v2-design-notes.md) | Maintained | JEG-602 | 2026-10-22 | v2 front end design notes and back-end contracts; dated build-log sections archived 2026-10-15 (JEG-602); nav structure, sub-routes, DDFAudit registry, Value pie, Writing tab, Customize tabs, shared search, chips and links, single-source compare, roster paste parser as merged 2026-10-22 (JEG-874). |
| [health-check-thresholds.md](health-check-thresholds.md) | Maintained | JEG-1011 | 2026-10-24 | Health check (Values auditing) flag limits: how each was derived from the engine on training weeks, validated on held-out weeks, and what is information only. |
| [v2-mobile-plan.md](v2-mobile-plan.md) | Maintained | JEG-927 | 2026-10-23 | Phone audit of the v2 pages (2026-10-22), defects per tab, chart and table patterns, three decisions, and the phased tickets; its status line says which phases are merged (JEG-927, JEG-947, JEG-953). |
| [fixture-transition-proposal.md](fixture-transition-proposal.md) | Record | - | - | Decision to pause stale adjusted curves, staged 2026-09-22. |

## Supabase

| Doc | Status | Owner | Verified | What it is |
|---|---|---|---|---|
| [supabase-naming-conventions.md](supabase-naming-conventions.md) | Maintained | unknown | unknown | Naming rules for tables, views and functions. |
| [supabase-source-mapping.md](supabase-source-mapping.md) | Maintained | unknown | unknown | How scraped references map into Supabase. |
| [SUPABASE_WRITER_AUDIT.md](SUPABASE_WRITER_AUDIT.md) | Record | - | - | Audit of Supabase writers' missing safeguards. |
| [supabase-tables.md](supabase-tables.md) | Maintained | JEG-600 | 2026-10-12 | Every public table and view, who writes it, who reads it, and whether it is live or legacy (JEG-600). |
| [projection-captures.md](projection-captures.md) | Maintained | JEG-944 | unknown | Forward-projection captures: what each source offers, the capture cadence, and the append-only table (JEG-944, parent JEG-943). |
| [values-endpoint.md](values-endpoint.md) | Maintained | JEG-1012 | 2026-10-24 | The `get-values` and remote `mcp` Supabase edge functions and the local MCP server that serve blended values (JEG-616, JEG-1012). |
| [use-ddf-in-claude-chatgpt.md](use-ddf-in-claude-chatgpt.md) | Maintained | JEG-1028 | 2026-10-24 | How to connect the values to Claude and ChatGPT (connector URL, skill, llms.txt, server card, Custom GPT Actions) and the current limits. Sources are in `app/llm/`, built by `pipelines/build_llm_surfaces.py`. |
| [get-values.openapi.yaml](get-values.openapi.yaml) | Maintained | JEG-1012 | 2026-10-24 | OpenAPI schema of `get-values` for a Custom GPT's Actions. |
| [supabase-egress-notes.md](supabase-egress-notes.md) | Record | JEG-793 | - | Which reads cost the cloud project's egress; steps 1 to 3 of JEG-793, figures inferred from code, not measured (2026-10-21). |
| [import-health-schema.md](import-health-schema.md) | Maintained | unknown | unknown | Import health tables (each section states its status). |

## Operations, process and agents

| Doc | Status | Owner | Verified | What it is |
|---|---|---|---|---|
| [picks-log.md](picks-log.md) | Record | - | - | Copy of the Claude lanes' picks log (choices made for Jeremy, each reversible; nothing merges on a pick alone). Source of truth is his main-chat log until lanes write here. |
| [review-context.md](review-context.md) | Maintained | JEG-1211 | 2026-10-29 | Selective PR reading, concise briefs, and keeping review evidence without memo streams. |
| [preview-deploys.md](preview-deploys.md) | Maintained | unknown | unknown | Preview deploy design and phase 1 status. |
| [qa-report.md](qa-report.md) | Record | - | - | Generated contract QA report (2026-10-19, `scripts/contract_qa_report.py`); do not edit, rerun the script. |
| [watchdog.md](watchdog.md) | Maintained | unknown | unknown | Every source-pulling job, who schedules it, and what watches it. |
| [guard-harness.md](guard-harness.md) | Maintained | unknown | unknown | Node harness for the browser curve-widget guard math. |
| [wiring-through-process.md](wiring-through-process.md) | Maintained | unknown | unknown | Standing rule: a fix is not done until wired to the live path. |
| [week-coding-rules.md](week-coding-rules.md) | Maintained | unknown | unknown | Rules for codifying page elements (headline etc.) to the dataset. |
| [engineering-notes.md](engineering-notes.md) | Maintained | unknown | unknown | Dated incident and design notes moved out of AGENTS.md. |
| [delegation-workflow.md](delegation-workflow.md) | Maintained | unknown | unknown | Tiers and how work is delegated to agents. |
| [agent-brief-template.md](agent-brief-template.md) | Maintained | unknown | unknown | Template for subagent briefs. |
| [director_operating_model.md](director_operating_model.md) | Record | - | - | Operating model for the lead session. |
| [merge-charter.md](merge-charter.md) | Record | - | - | Pre-authorized auto-merge tiers for lane PRs. |
| [health/](health/) | Record | - | - | Health program (JEG-78): best-practices standard, per-lane assessments, gap analysis, doc-vs-code tests, production-verified rule. |
| [../runbooks/](../runbooks/) | Maintained | JEG-601 | 2026-10-22 | One runbook per recurring job: weekly refresh, held source, run the chain, 12-combo sweep and rank guard, verify live, heavy suites and hot files, merging PRs (2026-10-22, JEG-874); plus the consolidated values loader and weekly dashboard freshness (JEG-601). |

## History and evidence (not maintained)

| Doc | Status | Owner | Verified | What it is |
|---|---|---|---|---|
| [review-evidence/2026-10-28-jeg-1142-impact.md](review-evidence/2026-10-28-jeg-1142-impact.md) | Record | - | - | Snapshot before/after tables preserved from PR #1044; not a fresh live calculation. |
| [claude-log/](claude-log/) | Record | - | - | One log file per PR, since 2026-10-07; see its README. |
| [audits/](audits/) | Record | - | - | Ticket audits: JEG-183 pipeline review, JEG-208 dashboard and monitor views, JEG-221 to JEG-243 guard/imputation/batch audits with their JSON oracles, JEG-285 scheduler inventory (phase 1) and pg_cron migration specs (phase 2), JEG-292 caption rank investigation. |
| [../archive/](../archive/) | Record | - | - | Archived material by date; see its README. `2026-10-15-docs/` holds the v2 design-notes build log (JEG-602). `2026-10-12-docs/` holds the frozen claude-log.md, JEG-92 pilot, QA round 1, migration plan/status, ChatGPT batch prompt and draft briefs (JEG-605). |

## Tracker

The documentation-store work is tracked under JEG-583 in Linear. The consolidation is JEG-597 to JEG-605; after this pass the open parts are the second-session runbook check (JEG-601), the Google Doc direction and "to build" edits (JEG-602), and the risk-register rows without an owner (JEG-628). The 2026-10-22 docs sync is JEG-874 (`docs/claude-log/2026-10-22-docs-sync.md`).
