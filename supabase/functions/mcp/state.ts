// JEG-1027: DDF state in and out of the MCP tools (spec: docs/design/llm-site-state.md).
// The codec itself is app/v2/ddf-state.js, loaded from the published site at cold start (index.ts),
// so the page and the tools read and write one format. Pure functions, no Deno APIs.

// deno-lint-ignore no-explicit-any
export type State = Record<string, any>;

export interface Codec {
  normalize(input: unknown): { state: State | null; warnings: string[] };
  encodeQuery(state: State): string;
  decodeBlock(text: string): { state: State | null; warnings: string[] };
  encodeBlock(state: State, opts?: { url?: string }): string;
}

export interface Deps {
  codec: Codec | null;
  siteOrigin: string;
}

export const ROUTES: Record<string, string> = {
  compare: "#compare-trade",
  targets: "#trade-targets",
  finder: "#find-trade",
  risers: "#risers-fallers",
};

// JEG-1031: get-values prices the whole league, so a state's settings beyond scoring, teams and superflex
// (roster shape, shares, bso, inj, conf, weeks) go to it as `league`. SUPERFLEX stays a top-level
// input so an explicit tool argument still wins over the pasted state.
export function leagueExtras(league: State | null | undefined): State | null {
  if (!league) return null;
  const out: State = {};
  for (const key of ["shares", "bso", "inj", "conf", "weeks"]) if (league[key] !== undefined) out[key] = league[key];
  const roster: State = {};
  for (const [k, v] of Object.entries(league.roster ?? {})) if (k !== "SUPERFLEX" && v !== undefined) roster[k] = v;
  if (Object.keys(roster).length) out.roster = roster;
  return Object.keys(out).length ? out : null;
}

export interface Prepared {
  args: Record<string, unknown>;
  state: State | null;
  warnings: string[];
}

// Merge a pasted state (block, bare JSON or site link) into the tool arguments. Explicit arguments win.
export function prepare(args: Record<string, unknown>, deps?: Deps): Prepared {
  const warnings: string[] = [];
  let state: State | null = null;
  if (typeof args.state === "string" && args.state.trim()) {
    if (!deps?.codec) {
      warnings.push("The shared state reader is unavailable right now, so the pasted state was not read; using the other settings.");
    } else {
      const r = deps.codec.decodeBlock(args.state);
      state = r.state;
      // The codec's "no DDF state found" line repeats the sentence added below.
      warnings.push(...r.warnings.filter((w) => !/no ddf state found/i.test(w)));
      if (!state) warnings.push("No usable DDF state was found in the pasted text; using the other settings.");
    }
  }
  const merged: Record<string, unknown> = { ...args };
  delete merged.state;
  const league = state?.league;
  if (league) {
    if (merged.scoring === undefined) merged.scoring = league.scoring;
    if (merged.teams === undefined && league.teams) merged.teams = league.teams;
    if (merged.superflex === undefined && league.roster && league.roster.SUPERFLEX !== undefined) {
      merged.superflex = Number(league.roster.SUPERFLEX) > 0;
    }
    const extras = leagueExtras(league);
    if (extras) merged.league = extras;
  }
  return { args: merged, state, warnings };
}

export interface Finish {
  prepared: Prepared;
  deps?: Deps;
  settings: { scoring: string; teams: number; superflex: number };
  view: string;
  work?: State;
  bare?: boolean;   // a plain site link with no state (explain)
  block?: boolean;  // append the pasteable block (make_state)
}

// Add the site link, the state to continue on the site, and any notes to a tool result.
export function finish<R extends { content: Array<{ type: "text"; text: string }>; structuredContent?: Record<string, unknown> }>(
  result: R,
  f: Finish,
): R {
  const { prepared, deps, settings: s } = f;
  const notes = [...new Set(prepared.warnings)];

  const league: State = { ...(prepared.state?.league ?? {}), scoring: s.scoring, teams: s.teams };
  // The link must describe the league actually priced. An explicit superflex argument
  // can override SF1 or SF0 in a pasted state, so replace that slot in either case.
  if (s.superflex || league.roster?.SUPERFLEX !== undefined) {
    league.roster = { ...(league.roster ?? {}), SUPERFLEX: s.superflex ? 1 : 0 };
  }
  const state: State = { v: 1, league, work: { ...(prepared.state?.work ?? {}), ...(f.work ?? {}), view: f.view } };

  const route = ROUTES[f.view] ?? ROUTES.targets;
  let url = `${deps?.siteOrigin ?? ""}/${route}`;
  let outState: State | null = state;
  if (f.bare) {
    url = `${deps?.siteOrigin ?? ""}/`;
    outState = null;
  } else if (deps?.codec) {
    const norm = deps.codec.normalize(state);
    outState = norm.state;
    if (outState) url = `${deps.siteOrigin}/${route}?${deps.codec.encodeQuery(outState)}`;
  }

  const block = f.block && deps?.codec && outState ? deps.codec.encodeBlock(outState, { url }) : "";
  const text = result.content[0].text +
    (notes.length ? `\n\n${notes.join("\n")}` : "") +
    (block ? `\n\n${block}` : deps ? `\n\nOpen this on the site: ${url}` : "");
  return {
    ...result,
    content: [{ type: "text", text }],
    structuredContent: { ...(result.structuredContent ?? {}), site_url: deps ? url : null, state: outState, notes },
  };
}
