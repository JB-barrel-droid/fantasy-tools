// JEG-1343 (JEG-1225 slice 4c): a pasted site link's own value context in the MCP tools. Pure functions, no
// Deno APIs (node tests import this file).
//
// A site share link can carry the sender's value basis and player overrides: `basis=`, `ov=` and the
// `valuecontext=1` marker (app/v2/ddf-value-link.js, written by overrides.js shareLink). The tools read them
// from the pasted text, send the link's own text to get-values (which reads it strictly and prices under it,
// JEG-1225 / JEG-1288), name the basis and overrides in the reply, and write the same three parameters into
// the link back. When get-values refuses the context, the tool gives no numbers: an answer under our
// methodology in place of the link's values would be the silent fallback the plan rules out.

// deno-lint-ignore no-explicit-any
type Any = any;

/** The link's own value-context text, as sent to get-values (`basis`, `ov`). */
export interface ValueContextText {
  basis: string | null;
  ov: string | null;
}

/** get-values' value_context on a priced answer. */
export interface PricedValueContext {
  basis?: unknown;
  basis_applied?: boolean;
  basis_members?: string[];
  overrides?: Record<string, unknown>;
  overrides_applied?: number;
  overrides_not_priced?: number[];
}

/**
 * `basis=`, `ov=` and `valuecontext=1` in a pasted site link or state text (the first query that carries any
 * of them), or null. A link with only `valuecontext=1` asks for our methodology with no overrides; it is
 * still a value context, so the link back keeps the marker.
 */
export function linkValueContext(text: unknown): (ValueContextText & { complete: boolean }) | null {
  // A link pasted from a page or a mail can come with its ampersands escaped.
  const src = String(text ?? "").replace(/&amp;/gi, "&");
  let first: (ValueContextText & { complete: boolean }) | null = null;
  for (const m of src.matchAll(/[?#&]((?:[A-Za-z0-9_]+=[^\s&#]*&?)+)/g)) {
    // Punctuation the link was pasted with: a markdown link's ")", a sentence's "." and the like. No basis or
    // ov value ends in one (sources, whole numbers, base64url).
    const query = m[1].replace(/[).,;:!?\]>'"]+$/, "");
    let params: URLSearchParams;
    try {
      params = new URLSearchParams(query);
    } catch {
      continue;
    }
    const basis = params.get("basis");
    // An adjustment typed into a link unencoded (ov=202:+5) reads back as "202: 5"; put its sign back.
    const ov = params.get("ov")?.replace(/:\s/g, ":+") ?? null;
    const complete = params.get("valuecontext") === "1";
    if (!basis && !ov && !complete) continue;
    const found = { basis: basis || null, ov: ov || null, complete };
    // The site writes valuecontext=1 with every value context; prefer that query over another URL's basis= or ov=.
    if (complete) return found;
    first ??= found;
  }
  return first;
}

/** The value context a tool call asks for (from the pasted `state`), or null for our methodology. */
export function askedValueContext(args: Record<string, unknown>): (ValueContextText & { complete: boolean }) | null {
  return linkValueContext(args.state);
}

/** get-values' refusal codes for a value context, and what the reply says about each. */
const REFUSALS: Record<string, string> = {
  basis_unavailable: "a source in the link's value basis isn't available at this setting and week",
  value_context_unreadable: "part of the link's basis or overrides can't be read",
  value_context_too_large: "the link's basis or overrides are larger than the chat accepts",
  value_context_unavailable: "the site's link reader isn't published yet",
};

/**
 * The reply for a get-values refusal of the link's value context, or null when the answer is not one.
 * It names why and gives no numbers.
 */
export function valueContextRefusal(status: number, body: Any): string | null {
  const code = body && typeof body === "object" ? String(body.code ?? "") : "";
  const why = REFUSALS[code];
  if (!why) return null;
  const detail = typeof body.error === "string" && body.error ? ` (${body.error})` : "";
  return `This link's own values can't be priced here: ${why}${detail}. No values are given, rather than ` +
    `values on Data Driven Football's default basis in their place. Open the link on the site to see them, or ` +
    `ask again without the link's basis and overrides for the default values.`;
}

/**
 * get-values answered without `value_context`: a build from before JEG-1225, which ignores `basis` and `ov` and
 * prices our methodology. Its numbers are not the link's, so the tool gives none.
 */
export const VALUE_CONTEXT_NOT_SUPPORTED = "This link's own values can't be priced here yet: the values service " +
  "doesn't read a link's basis and overrides in this version. No values are given, rather than values on Data " +
  "Driven Football's default basis in their place. Open the link on the site to see them, or ask again without " +
  "the link's basis and overrides for the default values.";

/** The link's basis text in words: "fantasycalc", or "a blend of espn 60%, razzball 40%". */
export function basisWords(basis: string): string {
  const blend = /^blend:(.+)$/i.exec(basis);
  if (!blend) return basis;
  return `a blend of ${blend[1].split("_").map((part) => {
    const [source, weight] = part.split(".");
    return weight ? `${source} ${weight}%` : source;
  }).join(", ")}`;
}

/**
 * One line for a tool's text: the basis and overrides priced. The basis is named from the link's own text;
 * get-values' `value_context.basis` is the engine's basis object, not words.
 */
export function valueContextLine(priced: PricedValueContext | null | undefined, asked?: ValueContextText | null): string | null {
  if (!priced) return null;
  const basis = asked?.basis ? `the link's basis ${basisWords(asked.basis)}` : "Data Driven Football's own methodology";
  const applied = priced.overrides_applied ?? 0;
  const parts = [`Values: priced under ${basis}`];
  if (applied) parts.push(`with ${applied} player override${applied === 1 ? "" : "s"} from the link`);
  const unpriced = priced.overrides_not_priced?.length ?? 0;
  if (unpriced) parts.push(`${unpriced} override${unpriced === 1 ? "" : "s"} for players with no value this week left out`);
  return `${parts.join(", ")}.`;
}

/** The link's value context as site link parameters (overrides.js shareLink's form). */
export function valueContextQuery(context: ValueContextText): string {
  return ["valuecontext=1", context.basis ? `basis=${encodeURIComponent(context.basis)}` : "",
    context.ov ? `ov=${encodeURIComponent(context.ov)}` : ""].filter(Boolean).join("&");
}

/** Players named in `overrides_not_priced` on a tool answer; the count carries the rest. */
const NOT_PRICED_SHOWN = 25;

/**
 * get-values' value_context as a tool answer carries it: the counts, with the basis as the link's text. The
 * overrides map stays out and the unpriced list is cut (a link can carry 2,000 overrides, which would count
 * against a trade reply's size budget and say "too large" for the wrong reason).
 */
function summaryOf(priced: PricedValueContext, asked: ValueContextText): Record<string, Any> {
  const { overrides: _overrides, basis: _basis, ...rest } = priced as Record<string, Any>;
  const notPriced: unknown[] = Array.isArray(rest.overrides_not_priced) ? rest.overrides_not_priced : [];
  return { basis: asked.basis, ...rest, overrides_not_priced: notPriced.slice(0, NOT_PRICED_SHOWN),
    overrides_not_priced_count: notPriced.length };
}

/**
 * Whether the site applies a link's basis and overrides on the view a link opens: Find a trade, a league link, and
 * a Compare link with player keys only (v2.js readTradeHash, league.js). Trade targets, Risers & fallers, values
 * auditing and a Compare link carrying more of the codec's state go through DDFAssist, which doesn't (JEG-1224 S1, S2).
 */
export function siteAppliesValueContext(url: string): boolean {
  if (!url.includes("#")) return false;
  const [base, query = ""] = url.slice(url.indexOf("#")).split("?");
  if (base === "#find-trade" || base === "#find-league") return true;
  if (base !== "#compare-trade") return false;
  const params = new URLSearchParams(query);
  if (params.has("mine") || params.has("theirs") || params.has("target")) return false;
  return !/(^|,)n:/i.test(`${params.get("give") || ""},${params.get("get") || ""}`);
}

interface Result {
  content: Array<{ type: "text"; text: string }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
}

/**
 * Put the priced value context on a tool result: `value_context` in structuredContent, a values line after the
 * settings line, and the link's own `valuecontext=1`, `basis=` and `ov=` on the site link and in a pasteable
 * state block's link, so the site opens on the same values. A link with only `valuecontext=1` (our methodology,
 * no overrides) keeps the marker even when get-values says nothing about it: any build prices that.
 */
export function withValueContext<R extends Result>(
  result: R,
  priced: PricedValueContext | null | undefined,
  asked: ValueContextText | null,
): R {
  if (!asked || result.isError) return result;
  let text = result.content[0]?.text ?? "";
  let line = valueContextLine(priced, asked);
  const structured: Record<string, Any> = { ...(result.structuredContent ?? {}) };
  if (priced) structured.value_context = summaryOf(priced, asked);
  const url = structured.site_url;
  if (typeof url === "string" && url && !/[?&]valuecontext=/.test(url)) {
    const withContext = `${url}${url.includes("?") ? "&" : "?"}${valueContextQuery(asked)}`;
    text = text.split(url).join(withContext);
    structured.site_url = withContext;
    if (line && (asked.basis || asked.ov) && !siteAppliesValueContext(withContext)) {
      line += " The site doesn't apply a link's own values on this view yet, so the link opens on the default values.";
      structured.site_applies_value_context = false;
    }
  }
  if (line) text = /^Settings: .*$/m.test(text) ? text.replace(/^Settings: .*$/m, (s) => `${s}\n${line}`) : `${line}\n${text}`;
  return { ...result, content: [{ type: "text", text }, ...result.content.slice(1)], structuredContent: structured };
}
