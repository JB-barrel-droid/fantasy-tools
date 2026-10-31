## 2026-10-30 - One name-alias list for roster paste and the chat (JEG-1388, part of JEG-1202)

Contract (Jeremy's pick A, 2026-10-30): one small alias list, built in the
repo, that the page's roster paste and the chat connector's name match both
read, so a platform spelling that isn't the site's name reaches its player.
Canonical names still win. No value, Supabase or deploy change.

### Verified (check named)
- `python3 pipelines/build_name_aliases.py --check`: 16 aliases, the same rows
  in `app/v2/roster-paste.js` and `supabase/functions/mcp/names.ts`. Left out:
  Jody Fortson, Mitch Tinsley, Nyheim Miller-Hines (each is also the own name
  of a duplicate row JEG-1351 deletes: 4655, 4660, 4653).
- `tests/node/platform_spellings_matchers_check.mjs` over 858 stored spellings
  of priced players: paste 857 right (was 856), chat 857 exact (was 851 exact
  and 3 fuzzy). The one miss left is Mitch Tinsley -> 4660 in both.
- `python3 -m unittest tests.test_platform_spellings.PasteAndChatMatchers`
  with the gap list cut to Mitch Tinsley: fails on the matchers from before
  this change (Kenny Gainwell, Michael Woods, Zonovan Knight miss), passes
  after.
- `python3 -m unittest tests.test_name_aliases tests.test_platform_spellings
  tests.test_player_aliases tests.test_mcp_remote
  tests.test_roster_paste_mutation_proof`: OK. `node
  tests/test_v2_roster_paste.js`: 41 passed.

### Claimed, not confirmed
- The chat side changes nothing live until the mcp edge function is
  redeployed, which waits on Jeremy's yes. Not run in Deno, only in Node with
  type stripping.
- `make validate` not run here (no Playwright in this container); CI is the
  check.
