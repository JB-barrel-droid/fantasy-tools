# DDF state: one object for the site and the LLM tools

Ticket JEG-1025 (part of JEG-1024). Status: spec and codec merged-ready 2026-10-24; the site controls are built (JEG-1026: `app/v2/ddf-assist.js`, footer on every tab); the MCP tools are JEG-1027.

Decision (Jeremy, 2026-10-24): "Portable link and code, no accounts (Recommended)". Work moves between a chat and the site as a link or a pasteable block; nothing is stored on a server, and the format leaves room for a saved-state backend later (the same object, stored under an id).

## The object

```
{ "v": 1,
  "league": { "scoring": "ppr|half_ppr|standard", "teams": 8|10|12|14,
              "roster": {"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1,"SUPERFLEX":0,"BENCH":6},
              "shares": {"QB":0.2,"RB":0.35,"WR":0.35,"TE":0.1},
              "bso": 0.2, "inj": "recent|all", "conf": 0.5|1|1.5,
              "weeks": {"regend":14,"playoffs":[15,17],"optimize":"season|regular|playoffs","week":7} },
  "work":   { "view": "compare|targets|finder",
              "give": [{"key":"101","name":"..."}], "get": [...],      // Compare a trade
              "mine": [...], "theirs": [...],                          // Find a trade rosters
              "target": {"key":"9"} },                                 // Trade targets
  "sources": ["espn","fantasycalc"], "asOf": "2026-10-24" }
```

Every section is optional. `league` carries the sender's settings so the receiver prices the same league. `work` is what the person was doing.

## Two encodings, one object

- **URL query**, appended to the site hash (`#compare-trade?...`, the existing form). The legacy parameters keep their meaning: `give`, `get`, `scoring`, `roster` (`QB1.RB2.WR3.TE1.FLEX1.SF0.BN6`), `shares` (`QB0.200_RB0.350_...`), `bso`, `inj`, `conf`, `regend`, `playoffs` (`15-17`), `optimize`, `week`, and the older `bench=` (0.150 means no override). New: `v`, `teams`, `view`, `mine`, `theirs`, `target`, `src`. The hash never leaves the browser, so links carry no data to our servers.
- **Pasteable block**, a fenced `ddf-state` code block holding compact JSON, plus an optional "Open on the site" line. The reader also accepts bare JSON and a site link inside prose, so it survives being pasted through a chat.

## Players

A list entry is `{key, name?}` or a name-only `{name}`. Keys are the engine's `player_key` and win when present. An LLM does not know keys, so name-only entries are normal: the site resolves them with the roster-paste matcher (JEG-1010) and says which it could not match. Names in the URL are written `n:<name>`. The name is percent-encoded once (a space is `%20`). Commas, ampersands and equals are encoded a second time, because `URLSearchParams` decodes once before the comma split. Lists are capped at 40 and de-duplicated.

## Rules a reader follows

1. Unknown fields are ignored. A newer `v` warns and reads the fields it knows.
2. A bad `league` drops the whole league section, never half of it (a partial league would price a different league than the sender meant). A bad `work` list drops that list. The reader returns warnings and the site shows them.
3. The reader never invents a player: unresolved names are reported, not guessed.
4. A reader that has no use for a section (a chat has no use for `view`) keeps it and returns it unchanged, so a state can round trip through a chat.

## Code

`app/v2/ddf-state.js`: `normalize`, `encodeQuery`, `decodeQuery`, `encodeBlock`, `decodeBlock`. Plain script that also loads under node and Deno. The MCP function will load it from the published site at cold start, the way `get-values` loads `value-model.js`, so the site and the tools cannot drift (JEG-1027). Test: `tests/test_ddf_state.py`.

## Open gaps (found writing this; tracked on the child tickets)

- **`get-values` prices the full league (JEG-1031).** It accepts the normalized `league` (roster shape, position shares, season weeks, advanced settings), maps it with the page's clamps and computes on demand with nothing stored. MCP passes `state.league` through and no longer adds the unpriced-league note.
- **Trade links now carry the team count** (JEG-1026): the site writes `teams` and reads it. Links written before that have none, and the reader's team count stays.
- **`sources` and `asOf` are advisory.** The receiver's shown sources and week win unless the person asks to match the sender.
