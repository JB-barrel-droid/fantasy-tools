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
  | { ok: false; status: number; code: string; error: string; unread?: string[] };

// JEG-1288: request size bounds, checked before the link is read, cached or priced. The site lists 1,163 players and
// prices 741 at a time (Oct 29, 2026), so 2,000 overrides is every player with room to spare. The texts are what
// 2,000 overrides take written the longest way the site writes them (plain, "16777215:+99.9," is 15 characters
// each, so 29,999; packed z2: is 16,003) and the longest basis (all seven sources: 91 characters), with headroom.
// To change one, change it here and in docs/values-endpoint.md; nothing else depends on the numbers.
export const MAX_OVERRIDES = 2000;
export const MAX_OV_TEXT = 32768;
export const MAX_BASIS_TEXT = 256;

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

const tooLarge = (error: string): ReadResult => ({ ok: false, status: 413, code: "value_context_too_large", error });

/** JEG-1288: the size bounds, on the raw text alone (no link reader needed). null when within them. */
export function checkBounds(rawBasis: unknown, rawOv: unknown): ReadResult | null {
  const basis = text(rawBasis);
  const ov = text(rawOv);
  if (basis !== null && basis.length > MAX_BASIS_TEXT) {
    return tooLarge(`basis is ${basis.length} characters; the most is ${MAX_BASIS_TEXT}`);
  }
  if (ov !== null && ov.length > MAX_OV_TEXT) {
    return tooLarge(`ov is ${ov.length} characters; the most is ${MAX_OV_TEXT} (up to ${MAX_OVERRIDES} overrides)`);
  }
  return null;
}

/** True when the published link reader can read a context strictly (JEG-1288); an older one cannot. */
export function canReadStrictly(link: Any): boolean {
  return Boolean(link && typeof link.readValueContext === "function" && typeof link.parseOvStrict === "function");
}

/**
 * Read the caller's `basis` and `ov` (the link's own parameter text), strictly: a part is taken whole or refused,
 * naming what could not be read, never a silent fall back to our methodology or a part of what was asked.
 */
export function readValueContext(link: Any, rawBasis: unknown, rawOv: unknown): ReadResult {
  const bounds = checkBounds(rawBasis, rawOv);
  if (bounds) return bounds;
  const read = link.readValueContext({ basis: text(rawBasis), ov: text(rawOv) }, { strict: true });
  if (read.unread.length) {
    const what = read.unread.map((part: string) => `${part}: ${read.reasons?.[part] ?? "unreadable"}`);
    return {
      ok: false,
      status: 400,
      code: "value_context_unreadable",
      unread: read.unread,
      error: `could not read ${what.join("; ")}. basis is a source key (${link.BASIS_KEYS.join(", ")}) or ` +
        `blend:<source>.<percent>_..., as a share link writes it; ov is <player_key>:<value> or <player_key>:+<delta>, ` +
        `comma separated, or the packed z:/z2: form.`,
    };
  }
  const overrides: Record<string, Override> = read.overrides ?? {};
  const count = Object.keys(overrides).length;
  if (count > MAX_OVERRIDES) return tooLarge(`ov has ${count} overrides; the most is ${MAX_OVERRIDES}`);
  const basis = canonicalBasis(link, read.basis);
  return { ok: true, context: { basis, overrides, custom: Boolean(basis || count) } };
}

/**
 * JEG-1288: the requested basis sources the pipeline could not use here (held, hidden or not published at this
 * setting and week), or null when it used every one. An answer is never priced under part of a basis or under the
 * fallback: the caller is told what is unavailable and what is.
 */
export function basisShortfall(
  context: ValueContext,
  pipeline: Any,
  input: Any,
): { requested: string[]; unavailable: string[]; available: string[] } | null {
  if (!context.basis) return null;
  const requested = [...context.basis.sources];
  const members: string[] = pipeline.basis?.applied ? [...(pipeline.basis.members ?? [])] : [];
  const unavailable = requested.filter((key) => !members.includes(key));
  if (!unavailable.length) return null;
  // The pipeline's own sources, less those it hides (pipeline input.hidden): what a basis could follow here.
  const hidden = new Set<string>(input?.hidden ?? []);
  const available = (pipeline.included ?? []).filter((key: string) => !hidden.has(key));
  return { requested, unavailable, available };
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

/**
 * include=series after overrides: an overridden player's `ddf_value` series is the value the caller set,
 * as the site's row shows it (curve-widget.js OVERRIDE_VERSIONS is DDF Value only). The charts-only and
 * projections-only versions and every source series stay the engine's. Edits `series` in place.
 */
export function overrideSeries(
  series: Record<string, Record<string, number>>,
  own: { values: Record<string, RowValue>; applied: string[] },
): Record<string, Record<string, number>> {
  for (const pk of own.applied) {
    const value = own.values[pk]?.value;
    if (series[pk] && typeof value === "number" && Number.isFinite(value)) series[pk].ddf_value = value;
  }
  return series;
}
