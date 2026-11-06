## 2026-11-03 - Stored roster-name matcher acceptance (JEG-1388)

Contract: Codex owns the current correction. Reconcile the stale offline
identity evidence and generated aliases after JEG-1351's completed cleanup;
preserve collision and ambiguity guards. No Supabase access/change, production
data action, merge or deployment is part of this work.

### Verified (check named)

- Ownership checks found no active JEG-1388 acceptance claim or overlapping
  open PR. Historical #1214 ownership is not a current Claude assignment.
  The correction branch starts at main `aba808b8e2459d103b920d8b8f6d0bfdfd486e28`.
- The [JEG-1351 read-back](https://linear.app/jegabee/issue/JEG-1351#comment-04a290c5-0d4b-48ae-8276-93ab9b5b9979)
  records 4653/4655/4660 removed and 2785/437/4363 active. Only those three
  duplicate rows are removed from the offline identity mirror; every other
  identity field is unchanged. Its paired active flags transfer to the three
  originals, leaving 4,699 identity rows and 2,126 active keys. The original
  pull date is preserved; reconciliation metadata explicitly says this was
  not a fresh database pull. The paired digest is recomputed locally.
- Before correction, the new snapshot acceptance assertion fails on all
  three obsolete keys, and the no-misses matcher assertion fails on
  Nyheim Miller-Hines. Collision and ambiguity controls already pass.
- `docs/research/JEG-1202/build_matrix.py --check`,
  `pipelines/build_platform_spellings.py --check`, and
  `pipelines/build_name_aliases.py --check`: no drift after regeneration.
  Audit evidence uses the committed Sleeper base pulled
  `2026-11-03T09:17:14+00:00`. Outputs contain 1,037 grounded platform rows
  (929 Sleeper, 83 ESPN, 25 Yahoo) and 19 identical matcher aliases.
  The SQL mirror is a generated parity artifact, not an apply instruction.
- `node --experimental-strip-types --no-warnings
  tests/node/platform_spellings_matchers_check.mjs`: 862 checked, paste
  862 correct, chat 862 exact, zero misses. The five pinned names resolve in
  both: Mitch Tinsley -> 4363, Zonovan Knight -> 868, Kenny Gainwell -> 785,
  Michael Woods -> 928, Nyheim Miller-Hines -> 2785. No obsolete known-gap
  exemption remains.
- `PLAYER_ALIASES_SOURCE=json python3 -m unittest
  tests.test_platform_spellings tests.test_name_aliases
  tests.test_jeg1202_platform_spellings tests.test_player_aliases
  tests.test_mcp_remote tests.test_sleeper_projection_idmap
  tests.test_roster_paste_mutation_proof`: 69 passed, zero skips.
  `node tests/test_v2_roster_paste.js`: 41 passed.
- The replaced assertions described obsolete evidence: real duplicate rows
  already removed by JEG-1351, and suffix spellings now independently
  grounded by Sleeper IDs. Synthetic tests retain the original protections:
  another player's canonical name and aliases shared by two keys are held;
  ungrounded observations cannot supply a stored row. Runtime ambiguity
  returns no player even when one candidate has a higher value. Canonical
  own names still win and absent alias targets stay unmatched.
- `data/fixtures/current/players.json` is byte-identical to the base:
  SHA-256 `2520a72a0bcdee9579ff92217c328b7faef779e01a7ebce3f0a8eacf3076866e`.

### Claimed, not confirmed

- These are offline Node/Python source-and-fixture results, not a live page,
  Deno runtime or deployed connector acceptance. The player-value fixture is
  dated October 31. The original #1214 implementation/deployment receipts
  do not establish that this correction is deployed.
- No merge, deployment, Supabase migration or production write was run.
  Independent review and current CI remain release gates.
