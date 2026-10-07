/**
 * monitoring-alert-email — JEG-435
 *
 * Called by pg_cron every 15 minutes.  Reads monitoring.check_heartbeats,
 * compares with monitoring.alert_state to find transitions (newly bad or
 * recovered), and sends ONE digest email via Resend on each batch.
 *
 * Fail-closed: if RESEND_API_KEY is absent, records a failed observation
 * and returns 503 so the evaluator marks this check red.
 *
 * Deploy: supabase functions deploy monitoring-alert-email --no-verify-jwt \
 *           --project-ref iskiybsimubiujwuchsl
 *
 * Required secret:
 *   supabase secrets set RESEND_API_KEY=re_... --project-ref iskiybsimubiujwuchsl
 *
 * Note: deployed with --no-verify-jwt so pg_cron can POST with no bearer token.
 * The function reads no user data and sends only to the hard-coded owner address,
 * so exposure risk is low: an unauthenticated caller can trigger a state check
 * but cannot read secrets or exfiltrate data.
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const RESEND_API_URL = "https://api.resend.com/emails";
const RECIPIENT = "jeremy.burstyn@gmail.com";
// Resend's onboarding address works for owner-address sends without domain setup.
// Jeremy must create a free Resend account at resend.com and generate an API key.
const SENDER = "onboarding@resend.dev";
const CHECK_ID = "monitoring_alert_email";

// States that constitute a bad outcome and warrant an alert.
const BAD_STATES = new Set(["missed", "error"]);
// States that constitute recovery from a previously alerted bad state.
const GOOD_STATES = new Set(["healthy", "degraded"]);

interface CheckHeartbeat {
  check_id: string;
  state: string;
  state_since: string;
}

interface AlertStateRow {
  check_id: string;
  last_alert_status: string;
  last_alerted_at: string;
}

Deno.serve(async (_req: Request) => {
  const startMs = Date.now();

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRoleKey) {
    return jsonResponse(
      { error: "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set" },
      500
    );
  }

  const resendApiKey = Deno.env.get("RESEND_API_KEY");

  const supabase = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false },
  });

  // Fail-closed: if no email channel, record the attempt and return 503
  // so the monitoring evaluator marks this check red.
  if (!resendApiKey) {
    await recordObservation(
      supabase,
      CHECK_ID,
      false,
      Date.now() - startMs,
      "NO_CHANNEL_CONFIGURED"
    );
    return jsonResponse(
      { error: "no channel configured: RESEND_API_KEY not set" },
      503
    );
  }

  try {
    // Read current states for all monitored checks.
    const { data: heartbeats, error: hbError } = await supabase
      .schema("monitoring")
      .from("check_heartbeats")
      .select("check_id, state, state_since");

    if (hbError) throw new Error(`read heartbeats: ${hbError.message}`);

    // Read last-alerted states to detect transitions.
    const { data: alertRows, error: asError } = await supabase
      .schema("monitoring")
      .from("alert_state")
      .select("check_id, last_alert_status, last_alerted_at");

    if (asError) throw new Error(`read alert_state: ${asError.message}`);

    const alertMap = new Map<string, string>(
      (alertRows as AlertStateRow[]).map((r) => [r.check_id, r.last_alert_status])
    );

    const newlyBad: CheckHeartbeat[] = [];
    const recovered: CheckHeartbeat[] = [];

    for (const hb of heartbeats as CheckHeartbeat[]) {
      // Skip the alerter itself to avoid self-report feedback loops.
      if (hb.check_id === CHECK_ID) continue;

      const lastStatus = alertMap.get(hb.check_id) ?? "unknown";
      const nowBad = BAD_STATES.has(hb.state);
      const wasGood = !BAD_STATES.has(lastStatus);
      const nowGood = GOOD_STATES.has(hb.state);
      const wasBad = BAD_STATES.has(lastStatus);

      if (nowBad && wasGood) newlyBad.push(hb);
      if (nowGood && wasBad) recovered.push(hb);
    }

    const transitions = [...newlyBad, ...recovered];

    if (transitions.length === 0) {
      // No new transitions: record success, no email sent.
      await recordObservation(supabase, CHECK_ID, true, Date.now() - startMs, null);
      return jsonResponse({ sent: false, reason: "no transitions" }, 200);
    }

    // Build and send one digest email for the transition batch.
    const subject = buildSubject(newlyBad, recovered);
    const html = buildEmailHtml(newlyBad, recovered);

    const emailResp = await fetch(RESEND_API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${resendApiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ from: SENDER, to: RECIPIENT, subject, html }),
    });

    if (!emailResp.ok) {
      const body = await emailResp.text().catch(() => "(unreadable)");
      throw new Error(`Resend API ${emailResp.status}: ${body}`);
    }

    // Update alert_state for every transitioned check so we don't re-alert.
    const now = new Date().toISOString();
    for (const hb of transitions) {
      const { error: upsertErr } = await supabase
        .schema("monitoring")
        .from("alert_state")
        .upsert(
          { check_id: hb.check_id, last_alert_status: hb.state, last_alerted_at: now },
          { onConflict: "check_id" }
        );
      if (upsertErr) {
        // Non-fatal: log and continue. Worst case: duplicate email on next run.
        console.error(`alert_state upsert ${hb.check_id}: ${upsertErr.message}`);
      }
    }

    await recordObservation(supabase, CHECK_ID, true, Date.now() - startMs, null);
    return jsonResponse(
      { sent: true, newly_bad: newlyBad.length, recovered: recovered.length },
      200
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await recordObservation(
      supabase,
      CHECK_ID,
      false,
      Date.now() - startMs,
      "ALERTER_ERROR"
    );
    return jsonResponse({ error: msg }, 500);
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function recordObservation(
  supabase: ReturnType<typeof createClient>,
  checkId: string,
  ok: boolean,
  latencyMs: number,
  errorCode: string | null
): Promise<void> {
  const { error } = await supabase.schema("monitoring").from("check_observations").insert({
    check_id: checkId,
    run_at: new Date().toISOString(),
    ok,
    latency_ms: latencyMs,
    source: "edge_function",
    error_code: errorCode,
  });
  if (error) {
    // Log only: if we can't record, the evaluator will eventually mark missed.
    console.error(`recordObservation failed: ${error.message}`);
  }
}

function buildSubject(
  newlyBad: CheckHeartbeat[],
  recovered: CheckHeartbeat[]
): string {
  const parts: string[] = [];
  if (newlyBad.length > 0) {
    parts.push(
      `${newlyBad.length} check${newlyBad.length > 1 ? "s" : ""} failed`
    );
  }
  if (recovered.length > 0) {
    parts.push(`${recovered.length} recovered`);
  }
  return `[Data Driven Football] ${parts.join(", ")}`;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function tableRows(checks: CheckHeartbeat[], label: string): string {
  return checks
    .map(
      (c) =>
        `<tr><td style="padding:4px 8px">${esc(c.check_id)}</td>` +
        `<td style="padding:4px 8px;font-weight:bold;color:${label === "NEW FAILURE" ? "#c00" : "#060"}">${label}</td>` +
        `<td style="padding:4px 8px">${esc(c.state)}</td>` +
        `<td style="padding:4px 8px;color:#888;font-size:12px">${esc(c.state_since?.slice(0, 16) ?? "")}</td></tr>`
    )
    .join("");
}

function buildEmailHtml(
  newlyBad: CheckHeartbeat[],
  recovered: CheckHeartbeat[]
): string {
  return `<html><body style="font-family:sans-serif;max-width:600px;margin:0 auto">
<h2 style="color:#333">Monitoring Alert — Data Driven Football</h2>
<table border="1" cellspacing="0" style="border-collapse:collapse;width:100%">
  <thead>
    <tr style="background:#f5f5f5">
      <th style="padding:4px 8px;text-align:left">Check</th>
      <th style="padding:4px 8px;text-align:left">Event</th>
      <th style="padding:4px 8px;text-align:left">State</th>
      <th style="padding:4px 8px;text-align:left">Since (UTC)</th>
    </tr>
  </thead>
  <tbody>
    ${tableRows(newlyBad, "NEW FAILURE")}
    ${tableRows(recovered, "RECOVERED")}
  </tbody>
</table>
<p style="color:#888;font-size:12px;margin-top:16px">
  Sent by monitoring-alert-email (JEG-435) every 15 min. One email per transition batch; no repeat spam.<br>
  Dashboard: <a href="https://jb-barrel-droid.github.io/fantasy-tools/status.html">status.html</a>
</p>
</body></html>`;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
