## 2026-10-31 - JEG-1400 redeploy succeeds

Contract: Jeremy's fresh yes at 12:38 PM CT authorizes fixed verification, mcp-only
redeploy from main and rollback on failure. Earlier entries record prior attempts.

### Verified (check named)
- First action, Supabase metadata: v20 verify_jwt false, matching recorded v18.
- git fetch origin: c267aa71 unchanged, both fixes present. Captured current v20
  source using functions download mcp with explicit project-ref.
- Corrected /tmp/jeg1400-verifier.mjs uses only public find_trades fields:
  structuredContent.trades, userGives[].name and userGets[].name. It asserts the
  exact Taylor -> St. Brown candidate exists at floor 0 and is absent at 0.5.
- Fresh get-values indexed data establishes the case (ppr/12): rival-ok nets
  +0.5 (band 1), +1.2 (band 1.56), -0.6 (band 1.053). Correct average 0.2,
  buggy Math.abs average 0.7667. CBS net +13.1 is not rival-ok and is excluded.
- node --experimental-strip-types /tmp/jeg1400-preflight.mjs: same check rejects
  local Math.abs mutation through handleRpc and passes live v20. v20/v18 already
  contain the fix, so calling them a buggy baseline would be incorrect.
- supabase functions deploy mcp --project-ref iskiybsimubiujwuchsl --no-verify-jwt
  --use-api from detached main: succeeds; metadata confirms ACTIVE v21, JWT false.
- node /tmp/jeg1400-postdeploy.mjs: live check A baseline=1 / filtered=0; check B
  get list has no total and Zzyzx Notaplayer has closest names Tylan Wallace,
  Kenneth Walker III, Josh Palmer. Both passed on v21; no rollback this run.
- Rollback point: v20 source in ops-JEG-1400-v20-rollback (itself restored v18).
  Failure handler was armed but not invoked. No retries, other function deploys,
  migrations, production-data writes or credential changes.

### Claimed, not confirmed
- None for the two requested checks. Earlier failed-verifier rollback remains
  historical; this successful run supersedes the incomplete verification status.
