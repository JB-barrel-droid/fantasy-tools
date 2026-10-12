# Run the rebuild chain

The chain (`.github/workflows/rebuild-chain.yml`, driver `pipelines/rebuild_comparison_chain.py`) imports fresh snapshots from Supabase, runs import health, rebuilds the comparison sections, runs the value check and fidelity hold, runs `make validate`, and commits generated output to main in one commit. pg_cron dispatches it every 6 hours (`rebuild-chain-live`, :17) and daily with a re-bake at 11:45 UTC (`rebuild-chain-bake-live`).

## In CI

```
gh workflow run rebuild-chain.yml
gh workflow run rebuild-chain.yml -f bake_players=true     # force a players.json re-bake
gh run list --workflow=rebuild-chain.yml --limit 3
gh run watch <run-id>
```

Expected: `completed success` (2026-10-12 runs took 14 to 40 minutes). The commit step pushes one generated-outputs commit to main and Pages deploys it. If the push conflicts with a newer generated commit, the chain re-dispatches itself with `attempt` + 1 and stops at the maximum, failing loudly. The status file `dist/modules/comparison-chain-status.json` is published even when the chain fails.

## Locally

```
export PATH=$HOME/code/fantasy-tools/.venv/bin:$PATH
make sync        # copies reference artifacts into app/ and dist/
make validate    # reference, sync, guard-harness, test-core, test-integration
```

Expected from `make sync`: a last line `Dashboard artifacts synced to app/trade-value-chart and dist (build tv-<date>-<time>-<sha>)`. Expected from `make validate`: exit 0. A red validate is a stop (it is also the deploy's own gate). Never edit or hand-merge generated files in `dist/` or `app/`; regenerate with `make sync`. The chain's data steps need Supabase credentials, so a full local chain run is not the normal path; use CI.

## When the chain is red

1. Open the failing step in the run log. A red import health stops the chain before it builds; nothing new publishes and the last good data stays live.
2. Held sources do not fail the chain; see [source-held.md](source-held.md).
3. `make validate` red inside the chain: reproduce locally on the same commit, fix forward in a PR. Never loosen an assertion to go green.
