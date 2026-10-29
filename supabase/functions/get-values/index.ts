// JEG-616 step 4: agent-callable values endpoint (Supabase edge function).
//
// Loads the published value-model.js (pure, no DOM) and the live bundle
// (comparison-sources-data.json + players-data from index.html), runs
// ValueModel.runValuePipeline() with the caller's league settings, and
// returns the same numbers the site shows.
//
// No accounts, no keys, no schema change. Reads only the published bundle.
// Rate-limited by Supabase's built-in edge function limits.
//
// Deploy: supabase functions deploy get-values --no-verify-jwt

// Published site the function reads from. The datadrivenfootball.com domain
// does not resolve yet (checked 2026-10-19), so default to the Pages URL and
// let a DDF_SITE_ORIGIN function secret override it once the domain is live.
const SITE_ORIGIN = (Deno.env.get("DDF_SITE_ORIGIN") ||
  "https://jb-barrel-droid.github.io/fantasy-tools").replace(/\/+$/, "");
const BUNDLE_URL = `${SITE_ORIGIN}/assets/comparison-sources-data.json`;
const PAGE_URL = `${SITE_ORIGIN}/`;
const VALUE_MODEL_URL = `${SITE_ORIGIN}/assets/value-model.js`;
const LINEUP_PARAMS_URL = `${SITE_ORIGIN}/assets/lineup-parameters.json`;

import { type League, type LeagueInputs, type LineupDefaults, leagueKey, mapLeague } from "./league.ts";

// --- In-memory cache (lives for the function instance's lifetime) ----------

interface CachedBundle {
  detail: Record<string, unknown>;
  players: Array<Record<string, unknown>>;
  meta: Record<string, unknown>;
  ValueModel: Record<string, unknown>;
  lineupConfig: Record<string, unknown> | null;
  loadedAt: number;
}

let cached: CachedBundle | null = null;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

// Pipeline source keys (must match curve-widget.js PIPELINE_SOURCE_KEYS).
const PIPELINE_SOURCE_KEYS = [
  "espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs",
];
const PROJECTION_SOURCE_KEYS = ["espn", "cbsros", "razzball"];
const PPG_FIELD_OF: Record<string, string> = {
  espn: "espn_ppg",
  cbsros: "cbsros_ppg",
  razzball: "rz_ppg",
};

// Scoring field from scoring name.
function scoringField(scoring: string): string {
  return scoring === "ppr" ? "ppr" : scoring === "half_ppr" ? "half_ppr" : "standard";
}

// Replicates product-data.js espnProjectsZero(): ESPN considers this player
// listed at 0 (injured/out) even though espn_ppg is absent.
// deno-lint-ignore no-explicit-any
function espnProjectsZero(player: any): boolean {
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

function contentWeekForDay(day: string | null): number | null {
  if (!day) return null;
  const [y, m, d] = day.split("-").map(Number);
  const days = Math.round((Date.UTC(y, m - 1, d) - CONTENT_WEEK_1_START_UTC) / DAY_MS);
  if (days < 0) return 1;
  return Math.min(Math.max(Math.floor(days / 7) + 1, 1), CONTENT_WEEK_MAX);
}

function todayIso(): string {
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

// deno-lint-ignore no-explicit-any
function sourceVintage(meta: any): { week: number | null; basis: string | null } {
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

// deno-lint-ignore no-explicit-any
function sectionHold(sourceSection: any): { reason: string; hidden: boolean } | null {
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

// Load the bundle from the live site.
async function loadBundle(): Promise<CachedBundle> {
  if (cached && Date.now() - cached.loadedAt < CACHE_TTL_MS) return cached;

  // Fetch value-model.js and eval it to get ValueModel on globalThis.
  const vmResponse = await fetch(VALUE_MODEL_URL);
  if (!vmResponse.ok) throw new Error(`value-model.js fetch failed: ${vmResponse.status}`);
  const vmSource = await vmResponse.text();

  // Create a clean scope and eval. value-model.js assigns to globalThis.ValueModel.
  // deno-lint-ignore no-eval
  const evalFn = eval;
  evalFn(vmSource);
  // deno-lint-ignore no-explicit-any
  const ValueModel = (globalThis as any).ValueModel;
  if (!ValueModel || typeof ValueModel.runValuePipeline !== "function") {
    throw new Error("ValueModel.runValuePipeline not found after loading value-model.js");
  }

  // Fetch bundle, page, and lineup parameters in parallel.
  const [bundleResponse, pageResponse, lpResponse] = await Promise.all([
    fetch(BUNDLE_URL),
    fetch(PAGE_URL),
    fetch(LINEUP_PARAMS_URL).catch(() => null),
  ]);
  if (!bundleResponse.ok) throw new Error(`bundle fetch failed: ${bundleResponse.status}`);
  if (!pageResponse.ok) throw new Error(`page fetch failed: ${pageResponse.status}`);

  const detail = await bundleResponse.json();
  const html = await pageResponse.text();

  // Extract players-data from the inline island.
  const match = html.match(/id="players-data"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) throw new Error("players-data island not found in page");
  const playersDoc = JSON.parse(match[1]);

  // Lineup parameters (optional; falls back to slices mode if missing).
  let lineupConfig: Record<string, unknown> | null = null;
  if (lpResponse && lpResponse.ok) {
    try { lineupConfig = await lpResponse.json(); } catch { /* ignore */ }
  }

  cached = {
    detail,
    players: playersDoc.players,
    meta: playersDoc.meta,
    ValueModel,
    lineupConfig,
    loadedAt: Date.now(),
  };
  return cached;
}

// Build the pipeline input for the given settings.
function buildPipelineInput(bundle: CachedBundle, m: LeagueInputs) {
  const { scoring, teams } = m;
  const superflex = m.setting.superflex;
  // deno-lint-ignore no-explicit-any
  const detail = bundle.detail as any;
  const players = bundle.players;
  // deno-lint-ignore no-explicit-any
  const ValueModel = bundle.ValueModel as any;
  const field = scoringField(scoring);
  // The engine page always looks up chart combos at qb1 (product-data.js
  // qbVariant: "qb1"). Superflex values are overlaid separately via
  // native_superflex, so the combo key is always qbSlots=1.
  const comboQbSlots = 1;

  // Build player map: player_key -> {pos, name}.
  const playerMap: Record<number, { pos: string; name: string }> = {};
  for (const p of players) {
    const pk = p.player_key as number;
    playerMap[pk] = { pos: p.pos as string, name: p.name as string };
  }

  // Source validation from the detail. Values are strings like "live", "stale".
  const sourceValidation = detail.source_validation as
    Record<string, string> | undefined;

  // --- Source freshness / eligibility (mirrors curve-widget.js) ---------------
  const currentContentWeek = contentWeekForDay(todayIso());

  // Build freshness per source.
  const freshnessRows: Record<string, { week: number | null; status: string; isWeekly: boolean }> = {};
  for (const key of PIPELINE_SOURCE_KEYS) {
    const sourceMeta = detail.sources?.[key];
    if (!sourceMeta) continue;
    const vintage = sourceVintage(sourceMeta);
    const isWeekly = WEEKED_SOURCES.has(key);
    const status = vintage.week === null ? "unknown"
      : (vintage.week >= (currentContentWeek ?? 0) ? "current" : "older");
    freshnessRows[key] = { week: vintage.week, status, isWeekly };
  }

  // first_load_reference_week: newest vintage among weekly sources, capped at current week.
  const weeklyWeeks = Object.entries(freshnessRows)
    .filter(([, r]) => r.isWeekly && r.week !== null)
    .map(([, r]) => r.week!);
  const referenceWeek = weeklyWeeks.length
    ? Math.min(Math.max(...weeklyWeeks), currentContentWeek ?? 0)
    : null;

  // first_load_excluded: weekly sources older than reference week.
  const firstLoadExcluded = new Set<string>();
  for (const [key, row] of Object.entries(freshnessRows)) {
    if (row.isWeekly && referenceWeek !== null && row.week !== null && row.week < referenceWeek) {
      firstLoadExcluded.add(key);
    }
  }

  // Build sources: for each pipeline source, extract native values.
  const sources: Record<string, unknown> = {};
  const included: string[] = [];
  const hiddenKeys: string[] = [];

  for (const key of PIPELINE_SOURCE_KEYS) {
    const family = PROJECTION_SOURCE_KEYS.includes(key) ? "projection" : "chart";
    const sourceSection = detail.sources?.[key];

    // Source hold (validationHold, promotionHold on source section).
    const hold = sectionHold(sourceSection);

    // Source validation status (string, e.g. "live", "stale").
    const svStatus = sourceValidation?.[key];
    const isValidationHeld = svStatus !== undefined && svStatus !== "live";

    // Older week: a weekly chart behind the newest published week (the first-load rule). The
    // calendar's week is not the test: on the Tuesday flip every chart is still on last week, and
    // judging them against the calendar dropped them all and priced nobody (Oct 27 2026).
    const isOlderWeek = firstLoadExcluded.has(key);

    // JEG-610 item 2: divergence 'exclude' resolution -> held semantics.
    const snapshot = detail.snapshot as Record<string, unknown> | undefined;
    const divergenceExclusions = (snapshot && Array.isArray(snapshot.divergence_exclusions))
      ? snapshot.divergence_exclusions as string[] : [];
    const isDivergenceExcluded = divergenceExclusions.indexOf(key) !== -1;

    // sourceMissingFromData: no source section at all.
    if (!sourceSection) continue;

    // Not yet published for current week: excluded (unless held or divergence-excluded).
    if (isOlderWeek && !hold && !isValidationHeld && !isDivergenceExcluded) continue;

    let values: Record<string, number>;

    if (family === "chart") {
      // Chart source: read saved native values from the combo.
      const comboKeyStr = ValueModel.sourceComboKey(key, scoring, 12, comboQbSlots);
      const combos = sourceSection?.combos as Record<string, Record<string, unknown>> | undefined;
      const combo = comboKeyStr ? combos?.[comboKeyStr] : null;
      if (!combo || !(combo as Record<string, unknown>).native) continue;
      values = {};
      const native = (combo as Record<string, unknown>).native as Record<string, number>;
      const pkMap = detail.player_keys as Record<string, number>;
      for (const [sourceId, val] of Object.entries(native)) {
        const playerKey = pkMap?.[sourceId];
        if (playerKey !== undefined && Number.isFinite(val)) {
          values[playerKey] = val;
        }
      }
      if (superflex && (combo as Record<string, unknown>).native_superflex) {
        const sfNative = (combo as Record<string, unknown>).native_superflex as Record<string, number>;
        for (const [sourceId, val] of Object.entries(sfNative)) {
          const playerKey = pkMap?.[sourceId];
          if (playerKey !== undefined && Number.isFinite(val)) {
            values[playerKey] = val;
          }
        }
      }
    } else {
      // Projection source: read per-game points from players.
      values = {};
      const ppgField = PPG_FIELD_OF[key];
      for (const p of players) {
        const pk = p.player_key as number;
        // ESPN zero handling: players ESPN lists at 0 (ineligible/zeroed).
        if (key === "espn" && espnProjectsZero(p) && !p.espn_ppg) {
          values[pk] = 0;
          continue;
        }
        const ppgObj = p[ppgField] as Record<string, number> | undefined;
        const ppg = ppgObj?.[field];
        if (ppg !== null && ppg !== undefined && Number.isFinite(ppg)) {
          values[pk] = ppg;
        }
      }
    }

    if (Object.keys(values).length === 0) continue;

    sources[key] = { family, status: "included", values, label: key };
    included.push(key);

    // Mark as hidden if red-held, validation-held, or divergence-excluded.
    // JEG-726 / JEG-787: amber holds label the source but do NOT hide it.
    if ((hold && hold.hidden) || isValidationHeld || isDivergenceExcluded) {
      hiddenKeys.push(key);
    }
  }

  // --- Load lineup parameters (expected-starts model) -------------------------
  // deno-lint-ignore no-explicit-any
  let resolvedLineup: any = null;
  // The edge function fetches lineup-parameters.json from the site alongside the bundle.
  if (bundle.lineupConfig &&
      (bundle.lineupConfig as Record<string, unknown>).schema === "lineup-parameters-config/2") {
    // deno-lint-ignore no-explicit-any
    const lp = bundle.lineupConfig as any;
    resolvedLineup = ValueModel.resolveLineupParameters(lp, m.lineupArgs);
  }

  // JEG-1031: the pipeline setting is the mapped league (roster shape, shares, bench override).
  const setting = m.setting;

  return {
    setting,
    players: playerMap,
    sources,
    included,
    hidden: hiddenKeys,
    lineup: resolvedLineup,
  };
}

// The chart source keys the finder compares (must match finder.js CHART_KEYS).
const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];

// Format pipeline output for the API response.
function formatResponse(
  // deno-lint-ignore no-explicit-any
  pipeline: any,
  // deno-lint-ignore no-explicit-any
  playerMap: Record<number, { pos: string; name: string }>,
  // deno-lint-ignore no-explicit-any
  meta: Record<string, unknown>,
  scoring: string,
  teams: number,
  superflex: number,
  includeCharts = false,
  custom: string[] = [],
) {
  const rows = pipeline.rows || {};
  // deno-lint-ignore no-explicit-any
  const values: any[] = [];

  for (const [pk, row] of Object.entries(rows)) {
    // deno-lint-ignore no-explicit-any
    const r = row as any;
    const player = playerMap[Number(pk)];
    if (!player) continue;

    // DDF blended value (the headline number).
    const ddfVersions = r.ddfByVersion;
    const blended = ddfVersions?.blended?.value;
    if (typeof blended !== "number" || !Number.isFinite(blended)) continue;

    // deno-lint-ignore no-explicit-any
    const entry: any = {
      player_key: Number(pk),
      name: player.name,
      pos: player.pos,
      value: Math.round(blended * 10) / 10,
      tier: r.tier ?? 0,
    };

    // include=charts: add per-chart values and DDF sub-versions so the finder
    // can check whether trade charts say the rival breaks even.
    // chart_values: each chart's Adjusted value (the inputs DDF Value averages).
    // chart_indexed: each chart's Indexed value, the market the other team
    // judges by (JEG-1129). The mean of the Adjusted values is DDF Value itself,
    // so the rival check must read chart_indexed.
    if (includeCharts) {
      const round1 = (v: unknown) => typeof v === "number" && Number.isFinite(v) ? Math.round(v * 10) / 10 : null;
      const cv: Record<string, number | null> = {};
      const ci: Record<string, number | null> = {};
      for (const ck of CHART_KEYS) {
        cv[ck] = round1(r.adjusted?.[ck]);
        ci[ck] = round1(r.indexed?.[ck]);
      }
      entry.chart_values = cv;
      entry.chart_indexed = ci;
      // DDF Value sub-versions (charts-only and projections-only) for noise estimation.
      const charts = ddfVersions?.charts?.value;
      const projs = ddfVersions?.projections?.value;
      entry.ddf_value_charts = typeof charts === "number" && Number.isFinite(charts) ? Math.round(charts * 10) / 10 : null;
      entry.ddf_value_projections = typeof projs === "number" && Number.isFinite(projs) ? Math.round(projs * 10) / 10 : null;
    }

    values.push(entry);
  }

  // Sort by value descending.
  values.sort((a: { value: number }, b: { value: number }) => b.value - a.value);

  // include=charts: the engine's ES-14 bench-share readout (each position's bench tier as a
  // share of its DDF Value), the weights the finder's fit rule counts bench players at. The
  // connector reads these instead of rebuilding them (JEG-1115, Jeremy's pick B 2026-10-26).
  // input is the league's bench share, the page's fallback when the engine gives no overall.
  // deno-lint-ignore no-explicit-any
  let benchShare: any = undefined;
  if (includeCharts) {
    const share = (v: unknown) => typeof v === "number" && Number.isFinite(v) ? v : null;
    const r = pipeline.benchShare || {};
    benchShare = {
      QB: share(r.QB), RB: share(r.RB), WR: share(r.WR), TE: share(r.TE),
      overall: share(r.overall), input: share(pipeline.setting?.bench_share),
    };
  }

  return {
    attribution: `Data Driven Football — ${SITE_ORIGIN}/`,
    as_of: (meta as Record<string, string>).as_of || null,
    setting: { scoring, teams, superflex },
    league_custom: custom,
    players: values,
    ...(benchShare ? { bench_share: benchShare } : {}),
    sources_included: Object.keys(pipeline.sources || {}).filter(
      (k: string) => pipeline.sources[k]?.included !== false,
    ),
    sources_excluded: pipeline.excluded?.map(
      // deno-lint-ignore no-explicit-any
      (e: any) => ({ key: e.key, reason: e.reason }),
    ) || [],
  };
}

// --- Allowed origins for CORS -----------------------------------------------
const ALLOWED_ORIGINS = new Set([
  "https://datadrivenfootball.com",
  "https://jb-barrel-droid.github.io",
  "http://localhost:3000",
  "http://localhost:5173",
  "http://127.0.0.1:3000",
  "http://127.0.0.1:5173",
]);

function corsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get("origin") || "";
  const headers: Record<string, string> = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
  if (ALLOWED_ORIGINS.has(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return headers;
}

// --- Rate limiting (simple per-IP in-memory) --------------------------------
const rateBuckets = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 30; // requests per window
const RATE_WINDOW_MS = 60_000; // 1 minute
// JEG-1031: a custom league is a fresh engine run (about 0.8 s warm), so it gets a tighter budget.
const COMPUTE_RATE_LIMIT = 10;
// Answers kept in memory only: a few entries, the same 5-minute TTL. Nothing is written anywhere.
const ANSWER_CACHE_MAX = 6;
const answerCache = new Map<string, { at: number; body: unknown }>();

function checkRate(ip: string, limit = RATE_LIMIT): boolean {
  const now = Date.now();
  let bucket = rateBuckets.get(ip);
  if (!bucket || now >= bucket.resetAt) {
    bucket = { count: 0, resetAt: now + RATE_WINDOW_MS };
    rateBuckets.set(ip, bucket);
  }
  bucket.count++;
  return bucket.count <= limit;
}

// --- Serve ------------------------------------------------------------------

Deno.serve(async (req: Request) => {
  const cors = corsHeaders(req);

  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }

  // Rate limit.
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    req.headers.get("cf-connecting-ip") || "unknown";
  if (!checkRate(ip)) {
    return Response.json(
      { error: "rate limited", retry_after_seconds: 60 },
      { status: 429, headers: cors },
    );
  }

  try {
    // Parse parameters from GET query or POST body. `league` is the normalized DDF league section
    // (roster, shares, bso, inj, conf, weeks); scoring, teams and superflex still work on their own.
    let scoring = "ppr";
    let teams = 12;
    let superflex = 0;
    let includeCharts = false;
    let league: League = {};
    let rawLeague: unknown = null;

    if (req.method === "POST") {
      const body = await req.json();
      scoring = body.scoring || scoring;
      teams = Number(body.teams) || teams;
      superflex = Number(body.superflex) || 0;
      includeCharts = body.include === "charts";
      rawLeague = body.league ?? null;
    } else {
      const url = new URL(req.url);
      scoring = url.searchParams.get("scoring") || scoring;
      teams = Number(url.searchParams.get("teams")) || teams;
      superflex = Number(url.searchParams.get("superflex")) || 0;
      includeCharts = url.searchParams.get("include") === "charts";
      rawLeague = url.searchParams.get("league");
    }
    if (typeof rawLeague === "string" && rawLeague.length <= 2000) {
      try { rawLeague = JSON.parse(rawLeague); } catch { rawLeague = null; }
    }
    if (rawLeague && typeof rawLeague === "object" && !Array.isArray(rawLeague)) league = rawLeague as League;

    // Validate.
    const validScorings = ["standard", "half_ppr", "ppr"];
    if (!validScorings.includes(scoring)) {
      return Response.json(
        { error: `invalid scoring: ${scoring}. Must be one of: ${validScorings.join(", ")}` },
        { status: 400, headers: cors },
      );
    }
    const validTeams = [8, 10, 12, 14];
    if (!validTeams.includes(teams)) {
      return Response.json(
        { error: `invalid teams: ${teams}. Must be one of: ${validTeams.join(", ")}` },
        { status: 400, headers: cors },
      );
    }
    // The top-level fields are the base; the league section adds what they cannot say.
    const merged: League = { ...league, scoring, teams };
    if (superflex && merged.roster?.SUPERFLEX === undefined) {
      merged.roster = { ...(merged.roster ?? {}), SUPERFLEX: 1 };
    }

    // Load bundle, map the league, and run the pipeline (answers are kept in memory only).
    const bundle = await loadBundle();
    const mapped = mapLeague(
      merged,
      bundle.lineupConfig as { defaults?: LineupDefaults; content_week?: number | null } | null,
    );
    const key = leagueKey(mapped) + (includeCharts ? "|charts" : "");
    let response = answerCache.get(key);
    if (!response || Date.now() - response.at > CACHE_TTL_MS) {
      if (mapped.custom.length && !checkRate(`compute:${ip}`, COMPUTE_RATE_LIMIT)) {
        return Response.json(
          { error: "rate limited", retry_after_seconds: 60 },
          { status: 429, headers: cors },
        );
      }
      const input = buildPipelineInput(bundle, mapped);
      // deno-lint-ignore no-explicit-any
      const pipeline = (bundle.ValueModel as any).runValuePipeline(input);
      response = {
        at: Date.now(),
        body: formatResponse(
          pipeline, input.players, bundle.meta, mapped.scoring, mapped.teams, mapped.setting.superflex, includeCharts, mapped.custom,
        ),
      };
      if (answerCache.size >= ANSWER_CACHE_MAX) answerCache.delete(answerCache.keys().next().value as string);
      answerCache.set(key, response);
    }

    return Response.json(response.body, {
      status: 200,
      headers: { ...cors, "Cache-Control": "public, max-age=300" },
    });
  } catch (e) {
    console.error("get-values error:", e);
    return Response.json(
      { error: "internal error", message: String((e as Error).message) },
      { status: 500, headers: cors },
    );
  }
});
