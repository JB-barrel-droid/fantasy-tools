## 2026-10-30 - JEG-1343: the chat honors a pasted link's own values (JEG-1225 slice 4c)

Contract (Jeremy, JEG-1224 D1 "B", and JEG-1124 "A"): a chat given a site link with the sender's own basis
or overrides prices its answer under them, says so, and its link back keeps them. Code and PR only;
nothing deployed.

What changed:
- `supabase/functions/mcp/value-context.ts` (new, pure): reads `basis=`, `ov=` and `valuecontext=1` from
  the pasted text, the "Values:" line, the refusal messages and the link-back parameters.
- `supabase/functions/mcp/values-client.ts` (new): the get-values request (GET as before; JSON POST when
  a value context is sent) and its error reading (week and value-context refusals become tool errors).
- `tools.ts`: `runTool` sends the context with every fetch, as it does the week, and fails closed when a
  get-values without `value_context` was asked for a basis or overrides. `index.ts`: the cache keys
  include the context. `analyses.ts`: the fetcher takes it.
- Tests: `tests/node/mcp_value_context_check.mjs` (+ `tests/test_mcp_value_context.py`, in `make
  validate`); fails on main ("the link's own text goes to get-values"), passes here. The JEG-1224 harness
  gets the 4a reader patch and a stub that prices a sent `ov`; M1-M3 flip to pass, mutation exit codes
  follow.

Independent review (before ready), fixed in the second commit:
- The "Values:" line printed get-values' basis object ("[object Object]"); it names the basis from the
  link's text now ("fantasycalc", "a blend of espn 60%, fantasycalc 40%"), tested against the real handler.
- The whole overrides map went into structuredContent and counted against a trade reply's size budget (600
  overrides made find_trades say "too large"); the answer keeps counts only.
- Pasted punctuation (a markdown ")", a full stop), `&amp;`, and another URL's `ov=` broke or took over the
  context; trailing punctuation is trimmed, `&amp;` decoded, and a `valuecontext=1` query wins.
- On views where the site doesn't apply a link's values yet, the reply says the link opens on the defaults.
- The chart cache is bounded like the values cache, since its key now carries link text.
- Tests now cover find_trades_league, risers_fallers, audit_values and compare_trade by_source too.

Current-head review (5afa2de, after the 6 PM CT main merge), fixed in the next commit:
- A link pasted as markdown `[url](url)` or Slack `<url|text>` ran its last value into the next URL and was
  refused; a value now stops at brackets, pipes and quotes.
- The value context could push a trimmed find_trades reply over its budget; the final size check leaves the
  "Values:" line and `value_context` out, like the site link.
- explain's bare site link no longer picks up the link's parameters.
- Decided and documented: an unmarked older link comes back marked, so the site opens on the values the chat
  priced rather than merging them into the reader's own (JEG-1224 O1L).

Left alone, noted:
- The site's `#trade-targets` path (DDFAssist) still doesn't apply a link's value context (S2 in the
  JEG-1224 README). A site gap, not this ticket.
- JEG-1224 O1/O2 and mutations W1/W3 fail with "carriedTrade is not defined": the harness lifts
  `tradeHash` out of v2.js and the #1208 change gave it a new dependency. Harness upkeep, before this
  branch too.

Deploy order when merged, each on Jeremy's yes: Pages (the strict reader), then get-values (JEG-1225),
then mcp (this).
