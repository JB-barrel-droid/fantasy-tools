# get-values logging contract (JEG-1258, part of JEG-1061)

Jeremy, Oct 25 (JEG-1061): keep get-values' in-memory limiter as a soft per-instance guard, and log
fresh custom-league computes and rate-limited requests, then revisit at launch. This directory holds
the contract for those log lines, the recorded state of the current handler against it, and a narrow
hook proposal for the get-values owner. Nothing here changes runtime code.

Files:

- `tests/node/jeg_1061_logging_contract.mjs`: the harness (runs `supabase/functions/get-values/index.ts`
  read only, in node, with a stub Deno, the built `dist/` served in place of the site, every other host
  refused, a frozen clock moved by hand, and a recording console; one fresh module instance per
  scenario).
- `tests/test_jeg_1061_logging_contract.py`: the offline wrapper (self-test, plus the handler in strict
  expected-failure mode).
- `expected_failures_before_hook.json`: the exact violations the current handler produces.
- `hook-proposal.patch`: the proposed hook against main `b8630697`.
- `hook-proposal-on-pr1024.patch`: the same hook rebased by hand onto PR #1024 (JEG-1179, head
  `179288b`), with the priced `week` added.

## The contract

Each event is one console call (any level) whose single argument is a JSON object string, or the object
itself, with `event` starting `get_values.`. Free text is allowed but carries no events.

| Event | When | Fields (all required unless marked) |
| --- | --- | --- |
| `get_values.compute` | once per fresh custom-league computation (answer-cache miss and `league_custom` not empty) | `scoring`, `teams`, `superflex`, `custom` (the answer's `league_custom`), `charts` (include=charts), `ms` (compute time, number >= 0), `week` optional (int or null) |
| `get_values.rate_limited`, `limit: "general"` | the 30/min per-key 429 | `limit`, `max` (30), `window_s` (60) |
| `get_values.rate_limited`, `limit: "compute"` | the 10/min per-key fresh-compute 429 | `limit`, `max` (10), `window_s` (60), `scoring`, `teams`, `superflex`, `custom`, `charts`, `week` optional |

No other fields. No compute event for a cached answer, the default league, a 400, a 429 or a preflight.
No request header value (IP or forwarded-for entry, authorization, apikey, cookie) and no player name
anywhere in the console output; the harness sends sentinel values in every one of those headers, and no
fixture contains an IP, token, key or roster/person data.

Statuses the harness also holds (a change is a harness failure, exit 2, not a contract result): 10 fresh
computes from one key pass and the 11th in the minute is a 429 `{error: "rate limited",
retry_after_seconds: 60}`; a cached league is still served to that key; another key has its own budget;
the window resets after 60 s; the 31st request in a minute is a 429; OPTIONS is 204 and never limited;
invalid input is a 400.

## Scenarios

- `fresh-custom`: a plain custom league, then one with include=charts and superflex: 2 compute events.
- `cache`: the same custom league by POST, again by POST, by GET with a JSON league string, then after the
  5-minute answer TTL: 2 compute events (first and after TTL).
- `default`: default league by POST and GET, a garbage league string, default with charts, invalid teams,
  OPTIONS: no events.
- `compute-limit`: 10 computes, the 11th (429), a cached league after the limit, another key, then the
  same key after 61 s: 12 compute events, 1 compute rate_limited event.
- `general-limit`: 30 cheap 400s, the 31st (429), OPTIONS, another key: 1 general rate_limited event.

## Commands

```
node --experimental-strip-types --no-warnings tests/node/jeg_1061_logging_contract.mjs --self-test
node --experimental-strip-types --no-warnings tests/node/jeg_1061_logging_contract.mjs dist
node --experimental-strip-types --no-warnings tests/node/jeg_1061_logging_contract.mjs dist --expect-failures tests/fixtures/jeg_1061_logging/expected_failures_before_hook.json
python3 -m unittest tests.test_jeg_1061_logging_contract -v
```

Exit codes: 0 pass, 1 contract violations (or, with `--expect-failures`, any unexpected failure or
unexpected pass), 2 harness failure.

## Current handler (main b8630697): failing before the hook

The plain run exits 1 with exactly these five violations, the same on every run; the `default` scenario
passes, the statuses all hold, and nothing leaks (the handler logs nothing):

```
fresh-custom/compute.count: expected 2, got 0
cache/compute.count: expected 2, got 0
compute-limit/compute.count: expected 12, got 0
compute-limit/rate_limited.count: expected 1, got 0
general-limit/rate_limited.count: expected 1, got 0
```

PR #1024's head `179288b` gives the same five.

## Hook proposal for the get-values owner

`hook-proposal.patch` (16 added lines, no removed lines, nothing else touched): a `logEvent()` helper
that writes `console.log(JSON.stringify(fields))`, one call before each of the two 429 returns, and one
after a fresh custom-league compute is cached, timed with `performance.now()`. No limiter, cache,
default, policy or response change. Verified in a scratch copy only (not in the repo): main + the patch
passes the full contract (exit 0), and PR #1024 + `hook-proposal-on-pr1024.patch` passes too. On #1024
the third hunk of the main patch does not apply as is (the cache key line changed); the second patch is
that hunk placed by hand.

When the hook lands, set `expected_failures_before_hook.json` to `[]` in the same PR; the wrapper then
requires a full pass. Until then the wrapper passes only while the violations are exactly the list
above, so a partial or wrong hook fails it, and so does a hook landing without the file update.

Mutations checked by hand against scratch copies (all caught): compute limit raised to 11 and general
limit raised to 31 (harness failure, exit 2); hook logging default-league computes, logging cache hits,
adding the client key as an `ip` field, and labeling the compute 429 as `general` (exit 1, named
violations). The self-test covers 17 log-level mutations without the handler.
