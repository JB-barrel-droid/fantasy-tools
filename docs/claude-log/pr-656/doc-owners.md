# PR 656: docs index Owner and Verified columns (JEG-601 / JEG-583)

Verified: `python3 -m unittest tests.test_doc_staleness` passes (4 tests); the checker flags a synthetic stale (>30 days), unknown-date and ownerless row and skips Record rows and the exact-30-day edge; `--today 2026-12-01` raises findings from 44 to 52; report exits 0.

Claimed, not checked: values in the new columns. Only dates and tickets stated in the README row or the doc's own Last updated/checked line were filled (10 rows); the other 21 Maintained rows are `unknown`, so the report currently lists 44 findings. No full `make validate` run (docs and a script only).
