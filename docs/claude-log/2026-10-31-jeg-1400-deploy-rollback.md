## 2026-10-31 - JEG-1400 authorized deployment and rollback

Contract: resume after Jeremy established CLI authentication; deploy only mcp and
run both live checks, restoring saved v18 source on failure, without automatic retries.

### Verified (check named)
- git fetch origin: main remains c267aa71; requested rival-edge and unmatched-name fixes present.
- supabase functions download mcp --project-ref iskiybsimubiujwuchsl --use-api:
  saved active v18 source in ops-JEG-1400-rollback.
- supabase functions deploy mcp --project-ref iskiybsimubiujwuchsl --no-verify-jwt --use-api
  from detached main: succeeded; metadata confirmed active v19.
- Live read_state: get list has no total; Zzyzx Notaplayer named with closest matches.
- Live find_trades baseline at min_rival_edge 0 returned Taylor for St. Brown. The
  verifier then threw because public trades omit charts. It never called the 0.5 case.
- Restored captured v18 source with one mcp-only deploy from rollback directory;
  metadata confirmed active v20 with verify_jwt false. Version counters advance
  on rollback deployments. No automatic retries, other function deploys, migrations,
  data writes or credential changes.

### Claimed, not confirmed
- Check A remains unverified due to the verifier error, not a demonstrated product failure.
- Both requested checks did not pass; JEG-1400 must remain open. Fix the verifier
  before a separately resumed run. This entry supersedes the earlier authentication
  blocker: Jeremy resolved authentication before this run.
