Main snapshot: `c267aa71ef1d445670516b1858e0f9dfe5a48f93`. Source: git, no changed-files API.

FULL = smoke, validate-base, core-1, core-2, core-3, core-4, core-5, full-unit. Any suffix lists additional touched shards.

| PR | Commit | Selection (smoke always runs) |
| --- | --- | --- |
| #1248 | `76ee1c41` | FULL |
| #1246 | `fc5fd8cc` | FULL |
| #1242 | `dcf7b4cc` | FULL + fe-values |
| #1211 | `168aba93` | FULL + fe-values, fe-targets, fe-league, fe-settings |
| #1231 | `db46ecaf` | FULL + connector, fe-finder, fe-league |
| #1232 | `7358589c` | FULL + fe-finder, fe-waivers, fe-league |
| #1227 | `31e53bec` | FULL + fe-finder, fe-league |
| #1192 | `8ec37b45` | FULL |
| #1228 | `eb9a75da` | FULL |
| #1220 | `374dc8f7` | FULL + connector, fe-values, fe-compare, fe-finder |
| #1033 | `a750ca07` | FULL + connector, fe-compare, fe-finder |
| #1222 | `37a35ced` | FULL + pipelines |
| #1210 | `60781577` | FULL |
| #1187 | `bb0bcf10` | FULL |
| #1216 | `b923c11d` | FULL + connector, fe-values, fe-compare, fe-finder |
| #1218 | `44d7f013` | FULL + pipelines |
| #1214 | `b5f35fca` | FULL + connector, fe-league |
| #1124 | `a95a3ded` | FULL + connector, fe-values, fe-compare, fe-finder |
| #1212 | `8d8c1931` | FULL |
| #1213 | `760a1cb9` | FULL |
| #1179 | `6a2cca0d` | smoke, fe-finder, fe-waivers, fe-league |
| #1145 | `661f3d0b` | FULL + fe-finder, fe-league |
| #1092 | `dc3f3d8d` | FULL + fe-finder, fe-league |
| #1208 | `b3eb8d97` | FULL + fe-finder, fe-league |
| #1105 | `5d339097` | FULL + fe-compare, fe-finder, fe-league |
| #1209 | `f2d50519` | FULL + pipelines |
| #1167 | `74464163` | FULL + fe-values, fe-compare, fe-finder, fe-targets, fe-league |
| #1156 | `0fc5eaa4` | FULL + connector, fe-values, fe-compare, fe-finder, fe-league |
| #1184 | `1adb13b2` | FULL |
| #1200 | `6b33b678` | smoke, connector |

Known follow-up audit (documented links; not proof that no other regression exists):

| Original → follow-up | Broken area | Skipped? | Evidence |
| --- | --- | --- | --- |
| #1192 → #1222 | pipelines | No | docs/claude-log/2026-10-30-jeg1391-prune-merged-player-keys.md: duplicate merge left stale slugs in comparison player_keys. |
| #1156 → #1220 | connector | No | docs/claude-log/2026-10-30-jeg-1385-get-values-pairing.md: current/prior included-set pairing; JEG-1029 redeploy held for fix. |
