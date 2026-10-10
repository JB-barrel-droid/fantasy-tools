#!/usr/bin/env python3
"""Data fidelity pulse (JEG-480): publisher site -> stored raw -> live chart.

Jeremy, 2026-10-08: "Data fidelity is the most critical part of the project,
else it's just junk and will lose the audience."

For each source this checks, end to end:

  1. publisher_vs_stored   Re-reads the publisher's live page or API and
                           compares every player's value with the newest bake
                           stored in Supabase for that week, in every scoring
                           and the superflex / 2-QB columns. Flags players the
                           publisher lists that are not stored, stored players
                           the publisher does not list, value mismatches, a
                           page whose week is not the stored week, and an
                           article that is not the one the stored rows name.
  2. stored_vs_chart       The live site's published native values (the
                           deployed assets/comparison-sources-data.json the
                           page loads) equal the stored bake the chart was
                           built from, player by player.
  3. freshness             The publisher has posted a newer week than the
                           live chart shows.
  4. reference_vs_engine   The JEG-479 engine-vs-Python-reference report
                           (value-check.json), when one is published.
  5. scrape_validity       Signals the scrape may have missed: sudden player
                           count drops per position (vs the prior week's
                           history) and per position x tier (vs the prior
                           week's pulse), thin or identity-fallback adjustment
                           cells, JEG-482 published-rank inversions.

Sources: the trade charts (USA Today, FantasyCalc, FantasyPros, CBS) are read
here; the projection sources (ESPN, CBS rest of season, Razzball) through
pipelines/fidelity_sources/<source>.py (contract in its __init__).

Independence. The publisher pages are parsed here with the standard library's
HTML parser (a DOM-style table walk keyed on column headers), not with the
ingest scrapers' regular expressions (ops/watchdog/pull_*.py), so a scraper
bug cannot hide itself by being run twice. Articles are discovered here
independently too (sitemaps, news sitemap, URL candidates) and the result is
compared with the article URL the stored rows name. Shared on purpose: the
fetch transport for USA Today (the Supabase relay, ops/watchdog/pull_usatoday.
fetch_via_relay: usatoday.com walls GitHub runner IPs) and the canonical
player resolver (pipelines/lib/canonical_players.py + player_aliases.py),
because the stored rows are keyed by the same player_key.

Match rule (stated, not tuned): exact. A stored native value matches the
publisher when it equals the number the publisher printed, which already
carries the publisher's own rounding (only float storage noise below 1e-9 is
ignored: a stored 36.4 against a printed 36 is a mismatch). The chart's
native value matches the stored bake when the two are equal to 1e-9.
There is no tolerance band, with one stated exception: FantasyCalc is a live
crowd feed with no versioned snapshot, so a difference from the stored bake
is movement since the save (amber, listed) unless it is systemic, a column
swap, or a player missing above the list's churn line (red); see RULES.
Players the page's player universe excludes (the chart file's player_keys)
are amber and listed by name rather than red: the publisher values them, the
page by design cannot show them.

Status per stage: red = wrong or missing numbers; amber = known, explainable
lag (publisher revised or posted a new week inside the grace window, a newer
stored bake the chart has not picked up, publisher names our canonical table
cannot resolve); unknown = the check could not read an input; n/a = the stage
does not apply or its input is not published yet. A source is the worst of
its stages (unknown counts as amber). Never blocks a deploy.

    python3 pipelines/fidelity_pulse.py --out output/fidelity-pulse.json \
        [--sources usatoday,cbs] [--write-supabase] [--offline-dir DIR]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "pipelines", ROOT / "pipelines" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SCHEMA = "fidelity-pulse/1"
CHECK_NAME = "fidelity_pulse"
SEASON = 2026
SITE = "https://jb-barrel-droid.github.io/fantasy-tools/"
SITE_FIXTURE = SITE + "assets/comparison-sources-data.json"
VALUE_CHECK_PATHS = ("output/value-check.json", "dist/modules/value-check.json")
VALUE_CHECK_URL = SITE + "modules/value-check.json"
UA = "DataDrivenFootball-fidelity-pulse/1.0 (+https://jb-barrel-droid.github.io/fantasy-tools/modules/status.html)"
HOST_GAP_S = 1.0           # politeness: at least this long between two requests to one host

GRACE_HOURS = 24           # a publisher revision after the save is 'update available' (amber) this long, then stale (red)
NEW_WEEK_GRACE_HOURS = 24  # a newer publisher week inside this window is amber, after it red
FC_DRIFT_REL = 0.25        # FantasyCalc movement band (relative to the stored value), see docstring
FC_DRIFT_ABS = 50          # ... or this many FantasyCalc points, whichever is larger
FC_SYSTEMIC_SHARE = 0.10   # more than this share of values outside the band is a broken save, not movement
FC_SWAP_RATIO = 1.5        # a stored list this much closer to another live list than to its own is a column swap
EXAMPLES = 8
MAX_DIVERGENCE_ROWS = 200  # per source per run, written to public.fidelity_divergences

TRADE_CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
PROJECTIONS = ("espn", "cbsros", "razzball")  # readers: pipelines/fidelity_sources/<source>.py
SOURCES = TRADE_CHARTS + PROJECTIONS
LABEL = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS",
         "espn": "ESPN", "cbsros": "CBS rest of season", "razzball": "Razzball"}
NOT_COVERED: dict[str, str] = {}
PROJECTION_AMBER_DAYS = 1  # projections are re-read daily (ingest on change, at least every 20 h)
PROJECTION_RED_DAYS = 3
# JEG-520 / JEG-480 (2026-10-09): projections change during the day (ESPN moved
# Pat Bryant to injured reserve at 20:17Z, after the 19:25Z save, and re-spread
# Denver's receivers). A stage-1 difference is a fault only when the publisher
# still serves the content the save was made from: the source probe's
# fingerprint (pipelines/source_probe.py) recorded with the save (acked_fp)
# equals the fingerprint read now. A changed fingerprint is a daily update
# waiting for the next ingest (amber) while the save is younger than
# PROJECTION_STALE_HOURS; after that the stored copy is stale (red).
PROJECTION_STALE_HOURS = 24
ACK_MATCH_MINUTES = 15     # an ack this close to the stored save names the content that save read
BLOCK_SHARE = 0.10         # missing + extra players above this share of a position is a block, never an update
BLOCK_MIN = 3              # ... and at least this many players
DROP_AMBER = 0.95          # a position's player count below this share of the prior week is amber (alert only)
DROP_RED = 0.90            # ... below this share (a drop of more than 10%), red and held, when the publisher's
                           # own list did not drop with it (Jeremy 2026-10-09, JEG-520: hold only on big drops)
THIN_CELL = 5              # an adjustment cell fitted on fewer players is thin (amber)
TIER_DROP = 0.60           # a tier's count below this share of the prior week's pulse is amber
SCORINGS = ("std", "half", "full")
STAGES = ("publisher_vs_stored", "stored_vs_chart", "freshness", "reference_vs_engine", "scrape_validity")
RANK = {"green": 0, "n/a": 0, "amber": 1, "unknown": 1, "red": 2}
# JEG-520: the stages whose red holds the source (reference_vs_engine reds are held by the JEG-479 value check).
HOLD_STAGES = ("publisher_vs_stored", "stored_vs_chart", "freshness", "scrape_validity")
HOLD_PREFIX = "fidelity: "

# Stored scoring labels per table, and the chart's combo names.
STORED_SCORING = {
    "cbs": {"standard": "std", "half_ppr": "half", "ppr": "full"},
    "default": {"std": "std", "half": "half", "full": "full"},
}
SITE_COMBO = {"std": "standard_12", "half": "half_12", "full": "full_12"}

RULES = {
    "match": "exact: the stored native equals the number the publisher printed (its own rounding; float noise "
             "below 1e-9 ignored); the chart native equals the stored native to 1e-9",
    "publisher_vs_stored": "red on any publisher player missing from the stored bake, stored player not on the "
                           "publisher page, value mismatch, page week != stored week, or a different article; "
                           f"amber when the publisher revised the page after the save and less than {GRACE_HOURS} h ago, "
                           "or when publisher names do not resolve to a canonical player",
    "fantasycalc": "FantasyCalc is a live crowd feed with no versioned snapshot, so values that moved since the save "
                   "are amber and listed (players outside the max("
                   f"{FC_DRIFT_REL:.0%}, {FC_DRIFT_ABS} points) band by name). Red: more than {FC_SYSTEMIC_SHARE:.0%} of values "
                   "outside that band (a broken save, not movement); a stored list closer to another live list "
                   f"(scoring or QB setting) than to its own by {FC_SWAP_RATIO}x (column swap); a player above the list's "
                   "churn line (its 15th-percentile value) on one side only",
    "universe": "players the chart's player universe (the chart file's player_keys) excludes are amber and listed "
                "by name: the publisher values them, the page cannot show them",
    "stored_vs_chart": "red on any difference between the live chart's native values and the stored bake the chart "
                       "was built from; amber when a newer stored bake (different values) is not on the chart yet",
    "freshness": f"amber when the publisher posted a newer week than the chart shows less than {NEW_WEEK_GRACE_HOURS} h "
                 "ago, red after that",
    "reference_vs_engine": "red when the JEG-479 value check reports a disagreement for the source; n/a while no "
                           "report is published",
    "projections": "ESPN, CBS rest of season, Razzball: stage 1 compares the publisher's own numbers with the "
                   "newest stored snapshot in the publisher's unit (ESPN and CBS rest-of-season totals, Razzball per "
                   "game), exactly. A difference is red when the publisher still serves the content the save read "
                   "(the source probe's fingerprint recorded with the save equals the one read now: stored != "
                   "same-version publisher), or when a block of players is missing or extra (more than "
                   f"{BLOCK_SHARE:.0%} of a position, at least {BLOCK_MIN}). It is amber while the publisher's own "
                   f"update stamp is newer than the snapshot (inside {GRACE_HOURS} h), the change probe has seen "
                   "content no ingest saved yet, or the fingerprint changed since the save (a daily update; red once "
                   f"the save is older than {PROJECTION_STALE_HOURS} h: stale), and amber 'unconfirmed' when no "
                   "fingerprint was recorded with the save or none can be read now. Stage 2: the chart's per-game native equals the stored snapshot it was built from, "
                   "rounded half-up to the chart's printed decimals. Stage 3: chart snapshot older than "
                   f"{PROJECTION_AMBER_DAYS} d amber, {PROJECTION_RED_DAYS} d red, or the publisher's own update "
                   "date is newer than the chart's",
    "scrape_validity": "signals that a scrape may have missed (Jeremy 2026-10-09): a position's stored or chart "
                       f"player count below {DROP_AMBER:.0%} of the prior week's is amber (alert only), below "
                       f"{DROP_RED:.0%} red (held) when the publisher's own list for that position did not drop below "
                       f"{DROP_RED:.0%} too (if it did, or it was not read, amber); "
                       f"an adjustment cell fitted on fewer than {THIN_CELL} players, an identity-fallback cell, or a "
                       f"position x tier count below {TIER_DROP:.0%} of the prior week's pulse is amber; JEG-482 "
                       "published-rank inversions are red. A player absent from a fully loaded chart means 0; "
                       "absences that may be processing errors are stages 1 and 2",
    "rollup": "a source is the worst of its stages; unknown (input unreadable) counts as amber",
    "hold": "JEG-520: a red in publisher_vs_stored, stored_vs_chart, freshness or scrape_validity holds that source "
            "and its derived series (the chain's validationHold, reason 'fidelity: <stage>'): kept out of DDF Value, "
            "labelled, a published chart served from its last good section. Amber and unknown never hold; "
            "reference_vs_engine reds are already held by the JEG-479 value check. While held, stored_vs_chart is "
            "n/a (the chart shows the kept section) unless the hold was stored_vs_chart on the same stored save, "
            "which stays red until a newer save; freshness reads the stored week or snapshot instead of the chart's.",
    "tolerance": "per-source tolerance (JEG-520, measured in docs/fidelity-tolerances.md): FantasyCalc live-feed "
                 f"movement band max({FC_DRIFT_REL:.0%}, {FC_DRIFT_ABS} points), red only above {FC_SYSTEMIC_SHARE:.0%} "
                 "of values outside it; article charts exact against the same article version, a later revision is "
                 f"'update available' for {GRACE_HOURS} h, then stale; projections exact against the same publisher "
                 f"version (probe fingerprint), a changed version amber for {PROJECTION_STALE_HOURS} h, then stale",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s[:10])
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def worst(*statuses) -> str:
    flat = [s for s in statuses if s]
    return max(flat, key=lambda s: RANK.get(s, 1), default="green")


def rollup(status: str) -> str:
    """A stage status as it counts toward the source status."""
    return {"unknown": "amber", "n/a": "green"}.get(status, status)


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------

class Fetcher:
    """Polite HTTP GET: honest User-Agent, one request per host per HOST_GAP_S,
    gzip, one retry on a network error or 5xx. Returns (status, text, final_url)."""

    BLOCKED = (401, 402, 403, 429)

    def __init__(self, gap_s: float = HOST_GAP_S, relay: Callable | None = None):
        self.gap_s = gap_s
        self.last: dict[str, float] = {}
        self.relay = relay
        self.log: list[dict] = []

    def _wait(self, host: str) -> None:
        delay = self.last.get(host, 0) + self.gap_s - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last[host] = time.monotonic()

    def get(self, url: str, timeout: float = 60, headers: dict | None = None) -> tuple[int, str, str]:
        host = urllib.parse.urlparse(url).hostname or ""
        status, text = 0, ""
        for attempt in (1, 2):
            self._wait(host)
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Encoding": "gzip",
                "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.5", **(headers or {})})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    status, text = r.status, raw.decode("utf-8", "replace")
                    break
            except urllib.error.HTTPError as e:
                status, text = e.code, ""
                if e.code < 500:
                    break
            except Exception as e:  # noqa: BLE001 - network error: retry once, then report status 0
                status, text = 0, f"{type(e).__name__}: {e}"
        via = "direct"
        if status in self.BLOCKED and self.relay and host.endswith("usatoday.com"):
            got = self.relay(url)
            if got:
                status, text, via = got[0], got[1], "supabase relay"
        self.log.append({"url": url, "status": status, "via": via})
        return status, text, url


def usatoday_relay(url: str):
    """The ingest's own fetch transport for usatoday.com (Supabase Edge Function
    `usatoday-fetch`): GitHub runner IPs get HTTP 402. Transport only; its
    parsing code is not used."""
    sys.path.insert(0, str(ROOT / "ops" / "watchdog"))
    try:
        from pull_usatoday import fetch_via_relay  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    return fetch_via_relay(url)


# --------------------------------------------------------------------------
# Independent HTML table reader (stdlib html.parser, keyed on headers)
# --------------------------------------------------------------------------

@dataclass
class Table:
    heading: str
    rows: list[list[str]] = field(default_factory=list)


class _TableParser(HTMLParser):
    """Every <table> as rows of cell texts, with the text of the last heading
    (h1-h4) or <caption> before it. Nested markup inside cells is flattened."""

    HEADINGS = ("h1", "h2", "h3", "h4", "caption")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self.title = ""
        self._heading = ""
        self._hbuf: list[str] | None = None
        self._tbuf: list[str] | None = None
        self._table: Table | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._tbuf = []
        elif tag in self.HEADINGS:
            self._hbuf = []
        elif tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._table = Table(self._heading)
        elif tag == "tr" and self._table is not None and self._depth == 1:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "title" and self._tbuf is not None:
            # The document title is the first <title>; later ones are SVG icon titles.
            self.title = self.title or " ".join("".join(self._tbuf).split())
            self._tbuf = None
        elif tag in self.HEADINGS and self._hbuf is not None:
            text = " ".join("".join(self._hbuf).split())
            if text:
                self._heading = text
                if tag == "caption" and self._table is not None:
                    self._table.heading = text
            self._hbuf = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._depth == 1 and self._table is not None:
                self.tables.append(self._table)
                self._table = None
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._tbuf is not None:
            self._tbuf.append(data)
        if self._hbuf is not None:
            self._hbuf.append(data)
        if self._cell is not None:
            self._cell.append(data)


def parse_page(html: str) -> tuple[str, list[Table]]:
    p = _TableParser()
    p.feed(html or "")
    p.close()
    return p.title, p.tables


def json_ld_dates(html: str) -> dict:
    """dateModified / datePublished from the page's structured data."""
    out = {}
    for key in ("dateModified", "datePublished"):
        m = re.search(r'"%s"\s*:\s*"([^"]+)"' % key, html or "")
        out[key] = m.group(1) if m else None
    return out


POSITION_WORDS = (("quarterback", "QB"), ("running back", "RB"), ("wide receiver", "WR"), ("tight end", "TE"))


def position_of(heading: str) -> str | None:
    h = (heading or "").lower()
    hits = {pos for word, pos in POSITION_WORDS if word in h}
    return hits.pop() if len(hits) == 1 else None


def header_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


@dataclass
class PubRow:
    name: str
    pos: str
    team: str | None
    values: dict  # grain -> printed text


# Column meaning per publisher: header_key -> list of grains it feeds.
# A grain is "<scoring>|<qb_slots>". QB values are published once (no
# per-scoring QB column), so the 1-QB column feeds every scoring, and the
# superflex / 2-QB column feeds qb_slots 2 (each source's documented rule).
ALL_QB1 = [f"{s}|1" for s in SCORINGS]
ALL_QB2 = [f"{s}|2" for s in SCORINGS]
COLUMNS = {
    "usatoday": {"name": ("player",), "team": (),
                 "QB": {"1qb": ALL_QB1, "sflex": ALL_QB2, "superflex": ALL_QB2},
                 "other": {"std": ["std|1"], "standard": ["std|1"], "half": ["half|1"], "halfppr": ["half|1"],
                           "ppr": ["full|1"], "full": ["full|1"], "fullppr": ["full|1"]}},
    "cbs": {"name": ("player",), "team": ("tm", "team"),
            "QB": {"1qb4": ALL_QB1, "2qb": ALL_QB2},
            "other": {"non": ["std|1"], "05": ["half|1"], "ppr": ["full|1"]}},
    "fantasypros": {"name": ("name", "player"), "team": ("team",),
                    "QB": {"value": ALL_QB1, "2qbvalue": ALL_QB2},
                    "other": {"value": ALL_QB1}},
}


def read_tables(source: str, tables: list[Table]) -> tuple[list[PubRow], list[str]]:
    """Publisher rows from a chart article's position tables. Returns (rows, notes)."""
    spec = COLUMNS[source]
    rows: list[PubRow] = []
    notes: list[str] = []
    seen_pos: dict[str, int] = {}
    for t in tables:
        pos = position_of(t.heading)
        if not pos or not t.rows:
            continue
        header = [header_key(h) for h in t.rows[0]]
        name_i = next((i for i, h in enumerate(header) if h in spec["name"]), None)
        if name_i is None:
            notes.append(f"{pos} table '{t.heading[:60]}': no player column in header {t.rows[0]}")
            continue
        team_i = next((i for i, h in enumerate(header) if h in spec["team"]), None)
        colmap = spec["QB"] if pos == "QB" else spec["other"]
        cols = {i: colmap[h] for i, h in enumerate(header) if h in colmap}
        if not cols:
            notes.append(f"{pos} table '{t.heading[:60]}': no value column in header {t.rows[0]}")
            continue
        seen_pos[pos] = seen_pos.get(pos, 0) + 1
        for r in t.rows[1:]:
            if len(r) <= name_i or not r[name_i] or header_key(r[name_i]) in spec["name"]:
                continue
            values = {}
            for i, grains in cols.items():
                cell = r[i].strip() if i < len(r) else ""
                if NUMBER.match(cell):
                    for g in grains:
                        values[g] = cell
            rows.append(PubRow(r[name_i], pos, r[team_i] if team_i is not None and team_i < len(r) else None, values))
    missing = [p for _, p in POSITION_WORDS if p not in seen_pos]
    if missing:
        notes.append(f"no table found for {', '.join(missing)}")
    dup = [p for p, n in seen_pos.items() if n > 1]
    if dup:
        notes.append(f"more than one table for {', '.join(dup)} (values merged, last wins)")
    return rows, notes


def read_fantasycalc(payloads: dict) -> tuple[list[PubRow], list[str]]:
    """payloads: grain -> FantasyCalc API list. One row per player across grains."""
    by_id: dict[Any, PubRow] = {}
    notes = []
    for grain, payload in payloads.items():
        if not isinstance(payload, list):
            notes.append(f"{grain}: API answer is not a list")
            continue
        for item in payload:
            pl = (item or {}).get("player") or {}
            val = item.get("value") if isinstance(item, dict) else None
            if not pl.get("name") or val is None:
                continue
            pid = pl.get("id") or pl.get("name")
            row = by_id.setdefault(pid, PubRow(pl["name"], str(pl.get("position") or "").upper(),
                                               pl.get("maybeTeam"), {}))
            row.values[grain] = str(int(val)) if float(val).is_integer() else str(val)
    return list(by_id.values()), notes


def page_week(url: str, title: str) -> tuple[int | None, str | None]:
    """(week, problem). Week from the URL slug and the page title; they must agree."""
    mu = re.search(r"week-(\d{1,2})(?!\d)", url or "", re.I)
    mt = re.search(r"\bweek\s*(\d{1,2})\b", title or "", re.I)
    wu, wt = (int(mu.group(1)) if mu else None), (int(mt.group(1)) if mt else None)
    if wu is not None and wt is not None and wu != wt:
        return None, f"URL says week {wu}, title says week {wt}"
    if wu is None and wt is None:
        return None, "no week in URL or title"
    return (wu if wu is not None else wt), None


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

class Identity:
    """Canonical player resolution (public.players + the verified alias list)."""

    def __init__(self, registry):
        self.reg = registry

    @classmethod
    def load(cls, player_rows: list[dict] | None = None) -> "Identity":
        import canonical_players  # noqa: PLC0415
        if player_rows is not None:
            return cls(canonical_players.load_registry(player_rows))
        return cls(canonical_players.load_registry())

    def resolve(self, name: str, pos: str | None) -> tuple[int | None, str]:
        import canonical_players  # noqa: PLC0415
        return canonical_players.resolve_with_reason(name, position=pos, registry=self.reg)

    def resolve_any(self, name: str) -> int | None:
        import canonical_players  # noqa: PLC0415
        return canonical_players.resolve_skill(name, registry=self.reg)

    def name(self, key) -> str | None:
        e = self.reg.by_key.get(int(key)) if key is not None else None
        return e["full_name"] if e else None

    def uuid(self, key) -> str | None:
        e = self.reg.by_key.get(int(key)) if key is not None else None
        return e.get("uuid") if e else None

    def pos(self, key) -> str | None:
        e = self.reg.by_key.get(int(key)) if key is not None else None
        return e["position"] if e else None


def publisher_grains(rows: list[PubRow], ident: Identity) -> tuple[dict, list[dict]]:
    """{grain: {player_key: cell}} and the names that did not resolve."""
    grains: dict[str, dict] = {}
    unresolved = []
    for r in rows:
        key, reason = ident.resolve(r.name, r.pos)
        if key is None:
            unresolved.append({"name": r.name, "pos": r.pos, "team": r.team, "reason": reason,
                               "values": dict(sorted(r.values.items()))})
            continue
        for g, text in r.values.items():
            grains.setdefault(g, {})[key] = {"value": float(text), "text": text, "name": r.name, "pos": r.pos}
    return grains, unresolved


# --------------------------------------------------------------------------
# Stored raw (Supabase)
# --------------------------------------------------------------------------

STORED_COLUMNS = "player_key,player_norm,position,scoring,qb_slots,week,bake_id,native_value,created_at,pulled_at,source_url"


def stored_table(source: str) -> str:
    return "cbs_trade_values" if source == "cbs" else "source_trade_values"


class SupabaseStore:
    """Reads (and the history write) through the env-based sbclient."""

    def __init__(self):
        import gh_sbclient as sb  # noqa: PLC0415
        self.sb = sb

    def latest_week(self, source: str) -> int | None:
        rows = self.sb.get(stored_table(source),
                           f"?select=week&source=eq.{source}&variant=eq.as_published&season=eq.{SEASON}"
                           "&or=(qb_slots.is.null,qb_slots.eq.1)&week=not.is.null&order=week.desc&limit=1")
        return int(rows[0]["week"]) if rows else None

    def rows(self, source: str, week: int) -> list[dict]:
        return self.sb.get_all(stored_table(source),
                               f"?select=id,{STORED_COLUMNS}&source=eq.{source}&variant=eq.as_published"
                               f"&season=eq.{SEASON}&week=eq.{week}")

    def players(self) -> list[dict] | None:
        return None  # canonical_players.load_registry reads public.players itself

    def latest_snapshot(self, mod) -> str | None:
        rows = self.sb.get(mod.STORED_TABLE, f"?select={mod.SNAPSHOT_COLUMN}&{mod.SNAPSHOT_COLUMN}=not.is.null"
                                             f"&order={mod.SNAPSHOT_COLUMN}.desc&limit=1")
        return str(rows[0][mod.SNAPSHOT_COLUMN]) if rows else None

    def snapshot_rows(self, mod, snapshot: str) -> list[dict]:
        return self.sb.get_all(mod.STORED_TABLE, f"?select=id,_written_at,{mod.STORED_SELECT}"
                                                 f"&{mod.SNAPSHOT_COLUMN}=eq.{snapshot}")

    def probe_state(self, source: str) -> dict | None:
        rows = self.sb.get("source_probe_state", f"?select=*&source=eq.{source}")
        return rows[0] if rows else None

    def live_fingerprint(self, source: str) -> dict | None:
        """The source probe's fingerprint of what the publisher serves now (same function the ingest acks)."""
        import source_probe  # noqa: PLC0415
        return source_probe.run_probe(source)

    def prior_pulse(self) -> dict:
        """{source: {week: tier_counts}} from earlier pulse runs (latest run per source and week)."""
        rows = self.sb.get("fidelity_runs", "?select=source,week,checks,finished_at&check_name=eq.fidelity_pulse"
                                            "&order=finished_at.desc&limit=500")
        out: dict = {}
        for r in rows:
            tiers = (((r.get("checks") or {}).get("scrape_validity") or {}).get("signals") or {}).get("tier_counts")
            if tiers and r.get("week") is not None:
                out.setdefault(r["source"], {}).setdefault(int(r["week"]), tiers)
        return out


class OfflineStore:
    """Test / local seam: stored_<source>.json files ({"rows": [...]}) and players.json."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def _doc(self, source):
        p = self.dir / f"stored_{source}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"rows": []}

    def latest_week(self, source):
        weeks = [r["week"] for r in self._doc(source)["rows"]
                 if r.get("week") is not None and (r.get("qb_slots") in (None, 1))]
        return max(weeks) if weeks else None

    def rows(self, source, week):
        return [r for r in self._doc(source)["rows"] if r.get("week") == week]

    def players(self):
        p = self.dir / "players.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def latest_snapshot(self, mod):
        dates = [str(r[mod.SNAPSHOT_COLUMN]) for r in self._doc(mod.SOURCE)["rows"] if r.get(mod.SNAPSHOT_COLUMN)]
        return max(dates) if dates else None

    def snapshot_rows(self, mod, snapshot):
        return [r for r in self._doc(mod.SOURCE)["rows"] if str(r.get(mod.SNAPSHOT_COLUMN)) == str(snapshot)]

    def probe_state(self, source):
        p = self.dir / "probe_state.json"
        return (json.loads(p.read_text(encoding="utf-8")).get(source) if p.exists() else None)

    def live_fingerprint(self, source):
        p = self.dir / "live_fingerprint.json"
        return (json.loads(p.read_text(encoding="utf-8")).get(source) if p.exists() else None)


def group_bakes(rows: list[dict]) -> list[dict]:
    """Bakes of one week, oldest first: id, saved_at (max created_at), pulled_at, url, rows."""
    bakes: dict[Any, list[dict]] = {}
    for r in rows:
        bakes.setdefault(r.get("bake_id"), []).append(r)
    out = []
    for bid, rs in bakes.items():
        urls = {r.get("source_url") for r in rs if r.get("source_url")}
        out.append({"bake_id": bid,
                    "saved_at": max((parse_ts(r.get("created_at")) for r in rs if r.get("created_at")),
                                    default=None),
                    "pulled_at": max((parse_ts(r.get("pulled_at")) for r in rs if r.get("pulled_at")),
                                     default=None),
                    "source_url": urls.pop() if len(urls) == 1 else None,
                    "source_urls": sorted(urls) if len(urls) > 1 else None,
                    "rows": rs})
    floor = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(out, key=lambda b: (b["saved_at"] or floor, str(b["bake_id"] or "")))


def stored_grains(source: str, rows: list[dict], ident: Identity | None = None) -> tuple[dict, list[dict]]:
    """{grain: {player_key: cell}} from one bake's rows; rows without a key or value are listed."""
    scoring_map = STORED_SCORING.get(source, STORED_SCORING["default"])
    grains: dict[str, dict] = {}
    bad = []
    for r in rows:
        s = scoring_map.get(str(r.get("scoring") or "").lower())
        qb = int(r.get("qb_slots") or 1)
        key, val = r.get("player_key"), r.get("native_value")
        if s is None or key is None or val is None:
            bad.append({"player_norm": r.get("player_norm"), "scoring": r.get("scoring"), "qb_slots": qb,
                        "player_key": key, "native_value": val})
            continue
        name = (ident.name(key) if ident else None) or r.get("player_norm")
        grains.setdefault(f"{s}|{qb}", {})[int(key)] = {"value": float(val), "text": None, "name": name,
                                                        "pos": r.get("position")}
    return grains, bad


# --------------------------------------------------------------------------
# Live chart (the deployed fixture the page loads)
# --------------------------------------------------------------------------

def site_section(doc: dict, source: str) -> dict:
    return ((doc or {}).get("sources") or {}).get(source) or {}


def site_meta(doc: dict, source: str) -> dict:
    sec = site_section(doc, source)
    prov = sec.get("source_provenance") or {}
    week = prov.get("week_designated")
    if week is None:
        m = re.search(r"(\d+)", str(sec.get("week_designated") or ""))
        week = int(m.group(1)) if m else None
    return {"week": int(week) if week is not None else None,
            "imported_at": prov.get("source_pulled_at"),
            "snapshot_fetched_at": prov.get("snapshot_fetched_at") or sec.get("fetched_at"),
            "url": prov.get("source_url") or sec.get("url"),
            "content_vintage": sec.get("content_vintage") or prov.get("content_vintage")}


def site_grains(doc: dict, source: str, ident: Identity | None = None) -> tuple[dict, list[dict]]:
    """{grain: {player_key: cell}} from the chart's native (1-QB) and native_superflex (2-QB) maps."""
    sec = site_section(doc, source)
    top_keys = (doc or {}).get("player_keys") or {}
    combos = sec.get("combos") or {}
    grains: dict[str, dict] = {}
    unresolved = []
    for s, combo in SITE_COMBO.items():
        c = combos.get(combo) or combos.get(f"{combo}_qb1")
        if not c:
            continue
        keys = {**top_keys, **(c.get("player_keys") or {})}
        for field_name, qb in (("native", 1), ("native_superflex", 2)):
            for slug, val in (c.get(field_name) or {}).items():
                if val is None:
                    continue
                key = keys.get(slug)
                if key is None and ident is not None:
                    key = ident.resolve_any(slug)
                if key is None:
                    unresolved.append({"slug": slug, "grain": f"{s}|{qb}", "value": val})
                    continue
                grains.setdefault(f"{s}|{qb}", {})[int(key)] = {"value": float(val), "text": None, "name": slug,
                                                                "pos": None}
    return grains, unresolved


# --------------------------------------------------------------------------
# Comparison (pure)
# --------------------------------------------------------------------------

def decimals(text: str | None) -> int:
    return len(text.split(".", 1)[1]) if text and "." in text else 0


def equal_after_rounding(printed: str, stored: float) -> bool:
    """Exact rule: the stored native equals the number the publisher printed
    (which already carries the publisher's own rounding). Only float storage
    noise is ignored (the stored value is read to 9 decimals); a stored 36.4
    against a printed 36 is a mismatch, not a rounding."""
    try:
        return (Decimal(repr(float(stored))).quantize(Decimal("1e-9"), rounding=ROUND_HALF_UP)
                == Decimal(printed).quantize(Decimal("1e-9")))
    except (InvalidOperation, ValueError):
        return False


def compare(left: dict, right: dict, *, printed: bool) -> dict:
    """Player-by-player comparison of two {grain: {key: cell}} maps.

    printed=True: left carries the publisher's printed text (exact after its
    rounding). printed=False: both are our copies; equal to 1e-9.
    missing = in left, not in right; extra = in right, not in left."""
    out = {"compared": 0, "matched": 0, "mismatches": [], "missing": [], "extra": [], "grains": {}}
    for g in sorted(set(left) | set(right)):
        L, R = left.get(g, {}), right.get(g, {})
        gm = {"left": len(L), "right": len(R), "mismatched": 0, "missing": 0, "extra": 0}
        for k in sorted(L.keys() & R.keys()):
            out["compared"] += 1
            lv, rv = L[k], R[k]
            same = ((equal_after_rounding(lv["text"], rv["value"])
                     or (lv.get("text_alt") is not None and equal_after_rounding(lv["text_alt"], rv["value"])))
                    if printed and lv.get("text") is not None
                    else abs(lv["value"] - rv["value"]) <= 1e-9)
            if same:
                out["matched"] += 1
                continue
            gm["mismatched"] += 1
            out["mismatches"].append({"type": "value_mismatch", "grain": g, "player_key": k,
                                      "name": lv.get("name") or rv.get("name"), "pos": lv.get("pos") or rv.get("pos"),
                                      "left": lv.get("text") if printed and lv.get("text") is not None else lv["value"],
                                      "right": rv["value"], "delta": round(rv["value"] - lv["value"], 6)})
        for k in sorted(L.keys() - R.keys()):
            gm["missing"] += 1
            out["missing"].append({"type": "missing", "grain": g, "player_key": k, "name": L[k].get("name"),
                                   "pos": L[k].get("pos"), "left": L[k].get("text") or L[k]["value"], "right": None})
        for k in sorted(R.keys() - L.keys()):
            gm["extra"] += 1
            out["extra"].append({"type": "extra", "grain": g, "player_key": k, "name": R[k].get("name"),
                                 "pos": R[k].get("pos"), "left": None, "right": R[k]["value"]})
        out["grains"][g] = gm
    return out


def worst_examples(cmp: dict, n: int = EXAMPLES) -> list[dict]:
    """Largest value differences first, then the most valuable missing / extra players."""
    mism = sorted(cmp["mismatches"], key=lambda m: -abs(m["delta"]))
    gone = sorted(cmp["missing"] + cmp["extra"],
                  key=lambda m: -float(m["left"] if m["left"] is not None else m["right"] or 0))
    out, seen = [], set()
    for m in mism[: n // 2 + 1] + gone[: n // 2] + mism[n // 2 + 1:] + gone[n // 2:]:
        ident = (m["type"], m["grain"], m["player_key"])
        if ident not in seen:
            seen.add(ident)
            out.append(m)
        if len(out) >= n:
            break
    return out


def players(items: list[dict]) -> int:
    """Distinct players among per-column entries."""
    return len({m["player_key"] for m in items})


def problem_count(cmp: dict) -> int:
    return len(cmp["mismatches"]) + len(cmp["missing"]) + len(cmp["extra"])


def chart_universe(site_doc: dict | None) -> set[int]:
    """The players the page can show (the chart file's player_keys). A section
    drops a player outside it (pipelines/build_week_history.py notes CBS week 5
    pricing Tyreek Hill, who is not in it)."""
    return {int(v) for v in ((site_doc or {}).get("player_keys") or {}).values() if v is not None}


def split_universe(cmp: dict, side: str, universe: set[int]) -> list[dict]:
    """Move cmp[side] entries for players outside the page's universe to
    cmp['outside_universe'] and return them grouped one per player."""
    if not universe:
        return []
    keep, out = [], []
    for m in cmp[side]:
        (keep if m["player_key"] in universe else out).append(m)
    cmp[side] = keep
    cmp.setdefault("outside_universe", []).extend(out)
    players: dict[int, dict] = {}
    for m in out:
        p = players.setdefault(m["player_key"], {"player_key": m["player_key"], "name": m.get("name"),
                                                 "pos": m.get("pos"), "values": {}})
        p["values"][m["grain"]] = m["left"] if m["left"] is not None else m["right"]
    return sorted(players.values(), key=lambda p: -max(float(v) for v in p["values"].values()))


def stage(status: str, summary: str, **kw) -> dict:
    return {"status": status, "summary": summary, **kw}


def divergence_items(cmp: dict) -> list[dict]:
    """Every per-player difference of a comparison, typed for the history table."""
    out = list(cmp.get("mismatches", [])) + list(cmp.get("missing", [])) + list(cmp.get("extra", []))
    out += [dict(m, type="outside_universe") for m in cmp.get("outside_universe", [])]
    out += [dict(m, type="list_churn") for m in cmp.get("churn", [])]
    return out


# --------------------------------------------------------------------------
# Publisher reads (discovery + fetch + independent parse)
# --------------------------------------------------------------------------

def article_key(u: str | None) -> str:
    """An article's identity: host + path without date directories. FantasyPros
    serves one article under several /YYYY/MM/ paths (the week-5 chart answers
    identically at /2026/09/ and /2026/10/), so the date part is not identity."""
    if not u:
        return ""
    p = urllib.parse.urlparse(u.strip())
    segs = [s for s in p.path.split("/") if s and not re.fullmatch(r"\d{2}|\d{4}", s)]
    return f"{p.netloc.lower().removeprefix('www.')}/{'/'.join(segs)}"


def sitemap_entries(xml: str) -> list[tuple[str, str | None]]:
    """(loc, lastmod or news publication date) for each <url> of a sitemap."""
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml or "", re.S):
        loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
        mod = re.search(r"<(?:lastmod|news:publication_date)>\s*([^<\s]+)\s*<", block)
        if loc:
            out.append((loc.group(1), mod.group(1) if mod else None))
    return out


def chart_week_urls(entries, must: tuple[str, ...]) -> dict[int, tuple[str, str | None]]:
    """Newest trade-chart article per week among sitemap entries."""
    best: dict[int, tuple[str, str | None]] = {}
    for loc, mod in entries:
        low = loc.lower()
        if not all(w in low for w in must):
            continue
        m = re.search(r"week-(\d{1,2})(?!\d)", low)
        if not m:
            continue
        wk = int(m.group(1))
        if wk not in best or (mod or "") >= (best[wk][1] or ""):
            best[wk] = (loc, mod)
    return best


def discover(source: str, fetch: Fetcher, now: datetime, site_week: int | None) -> dict:
    """Publisher articles by week: {week: {"url", "published"}}, plus notes.
    Independent of the ingest's discovery code."""
    found: dict[int, dict] = {}
    notes: list[str] = []
    months = [(now.year, now.month), ((now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12))]
    if source == "usatoday":
        for y, m in months:
            st, xml, _ = fetch.get(f"https://www.gannett-cdn.com/sitemaps/USAT/web/web-sitemap-{y:04d}-{m:02d}.xml")
            if st != 200 or "</urlset>" not in xml:
                notes.append(f"USA Today sitemap {y}-{m:02d}: HTTP {st}{'' if st != 200 else ' (truncated)'}")
                continue
            for wk, (loc, mod) in chart_week_urls(sitemap_entries(xml),
                                                  ("/sports/fantasy/football/", "trade", "chart")).items():
                if wk not in found or (mod or "") >= (found[wk]["published"] or ""):
                    found[wk] = {"url": loc, "published": mod}
    elif source == "fantasypros":
        st, xml, _ = fetch.get("https://www.fantasypros.com/sitemaps/articles-sitemap.php")
        if st == 200:
            for wk, (loc, mod) in chart_week_urls(sitemap_entries(xml), ("fantasy-football-trade-value-chart",)).items():
                found[wk] = {"url": loc, "published": mod}
        else:
            notes.append(f"FantasyPros news sitemap: HTTP {st}")
        if site_week is not None and site_week + 1 not in found:
            for y, m in months:
                url = (f"https://www.fantasypros.com/{y:04d}/{m:02d}/"
                       f"fantasy-football-trade-value-chart-week-{site_week + 1}-{SEASON}/")
                st, _html, _ = fetch.get(url)
                if st == 200:
                    found[site_week + 1] = {"url": url, "published": json_ld_dates(_html).get("datePublished")}
                    break
    elif source == "cbs" and site_week is not None:
        for wk in (site_week, site_week + 1):
            url = f"https://www.cbssports.com/fantasy/football/news/dave-richards-{SEASON}-week-{wk}-trade-chart/"
            st, html, _ = fetch.get(url)
            if st == 200:
                found[wk] = {"url": url, "published": json_ld_dates(html).get("datePublished"), "html": html}
            elif st != 404:
                notes.append(f"CBS week {wk} candidate: HTTP {st}")
    return {"by_week": found, "notes": notes}


FC_API = "https://api.fantasycalc.com/values/current?isDynasty=false&numQbs={qb}&numTeams=12&ppr={ppr}"
FC_PPR = {"std": 0, "half": 0.5, "full": 1}


def read_publisher(source: str, fetch: Fetcher, stored: dict, disc: dict) -> dict:
    """The publisher's current values for the stored week: {rows, url, week, title, dates, notes, error}."""
    if source == "fantasycalc":
        payloads, notes = {}, []
        for s, ppr in FC_PPR.items():
            for qb in (1, 2):
                url = FC_API.format(qb=qb, ppr=ppr)
                st, text, _ = fetch.get(url)
                if st != 200:
                    return {"error": f"FantasyCalc API HTTP {st} for {url}"}
                try:
                    payloads[f"{s}|{qb}"] = json.loads(text)
                except ValueError:
                    return {"error": f"FantasyCalc API answer is not JSON for {url}"}
        rows, notes = read_fantasycalc(payloads)
        return {"rows": rows, "url": "https://api.fantasycalc.com/values/current (12 teams, 1 and 2 QB, 3 scorings)",
                "week": None, "title": None, "dates": {}, "notes": notes, "fetched_at": iso(utcnow())}

    week = stored.get("week")
    found = (disc.get("by_week") or {}).get(week) if week is not None else None
    url = (found or {}).get("url") or stored.get("source_url")
    if not url:
        return {"error": f"no {LABEL[source]} article found for week {week} (discovery and stored rows name none)"}
    html = (found or {}).get("html")
    if html is None:
        st, html, _ = fetch.get(url)
        if st != 200 or not html:
            return {"error": f"{LABEL[source]} article HTTP {st}: {url}", "url": url}
    title, tables = parse_page(html)
    rows, notes = read_tables(source, tables)
    if not rows:
        return {"error": f"no player rows parsed from {url} ({'; '.join(notes) or 'no tables'})", "url": url}
    wk, wk_problem = page_week(url, title)
    return {"rows": rows, "url": url, "discovered_url": (found or {}).get("url"), "week": wk,
            "week_problem": wk_problem, "title": title, "dates": json_ld_dates(html), "notes": notes,
            "fetched_at": iso(utcnow())}


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------

def fc_classify(cmp: dict) -> tuple[bool, float, list[dict]]:
    """FantasyCalc movement: (systemic, largest relative move, moves outside the band).

    Individual players move on news (a backup QB named starter jumps 50%), so
    a single large move is shown, not failed. Systemic means more than
    FC_SYSTEMIC_SHARE of the compared values sit outside the band, which
    movement over hours does not produce (measured 2026-10-08: 15 of 1,161
    values outside after 4 h, 1.3%) and a broken save does."""
    worst_rel = 0.0
    outside = []
    for m in cmp["mismatches"]:
        base = abs(float(m["right"])) or 1.0
        rel = abs(m["delta"]) / base
        worst_rel = max(worst_rel, rel)
        if abs(m["delta"]) > max(FC_DRIFT_ABS, FC_DRIFT_REL * base):
            outside.append(m)
    systemic = cmp["compared"] > 0 and len(outside) > FC_SYSTEMIC_SHARE * cmp["compared"]
    return systemic, worst_rel, outside


def fc_list_churn(cmp: dict, left: dict, right: dict) -> list[dict]:
    """FantasyCalc lists ~200 players; as values move, players at the bottom
    enter and leave. Missing / extra players valued at or below the list's
    churn line (the 15th-percentile value of that list, or FC_DRIFT_ABS) are
    movement, not a fidelity fault: moved to cmp['churn']."""
    churn = []
    for side, src in (("missing", left), ("extra", right)):
        keep = []
        for m in cmp[side]:
            vals = sorted(c["value"] for c in src.get(m["grain"], {}).values())
            line = max(FC_DRIFT_ABS, vals[int(len(vals) * 0.15)] if vals else 0)
            v = float(m["left"] if m["left"] is not None else m["right"])
            (churn if v <= line else keep).append(m)
        cmp[side] = keep
    cmp["churn"] = churn
    return churn


def fc_grain_check(left: dict, right: dict) -> list[str]:
    """Column-swap cross-check: each stored FantasyCalc list must be closest to
    the live list of the same scoring and QB setting (sum of absolute
    differences over shared players). Movement cannot make a swapped column
    look right, so this stays exact in spirit while values drift."""
    problems = []
    for g, R in right.items():
        dist = {}
        for g2, L in left.items():
            shared = R.keys() & L.keys()
            if len(shared) >= 20:
                dist[g2] = sum(abs(R[k]["value"] - L[k]["value"]) for k in shared) / len(shared)
        if dist and min(dist, key=dist.get) != g and dist.get(g, float("inf")) > FC_SWAP_RATIO * min(dist.values()):
            problems.append(f"stored {g} list is closest to the live {min(dist, key=dist.get)} list "
                            f"(mean |diff| {min(dist.values()):.0f} vs {dist.get(g, float('nan')):.0f})")
    return problems


def stage_publisher(source: str, pub: dict, stored: dict, ident: Identity, now: datetime,
                    universe: set[int] | frozenset = frozenset()) -> tuple[dict, dict]:
    """Stage 1. Returns (stage dict, comparison)."""
    if pub.get("error"):
        return stage("unknown", f"publisher not read: {pub['error']}", url=pub.get("url")), {}
    if not stored.get("bake"):
        return stage("red", f"no stored {LABEL[source]} rows for season {SEASON}"), {}
    left, unresolved = publisher_grains(pub["rows"], ident)
    right = stored["grains"]
    cmp = compare(left, right, printed=True)
    outside = split_universe(cmp, "missing", universe)
    churn = fc_list_churn(cmp, left, right) if source == "fantasycalc" else []
    swapped = fc_grain_check(left, right) if source == "fantasycalc" else []
    n_bad = problem_count(cmp)
    reasons, status = [], "green"
    if swapped:
        status = "red"
        reasons.append("column check: " + "; ".join(swapped))
    bake = stored["bake"]
    saved_at = bake["saved_at"]
    revised = parse_ts((pub.get("dates") or {}).get("dateModified"))
    if source == "fantasycalc":
        systemic, rel, out_band = fc_classify(cmp)
        if cmp["missing"] or cmp["extra"] or systemic:
            status = "red"
            reasons.append(f"{len(cmp['mismatches'])} values differ, {len(out_band)} outside the movement band"
                           f"{' (systemic: more than ' + format(FC_SYSTEMIC_SHARE, '.0%') + ' of values)' if systemic else ''}; "
                           f"{players(cmp['missing'])} live players not stored, {players(cmp['extra'])} stored players not "
                           "live (above the list's churn line)")
        elif cmp["mismatches"]:
            status = worst(status, "amber")
            reasons.append(f"{len(cmp['mismatches'])} of {cmp['compared']} values moved since the save at "
                           f"{iso(saved_at)} (largest {rel:.0%}; {len(out_band)} outside the "
                           f"max({FC_DRIFT_REL:.0%}, {FC_DRIFT_ABS}) band: "
                           f"{', '.join(sorted({m['name'] for m in out_band}))[:200] or 'none'})")
        if churn:
            reasons.append(f"{len({m['player_key'] for m in churn})} players entered or left the bottom of the list "
                           "since the save (churn)")
    elif n_bad:
        after_save = revised and saved_at and revised > saved_at
        if after_save and (now - revised) <= timedelta(hours=GRACE_HOURS):
            status = worst(status, "amber")
            reasons.append(f"update available: the publisher revised the page at {iso(revised)}, after the "
                           f"save at {iso(saved_at)} (a newer article version, not bad data; stale after "
                           f"{GRACE_HOURS} h)")
        else:
            status = "red"
            if after_save:
                reasons.append(f"stale: the publisher revised the page at {iso(revised)}, after the save at "
                               f"{iso(saved_at)}, and the revision is still not stored after {GRACE_HOURS} h")
        reasons.insert(0, f"{len(cmp['mismatches'])} value mismatches, {players(cmp['missing'])} publisher players not "
                          f"stored, {players(cmp['extra'])} stored players not on the page")
    if source != "fantasycalc":
        if pub.get("week_problem"):
            status = "red"
            reasons.append(f"page week unclear: {pub['week_problem']}")
        elif pub.get("week") is not None and pub["week"] != stored.get("week"):
            status = "red"
            reasons.append(f"page is week {pub['week']}, stored rows are week {stored.get('week')}")
        stored_url = bake.get("source_url")
        if bake.get("source_urls"):
            status = "red"
            reasons.append(f"stored bake names {len(bake['source_urls'])} different articles")
        disc_url = pub.get("discovered_url")
        if disc_url and stored_url and article_key(disc_url) != article_key(stored_url):
            status = "red"
            reasons.append(f"independent discovery found {disc_url}; stored rows name {stored_url}")
    if outside:
        status = worst(status, "amber")
        reasons.append(f"{len(outside)} publisher players are not stored because the page's player universe excludes "
                       f"them ({', '.join(p['name'] for p in outside[:5])}{', ...' if len(outside) > 5 else ''})")
    if unresolved:
        status = worst(status, "amber")
        reasons.append(f"{len(unresolved)} publisher names do not resolve to a canonical player")
    if pub.get("notes"):
        reasons.append("parse notes: " + "; ".join(pub["notes"]))
    counts = {"publisher_players": len({k for g in left.values() for k in g}),
              "stored_players": len({k for g in right.values() for k in g}),
              "compared": cmp["compared"], "matched": cmp["matched"], "mismatched": len(cmp["mismatches"]),
              "missing_in_stored": players(cmp["missing"]), "extra_in_stored": players(cmp["extra"]),
              "outside_universe": len(outside), "list_churn": len({m["player_key"] for m in churn}),
              "unresolved_names": len(unresolved)}
    summary = (f"{cmp['matched']}/{cmp['compared']} values match exactly across {len(cmp['grains'])} columns"
               + (f"; {'; '.join(reasons)}" if reasons else ""))
    return stage(status, summary, counts=counts, url=pub.get("url"), page_week=pub.get("week"),
                 page_modified=(pub.get("dates") or {}).get("dateModified"),
                 bake_id=bake.get("bake_id"), bake_saved_at=iso(saved_at), grains=cmp["grains"],
                 examples=worst_examples(cmp), outside_universe=outside[:EXAMPLES * 3],
                 unresolved=unresolved[:EXAMPLES]), dict(cmp, left_grains=left, right_grains=right)


def chart_bake(bakes: list[dict], imported_at: datetime | None) -> dict | None:
    """The bake the chart was built from: the newest saved at or before the chart's import."""
    if not bakes:
        return None
    if imported_at is None:
        return bakes[-1]
    eligible = [b for b in bakes if b["saved_at"] and b["saved_at"] <= imported_at]
    return eligible[-1] if eligible else None


def stage_chart(source: str, site_doc: dict | None, site_error: str | None, store, ident: Identity,
                stored: dict) -> tuple[dict, dict]:
    """Stage 2. Returns (stage dict, comparison)."""
    if site_doc is None:
        return stage("unknown", f"live chart not read: {site_error}"), {}
    meta = site_meta(site_doc, source)
    if not site_section(site_doc, source):
        return stage("red", f"{LABEL[source]} is not in the live chart file"), {}
    week = meta["week"]
    if week is None:
        return stage("red", "live chart section names no week"), {}
    bakes = stored["bakes"] if week == stored.get("week") else group_bakes(store.rows(source, week))
    imported_at = parse_ts(meta["imported_at"])
    bake = chart_bake(bakes, imported_at)
    if bake is None:
        return stage("red", f"no stored bake for week {week} saved before the chart's import at {meta['imported_at']}"), {}
    stored_g, _bad = stored_grains(source, bake["rows"], ident)
    chart_g, unresolved = site_grains(site_doc, source, ident)
    cmp = compare(stored_g, chart_g, printed=False)
    outside = split_universe(cmp, "missing", chart_universe(site_doc))
    n_bad = problem_count(cmp)
    status = "red" if n_bad or unresolved else "green"
    reasons = []
    if n_bad:
        reasons.append(f"{len(cmp['mismatches'])} chart values differ from the stored bake, "
                       f"{players(cmp['missing'])} stored players not on the chart, {players(cmp['extra'])} chart players not stored")
    if unresolved:
        reasons.append(f"{len(unresolved)} chart names have no player key")
    if outside:
        status = worst(status, "amber")
        reasons.append(f"{len(outside)} stored players are left off the chart because the page's player universe "
                       f"excludes them ({', '.join(p['name'] or str(p['player_key']) for p in outside[:5])}"
                       f"{', ...' if len(outside) > 5 else ''})")
    latest = stored.get("bake")
    floor = datetime.min.replace(tzinfo=timezone.utc)
    newer = latest if latest and latest["bake_id"] != bake["bake_id"] and (
        (stored.get("week") or 0) > week or (latest["saved_at"] or floor) > (bake["saved_at"] or floor)) else None
    behind = None
    if newer:
        newer_g, _ = stored_grains(source, newer["rows"], ident)
        diff = compare(stored_g, newer_g, printed=False)
        if problem_count(diff) or stored.get("week") != week:
            behind = {"bake_id": newer["bake_id"], "saved_at": iso(newer["saved_at"]), "week": stored.get("week"),
                      "changed_values": len(diff["mismatches"]), "added": len(diff["extra"]),
                      "dropped": len(diff["missing"])}
            status = worst(status, "amber")
            reasons.append(f"newer stored bake {newer['bake_id']} (week {stored.get('week')}, saved "
                           f"{iso(newer['saved_at'])}) is not on the chart yet: {behind['changed_values']} values "
                           f"changed, {behind['added']} added, {behind['dropped']} dropped")
    counts = {"chart_players": len({k for g in chart_g.values() for k in g}),
              "stored_players": len({k for g in stored_g.values() for k in g}),
              "compared": cmp["compared"], "matched": cmp["matched"], "mismatched": len(cmp["mismatches"]),
              "missing_on_chart": players(cmp["missing"]), "extra_on_chart": players(cmp["extra"]),
              "outside_universe": len(outside), "unresolved_names": len(unresolved)}
    summary = (f"{cmp['matched']}/{cmp['compared']} chart values equal stored bake {bake['bake_id']}"
               + (f"; {'; '.join(reasons)}" if reasons else ""))
    return stage(status, summary, counts=counts, chart_week=week, chart_imported_at=meta["imported_at"],
                 bake_id=bake["bake_id"], bake_saved_at=iso(bake["saved_at"]), behind=behind, grains=cmp["grains"],
                 examples=worst_examples(cmp), outside_universe=outside[:EXAMPLES * 3],
                 unresolved=unresolved[:EXAMPLES]), dict(cmp, left_grains=stored_g, right_grains=chart_g)


def stage_freshness(source: str, site_doc: dict | None, disc: dict, stored: dict, now: datetime) -> dict:
    """Stage 3."""
    if site_doc is None:
        return stage("unknown", "live chart not read")
    week = site_meta(site_doc, source)["week"]
    if week is None:
        return stage("unknown", "live chart names no week")
    if source == "fantasycalc":
        from nfl_week import content_week, content_week_start  # noqa: PLC0415
        cw = content_week(now.date())
        if cw <= week:
            return stage("green", f"chart shows week {week}; content week is {cw}", chart_week=week, publisher_week=cw)
        opened = datetime.combine(content_week_start(cw), datetime.min.time(), timezone.utc) + timedelta(hours=12)
        age = (now - opened).total_seconds() / 3600
        st = "red" if age > NEW_WEEK_GRACE_HOURS else "amber"
        return stage(st, f"content week {cw} opened {age:.0f} h ago; chart still shows FantasyCalc week {week}",
                     chart_week=week, publisher_week=cw)
    by_week = disc.get("by_week") or {}
    newer = {w: v for w, v in by_week.items() if w > week}
    notes = disc.get("notes") or []
    if not newer:
        st = "unknown" if notes and not by_week else "green"
        msg = (f"publisher has no newer week than the chart's week {week}" if st == "green"
               else f"publisher discovery failed: {'; '.join(notes)}")
        return stage(st, msg, chart_week=week, publisher_week=max(by_week) if by_week else None, notes=notes)
    top = max(newer)
    pub_at = parse_ts(newer[top].get("published"))
    age = (now - pub_at).total_seconds() / 3600 if pub_at else None
    st = "red" if age is not None and age > NEW_WEEK_GRACE_HOURS else "amber"
    stored_note = (f"; stored rows already have week {stored.get('week')}" if (stored.get("week") or 0) >= top
                   else "; not stored yet")
    return stage(st, f"publisher posted week {top} ({newer[top]['url']}"
                     f"{', ' + format(age, '.0f') + ' h ago' if age is not None else ', time unknown'}); "
                     f"chart shows week {week}{stored_note}",
                 chart_week=week, publisher_week=top, publisher_url=newer[top]["url"], notes=notes)


# --------------------------------------------------------------------------
# Stage 5: scrape-validity signals (Jeremy 2026-10-09: thin or odd adjustment
# fits are signals that the scrape may have missed the mark)
# --------------------------------------------------------------------------

SITE_ADJUSTMENT = SITE + "assets/adjustment-inputs.json"
SITE_HISTORY = SITE + "assets/history/week-{week}.json"
RANK_GUARD_PATHS = ("output/rank-guard.json", "dist/modules/rank-guard.json")
RANK_GUARD_URL = SITE + "modules/rank-guard.json"
POSITIONS = ("QB", "RB", "WR", "TE")


def load_json_any(paths, url, fetch: Fetcher | None, what: str):
    """(doc, where) from the first local path, else the live URL, else (None, why)."""
    for p in paths:
        f = ROOT / p
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8")), str(p)
            except ValueError:
                return None, f"{p} is not valid JSON"
    if url and fetch:
        st, text, _ = fetch.get(url)
        if st == 200:
            try:
                return json.loads(text), url
            except ValueError:
                return None, f"{url} is not valid JSON"
    return None, f"not yet available: no {what} is published"


def load_extras(fetch: Fetcher, site_doc: dict | None, now: datetime, store=None) -> dict:
    """Inputs of the scrape-validity stage, read once per run."""
    from nfl_week import content_week  # noqa: PLC0415
    extras = {"history": {}, "prior_pulse": {}}
    extras["adjustment"], extras["adjustment_where"] = load_json_any(
        (), SITE_ADJUSTMENT + f"?pulse={int(time.time())}", fetch, "adjustment-inputs.json")
    extras["rank_guard"], extras["rank_guard_where"] = load_json_any(
        RANK_GUARD_PATHS, RANK_GUARD_URL, fetch, "JEG-482 rank-guard report (rank-guard.json)")
    weeks = {content_week(now.date()) - 1}
    for src in TRADE_CHARTS:
        w = site_meta(site_doc, src)["week"] if site_doc else None
        if w:
            weeks.add(w - 1)
    for w in sorted(x for x in weeks if x and x > 0):
        extras["history"][w], _ = load_json_any((), SITE_HISTORY.format(week=w), fetch, f"week {w} history")
    if store is not None and hasattr(store, "prior_pulse"):
        try:
            extras["prior_pulse"] = store.prior_pulse() or {}
        except Exception:  # noqa: BLE001 - a missing baseline is reported, not fatal
            extras["prior_pulse"] = {}
    return extras


def count_by_position(grain: dict, ident: Identity) -> dict[str, int]:
    out = {p: 0 for p in POSITIONS}
    for k, cell in grain.items():
        pos = (ident.pos(k) or cell.get("pos") or "").upper()
        if pos in out:
            out[pos] += 1
    return out


def history_counts(doc: dict | None, source: str, ident: Identity,
                   universe: set[int] | None = None) -> dict[str, int] | None:
    entry = ((doc or {}).get("sources") or {}).get(source) or {}
    natives = entry.get("natives") or {}
    if natives:  # published charts: {scoring: {player_key: native}}
        scoring = next((k for k in natives if "half" in k), next(iter(natives)))
        keys = natives[scoring]
    else:        # projection sources: {"ppg": {player_key: ...}}
        keys = entry.get("ppg") or {}
    if not keys:
        return None
    return count_by_position({int(k): {} for k in keys if not universe or int(k) in universe}, ident)


def rank_guard_inversions(doc: dict | None, source: str) -> int | None:
    """Total inversions reported for a source, whatever the nesting (the
    JEG-482 report's schema is not fixed yet): every integer under a key named
    'inversions' inside the source's entry. None when the source is absent."""
    if not isinstance(doc, dict):
        return None
    srcs = doc.get("sources", doc)
    if isinstance(srcs, dict):
        entry = srcs.get(source)
    elif isinstance(srcs, list):
        entry = [e for e in srcs if isinstance(e, dict) and e.get("source") == source] or None
    else:
        entry = None
    if entry is None:
        return None

    def walk(x):
        if isinstance(x, dict):
            return sum((v if k == "inversions" and isinstance(v, int) else walk(v)) for k, v in x.items())
        if isinstance(x, list):
            return sum(walk(v) for v in x)
        return 0
    return walk(entry)


def stage_scrape_validity(source: str, extras: dict, ident: Identity, *, publisher: dict | None,
                          stored: dict | None, chart: dict | None, chart_week: int | None, now: datetime,
                          universe: set[int] | None = None) -> dict:
    """Signals that a scrape may have missed: sudden player-count drops per
    position (vs the prior week) and per position x tier (vs the prior week's
    pulse), thin or identity-fallback adjustment cells, and published-rank
    inversions (JEG-482). Absences from a fully loaded chart mean 0 by design;
    the absences that may be processing errors (on the publisher page, not
    stored; stored, not on the chart) are stages 1 and 2."""
    from nfl_week import content_week  # noqa: PLC0415
    status, reasons, signals = "green", [], {}
    g = "half|1"
    counts = {"publisher": count_by_position((publisher or {}).get(g, {}), ident) if publisher else None,
              "stored": count_by_position((stored or {}).get(g, {}), ident) if stored else None,
              "chart": count_by_position((chart or {}).get(g, {}), ident) if chart else None}
    prior_week = (chart_week - 1) if chart_week else content_week(now.date()) - 1
    prior_doc = extras.get("history", {}).get(prior_week)
    counts["prior_week"] = history_counts(prior_doc, source, ident)
    # The chart shows only the page's player universe; compare it with last
    # week's players inside the same universe (projection weeks keep every
    # stored player, the chart drops those outside it).
    counts["prior_week_in_universe"] = history_counts(prior_doc, source, ident, universe) if universe else None
    signals["position_counts"] = {"week_compared": prior_week, **counts}
    drops = []
    if counts["prior_week"]:
        for side in ("stored", "chart"):
            prior = (counts["prior_week_in_universe"] if side == "chart" and counts["prior_week_in_universe"]
                     else counts["prior_week"])
            for pos, n in (counts.get(side) or {}).items():
                base = prior.get(pos) or 0
                if base >= 5 and n < DROP_AMBER * base:
                    sev = "red" if n < DROP_RED * base else "amber"
                    listed = (counts.get("publisher") or {}).get(pos) if counts.get("publisher") else None
                    why = None
                    if sev == "red" and listed is None:
                        sev, why = "amber", "publisher list not read: drop unconfirmed"
                    elif sev == "red" and listed < DROP_RED * base:
                        sev, why = "amber", f"the publisher's own list dropped too ({listed})"
                    drops.append({"side": side, "position": pos, "now": n, "prior_week": base, "severity": sev,
                                  **({"note": why} if why else {})})
                    status = worst(status, sev)
        if drops:
            reasons.append("player count dropped vs week " + str(prior_week) + ": " + ", ".join(
                f"{d['side']} {d['position']} {d['prior_week']}->{d['now']}" + (f" ({d['note']})" if d.get("note") else "")
                for d in drops))
    else:
        reasons.append(f"no week {prior_week} history to compare position counts with")
    signals["count_drops"] = drops

    adj = extras.get("adjustment")
    entry = ((adj or {}).get("sources") or {}).get(source) if adj else None
    if entry:
        diag = entry.get("diagnostics") or {}
        cells = entry.get("cells") or []
        tiers = {f"{c.get('position')}|{c.get('tier')}": c.get("n") for c in cells}
        signals["tier_counts"] = tiers
        fallbacks = [{"cell": f"{c.get('position')}|{c.get('tier')}", "n": c.get("n"), "fallback": c.get("fallback"),
                      "reason": (diag.get(f"{c.get('position')}|{c.get('tier')}") or {}).get("reason")}
                     for c in cells if c.get("fallback")]
        thin = [{"cell": f"{c.get('position')}|{c.get('tier')}", "n": c.get("n")}
                for c in cells if isinstance(c.get("n"), int) and c["n"] < THIN_CELL and not c.get("fallback")]
        signals["fallback_cells"], signals["thin_cells"] = fallbacks, thin
        if fallbacks:
            status = worst(status, "amber")
            reasons.append("identity-fallback fit cells: " + ", ".join(
                f"{f['cell']} (n={f['n']}, {f['reason'] or f['fallback']})" for f in fallbacks))
        if thin:
            status = worst(status, "amber")
            reasons.append("thin fit cells: " + ", ".join(f"{t['cell']} n={t['n']}" for t in thin))
        prior_tiers = ((extras.get("prior_pulse") or {}).get(source) or {}).get(prior_week)
        if prior_tiers:
            tier_drops = [{"cell": k, "now": v, "prior_week": prior_tiers.get(k)} for k, v in tiers.items()
                          if isinstance(v, int) and isinstance(prior_tiers.get(k), int) and prior_tiers[k] >= 5
                          and v < TIER_DROP * prior_tiers[k]]
            signals["tier_drops"] = tier_drops
            if tier_drops:
                status = worst(status, "amber")
                reasons.append("tier count dropped vs week " + str(prior_week) + ": " + ", ".join(
                    f"{t['cell']} {t['prior_week']}->{t['now']}" for t in tier_drops))
        else:
            signals["tier_drops"] = None
            reasons.append(f"no week {prior_week} pulse baseline for tier counts yet")
    else:
        reasons.append(f"adjustment inputs not read ({extras.get('adjustment_where')})" if adj is None
                       else "no adjustment cells for this source")

    inv = rank_guard_inversions(extras.get("rank_guard"), source)
    signals["rank_inversions"] = inv
    if extras.get("rank_guard") is None:
        reasons.append(f"rank guard: {extras.get('rank_guard_where')}")
    elif inv:
        status = "red"
        reasons.append(f"rank guard: {inv} published-rank inversions (JEG-482)")
    signals["note"] = ("a player absent from a fully loaded chart means 0 by design; absences that may be "
                       "processing errors are flagged in publisher_vs_stored and stored_vs_chart")
    flagged = [r for r in reasons if not r.startswith(("no week", "rank guard: not yet", "adjustment inputs not"))]
    summary = ("; ".join(flagged) if flagged else "no scrape-validity signal") + (
        "; " + "; ".join(r for r in reasons if r not in flagged) if len(flagged) != len(reasons) else "")
    return stage(status, summary, signals=signals)


def load_value_check(paths=VALUE_CHECK_PATHS, url: str | None = VALUE_CHECK_URL, fetch: Fetcher | None = None):
    """The JEG-479 report, or (None, why)."""
    for p in paths:
        f = ROOT / p
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8")), str(p)
            except ValueError:
                return None, f"{p} is not valid JSON"
    if url and fetch:
        st, text, _ = fetch.get(url)
        if st == 200:
            try:
                return json.loads(text), url
            except ValueError:
                return None, f"{url} is not valid JSON"
    return None, "not yet available: no JEG-479 value-check report is published (value-check.json)"


def stage_reference(source: str, report: dict | None, where: str) -> dict:
    """Stage 4."""
    if report is None:
        return stage("n/a", where)
    entry = (report.get("sources") or {}).get(source)
    if entry is None:
        return stage("n/a", f"{where}: report does not cover {source}", report_generated_at=report.get("generated_at"))
    if entry.get("status") == "disagree":
        series = entry.get("disagreeing_series") or []
        ex = [e for k in series for e in ((report.get("series") or {}).get(k) or {}).get("examples", [])][:EXAMPLES]
        return stage("red", f"engine and Python reference disagree on {', '.join(series) or source}",
                     report_generated_at=report.get("generated_at"), examples=ex)
    return stage("green", f"engine and Python reference agree ({report.get('values_compared', '?')} values compared "
                          f"in the whole report)", report_generated_at=report.get("generated_at"))


# --------------------------------------------------------------------------
# Projection sources (ESPN, CBS rest of season, Razzball)
# --------------------------------------------------------------------------
#
# Same four stages. Differences from the trade charts: a stored "bake" is a
# snapshot date (one row per player per day, all scorings in columns); the
# publisher reader and the unit conversions live in pipelines/fidelity_sources/
# <source>.py (contract in its __init__); the chart compares per-game values
# printed to the module's CHART_DECIMALS; and, because ESPN and CBS print no
# update time, "the publisher changed after our save" is read from the change
# probe (public.source_probe_state: last fingerprint != acknowledged one).

def projection_module(source: str):
    import importlib  # noqa: PLC0415
    return importlib.import_module(f"fidelity_sources.{source}")


def written_at(row: dict) -> datetime | None:
    """When a stored row's values were last written. `_written_at` is a column
    default, so an upsert re-save of the same date never moves it; the save's
    own `pulled_at` does (GAP-RAZZBALL-CHART-BEHIND-STORED: the 03:25 re-save
    read as 23:25)."""
    stamps = [parse_ts(row.get(k)) for k in ("_written_at", "pulled_at", "created_at")]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


def dedupe_snapshot(rows: list[dict], mod=None) -> list[dict]:
    """One row per player: the latest written (a day can be re-saved). For a
    source whose saves stamp every row with one `SAVE_STAMP`, only the newest
    save counts: rows of players dropped since are superseded (the chain's
    import drops them too, lib/latest_save.py)."""
    stamp_key = getattr(mod, "SAVE_STAMP", None)
    if stamp_key:
        from latest_save import latest_save_rows  # noqa: PLC0415
        rows = latest_save_rows(rows, stamp_key)[0]
    floor = datetime.min.replace(tzinfo=timezone.utc)
    best: dict[int, dict] = {}
    for r in rows:
        k = r.get("player_key")
        if k is None:
            continue
        k = int(k)
        if k not in best or (written_at(r) or floor) >= (written_at(best[k]) or floor):
            best[k] = r
    return list(best.values())


def fmt_dec(value: float, places: int, rounding=ROUND_HALF_UP) -> str:
    return str(Decimal(repr(float(value))).quantize(Decimal(1).scaleb(-places), rounding=rounding))


def projection_grains(rows: list[dict], fn, places: int | None = None, ident: Identity | None = None) -> dict:
    """{grain: {player_key: cell}} from a module's stored-value function. With
    `places`, the stored value is rounded half-up to the chart's printed
    decimals and carried as printed text (the chart prints rounded natives).
    `text_alt` is the half-down rounding: on an exact tie (ESPN Tyler Warren
    full PPR 141.66 / 12 games = 11.805) the chart's builder may round either
    way (Python round() on the binary 11.80499... gives 11.8), and both are
    the stored number printed to the chart's decimals. Off a tie the two are
    the same text, so the rule stays exact (JEG-480, 27 such ties on
    2026-10-09)."""
    out: dict[str, dict] = {}
    for r in rows:
        for g, v in (fn(r) or {}).items():
            if v is None:
                continue
            cell = {"value": float(v), "text": fmt_dec(v, places) if places is not None else None,
                    "text_alt": fmt_dec(v, places, ROUND_HALF_DOWN) if places is not None else None,
                    "name": (ident.name(r["player_key"]) if ident else None) or r.get("player_norm")
                            or str(r.get("player_key")),
                    "pos": r.get("pos") or r.get("position") or (ident.pos(r["player_key"]) if ident else None)}
            out.setdefault(g, {})[int(r["player_key"])] = cell
    return out


def chart_snapshot(site_doc: dict, source: str) -> str | None:
    sec = site_section(site_doc, source)
    for v in ((sec.get("lineage") or {}).get("raw_vintage"), sec.get("espn_snapshot"), sec.get("vintage")):
        if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)):
            return str(v)
    return None


def projection_chart_grains(site_doc: dict, source: str, ident: Identity | None) -> tuple[dict, list[dict]]:
    """Projection sections carry 8/10/12/14-team combos with one per-game native; read the 12-team ones."""
    sec = site_section(site_doc, source)
    keys = {**((site_doc or {}).get("player_keys") or {})}
    grains, unresolved = {}, []
    for s, combo in SITE_COMBO.items():
        c = (sec.get("combos") or {}).get(combo) or {}
        ck = {**keys, **(c.get("player_keys") or {})}
        for slug, val in (c.get("native") or {}).items():
            if val is None:
                continue
            key = ck.get(slug)
            if key is None and ident is not None:
                key = ident.resolve_any(slug)
            if key is None:
                unresolved.append({"slug": slug, "grain": f"{s}|1", "value": val})
                continue
            grains.setdefault(f"{s}|1", {})[int(key)] = {"value": float(val), "text": None, "name": slug, "pos": None}
    return grains, unresolved


def probe_changed(probe: dict | None) -> bool:
    """The change probe saw publisher content the last successful ingest has not acknowledged."""
    return bool(probe and probe.get("last_ok") and probe.get("last_fp") and probe.get("last_fp") != probe.get("acked_fp"))


def cap_tie_churn(cmp: dict, left: dict, right: dict, ident: Identity) -> list[dict]:
    """Rows at a capped page's cut-off: CBS lists at most 100 players per
    position, sorted by standard points, and the order among players tied at
    the last value varies between requests (2026-10-09: Audric Estime and
    Andrew Beck, both 8.8, swapped places an hour apart). A missing / extra
    player whose standard value is at or below the publisher's lowest listed
    value for that position is churn, not a fidelity fault."""
    floor: dict[str, float] = {}
    for k, cell in left.get("std|1", {}).items():
        pos = ident.pos(k) or cell.get("pos")
        floor[pos] = min(floor.get(pos, float("inf")), cell["value"])
    churn = []
    for side in ("missing", "extra"):
        keep = []
        for m in cmp[side]:
            src = left if side == "missing" else right
            std = (src.get("std|1", {}).get(m["player_key"]) or {}).get("value")
            pos = ident.pos(m["player_key"]) or m.get("pos")
            (churn if std is not None and pos in floor and std <= floor[pos] else keep).append(m)
        cmp[side] = keep
    cmp["churn"] = churn
    return churn


class StoredRowIdentity:
    """A publisher name the canonical resolver refuses resolves through the
    stored row of exactly that name and position, keyed by the saver's
    verified player_key.

    Razzball lists fullbacks and some special-teamers under another position
    (Brady Russell RB, Jackson Meeks TE): the resolver says position_conflict,
    while the saver stored them under their key. The page row and the stored
    row are then the same player with the same numbers, and reading them as
    "stored players not on the page" turned Razzball red (pulse run
    37945152207: 2040/2040 values equal, 5 such players). Only an exact
    (normalized name, position) match with one stored row is accepted.
    """

    def __init__(self, ident: "Identity", rows: list[dict]):
        from canonical_players import norm_plain  # noqa: PLC0415
        self.ident, self.norm = ident, norm_plain
        seen: dict[tuple, set] = {}
        for r in rows:
            if r.get("player_norm") and r.get("player_key") is not None:
                seen.setdefault((r["player_norm"], (r.get("pos") or "").upper()), set()).add(int(r["player_key"]))
        self.by_name = {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}
        self.used: list[str] = []

    def resolve(self, name, pos):
        key, reason = self.ident.resolve(name, pos)
        if key is None:
            stored = self.by_name.get((self.norm(name), (pos or "").upper()))
            if stored is not None:
                self.used.append(name)
                return stored, None
        return key, reason


def same_version(probe: dict | None, live: dict | None, saved_at: datetime | None) -> tuple[str, str]:
    """Is the publisher still serving the content the stored save read?

    ('same' | 'changed' | 'unconfirmed', detail). The save's content is named
    by the probe fingerprint acknowledged with it (source_probe_state.acked_fp,
    acked within ACK_MATCH_MINUTES of the save); `live` is a fresh
    source_probe.run_probe() result."""
    probe = probe or {}
    acked_fp, acked_at = probe.get("acked_fp"), parse_ts(probe.get("acked_at"))
    if not live or not live.get("ok") or not live.get("fingerprint"):
        why = (live or {}).get("error") or "no probe result"
        return "unconfirmed", f"the publisher's fingerprint could not be read now ({why})"
    if (not acked_fp or acked_at is None or saved_at is None
            or abs(acked_at - saved_at) > timedelta(minutes=ACK_MATCH_MINUTES)):
        return "unconfirmed", (f"no publisher fingerprint was recorded with the save at {iso(saved_at)} "
                               f"(last ack {iso(acked_at)})")
    if live["fingerprint"] == acked_fp:
        return "same", f"the publisher serves the content the save read (fingerprint {acked_fp})"
    return "changed", (f"the publisher changed since the save (fingerprint {acked_fp} at the save, "
                       f"{live['fingerprint']} now)")


def player_blocks(cmp: dict, left: dict, ident: Identity) -> list[str]:
    """Positions where the publisher and the stored copy disagree on a block of
    players (missing + extra above BLOCK_SHARE of the publisher's count, at
    least BLOCK_MIN): a truncated or padded save, never a daily update."""
    listed: dict[str, set] = {}
    for g in left.values():
        for k, cell in g.items():
            listed.setdefault(ident.pos(k) or cell.get("pos"), set()).add(k)
    off: dict[str, set] = {}
    for m in cmp["missing"] + cmp["extra"]:
        off.setdefault(ident.pos(m["player_key"]) or m.get("pos"), set()).add(m["player_key"])
    return sorted(f"{pos} {len(keys)} of {len(listed.get(pos, ()))}" for pos, keys in off.items()
                  if len(keys) >= BLOCK_MIN and len(keys) > BLOCK_SHARE * len(listed.get(pos, ())))


def negligible_absences(cmp: dict, left: dict) -> list[dict]:
    """Publisher players not stored whose every printed value is at most one printed unit (0.1 per game on
    Razzball, 0.00 on ESPN). A player absent from a fully loaded chart means 0, so serving him as absent
    differs from the publisher by at most that unit: listed (amber), never a hold. 2026-10-09 23:40Z:
    Razzball held on Scotty Miller, printed 0.1 per game in every scoring and not stored."""
    small: dict[int, bool] = {}
    for m in cmp["missing"]:
        cell = (left.get(m["grain"]) or {}).get(m["player_key"]) or {}
        text = cell.get("text")
        unit = 10 ** -decimals(text) if text else 0
        ok = text is not None and abs(cell.get("value", 0)) <= unit + 1e-9
        small[m["player_key"]] = small.get(m["player_key"], True) and ok
    keep, gone = [], []
    for m in cmp["missing"]:
        (gone if small.get(m["player_key"]) else keep).append(m)
    cmp["missing"] = keep
    return gone


def stage_projection_publisher(source, mod, pub, rows, snapshot, saved_at, ident, now, universe, probe,
                               live_fingerprint: Callable[[], dict | None] | None = None):
    if pub.get("error"):
        return stage("unknown", f"publisher not read: {pub['error']}", url=pub.get("url")), {}
    if not rows:
        return stage("red", f"no stored {LABEL[source]} rows"), {}
    stored_ident = StoredRowIdentity(ident, rows)
    left, unresolved = publisher_grains(pub.get("rows") or [], stored_ident)
    right = projection_grains(rows, mod.stored_publisher_values, ident=ident)
    cmp = compare(left, right, printed=True)
    outside = split_universe(cmp, "missing", universe)
    churn = cap_tie_churn(cmp, left, right, ident)
    negligible = negligible_absences(cmp, left)
    n_bad = problem_count(cmp)
    status, reasons = "green", []
    vintage = pub.get("vintage")
    revised = parse_ts((pub.get("dates") or {}).get("dateModified"))
    if n_bad:
        reasons.append(f"{len(cmp['mismatches'])} value mismatches, {players(cmp['missing'])} publisher players not "
                       f"stored, {players(cmp['extra'])} stored players not on the page")
        newer = (vintage and str(vintage) > str(snapshot)) or (revised and saved_at and revised > saved_at)
        blocks = player_blocks(cmp, left, ident)
        stale = saved_at is None or (now - saved_at) > timedelta(hours=PROJECTION_STALE_HOURS)
        version = ("", "")
        if not blocks and not (newer and (not revised or (now - revised) <= timedelta(hours=GRACE_HOURS))) \
                and not probe_changed(probe):
            version = same_version(probe, live_fingerprint() if live_fingerprint else None, saved_at)
        if blocks:
            status = "red"
            reasons.append(f"a block of players is missing or extra ({', '.join(blocks)})")
        elif newer and (not revised or (now - revised) <= timedelta(hours=GRACE_HOURS)):
            status = "amber"
            reasons.append(f"publisher updated ({vintage or iso(revised)}) after the stored snapshot {snapshot}; "
                           f"inside the {GRACE_HOURS} h grace window")
        elif probe_changed(probe):
            status = "amber"
            reasons.append(f"the change probe saw new publisher content at {probe.get('last_probe_at')} that no "
                           "ingest has saved yet (ingest pending)")
        elif version[0] == "same":
            status = "red"
            reasons.append(f"stored values differ from the same publisher version: {version[1]}")
        elif version[0] == "changed" and not stale:
            status = "amber"
            reasons.append(f"daily update, ingest pending: {version[1]}")
        elif version[0] == "changed":
            status = "red"
            reasons.append(f"stale: {version[1]} and the save is older than {PROJECTION_STALE_HOURS} h")
        else:
            status = "amber"
            reasons.append(f"unconfirmed: {version[1]}")
    if outside:
        status = worst(status, "amber")
        reasons.append(f"{len(outside)} publisher players are not stored because the page's player universe excludes "
                       f"them ({', '.join(p['name'] for p in outside[:5])}{', ...' if len(outside) > 5 else ''})")
    if unresolved:
        status = worst(status, "amber")
        reasons.append(f"{len(unresolved)} publisher names do not resolve to a canonical player")
    if negligible:
        status = worst(status, "amber")
        reasons.append(f"{players(negligible)} publisher players not stored whose printed values are at most one "
                       f"printed unit (absent means 0): {', '.join(sorted({m['name'] for m in negligible}))[:200]}")
    if stored_ident.used:
        reasons.append(f"{len(stored_ident.used)} publisher names matched by the stored row's key (the canonical "
                       f"resolver refuses their listed position: {', '.join(stored_ident.used[:5])})")
    if churn:
        reasons.append(f"{players(churn)} players at the page's last listed value swapped in or out "
                       f"(ties at the row cap: {', '.join(sorted({m['name'] for m in churn}))[:200]})")
    if pub.get("notes"):
        reasons.append("parse notes: " + "; ".join(pub["notes"][:5]))
    counts = {"publisher_players": len({k for g in left.values() for k in g}),
              "stored_players": len({k for g in right.values() for k in g}),
              "compared": cmp["compared"], "matched": cmp["matched"], "mismatched": len(cmp["mismatches"]),
              "missing_in_stored": players(cmp["missing"]), "extra_in_stored": players(cmp["extra"]),
              "outside_universe": len(outside), "list_churn": players(churn), "unresolved_names": len(unresolved)}
    summary = (f"{cmp['matched']}/{cmp['compared']} values match exactly across {len(cmp['grains'])} columns"
               + (f"; {'; '.join(reasons)}" if reasons else ""))
    return stage(status, summary, counts=counts, url=pub.get("url"), publisher_vintage=vintage,
                 stored_snapshot=snapshot, stored_saved_at=iso(saved_at), grains=cmp["grains"],
                 publisher_version=(version[0] or None) if n_bad else None,
                 examples=worst_examples(cmp), outside_universe=outside[:EXAMPLES * 3],
                 unresolved=unresolved[:EXAMPLES]), dict(cmp, left_grains=left, right_grains=right)


def verified_keys(cmp: dict) -> set[int] | None:
    """Players stage 1 compared and found equal to the publisher in every column (None: stage 1 did not run)."""
    if not cmp or "left_grains" not in cmp:
        return None
    bad = {m["player_key"] for m in cmp.get("mismatches", []) + cmp.get("missing", []) + cmp.get("extra", [])}
    return {k for g in cmp["right_grains"].values() for k in g if k not in bad}


def read_projection_publisher(mod, fetch, rows: list[dict]) -> dict:
    """Call the module's reader; a reader that takes `window` gets the stored
    rows' (most common) weeks_covered so both sides sum the same weeks."""
    import inspect  # noqa: PLC0415
    if "window" in inspect.signature(mod.read_publisher).parameters:
        windows = [str(r.get("weeks_covered")) for r in rows if r.get("weeks_covered")]
        if windows:
            return mod.read_publisher(fetch, window=max(set(windows), key=windows.count))
    return mod.read_publisher(fetch)


def stage_projection_chart(source, mod, site_doc, site_error, store, ident, now, latest, latest_rows,
                           verified_keys: set[int] | None = None):
    if site_doc is None:
        return stage("unknown", f"live chart not read: {site_error}"), {}
    if not site_section(site_doc, source):
        return stage("red", f"{LABEL[source]} is not in the live chart file"), {}
    snap = chart_snapshot(site_doc, source)
    if snap is None:
        return stage("red", "live chart section names no snapshot date"), {}
    rows = latest_rows if snap == latest else dedupe_snapshot(store.snapshot_rows(mod, snap), mod)
    if not rows:
        return stage("red", f"no stored {LABEL[source]} snapshot {snap} (the chart's vintage)"), {}
    ctx = {"ident": ident, "now": now, "season": SEASON}
    left = projection_grains(rows, lambda r: mod.stored_chart_values(r, ctx), mod.CHART_DECIMALS, ident)
    right, unresolved = projection_chart_grains(site_doc, source, ident)
    cmp = compare(left, right, printed=True)
    outside = split_universe(cmp, "missing", chart_universe(site_doc))
    n_bad = problem_count(cmp)
    status = "red" if n_bad or unresolved else "green"
    reasons = []
    # A snapshot date is re-saved in place (upsert) when the publisher updates
    # the same day; the rows the chart was built from are then overwritten.
    # Differences on rows written after the chart's raw_built_at cannot be
    # checked against what the chart used: amber until the next chain run.
    built = parse_ts((site_section(site_doc, source).get("lineage") or {}).get("raw_built_at"))
    floor = datetime.min.replace(tzinfo=timezone.utc)
    by_key = {int(r["player_key"]): r for r in rows if r.get("player_key") is not None}
    # Exempt only rows stage 1 shows equal to the publisher now (the stored
    # value is a genuine publisher update); a row that also differs from the
    # publisher (e.g. ESPN projections stored as 0) stays red.
    resaved = [m for m in cmp["mismatches"] + cmp["missing"]
               if built and verified_keys is not None and m["player_key"] in verified_keys
               and (written_at(by_key.get(m["player_key"]) or {}) or floor) > built]
    # A chart player the stored snapshot no longer has, when the snapshot was re-saved after the chart was
    # built: the save replaced the day's set (2026-10-09 23:25Z CBS rest of season: one player swapped at
    # the row cap). A player the publisher still lists is missing in stage 1 (red there).
    last_write = max((t for t in map(written_at, rows) if t is not None), default=None)
    if built and verified_keys is not None and last_write and last_write > built:
        resaved += cmp["extra"]
    if n_bad and resaved and len(resaved) == n_bad and not unresolved:
        status = "amber"
        last = last_write
        reasons.append(f"{len(resaved)} chart values differ because snapshot {snap} was re-saved at {iso(last)}, after "
                       f"the chart was built from it at {iso(built)}; the chart's version is overwritten, so these "
                       "cannot be checked until the next chain run rebuilds from the stored rows")
    elif n_bad:
        reasons.append(f"{len(cmp['mismatches'])} chart values differ from the stored snapshot, "
                       f"{players(cmp['missing'])} stored players not on the chart, "
                       f"{players(cmp['extra'])} chart players not stored")
    if unresolved:
        reasons.append(f"{len(unresolved)} chart names have no player key")
    if outside:
        status = worst(status, "amber")
        reasons.append(f"{len(outside)} stored players are left off the chart because the page's player universe "
                       f"excludes them ({', '.join(p['name'] or str(p['player_key']) for p in outside[:5])}"
                       f"{', ...' if len(outside) > 5 else ''})")
    behind = None
    if latest and latest > snap:
        newer = projection_grains(latest_rows, lambda r: mod.stored_chart_values(r, ctx), mod.CHART_DECIMALS, ident)
        diff = compare(left, newer, printed=True)
        if problem_count(diff):
            behind = {"snapshot": latest, "changed_values": len(diff["mismatches"]),
                      "added": players(diff["extra"]), "dropped": players(diff["missing"])}
            status = worst(status, "amber")
            reasons.append(f"newer stored snapshot {latest} is not on the chart yet: {behind['changed_values']} "
                           f"values changed, {behind['added']} added, {behind['dropped']} dropped")
    counts = {"chart_players": len({k for g in right.values() for k in g}),
              "stored_players": len({k for g in left.values() for k in g}),
              "compared": cmp["compared"], "matched": cmp["matched"], "mismatched": len(cmp["mismatches"]),
              "missing_on_chart": players(cmp["missing"]), "extra_on_chart": players(cmp["extra"]),
              "outside_universe": len(outside), "unresolved_names": len(unresolved)}
    summary = (f"{cmp['matched']}/{cmp['compared']} chart values equal stored snapshot {snap} "
               f"(per game, {mod.CHART_DECIMALS} decimals)" + (f"; {'; '.join(reasons)}" if reasons else ""))
    return stage(status, summary, counts=counts, chart_snapshot=snap, behind=behind, grains=cmp["grains"],
                 examples=worst_examples(cmp), outside_universe=outside[:EXAMPLES * 3],
                 unresolved=unresolved[:EXAMPLES]), dict(cmp, left_grains=left, right_grains=right)


def stage_projection_freshness(source, site_doc, pub, latest, now):
    if site_doc is None:
        return stage("unknown", "live chart not read")
    snap = chart_snapshot(site_doc, source)
    if snap is None:
        return stage("unknown", "live chart names no snapshot date")
    vintage = (pub or {}).get("vintage")
    stamp = parse_ts(((pub or {}).get("dates") or {}).get("dateModified"))
    if vintage and str(vintage) > snap:
        age = (now - stamp).total_seconds() / 3600 if stamp else None
        st = "red" if age is not None and age > NEW_WEEK_GRACE_HOURS else "amber"
        return stage(st, f"publisher updated {vintage}{f' ({age:.0f} h ago)' if age is not None else ''}; chart shows "
                         f"snapshot {snap}" + (f"; stored has {latest}" if latest and latest > snap else ""),
                     chart_snapshot=snap, publisher_vintage=vintage)
    days = (now.date() - date.fromisoformat(snap)).days
    st = "red" if days > PROJECTION_RED_DAYS else "amber" if days > PROJECTION_AMBER_DAYS else "green"
    return stage(st, f"chart shows snapshot {snap} ({days} d old)"
                     + (f"; publisher's own update date {vintage}" if vintage else "; the publisher prints no update date"),
                 chart_snapshot=snap, publisher_vintage=vintage)


def section_hold(site_doc: dict | None, source: str) -> dict | None:
    """The fidelity hold (JEG-520) the live chart's section carries, if any."""
    hold = site_section(site_doc or {}, source).get("validationHold")
    if isinstance(hold, dict) and str(hold.get("reason") or "").startswith(HOLD_PREFIX):
        return hold
    return None


def held_chart_stage(held: dict, identity: str | None) -> dict:
    """Stage 2 for a held source: the chart serves the kept (last good) section, so comparing it with the
    newest stored save says nothing. A hold caused by stage 2 stays red until a newer save exists: the chain
    would rebuild the same chart from the same save."""
    if held.get("stage") == "stored_vs_chart" and identity and held.get("identity") == identity:
        return stage("red", f"held ({held.get('reason')}) since {held.get('since')}: the chart built from stored save "
                            f"{identity} differed from it; held until a newer save", held=True)
    return stage("n/a", f"held ({held.get('reason')}) since {held.get('since')}: the chart serves the last good "
                        "section; compared again once the hold is released", held=True)


def hold_decision(result: dict, identity: str | None, held: dict | None, now: datetime) -> dict | None:
    """JEG-520: a red in a holding stage holds the source; amber and unknown never do."""
    red = [n for n in HOLD_STAGES if (result["stages"].get(n) or {}).get("status") == "red"]
    if not red:
        return None
    first = red[0]
    return {"stage": first, "stages": red, "reason": HOLD_PREFIX + first, "identity": identity,
            "since": (held or {}).get("since") if (held or {}).get("reason") == HOLD_PREFIX + first else iso(now),
            "summary": str(result["stages"][first].get("summary") or "")[:300]}


def _content_week(now: datetime) -> int:
    from nfl_week import content_week  # noqa: PLC0415
    return content_week(now.date())


def check_projection(source: str, *, fetch, store, ident, site_doc, site_error, report, report_where,
                     now, extras: dict | None = None) -> tuple[dict, list[dict]]:
    stages: dict[str, dict] = {}
    divergences: list[dict] = []
    cmp: dict = {}
    cmp2: dict = {}
    mod = projection_module(source)
    latest, latest_rows, saved_at, probe, pub = None, [], None, None, {}
    try:
        latest = store.latest_snapshot(mod)
        latest_rows = dedupe_snapshot(store.snapshot_rows(mod, latest), mod) if latest else []
        saved_at = max((t for t in map(written_at, latest_rows) if t is not None), default=None)
        probe = store.probe_state(source)
        read_error = None
    except Exception as e:  # noqa: BLE001
        read_error = f"{type(e).__name__}: {e}"
    if read_error:
        stages["publisher_vs_stored"] = stage("unknown", f"stored rows not read: {read_error}")
    else:
        try:
            pub = read_projection_publisher(mod, fetch, latest_rows)
            live = getattr(store, "live_fingerprint", None)
            stages["publisher_vs_stored"], cmp = stage_projection_publisher(
                source, mod, pub, latest_rows, latest, saved_at, ident, now, chart_universe(site_doc), probe,
                live_fingerprint=(lambda: live(source)) if live else None)
            divergences += [dict(d, stage="publisher_vs_stored", source_url=pub.get("url")) for d in divergence_items(cmp)]
        except Exception as e:  # noqa: BLE001
            stages["publisher_vs_stored"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    held = section_hold(site_doc, source)
    identity = f"{latest}@{iso(saved_at)}" if latest else None
    try:
        if held:
            stages["stored_vs_chart"] = held_chart_stage(held, identity)
        else:
            stages["stored_vs_chart"], cmp2 = stage_projection_chart(source, mod, site_doc, site_error, store, ident,
                                                                     now, latest, latest_rows, verified_keys(cmp))
            divergences += [dict(d, stage="stored_vs_chart", source_url=SITE_FIXTURE) for d in divergence_items(cmp2)]
    except Exception as e:  # noqa: BLE001
        stages["stored_vs_chart"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    try:
        # A held chart serves the kept section: judge what the next build would serve (the stored snapshot).
        fresh_doc = {"sources": {source: {"lineage": {"raw_vintage": latest}}}} if held and latest else site_doc
        stages["freshness"] = stage_projection_freshness(source, fresh_doc, pub, latest, now)
    except Exception as e:  # noqa: BLE001
        stages["freshness"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    stages["reference_vs_engine"] = stage_reference(source, report, report_where)
    try:
        stages["scrape_validity"] = stage_scrape_validity(
            source, extras or {}, ident, publisher=cmp.get("left_grains"),
            stored=projection_grains(latest_rows, mod.stored_publisher_values, ident=ident) if latest_rows else None,
            chart=cmp2.get("right_grains"), chart_week=None, now=now, universe=chart_universe(site_doc))
    except Exception as e:  # noqa: BLE001
        stages["scrape_validity"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    status = worst(*(rollup(s["status"]) for s in stages.values()))
    examples = [{"stage": n, **ex} for n in STAGES for ex in (stages[n].get("examples") or [])]
    result = {"source": source, "label": LABEL[source], "status": status,
              "stored_week": None, "chart_week": None, "content_week": _content_week(now), "stored_snapshot": latest,
              "chart_snapshot": chart_snapshot(site_doc, source) if site_doc else None,
              "stored_bake": latest, "stages": stages, "worst_examples": examples[:EXAMPLES], "held": held}
    result["hold"] = hold_decision(result, identity, held, now)
    return result, divergences


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

def load_stored(source: str, store) -> dict:
    week = store.latest_week(source)
    if week is None:
        return {"week": None, "bakes": [], "bake": None, "grains": {}}
    bakes = group_bakes(store.rows(source, week))
    return {"week": week, "bakes": bakes, "bake": bakes[-1] if bakes else None,
            "source_url": bakes[-1]["source_url"] if bakes else None}


def check_source(source: str, *, fetch: Fetcher, store, ident: Identity, site_doc, site_error, report,
                 report_where, now: datetime, extras: dict | None = None) -> tuple[dict, list[dict]]:
    """All four stages for one source. Returns (source result, divergence rows)."""
    if source in PROJECTIONS:
        return check_projection(source, fetch=fetch, store=store, ident=ident, site_doc=site_doc,
                                site_error=site_error, report=report, report_where=report_where, now=now,
                                extras=extras)
    stages: dict[str, dict] = {}
    divergences: list[dict] = []
    cmp1: dict = {}
    cmp2: dict = {}
    try:
        stored = load_stored(source, store)
        if stored.get("bake"):
            stored["grains"], stored["bad_rows"] = stored_grains(source, stored["bake"]["rows"], ident)
    except Exception as e:  # noqa: BLE001 - a read failure is a stage result, not a crash
        stored = {"week": None, "bakes": [], "bake": None, "grains": {}, "error": f"{type(e).__name__}: {e}"}
    site_week = site_meta(site_doc, source)["week"] if site_doc else None

    try:
        disc = discover(source, fetch, now, site_week if site_week is not None else stored.get("week"))
    except Exception as e:  # noqa: BLE001
        disc = {"by_week": {}, "notes": [f"discovery failed: {type(e).__name__}: {e}"]}

    if stored.get("error"):
        stages["publisher_vs_stored"] = stage("unknown", f"stored rows not read: {stored['error']}")
    else:
        try:
            pub = read_publisher(source, fetch, stored, disc)
            stages["publisher_vs_stored"], cmp1 = stage_publisher(source, pub, stored, ident, now,
                                                                 chart_universe(site_doc))
            divergences += [dict(d, stage="publisher_vs_stored", source_url=pub.get("url"))
                            for d in divergence_items(cmp1)]
        except Exception as e:  # noqa: BLE001
            stages["publisher_vs_stored"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    held = section_hold(site_doc, source)
    identity = (stored.get("bake") or {}).get("bake_id")
    try:
        if held:
            stages["stored_vs_chart"] = held_chart_stage(held, identity)
        else:
            stages["stored_vs_chart"], cmp2 = stage_chart(source, site_doc, site_error, store, ident, stored)
            divergences += [dict(d, stage="stored_vs_chart", source_url=SITE_FIXTURE)
                            for d in divergence_items(cmp2)]
    except Exception as e:  # noqa: BLE001
        stages["stored_vs_chart"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    try:
        # A held chart serves the kept section: judge what the next build would serve (the stored week).
        fresh_doc = ({"sources": {source: {"source_provenance": {"week_designated": stored["week"]}}}}
                     if held and stored.get("week") is not None else site_doc)
        stages["freshness"] = stage_freshness(source, fresh_doc, disc, stored, now)
    except Exception as e:  # noqa: BLE001
        stages["freshness"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    stages["reference_vs_engine"] = stage_reference(source, report, report_where)
    try:
        stages["scrape_validity"] = stage_scrape_validity(
            source, extras or {}, ident, publisher=cmp1.get("left_grains"), stored=stored.get("grains"),
            chart=cmp2.get("right_grains"), chart_week=site_week, now=now, universe=chart_universe(site_doc))
    except Exception as e:  # noqa: BLE001
        stages["scrape_validity"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")

    status = worst(*(rollup(s["status"]) for s in stages.values()))
    examples = []
    for name in STAGES:
        for ex in stages[name].get("examples") or []:
            examples.append({"stage": name, **ex})
    result = {"source": source, "label": LABEL[source], "status": status,
              "stored_week": stored.get("week"), "chart_week": site_week,
              "stored_bake": (stored.get("bake") or {}).get("bake_id"),
              "stages": stages, "worst_examples": examples[:EXAMPLES], "held": held}
    result["hold"] = hold_decision(result, identity, held, now)
    return result, divergences


PLAYERS_FIXTURE = ROOT / "data" / "fixtures" / "current" / "players.json"


def universe_report(path: Path = PLAYERS_FIXTURE) -> dict:
    """JEG-502: the player universe the page searches (players.json rows), with
    the active NFL universe count by roster status (meta.universe.nfl_active,
    written by bake_players.py). Informational: never sets a source's status."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"status": "unknown", "summary": f"players.json unreadable: {type(e).__name__}"}
    meta = doc.get("meta") or {}
    nfl = (meta.get("universe") or {}).get("nfl_active")
    n_rows = len(doc.get("players") or [])
    if not nfl:
        return {"status": "amber", "n_rows": n_rows, "as_of": meta.get("as_of"),
                "summary": f"{n_rows} players searchable; no active NFL universe count in this bake"}
    by_status = nfl.get("by_roster_status") or {}
    parts = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in by_status.items())
    return {"status": "green", "n_rows": n_rows, "as_of": meta.get("as_of"),
            "n_nfl_active": nfl.get("n_nfl_active"), "by_roster_status": by_status,
            "n_universe_only": nfl.get("n_universe_only"),
            "n_not_on_players_table": nfl.get("n_not_on_players_table"),
            "identity_base_pulled_at": nfl.get("identity_base_pulled_at"),
            "definition": nfl.get("definition"),
            "summary": f"{n_rows} players searchable; {nfl.get('n_nfl_active')} active NFL players ({parts})"}


def last_good(sources, holds: dict, site_doc: dict | None, previous: dict | None) -> dict:
    """{source: built_at of the last chart file this source was not held on}. The chain restores a held
    published chart's sections from the fixture commit with that built_at. Carried forward while held."""
    prev = previous or {}
    prev_good = prev.get("last_good") or {}
    prev_holds = prev.get("holds") or {}
    prev_built = (prev.get("site") or {}).get("built_at")
    out = {}
    for source in sources:
        if source not in holds:
            out[source] = (site_doc or {}).get("built_at") or prev_good.get(source)
        elif source in prev_holds:
            out[source] = prev_good.get(source)
        else:  # newly held: the chart the previous run saw without a hold
            out[source] = prev_built or prev_good.get(source)
    return out


def run(sources=SOURCES, *, fetch: Fetcher, store, ident: Identity, site_doc, site_error, report, report_where,
        now: datetime | None = None, extras: dict | None = None, universe: dict | None = None,
        previous: dict | None = None) -> tuple[dict, dict]:
    now = now or utcnow()
    results, divergences = [], {}
    for source in sources:
        res, div = check_source(source, fetch=fetch, store=store, ident=ident, site_doc=site_doc,
                                site_error=site_error, report=report, report_where=report_where, now=now,
                                extras=extras)
        results.append(res)
        divergences[source] = div
    doc = {
        "schema": SCHEMA, "checked_at": iso(now), "run_id": str(uuid.uuid4()),
        "overall": worst(*(r["status"] for r in results)),
        "site": {"url": SITE_FIXTURE, "built_at": (site_doc or {}).get("built_at"), "error": site_error},
        "rules": RULES,
        "holds": {r["source"]: r["hold"] for r in results if r.get("hold")},
        "sources": results,
        "not_covered": NOT_COVERED,
        "requests": len(fetch.log),
        "universe": universe if universe is not None else universe_report(),
    }
    doc["last_good"] = last_good(sources, doc["holds"], site_doc, previous)
    before = {k: (v or {}).get("reason") for k, v in ((previous or {}).get("holds") or {}).items() if k in sources}
    doc["holds_changed"] = before != {k: v["reason"] for k, v in doc["holds"].items()}
    return doc, divergences


# --------------------------------------------------------------------------
# History (Supabase) -- public.fidelity_runs / public.fidelity_divergences
# --------------------------------------------------------------------------

def history_rows(doc: dict, divergences: dict, ident: Identity | None = None) -> tuple[list[dict], list[dict]]:
    """One fidelity_runs row per source and up to MAX_DIVERGENCE_ROWS divergence rows per source."""
    runs, divs = [], []
    finished = doc["checked_at"]
    for r in doc["sources"]:
        run_id = str(uuid.uuid4())
        stages = r["stages"]
        compared = sum((s.get("counts") or {}).get("compared", 0) for s in stages.values())
        diverged = len(divergences.get(r["source"], []))
        blocked = sum(1 for s in stages.values() if s["status"] == "unknown")
        runs.append({
            "run_id": run_id, "pulse_id": doc["run_id"], "check_name": CHECK_NAME, "source": r["source"],
            "status": r["status"], "season": SEASON,
            "week": r.get("chart_week") or r.get("stored_week") or r.get("content_week"),
            "scoring_format": "all", "exit_code": {"green": 0, "amber": 1, "red": 2}.get(r["status"], 1),
            "n_compared": compared, "n_diverged": diverged, "n_blocked": blocked,
            "checks": {k: {kk: vv for kk, vv in v.items()
                           if kk not in ("examples", "unresolved", "grains", "outside_universe")}
                       for k, v in stages.items()} | {"hold": r.get("hold")},
            "started_at": finished, "finished_at": finished})
        ranked = sorted(divergences.get(r["source"], []),
                        key=lambda d: -abs(d.get("delta") or 0) if d["type"] == "value_mismatch" else 0)
        for d in ranked[:MAX_DIVERGENCE_ROWS]:
            divs.append({
                "run_id": run_id, "check_name": CHECK_NAME, "source": r["source"], "stage": d["stage"],
                "season": SEASON, "week": r.get("chart_week") or r.get("stored_week"), "scoring_format": d["grain"],
                "player_key": d["player_key"], "player_id": ident.uuid(d["player_key"]) if ident else None,
                "player_name": d.get("name"), "canonical_name": ident.name(d["player_key"]) if ident else None,
                "position": d.get("pos"),
                "live_value": _num(d.get("left")), "served_value": _num(d.get("right")),
                "diff": d.get("delta"), "divergence_type": d["type"], "source_url": d.get("source_url"),
                "checked_at": finished})
    return runs, divs


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def write_history(doc: dict, divergences: dict, ident: Identity) -> str:
    import gh_sbclient as sb  # noqa: PLC0415
    runs, divs = history_rows(doc, divergences, ident)
    sb.post("fidelity_runs", runs, prefer="return=minimal")
    for i in range(0, len(divs), 500):
        sb.post("fidelity_divergences", divs[i:i + 500], prefer="return=minimal")
    return f"wrote {len(runs)} fidelity_runs and {len(divs)} fidelity_divergences rows"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_site(fetch: Fetcher, path: str | None) -> tuple[dict | None, str | None]:
    if path:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8")), None
        except Exception as e:  # noqa: BLE001
            return None, f"{path}: {type(e).__name__}: {e}"
    st, text, _ = fetch.get(SITE_FIXTURE + f"?pulse={int(time.time())}")
    if st != 200:
        return None, f"{SITE_FIXTURE}: HTTP {st}"
    try:
        return json.loads(text), None
    except ValueError:
        return None, f"{SITE_FIXTURE}: not valid JSON"


def summary_lines(doc: dict) -> list[str]:
    lines = [f"Fidelity pulse {doc['checked_at']}: overall {doc['overall']}"]
    if doc.get("universe"):
        lines.append(f"  Universe     {doc['universe'].get('status'):<7} {doc['universe'].get('summary')}")
    for r in doc["sources"]:
        lines.append(f"  {r['label']:<12} {r['status']:<7} stored week {r['stored_week']} / chart week {r['chart_week']}"
                     + (f"  HOLD {r['hold']['reason']}" if r.get("hold") else ""))
        for name in STAGES:
            s = r["stages"][name]
            lines.append(f"    {name:<20} {s['status']:<7} {s['summary'][:400]}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "output" / "fidelity-pulse.json"))
    ap.add_argument("--sources", default=",".join(SOURCES))
    ap.add_argument("--site-json", help="read the chart file from disk instead of the live site")
    ap.add_argument("--offline-dir", help="stored_<source>.json + players.json instead of Supabase (local runs)")
    ap.add_argument("--write-supabase", action="store_true", help="append the run to public.fidelity_runs")
    ap.add_argument("--no-relay", action="store_true", help="do not use the USA Today relay")
    ap.add_argument("--previous", default=str(ROOT / "dist" / "modules" / "fidelity-pulse.json"),
                    help="the last published pulse (carries each source's last good chart forward)")
    args = ap.parse_args(argv)

    sources = [s for s in args.sources.split(",") if s]
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        ap.error(f"unknown or not yet covered source(s): {unknown}")
    fetch = Fetcher(relay=None if args.no_relay else usatoday_relay)
    store = OfflineStore(Path(args.offline_dir)) if args.offline_dir else SupabaseStore()
    ident = Identity.load(store.players())
    site_doc, site_error = load_site(fetch, args.site_json)
    report, where = load_value_check(fetch=fetch)
    extras = load_extras(fetch, site_doc, utcnow(), store)
    try:
        previous = json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous else None
    except (OSError, ValueError):
        previous = None
    doc, divergences = run(sources, fetch=fetch, store=store, ident=ident, site_doc=site_doc,
                           site_error=site_error, report=report, report_where=where, extras=extras,
                           previous=previous)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
    print("\n".join(summary_lines(doc)))
    print(f"wrote {out}")
    if args.write_supabase:
        try:
            print(write_history(doc, divergences, ident))
        except Exception as e:  # noqa: BLE001 - history is best effort; the artifact is written
            print(f"::warning title=fidelity pulse history::{type(e).__name__}: {str(e)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
