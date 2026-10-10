# Fidelity pulse: per-source tolerance and holds (JEG-520)

Jeremy, 2026-10-09: a red in the fidelity pulse holds that source, "though with
some tolerance. Some of the values like fantasy calc are based on live data,
some update at the posters discretion, so we need a tolerance to understand the
difference between day to day adjustments vs old/bad data."

The rules are implemented in `pipelines/fidelity_pulse.py` (`RULES` in the
published `dist/modules/fidelity-pulse.json`). The holds are applied in the
rebuild chain by `pipelines/fidelity_hold.py`. Tests:
`tests/test_fidelity_hold.py`, plus `ProjectionSameVersion` and the count-drift
cases in `tests/test_fidelity_pulse.py`.

## What holds

A red result in `publisher_vs_stored`, `stored_vs_chart`, `freshness` or
`scrape_validity` holds the source. Amber and unknown results never hold.
`reference_vs_engine` reds are already held by the JEG-479 value check.

A hold applies to one source and every series derived from it
(`value_check.SOURCE_DERIVED`). It is written as `validationHold` with reason
`fidelity: <stage>`. The page labels the held series and keeps them out of DDF
Value. Every other source still publishes, so a hold never takes down the whole
site.

- **Published charts** (USA Today, FantasyCalc, FantasyPros, CBS) are served
  from the section of the last chart file the pulse did not hold. The pulse
  carries that file's `built_at` forward in `last_good`, and the chain finds the
  fixture commit with that `built_at`.
- **Projections** (ESPN, CBS rest of season, Razzball) keep their current
  section, labelled and out of DDF Value. Their values are baked into
  players.json together with the ESPN anchor, and `test_static_export` checks
  that triple, so restoring the section alone would fail validate and stop
  every source. Restoring the whole set is open as a follow-up.

**When holds start and end.** When a hold starts, ends or changes stage, the
pulse dispatches the chain. The chain's completion re-runs the pulse, which
sees the same holds, so the cycle stops there. A hold lasts while the pulse
reports it.

**What the pulse checks while a source is held.**

- `stored_vs_chart` is n/a, because the chart shows the kept section. The
  exception is a hold caused by `stored_vs_chart` itself: it stays red until a
  newer stored save exists.
- `freshness` reads the stored week or snapshot, which is what the next build
  would serve.

## Per-source tolerance, with the measured drift

### FantasyCalc (live crowd feed)

There is no versioned snapshot, so the stored save is compared with the live
API. Rule:

- A value that moved since the save is amber. Players outside a movement band
  of max(25%, 50 points) are listed by name.
- The result is red (held) when more than 10% of values are outside that band,
  which means a broken save rather than movement.
- It is also red on a column swap, or on a player above the list's churn line
  who appears on one side only.

**Measured on 2026-10-09** from `source_trade_values`: week 5 as_published,
every pair of saves from 10-08 12:59Z to 10-09 17:05Z, about 1,150 to 1,185
values per pair.

| Gap between saves | Median move | p90 move | Share outside the band |
| --- | --- | --- | --- |
| 0.9 h | 0% | 0% | 0% |
| 3 to 4 h | 1.5 to 1.7% | 7 to 10% | 0 to 0.8% |
| 6 to 7 h | 2.4 to 5.0% | 13 to 27% | 0.5 to 4.2% |
| 10 to 14 h | 4.9 to 6.4% | 20 to 31% | 2.3 to 7.0% |
| 17 to 28 h | 6.1 to 7.6% | 28 to 33% | 5.5 to 8.0% |

The probe saves FantasyCalc whenever it changes, at least every 4 h, so the
pulse normally sees a save under 7 h old, where at most 4.2% of values fall
outside the band. A full day of drift still stays under the 10% red line, at
8.0%.

The 10-06 save is left out of the table: it holds only 585 rows (one QB
setting), and it disagrees with every later save on 25 to 29% of values. That
is the broken-save signature the red line exists for.

The band is unchanged by JEG-520; this measurement confirms it.

### Article charts (USA Today, FantasyPros, CBS)

The match is exact against the same article version.

- **Update available (amber).** The page's `dateModified` is later than the
  save. This is a newer article version, not bad data, and stays amber for
  24 h (`GRACE_HOURS`).
- **Stale (red, held).** The revision is still not stored after 24 h.
- **Red (held) at once.** A difference with no later revision, a different
  week, or a different article.

**Measured:** in the 21:51Z run on 2026-10-09, every stored value matched the
publisher exactly: USA Today 891/891, FantasyPros 630/630 and CBS 448/448.
Since the pulse started, mismatches on these charts have come from save
faults, such as GAP-USAT-SAVER-LEGACY-RESOLVER, and not from publisher edits.
That is why there is no value band.

### Projections (ESPN, CBS rest of season, Razzball)

Daily changes are normal. The comparison is exact against the same publisher
version. The source probe's fingerprint (`pipelines/source_probe.py`) that is
acknowledged with the save names the content the save read.

- **Red (held)** when any of these is true:
  - The fingerprint read now equals that acknowledged fingerprint, so stored
    differs from the same-version publisher.
  - A block of players is missing or extra: more than 10% of a position, and
    at least 3 players.
  - The fingerprint changed, but the save is more than 24 h old (stale).
- **Amber** while the fingerprint has changed and the save is less than 24 h
  old. This is a daily update with an ingest pending.
- **Amber "unconfirmed"** when no fingerprint was recorded with the save, or
  none can be read now.

All three sync workflows now take a fingerprint before reading data on runs the
probe did not dispatch, and acknowledge it, so every save names its content.

**ESPN: amber, then re-sync.** Jeremy, 2026-10-10: "Amber, then re-sync." ESPN
revises projections during the day without changing the date.

- A live value that differs from a row saved before ESPN's last change is
  amber, labelled "update available". That covers a changed fingerprint, the
  change probe holding content no ingest has saved, and a save with no
  recorded fingerprint.
- The pulse then dispatches the ESPN sync (`espn-supabase-sync.yml`, the
  module's `RESYNC_WORKFLOW`). It sends one request per ESPN version every
  3 h (`RESYNC_RETRY_HOURS`), and none when the change probe already
  dispatched that version. The sync acknowledges the fingerprint it read and,
  on new content, runs the chain. The chain's completion re-runs the pulse.
- Only a mismatch that survives the re-sync is red and holds ESPN: the save's
  fingerprint equals ESPN's now, so stored differs from the version it read.
  A missing or extra block of players is red at once. A save more than 24 h
  behind a changed ESPN is still stale (red).

Measured: within one day, 13 of 566 ESPN players changed between the 19:25Z
save and 21:51Z on 2026-10-09 (one injured-reserve move). The 18:00Z and
21:51Z pulses had 27 and 39 mismatches, and a fresh ESPN sync cleared each
set. CBS rest of season and Razzball keep the plain rule above. Their
changes come in daily batches, and the probe's own 4-hourly ingest covers
them.

### Same-day re-save after the chart was built (stage 2)

A snapshot date can be re-saved in place after the chart was built from it.
Stage 2 treats every player the re-save changed, added or dropped as amber
until the next chain run, provided stage 1 shows that player equal to the
publisher. The save time is the snapshot's last row write, or the fingerprint
acknowledgement of that save, whichever is later. A re-save that only
deletes rows (ESPN prunes the players it no longer lists) moves no remaining
row's stamp. The same difference against a save made before the build is a
chart fault and holds. So is a re-saved row that differs from the publisher.

**Measured day-to-day change:** per stored snapshot date, half-PPR, players
present on both days.

| Source | Days | Players changed | Median move | p90 move |
| --- | --- | --- | --- | --- |
| CBS rest of season | 10-08 to 10-09 | 72% | 2.5% | 13.9% |
| CBS rest of season | 10-02 to 10-08 | 97% | 9.6% | 22.7% |
| Razzball | 10-07 to 10-08 | 12% | 0% | 1.2% |
| Razzball | 10-06 to 10-07 | 34% | 0% | 9.0% |

ESPN keeps one live set, so it has no stored history. Within one day, 13 of
566 ESPN players changed between the 19:25Z save and 21:51Z, after one
injured-reserve move. Changes this broad, and this uneven between publishers,
leave no value band that separates an update from a fault. Only version
identity does.

### Count drift (all sources)

Jeremy, 2026-10-09, applied in the pulse's scrape-validity stage:

- A drop of more than 10% in a position's stored or chart player count against
  the prior week is red (held), but only when the publisher's own list for
  that position did not drop below 90% too. That case is a scrape loss.
- A drop that the publisher made itself, or that cannot be confirmed because
  the publisher was not read, is amber.
- A drop of 5 to 10% is amber, alert only.

The import-health count hold (JEG-512, `verify_import_health.py`) is a separate
check with its own code path. It uses the same 10% threshold.
