// The engine input get-values builds from the published bundle, and the week it prices (JEG-1179).
// Pure functions, no Deno APIs: the deployed handler (index.ts) and the parity runner
// (tests/_edge_pipeline_runner.cjs) both import this file, so the parity test exercises the shipped code.
//
// Source eligibility mirrors curve-widget.js (eligibilityReason, compositeKeyOlderWeek). The week view
// mirrors curve-widget.js resolveWeekView / computePipeline and value_reference.Setting.week_view: the
// default week is the site's own ValueModel.weekState (value-model.js, loaded from the published site,
// so the rule is the site's code, not a copy). No carry-forward (Jeremy, 2026-10-27, JEG-1176): a source
// serving an earlier week is left out of the view; a source serving a later week is priced on its saved
// copy of the view's week, or left out when no copy is saved.

import type { LeagueInputs } from "./league.ts";

// deno-lint-ignore no-explicit-any
type Any = any;

/** The published history the page reads (assets/history/index.json and the week-<N>.json documents). */
export interface HistoryData {
  index: Any | null;
  /** Week documents by week number (as a string), loaded on demand. */
  docs: Record<string, Any>;
}

export interface Bundle {
  detail: Record<string, unknown>;
  players: Array<Record<string, unknown>>;
  ValueModel: Record<string, unknown>;
  lineupConfig: Record<string, unknown> | null;
  history?: HistoryData | null;
}

// Pipeline source keys (must match curve-widget.js PIPELINE_SOURCE_KEYS).
export const PIPELINE_SOURCE_KEYS = [
  "espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs",
];
const PROJECTION_SOURCE_KEYS = ["espn", "cbsros", "razzball"];
const PPG_FIELD_OF: Record<string, string> = {
  espn: "espn_ppg",
  cbsros: "cbsros_ppg",
  razzball: "rz_ppg",
};
// curve-widget.js HISTORY_SCORING_INDEX: a saved projection is [standard, half_ppr, ppr].
const HISTORY_SCORING_INDEX: Record<string, number> = { standard: 0, half_ppr: 1, ppr: 2 };

// Scoring field from scoring name.
function scoringField(scoring: string): string {
  return scoring === "ppr" ? "ppr" : scoring === "half_ppr" ? "half_ppr" : "standard";
}

// Replicates product-data.js espnProjectsZero(): ESPN considers this player
// listed at 0 (injured/out) even though espn_ppg is absent.
function espnProjectsZero(player: Any): boolean {
  if (player.espn_status === "ineligible") return true;
  if (player.espn_status === "absent") return false;
  if (player.espn_zeroed === true) return true;
  const ppg = player.espn_ppg;
  if (!ppg || typeof ppg !== "object") return false;
  const values = Object.values(ppg);
  return values.length > 0 && values.every((v) => typeof v === "number" && v === 0);
}

// --- Source freshness / eligibility (mirrors product-data.js + curve-widget.js)

const CONTENT_WEEK_1_START_UTC = Date.UTC(2026, 8, 8); // Tue 2026-09-08
const CONTENT_WEEK_MAX = 18;
const DAY_MS = 86400000;

export function contentWeekForDay(day: string | null): number | null {
  if (!day) return null;
  const [y, m, d] = day.split("-").map(Number);
  const days = Math.round((Date.UTC(y, m - 1, d) - CONTENT_WEEK_1_START_UTC) / DAY_MS);
  if (days < 0) return 1;
  return Math.min(Math.max(Math.floor(days / 7) + 1, 1), CONTENT_WEEK_MAX);
}

/** Today's date in New York (the page's content-week clock). */
export function todayIso(): string {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

function isoDay(v: unknown): string | null {
  if (!v || typeof v !== "string") return null;
  const m = v.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

function parseWeekLabel(value: unknown): number | null {
  const m = String(value || "").match(/week\s*(\d+)|wk\s*(\d+)/i);
  return m ? Number(m[1] || m[2]) : null;
}

function sourceVintage(meta: Any): { week: number | null; basis: string | null } {
  const m = meta && typeof meta === "object" ? meta : {};
  const designated = parseWeekLabel(m.week_designated);
  if (designated) return { week: designated, basis: "week_designated" };
  const vintageWeek = parseWeekLabel(m.content_vintage);
  if (vintageWeek) return { week: vintageWeek, basis: "content_vintage" };
  const dated: Array<[string, unknown]> = [
    ["content_vintage", m.content_vintage],
    ["vintage", m.vintage],
    ["espn_snapshot", m.espn_snapshot],
    ["lineage.raw_vintage", m.lineage?.raw_vintage],
    ["fetched_at", m.fetched_at],
  ];
  const found = dated.find(([, value]) => isoDay(value));
  if (found) return { week: contentWeekForDay(isoDay(found[1])), basis: found[0] };
  return { week: null, basis: null };
}

// Weekly chart sources (curve-widget.js WEEKED_SOURCE_KEYS base set).
const WEEKED_SOURCES = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs"]);

// Hold fields on source sections.
const HOLD_FIELDS = ["validationHold", "promotionHold"];

function sectionHold(sourceSection: Any): { reason: string; hidden: boolean } | null {
  if (!sourceSection || typeof sourceSection !== "object") return null;
  for (const field of HOLD_FIELDS) {
    const hold = sourceSection[field];
    if (hold && typeof hold === "object" && hold.reason) {
      // JEG-726 / JEG-787: an amber validationHold labels the source but does
      // NOT hide it from DDF Value or Indexed.  Only red holds (the default
      // when hold_level is absent) and promotionHolds hide.
      const isAmber = field === "validationHold" && hold.hold_level === "amber";
      return { reason: hold.reason, hidden: !isAmber };
    }
  }
  return null;
}

// What keeps a source out of DDF Value regardless of week (curve-widget.js eligibilityReason with
// ignoreWeek): a red hold, a failed source validation, a divergence exclusion.
function sourceFlags(detail: Any, key: string) {
  const section = detail.sources?.[key];
  const hold = sectionHold(section);
  const svStatus = (detail.source_validation as Record<string, string> | undefined)?.[key];
  // product-data.js reads divergence_exclusions from the bundle's top level (sync_dashboard_artifacts.py
  // writes it there); the snapshot field is kept as a fallback.
  const exclusions = Array.isArray(detail.divergence_exclusions) ? detail.divergence_exclusions
    : Array.isArray(detail.snapshot?.divergence_exclusions) ? detail.snapshot.divergence_exclusions : [];
  return {
    section,
    hold,
    validationHeld: svStatus !== undefined && svStatus !== "live",
    divergenceExcluded: exclusions.indexOf(key) !== -1,
  };
}

/** A source's natives this week (curve-widget.js currentNatives): {player_key: value}. */
function currentNatives(bundle: Bundle, key: string, scoring: string, superflex: number): Record<number, number> {
  const detail = bundle.detail as Any;
  const section = detail.sources?.[key];
  const values: Record<number, number> = {};
  if (!section) return values;
  if (!PROJECTION_SOURCE_KEYS.includes(key)) {
    // Chart source: read saved native values from the combo. The engine page always looks up chart
    // combos at qb1 (product-data.js qbVariant: "qb1"); superflex values are overlaid via native_superflex.
    const comboKeyStr = (bundle.ValueModel as Any).sourceComboKey(key, scoring, 12, 1);
    const combo = comboKeyStr ? section.combos?.[comboKeyStr] : null;
    if (!combo || !combo.native) return values;
    const pkMap = detail.player_keys as Record<string, number>;
    for (const [sourceId, val] of Object.entries(combo.native as Record<string, number>)) {
      const playerKey = pkMap?.[sourceId];
      if (playerKey !== undefined && Number.isFinite(val)) values[playerKey] = val;
    }
    if (superflex && combo.native_superflex) {
      for (const [sourceId, val] of Object.entries(combo.native_superflex as Record<string, number>)) {
        const playerKey = pkMap?.[sourceId];
        if (playerKey !== undefined && Number.isFinite(val)) values[playerKey] = val;
      }
    }
    return values;
  }
  // Projection source: read per-game points from players.
  const field = scoringField(scoring);
  const ppgField = PPG_FIELD_OF[key];
  for (const p of bundle.players) {
    const pk = p.player_key as number;
    // ESPN zero handling: players ESPN lists at 0 (ineligible/zeroed).
    if (key === "espn" && espnProjectsZero(p) && !p.espn_ppg) {
      values[pk] = 0;
      continue;
    }
    const ppg = (p[ppgField] as Record<string, number> | undefined)?.[field];
    if (ppg !== null && ppg !== undefined && Number.isFinite(ppg)) values[pk] = ppg;
  }
  return values;
}

// --- The week view (JEG-1177 on the page, JEG-1179 here) ---------------------

/** The week a response is priced on, and what that week leaves out. */
export interface WeekInfo {
  /** The week priced. */
  week: number | null;
  /** The week the site opens on at this setting (ValueModel.weekState default_week). */
  default_week: number | null;
  /** Weeks that can be asked for (the transition's two weeks, or the one week). */
  weeks: number[];
  /** "history" when the week view came from the published week history; "calendar" otherwise. */
  basis: "history" | "calendar";
  /** DDF Value sources priced on this week. */
  sources: string[];
  /** DDF Value sources at this setting that have not published this week (or have no saved copy of it). */
  missing_sources: string[];
}

export type WeekPlan =
  | {
    ok: true;
    week: number | null;
    /** The history document this week needs (a source serving a later week is read from it), or null. */
    docWeek: number | null;
    view: Any | null; // ValueModel.weekState result, plus served weeks
    served: Record<string, number | null>;
    candidates: string[];
    fallback: { referenceWeek: number | null; olderWeek: Set<string> };
  }
  | { ok: false; error: string; weeks: number[]; default_week: number | null };

// The history index belongs to the bundle being served (curve-widget.js servedWeekOf).
export function historyMatchesBuild(bundle: Bundle): boolean {
  const index = bundle.history?.index;
  if (!index || typeof index !== "object") return false;
  const built = (bundle.detail as Any).built_at;
  return !(index.fixture_built_at && built && index.fixture_built_at !== built);
}

// The calendar fallback when there is no week view (first_load_reference_week, first_load_excluded):
// the calendar only caps the reference week; a chart is older only when behind that week (#1028).
function calendarFreshness(detail: Any, today: string) {
  const currentContentWeek = contentWeekForDay(today);
  const rows: Record<string, { week: number | null }> = {};
  for (const key of PIPELINE_SOURCE_KEYS) {
    const sourceMeta = detail.sources?.[key];
    if (!sourceMeta) continue;
    rows[key] = { week: sourceVintage(sourceMeta).week };
  }
  const weeklyWeeks = Object.entries(rows)
    .filter(([key, r]) => WEEKED_SOURCES.has(key) && r.week !== null)
    .map(([, r]) => r.week!);
  const referenceWeek = weeklyWeeks.length ? Math.min(Math.max(...weeklyWeeks), currentContentWeek ?? 0) : null;
  const olderWeek = new Set<string>();
  for (const [key, r] of Object.entries(rows)) {
    if (!WEEKED_SOURCES.has(key) || r.week === null) continue;
    // Older week: a weekly chart behind the newest published week (the first-load rule, #1028). The
    // calendar's week is not the test: on the Tuesday flip every chart is still on last week, and
    // judging them against the calendar dropped them all and priced nobody (Oct 27 2026).
    if (referenceWeek !== null && r.week < referenceWeek) olderWeek.add(key);
  }
  return { referenceWeek: referenceWeek ?? currentContentWeek, olderWeek, labels: rows };
}

function weekList(weeks: number[]): string {
  return weeks.length ? weeks.join(", ") : "none";
}

/**
 * Which week to price: the requested one, or the site's default (ValueModel.weekState over the
 * DDF Value sources at this setting, each with the week it serves). A requested week that is not
 * one of the weeks with published sources is an error, never an empty list.
 */
export function planWeek(bundle: Bundle, m: LeagueInputs, requested: number | null, today: string): WeekPlan {
  const detail = bundle.detail as Any;
  const superflex = m.setting.superflex;
  // DDF Value sources at this setting, judged without any week rule (resolveWeekView's candidates).
  const candidates = PIPELINE_SOURCE_KEYS.filter((key) => {
    const f = sourceFlags(detail, key);
    if (!f.section) return false;
    if ((f.hold && f.hold.hidden) || f.validationHeld || f.divergenceExcluded) return false;
    return Object.keys(currentNatives(bundle, key, m.scoring, superflex)).length > 0;
  });
  const fallback = calendarFreshness(detail, today);
  const served: Record<string, number | null> = {};
  let view: Any | null = null;
  // A published value-model.js from before JEG-1177 has no weekState: the calendar rule then applies.
  if (historyMatchesBuild(bundle) && typeof (bundle.ValueModel as Any).weekState === "function") {
    const index = bundle.history!.index;
    for (const key of PIPELINE_SOURCE_KEYS) {
      const w = index.served?.[key]?.week;
      served[key] = Number.isInteger(w) ? w : null;
    }
    const state = (bundle.ValueModel as Any).weekState(candidates.map((key) => ({ source: key, week: served[key] })));
    if (Number.isInteger(state.default_week)) view = state;
  }

  if (view) {
    const week = requested ?? view.default_week;
    if (!view.weeks.includes(week)) {
      return {
        ok: false,
        error: `Week ${week} has no published sources at this setting. Weeks available: ${weekList(view.weeks)} ` +
          `(default ${view.default_week}).`,
        weeks: view.weeks, default_week: view.default_week,
      };
    }
    const docWeek = PIPELINE_SOURCE_KEYS.some((key) => Number.isInteger(served[key]) && served[key]! > week) ? week : null;
    return { ok: true, week, docWeek, view, served, candidates, fallback };
  }
  // No week history for this build: the calendar's week, the only week that can be asked for.
  const week = fallback.referenceWeek;
  if (requested !== null && requested !== week) {
    const weeks = week === null ? [] : [week];
    return {
      ok: false,
      error: `Week ${requested} has no published sources at this setting. Weeks available: ${weekList(weeks)}` +
        (week === null ? "." : ` (default ${week}).`),
      weeks, default_week: week,
    };
  }
  return { ok: true, week, docWeek: null, view: null, served: {}, candidates, fallback };
}

// A saved week's natives for one source (curve-widget.js weekNatives / historyNatives / historyPpg).
// The saved weeks carry 1-QB chart natives only, so a saved week at a superflex setting runs on them.
export function savedNatives(bundle: Bundle, key: string, week: number, scoring: string): { values?: Record<number, number>; reason?: string } {
  const doc = bundle.history?.docs?.[String(week)];
  const entry = doc?.sources?.[key];
  if (!doc) return { reason: `no Week ${week} content saved` };
  if (!entry) return { reason: `no Week ${week} ${key} content saved` };
  if (entry.week !== week) return { reason: `saved entry is labelled week ${entry.week}` };
  const known = new Set(bundle.players.map((p) => Number(p.player_key)));
  const values: Record<number, number> = {};
  if (PROJECTION_SOURCE_KEYS.includes(key)) {
    const idx = HISTORY_SCORING_INDEX[scoringField(scoring)];
    for (const [pk, triple] of Object.entries((entry.ppg ?? {}) as Record<string, number[]>)) {
      const value = Number(triple?.[idx]);
      if (known.has(Number(pk)) && Number.isFinite(value)) values[Number(pk)] = value;
    }
  } else {
    for (const [pk, raw] of Object.entries((entry.natives?.[scoring] ?? {}) as Record<string, number>)) {
      const value = Number(raw);
      if (known.has(Number(pk)) && Number.isFinite(value)) values[Number(pk)] = value;
    }
  }
  if (!Object.keys(values).length) return { reason: `no ${scoring} values saved for Week ${week}` };
  return { values };
}

// Build the pipeline input for the given settings and week plan.
export function buildPipelineInput(bundle: Bundle, m: LeagueInputs, plan: Extract<WeekPlan, { ok: true }>) {
  const { scoring } = m;
  const superflex = m.setting.superflex;
  const detail = bundle.detail as Any;
  const ValueModel = bundle.ValueModel as Any;

  // Build player map: player_key -> {pos, name}.
  const playerMap: Record<number, { pos: string; name: string }> = {};
  for (const p of bundle.players) {
    playerMap[p.player_key as number] = { pos: p.pos as string, name: p.name as string };
  }

  const week = plan.week;
  const view = plan.view;
  // A source serving a later week than the view is priced on its saved copy of the view's week.
  const saved: Record<string, Record<number, number>> = {};
  const missingSaved: Record<string, string> = {};
  if (view && week !== null) {
    for (const key of PIPELINE_SOURCE_KEYS) {
      const s = plan.served[key];
      if (!(Number.isInteger(s) && s! > week)) continue;
      const got = savedNatives(bundle, key, week, scoring);
      if (got.values) saved[key] = got.values;
      else missingSaved[key] = got.reason!;
    }
  }

  const sources: Record<string, unknown> = {};
  const included: string[] = [];
  const hiddenKeys: string[] = [];

  for (const key of PIPELINE_SOURCE_KEYS) {
    const family = PROJECTION_SOURCE_KEYS.includes(key) ? "projection" : "chart";
    const f = sourceFlags(detail, key);
    // sourceMissingFromData: no source section at all.
    if (!f.section) continue;

    let values = currentNatives(bundle, key, scoring, superflex);
    const served = view ? plan.served[key] : null;
    let olderWeek: boolean;
    if (view && Number.isInteger(served)) {
      if (served !== week) {
        // No carry-forward: a source on an earlier week is left out of this week's view.
        if (served! < week!) continue;
        if (!saved[key]) continue;
        values = saved[key];
      }
      // Inside a week view "older" is judged against the view's week (compositeKeyOlderWeek).
      const label = WEEKED_SOURCES.has(key) ? sourceVintage(f.section).week : null;
      olderWeek = served! < week! || (label !== null && label < week!);
    } else {
      olderWeek = plan.fallback.olderWeek.has(key);
    }

    // Not yet published for this week: excluded (unless held or divergence-excluded).
    if (olderWeek && !f.hold && !f.validationHeld && !f.divergenceExcluded) continue;
    if (Object.keys(values).length === 0) continue;

    sources[key] = { family, status: "included", values, label: key };
    included.push(key);

    // Mark as hidden if red-held, validation-held, or divergence-excluded.
    // JEG-726 / JEG-787: amber holds label the source but do NOT hide it.
    if ((f.hold && f.hold.hidden) || f.validationHeld || f.divergenceExcluded) hiddenKeys.push(key);
  }

  // JEG-1385, VP-1.2 (curve-widget.js computePipeline, value_reference result()): when at least one included
  // source has Week N-1 saved, the included set I is those sources and this week is priced on I; the others
  // are shown, never counted. When none has it, I is every included source. A source pairs only with this
  // build's history (the week view) and a served week of its own (servedWeekOf, JEG-1390). The caller loads
  // Week N-1's document first (index.ts); an unread document reads as no source paired, so nothing narrows.
  const unpaired: Record<string, string> = {};
  if (view && week !== null) {
    const reasons: Record<string, string> = {};
    for (const key of included) {
      if (!Number.isInteger(plan.served[key])) {
        reasons[key] = bundle.history?.index?.served?.[key]?.reason || `no saved week matches the ${key} values served now`;
        continue;
      }
      const got = savedNatives(bundle, key, week - 1, scoring);
      if (!got.values) reasons[key] = got.reason!;
    }
    const paired = included.filter((key) => !reasons[key]);
    if (paired.length && paired.length < included.length) {
      for (const key of included) {
        if (paired.includes(key)) continue;
        sources[key] = { ...(sources[key] as Any), status: "excluded" };
        unpaired[key] = `no prior week: ${reasons[key]}`;
      }
      included.splice(0, included.length, ...paired);
    }
  }

  // The week this answer is priced on, with the view's sources and missing sources.
  let info: WeekInfo;
  if (view) {
    const v = view.views[String(week)] ?? { sources: [], missing_sources: [] };
    const gone = (v.sources as string[]).filter((key) => missingSaved[key]);
    info = {
      week, default_week: view.default_week, weeks: [...view.weeks], basis: "history",
      sources: (v.sources as string[]).filter((key) => !gone.includes(key)),
      missing_sources: [...v.missing_sources, ...gone].sort(),
    };
  } else {
    const missing = plan.candidates.filter((key) => plan.fallback.olderWeek.has(key)).sort();
    info = {
      week, default_week: week, weeks: week === null ? [] : [week], basis: "calendar",
      sources: plan.candidates.filter((key) => !missing.includes(key)).sort(), missing_sources: missing,
    };
  }

  // --- Load lineup parameters (expected-starts model) -------------------------
  let resolvedLineup: Any = null;
  if (bundle.lineupConfig && (bundle.lineupConfig as Record<string, unknown>).schema === "lineup-parameters-config/2") {
    resolvedLineup = ValueModel.resolveLineupParameters(bundle.lineupConfig, m.lineupArgs);
  }

  // JEG-1031: the pipeline setting is the mapped league (roster shape, shares, bench override).
  return {
    setting: m.setting,
    players: playerMap,
    sources,
    included,
    hidden: hiddenKeys,
    lineup: resolvedLineup,
    week: info,
    unpaired,
  };
}

/** sources_excluded: the run's excluded sources, an unpaired one with the page's "no prior week" reason (JEG-1390). */
export function excludedSources(pipeline: Any, input: { unpaired?: Record<string, string> }) {
  return ((pipeline.excluded ?? []) as Any[]).map((e) => ({ key: e.key, reason: input.unpaired?.[e.key] ?? e.reason }));
}

/** Parse a `week` request value: null when absent, a number when it is an integer 1-22, else NaN. */
export function parseWeek(raw: unknown): number | null {
  if (raw === undefined || raw === null || raw === "") return null;
  const n = typeof raw === "number" ? raw : /^\s*\d+\s*$/.test(String(raw)) ? Number(raw) : NaN;
  return Number.isInteger(n) && n >= 1 && n <= 22 ? n : NaN;
}
