// JEG-1179: the week the MCP tools price. Pure functions, no Deno APIs (node tests import this file).
//
// get-values decides the week: the site's default (ValueModel.weekState, the same code the page runs) or
// the `week` a tool is asked for. These helpers read the asked week (a `week` argument, or `wk=` in a
// pasted site link), carry it to get-values, and put the answer's week, sources_included and
// missing_sources on every tool result.

// deno-lint-ignore no-explicit-any
type Any = any;

/** The week fields get-values returns with every answer. */
export interface WeekFields {
  week?: number | null;
  default_week?: number | null;
  weeks?: number[];
  sources_included?: string[];
  missing_sources?: string[];
}

export const weekProp = {
  week: {
    type: "integer",
    minimum: 1,
    maximum: 22,
    description:
      "Optional: the NFL week to price. Leave it out for the site's default week. During a week transition two weeks " +
      "can be asked for (the newest, and the week before); a week with no published sources is an error that lists the weeks there are.",
  },
};

/** `wk=N` in a pasted site link or state text (the site's week selector), or null. */
export function linkWeek(text: unknown): number | null {
  const m = String(text ?? "").match(/[?&#]wk=(\d{1,2})(?![\d])/);
  return m ? Number(m[1]) : null;
}

/**
 * The week a tool call asks for: the `week` argument, else `wk=` in a pasted link, else null (the
 * default week). NaN when the `week` argument is not a whole number from 1 to 22.
 */
export function askedWeek(args: Record<string, unknown>): number | null {
  const raw = args.week;
  if (raw !== undefined && raw !== null && raw !== "") {
    const n = typeof raw === "number" ? raw : /^\s*\d+\s*$/.test(String(raw)) ? Number(raw) : NaN;
    return Number.isInteger(n) && n >= 1 && n <= 22 ? n : NaN;
  }
  return linkWeek(args.state);
}

/** One line for a tool's text: the week priced and what it leaves out. */
export function weekLine(data: WeekFields): string | null {
  if (!Number.isInteger(data.week)) return null;
  const parts = [`Week: ${data.week}${data.week === data.default_week ? " (the site's default)" : `, asked for (the site's default is ${data.default_week})`}`];
  const other = (data.weeks ?? []).filter((w) => w !== data.week);
  if (other.length) parts.push(`week ${other.join(", ")} can also be asked for`);
  if (data.missing_sources?.length) {
    parts.push(`not yet published for week ${data.week}, left out: ${data.missing_sources.join(", ")}`);
  }
  return `${parts.join("; ")}.`;
}

interface Result {
  content: Array<{ type: "text"; text: string }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
}

/**
 * Put the priced week on a tool result: `week`, `default_week`, `weeks`, `sources_included` and
 * `missing_sources` in structuredContent, a week line after the settings line, and `wk=` on the site
 * link when a week was asked for (so the site opens on the same week).
 */
export function withWeek<R extends Result>(result: R, data: WeekFields | null, asked: number | null): R {
  if (!data || result.isError) return result;
  const fields = {
    week: data.week ?? null,
    default_week: data.default_week ?? null,
    weeks: data.weeks ?? [],
    sources_included: data.sources_included ?? [],
    missing_sources: data.missing_sources ?? [],
  };
  let text = result.content[0]?.text ?? "";
  const line = weekLine(data);
  if (line) text = /^Settings: .*$/m.test(text) ? text.replace(/^Settings: .*$/m, (s) => `${s}\n${line}`) : `${line}\n${text}`;
  const structured: Record<string, Any> = { ...(result.structuredContent ?? {}), ...fields };
  const url = structured.site_url;
  if (asked !== null && typeof url === "string" && url && !/[?&]wk=/.test(url)) {
    const withWk = `${url}${url.includes("?") ? "&" : "?"}wk=${asked}`;
    text = text.split(url).join(withWk);
    structured.site_url = withWk;
  }
  return { ...result, content: [{ type: "text", text }, ...result.content.slice(1)], structuredContent: structured };
}
