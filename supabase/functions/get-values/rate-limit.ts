// JEG-1061: a compute limit that holds across get-values instances.
//
// The in-memory limiter in index.ts counts per function instance, so live traffic that spreads over
// several instances never reached the 10/min compute limit (2026-10-24 live check). This module keeps
// that limiter and adds an optional shared count in Postgres: one call to public.edge_rate_hit (migration
// supabase/migrations/jeg1061_shared_rate_limit_20261030.sql) per fresh custom-league compute, counted in
// one row per key and window for every instance.
//
// Two-way door:
// - Off unless the function secret DDF_SHARED_RATE_LIMIT is "1" (and SUPABASE_URL and
//   SUPABASE_SERVICE_ROLE_KEY are set, as Supabase sets them for every function). Off, nothing changes:
//   the in-memory count decides, exactly as before.
// - On, any failure of the shared call (missing function, error, timeout) falls back to the in-memory
//   count for that request and logs get_values.rate_limit_fallback, so a slow or missing database never
//   blocks a request. The in-memory count is fed on every request, on or off, and a request runs only when
//   both counts allow it, so the guard is never weaker than the old per-instance one.
// - The key leaves the function only as an HMAC-SHA-256 under the service role key, so the stored bucket
//   cannot be turned back into an IP by hashing every address.
// - The secret is read when an instance starts, so switching it off takes effect as instances recycle.
// The key is still the first x-forwarded-for entry, which a client can set; this fixes the per-instance
// count, not key forgery.

export type MemoryCheck = (key: string, limit: number) => boolean;
export type SharedCheck = (key: string, limit: number, windowSeconds: number) => Promise<boolean>;

export interface SharedOptions {
  env: (name: string) => string | undefined;
  fetchFn?: typeof fetch;
  timeoutMs?: number;
  log?: (fields: Record<string, unknown>) => void;
}

const DEFAULT_TIMEOUT_MS = 400;

async function hmacKey(secret: string, key: string): Promise<string> {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const bytes = await crypto.subtle.sign("HMAC", k, enc.encode(`get-values:${key}`));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** The shared check, or null when it is switched off or the function has no database credentials. */
export function sharedCheck(opts: SharedOptions): SharedCheck | null {
  if (opts.env("DDF_SHARED_RATE_LIMIT") !== "1") return null;
  const base = (opts.env("SUPABASE_URL") || "").replace(/\/+$/, "");
  const key = opts.env("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!base || !key) return null;
  const fetchFn = opts.fetchFn ?? fetch;
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return async (bucket, limit, windowSeconds) => {
    const res = await fetchFn(`${base}/rest/v1/rpc/edge_rate_hit`, {
      method: "POST",
      headers: { "content-type": "application/json", apikey: key, authorization: `Bearer ${key}` },
      body: JSON.stringify({ p_bucket: await hmacKey(key, bucket), p_limit: limit, p_window_s: windowSeconds }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) throw new Error(`edge_rate_hit ${res.status}`);
    const allowed = await res.json();
    if (typeof allowed !== "boolean") throw new Error("edge_rate_hit returned no boolean");
    return allowed;
  };
}

/**
 * The compute check: the shared count when it is on and answers, else the in-memory count.
 * Returns true when the request may run.
 */
export function computeLimiter(memory: MemoryCheck, shared: SharedCheck | null,
  log: (fields: Record<string, unknown>) => void = () => {}) {
  return async (key: string, limit: number, windowSeconds: number): Promise<boolean> => {
    // The local count always runs, so a database that answers and then fails falls back to a full count.
    const local = memory(key, limit);
    if (!shared || !local) return local;
    try {
      return await shared(key, limit, windowSeconds);
    } catch (e) {
      log({ event: "get_values.rate_limit_fallback", reason: String((e as Error).message || e).slice(0, 120) });
      return local;
    }
  };
}
