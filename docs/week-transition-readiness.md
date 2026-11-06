# Week-transition readiness gate

JEG-1526 provides an offline capture, deduplicated event queue, and isolated diagnostic runner. Owner: JEG-1526. Last verified: 2026-11-05. Implementation is a core slice; staging adapters and infrastructure remain required. It cannot return READY.

Run from this checkout with Python 3.10+:

```
python3 pipelines/week_transition_readiness.py --season 2026 --week 10 \
  --today 2026-11-11 --policy ticket-work/policy.json \
  --arrivals ticket-work/arrivals.json --output ticket-work/run-001
```

Exit 2 means BLOCKED; exit 1 means an executed diagnostic failed. Outputs include readiness.json, summary.md, source-manifest.json and content-addressed captured bytes. Output directories must be new. No image means no subprocess diagnostics. Optional `--image sha256:<64 hex digits>` uses an already installed trusted image with dependencies: no pulls, no host credentials passed, no network, no privileges, and only the scratch copy mounted. Images themselves must contain no credentials. Container execution has not been exercised here. Scratch copies omit Git, environment files, symlinks, dependencies and previous outputs. The diagnostic image must contain dependencies outside /work.

Policy JSON is `{"version":1,"sources":{...}}`; it must cover fantasycalc, usatoday, fantasypros, espn, cbs, cbsros and razzball. Each source needs `kind` (`week` or `date`), `scorings` (nonempty subset of standard/half_ppr/ppr), and `grains` (nonempty map of grain names to positive minimum row counts). Date policies also need ISO `earliest`/`latest`. No implicit carry-forward applies. Owner-reviewed real coverage expectations are not supplied by this implementation.

Arrivals JSON maps the same source names to `path` (inside checkout), `season`, `week` for weekly feeds or `content_date` for dated feeds, `scorings`, and `grains`. Hashes are calculated from bytes. Coverage/vintage metadata currently comes from this caller-owned envelope; a trusted importer adapter must derive and verify it from source payloads before production use. Missing inputs never pass completeness.

Add `--event landing --state ticket-work/queue.json` to enqueue after a committed source transaction; use `--event hourly` with the same arguments for reconciliation. These invoke the same locked, atomically persisted content-addressed queue. They do not execute jobs. Duplicate/failed keys are not retried automatically. Changed source bytes, expectations, target, or code create a new key and invalidate the previous current key. One consumer and actual source transaction hooks/hourly scheduler still need wiring. `receipt_valid` compares current completeness, code and input hashes; consumers must call it rather than trust an old readiness file. Keep operational files under ticket-work so they do not invalidate the code digest.

The Week 9 evidence is pinned in week9-regression-evidence.json. It identifies the actual two failing tests and three cases. Current tests contain pre-existing approved exemptions. Historical inputs and a true failing-before/passing-after reproducer remain unavailable; no exemption or value rule was changed here.

All database-dependent stages are explicit BLOCKED adapters. There is no arbitrary-command adapter or production database option. Missing pieces are import/health, first chain, writing refresh and 21-grain verification, second-chain consumption provenance, consolidation write/export, lineage, and weekly-loader/freshness staging. The diagnostic runner separately records sync, validate with target TODAY, integration, the perturbation suite and all three browser commands. It does not certify target-week plumbing inside legacy consumers. No publish command is exposed.
