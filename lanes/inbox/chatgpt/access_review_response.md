ACCESS REVIEW — ChatGPT lane opinion on access and coordination (grounded)

Context I verified
- Live site: index build tag on production is "<meta name="trade-chart-build" content="tv-20261004-2007-40e31d7">" (fetched from https://jb-barrel-droid.github.io/fantasy-tools/). Repo’s app/trade-value-chart/index.html currently carries "<meta name="trade-chart-build" content="tv-20261004-0722-7c5ae1c">" — deploys are happening after commits.
- Frontend contract boundary: app/trade-value-chart/assets/comparison-dashboard.js explicitly says "JEG-363: product-data.js is the ONLY module that talks to the FE contract; this dashboard calls into its five semantic methods …" and exposes legacy globals via that layer.
- Shared value invariants live in app/trade-value-chart/assets/value-model.js: "Everything here is PURE: no module state, no DOM … That is what makes the two callers testable against each other" and guardrails like MIN_SHARED_FOR_PIE = 40 and scaleToSharedTotal/benchShareOf.
- System boundary on DB writes: SYSTEM_MAP.md says "Supabase is the production source store, but production writes require explicit user approval."
- Pipeline import rule: docs/modular-pipeline.md: "Scraped references are saved to Supabase first … then the repo imports from Supabase — never from ad-hoc files."
- Supabase I inspected (read-only via this lane):
  - v_source_trade_values_wide has as_published, bias_adjusted, native_value, bake_id, week, qb_slots. Sample rows for player_key 468 confirm week scoping and per-scoring natives (half/full/std) exist.
  - gate_audits and pipeline_cron_log exist; gate_audits carries passed:boolean, failed_gates[], outcome. That’s the right place to read gate results — not to write them.

Question 1 — what access SHOULD I have?
A. Keep, as-is (necessary, proportionate)
- Repo read + write/commit on my own branch: necessary to do real reviews and land docs/patches in coherent slices.
- Supabase read-only: necessary for grounding reviews (e.g., v_source_trade_values_wide columns and rows; gate_audits schema), low risk.
- Live-site fetch: necessary to validate deploy artifacts (e.g., reading the trade-chart build tag and checking presence of curve/dashboard markers; verify_live.py codifies that check).

B. Remove or narrow (unnecessary/risky)
- None of the current capabilities are excessive given the commit-only-to-branch constraint. The only risk surface would be if I were allowed to push/merge/deploy — that should remain strictly Roman-only.

C. Missing access that would materially raise quality
- Read-only CI/Actions results: I can check the live site, but I cannot see which CI workflow ran, which tests failed, or what gates were red. A read-only fetch of the latest workflow summaries (per repo, per branch) would shorten feedback loops. Even a generated artifact in-repo (e.g., modules/ci-last-run.json updated by CI) would help this lane. Today, I can only infer via files like verify_live.py and live HTML.
- Read-only ticket context: The briefs reference JEG-xxx. A lightweight, read-only link to the Linear (or equivalent) summary for each ticket would prevent me from back-solving requirements from code comments. I don’t need full Linear access; an exported summary blob in lanes/ or docs/ per ticket is enough.
- Hermetic validation snapshots: I cannot run make validate. Publishing the latest validation report artifacts (e.g., tests/ summaries, output/reference-build-report.json, import-health reports) under modules/ or output/ on CI for my branch would let me review concrete failures rather than speculate.

D. Supabase write access — argue both sides, then verdict
- For: Faster end-to-end iteration on data-path issues (e.g., saving a USA Today week by running an idempotent upsert). In theory, I could help clear review holds by writing to staging tables during a chain and verifying downstream artifacts immediately.
- Against: It violates our explicit boundary and amplifies blast radius. SYSTEM_MAP.md: "production writes require explicit user approval". This lane lacks the browser, credentials, and deploy responsibility — the triad that forces accountability for writes. We also enforce fail-closed on ambiguity; a mistaken write (wrong grain, wrong bake_id, wrong week) creates durable corruption not caught by my tools alone. gate_audits/pipeline_write_audit exist to record Roman’s writes; splitting that responsibility weakens auditability.
- Verdict: No Supabase write access for ChatGPT. If we ever need lane-written data, create a staging schema with strict RLS, TTL, and row caps, and have Roman run the actual write on my artifacts through a single, audited path. Writes to production schemas stay Roman-only permanently.

Where I draw the line
- Green: repo read, Supabase read, live fetch, write/commit to my branch, read-only CI/ticket artifacts.
- Red: any credentials, any write to Supabase, any push/merge/deploy, any direct network scraping or API keys.

Question 2 — coordination between the three lanes
A. Who is best at what (grounded)
- M3 (MiniMax): Best at parallel implementation on well-bounded tasks with a hard contract. The code clearly separates contract surfaces (e.g., comparison-dashboard.js explicitly routes all fixture IO through product-data.js). M3 should be pointed at code inside those seams: pure renderers, utils, adapters — never database writers.
- ChatGPT (me): Best at repo-wide review and invariants. value-model.js centralizes shared math with comments that justify why: "Everything here is PURE … testable against each other"; "Minimum shared players before a source may be anchored … MIN_SHARED_FOR_PIE = 40"; "Scale … WITHOUT re-splitting its tiers". My strength is catching drift against those invariants, across modules.
- Roman: Integration, validation, production QA, DB writes, and deploys. verify_live.py exists to check production bytes; gate_audits/pipeline_cron_log exist in DB; Roman owns those levers and the live browser.

B. Where today’s flow breaks down
- M3 works blind: AGENTS.md says M3 is first for implementation and its “tests pass” claims are verified later. Without repo/DB context, M3 tends to invent or guess contracts. comparison-dashboard.js says "product-data.js is the ONLY module that talks to the FE contract"; a blind worker will often bypass or duplicate that. That costs cycles at integration.
- DB and pipeline assumptions leak: docs/modular-pipeline.md is clear: "… imports from Supabase — never from ad-hoc files"; if a worker assumes local CSVs are acceptable or writes to source_trade_values outside upsert grains, Roman has to unwind it.

C. Proposed 5-rule protocol (implement → review → integrate → deploy)
1) Roman authors the brief with: allowed-touch paths, the exact contract surface(s) to use (e.g., product-data.js methods), and a small, real sample payload excerpted from current fixtures. Attach links to any relevant tests by path.
2) ChatGPT goes first to confirm/shape the contract: add or update a stub/SDK or interface doc in-repo (no behavior changes), assert the invariants and I/O (e.g., method signatures, expected shapes), and commit that slice.
3) M3 implements against that stub only. No new IO surfaces, no direct fixture reads/writes. Output is a diff that compiles under the stub and includes narrow tests/examples, but claims of “tests pass” are advisory only.
4) ChatGPT reviews and hardens: reads the real repo, fits the code into the actual modules, fixes edge cases, and documents any DB or pipeline impacts. Commit coherent slices to the feature branch.
5) Roman integrates: runs make validate, inspects gate_audits/import-health, runs verify_live.py, does a live visual check, then merges/deploys. Any Supabase writes or fixture promotions are Roman-only.

D. One failure mode not called out yet
- SDK drift across sprints: once we introduce a stubbed SDK (e.g., product-data.js interface), M3 can accumulate a private copy and code to an outdated version. Their later diffs “work” in their sandbox but mismatch the repo contract, only failing at integration. Countermeasure: each M3 brief must pin the SDK commit SHA and forbid local copies; Roman rejects any change that isn’t based on the current stub.

Question 3 — M3’s operating model
A. What should change
- Give M3 a contract devkit instead of blindness:
  - A repo-sourced SDK stub for the exact entrypoints they must use (e.g., for product-data.js: initProductData(), getSnapshot(), getPlayers(), getPlayerContext()).
  - A tiny fixture excerpt (3–5 players) matching data/fixtures/current/comparison-sources-data.json and players.json so shape assumptions are concrete.
  - A manifest of allowed files and disallowed ones (e.g., allowed: app/trade-value-chart/assets/comparison-dashboard.js; disallowed: assets/product-data.js, data/fixtures/current/*, any supabase/* writer).
- Keep M3 as the first coder for tasks inside those boundaries. For any DB/pipeline task, flip the order: ChatGPT shapes the contract and writes the non-destructive parts; M3 only implements pure transforms under that API.
- Do not ask M3 to touch anything that writes to Supabase, promotes fixtures, or edits public copy/methodology. SYSTEM_MAP.md + standing rules reserve those for Roman/Jeremy.

B. One change to M3 briefs
- Add a "Contract and Samples" section with:
  - The function/class signatures to implement, with argument/return shapes.
  - 2–3 sample inputs/outputs copied from real fixtures.
  - The precise list of allowed file paths and a statement that bypassing the contract is a fail.
  - The SDK stub commit SHA. Any drift requires Roman to update the stub first.

Final stance (succinct)
- My current access level is appropriately conservative. Add read-only CI/ticket artifacts; keep Supabase strictly read-only for this lane. Writes (DB, deploy) stay Roman-only. Coordinate by contracts: ChatGPT shapes the seam, M3 codes inside it, Roman integrates. Enforce SDK pinning to prevent contract drift.
