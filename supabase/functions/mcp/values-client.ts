// JEG-1343: the MCP function's get-values request and how it reads the answer. Pure (the fetch is passed in), so
// node checks can run it against the get-values handler itself (tests/node/mcp_value_context_check.mjs).

import { ToolInputError } from "./tools.ts";
import { type ValueContextText, valueContextRefusal } from "./value-context.ts";

/** A get-values answer, or the error a tool shows: a week or value-context refusal is the tool's own message. */
export async function readValuesResponse(res: Response): Promise<unknown> {
  if (res.ok) return await res.json();
  if ([400, 413, 422, 503].includes(res.status)) {
    const body = await res.json().catch(() => null) as { code?: string; error?: string } | null;
    if (res.status === 400 && body?.code === "week_unavailable" && body.error) throw new ToolInputError(body.error);
    // JEG-1343: get-values refused the pasted link's basis or overrides; the tool says why and gives no numbers.
    const refusal = valueContextRefusal(res.status, body);
    if (refusal) throw new ToolInputError(refusal);
  }
  throw new Error(`get-values ${res.status}`);
}

/**
 * One get-values request. Without a value context it is the plain GET it has always been; with one it is a POST,
 * because an `ov` can run to 32 KB, too long for a query string.
 */
export function requestValuesWith(
  fetchFn: (input: string | URL, init?: RequestInit) => Promise<Response>,
  valuesUrl: string,
  scoring: string, teams: number, superflex: number, league: Record<string, unknown> | undefined,
  week: number | null | undefined, include: string | null, context: ValueContextText | null | undefined,
): Promise<Response> {
  if (context) {
    const body: Record<string, unknown> = { scoring, teams, superflex };
    if (league) body.league = league;
    if (week) body.week = week;
    if (include) body.include = include;
    if (context.basis) body.basis = context.basis;
    if (context.ov) body.ov = context.ov;
    return fetchFn(valuesUrl, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  const url = new URL(valuesUrl);
  url.searchParams.set("scoring", scoring);
  url.searchParams.set("teams", String(teams));
  url.searchParams.set("superflex", String(superflex));
  if (league) url.searchParams.set("league", JSON.stringify(league));
  if (week) url.searchParams.set("week", String(week));
  if (include) url.searchParams.set("include", include);
  return fetchFn(url, { headers: { Accept: "application/json" } });
}
