"""Standalone Supabase client for GitHub Actions (no Muse dependency).

Implements the same interface as the Muse-backed sbclient.py, but reads
credentials from environment variables:

    SUPABASE_URL          e.g. https://iskiybsimubiujwuchsl.supabase.co
    SUPABASE_SERVICE_KEY  the service_role key (stored as a GitHub secret)

Drop this on PYTHONPATH as sbclient.py when running outside Muse.
"""

import json
import os
import urllib.parse
import urllib.request


class SupabaseError(Exception):
    pass


def _base_url():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise SupabaseError("SUPABASE_URL not set")
    return url


def _api_key():
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise SupabaseError("SUPABASE_SERVICE_KEY not set")
    return key


def _request(method, path, body=None, params="", prefer="return=representation",
             schema=None):
    url = _base_url() + path + params
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", _api_key())
    req.add_header("Authorization", f"Bearer {_api_key()}")
    req.add_header("Content-Type", "application/json")
    if schema:
        # PostgREST schema selector for non-public schemas (e.g. api.*).
        req.add_header("Accept-Profile", schema)
        req.add_header("Content-Profile", schema)
    if prefer:
        req.add_header("Prefer", prefer)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        raw = resp.read()
        if not raw:
            return []
        try:
            return json.loads(raw.decode())
        except json.JSONDecodeError:
            return raw.decode()[:500]
    except urllib.error.HTTPError as e:
        raise SupabaseError(f"{method} {path}: HTTP {e.code} {e.read().decode()[:400]}")


def get(table, params="", schema=None):
    return _request("GET", f"/rest/v1/{table}", params=params, prefer="",
                    schema=schema)


def rpc(function, payload, params=""):
    """Call a Postgres function via PostgREST RPC.

    POST /rest/v1/rpc/<function> with a JSON body; returns the decoded
    response. Raises SupabaseError on HTTP errors (the loader treats any
    promote failure as fail-closed).
    """
    return _request("POST", f"/rest/v1/rpc/{function}", body=payload,
                    params=params, prefer="")


def get_all(table, params="", batch=1000):
    """Paginated read past PostgREST's 1000-row cap, with order=id enforced."""
    rows, offset = [], 0
    parts = [p for p in params.lstrip("?").split("&")
             if p and not p.startswith("limit=") and not p.startswith("offset=")]
    if not any(p.startswith("order=") for p in parts):
        parts.append("order=id")
    base = "&".join(parts)
    while True:
        page = _request("GET", f"/rest/v1/{table}",
                        params=f"?{base}&limit={batch}&offset={offset}" if base
                        else f"?limit={batch}&offset={offset}", prefer="")
        rows.extend(page)
        if len(page) < batch:
            return rows
        offset += batch


def post(table, body, params="", prefer="return=representation"):
    return _request("POST", f"/rest/v1/{table}", body=body, params=params,
                    prefer=prefer)


def patch(table, body, params):
    return _request("PATCH", f"/rest/v1/{table}", body=body, params=params)


def delete(table, params):
    return _request("DELETE", f"/rest/v1/{table}", params=params, prefer="")
