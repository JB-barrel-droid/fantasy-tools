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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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

GRACE_HOURS = 12           # a publisher revision inside this window is amber, after it red
NEW_WEEK_GRACE_HOURS = 24  # a newer publisher week inside this window is amber, after it red
FC_DRIFT_REL = 0.25        # FantasyCalc movement band (relative to the stored value), see docstring
FC_DRIFT_ABS = 50          # ... or this many FantasyCalc points, whichever is larger
FC_SYSTEMIC_SHARE = 0.10   # more than this share of values outside the band is a broken save, not movement
FC_SWAP_RATIO = 1.5        # a stored list this much closer to another live list than to its own is a column swap
EXAMPLES = 8
MAX_DIVERGENCE_ROWS = 200  # per source per run, written to public.fidelity_divergences

SOURCES = ("usatoday", "fantasycalc", "fantasypros", "cbs")
LABEL = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS",
         "espn": "ESPN", "cbsros": "CBS rest of season", "razzball": "Razzball"}
NOT_COVERED = {
    "espn": "not covered yet: projection sources (ESPN, CBS rest of season, Razzball) are the second JEG-480 slice",
    "cbsros": "not covered yet: projection sources are the second JEG-480 slice",
    "razzball": "not covered yet: projection sources are the second JEG-480 slice",
}
SCORINGS = ("std", "half", "full")
STAGES = ("publisher_vs_stored", "stored_vs_chart", "freshness", "reference_vs_engine")
RANK = {"green": 0, "n/a": 0, "amber": 1, "unknown": 1, "red": 2}

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
    "rollup": "a source is the worst of its stages; unknown (input unreadable) counts as amber",
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
            same = (equal_after_rounding(lv["text"], rv["value"]) if printed and lv.get("text") is not None
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
            reasons.append(f"publisher revised the page at {iso(revised)}, after the save; inside the "
                           f"{GRACE_HOURS} h grace window")
        else:
            status = "red"
            if after_save:
                reasons.append(f"publisher revised the page at {iso(revised)}, after the save at {iso(saved_at)}, "
                               f"and the revision is not stored ({GRACE_HOURS} h grace passed)")
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
                 unresolved=unresolved[:EXAMPLES]), cmp


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
                 unresolved=unresolved[:EXAMPLES]), cmp


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
                 report_where, now: datetime) -> tuple[dict, list[dict]]:
    """All four stages for one source. Returns (source result, divergence rows)."""
    stages: dict[str, dict] = {}
    divergences: list[dict] = []
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
            stages["publisher_vs_stored"], cmp = stage_publisher(source, pub, stored, ident, now,
                                                                 chart_universe(site_doc))
            divergences += [dict(d, stage="publisher_vs_stored", source_url=pub.get("url"))
                            for d in divergence_items(cmp)]
        except Exception as e:  # noqa: BLE001
            stages["publisher_vs_stored"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    try:
        stages["stored_vs_chart"], cmp2 = stage_chart(source, site_doc, site_error, store, ident, stored)
        divergences += [dict(d, stage="stored_vs_chart", source_url=SITE_FIXTURE)
                        for d in divergence_items(cmp2)]
    except Exception as e:  # noqa: BLE001
        stages["stored_vs_chart"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    try:
        stages["freshness"] = stage_freshness(source, site_doc, disc, stored, now)
    except Exception as e:  # noqa: BLE001
        stages["freshness"] = stage("unknown", f"check failed: {type(e).__name__}: {e}")
    stages["reference_vs_engine"] = stage_reference(source, report, report_where)

    status = worst(*(rollup(s["status"]) for s in stages.values()))
    examples = []
    for name in STAGES:
        for ex in stages[name].get("examples") or []:
            examples.append({"stage": name, **ex})
    result = {"source": source, "label": LABEL[source], "status": status,
              "stored_week": stored.get("week"), "chart_week": site_week,
              "stored_bake": (stored.get("bake") or {}).get("bake_id"),
              "stages": stages, "worst_examples": examples[:EXAMPLES]}
    return result, divergences


def run(sources=SOURCES, *, fetch: Fetcher, store, ident: Identity, site_doc, site_error, report, report_where,
        now: datetime | None = None) -> tuple[dict, dict]:
    now = now or utcnow()
    results, divergences = [], {}
    for source in sources:
        res, div = check_source(source, fetch=fetch, store=store, ident=ident, site_doc=site_doc,
                                site_error=site_error, report=report, report_where=report_where, now=now)
        results.append(res)
        divergences[source] = div
    doc = {
        "schema": SCHEMA, "checked_at": iso(now), "run_id": str(uuid.uuid4()),
        "overall": worst(*(r["status"] for r in results)),
        "site": {"url": SITE_FIXTURE, "built_at": (site_doc or {}).get("built_at"), "error": site_error},
        "rules": RULES,
        "sources": results,
        "not_covered": NOT_COVERED,
        "requests": len(fetch.log),
    }
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
            "status": r["status"], "season": SEASON, "week": r.get("chart_week") or r.get("stored_week"),
            "scoring_format": "all", "exit_code": {"green": 0, "amber": 1, "red": 2}.get(r["status"], 1),
            "n_compared": compared, "n_diverged": diverged, "n_blocked": blocked,
            "checks": {k: {kk: vv for kk, vv in v.items() if kk not in ("examples", "unresolved", "grains")}
                       for k, v in stages.items()},
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
    for r in doc["sources"]:
        lines.append(f"  {r['label']:<12} {r['status']:<7} stored week {r['stored_week']} / chart week {r['chart_week']}")
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
    doc, divergences = run(sources, fetch=fetch, store=store, ident=ident, site_doc=site_doc,
                           site_error=site_error, report=report, report_where=where)
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
