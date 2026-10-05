"""Heartbeat observation producer (JEG-339 / JEG-357).

Single-pass CLI: fetch each check URL, classify the result into the approved
verdict set, and hand a row to a writer. Intended to be invoked every 60s
by a systemd timer (the timer itself lives elsewhere).

Standing rule: this module MUST NOT carry any credentials. No keys, tokens,
passwords, or connection strings — not even placeholder examples that look
real. SupabaseWriter exists as a class so deploy wiring can attach credentials
at runtime; the worker code intentionally raises NotImplementedError.

Verdict set (Jeremy 2026-10-04): ok, content_mismatch, timeout, dns_error,
tls_error, connect_error, http_error. content_mismatch is accepted but never
emitted by this producer (a future content-checking producer will own it).
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional, Tuple


# ---- Verdict constants -------------------------------------------------


VERDICT_OK = "ok"
VERDICT_CONTENT_MISMATCH = "content_mismatch"
VERDICT_TIMEOUT = "timeout"
VERDICT_DNS_ERROR = "dns_error"
VERDICT_TLS_ERROR = "tls_error"
VERDICT_CONNECT_ERROR = "connect_error"
VERDICT_HTTP_ERROR = "http_error"

# Approved verdict set — content_mismatch is included for completeness even
# though this producer never emits it (a future content-checking producer will).
APPROVED_VERDICTS = frozenset({
    VERDICT_OK,
    VERDICT_CONTENT_MISMATCH,
    VERDICT_TIMEOUT,
    VERDICT_DNS_ERROR,
    VERDICT_TLS_ERROR,
    VERDICT_CONNECT_ERROR,
    VERDICT_HTTP_ERROR,
})


# ---- Time helpers ------------------------------------------------------


def _now_utc_z() -> str:
    """Current UTC time as ISO-8601 with a 'Z' suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---- Network -----------------------------------------------------------
#
# _fetch is intentionally a module-level function so tests can monkey-patch
# it without touching the network. Production uses urllib.request.urlopen
# directly to avoid adding third-party deps (requests) for a one-shot probe.


def _fetch(url: str, timeout_seconds: int) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Single HTTP GET. Returns (status_code, elapsed_ms, error).

    `error` is one of None | 'timeout' | 'dns' | 'tls' | 'connect'.
    Never raises; every network exception is mapped into one of those codes.
    """
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jeg339-heartbeat/1"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            status_code = getattr(resp, "status", None) or resp.getcode()
            # Drain a small slice of the body so the connection state matches
            # what a real probe observed.
            try:
                resp.read(1024)
            except Exception:
                pass
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return status_code, elapsed_ms, None
    except (socket.timeout, TimeoutError):
        return None, int((time.monotonic() - started) * 1000), "timeout"
    except (ssl.SSLError, ssl.CertificateError):
        return None, int((time.monotonic() - started) * 1000), "tls"
    except socket.gaierror:
        return None, int((time.monotonic() - started) * 1000), "dns"
    except (ConnectionRefusedError, ConnectionResetError):
        return None, int((time.monotonic() - started) * 1000), "connect"
    except urllib.error.URLError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return None, elapsed_ms, "timeout"
        if isinstance(reason, (ssl.SSLError, ssl.CertificateError)):
            return None, elapsed_ms, "tls"
        if isinstance(reason, socket.gaierror):
            return None, elapsed_ms, "dns"
        # ConnectionRefusedError, ConnectionResetError, network unreachable, etc.
        # Anything else is treated as a connect failure. The "any ambiguity → never
        # green" rule covers this branch by construction.
        return None, elapsed_ms, "connect"
    except (ConnectionError, OSError):
        # Treat generic connection-class failures as 'connect'.
        return None, int((time.monotonic() - started) * 1000), "connect"


# ---- Classification ----------------------------------------------------


def classify_result(
    url: str,
    status_code: Optional[int],
    elapsed_ms: Optional[int],
    error: Optional[str],
    check: dict,
) -> dict:
    """Map a single fetch outcome into an observation row.

    Verdict mapping (per Jeremy 2026-10-04):
        error='timeout'  → 'timeout'
        error='dns'      → 'dns_error'
        error='tls'      → 'tls_error'
        error='connect'  → 'connect_error'
        status_code None → 'connect_error'   (ambiguity: never green)
        200 ≤ status < 300 → 'ok'
        otherwise        → 'http_error'

    Escape hatch: a future content-checking phase may set
    `check['force_verdict']` to one of the approved verdicts to override
    the network-based mapping (e.g. 'content_mismatch' on a 200 response).
    The forced value is validated against `APPROVED_VERDICTS`; anything
    else is ignored and the normal mapping runs.
    """
    forced = check.get("force_verdict")
    if forced in APPROVED_VERDICTS:
        verdict = forced
    elif error == "timeout":
        verdict = VERDICT_TIMEOUT
    elif error == "dns":
        verdict = VERDICT_DNS_ERROR
    elif error == "tls":
        verdict = VERDICT_TLS_ERROR
    elif error == "connect":
        verdict = VERDICT_CONNECT_ERROR
    elif status_code is None:
        # Ambiguity: no error tag AND no status code. Per the standing rule
        # ("evaluator must never see fabricated green"), this cannot be 'ok'.
        verdict = VERDICT_CONNECT_ERROR
    elif 200 <= status_code < 300:
        verdict = VERDICT_OK
    else:
        verdict = VERDICT_HTTP_ERROR

    return {
        "checked_at": _now_utc_z(),
        "url": url,
        "status_code": status_code,
        "response_ms": elapsed_ms,
        "verdict": verdict,
    }


# ---- Writers -----------------------------------------------------------


class ObservationWriter:
    """Pluggable sink for observation rows.

    The producer loop isolates per-check failures, so a single broken write
    should not poison the rest of the pass.
    """

    def write(self, row: dict) -> None:
        raise NotImplementedError


class NDJSONWriter(ObservationWriter):
    """Append-only NDJSON file. Safe to use across the 60s timer ticks."""

    def __init__(self, path: str) -> None:
        self._path = path

    def write(self, row: dict) -> None:
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


class SupabaseWriter(ObservationWriter):
    """DB writer placeholder.

    The real DB writer is wired at deploy time by Roman; this class carries
    no credentials — keys, tokens, passwords, or connection strings are
    forbidden in worker code per JEG-339 standing rules. Any args the
    deploy layer may pass are accepted and ignored.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Accept and discard. We never persist anything that could be a
        # credential; the deploy layer injects them at call time.
        return None

    def write(self, row: dict) -> None:
        raise NotImplementedError(
            "DB writer is wired at deploy by Roman — no credentials in worker code"
        )


# ---- Driver loop -------------------------------------------------------


def run_once(checks: List[dict], writer: ObservationWriter) -> dict:
    """Run one pass: fetch each enabled check, classify, write a row.

    Never raises on a single check failing — the failure verdict is written
    and the next check is attempted.

    Returns: {ran, ok_count, failed: [check_id], elapsed_ms}
    """
    started = time.monotonic()
    ran = 0
    ok_count = 0
    failed: List[str] = []
    for check in checks:
        check_id = check.get("check_id")
        if not check.get("enabled", True):
            continue
        url = check.get("url")
        if not url:
            # Bad config: skip, do not raise.
            failed.append(str(check_id))
            continue
        timeout_seconds = int(check.get("timeout_seconds", 10))
        ran += 1
        status_code, elapsed_ms, error = _fetch(url, timeout_seconds)
        row = classify_result(url, status_code, elapsed_ms, error, check)
        try:
            writer.write(row)
        except NotImplementedError:
            # Wiring is intentionally absent in worker; surface to caller so
            # the operator notices instead of silently dropping rows.
            raise
        except Exception:
            failed.append(str(check_id))
            continue
        if row["verdict"] == VERDICT_OK:
            ok_count += 1
        else:
            failed.append(str(check_id))
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {"ran": ran, "ok_count": ok_count, "failed": failed, "elapsed_ms": elapsed_ms}


# ---- CLI ---------------------------------------------------------------


def _writer_for(spec: str, dry_run: bool) -> ObservationWriter:
    """Resolve the --out spec to an ObservationWriter.

    Supported specs:
        ndjson:<path>     → NDJSONWriter(path)
        supabase:...      → SupabaseWriter()  (or NDJSONWriter(/dev/null) if --dry-run)
    """
    if spec.startswith("ndjson:"):
        return NDJSONWriter(spec[len("ndjson:"):])
    if spec.startswith("supabase:"):
        if dry_run:
            # Smoke test: never touch the real DB writer. Write rows to
            # /dev/null so the pipeline shape stays observable.
            return NDJSONWriter("/dev/null")
        return SupabaseWriter()
    raise ValueError(f"unsupported --out spec: {spec!r}")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipelines.heartbeat_producer")
    p.add_argument("--checks", required=True,
                   help="Path to checks config JSON (see config/heartbeat_checks.json).")
    p.add_argument("--out", required=True,
                   help="Output sink. Supported: ndjson:<path> or supabase:...")
    p.add_argument("--dry-run", action="store_true",
                   help="Force NDJSONWriter regardless of --out (smoke tests).")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    with open(args.checks, encoding="utf-8") as fh:
        cfg = json.load(fh)
    checks = list(cfg.get("checks", []))
    writer = _writer_for(args.out, args.dry_run)
    summary = run_once(checks, writer)
    json.dump(summary, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())