# Consolidation Layer — Codex Architectural Review

**Status:** Input for Jeremy's review. Not a decision — recommendations only.
**Date:** 2026-10-03
**Source:** Codex (gpt-5.6-sol) via `codex exec`, prompted with the full scope text.
**Scope under review:** [consolidation-layer-scope.md](./consolidation-layer-scope.md)

**How to read this:** Codex evaluated the scope against the six consolidation goals Jeremy set:

1. **Single source of truth** — one final value per player/source/scoring/teams/view
2. **Separation of concerns** — detail rich, consolidation dumb/flat, presentation reads consolidation only
3. **Debuggability** — wrong values localize to exactly one layer
4. **No disruption** — strangler-fig migration, detail keeps working
5. **Fail-closed** — SHA-verified bake, divergence blocks the build
6. **Easy auditability** — any chart value traces back: presentation → consolidation row → detail bake → source data

Each section names which goals the scope's choices serve or put at risk.

> Environment note: Codex's file/shell access was unavailable in this sandbox
> (`codex-code-mode-host` missing), so the full scope text was pasted into the
> prompt. Codex did not read repo files directly; findings grounded in the
> pasted scope plus the background facts supplied in the prompt.

---

# 1. Schema Design

## a. Explicit `qb_variant` versus an opaque combo key

Using separate `scoring`, `teams`, and `qb_variant` fields is the better storage schema, but only if the consolidation schema—not `sourceComboKey()`—becomes the canonical definition of tuple identity.

It serves:

- **Goal 1 — Single source of truth:** Consumers can request the exact semantic grain directly instead of parsing a convention-heavy string.
- **Goal 2 — Separation of concerns:** The consolidation layer exposes dimensions, not UI-specific key construction.
- **Goal 3 — Debuggability:** A malformed tuple such as `standard`, `12`, `qb2` on CBS is easy to identify.
- **Goal 6 — Auditability:** The league assumptions behind a row are explicit.

It puts at risk:

- **Goal 1:** If the JavaScript `sourceComboKey()` logic and the Python bake independently encode which sources support QB variants, there are two definitions of tuple identity.
- **Goal 5 — Fail-closed:** A future source supporting QB variants could be added to one implementation but not the other.
- **Goal 4 — No disruption:** UI code still speaks combo keys while consolidation speaks decomposed dimensions.

Recommendation: retain the decomposed columns, but establish one shared, registry-derived contract for valid tuples. The bake, validation, and presentation adapter should all derive from that contract. At minimum, add discrimination tests covering every registered source and every valid/invalid tuple.

The row’s logical primary key should be explicitly defined and enforced:

```text
(player, source, scoring, teams, qb_variant, view)
```

The bake must reject duplicate keys. A row-count check will not detect one missing row offset by one duplicate row.

An opaque `combo` field avoids decomposition drift, but it embeds a presentation convention into the data layer and is harder to validate or query. It is acceptable as a redundant, generated diagnostic field, but it should not be a second independently populated identity field.

There is also an unresolved question for VORP views: the scope must specify whether all VORP rows genuinely have `scoring`, `teams`, and `qb_variant` dimensions. If their grain differs from combo rows, forcing both into the same key shape may manufacture false dimensionality. The schema should document the exact grain of each view.

## b. `indexed` versus `reindexed`

The names are too similar for a flat schema. I recommend renaming them to encode their semantic family, for example:

- `combo_reindexed`
- `vorp_indexed`
- `vorp`
- `vorp_adjusted`

Alternatively, use two dimensions:

```json
{
  "value_family": "combo",
  "view": "reindexed"
}
```

and:

```json
{
  "value_family": "vorp_translation",
  "view": "indexed"
}
```

The present proposal serves:

- **Goal 2:** It faithfully copies already-produced final values without adding calculation logic.
- **Goal 4:** Keeping existing names minimizes migration work.

It puts at risk:

- **Goal 3:** `indexed` and `reindexed` do not explain which calculation path produced a value.
- **Goal 6:** An auditor needs knowledge of the old nested detail structure to interpret a supposedly flat, self-explanatory row.
- **Goal 1:** Consumers can easily request the wrong “indexed” family while still receiving a plausible number.

If left as-is, nothing necessarily breaks syntactically. The failure mode is worse: requests can succeed with the wrong semantic value. Documentation alone is not a strong enough guard for that class of error.

## c. Array-of-objects versus array-of-arrays

Use array-of-objects for the committed fixture and minify or transform only the served copy if measured performance requires it.

This serves:

- **Goal 3:** Diffs identify the changed dimension and value directly.
- **Goal 6:** A row can be inspected without consulting a positional schema.
- **Goal 1:** Named fields reduce column-shift and decoder-version mistakes.
- **Goal 5:** Schema validators can reject missing, extra, or mistyped fields clearly.

Arrays-of-arrays save transfer bytes, but introduce positional coupling between the producer and every consumer. A schema-order mismatch can silently reinterpret `teams` as another field. Compression will also remove much of the repeated-key cost for network delivery.

Use deterministic sorting so committed diffs remain stable. Define the order, for example:

```text
source, scoring, teams, qb_variant, view, player
```

## d. Per-value auditability

A file-level `detail_sha256` is necessary but not sufficient for **Goal 6** as stated. It proves which complete detail artifact was used, but it does not tell an auditor where one row came from or which input lineage produced it.

The proposed metadata serves:

- **Goal 1:** It binds the projection to one exact detail file.
- **Goal 5:** It can block serving a projection derived from a different detail artifact.
- **Goal 4:** It avoids changing the existing detail schema.

It puts at risk:

- **Goal 6:** “Pick any number and follow the chain” still requires reconstructing the old path and searching a large file.
- **Goal 3:** A wrong value can be assigned to the wrong tuple while retaining the correct file SHA.
- **Goal 2:** If the remedy is to copy all rich provenance into every row, consolidation stops being dumb and flat.

The right compromise is lightweight lineage, not full provenance duplication:

- File/bake level:
  - immutable `bake_id`
  - `detail_sha256`
  - adjustment-input artifact hash where applicable
  - schema/registry version or hash
  - per-source content vintage
- Row level:
  - a deterministic `detail_locator`, such as the exact source/combo/view/player path, or enough fields to generate it without hidden source-specific logic
  - optionally a compact `lineage_id` referencing a file-level lineage dictionary

Do not repeat the same large hashes in 20,000 rows. A row locator plus immutable bake metadata is enough to keep consolidation flat while making the audit path explicit.

A further issue: rounding consolidation values to one decimal conflicts with strict equality and with “just the numbers.” Consolidation should store the exact final numeric value from detail. Presentation should round for display. Otherwise consolidation introduces a transformation, reconciliation cannot use strict equality, and calculators may compute from rounded values. That puts **Goals 1, 2, 3, 5, and 6** at risk.

# 2. JSON-First vs Supabase

JSON-first is reasonable for the current static architecture. A database would not inherently create a stronger single source of truth; if both JSON and a Supabase table exist, it may create another synchronization boundary.

JSON-first serves:

- **Goal 1:** One immutable artifact can be the sole presentation source.
- **Goal 2:** The layer remains a simple projection rather than acquiring database-side logic.
- **Goal 4:** It fits GitHub Pages and minimizes migration disruption.
- **Goal 5:** A committed artifact can be validated in the same deploy transaction as the detail fixture.

It puts at risk:

- **Goal 6:** Per-value queries are less convenient than SQL.
- **Goal 1:** Calling detail the “system of record” while calling consolidation the sole source for presentation needs precise wording. Detail is authoritative for derivation; consolidation is authoritative for served final values.
- **Goal 5:** A hash verifies artifact identity, but not uniqueness, completeness, semantic validity, or correct row-to-path mapping.

The JSON is not an illegitimate second truth if its status is explicit:

```text
Detail: authoritative derivation record
Consolidation: authoritative presentation-value projection
```

The `detail_sha256` establishes derivation identity, but the deploy gate also needs:

- exact key-set equality, not merely equal counts;
- duplicate-key rejection;
- bidirectional reconciliation;
- finite-number/type validation;
- valid tuple validation;
- exact-value preservation, without consolidation-layer rounding;
- atomic publication of detail and consolidation.

Postgres constraints could enforce uniqueness and domains, and SQL would improve ad hoc auditing. But a database does not guarantee the static artifact matches the table. If Supabase were introduced now as a mirror, **Goal 1** would require a declared authority and mirror-parity checks. Otherwise there would be three potentially divergent representations: detail JSON, consolidation JSON, and the table.

Deferral costs include:

- later schema and backfill work;
- designing stable identifiers and upsert semantics later;
- reconciling historical bake/vintage representation;
- adding JSON/database parity validation when a server consumer appears.

Those costs are manageable at roughly 20,000 rows. I agree with JSON-first, provided the schema is designed now so that it could map cleanly to a table later and the JSON supports a small audit/query utility. Supabase should not be added solely because SQL is more convenient.

# 3. Migration Plan (Strangler-Fig)

The strangler sequence is directionally correct but underspecified.

It serves:

- **Goal 4:** Consumers can move independently and rollback remains possible.
- **Goal 2:** Presentation code gradually stops knowing the detail schema.
- **Goal 3:** Reconciliation offers a clear boundary between bake and UI failures.

It puts at risk:

- **Goal 1:** During migration, different code paths can serve values from different layers.
- **Goal 5:** Row reconciliation alone does not prove that all expected combinations exist.
- **Goal 6:** The plan does not record which layer supplied a displayed value.
- **Goal 4:** Migrating “read-by-read” inside one dashboard can leave a mixed consumer whose behavior is hard to reason about.

Temporary dual availability does not have to violate Goal 1, but temporary dual authority does. During migration, each feature or release must have exactly one selected provider. Avoid silent per-value fallback from consolidation to detail. A fallback would hide missing rows and undermine fail-closed behavior.

Use a provider-level switch:

```text
detail provider OR consolidation provider
```

not:

```text
try consolidation, then silently use detail
```

During a shadow period, the non-selected provider may be read only for comparison and telemetry; it must not supply the displayed value.

Before consumer migration, validate exact key-set equality:

```text
expected detail keys
  − consolidation keys = ∅

consolidation keys
  − expected detail keys = ∅
```

This is stronger than row counts and directly catches a dropped combo. `sourceComboExists` should eventually query an explicit consolidation manifest of available tuples, generated from the same emitted rows. It should not continue reading detail structure after migration. The validator should compare that manifest with the derivable detail combo registry and reject unexplained missing or extra tuples.

For transition visibility:

- Expose the selected data provider and `bake_id` in a diagnostic panel or application debug state.
- Log/assert that no production value lookup reaches the old detail provider when consolidation mode is selected.
- Add tests that remove a consolidation tuple and prove the consumer does not fall back.
- Test all chart features—including calculator and trade designer—even though they live inside the same app.
- Publish detail and consolidation atomically from the same validated build.

“One full rebuild cycle” is not a sufficient deletion criterion. It tests time, not coverage. Delete the old paths only after:

- at least two successful scheduled rebuilds with different or changed source content;
- exact key-set and value reconciliation;
- end-to-end tests across all supported scoring/team/QB combinations;
- explicit tests of absent values, zero values, and unsupported combos;
- production shadow comparison or spot checks;
- confirmation that no presentation import or deep-path access remains.

# 4. The Five Open Questions

## Q1: JSON only, or Supabase mirror too?

Recommendation: JSON only for phase 1.

This serves **Goals 1, 2, and 4** by keeping one presentation artifact, a dumb projection, and a low-disruption migration. It risks **Goal 6** only in query convenience, which can be addressed with deterministic row locators and a small audit command. A Supabase mirror should be introduced only with a concrete consumer and an explicit parity contract.

## Q2: Do native values belong in consolidation?

Recommendation: inventory every presentation read before approving the schema. If any chart surface, tooltip, curve widget, calculator, or designer displays or computes from native values, include `native` in consolidation and migrate that read.

This serves **Goals 1 and 2**: presentation must not retain a detail read for one special value family. It also improves **Goals 3 and 6**, because all user-visible numbers cross the same boundary.

If native values are genuinely audit-only, exclude them. The scope itself notes a suspicious use in `curve-widget.js`; that must be resolved before calling native values a non-goal. “Display-adjacent” is not enough evidence to exclude them.

## Q3: Should the monitor dashboard read consolidation?

Recommendation: yes, but as an end-to-end monitor—not as another presentation source or derivation authority.

It should spot-check or fully validate:

```text
served consolidation artifact
→ expected bake/detail hash
→ selected rows
→ detail locators
→ source vintages
```

This serves:

- **Goal 3:** Distinguishes build correctness from publication/caching failure.
- **Goal 5:** Detects a validated artifact that was not actually deployed or was deployed alongside the wrong detail file.
- **Goal 6:** Provides an operational audit trail.
- **Goal 1:** Confirms the artifact users receive is the intended one.

The monitor must validate the served URL, not merely the local build copy.

## Q4: Is the indexed/reindexed naming collision acceptable?

Recommendation: rename now, before consumers depend on v1. Use `combo_reindexed` and `vorp_indexed`, or introduce a `value_family` dimension.

This serves **Goals 3 and 6** and reduces risk to **Goal 1**. Keeping the names minimizes short-term disruption under **Goal 4**, but this is the cheapest moment to remove the ambiguity.

## Q5: Array-of-objects or array-of-arrays?

Recommendation: array-of-objects for the canonical committed artifact. Minify and gzip the served file. Only add a positional transport representation if measurements show a real load-time problem.

This best serves **Goals 1, 3, 5, and 6**. Arrays-of-arrays mainly optimize size while weakening reviewability and schema safety.

# 5. What the Scope Missed

## Missing versus zero versus unsupported

The scope must define three distinct states:

1. Source supports the tuple and prices the player at `0`.
2. Source supports the tuple but has no value for that player.
3. Source does not support the tuple.

Use absent player rows for “not priced,” explicit numeric `0` for a priced zero such as `espn_zeroed`, and an explicit tuple manifest for supported/unsupported combinations. Do not emit `null` value rows unless `null` has a single rigorously defined meaning.

This serves **Goals 1, 3, 5, and 6**. Without the distinction, presentation may silently substitute a fallback, interpret missing as zero, or hide a derivation failure.

`espn_zeroed` values should therefore appear as `value: 0`, while their reason remains in detail and is reachable through the row locator. Truthiness-based lookup code must be prohibited and tested.

## Coverage and exclusions

The scope does not define how K/DST or other excluded entity classes are handled. It should state:

- which entity types are eligible;
- whether exclusions are global or source-specific;
- how the expected key set is derived;
- how an auditor distinguishes a deliberate exclusion from an accidental omission.

This affects **Goals 1, 3, 5, and 6**.

## Rounding changes the data

The proposed one-decimal rounding should be removed. The consolidation layer should copy exact final detail values; the UI may round labels. A calculator or trade designer can produce different results when summing rounded values.

This is a direct risk to **Goals 1, 2, 3, 5, and 6**, and it contradicts the proposed strict-equality reconciliation.

## Reconciliation is only one-way

“For every row emitted, read detail and compare” proves that emitted rows are correct. It does not prove all required detail cells were emitted. A dynamic row-count check helps, but exact key-set equality is stronger and detects duplicates or substitution.

The bake needs:

- detail-derived expected-key set;
- consolidation actual-key set;
- exact set equality;
- uniqueness check;
- exact value equality for each key;
- discrimination tests for missing row, duplicate row, extra row, wrong tuple, wrong zero handling, and invalid QB variant.

This principally serves **Goals 1 and 5**, while improving **Goals 3 and 6**.

## Artifact synchronization and atomic deployment

A SHA comparison works only if the served detail and consolidation artifacts are from the same release. The scope lists multiple copies but does not define atomic copy/sync behavior or verify every served copy is identical.

The gate should hash all published copies and verify that:

- they are byte-identical or canonically equivalent;
- consolidation’s `detail_sha256` matches the exact served detail artifact;
- the HTML/JS deployment cannot update before its corresponding data artifacts.

This serves **Goals 1 and 5**.

Regarding the 30-minute health push: the scope must verify—not assume—whether it touches `comparison-sources-data.json` or any sync step that rewrites its served copy. If it does, either the health workflow must stop modifying that artifact or must run the complete paired bake and validation. “Must not regenerate consolidation” is safe only if it also cannot change the hashed detail artifact. This affects **Goals 4 and 5**.

## Pinned-value tests target the wrong boundary

Once presentation reads consolidation, pinned user-visible values should be asserted against consolidation. Detail pins should remain as build-layer tests, but they do not prove the user-facing projection contains the pinned value under the correct tuple.

Use both:

- detail pin: build/methodology correctness;
- consolidation pin: bake and presentation-contract correctness.

That serves **Goals 1, 3, and 5**.

## Consumer completeness

The scope names `comparison-dashboard.js` and `curve-widget.js`, but it must inventory all value reads in the chart app, including calculator and trade designer paths. Being features within one application does not guarantee they use the same provider.

Any remaining direct detail read by a presentation feature violates **Goals 1 and 2**.

## Cache and version coordination

Static Pages and browsers can cache JSON and JavaScript independently. A new JS bundle can request a schema the cached JSON does not support, or vice versa.

The scope should define:

- schema-version rejection;
- cache-busting or content-addressed artifact URLs;
- compatible rollout order;
- visible bake/schema identifiers;
- no silent fallback to detail on version mismatch.

This serves **Goals 1, 4, and 5**.

## Stable numeric serialization

The scope should define non-finite number rejection, treatment of negative zero, decimal serialization, and whether equality is numeric or byte-level. The build must never emit `NaN`, infinity, or stringified numbers.

This serves **Goals 1, 3, and 5**.

## `bake_id` semantics

The sample `bake_id` appears tied to one ESPN/PPR/12-team operation, while the artifact spans multiple sources, scoring systems, teams, and views. A file-wide bake identifier should identify the whole comparison build. Source-specific operation IDs belong in lineage metadata or a lineage dictionary.

This affects **Goals 3 and 6**.

## Per-value lineage remains inadequate

The scope claims that detail contains the audit trail, but it does not complete the link from a consolidation row to the relevant detail node and its upstream artifacts. A file hash answers “which file?” but not “where in that file and which source inputs?”

Add a deterministic row locator and bake-level hashes/versions. That is enough to support:

```text
presentation lookup key
→ consolidation row
→ exact detail path
→ detail lineage/fit metadata
→ source snapshot and adjustment inputs
```

This is required to satisfy **Goal 6** as written.

## Performance

A full reconciliation over roughly 20,500 rows is unlikely to be problematic, but the scope should measure it rather than promise it “adds seconds.” Build the expected rows and reconcile in one traversal or indexed traversal, avoiding repeated deep scans. Performance should never be used to weaken complete reconciliation.

This supports **Goals 4 and 5**.

# Top 5 Recommendations

1. **Preserve exact values; do not round in consolidation.** Rounding belongs in presentation and otherwise breaks strict reconciliation, calculator consistency, and the claim of one final value.

2. **Require bidirectional key-set reconciliation and uniqueness, not just row counts and emitted-row checks.** Validate the exact composite primary key, missing rows, extra rows, duplicates, invalid tuples, and zero handling.

3. **Add explicit audit links.** Give every row a deterministic detail locator or compact lineage reference, and bind the artifact to an immutable build ID, detail hash, input hashes, registry version, and source vintages.

4. **Make migration provider-atomic and observable.** Each feature must use either detail or consolidation, never per-value fallback. Shadow-compare both, expose the active provider and bake ID, and retire old paths based on coverage evidence rather than one rebuild cycle.

5. **Clarify the schema before v1 ships.** Keep decomposed dimensions, derive tuple validity from one shared registry, distinguish `combo_reindexed` from `vorp_indexed`, represent zero/missing/unsupported states explicitly, and use array-of-objects for the canonical fixture.
