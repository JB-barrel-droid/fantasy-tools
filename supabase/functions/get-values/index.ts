// JEG-616 step 4: agent-callable values endpoint (Supabase edge function).
//
// Loads the published value-model.js (pure, no DOM) and the live bundle
// (comparison-sources-data.json + players-data from index.html), runs
// ValueModel.runValuePipeline() with the caller's league settings, and
// returns the same numbers the site shows.
//
// JEG-1179: the week priced is the site's default week (ValueModel.weekState over the published week
// history) or the `week` the caller asks for; the input building is in pipeline.ts, shared with the
// parity runner (tests/_edge_pipeline_runner.cjs).
//
// JEG-1225: an optional value basis and player overrides (`basis`, `ov`), in the text a share link carries. They
// are read by the site's own app/v2/ddf-value-link.js (loaded from the published site like value-model.js) and
// applied as the site applies them (value-context.ts), so a chat prices a pasted link the way the site does.
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
const HISTORY_INDEX_URL = `${SITE_ORIGIN}/assets/history/index.json`;
const VALUE_LINK_URL = `${SITE_ORIGIN}/v2/ddf-value-link.js`;

import { type League, type LineupDefaults, leagueKey, mapLeague } from "./league.ts";
import { auditBlock, type Include, parseIncludes, priorBlock, seriesBlock } from "./analysis.ts";
import {
  type Bundle,
  buildPipelineInput,
  type HistoryData,
  parseWeek,
  planWeek,
  todayIso,
  type WeekInfo,
} from "./pipeline.ts";
import {
  applyOverrides, basisConfigOf, basisShortfall, canReadStrictly, checkBounds, contextKey, overrideSeries, readValueContext,
  type ValueContext,
} from "./value-context.ts";
import { computeLimiter, sharedCheck } from "./rate-limit.ts";

// --- In-memory cache (lives for the function instance's lifetime) ----------

interface CachedBundle extends Bundle {
  meta: Record<string, unknown>;
  history: HistoryData | null;
  /** The site's share-link value reader (DDFValueLink), or null when the site does not publish it yet. */
  // deno-lint-ignore no-explicit-any
  valueLink: any | null;
  loadedAt: number;
}

let cached: CachedBundle | null = null;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

// JEG-1179: the week history the page reads (assets/history/index.json), so the default week and the
// week view match the page. Optional: without it the calendar rule applies, as on the page.
async function loadHistoryIndex(): Promise<HistoryData | null> {
  try {
    const res = await fetch(HISTORY_INDEX_URL);
    if (!res.ok) return null;
    return { index: await res.json(), docs: {} };
  } catch {
    return null;
  }
}

// One saved week's document (assets/history/week-<N>.json), read only when the priced week needs it
// (a source serving a later week is priced on its saved copy of this week). A failed read leaves the
// week without the document, so those sources are named in missing_sources.
async function loadHistoryDoc(bundle: CachedBundle, week: number): Promise<void> {
  const history = bundle.history;
  if (!history || history.docs[String(week)]) return;
  const file = history.index?.weeks?.[String(week)]?.file;
  if (typeof file !== "string" || !/^[\w./-]+\.json$/.test(file) || file.includes("..")) return;
  try {
    const res = await fetch(`${SITE_ORIGIN}/${file.replace(/^\/+/, "")}`);
    if (!res.ok) return;
    const doc = await res.json();
    if (doc?.week === week) history.docs[String(week)] = doc;
  } catch {
    // Left unloaded: the sources that needed it are reported missing for this week.
  }
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

  // Fetch bundle, page, lineup parameters, the week history index and the link reader in parallel.
  const [bundleResponse, pageResponse, lpResponse, history, valueLink] = await Promise.all([
    fetch(BUNDLE_URL),
    fetch(PAGE_URL),
    fetch(LINEUP_PARAMS_URL).catch(() => null),
    loadHistoryIndex(),
    loadValueLink(evalFn),
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
    history,
    valueLink,
    loadedAt: Date.now(),
  };
  return cached;
}

// JEG-1225: the site's share-link value reader (app/v2/ddf-value-link.js, published at /v2/). Optional: a site
// that does not publish it yet still answers every request without a basis or overrides.
// deno-lint-ignore no-explicit-any
async function loadValueLink(evalFn: (src: string) => unknown): Promise<any | null> {
  try {
    const res = await fetch(VALUE_LINK_URL);
    if (!res.ok) return null;
    evalFn(await res.text());
    // deno-lint-ignore no-explicit-any
    const link = (globalThis as any).DDFValueLink;
    return link && typeof link.readValueContext === "function" ? link : null;
  } catch {
    return null;
  }
}

// JEG-1029: the opt-in analysis blocks (analysis.ts). prior needs the week before's saved document.
async function addAnalysis(
  // deno-lint-ignore no-explicit-any
  body: any, includes: Set<Include>, bundle: CachedBundle, input: any, pipeline: any,
  plan: { week: number | null; served: Record<string, number | null> }, scoring: string,
  context: ValueContext = { basis: null, overrides: {}, custom: false },
): Promise<void> {
  // JEG-1225: the DDF Value series carries the caller's overrides, so it agrees with players[].value.
  if (includes.has("series")) {
    body.series = overrideSeries(seriesBlock(pipeline, input.hidden ?? []),
      applyOverrides(bundle.ValueModel, pipeline, context));
  }
  if (includes.has("prior")) {
    if (Number.isInteger(plan.week)) await loadHistoryDoc(bundle, (plan.week as number) - 1);
    body.prior = priorBlock(bundle, input, pipeline, plan.week, plan.served ?? {}, scoring);
  }
  if (includes.has("audit")) body.audit = auditBlock(bundle, pipeline, body.sources_excluded);
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
  week: WeekInfo | null = null,
  // deno-lint-ignore no-explicit-any
  ValueModel: any = null,
  context: ValueContext = { basis: null, overrides: {}, custom: false },
) {
  const rows = pipeline.rows || {};
  // JEG-1225: DDF Value after the caller's overrides (the pipeline's own value when there are none).
  const own = applyOverrides(ValueModel, pipeline, context);
  // deno-lint-ignore no-explicit-any
  const values: any[] = [];

  for (const [pk, row] of Object.entries(rows)) {
    // deno-lint-ignore no-explicit-any
    const r = row as any;
    const player = playerMap[Number(pk)];
    if (!player) continue;

    // DDF blended value (the headline number), after the caller's override if any.
    const ddfVersions = r.ddfByVersion;
    const rowValue = own.values[pk];
    const blended = rowValue?.value;
    if (typeof blended !== "number" || !Number.isFinite(blended)) continue;

    // deno-lint-ignore no-explicit-any
    const entry: any = {
      player_key: Number(pk),
      name: player.name,
      pos: player.pos,
      value: Math.round(blended * 10) / 10,
      tier: r.tier ?? 0,
    };
    if (rowValue.override !== undefined) {
      const pv = rowValue.pipeline_value;
      entry.override = rowValue.override;
      entry.pipeline_value = typeof pv === "number" && Number.isFinite(pv) ? Math.round(pv * 10) / 10 : null;
    }

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
    // JEG-1179: the week these values are for. missing_sources: DDF Value sources at this setting that
    // have not published this week; they are left out, never filled from another week.
    week: week?.week ?? null,
    default_week: week?.default_week ?? null,
    weeks: week?.weeks ?? [],
    missing_sources: week?.missing_sources ?? [],
    // JEG-1225: the basis DDF Value follows (null = our methodology) and the overrides applied.
    value_context: {
      basis: context.basis,
      basis_applied: context.basis ? Boolean(pipeline.basis?.applied) : true,
      basis_members: context.basis ? [...(pipeline.basis?.members ?? [])] : [],
      basis_fell_back_to_default: Boolean(context.basis && pipeline.basis?.fellBackToDefault),
      overrides: context.overrides,
      overrides_applied: own.applied.length,
      overrides_not_priced: own.not_priced.map(Number),
    },
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
// JEG-1061: this limiter is a SOFT GUARD ONLY, not a real per-client limit.
// The buckets live in a Map in this function instance's memory: the counts
// reset whenever the instance recycles and are never shared across instances,
// so under load each instance keeps its own count and the "limit" is really
// per instance. The key is the first entry of the x-forwarded-for header
// (falling back to cf-connecting-ip), which the client can set to anything,
// so a caller can mint a fresh bucket by changing one header. All this does
// is blunt a naive burst against one warm instance. That is accepted on
// purpose: the function stores no data, so abuse costs CPU only (about
// 0.3 s per fresh custom league; the answer cache below is per-instance too).
// A shared or unforgeable-key limiter would be a separate, deliberate
// change — do not read the numbers below as a guarantee.
// JEG-1061 follow-up: the compute bucket can be counted across instances in
// Postgres (rate-limit.ts), off unless DDF_SHARED_RATE_LIMIT=1; off, or when the
// database does not answer, this in-memory count decides as before.
const rateBuckets = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 30; // requests per window
const RATE_WINDOW_MS = 60_000; // 1 minute
// JEG-1031: a custom league is a fresh engine run (about 0.8 s warm), so it gets a tighter budget.
const COMPUTE_RATE_LIMIT = 10;
// Answers kept in memory only: a few entries, the same 5-minute TTL. Nothing is written anywhere.
const ANSWER_CACHE_MAX = 6;
const answerCache = new Map<string, { at: number; body: unknown; status?: number }>();

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

const checkCompute = computeLimiter(checkRate, sharedCheck({ env: (name) => Deno.env.get(name) }),
  (fields) => logEvent(fields));

// JEG-1061: one structured log line per fresh custom compute and per 429, so the soft limiter can be
// measured (contract: tests/node/jeg_1061_logging_contract.mjs). Settings only: no IP, header, token or
// player data.
function logEvent(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
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
    logEvent({ event: "get_values.rate_limited", limit: "general", max: RATE_LIMIT, window_s: RATE_WINDOW_MS / 1000 });
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
    let rawInclude: unknown = null;
    let league: League = {};
    let rawLeague: unknown = null;
    let rawWeek: unknown = null;
    let rawBasis: unknown = null;
    let rawOv: unknown = null;

    if (req.method === "POST") {
      const body = await req.json();
      scoring = body.scoring || scoring;
      teams = Number(body.teams) || teams;
      superflex = Number(body.superflex) || 0;
      rawInclude = body.include ?? null;
      rawLeague = body.league ?? null;
      rawWeek = body.week ?? null;
      rawBasis = body.basis ?? null;
      rawOv = body.ov ?? null;
    } else {
      const url = new URL(req.url);
      scoring = url.searchParams.get("scoring") || scoring;
      teams = Number(url.searchParams.get("teams")) || teams;
      superflex = Number(url.searchParams.get("superflex")) || 0;
      rawInclude = url.searchParams.get("include");
      rawLeague = url.searchParams.get("league");
      rawWeek = url.searchParams.get("week");
      rawBasis = url.searchParams.get("basis");
      rawOv = url.searchParams.get("ov");
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
    // JEG-1029: include is a comma list (charts, series, prior, audit); absent = the plain answer.
    const parsedInclude = parseIncludes(rawInclude);
    if (parsedInclude.error) {
      return Response.json({ error: parsedInclude.error }, { status: 400, headers: cors });
    }
    const includes = parsedInclude.includes;
    const includeCharts = includes.has("charts");
    // JEG-1179: optional week (N or N+1 during a transition); absent = the site's default week.
    const requestedWeek = parseWeek(rawWeek);
    if (Number.isNaN(requestedWeek)) {
      return Response.json(
        { error: `invalid week: ${rawWeek}. Must be a whole number from 1 to 22, or left out for the default week` },
        { status: 400, headers: cors },
      );
    }
    // The top-level fields are the base; the league section adds what they cannot say.
    const merged: League = { ...league, scoring, teams };
    if (superflex && merged.roster?.SUPERFLEX === undefined) {
      merged.roster = { ...(merged.roster ?? {}), SUPERFLEX: 1 };
    }

    // JEG-1288: basis and ov past their size bounds are refused before anything is loaded, read or cached.
    const bounds = checkBounds(rawBasis, rawOv);
    if (bounds && !bounds.ok) {
      return Response.json({ error: bounds.error, code: bounds.code }, { status: bounds.status, headers: cors });
    }

    // Load bundle, map the league, and run the pipeline (answers are kept in memory only).
    const bundle = await loadBundle();
    // JEG-1225: the caller's basis and overrides, as a share link writes them. Unreadable is an error, never ours,
    // and (JEG-1288) a part with anything unreadable in it is refused whole.
    let context: ValueContext = { basis: null, overrides: {}, custom: false };
    if ((rawBasis !== null && rawBasis !== "") || (rawOv !== null && rawOv !== "")) {
      if (!canReadStrictly(bundle.valueLink)) {
        return Response.json(
          { error: "basis and ov are not available yet: the site does not publish its link reader", code: "value_context_unavailable" },
          { status: 503, headers: cors },
        );
      }
      const read = readValueContext(bundle.valueLink, rawBasis, rawOv);
      if (!read.ok) {
        return Response.json(
          { error: read.error, code: read.code, ...(read.unread ? { unread: read.unread } : {}) },
          { status: read.status, headers: cors },
        );
      }
      context = read.context;
    }
    const mapped = mapLeague(
      merged,
      bundle.lineupConfig as { defaults?: LineupDefaults; content_week?: number | null } | null,
    );
    // The week: the site's default (ValueModel.weekState) or the one asked for. A week with no
    // published sources is an error that names the weeks there are, never an empty list.
    const plan = planWeek(bundle, mapped, requestedWeek, Deno.env.get("DDF_TODAY") || todayIso());
    if (!plan.ok) {
      return Response.json(
        { error: plan.error, code: "week_unavailable", weeks: plan.weeks, default_week: plan.default_week },
        { status: 400, headers: cors },
      );
    }
    const includeKey = [...includes].sort().join(",");
    const key = `${leagueKey(mapped)}${includeKey ? `|${includeKey}` : ""}|wk=${plan.week}${contextKey(context)}`;
    let response = answerCache.get(key);
    if (!response || Date.now() - response.at > CACHE_TTL_MS) {
      // A custom league or a link's value context is a fresh engine run: limited and logged as compute.
      const fresh = Boolean(mapped.custom.length || context.custom);
      const settings = { scoring: mapped.scoring, teams: mapped.teams, superflex: mapped.setting.superflex,
        custom: mapped.custom, charts: includeCharts, week: plan.week };
      if (fresh && !(await checkCompute(`compute:${ip}`, COMPUTE_RATE_LIMIT, RATE_WINDOW_MS / 1000))) {
        logEvent({ event: "get_values.rate_limited", limit: "compute", max: COMPUTE_RATE_LIMIT,
          window_s: RATE_WINDOW_MS / 1000, ...settings });
        return Response.json(
          { error: "rate limited", retry_after_seconds: 60 },
          { status: 429, headers: cors },
        );
      }
      const started = performance.now();
      if (plan.docWeek !== null) await loadHistoryDoc(bundle, plan.docWeek);
      const input = { ...buildPipelineInput(bundle, mapped, plan), basisConfig: basisConfigOf(context) };
      if (requestedWeek !== null && !input.week.sources.length) {
        return Response.json(
          {
            error: `Week ${requestedWeek} has no published sources at this setting (missing: ` +
              `${input.week.missing_sources.join(", ") || "none"}). Weeks available: ${input.week.weeks.join(", ")} ` +
              `(default ${input.week.default_week}).`,
            code: "week_unavailable", weeks: input.week.weeks, default_week: input.week.default_week,
          },
          { status: 400, headers: cors },
        );
      }
      // deno-lint-ignore no-explicit-any
      const pipeline = (bundle.ValueModel as any).runValuePipeline(input);
      // JEG-1288: a basis source that is not available here is refused, never priced under part of the basis or the
      // fallback. The refusal is cached like an answer, so asking again costs no new run.
      const shortfall = basisShortfall(context, pipeline, input);
      if (shortfall) {
        response = {
          at: Date.now(),
          status: 422,
          body: {
            error: `basis ${shortfall.unavailable.join(", ")} ${shortfall.unavailable.length === 1 ? "is" : "are"} not ` +
              `available at this setting and week, so these values cannot follow the basis asked for. Available: ` +
              `${shortfall.available.join(", ") || "none"}.`,
            code: "basis_unavailable",
            ...shortfall,
          },
        };
      } else {
        const body = formatResponse(
          pipeline, input.players, bundle.meta, mapped.scoring, mapped.teams, mapped.setting.superflex, includeCharts,
          mapped.custom, input.week, bundle.ValueModel, context,
        );
        await addAnalysis(body, includes, bundle, input, pipeline, plan, mapped.scoring, context);
        response = { at: Date.now(), body };
      }
      if (answerCache.size >= ANSWER_CACHE_MAX) answerCache.delete(answerCache.keys().next().value as string);
      answerCache.set(key, response);
      if (fresh) logEvent({ event: "get_values.compute", ...settings, ms: Math.round(performance.now() - started) });
    }

    if (response.status && response.status !== 200) {
      return Response.json(response.body, { status: response.status, headers: cors });
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
