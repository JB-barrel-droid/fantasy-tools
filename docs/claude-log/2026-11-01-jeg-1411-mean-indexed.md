## 2026-11-01 - JEG-1411 settled mean and Indexed

Contract: Jeremy authorized the post 07 research aggregation change to the mean (Oct 31, reaffirmed Nov 1). Apply Indexed outside the site, retain the existing draft PR #1252, and finish pushes before 20:40 UTC. No engine or site value math changed.

### Verified (check named)
- Fetched and fast-forwarded to the existing PR head `88f51c1f`; its owner had merged main normally. Read the F6/F18 decision briefs on JEG-1411 in the preceding continuation; Jeremy explicitly confirmed their scope in this job.
- `GLOSSARY_REF=88f51c1f python3 -m unittest tests.test_glossary_outside_site`: FAIL before changes (12 checks), including a behavioral mean-vs-median sentinel with real zero and missing chart inputs.
- `python3 tools/research/gap_backtest.py --aggregation median --output-dir /tmp/jeg1411-median`: PASS. Same-input median JSON retained in `docs/research/data/jeg1411-mean/median-baseline.json`.
- `python3 tools/research/gap_backtest.py --output-dir docs/research/data/jeg1411-mean --post docs/research/posts/07-does-the-gap-predict.md --median-baseline docs/research/data/jeg1411-mean/median-baseline.json`: PASS. Mean-based figures, source rows, tables and before/after generated from saved 2026 weeks 2–7; Standard/Half PPR/PPR settings present. The historical October 22 evidence remains unchanged.
- `python3 -m unittest tests.test_glossary_outside_site tests.test_mcp_remote`: PASS, 9 tests. Guard now covers generated llms.txt and skill text, Indexed labels, mean-based post wording and missed Muse headings.
- Generated-content comparisons using `gap_backtest.post_markdown`, `markdown`, `comparison_markdown` and `build_llm_surfaces.fill`: PASS. CSV projection-view row count and Spearman recomputation match the JSON result; local skill ZIP matches its source. Added a CSV `view` field because the old exporter overwrote its intended view label with numeric `ours`; statistics unchanged by this export correction.
- `python3 pipelines/build_llm_surfaces.py`: regenerated LLM copies. llms.txt and skill remain byte-identical to their previously corrected versions; unrelated server-card tool-list/version catch-up excluded. Existing untracked build files left locally, not deleted or committed.
- `git diff --check`: PASS. Protected UI files and posts 02/04–06 unchanged. Open #1076 still owns post 04; its owner must apply Indexed there.
- Historical snapshot vs current fixture diagnostic is red, max difference 14.3009 (0.05 tolerance). Post and evidence disclose this; no historical live parity claimed. This does not change the same-input research comparison.

### Claimed, not confirmed
- Full `make validate` deliberately NOT RUN: #1233 owns the heavy-suite lane. Previous keyboard render red remains outside this PR.
- No independent review or live check claimed. No merge, deploy, Supabase write, production deletion or credential change. Connector wording needs the next authorized mcp deploy (JEG-1400 / Jeremy's yes).
- F6 and F18 are settled; no naming decision remains for Jeremy on this ticket. Post 04's owner action remains separate.
