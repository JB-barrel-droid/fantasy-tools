// JEG-1038: trade viability scoring and ranking.
// Pure functions, no I/O, no Deno APIs. Runs under node in tests.
//
// For each trade offer, runs ALL viability checks and records each failure.
// Viable offers are ranked first (by DDF edge, lineup improvement, perceived
// fairness); non-viable offers follow (fewest failures first, then DDF edge).
// The package selector picks the best combination of viable offers across all
// opponents that never sends the same player twice.
//
// Value lenses (Jeremy, 2026-10-26 and 2026-10-28; JEG-1129): the user's side
// is judged on DDF Value ("ddf_value", the mean of the charts' weight-adjusted
// Indexed values); the other team's side on the Trade chart average, the mean of the
// trade charts' Indexed values (the site's "chart_avg" in the Indexed view).
// The chart keys must therefore carry Indexed values: get-values sends them as
// chart_indexed. Never ddf_value_charts, which equals DDF Value since JEG-1073.
//
// Every threshold is configurable through ViabilityConfig. Defaults listed
// in DEFAULT_CONFIG are conservative and await Jeremy's review.

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ViabilityRow {
  player_key: number;
  name: string;
  pos: string;
  values: Record<string, number | null>;
  ddfTier?: string;
  /** Injury/out status. "out" or "injured" means currently not playing. */
  status?: string;
  /** Weeks expected out, if injured/out. */
  weeksOut?: number;
}

/** League roster shape: how many starters at each slot. */
export interface RosterShape {
  QB: number;
  RB: number;
  WR: number;
  TE: number;
  FLEX: number;
  SUPERFLEX: number;
}

/** User-defined position guardrails. */
export interface Guardrail {
  /** Position to protect (e.g. "RB"). */
  pos: string;
  /** Minimum starter-tier players the user must keep at this position. */
  minStarters?: number;
  /** The user's starting group at this position must not get weaker on DDF value. */
  neverWeaker?: boolean;
}

/** All configurable thresholds with documented defaults. */
export interface ViabilityConfig {
  /** DDF value key for the user's side. Default "ddf_value". */
  ddfKey: string;
  /** Chart keys for the other team's Trade chart average view. Default all 4. */
  chartKeys: string[];
  /** Minimum DDF edge (receive - give) for the user. Default 0 (any gain). */
  minDdfEdge: number;
  /** Minimum Trade chart average net for the other team (receive - give). Default 0 (break even). */
  minMarketNet: number;
  /** Minimum DDF lineup improvement (starter value after - before). Default 0. */
  minUserLineupGain: number;
  /** Minimum Trade chart average lineup improvement for the other team. Default 0. */
  minTheirLineupGain: number;
  /** (Removed: per-position weaker threshold replaced by total lineup check.
   *  Kept as unused field for config compat; ignored by checks.) */
  positionWeakerThreshold: number;
  /** Minimum value for a player to count as real depth. Default 0.5 (DDF points). */
  depthPlayerCutoff: number;
  /** Dead-weight cutoff: a player below this value is droppable for roster space. Default 0.5. */
  deadWeightCutoff: number;
  /** Minimum healthy RB backups beyond starters. Default 1. */
  minRbBackups: number;
  /** Minimum healthy WR backups beyond starters. Default 0 (Jeremy 2026-10-28, JEG-1129). */
  minWrBackups: number;
  /** User-defined guardrails. Default empty. */
  guardrails: Guardrail[];
}

export const DEFAULT_CONFIG: ViabilityConfig = {
  ddfKey: "ddf_value",
  chartKeys: ["usatoday", "fantasycalc", "fantasypros", "cbs"],
  minDdfEdge: 0,
  minMarketNet: 0,
  minUserLineupGain: 0,
  minTheirLineupGain: 0,
  positionWeakerThreshold: 0.15,
  depthPlayerCutoff: 0.5,
  deadWeightCutoff: 0.5,
  minRbBackups: 1,
  minWrBackups: 0,
  guardrails: [],
};

// ---------------------------------------------------------------------------
// Check results
// ---------------------------------------------------------------------------

export type CheckName =
  | "arbitrage"
  | "perceived_fairness"
  | "user_lineup_improves"
  | "their_lineup_improves"
  | "position_protection"
  | "depth"
  | "roster_space"
  | "qb_kept"
  | "user_guardrails";

export interface CheckResult {
  name: CheckName;
  passed: boolean;
  detail: string;
}

export interface ViabilityResult {
  /** All checks, each with passed/failed and a human-readable detail. */
  checks: CheckResult[];
  /** True when every check passed. */
  viable: boolean;
  /** Number of failed checks. */
  failedCount: number;
  /** Human-readable failure reasons (empty when viable). */
  failureReasons: string[];
  /** Acceptance label for viable offers. */
  label: "High" | "Med-High" | "Medium" | null;
  /** True when the trade leaves either team unable to fill a starting slot
   *  while injured/out players are out. */
  temporaryGap: boolean;

  // --- ranking inputs ---
  /** DDF edge: user receives - user gives. */
  ddfEdge: number;
  /** User's starting lineup change on DDF value. */
  userLineupDelta: number;
  /** Other team's Trade chart average net (receive - give). */
  theirMarketNet: number;
  /** Other team's starting lineup change on the Trade chart average. */
  theirLineupDelta: number;

  // --- per-position starters for the other team, before/after ---
  theirPositionsBefore: Record<string, { starters: string[]; value: number }>;
  theirPositionsAfter: Record<string, { starters: string[]; value: number }>;

  // --- user's protected positions after ---
  userProtectedAfter: Record<string, { starters: string[]; value: number }>;
}

/** A scored offer in the final output. */
export interface ScoredOffer {
  team: string;
  userGives: Array<{ player_key: number; name: string; pos: string; ddfValue: number | null }>;
  userGets: Array<{ player_key: number; name: string; pos: string; ddfValue: number | null }>;
  ddfEdge: number;
  userLineupDelta: number;
  theirMarketNet: number;
  theirLineupDelta: number;
  theirPositionsBefore: Record<string, { starters: string[]; value: number }>;
  theirPositionsAfter: Record<string, { starters: string[]; value: number }>;
  userProtectedAfter: Record<string, { starters: string[]; value: number }>;
  viable: boolean;
  label: "High" | "Med-High" | "Medium" | null;
  failedChecks: string[];
  temporaryGap: boolean;
  checks: CheckResult[];
}

/** The best combination of viable offers across opponents. */
export interface PackageResult {
  offers: ScoredOffer[];
  /** Total DDF edge across all offers in the package. */
  totalDdfEdge: number;
  /** User's lineup after all package trades applied. */
  userLineupAfter: Array<{ player_key: number; name: string; pos: string; ddfValue: number | null }>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const finite = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);

const val = (row: ViabilityRow, key: string): number | null => {
  const v = row.values?.[key];
  return finite(v) ? v : null;
};

/** Mean of the chart values for a player (null if any chart missing). */
function marketValue(row: ViabilityRow, chartKeys: string[]): number | null {
  const vals = chartKeys.map((k) => val(row, k));
  if (vals.some((v) => v === null)) return null;
  return (vals as number[]).reduce((a, b) => a + b, 0) / vals.length;
}

function sumValues(rows: ViabilityRow[], key: string): number {
  return rows.reduce((total, r) => total + (val(r, key) ?? 0), 0);
}

function sumMarket(rows: ViabilityRow[], chartKeys: string[]): number {
  return rows.reduce((total, r) => total + (marketValue(r, chartKeys) ?? 0), 0);
}

const FLEX_POS = ["RB", "WR", "TE"];
const SUPERFLEX_POS = ["QB", "RB", "WR", "TE"];
const POSITION_SLOTS = ["QB", "RB", "WR", "TE"] as const;
const ALL_SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"] as const;

/** Pick the best starting lineup for a roster under the given shape and value key. */
function pickStarters(
  rows: ViabilityRow[],
  shape: RosterShape,
  key: string,
): { starters: ViabilityRow[]; bench: ViabilityRow[]; slots: Record<string, ViabilityRow[]>; empty: Record<string, number> } {
  const valued = rows
    .filter((r) => finite(val(r, key)))
    .sort((a, b) => (val(b, key)! - val(a, key)!) || String(a.player_key).localeCompare(String(b.player_key)));
  const taken = new Set<ViabilityRow>();
  const slots: Record<string, ViabilityRow[]> = {};
  const empty: Record<string, number> = {};

  const fill = (slot: string, allowed: string[]) => {
    const want = shape[slot as keyof RosterShape] || 0;
    const got: ViabilityRow[] = [];
    for (const r of valued) {
      if (got.length >= want) break;
      if (!taken.has(r) && allowed.includes(r.pos)) {
        got.push(r);
        taken.add(r);
      }
    }
    slots[slot] = got;
    if (got.length < want) empty[slot] = want - got.length;
  };

  for (const pos of POSITION_SLOTS) fill(pos, [pos]);
  fill("FLEX", FLEX_POS);
  fill("SUPERFLEX", SUPERFLEX_POS);

  return {
    starters: ALL_SLOTS.flatMap((s) => slots[s] || []),
    bench: valued.filter((r) => !taken.has(r)),
    slots,
    empty,
  };
}

function starterValueAtPos(
  rows: ViabilityRow[],
  shape: RosterShape,
  key: string,
  pos: string,
): { starters: ViabilityRow[]; value: number } {
  const picked = pickStarters(rows, shape, key);
  const atPos = picked.starters.filter((r) => r.pos === pos);
  return {
    starters: atPos,
    value: atPos.reduce((s, r) => s + (val(r, key) ?? 0), 0),
  };
}

function lineupStarterValue(rows: ViabilityRow[], shape: RosterShape, key: string): number {
  const picked = pickStarters(rows, shape, key);
  return picked.starters.reduce((s, r) => s + (val(r, key) ?? 0), 0);
}

/** Apply a trade to a roster: remove leaving players, add arriving players. */
function applyTrade(roster: ViabilityRow[], leaving: ViabilityRow[], arriving: ViabilityRow[]): ViabilityRow[] {
  const gone = new Set(leaving.map((r) => r.player_key));
  return roster.filter((r) => !gone.has(r.player_key)).concat(arriving);
}

/** Whether a player is currently out/injured. */
function isOut(row: ViabilityRow): boolean {
  const s = (row.status || "").toLowerCase();
  return s === "out" || s === "injured" || s === "ir";
}

/** Count healthy players at a position with value above a cutoff. */
function healthyDepth(rows: ViabilityRow[], pos: string, key: string, cutoff: number): number {
  return rows.filter(
    (r) => r.pos === pos && !isOut(r) && finite(val(r, key)) && val(r, key)! >= cutoff,
  ).length;
}

/** Count dead-weight players on a roster (value below cutoff in DDF). */
function deadWeightCount(rows: ViabilityRow[], key: string, cutoff: number): number {
  return rows.filter(
    (r) => !finite(val(r, key)) || val(r, key)! < cutoff,
  ).length;
}

// ---------------------------------------------------------------------------
// Viability checks
// ---------------------------------------------------------------------------

export function runViabilityChecks(
  userRoster: ViabilityRow[],
  theirRoster: ViabilityRow[],
  userGives: ViabilityRow[],
  userGets: ViabilityRow[],
  shape: RosterShape,
  config: ViabilityConfig = DEFAULT_CONFIG,
): ViabilityResult {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const ddf = cfg.ddfKey;
  const charts = cfg.chartKeys;

  const userAfter = applyTrade(userRoster, userGives, userGets);
  const theirAfter = applyTrade(theirRoster, userGets, userGives);

  // --- Value sums ---
  const userGivesDdf = sumValues(userGives, ddf);
  const userGetsDdf = sumValues(userGets, ddf);
  const ddfEdge = userGetsDdf - userGivesDdf;

  const theirGivesMarket = sumMarket(userGets, charts); // what they give = what user gets
  const theirGetsMarket = sumMarket(userGives, charts);  // what they get = what user gives
  const theirMarketNet = theirGetsMarket - theirGivesMarket;

  // --- Lineup values ---
  const userLineupBefore = lineupStarterValue(userRoster, shape, ddf);
  const userLineupAfter = lineupStarterValue(userAfter, shape, ddf);
  const userLineupDelta = userLineupAfter - userLineupBefore;

  // Their lineup on the Trade chart average: attach each player's Indexed chart mean.
  const withMarket = (rows: ViabilityRow[]): ViabilityRow[] =>
    rows.map((r) => ({
      ...r,
      values: { ...r.values, _market: marketValue(r, charts) },
    }));

  const theirRosterM = withMarket(theirRoster);
  const theirAfterM = withMarket(theirAfter);
  const theirLineupBeforeM = lineupStarterValue(theirRosterM, shape, "_market");
  const theirLineupAfterM = lineupStarterValue(theirAfterM, shape, "_market");
  const theirLineupDelta = theirLineupAfterM - theirLineupBeforeM;

  const checks: CheckResult[] = [];

  // 1. Arbitrage: user receives more DDF value than sent.
  const arbitragePass = ddfEdge > cfg.minDdfEdge;
  checks.push({
    name: "arbitrage",
    passed: arbitragePass,
    detail: arbitragePass
      ? `You gain ${ddfEdge.toFixed(1)} DDF Value`
      : `You ${ddfEdge >= 0 ? "only gain" : "lose"} ${ddfEdge.toFixed(1)} DDF Value`,
  });

  // 2. Perceived fairness: other team receives >= what it sends on the Trade chart average.
  const fairnessPass = theirMarketNet >= cfg.minMarketNet;
  checks.push({
    name: "perceived_fairness",
    passed: fairnessPass,
    detail: fairnessPass
      ? `They gain ${theirMarketNet.toFixed(1)} on the Trade chart average`
      : `Looks lopsided to them (${theirMarketNet.toFixed(1)} on the Trade chart average)`,
  });

  // 3. User's starting lineup improves on DDF value (strictly > 0; Jeremy 2026-10-24).
  const userLineupPass = userLineupDelta > cfg.minUserLineupGain;
  checks.push({
    name: "user_lineup_improves",
    passed: userLineupPass,
    detail: userLineupPass
      ? `Your lineup improves by ${userLineupDelta.toFixed(1)}`
      : `Your lineup ${userLineupDelta >= 0 ? "doesn't improve" : "gets weaker by " + Math.abs(userLineupDelta).toFixed(1)}`,
  });

  // 4. Other team's starting lineup improves on the Trade chart average (strictly > 0; Jeremy 2026-10-24).
  const theirLineupPass = theirLineupDelta > cfg.minTheirLineupGain;
  checks.push({
    name: "their_lineup_improves",
    passed: theirLineupPass,
    detail: theirLineupPass
      ? `Their lineup improves by ${theirLineupDelta.toFixed(1)} on the Trade chart average`
      : `Doesn't improve their lineup (${theirLineupDelta.toFixed(1)} on the Trade chart average)`,
  });

  // 5. Position protection: their resulting starting lineup total Trade chart average
  //    must not decrease. Empty slots are filled at replacement level (0), so a
  //    real hole shows up as a value loss. Per-position before/after is display
  //    only, not a pass/fail gate. (Jeremy 2026-10-24: dropped per-position 15%
  //    weaker test; focus on total starting lineup Trade chart average.)

  // Build their position before/after for every position (display only)
  const theirPosBefore: Record<string, { starters: string[]; value: number }> = {};
  const theirPosAfter: Record<string, { starters: string[]; value: number }> = {};
  for (const pos of POSITION_SLOTS) {
    const before = starterValueAtPos(theirRosterM, shape, "_market", pos);
    const after = starterValueAtPos(theirAfterM, shape, "_market", pos);
    theirPosBefore[pos] = { starters: before.starters.map((r) => r.name), value: before.value };
    theirPosAfter[pos] = { starters: after.starters.map((r) => r.name), value: after.value };
  }

  // Total starting lineup Trade chart average check
  const theirPickedAfter = pickStarters(theirAfterM, shape, "_market");
  const emptySlots = Object.entries(theirPickedAfter.empty);
  let posProtectionPass: boolean;
  let posProtectionDetail: string;

  if (emptySlots.length > 0) {
    // Trade leaves them unable to fill starting slots
    posProtectionPass = false;
    const slotNames = emptySlots.map(([slot, count]) => `${count} ${slot}`).join(", ");
    posProtectionDetail = `Trade leaves them unable to fill starting slots: ${slotNames}`;
  } else if (theirLineupAfterM < theirLineupBeforeM - 0.05) {
    // Their total starting lineup value drops
    posProtectionPass = false;
    const drop = theirLineupBeforeM - theirLineupAfterM;
    posProtectionDetail = `Their starting lineup drops ${drop.toFixed(1)} on the Trade chart average`;
  } else {
    posProtectionPass = true;
    posProtectionDetail = "Their starting lineup holds or improves on the Trade chart average";
  }

  checks.push({
    name: "position_protection",
    passed: posProtectionPass,
    detail: posProtectionDetail,
  });

  // 6. Depth: neither team lacks enough healthy relevant players.
  let depthPass = true;
  const depthDetails: string[] = [];
  const checkDepth = (
    roster: ViabilityRow[],
    who: string,
    key: string,
  ) => {
    const rbSlots = shape.RB + (shape.FLEX || 0); // RB can fill flex
    const wrSlots = shape.WR + (shape.FLEX || 0); // WR can fill flex
    const rbDepth = healthyDepth(roster, "RB", key, cfg.depthPlayerCutoff);
    const wrDepth = healthyDepth(roster, "WR", key, cfg.depthPlayerCutoff);
    const rbNeed = shape.RB + cfg.minRbBackups;
    const wrNeed = shape.WR + cfg.minWrBackups;
    if (rbDepth < rbNeed) {
      depthPass = false;
      depthDetails.push(`Leaves ${who} thin at RB (${rbDepth} healthy, need ${rbNeed})`);
    }
    if (wrDepth < wrNeed) {
      depthPass = false;
      depthDetails.push(`Leaves ${who} thin at WR (${wrDepth} healthy, need ${wrNeed})`);
    }
  };
  checkDepth(userAfter, "you", ddf);
  checkDepth(theirAfterM, "them", "_market");
  checks.push({
    name: "depth",
    passed: depthPass,
    detail: depthPass ? "Both teams have adequate depth" : depthDetails.join("; "),
  });

  // 7. Roster space: a team taking more players than it sends must have dead weight to drop.
  const userNetPlayers = userGets.length - userGives.length;
  const theirNetPlayers = userGives.length - userGets.length;
  let rosterSpacePass = true;
  const rosterSpaceDetails: string[] = [];
  if (userNetPlayers > 0) {
    const drops = deadWeightCount(userAfter, ddf, cfg.deadWeightCutoff);
    if (drops < userNetPlayers) {
      rosterSpacePass = false;
      rosterSpaceDetails.push(`You take ${userNetPlayers} more player${userNetPlayers > 1 ? "s" : ""} but have no dead weight to drop`);
    }
  }
  if (theirNetPlayers > 0) {
    const drops = deadWeightCount(theirAfter, ddf, cfg.deadWeightCutoff);
    if (drops < theirNetPlayers) {
      rosterSpacePass = false;
      rosterSpaceDetails.push(`They take ${theirNetPlayers} more player${theirNetPlayers > 1 ? "s" : ""} but have no dead weight to drop`);
    }
  }
  checks.push({
    name: "roster_space",
    passed: rosterSpacePass,
    detail: rosterSpacePass ? "Roster space OK" : rosterSpaceDetails.join("; "),
  });

  // 8. Both teams keep a QB.
  const userQBs = userAfter.filter((r) => r.pos === "QB").length;
  const theirQBs = theirAfter.filter((r) => r.pos === "QB").length;
  const qbPass = userQBs >= 1 && theirQBs >= 1;
  checks.push({
    name: "qb_kept",
    passed: qbPass,
    detail: qbPass
      ? "Both teams keep a QB"
      : `${userQBs < 1 ? "You" : "They"} would have no QB`,
  });

  // 9. User guardrails.
  let guardrailPass = true;
  const guardrailDetails: string[] = [];
  for (const g of cfg.guardrails) {
    if (g.minStarters !== undefined) {
      const afterAtPos = userAfter.filter(
        (r) => r.pos === g.pos && r.ddfTier === "starter",
      );
      if (afterAtPos.length < g.minStarters) {
        guardrailPass = false;
        guardrailDetails.push(
          `Weakens your ${g.pos} below ${g.minStarters} starter${g.minStarters > 1 ? "s" : ""}`,
        );
      }
    }
    if (g.neverWeaker) {
      const before = starterValueAtPos(userRoster, shape, ddf, g.pos);
      const after = starterValueAtPos(userAfter, shape, ddf, g.pos);
      if (after.value < before.value - 0.05) {
        guardrailPass = false;
        guardrailDetails.push(`Weakens your starting ${g.pos} group`);
      }
    }
  }
  checks.push({
    name: "user_guardrails",
    passed: guardrailPass,
    detail: guardrailPass
      ? (cfg.guardrails.length ? "User guardrails satisfied" : "No guardrails set")
      : guardrailDetails.join("; "),
  });

  // --- Temporary gap flag ---
  const tempGap = checkTemporaryGap(userAfter, shape, ddf) ||
    checkTemporaryGap(theirAfterM, shape, "_market");

  // --- Viable? ---
  const failedChecks = checks.filter((c) => !c.passed);
  const viable = failedChecks.length === 0;

  // --- Label ---
  let label: ViabilityResult["label"] = null;
  if (viable) {
    // High: a position they traded from actually gets better AND their lineup clearly improves
    const positionsTheyTraded = [...new Set(userGets.map((r) => r.pos))];
    const posGetsStronger = positionsTheyTraded.some((pos) => {
      if (!POSITION_SLOTS.includes(pos as typeof POSITION_SLOTS[number])) return false;
      return (theirPosAfter[pos]?.value ?? 0) > (theirPosBefore[pos]?.value ?? 0) + 0.05;
    });
    if (posGetsStronger && theirLineupDelta > 0.5) {
      label = "High";
    } else if (theirLineupDelta > 0.5 || theirMarketNet > 1) {
      label = "Med-High";
    } else {
      label = "Medium";
    }
  }

  // --- User's protected positions after ---
  const userProtectedAfter: Record<string, { starters: string[]; value: number }> = {};
  for (const g of cfg.guardrails) {
    const after = starterValueAtPos(userAfter, shape, ddf, g.pos);
    userProtectedAfter[g.pos] = { starters: after.starters.map((r) => r.name), value: after.value };
  }

  return {
    checks,
    viable,
    failedCount: failedChecks.length,
    failureReasons: failedChecks.map((c) => c.detail),
    label,
    temporaryGap: tempGap,
    ddfEdge,
    userLineupDelta,
    theirMarketNet,
    theirLineupDelta,
    theirPositionsBefore: theirPosBefore,
    theirPositionsAfter: theirPosAfter,
    userProtectedAfter,
  };
}

/** Check if a roster has a temporary lineup gap (cannot fill starting slots
 *  while injured/out players are out). */
function checkTemporaryGap(
  roster: ViabilityRow[],
  shape: RosterShape,
  key: string,
): boolean {
  const healthy = roster.filter((r) => !isOut(r));
  const picked = pickStarters(healthy, shape, key);
  return Object.keys(picked.empty).length > 0;
}

// ---------------------------------------------------------------------------
// Scoring and ordering
// ---------------------------------------------------------------------------

export interface TradeOfferInput {
  team: string;
  userGives: ViabilityRow[];
  userGets: ViabilityRow[];
  userRoster: ViabilityRow[];
  theirRoster: ViabilityRow[];
}

/** Score and rank a list of trade offers. */
export function scoreAndRankOffers(
  offers: TradeOfferInput[],
  shape: RosterShape,
  config: ViabilityConfig = DEFAULT_CONFIG,
): ScoredOffer[] {
  const cfg = { ...DEFAULT_CONFIG, ...config };

  const scored: ScoredOffer[] = offers.map((offer) => {
    const result = runViabilityChecks(
      offer.userRoster,
      offer.theirRoster,
      offer.userGives,
      offer.userGets,
      shape,
      cfg,
    );

    return {
      team: offer.team,
      userGives: offer.userGives.map((r) => ({
        player_key: r.player_key,
        name: r.name,
        pos: r.pos,
        ddfValue: val(r, cfg.ddfKey),
      })),
      userGets: offer.userGets.map((r) => ({
        player_key: r.player_key,
        name: r.name,
        pos: r.pos,
        ddfValue: val(r, cfg.ddfKey),
      })),
      ddfEdge: result.ddfEdge,
      userLineupDelta: result.userLineupDelta,
      theirMarketNet: result.theirMarketNet,
      theirLineupDelta: result.theirLineupDelta,
      theirPositionsBefore: result.theirPositionsBefore,
      theirPositionsAfter: result.theirPositionsAfter,
      userProtectedAfter: result.userProtectedAfter,
      viable: result.viable,
      label: result.label,
      failedChecks: result.failureReasons,
      temporaryGap: result.temporaryGap,
      checks: result.checks,
    };
  });

  // Deduplicate: offers that receive the same players keep only the best.
  const deduped = deduplicateOffers(scored);

  // Sort: viable first, then by ranking criteria.
  return deduped.sort((a, b) => {
    // Viable first
    if (a.viable !== b.viable) return a.viable ? -1 : 1;

    if (a.viable && b.viable) {
      // Among viable: DDF edge desc, then user lineup improvement desc,
      // then how much better it looks to them desc.
      return (
        b.ddfEdge - a.ddfEdge ||
        b.userLineupDelta - a.userLineupDelta ||
        b.theirMarketNet - a.theirMarketNet
      );
    }

    // Among non-viable: fewest failed checks first, then DDF edge desc.
    const aFailed = a.checks.filter((c) => !c.passed).length;
    const bFailed = b.checks.filter((c) => !c.passed).length;
    return aFailed - bFailed || b.ddfEdge - a.ddfEdge;
  });
}

/** Deduplicate offers that receive the same players. Keep the best by DDF edge. */
function deduplicateOffers(offers: ScoredOffer[]): ScoredOffer[] {
  const seen = new Map<string, ScoredOffer>();
  for (const offer of offers) {
    const key = offer.userGets
      .map((p) => p.player_key)
      .sort((a, b) => a - b)
      .join(",");
    const existing = seen.get(key);
    if (!existing || offer.ddfEdge > existing.ddfEdge) {
      seen.set(key, offer);
    }
  }
  return [...seen.values()];
}

// ---------------------------------------------------------------------------
// Package selection
// ---------------------------------------------------------------------------

/**
 * Select the best combination of viable offers that:
 * - Never sends the same player twice
 * - Uses each opponent team at most once
 * Returns the package and the user's lineup after all trades applied.
 */
export function selectPackage(
  rankedOffers: ScoredOffer[],
  userRoster: ViabilityRow[],
  shape: RosterShape,
  ddfKey: string = "ddf_value",
): PackageResult {
  const viable = rankedOffers.filter((o) => o.viable);
  if (!viable.length) {
    return {
      offers: [],
      totalDdfEdge: 0,
      userLineupAfter: userRoster.map((r) => ({
        player_key: r.player_key,
        name: r.name,
        pos: r.pos,
        ddfValue: val(r, ddfKey),
      })),
    };
  }

  // Greedy: take viable offers in rank order, skip if conflict.
  const usedTeams = new Set<string>();
  const sentPlayers = new Set<number>();
  const selected: ScoredOffer[] = [];

  for (const offer of viable) {
    if (usedTeams.has(offer.team)) continue;
    const playerKeys = offer.userGives.map((p) => p.player_key);
    if (playerKeys.some((k) => sentPlayers.has(k))) continue;

    selected.push(offer);
    usedTeams.add(offer.team);
    for (const k of playerKeys) sentPlayers.add(k);
  }

  // Build the user's roster after all selected trades.
  let finalRoster = userRoster;
  for (const offer of selected) {
    const giving = new Set(offer.userGives.map((p) => p.player_key));
    const getting = offer.userGets.map((p) => {
      // Find full row from the original offer input - we need the values
      // For now, construct a minimal row
      return {
        player_key: p.player_key,
        name: p.name,
        pos: p.pos,
        values: { [ddfKey]: p.ddfValue },
      } as ViabilityRow;
    });
    finalRoster = finalRoster.filter((r) => !giving.has(r.player_key)).concat(getting);
  }

  const picked = pickStarters(finalRoster, shape, ddfKey);
  const lineupAfter = picked.starters.concat(picked.bench).map((r) => ({
    player_key: r.player_key,
    name: r.name,
    pos: r.pos,
    ddfValue: val(r, ddfKey),
  }));

  return {
    offers: selected,
    totalDdfEdge: selected.reduce((s, o) => s + o.ddfEdge, 0),
    userLineupAfter: lineupAfter,
  };
}
