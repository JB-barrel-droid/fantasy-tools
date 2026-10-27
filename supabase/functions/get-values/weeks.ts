// JEG-1156 / JEG-1157: which week of trade charts DDF Value uses, and the label that says so.
// Pure functions, no Deno APIs, so node tests import this file directly (as league.ts).
//
// Mirrors app/trade-value-chart/assets/product-data.js buildSourceFreshness() and curve-widget.js
// compositeKeyOlderWeek(); tests/node/week_fallback_check.mjs fails if the two disagree.
//
// The rule (Jeremy, 2026-10-27, option A): the values week is the newest week any weekly chart has
// published, capped at the content week. A chart older than the values week is left out ("not yet
// published for week N"). When no chart has reached the content week yet (the Tuesday flip, before
// publishers post), the values week is the latest published one and the response says so:
// "Week 7 values, week 8 not published yet". Once a current-week chart lands, the normal rule returns.

const CONTENT_WEEK_1_START_UTC = Date.UTC(2026, 8, 8); // Tue 2026-09-08 (pipelines/nfl_week.py)
const CONTENT_WEEK_MAX = 18;
const DAY_MS = 86400000;

// Weekly chart sources (curve-widget.js WEEKED_SOURCE_KEYS base set).
export const WEEKED_SOURCES = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs"]);

export function isoDay(v: unknown): string | null {
  if (!v || typeof v !== "string") return null;
  const m = v.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

export function contentWeekForDay(day: string | null): number | null {
  const iso = isoDay(day);
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  const days = Math.round((Date.UTC(y, m - 1, d) - CONTENT_WEEK_1_START_UTC) / DAY_MS);
  if (days < 0) return 1;
  return Math.min(Math.max(Math.floor(days / 7) + 1, 1), CONTENT_WEEK_MAX);
}

// The New York calendar day of `now` (the page's todayIsoDay).
export function todayIso(now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(now);
  } catch {
    return now.toISOString().slice(0, 10);
  }
}

function parseWeekLabel(value: unknown): number | null {
  const m = String(value || "").match(/week\s*(\d+)|wk\s*(\d+)/i);
  return m ? Number(m[1] || m[2]) : null;
}

// deno-lint-ignore no-explicit-any
export function sourceVintage(meta: any): { week: number | null; basis: string | null } {
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

// The reader-facing values-week line (same words as product-data.js valuesWeekLabel).
export function valuesWeekLabel(valuesWeek: number | null, currentWeek: number | null): string {
  if (valuesWeek === null) return "No trade chart published yet";
  if (currentWeek !== null && valuesWeek < currentWeek) {
    return `Week ${valuesWeek} values, week ${currentWeek} not published yet`;
  }
  return `Week ${valuesWeek} values`;
}

export interface WeekPlan {
  today: string;
  current_week: number | null;
  values_week: number | null;
  fallback: boolean;
  label: string;
  weeks: Record<string, number | null>;
  // Weekly charts older than the values week, with the reason they are left out.
  not_published: Array<{ key: string; week: number | null; reason: string }>;
  // Weekly charts used from an earlier week than the content week (the fallback).
  fallback_charts: Array<{ key: string; week: number; reason: string }>;
}

// deno-lint-ignore no-explicit-any
export function chartWeekPlan(sources: Record<string, any> | null | undefined, keys: string[], today: string): WeekPlan {
  const src = sources && typeof sources === "object" ? sources : {};
  const currentWeek = contentWeekForDay(today);
  const weeks: Record<string, number | null> = {};
  for (const key of keys) {
    if (!src[key]) continue;
    weeks[key] = sourceVintage(src[key]).week;
  }
  const weeklyWeeks = Object.entries(weeks)
    .filter(([key, week]) => WEEKED_SOURCES.has(key) && week !== null)
    .map(([, week]) => week as number);
  const valuesWeek = weeklyWeeks.length ? Math.min(Math.max(...weeklyWeeks), currentWeek ?? Infinity) : null;
  const fallback = valuesWeek !== null && currentWeek !== null && valuesWeek < currentWeek;
  const notPublished: WeekPlan["not_published"] = [];
  const fallbackCharts: WeekPlan["fallback_charts"] = [];
  // With no weekly chart dated at all, the content week is the bar (the old rule).
  const bar = valuesWeek ?? currentWeek;
  for (const [key, week] of Object.entries(weeks)) {
    if (!WEEKED_SOURCES.has(key) || week === null || bar === null) continue;
    if (week < bar) {
      notPublished.push({ key, week, reason: `not yet published for week ${bar}; latest is week ${week}` });
    } else if (fallback) {
      fallbackCharts.push({ key, week, reason: `week ${currentWeek} not published yet; using its week ${week} chart` });
    }
  }
  return {
    today,
    current_week: currentWeek,
    values_week: valuesWeek,
    fallback,
    label: valuesWeekLabel(valuesWeek, currentWeek),
    weeks,
    not_published: notPublished,
    fallback_charts: fallbackCharts,
  };
}
