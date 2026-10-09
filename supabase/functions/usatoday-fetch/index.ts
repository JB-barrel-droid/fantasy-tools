// Fetch relay for the USA Today trade-chart ingest (GAP-USAT-CI-BLOCKED).
// GitHub-hosted runner IPs are walled (HTTP 402) by usatoday.com; this relays
// a GET from Supabase egress and returns {status, body}. Parsing and all
// fail-closed checks stay in ops/watchdog/*.py. No header spoofing, no
// challenge solving: a non-200 is returned as-is.
//
// GAP-USAT-RELAY-ANON (2026-10-09): service role only. verify_jwt checks the
// signature; this checks the role claim, so the public anon key is refused.
// Every URL, including each redirect hop, must match ALLOWED (host + path).
// Deployed from this file (Supabase MCP deploy_edge_function, verify_jwt true).
const ALLOWED: Record<string, RegExp[]> = {
  "www.usatoday.com": [/^\/story\/sports\/fantasy\//, /^\/web-sitemap-index\.xml$/],
  "usatoday.com": [/^\/story\/sports\/fantasy\//, /^\/web-sitemap-index\.xml$/],
  "amp.usatoday.com": [/^\/story\/sports\/fantasy\//],
  "www.gannett-cdn.com": [/^\/sitemaps\/USAT\/web\/web-sitemap-\d{4}-\d{2}\.xml$/],
};
const MAX_REDIRECTS = 5;

function allowed(raw: string): URL | null {
  let u: URL;
  try { u = new URL(raw); } catch { return null; }
  if (u.protocol !== "https:" || u.username || u.password || u.port) return null;
  const rules = ALLOWED[u.hostname];
  return rules && rules.some((re) => re.test(u.pathname)) ? u : null;
}

function callerRole(req: Request): string {
  const token = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (serviceKey && token === serviceKey) return "service_role";
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part + "=".repeat((4 - part.length % 4) % 4))).role ?? "";
  } catch {
    return "";
  }
}

Deno.serve(async (req: Request) => {
  if (callerRole(req) !== "service_role") {
    return Response.json({ error: "forbidden" }, { status: 403 });
  }
  let url = "";
  try {
    if (req.method === "POST") url = (await req.json()).url ?? "";
    else url = new URL(req.url).searchParams.get("url") ?? "";
    let target = allowed(url);
    if (!target) return Response.json({ error: "url not allowed" }, { status: 400 });
    for (let hop = 0; ; hop++) {
      const r = await fetch(target.toString(), {
        headers: {
          "User-Agent": "DataDrivenFootball-ingest/1.0 (+https://datadrivenfootball.com)",
          "Accept": "text/html,application/xml;q=0.9,*/*;q=0.5",
        },
        redirect: "manual",
      });
      const location = r.headers.get("location");
      if (r.status >= 300 && r.status < 400 && location) {
        await r.body?.cancel();
        const next = allowed(new URL(location, target).toString());
        if (!next || hop >= MAX_REDIRECTS) {
          return Response.json({ error: "redirect not allowed", status: r.status }, { status: 400 });
        }
        target = next;
        continue;
      }
      const body = await r.text();
      return Response.json({ status: r.status, len: body.length, body });
    }
  } catch (e) {
    return Response.json({ error: String(e), url }, { status: 502 });
  }
});
