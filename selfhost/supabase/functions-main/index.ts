// Edge-runtime main service for the self-hosted relay (JEG-792).
//
// The cloud gateway enforces verify_jwt per function; the self-hosted edge
// runtime has no gateway of its own, so this router does it:
//
//   usatoday-fetch  verify_jwt = true (as deployed in the cloud, v3), and the
//                   token's role must be service_role. The public anon key is
//                   refused here AND by the function itself
//                   (GAP-USAT-RELAY-ANON). The function's own role check only
//                   decodes the claim, so the signature check below is what
//                   stops a forged token.
//   get-values      verify_jwt = false (supabase/config.toml, JEG-616).
//
// Any other path is 404. Each worker gets only the env vars it needs: the
// JWT secret never reaches a function. No external imports.

type FnSpec = { verifyJwt: boolean; requireRole?: string; env: string[] };

const FUNCTIONS: Record<string, FnSpec> = {
  "usatoday-fetch": {
    verifyJwt: true,
    requireRole: "service_role",
    env: ["SUPABASE_SERVICE_ROLE_KEY"],
  },
  "get-values": { verifyJwt: false, env: ["DDF_SITE_ORIGIN"] },
};

const JWT_SECRET = Deno.env.get("JWT_SECRET") ?? "";

function json(status: number, body: unknown): Response {
  return Response.json(body, { status });
}

function b64urlToBytes(s: string): Uint8Array {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

// HS256 verification with WebCrypto. Returns the payload, or null.
async function verifyHs256(token: string): Promise<Record<string, unknown> | null> {
  if (!JWT_SECRET) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const header = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[0])));
    if (header.alg !== "HS256") return null;
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(JWT_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"],
    );
    const ok = await crypto.subtle.verify(
      "HMAC",
      key,
      b64urlToBytes(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
    if (!ok) return null;
    const payload = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[1])));
    const now = Math.floor(Date.now() / 1000);
    if (typeof payload.exp === "number" && payload.exp <= now) return null;
    if (typeof payload.nbf === "number" && payload.nbf > now) return null;
    return payload;
  } catch {
    return null;
  }
}

Deno.serve(async (req: Request) => {
  const name = new URL(req.url).pathname.split("/")[1] ?? "";
  const spec = Object.hasOwn(FUNCTIONS, name) ? FUNCTIONS[name] : undefined;
  if (!spec) return json(404, { code: "NOT_FOUND", message: "Requested function was not found" });

  if (spec.verifyJwt && req.method !== "OPTIONS") {
    const m = (req.headers.get("authorization") ?? "").match(/^Bearer\s+(\S+)$/i);
    const payload = m ? await verifyHs256(m[1]) : null;
    if (!payload) return json(401, { code: "UNAUTHORIZED", message: "Invalid JWT" });
    if (spec.requireRole && payload.role !== spec.requireRole) {
      return json(403, { error: "forbidden" });
    }
  }

  const envVars = spec.env
    .filter((k) => Deno.env.get(k))
    .map((k) => [k, Deno.env.get(k) as string]);

  try {
    // deno-lint-ignore no-explicit-any
    const worker = await (globalThis as any).EdgeRuntime.userWorkers.create({
      servicePath: `/home/deno/functions/${name}`,
      memoryLimitMb: 150,
      workerTimeoutMs: 5 * 60 * 1000,
      noModuleCache: false,
      envVars,
      forceCreate: false,
    });
    return await worker.fetch(req);
  } catch (e) {
    console.error(`[main] ${name}:`, e);
    return json(500, { code: "WORKER_ERROR", message: "Function failed (see container logs)" });
  }
});
