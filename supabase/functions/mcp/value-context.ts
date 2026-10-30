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
  basis?: string | null;
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
  const src = String(text ?? "");
  for (const m of src.matchAll(/[?#&]((?:[A-Za-z0-9_]+=[^\s&#]*&?)+)/g)) {
    let params: URLSearchParams;
    try {
      params = new URLSearchParams(m[1]);
    } catch {
      continue;
    }
    const basis = params.get("basis");
    // An adjustment typed into a link unencoded (ov=202:+5) reads back as "202: 5"; put its sign back.
    const ov = params.get("ov")?.replace(/:\s/g, ":+") ?? null;
    const complete = params.get("valuecontext") === "1";
    if (basis || ov || complete) return { basis: basis || null, ov: ov || null, complete };
  }
  return null;
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

/** One line for a tool's text: the basis and overrides priced. */
export function valueContextLine(priced: PricedValueContext | null | undefined): string | null {
  if (!priced) return null;
  const basis = priced.basis ? `the link's basis ${priced.basis}` : "Data Driven Football's own methodology";
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
  const line = valueContextLine(priced);
  if (line) text = /^Settings: .*$/m.test(text) ? text.replace(/^Settings: .*$/m, (s) => `${s}\n${line}`) : `${line}\n${text}`;
  const structured: Record<string, Any> = { ...(result.structuredContent ?? {}) };
  if (priced) structured.value_context = priced;
  const url = structured.site_url;
  if (typeof url === "string" && url && !/[?&]valuecontext=/.test(url)) {
    const withContext = `${url}${url.includes("?") ? "&" : "?"}${valueContextQuery(asked)}`;
    text = text.split(url).join(withContext);
    structured.site_url = withContext;
  }
  return { ...result, content: [{ type: "text", text }, ...result.content.slice(1)], structuredContent: structured };
}
