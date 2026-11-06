## 2026-11-05 - Preserve malformed override delimiters (JEG-1343 / PR #1219)

Contract: Jeremy explicitly approved the scoped `mcp/value-context.ts` correction after the diagnostic dispatch was denied without execution. This is the single author retry with that fresh approval; it authorizes code correction, not deployment. Continue existing `claude/JEG-1343` from `18bc15857231a6d7a5f701e61750b6efc83323d6`.

### Verified (check named)

- PR/head and ticket comments were reread before work; the branch remained at `18bc1585`, the original checkout was clean, and the diagnostic session had finished. Recorded the author claim before changes. Shared agent context still returns Tool not found. No JEG-1506/1479 source or other writer's branch was touched.
- Root cause: `linkValueContext` stripped trailing commas and colons before strict validation. `valuecontext=1&ov=:` became an empty context/default prices; `ov=<key>:58,` became a valid override. Direct get-values correctly rejects both with HTTP 400.
- Only production change: retain `:` and `,` while trimming ordinary sentence punctuation. Those characters are override delimiters, so malformed text must reach strict validation intact. Period/semicolon/question/exclamation trimming and existing URL wrapper/percent decoding remain.
- Failing before: the extended `tests/node/mcp_value_context_check.mjs` on original production code fails at `MCP must refuse the same malformed override: :`; direct handler returns 400 but MCP returns a successful answer. Log: `/workspace/jeg1343-malformed-before.log`.
- Passing after: `node --experimental-strip-types --no-warnings tests/node/mcp_value_context_check.mjs /workspace/jeg1343-fullvalidate/dist`, exit 0 (`/workspace/jeg1343-malformed-after.log`). It exercises raw and encoded colon-only/trailing-comma overrides through the parser, real get-values handler and deployed MCP handler. No prices or repaired return link appear on refusal. The actual MCP cache is warmed with default and valid custom answers first: malformed requests reach get-values unchanged and receive 400; subsequent default/custom answers stay unchanged and cached.
- Successful controls preserve exact return-link `ov` for sentence punctuation, Markdown/Slack wrappers, unencoded and encoded positive adjustments, and both packed override encodings (`z:` / `z2:`). The test's first packed-adjustment fixture used the wrong property (`kind`); corrected it to the existing codec contract (`type`) before the final passing run. Production code needed no additional change.
- `tests/node/mcp_week_check.mjs` passed. JEG-1224 shared-link harness: M1–M3 pass; 22 cases, 0 harness errors and 0 differences from the declared record (11 other specs remain declared failing). `git diff --check` passed. Logs: `/workspace/jeg1343-malformed-week.log`, `/workspace/jeg1343-malformed-regressions.log`.
- Focused checks reuse the retained built fixture from the earlier full validation; they import the current handler/parser source. No broad suite or site build was duplicated. Tests strengthen coverage without removing or weakening prior assertions.

### Claimed, not confirmed

- The earlier full `make validate` PASS belongs to `18bc1585`; it does not qualify this corrected source. Full current-head CI and independent high-risk review remain deferred/pending; the diagnostic finding was not a qualifying review pass.
- No live behavior or deployment is claimed. No release merge, edge-function deployment, Supabase runtime/data change, deletion or access change occurred. The PR remains draft; release/ready-cap holds remain in force.
