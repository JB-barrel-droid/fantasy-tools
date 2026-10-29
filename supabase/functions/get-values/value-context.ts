// JEG-1225 (slice 4b of the JEG-1224 plan): the caller's value basis and player overrides, as a share link
// carries them (basis=, ov=). Pure functions, no Deno APIs: the deployed handler (index.ts) and the parity
// runner (tests/_edge_pipeline_runner.cjs) both import this file.
//
// No new value math. The link text is read by the site's own app/v2/ddf-value-link.js (passed in as `link`,
// loaded from the published site like value-model.js). The basis goes to ValueModel.runValuePipeline as
// basisConfig, in the form the site's engine sends it (curve-widget.js canonicalBasis); the overrides are applied
// to each row's DDF Value with ValueModel.applyDdfOverride, as the site does (curve-widget.js setCompositeFields).
// An override replaces DDF Value only: the tier, the trade charts' values and the projections version are the
// pipeline's, as on the site.

// deno-lint-ignore no-explicit-any
type Any = any;

export type Basis =
  | { mode: "single"; source: string; sources: string[]; weights: Record<string, number> }
  | { mode: "blend"; sources: string[]; weights: Record<string, number> };
export type Override = number | { type: "adjustment"; delta: number };

/** What the caller asked for, read and put in the engine's form. basis null = our methodology. */
export interface ValueContext {
  basis: Basis | null;
  overrides: Record<string, Override>;
  /** True when the caller sent a basis or overrides (the answer is a fresh engine run). */
  custom: boolean;
}

export type ReadResult =
  | { ok: true; context: ValueContext }
  | { ok: false; error: string; unread: string[] };

// curve-widget.js COMPOSITE_INPUT_KEYS: our methodology is these four charts at equal weight.
const OUR_METHODOLOGY = ["fantasycalc", "usatoday", "fantasypros", "cbs"];

const text = (v: unknown): string | null => (v === undefined || v === null || v === "" ? null : String(v));

/**
 * The engine's form of a basis the link reader returned, as curve-widget.js canonicalBasis makes it from the
 * record overrides.js sends (setBasisState -> basisRecord -> setBasis): sources in the engine's order, a single
 * source at weight 100, and an equal-weight blend of our methodology's four charts stored as our methodology.
 */
export function canonicalBasis(link: Any, parsed: Any): Basis | null {
  if (!parsed) return null;
  const order: string[] = link.BASIS_KEYS;
  if (parsed.mode === "single") {
    return { mode: "single", source: parsed.source, sources: [parsed.source], weights: { [parsed.source]: 100 } };
  }
  const sources = order.filter((key) => parsed.weights[key] !== undefined);
  const weights = Object.fromEntries(sources.map((key) => [key, parsed.weights[key] as number]));
  const equalDefault = sources.length === OUR_METHODOLOGY.length &&
    OUR_METHODOLOGY.every((key) => sources.includes(key)) && new Set(sources.map((key) => weights[key])).size === 1;
  return equalDefault ? null : { mode: "blend", sources, weights };
}

/**
 * Read the caller's `basis` and `ov` (the link's own parameter text). A part that is sent but cannot be read is an
 * error naming it, never a silent fall back to our methodology.
 */
export function readValueContext(link: Any, rawBasis: unknown, rawOv: unknown): ReadResult {
  const read = link.readValueContext({ basis: text(rawBasis), ov: text(rawOv) });
  if (read.unread.length) {
    const what = read.unread.map((part: string) => (part === "basis" ? `basis "${read.basisText}"` : `ov "${read.ovText}"`));
    return {
      ok: false,
      unread: read.unread,
      error: `could not read ${what.join(" or ")}. basis is a source key (${link.BASIS_KEYS.join(", ")}) or ` +
        `blend:<source>.<percent>_..., as a share link writes it; ov is <player_key>:<value> or <player_key>:+<delta>, ` +
        `comma separated, or the packed z:/z2: form.`,
    };
  }
  const basis = canonicalBasis(link, read.basis);
  const overrides: Record<string, Override> = read.overrides ?? {};
  return { ok: true, context: { basis, overrides, custom: Boolean(basis || Object.keys(overrides).length) } };
}

/** A cache key part that is the same for the same context however it was written. */
export function contextKey(context: ValueContext): string {
  if (!context.custom) return "";
  const ov = Object.keys(context.overrides).sort((a, b) => Number(a) - Number(b))
    .map((key) => `${key}:${JSON.stringify(context.overrides[key])}`).join(",");
  return `|basis=${JSON.stringify(context.basis)}|ov=${ov}`;
}

/** The pipeline input's basisConfig (a copy, as curve-widget.js runPipeline passes it). */
export function basisConfigOf(context: ValueContext): Basis | null {
  const b = context.basis;
  return b ? JSON.parse(JSON.stringify(b)) : null;
}

/** One row's DDF Value after the caller's override, and what the pipeline said before it. */
export interface RowValue {
  value: number | null;
  /** The pipeline's own DDF Value when an override applies; absent otherwise. */
  pipeline_value?: number | null;
  /** The override as applied, when one applies. */
  override?: Override;
}

/**
 * Each pipeline row's DDF Value (the blended version) with the caller's overrides applied by the site's own
 * ValueModel.applyDdfOverride. Overrides for players with no pipeline row are not added: they are listed in
 * `not_priced` (the response names them).
 */
export function applyOverrides(
  ValueModel: Any,
  pipeline: Any,
  context: ValueContext,
): { values: Record<string, RowValue>; applied: string[]; not_priced: string[] } {
  const values: Record<string, RowValue> = {};
  const rows = pipeline.rows || {};
  const applied: string[] = [];
  for (const [pk, row] of Object.entries(rows)) {
    const blended = (row as Any).ddfByVersion?.blended;
    const own = blended && Number.isFinite(blended.value) ? blended.value : null;
    const override = Object.prototype.hasOwnProperty.call(context.overrides, pk) ? context.overrides[pk] : null;
    if (override === null) {
      values[pk] = { value: own };
      continue;
    }
    const entry = ValueModel.applyDdfOverride({ value: own }, override);
    if (!entry.overridden) {
      values[pk] = { value: own };
      continue;
    }
    values[pk] = { value: entry.value, pipeline_value: own, override };
    applied.push(pk);
  }
  const not_priced = Object.keys(context.overrides).filter((pk) => !(pk in rows))
    .sort((a, b) => Number(a) - Number(b));
  return { values, applied, not_priced };
}
