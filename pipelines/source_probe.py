#!/usr/bin/env python3
"""Cheap per-source change probes: run the full scrape only when a source moved.

Every source the chart reads gets a probe that costs a few small requests and
returns a *content fingerprint*: a hash of the signals that change when the
numbers can change (and, as far as measured, only then). The probe compares it
with the fingerprint the last successful full ingest acknowledged and decides:

    ingest  the fingerprint differs from the acknowledged one (``changed``), the
            last acknowledged ingest is older than the source's max age
            (``max_age``), nothing was ever acknowledged (``first``), or the
            probe itself failed (``probe_failed``; the full ingest is fail-closed
            on its own, so an unreadable probe never hides a change)
    wait    an ingest for this exact fingerprint was dispatched less than
            ``retry_gap`` ago and has not acknowledged yet (in flight), or a
            change arrived inside the source's ``min_interval`` (FantasyCalc)
    skip    unchanged and fresh

An ingest acknowledges only on success (``source_probe.py ack``, called by the
ingest workflow), so a failed ingest is retried on the next probe slot once
``retry_gap`` has passed, up to ``max_attempts`` times per fingerprint; after
that the source tries once per max age (logged ``gave_up``, a warning). When
the probe itself cannot read a source, one blind full ingest runs; once that
succeeds (acknowledged as ``unprobed``) the source falls back to max-age runs.

A probe-driven ingest that acknowledges a *new* fingerprint dispatches the
rebuild chain (``ack`` writes ``new_content=true`` to $GITHUB_OUTPUT).

Signals per source (measured 2026-10-08, docs/claude-log/2026-10-08-refresh-cadence.md):

    fantasycalc  JSON API, no ETag/Last-Modified, HEAD 404, Cache-Control
                 max-age=1200 -> hash of the (player id, value) pairs of the
                 three 12-team 1-QB lists (3 x ~150 KB)
    usatoday     the article the ingest's own discover_url finds in the monthly
                 web sitemaps, and its <lastmod> there; the article page is
                 never fetched (it 402s plain clients from CI)
    fantasypros  no ETag/Last-Modified -> the article the ingest's own
                 discover_url finds, its JSON-LD dateModified and a tables hash
    cbs          as FantasyPros, on www.cbssports.com (the sportsfly mirror's
                 ETag answers 304, but it is a 60-day CDN that served a stale
                 revision); the ETag is recorded, not hashed
    espn         JSON API (projection blocks only) -> hash of
                 (player id, period, appliedTotal) for the weekly projection
                 blocks the puller sums (4 requests)
    cbsros       4 stats pages, weak ETag (stable across requests) -> hash of
                 the stats tables (ETag kept as a signal only)
    razzball     4 pages, no ETag, dateModified frozen in July -> the pages'
                 own "Updated: <date> <time>" stamps + tables hash

Usage:
    source_probe.py probe [--sources a,b] [--state-file F | --supabase]
                          [--dispatch-out F] [--dry-run]
    source_probe.py ack --source S --fingerprint FP [--state-file F | --supabase]
    source_probe.py show [--state-file F | --supabase]

``probe`` prints one JSON line per source and, with ``--dispatch-out``, writes
the ``gh workflow run`` argument lists for the sources to ingest.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html as htmllib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from nfl_week import current_nfl_week as content_week  # noqa: E402  (content week, Tuesday flip)

SEASON = 2026
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HTML_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
}


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Policy:
    """When a probe result turns into a full ingest.

    max_age       force a full ingest when the last acknowledged one is older
    retry_gap     do not re-dispatch the same fingerprint sooner than this
    max_attempts  dispatches per fingerprint before waiting for max_age
    min_interval  a *change* is ingested no sooner than this after the last
                  acknowledged ingest (0 = immediately). Max age and first runs
                  ignore it.
    """
    max_age: timedelta
    retry_gap: timedelta = timedelta(minutes=50)
    max_attempts: int = 4
    min_interval: timedelta = timedelta(0)


H = timedelta(hours=1)
# Max age is 20 h, not 24: a forced run then always lands in the next probe
# slot (projections every 4 h, trade charts every 3 h / 12 h), so the gap
# between saves stays under 24 h and every UTC day has one.
POLICIES: dict[str, Policy] = {
    # Live crowd values move every hour; a save is a new bake (~585 rows), so
    # changes are taken at most every 6 h. The Tuesday + Friday 13:07 UTC fixed
    # saves stay (the week-history FantasyCalc cut is the first pull at or
    # after Tuesday 12:00 UTC).
    "fantasycalc": Policy(max_age=24 * H, min_interval=6 * H),
    # Weekly articles, edited by hand after publication.
    "usatoday": Policy(max_age=20 * H),
    "fantasypros": Policy(max_age=20 * H),
    "cbs": Policy(max_age=20 * H),
    # Projections: the week-N snapshot is the newest one dated in week N.
    "espn": Policy(max_age=20 * H),
    "cbsros": Policy(max_age=20 * H),
    "razzball": Policy(max_age=20 * H),
}

SOURCES = tuple(POLICIES)

# Full-ingest workflow per source: (workflow file, extra -f inputs).
INGEST: dict[str, tuple[str, dict[str, str]]] = {
    "fantasycalc": ("fantasycalc-weekly-save.yml", {"mode": "write"}),
    "usatoday": ("trade-chart-ingest.yml", {"mode": "write", "source": "usatoday"}),
    "fantasypros": ("trade-chart-ingest.yml", {"mode": "write", "source": "fantasypros"}),
    "cbs": ("trade-chart-ingest.yml", {"mode": "write", "source": "cbs"}),
    "espn": ("espn-supabase-sync.yml", {}),
    "cbsros": ("cbsros-supabase-sync.yml", {}),
    "razzball": ("razzball-supabase-sync.yml", {"mode": "write"}),
}


# Fingerprint recorded for an ingest dispatched while the probe could not read
# the source; acknowledging it restarts the max-age clock.
UNPROBED = "unprobed"


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def decide(state: dict[str, Any] | None, probe: dict[str, Any], now: datetime,
           policy: Policy) -> dict[str, str]:
    """Pure decision: {"action": ingest|wait|skip, "reason": ...}.

    ``state`` is the source's stored row (acked_fp, acked_at, dispatched_fp,
    dispatched_at, attempts) or None; ``probe`` is a probe result
    ({"ok": bool, "fingerprint": str | None}).
    """
    state = state or {}
    acked_fp = state.get("acked_fp")
    acked_at = _ts(state.get("acked_at"))
    disp_fp = state.get("dispatched_fp")
    disp_at = _ts(state.get("dispatched_at"))
    attempts = int(state.get("attempts") or 0)
    fp = probe.get("fingerprint") if probe.get("ok") else None
    token = fp or UNPROBED
    in_flight = disp_at is not None and now - disp_at < policy.retry_gap
    age = (now - acked_at) if acked_at is not None else None
    stale = age is None or age >= policy.max_age
    gave_up = disp_at is not None and disp_fp == token and attempts >= policy.max_attempts
    # After max_attempts failed ingests of one fingerprint, try once per max_age.
    resting = gave_up and now - disp_at < policy.max_age

    def ingest(reason: str) -> dict[str, str]:
        # Never stack a second dispatch on one still inside its retry gap.
        if in_flight and disp_fp == token:
            return {"action": "wait", "reason": f"{reason}; ingest in flight"}
        return {"action": "ingest", "reason": reason}

    if resting:
        return {"action": "wait", "reason": f"gave_up: {attempts} ingests of this content "
                "failed; next try at max_age"}
    if fp is None:
        # The probe could not read the source. The full ingest (fail-closed on
        # its own) looks instead; once one such blind ingest succeeded, the
        # source falls back to max-age runs until the probe reads again.
        if stale:
            return ingest("probe_failed")
        if acked_fp == UNPROBED:
            return {"action": "skip", "reason": "probe failing; blind ingest acknowledged, "
                    "next at max_age"}
        return ingest("probe_failed")
    if acked_fp is None or age is None:
        return ingest("first")
    if fp == acked_fp:
        if stale:
            return ingest("max_age")
        return {"action": "skip", "reason": "unchanged"}
    # Changed content.
    if stale:
        return ingest("changed")
    if age < policy.min_interval:
        return {"action": "wait", "reason": "changed; inside min_interval"}
    return ingest("retry" if disp_fp == fp else "changed")


def apply_decision(state: dict[str, Any] | None, source: str, probe: dict[str, Any],
                   decision: dict[str, str], now: datetime) -> dict[str, Any]:
    """New state row after a probe (dispatch bookkeeping only; acks are separate)."""
    row = dict(state or {})
    row["source"] = source
    row["last_probe_at"] = now.isoformat()
    row["last_ok"] = bool(probe.get("ok"))
    if probe.get("ok"):
        row["last_fp"] = probe.get("fingerprint")
    row["last_signals"] = probe.get("signals") or {}
    row["last_error"] = probe.get("error")
    row["last_action"] = decision["action"]
    row["last_reason"] = decision["reason"]
    if decision["action"] == "ingest":
        fp = (probe.get("fingerprint") if probe.get("ok") else None) or UNPROBED
        same = row.get("dispatched_at") is not None and row.get("dispatched_fp") == fp
        row["attempts"] = (int(row.get("attempts") or 0) + 1) if same else 1
        row["dispatched_fp"] = fp
        row["dispatched_at"] = now.isoformat()
    return row


def apply_ack(state: dict[str, Any] | None, source: str, fingerprint: str,
              now: datetime) -> dict[str, Any]:
    """A successful full ingest acknowledges the fingerprint it was sent for."""
    row = dict(state or {})
    row["source"] = source
    row["acked_fp"] = fingerprint
    row["acked_at"] = now.isoformat()
    if row.get("dispatched_fp") == fingerprint:
        row["attempts"] = 0
    return row


# --------------------------------------------------------------------------
# Fingerprint helpers
# --------------------------------------------------------------------------

def digest(obj: Any) -> str:
    """Stable short hash of a JSON-able object."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


TABLE_RE = re.compile(r"<table\b.*?</table>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def tables_text(page: str) -> str:
    """Visible text of every <table> on the page, whitespace-normalised.

    Attributes, scripts and ad slots outside tables are ignored, so page
    chrome that changes per request does not move the hash."""
    parts = []
    for block in TABLE_RE.findall(page or ""):
        txt = htmllib.unescape(TAG_RE.sub(" ", block))
        parts.append(WS_RE.sub(" ", txt).strip())
    return "\n".join(parts)


ROW_RE = re.compile(r"<tr\b.*?</tr>", re.S | re.I)


def table_rows(page: str) -> list[list[str]]:
    """Per table, the visible text of each row, rows sorted.

    Sorting makes the hash order-insensitive: CBS's rest-of-season pages list
    players tied on fantasy points in a different order on every few requests
    (measured 2026-10-08: three table hashes in 25 minutes, no value moved),
    and row order never changes a value we read (rows are keyed by player)."""
    out = []
    for block in TABLE_RE.findall(page or ""):
        rows = []
        for tr in ROW_RE.findall(block):
            txt = WS_RE.sub(" ", htmllib.unescape(TAG_RE.sub(" ", tr))).strip()
            if txt:
                rows.append(txt)
        if not rows:
            txt = WS_RE.sub(" ", htmllib.unescape(TAG_RE.sub(" ", block))).strip()
            rows = [txt] if txt else []
        if rows:
            out.append(sorted(rows))
    return out


def tables_hash(page: str) -> str | None:
    rows = table_rows(page)
    return digest(rows) if rows else None


DATE_MODIFIED_RE = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')


def date_modified(page: str) -> str | None:
    """Newest JSON-LD dateModified on the page (a page can carry several)."""
    found = DATE_MODIFIED_RE.findall(page or "")
    return max(found) if found else None


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

@dataclass
class Resp:
    status: int | None
    headers: dict[str, str]
    body: str

    def header(self, name: str) -> str | None:
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return None


def http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 40) -> Resp:
    req = urllib.request.Request(url, headers={**HTML_HEADERS, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, status, hd = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, hd = e.read(), e.code, dict(e.headers or {})
    except Exception as e:  # noqa: BLE001  network error -> probe failure
        return Resp(None, {}, f"{type(e).__name__}: {e}")
    if any(k.lower() == "content-encoding" and v == "gzip" for k, v in hd.items()):
        raw = gzip.decompress(raw)
    return Resp(status, hd, raw.decode("utf-8", "replace"))


Fetch = Callable[..., Resp]


class ProbeError(RuntimeError):
    pass


def _need_200(resp: Resp, what: str) -> str:
    if resp.status != 200 or not resp.body:
        raise ProbeError(f"{what}: status={resp.status} {resp.body[:120] if resp.status is None else ''}")
    return resp.body


# --------------------------------------------------------------------------
# Probes (each returns {"fingerprint", "signals"}; raises ProbeError)
# --------------------------------------------------------------------------

FC_API = ("https://api.fantasycalc.com/values/current?isDynasty=false&numQbs=1"
          "&numTeams=12&ppr={ppr}")


def probe_fantasycalc(fetch: Fetch, week: int) -> dict[str, Any]:
    lists, signals = {}, {}
    for ppr in ("0", "0.5", "1"):
        body = _need_200(fetch(FC_API.format(ppr=ppr), {"Accept": "application/json"}),
                         f"fantasycalc ppr={ppr}")
        try:
            rows = json.loads(body)
            pairs = sorted((int(r["player"]["id"]), r["value"]) for r in rows)
        except (ValueError, KeyError, TypeError) as e:
            raise ProbeError(f"fantasycalc ppr={ppr}: unparseable ({e})") from e
        if len(pairs) < 100:
            raise ProbeError(f"fantasycalc ppr={ppr}: only {len(pairs)} players")
        lists[ppr] = pairs
        signals[f"n_{ppr}"] = len(pairs)
        signals[f"sum_{ppr}"] = sum(v for _, v in pairs)
    return {"fingerprint": digest(lists), "signals": signals}


USAT_SITEMAP = "https://www.gannett-cdn.com/sitemaps/USAT/web/web-sitemap-%04d-%02d.xml"
SITEMAP_URL_RE = re.compile(r"<url>\s*<loc>([^<]+)</loc>\s*(?:<lastmod>([^<]+)</lastmod>)?", re.S)


def _months_back(today: date) -> list[tuple[int, int]]:
    prev = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return [(today.year, today.month), prev]


def probe_usatoday(fetch: Fetch, week: int, today: date | None = None,
                   discover=None) -> dict[str, Any]:
    """The article the ingest's own discover_url finds (USA Today's monthly
    sitemaps; the article page itself 402s plain clients from CI) and that
    URL's <lastmod> in the same sitemaps."""
    ad = _DiscoveryFetch(fetch)
    url = _discover("usatoday", "pull_usatoday", ad, week, discover)
    lastmod = None
    today = today or datetime.now(timezone.utc).date()
    for ym in _months_back(today):
        sitemap = USAT_SITEMAP % ym
        r = ad.resp(sitemap)
        if r.status == 200 and "</urlset>" in (r.body or ""):
            hits = [lm for u, lm in SITEMAP_URL_RE.findall(r.body) if u == url]
            if hits:
                lastmod = hits[-1]
                break
    m = re.search(r"week-(\d+)", url)
    sig = {"week": int(m.group(1)) if m else None, "url": url, "lastmod": lastmod}
    return {"fingerprint": digest(sig), "signals": sig}


# Article discovery is the ingest's own (ops/watchdog/pull_fantasypros.py and
# pull_cbs.py discover_url): the slugs change from week to week (CBS Week 5 is
# ".../dave-richards-2026-week-5-trade-chart/", Week 4 was
# ".../dave-richards-week-4-trade-chart-and-rest-of-season-..."), so a probe
# guessing slugs would keep fingerprinting last week's article while the new
# one is up. Sharing the function means the probe and the ingest always look at
# the same article.
WATCHDOG = ROOT / "ops" / "watchdog"
WEEK_RE = re.compile(r"\bweek\s+(\d+)\b", re.I)


class _DiscoveryFetch:
    """(status, body) adapter for the watchdog discover_url(fetch_fn=...) API,
    remembering each response so the discovered page is not fetched twice."""

    def __init__(self, fetch: "Fetch", headers: dict[str, str] | None = None):
        self.fetch, self.headers, self.seen = fetch, headers or {}, {}

    def __call__(self, url: str) -> tuple[int | None, str]:
        if url not in self.seen:
            self.seen[url] = self.fetch(url, self.headers)
        r = self.seen[url]
        return r.status, r.body

    def resp(self, url: str) -> "Resp":
        self(url)
        return self.seen[url]


def _watchdog_module(name: str):
    if str(WATCHDOG) not in sys.path:
        sys.path.insert(0, str(WATCHDOG))
    import importlib
    return importlib.import_module(name)


def _discover(source: str, module: str, ad: "_DiscoveryFetch", week: int,
              discover: Callable[..., str] | None) -> str:
    discover = discover or _watchdog_module(module).discover_url
    try:
        try:
            return discover(week, fetch_fn=ad)
        except Exception as e:  # noqa: BLE001
            # A quiet DiscoveryFailed means "week N is not out yet" (CBS returns
            # only the exact week): fingerprint last week's article instead, so
            # the probe reads as unchanged rather than failing every slot.
            if not getattr(e, "quiet", False) or week <= 1:
                raise
            return discover(week - 1, fetch_fn=ad)
    except Exception as e:  # noqa: BLE001  DiscoveryFailed / RuntimeError / network
        raise ProbeError(f"{source} discovery: {e}") from e


def _article_probe(source: str, module: str, fetch: "Fetch", week: int,
                   discover: Callable[..., str] | None, headers: dict[str, str] | None,
                   headline: Callable[[str], str | None]) -> dict[str, Any]:
    ad = _DiscoveryFetch(fetch, headers)
    url = _discover(source, module, ad, week, discover)
    r = ad.resp(url)
    if r.status != 200 or not r.body:
        raise ProbeError(f"{source} {url}: status={r.status}")
    title = headline(r.body) or ""
    m = WEEK_RE.search(title)
    if not m:
        raise ProbeError(f"{source} {url}: no week in the headline {title[:80]!r}")
    th = tables_hash(r.body)
    if not th:
        raise ProbeError(f"{source} {url}: no tables")
    sig = {"week": int(m.group(1)), "url": url, "date_modified": date_modified(r.body),
           "tables": th, "etag": r.header("ETag")}
    # The ETag is recorded but not hashed: tables + dateModified carry the
    # content, and a CDN re-encode must not count as a change.
    return {"fingerprint": digest({k: v for k, v in sig.items() if k != "etag"}),
            "signals": sig}


TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)


def _title(page: str) -> str | None:
    for rx in (TITLE_RE, H1_RE):
        m = rx.search(page or "")
        if m and TAG_RE.sub("", m.group(1)).strip():
            return htmllib.unescape(TAG_RE.sub("", m.group(1)).strip())
    return None


def probe_fantasypros(fetch: Fetch, week: int, discover=None) -> dict[str, Any]:
    return _article_probe("fantasypros", "pull_fantasypros", fetch, week, discover, None, _title)


def probe_cbs(fetch: Fetch, week: int, discover=None) -> dict[str, Any]:
    # Identity encoding, as the ingest's curl asks: the sportsfly mirror's gzip
    # variant served a day-old revision on 2026-10-08.
    def headline(page: str) -> str | None:
        try:
            return _watchdog_module("pull_cbs").extract_page_headline(page) or _title(page)
        except Exception:  # noqa: BLE001
            return _title(page)
    return _article_probe("cbs", "pull_cbs", fetch, week, discover,
                          {"Accept-Encoding": "identity"}, headline)


ESPN_API = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/"
            "segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info")
ESPN_SLOTS = (0, 2, 4, 6)


def probe_espn(fetch: Fetch, week: int) -> dict[str, Any]:
    """Weekly projection blocks (source 1, split 1, 2026): what the puller sums."""
    blocks, signals = [], {}
    for slot in ESPN_SLOTS:
        filt = {"players": {"filterSlotIds": {"value": [slot]},
                            "filterStatsForSourceIds": {"value": [1]},
                            "sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 3,
                                                     "value": "1120260"},
                            "limit": 400, "offset": 0}}
        r = fetch(ESPN_API, {"Accept": "application/json", "X-Fantasy-Source": "kona",
                             "X-Fantasy-Platform": "kona-web",
                             "X-Fantasy-Filter": json.dumps(filt)})
        body = _need_200(r, f"espn slot {slot}")
        try:
            players = json.loads(body)["players"]
        except (ValueError, KeyError) as e:
            raise ProbeError(f"espn slot {slot}: unparseable ({e})") from e
        n = 0
        for p in players:
            for s in (p.get("player") or {}).get("stats") or []:
                if (s.get("seasonId") == SEASON and s.get("statSourceId") == 1
                        and s.get("statSplitTypeId") == 1):
                    blocks.append((p.get("id"), s.get("scoringPeriodId"),
                                   round(float(s.get("appliedTotal") or 0), 4)))
                    n += 1
        if n == 0:
            raise ProbeError(f"espn slot {slot}: no 2026 projection blocks")
        signals[f"blocks_{slot}"] = n
    blocks.sort(key=lambda b: (b[0] or 0, b[1] or 0))
    return {"fingerprint": digest(blocks), "signals": signals}


CBSROS_URL = ("https://www.cbssports.com/fantasy/football/stats/{pos}/2026/restofseason/"
              "projections/nonppr/")
POSITIONS = ("QB", "RB", "WR", "TE")


def cbsros_stable_rows(page: str) -> list[str]:
    """The stats table's player rows minus the ones tied at the cutoff.

    Each page lists the top 100 players by projected points, and players tied
    on the last row's points swap in and out between requests (measured
    2026-10-08: Corey Kiner / Andrew Beck at 8.8, Justin Joly / Ja'Tavion
    Sanders at 4.1, nothing else moving). Rows are compared as a sorted set."""
    rows = []
    for block in TABLE_RE.findall(page or ""):
        for tr in ROW_RE.findall(block):
            toks = WS_RE.sub(" ", htmllib.unescape(TAG_RE.sub(" ", tr))).strip().split(" ")
            if len(toks) >= 4 and re.fullmatch(r"-?[\d.]+", toks[-2]):
                rows.append(toks)
    if not rows:
        return []
    cutoff = rows[-1][-2]  # projected points of the last listed player
    return sorted(" ".join(t) for t in rows if t[-2] != cutoff)


def probe_cbsros(fetch: Fetch, week: int) -> dict[str, Any]:
    hashes, etags = {}, {}
    for pos in POSITIONS:
        r = fetch(CBSROS_URL.format(pos=pos))
        body = _need_200(r, f"cbsros {pos}")
        rows = cbsros_stable_rows(body)
        if len(rows) < 10:
            raise ProbeError(f"cbsros {pos}: no stats table ({len(rows)} rows)")
        hashes[pos], etags[pos] = digest(rows), r.header("ETag")
    return {"fingerprint": digest(hashes), "signals": {"tables": hashes, "etags": etags}}


RAZZBALL_URL = "https://football.razzball.com/projections-{pos}-restofseason"
RAZZ_STAMP_RE = re.compile(r"Updated:?\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}\s*[AP]M\s*\w*)",
                           re.I)


def probe_razzball(fetch: Fetch, week: int) -> dict[str, Any]:
    stamps, hashes = {}, {}
    for pos in POSITIONS:
        body = _need_200(fetch(RAZZBALL_URL.format(pos=pos.lower())), f"razzball {pos}")
        m = RAZZ_STAMP_RE.search(TAG_RE.sub(" ", body))
        if not m:
            raise ProbeError(f"razzball {pos}: no 'Updated:' stamp")
        stamps[pos] = WS_RE.sub(" ", m.group(1)).strip()
        hashes[pos] = tables_hash(body)
    sig = {"stamps": stamps, "tables": hashes}
    return {"fingerprint": digest(sig), "signals": sig}


PROBES: dict[str, Callable[[Fetch, int], dict[str, Any]]] = {
    "fantasycalc": probe_fantasycalc,
    "usatoday": probe_usatoday,
    "fantasypros": probe_fantasypros,
    "cbs": probe_cbs,
    "espn": probe_espn,
    "cbsros": probe_cbsros,
    "razzball": probe_razzball,
}


def run_probe(source: str, fetch: Fetch = http_get, week: int | None = None) -> dict[str, Any]:
    week = week or content_week(datetime.now(timezone.utc).date())
    try:
        out = PROBES[source](fetch, week)
        return {"source": source, "ok": True, "fingerprint": out["fingerprint"],
                "signals": out["signals"], "error": None}
    except ProbeError as e:
        return {"source": source, "ok": False, "fingerprint": None, "signals": {},
                "error": str(e)[:500]}


# --------------------------------------------------------------------------
# State stores
# --------------------------------------------------------------------------

LOG_RETENTION = timedelta(days=60)

# The probe and the ack write disjoint columns, so an ack landing while a
# probe run is in progress is never overwritten by the probe's stale copy.
PROBE_COLUMNS = ("last_probe_at", "last_ok", "last_fp", "last_signals", "last_error",
                 "last_action", "last_reason", "dispatched_fp", "dispatched_at", "attempts")
ACK_COLUMNS = ("acked_fp", "acked_at", "attempts")


class FileStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def save_row(self, row: dict[str, Any], columns: tuple[str, ...]) -> None:
        data = self.load()
        merged = dict(data.get(row["source"]) or {"source": row["source"]})
        merged.update({k: row.get(k) for k in columns})
        data[row["source"]] = merged
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    def prune(self, now: datetime) -> None:
        pass

    def log(self, entry: dict[str, Any]) -> None:
        with self.path.with_suffix(".log.jsonl").open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")


class SupabaseStore:
    """public.source_probe_state (one row per source) + public.source_probe_log."""

    def __init__(self):
        import sbclient  # the gh_sbclient shim in CI
        self.sb = sbclient

    def load(self) -> dict[str, dict[str, Any]]:
        rows = self.sb.get("source_probe_state", "?select=*")
        return {r["source"]: r for r in rows or []}

    def save_row(self, row: dict[str, Any], columns: tuple[str, ...]) -> None:
        body = {"source": row["source"], **{k: row.get(k) for k in columns}}
        body["attempts"] = int(body.get("attempts") or 0) if "attempts" in body else None
        if body["attempts"] is None:
            del body["attempts"]
        if "last_signals" in body and body["last_signals"] is None:
            body["last_signals"] = {}
        body["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.sb.post("source_probe_state", [body], params="?on_conflict=source",
                     prefer="resolution=merge-duplicates,return=minimal")

    def log(self, entry: dict[str, Any]) -> None:
        self.sb.post("source_probe_log", [{
            "source": entry["source"], "probed_at": entry["probed_at"],
            "ok": entry["ok"], "fingerprint": entry.get("fingerprint"),
            "signals": entry.get("signals") or {}, "error": entry.get("error"),
            "action": entry.get("action"), "reason": entry.get("reason"),
        }], prefer="return=minimal")

    def prune(self, now: datetime) -> None:
        cutoff = (now - LOG_RETENTION).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.sb.delete("source_probe_log", f"?probed_at=lt.{cutoff}")


def _store(args) -> FileStore | SupabaseStore:
    if args.supabase:
        return SupabaseStore()
    return FileStore(Path(args.state_file))


def dispatch_args(source: str, fingerprint: str | None) -> list[str]:
    wf, inputs = INGEST[source]
    out = ["workflow", "run", wf]
    for k, v in {**inputs, "probe_fp": fingerprint or ""}.items():
        out += ["-f", f"{k}={v}"]
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_probe(args) -> int:
    store = _store(args)
    state = store.load()
    now = datetime.now(timezone.utc)
    sources = [s.strip() for s in args.sources.split(",")] if args.sources else list(SOURCES)
    dispatches = []
    for src in sources:
        if src not in PROBES:
            raise SystemExit(f"unknown source {src!r}")
        probe = run_probe(src)
        decision = decide(state.get(src), probe, now, POLICIES[src])
        entry = {**probe, "probed_at": now.isoformat(), **decision}
        print(json.dumps(entry, sort_keys=True))
        if args.dry_run:
            continue
        store.log(entry)
        store.save_row(apply_decision(state.get(src), src, probe, decision, now), PROBE_COLUMNS)
        if decision["action"] == "ingest":
            dispatches.append(dispatch_args(src, probe.get("fingerprint") or UNPROBED))
    if not args.dry_run:
        store.prune(now)
    if args.dispatch_out:
        Path(args.dispatch_out).write_text(
            "".join(json.dumps(d) + "\n" for d in dispatches))
    return 0


def ack_changes_content(previous_acked_fp: str | None, fingerprint: str) -> bool:
    """Whether an ack means new source content reached the database, i.e. the
    rebuild chain should run now. A max-age re-run of acknowledged content and
    a blind (unprobed) run do not; the daily chain and the hourly vintage
    check cover those."""
    return bool(fingerprint) and fingerprint != UNPROBED and fingerprint != previous_acked_fp


def cmd_ack(args) -> int:
    if args.source not in SOURCES:
        raise SystemExit(f"unknown source {args.source!r}")
    new_content = False
    if not args.fingerprint:
        print(f"{args.source}: no probe fingerprint (manual or scheduled run); nothing to ack")
    else:
        store = _store(args)
        state = store.load().get(args.source)
        new_content = ack_changes_content((state or {}).get("acked_fp"), args.fingerprint)
        row = apply_ack(state, args.source, args.fingerprint, datetime.now(timezone.utc))
        store.save_row(row, ACK_COLUMNS)
        print(f"{args.source}: acked {args.fingerprint} new_content={str(new_content).lower()}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"new_content={str(new_content).lower()}\n")
    return 0


WAITING_STATUSES = ("queued", "pending", "waiting", "requested")


def dispatch_chain(reason: str, run=None) -> str:
    """Dispatch rebuild-chain.yml unless a run is already waiting to start.

    The chain has one concurrency group (one run at a time, never cancelled).
    A run that has not started yet will read the database after this ingest's
    write, so a burst of changed ingests coalesces into that one queued run.
    Skipping also keeps a waiting run (e.g. the 11:45 bake) from being replaced:
    GitHub cancels an older pending run when a newer one joins the group.
    A run already in progress may have read the database before this write,
    so it does not count."""
    import subprocess
    run = run or (lambda argv: subprocess.run(argv, capture_output=True, text=True, check=True).stdout)
    out = run(["gh", "run", "list", "--workflow", "rebuild-chain.yml", "--limit", "20",
               "--json", "status,databaseId"])
    waiting = [r for r in json.loads(out or "[]") if r.get("status") in WAITING_STATUSES]
    if waiting:
        return f"skipped: rebuild-chain run {waiting[0].get('databaseId')} is already waiting"
    run(["gh", "workflow", "run", "rebuild-chain.yml", "-f", f"source={reason}"])
    return "dispatched"


def cmd_dispatch_chain(args) -> int:
    print(f"rebuild-chain ({args.reason}): {dispatch_chain(args.reason)}")
    return 0


def cmd_show(args) -> int:
    print(json.dumps(_store(args).load(), indent=2, sort_keys=True, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    dc = sub.add_parser("dispatch-chain")
    dc.add_argument("--reason", required=True)
    for name in ("probe", "ack", "show"):
        p = sub.add_parser(name)
        g = p.add_mutually_exclusive_group()
        g.add_argument("--state-file", default=str(ROOT / "output" / "source-probe-state.json"))
        g.add_argument("--supabase", action="store_true")
        if name == "probe":
            p.add_argument("--sources", default="")
            p.add_argument("--dispatch-out", default="")
            p.add_argument("--dry-run", action="store_true",
                           help="probe and decide, write nothing")
        if name == "ack":
            p.add_argument("--source", required=True)
            p.add_argument("--fingerprint", default="")
    args = ap.parse_args(argv)
    return {"probe": cmd_probe, "ack": cmd_ack, "show": cmd_show,
            "dispatch-chain": cmd_dispatch_chain}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
