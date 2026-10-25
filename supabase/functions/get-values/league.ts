// JEG-1031: map a normalized DDF league (docs/design/llm-site-state.md, app/v2/ddf-state.js) onto the
// two inputs the engine takes: the pipeline `setting` and the arguments of resolveLineupParameters.
// Pure functions, no Deno APIs, so node tests import this file directly.
//
// Every clamp below is the page's own (app/trade-value-chart/assets/curve-widget.js): setRosterSpot,
// setBenchShareOverride, setPositionWeights, setLineupSettings, and the order v2's applyLinkLeague
// applies them in. A bad value is clamped or ignored the way the page would, never thrown, so one
// odd field cannot turn a request into a 500.

// deno-lint-ignore no-explicit-any
export type League = Record<string, any>;

export const TEAM_OPTIONS = [8, 10, 12, 14];
export const SCORINGS = ["standard", "half_ppr", "ppr"];
const POSITIONS = ["QB", "RB", "WR", "TE"] as const;

// curve-widget.js DEFAULT_ROSTER / ROSTER_BOUNDS / rosterBounds (QB, RB, WR, TE and FLEX are 1 to 5).
const DEFAULT_ROSTER: Record<string, number> = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7 };
const ROSTER_BOUNDS: Record<string, [number, number]> = { BENCH: [0, 14], SUPERFLEX: [0, 1] };
const rosterBounds = (key: string): [number, number] => ROSTER_BOUNDS[key] ?? [1, 5];

const DEFAULT_BENCH_SHARE = 0.15;
const BENCH_SHARE_BOUNDS = [0.01, 0.30];
const POSITION_WEIGHT_FLOOR = 0.01;
const PROJECTION_CONFIDENCE_STEPS = [0.5, 1, 1.5];
const OBJECTIVES = ["season", "regular", "playoffs"];
const INJURY_HISTORY = ["recent", "all"];

export interface LineupDefaults {
  objective?: string;
  injury_history?: string;
  league_weeks?: { regular_season_end?: number; playoff_weeks?: number[] };
  projection_confidence?: number;
}

export interface LeagueInputs {
  scoring: string;
  teams: number;
  setting: {
    teams: number;
    slots: { QB: number; RB: number; WR: number; TE: number };
    flex: number;
    superflex: number;
    bench_per_team: number;
    bench_share: number;
    bench_share_override: number | null;
    position_shares: Record<string, number> | null;
  };
  // Arguments for ValueModel.resolveLineupParameters(config, args).
  lineupArgs: {
    objective: string;
    injury_history: string;
    league_weeks: { regular_season_end: number; playoff_weeks: number[] };
    projection_confidence: number;
    content_week: number | null;
  };
  // Settings that differ from the site defaults (for the response note and the cache key).
  custom: string[];
}

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const isWeek = (n: unknown): n is number => Number.isInteger(n) && (n as number) >= 1 && (n as number) <= 18;

// curve-widget.js liftToPositionFloor: lift shares below the floor, taking from the rest proportionally.
function liftToPositionFloor(weights: Record<string, number>, positions: readonly string[] = POSITIONS) {
  const w = { ...weights };
  const setTotal = positions.reduce((s, pos) => s + w[pos], 0);
  for (let pass = 0; pass < positions.length; pass += 1) {
    const low = positions.filter((pos) => w[pos] < POSITION_WEIGHT_FLOOR - 1e-12);
    if (!low.length) break;
    low.forEach((pos) => { w[pos] = POSITION_WEIGHT_FLOOR; });
    const fixed = positions.filter((pos) => w[pos] <= POSITION_WEIGHT_FLOOR + 1e-12);
    const rest = positions.filter((pos) => !fixed.includes(pos));
    if (!rest.length) break;
    const room = setTotal - fixed.length * POSITION_WEIGHT_FLOOR;
    const restTotal = rest.reduce((s, pos) => s + w[pos], 0);
    rest.forEach((pos) => { w[pos] = restTotal > 0 ? w[pos] * room / restTotal : room / rest.length; });
  }
  return w;
}

// curve-widget.js setPositionWeights with all four shares named (the only form a league carries).
function normalizeShares(shares: League): Record<string, number> | null {
  const asked: Record<string, number> = {};
  for (const pos of POSITIONS) {
    const n = Number(shares?.[pos]);
    if (!Number.isFinite(n)) return null;
    asked[pos] = n;
  }
  const hi = 1 - (POSITIONS.length - 1) * POSITION_WEIGHT_FLOOR;
  const set: Record<string, number> = {};
  POSITIONS.forEach((pos) => { set[pos] = clamp(asked[pos], POSITION_WEIGHT_FLOOR, hi); });
  const total = POSITIONS.reduce((s, pos) => s + set[pos], 0);
  let w: Record<string, number> = {};
  POSITIONS.forEach((pos) => { w[pos] = set[pos] / total; });
  w = liftToPositionFloor(w);
  const t2 = POSITIONS.reduce((s, pos) => s + w[pos], 0);
  POSITIONS.forEach((pos) => { w[pos] /= t2; });
  return w;
}

// `lineupConfig` is lineup-parameters.json (its `defaults` and `content_week`); null when it did not load.
export function mapLeague(
  league: League | null | undefined,
  lineupConfig: { defaults?: LineupDefaults; content_week?: number | null } | null,
): LeagueInputs {
  const l: League = league && typeof league === "object" ? league : {};
  const scoring = SCORINGS.includes(l.scoring) ? l.scoring : "ppr";
  const teams = TEAM_OPTIONS.includes(Number(l.teams)) ? Number(l.teams) : 12;
  const custom: string[] = [];

  // Roster: each given slot is rounded and clamped like setRosterSpot; unknown keys (K, DST) are ignored.
  const shape = { ...DEFAULT_ROSTER };
  let rosterChanged = false;
  if (l.roster && typeof l.roster === "object") {
    for (const key of Object.keys(DEFAULT_ROSTER)) {
      if (l.roster[key] === undefined) continue;
      const [lo, hi] = rosterBounds(key);
      const next = clamp(Math.round(Number(l.roster[key])), lo, hi);
      if (!Number.isFinite(next)) continue;
      if (next !== shape[key]) rosterChanged = true;
      shape[key] = next;
    }
  }
  if (rosterChanged) custom.push("roster");

  // Bench-share override: setBenchShareOverride's bounds.
  let bso: number | null = null;
  if (l.bso !== undefined && l.bso !== null && l.bso !== "") {
    const n = Number(l.bso);
    if (Number.isFinite(n)) bso = clamp(n, BENCH_SHARE_BOUNDS[0], BENCH_SHARE_BOUNDS[1]);
  }
  if (bso !== null) custom.push("bso");

  const shares = l.shares !== undefined ? normalizeShares(l.shares) : null;
  if (shares) custom.push("shares");

  // Season weeks, objective, injury history, confidence: setLineupSettings's checks. A value the page
  // would reject (it throws) falls back to the default here, so the answer is the default league's.
  const d = lineupConfig?.defaults ?? {};
  const defWeeks = {
    end: d.league_weeks?.regular_season_end ?? 14,
    playoffs: [...(d.league_weeks?.playoff_weeks ?? [15, 17])],
  };
  let objective = d.objective ?? "season";
  let injury = d.injury_history ?? "recent";
  let confidence = d.projection_confidence ?? 1;
  let end = defWeeks.end;
  let playoffs = defWeeks.playoffs;
  let contentWeek: number | null = null;

  const w = l.weeks && typeof l.weeks === "object" ? l.weeks : {};
  const wantEnd = w.regend !== undefined ? w.regend : end;
  const wantPlayoffs = Array.isArray(w.playoffs) ? w.playoffs.map(Number) : playoffs;
  if (
    isWeek(wantEnd) && wantPlayoffs.length === 2 && wantPlayoffs.every(isWeek) &&
    wantPlayoffs[0] <= wantPlayoffs[1] && wantPlayoffs[0] > wantEnd
  ) {
    if (wantEnd !== end || wantPlayoffs[0] !== playoffs[0] || wantPlayoffs[1] !== playoffs[1]) custom.push("weeks");
    end = wantEnd;
    playoffs = wantPlayoffs;
  }
  if (OBJECTIVES.includes(w.optimize)) {
    if (w.optimize !== objective) custom.push("optimize");
    objective = w.optimize;
  }
  // The page keeps the build's week as "no reader week" (v2.js applySeasonWeeks), and allows 1 to 17.
  const buildWeek = lineupConfig?.content_week ?? null;
  if (Number.isInteger(w.week) && w.week >= 1 && w.week <= 17 && w.week !== buildWeek) {
    contentWeek = w.week;
    custom.push("week");
  }
  if (INJURY_HISTORY.includes(l.inj)) {
    if (l.inj !== injury) custom.push("inj");
    injury = l.inj;
  }
  if (PROJECTION_CONFIDENCE_STEPS.includes(Number(l.conf))) {
    if (Number(l.conf) !== confidence) custom.push("conf");
    confidence = Number(l.conf);
  }

  return {
    scoring,
    teams,
    setting: {
      teams,
      slots: { QB: shape.QB, RB: shape.RB, WR: shape.WR, TE: shape.TE },
      flex: shape.FLEX,
      superflex: shape.SUPERFLEX > 0 ? Math.floor(shape.SUPERFLEX) : 0,
      bench_per_team: shape.BENCH,
      bench_share: bso ?? DEFAULT_BENCH_SHARE,
      bench_share_override: bso,
      position_shares: shares,
    },
    lineupArgs: {
      objective,
      injury_history: injury,
      league_weeks: { regular_season_end: end, playoff_weeks: [...playoffs] },
      projection_confidence: confidence,
      content_week: contentWeek,
    },
    custom,
  };
}

// Stable key for the answer cache: the mapped inputs, not the raw request, so equal leagues share an entry.
export function leagueKey(m: LeagueInputs): string {
  return JSON.stringify([m.scoring, m.setting, m.lineupArgs]);
}
