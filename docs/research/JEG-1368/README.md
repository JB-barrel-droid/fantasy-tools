# FantasyCalc Week 8 divergence (JEG-1368)

Accepted as genuine source opinion, consistent with JEG-830. No pricing, parser,
fit, default, or production changes. Published 2026 data only.

## Source and week

Source: https://fantasycalc.com/trade-value-chart . Producer:
`pipelines/pull_fantasycalc_12team.py`, rolling `/values/current` API.
There is no article date or upstream week: week is asserted from the content
calendar. Frozen alert-adjacent input at `4d480a6d` was fetched Oct 29 at
21:12:51 UTC, served as Week 8; latest inspected input at `168aba93` was
fetched Oct 30 at 17:05:25 UTC, also Week 8. Acquisition dates support that
label; they do not prove an upstream publication week. No 2027 claim.

## Column and scoring

`isDynasty=false&numQbs=1&numTeams=12&ppr=0/0.5/1` requests Standard,
Half PPR, and PPR separately. `to_rows` reads `value`; `redraftValue` and
`combinedValue` are distinct fields and are not the selected scoring value.
2-QB values are stored separately; no TEP column is selected.
Read-only live API checks on Oct 30 returned 197 players per scoring and
confirmed that schema (live values can move; they are not the historical pull).

## Alert and evidence limits

The committed alert at `4d480a6d` says standard/half/full 45.3/45.3/43.6%.
Recomputing from the fixture at that same commit gives 48.3/46.5/44.2%.
The report and neighboring fixture are not a transactionally paired receipt;
we cannot claim exact reproduction of the original alert. `alert.json` freezes
both the report and the actual fixture values used for reconstruction.
The latest report says 48.8/47.1/45.9%, with biases +0.60/+0.49/+0.52,
within the roughly 38–52% historical range already examined in JEG-830.
The recurring absolute 45% threshold explains investigate; no wrong-column
or nonlinear mapping evidence was found. Acceptance is source/week scoped,
like JEG-830, and leaves computed_status and numerical metrics visible.

## Five-player trace

The soft check uses the saved Indexed series (ESPN-anchor factor). The page
engine recomputes Indexed against the blended DDF basis (`value-model.js`,
VP-6.4); these are different bases, not a parser defect. Each path preserves
native × its own single factor across positions. Changing either basis would
be a computation decision for Jeremy; none is proposed here.

Stored alert-adjacent fixture (native → Indexed → one-decimal display):

|Scoring|Player|Native|Factor|Indexed|Display|
|---|---|---:|---:|---:|---:|
|standard|josh allen|6486|0.007129273054|46.240465|46.2|
|standard|bijan robinson|9657|0.007129273054|68.847390|68.8|
|standard|jahmyr gibbs|10695|0.007129273054|76.247575|76.2|
|standard|jamarr chase|7848|0.007129273054|55.950535|56.0|
|standard|brock bowers|5785|0.007129273054|41.242845|41.2|
|half|josh allen|6564|0.007009214370|46.008483|46.0|
|half|bijan robinson|9597|0.007009214370|67.267430|67.3|
|half|jahmyr gibbs|10628|0.007009214370|74.493930|74.5|
|half|jamarr chase|7933|0.007009214370|55.604098|55.6|
|half|brock bowers|5773|0.007009214370|40.464195|40.5|
|full|josh allen|6559|0.006918697071|45.379734|45.4|
|full|bijan robinson|9602|0.006918697071|66.433329|66.4|
|full|jahmyr gibbs|10634|0.006918697071|73.573425|73.6|
|full|jamarr chase|7988|0.006918697071|55.266552|55.3|
|full|brock bowers|5918|0.006918697071|40.944849|40.9|

Current display engine, 12 teams, default roster, same five players:

|Scoring|Player|Native|Factor|Indexed|Display|
|---|---|---:|---:|---:|---:|
|standard|josh allen|5935|0.006574972072|39.022459|39.0|
|standard|bijan robinson|9680|0.006574972072|63.645730|63.6|
|standard|jahmyr gibbs|10679|0.006574972072|70.214127|70.2|
|standard|jamarr chase|8007|0.006574972072|52.645801|52.6|
|standard|brock bowers|5664|0.006574972072|37.240642|37.2|
|half_ppr|josh allen|6006|0.006571339800|39.467467|39.5|
|half_ppr|bijan robinson|9620|0.006571339800|63.216289|63.2|
|half_ppr|jahmyr gibbs|10612|0.006571339800|69.735058|69.7|
|half_ppr|jamarr chase|8094|0.006571339800|53.188424|53.2|
|half_ppr|brock bowers|5652|0.006571339800|37.141213|37.1|
|ppr|josh allen|6002|0.006535348958|39.225164|39.2|
|ppr|bijan robinson|9625|0.006535348958|62.902734|62.9|
|ppr|jahmyr gibbs|10618|0.006535348958|69.392335|69.4|
|ppr|jamarr chase|8150|0.006535348958|53.263094|53.3|
|ppr|brock bowers|5794|0.006535348958|37.865812|37.9|

Reproduce: `node --experimental-strip-types docs/research/JEG-1368/trace.cjs`.
This uses the shared get-values input builder and actual browser value engine,
not a browser screenshot. No visual/render sweep was run.

Test: `python3 -m unittest tests.test_jeg1368_fantasycalc tests.test_source_divergence`.
The resolution test fails on base `168aba93` (investigate != reviewed), observed
before the resolution edit; metrics remain investigate after acceptance.
No before/after pricing change: all sample values remain identical.
