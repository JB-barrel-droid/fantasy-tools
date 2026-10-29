#!/usr/bin/env python3
"""Scrape public rest-of-season (ROS) rankings -> ros_rankings snapshot.json (JEG-1198 option C).

Jeremy, 2026-10-29 (option C): "get the fantasy pros ranking, the rankings from hayden winks
and other yahoo analysts, the rankings from espn analysts ... start with 4-5 sources, piped
through supabase". These are RANKINGS for research and review. They never feed DDF Value or
DDF Projections (docs/pipeline-rules.md section 7; tests/test_ros_rankings.py).

Jeremy, 2026-10-29, on reaching 4-5: "try fantasylife, footballguys, rotoballer, roto street
journal, and multiple cuts of the fantasypros data". And, standing: "do not blend weekly data
with ROS data, ever". Every source here is a rest-of-season list; a page that is not one
(title, ecrData type) fails closed, and no weekly ranking is ever stored in this table.

Sources that read cleanly from a GitHub runner without a sign-in (probe runs 2026-10-29):

  fantasypros_ros_ecr   the public ROS expert-consensus pages, one per scoring. Start page
                        https://www.fantasypros.com/nfl/rankings/?type=ros links the Half PPR
                        overall page, which names the PPR and Standard overall pages; each
                        carries its full list as embedded `ecrData` JSON (~400 players,
                        positional rank, min/max/avg/std, expert count, `last_updated_ts`).
                        Positional pages are the same consensus cut by position: not pulled.
  fantasypros_expert_ros each expert's own ROS list that the consensus start page links in its
                        expert table (about 20 experts, among them Roto Street Journal's "Wolf
                        of Roto Street"), in Half PPR, PPR and Standard, the scorings the page
                        offers. Vintage is the table's "Updated" date for that expert. DOUBLE
                        COUNT: the consensus averages a subset of these lists, so a study uses
                        the consensus or the expert lists, never both averaged together.
  yahoo_pianowski_ros   Scott Pianowski's Yahoo "rest-of-season rankings: <POS> Tiers" articles,
                        one position per article on a rotating week. Discovered from his author
                        page plus the seed articles below; the newest article per position wins.
                        Rows are "$<value> <name>" list items under tier headings, in page order.
                        Scoring is not stated on the page: stored as `unstated`.

Not pulled (named in the snapshot's `unavailable` list so the gap stays visible):
  espn_ros_article      the ESPN ROS article answers a runner with HTTP 202 and an empty body;
                        not read any other way.
  hayden_winks_ros      no Hayden Winks ROS ranking page found (his Yahoo hub is preseason and
                        loads by embed; his author page lists weekly "Blueprint" articles only).
  usat_ros_overall      the USA Today ROS table is its trade chart re-sorted (same numbers), and
                        that chart is already a DDF Value input: storing it here would double count.
  fantasylife_ros       the ROS page ships an empty table and fills it in the browser behind a
                        sign-in wall; nothing readable without signing in.
  footballguys_ros      Dave Kluge's weekly ROS article shows QBs only; the rest needs a free
                        account sign-up, which this feed never does.
  rotoballer_ros        the ROS page carries no ranking list; its ranking widget is not a ROS list.
  rsj_ros_article       Roto Street Journal's own site answers a runner with a bot check, and its
                        ROS articles are images; its ROS list is read through the consensus
                        site's expert table instead (fantasypros_expert_ros).

Output: <out-dir>/snapshot.json
  {"schema": "ros-rankings-snapshot-v1", "fetched_at", "sources": {src: {url(s), vintage,
   scoring, experts, rows}}, "rows": [...], "review_rows": [...], "unavailable": [...]}
Each row: source, analyst, scoring, pos, player_name, team, pos_rank, overall_rank,
source_value, tier, rank_min, rank_max, rank_avg, rank_std, experts, source_vintage, source_url.

Fail closed (non-zero exit, no snapshot) with a named code on the
`ROS RANKINGS PULL FAILED [CODE]` line:
  SOURCE_BLOCKED   non-200, bot wall, empty or tiny body
  SOURCE_LAYOUT    the rankings JSON or list markup is gone, or no vintage stamp
  SOURCE_TRUNCATED a position below its row floor
A source that fails is reported and the others still save only when --allow-partial is
passed; by default any source failure fails the run.
Identity (player_key) is resolved by the saver through lib/canonical_players, never here.
DATING: source_vintage is the source's own stamp (ecrData last_updated_ts; the article's
datePublished; the expert table's Updated date), never the run date.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from timestamps import parse_iso_timestamp  # noqa: E402  the repo's stamp parser

POSITIONS = ("QB", "RB", "WR", "TE")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MIN_BODY = 20000
CT = ZoneInfo("America/Chicago")

FP_START = "https://www.fantasypros.com/nfl/rankings/?type=ros"
FP_LINK_RE = re.compile(r"^/nfl/rankings/ros-[a-z-]+\.php$")
FP_SCORING = {"HALF": "half_ppr", "PPR": "ppr", "STD": "standard"}
FP_FLOORS = {"QB": 30, "RB": 60, "WR": 80, "TE": 30}
FP_CUTS_RE = re.compile(r"\bros-(?:half-point-ppr-|ppr-)?overall\.php\b")  # overall page per scoring
FP_EXPERT_RE = re.compile(r"^/nfl/rankings/[a-z0-9-]+\.php$")
FP_EXPERT_TITLE = {"HALF": re.compile(r"\bHalf PPR Rankings\b", re.I),
                   "PPR": re.compile(r"(?<!Half )\bPPR Rankings\b", re.I),
                   "STD": re.compile(r"Fantasy Football Rankings\b", re.I)}
EXPERT_FLOORS = {"QB": 20, "RB": 40, "WR": 50, "TE": 20}
EXPERT_DELAY_S = 0.5  # between expert pages, to read the site gently
EXPERT_STALE_DAYS = 14  # an expert list older than this is kept but labelled stale

YAHOO_AUTHOR = "https://sports.yahoo.com/author/scott-pianowski/"
# Articles a web search returned on 2026-10-29; discovery adds newer ones from the author page.
YAHOO_SEEDS = (
    "https://sports.yahoo.com/fantasy/article/fantasy-football-rest-of-season-rankings-quarterback-tiers-204123014.html",
    "https://sports.yahoo.com/fantasy/article/fantasy-football-rest-of-season-rankings-te-tight-end-tiers-204023236.html",
    "https://sports.yahoo.com/fantasy/article/fantasy-football-rest-of-season-rankings-rb-tiers-195450347.html",
    "https://sports.yahoo.com/fantasy/article/fantasy-football-rest-of-season-rankings-wr-wide-receiver-tiers-205008446.html",
)
YAHOO_LINK_RE = re.compile(r"^/fantasy/article/fantasy-football-rest-of-season-rankings-[a-z0-9-]+\.html$")
YAHOO_TITLE_RE = re.compile(
    r"rest-of-season rankings:\s*(quarterback|qb|running back|rb|wide receiver|wr|tight end|te)\s+tiers", re.I)
YAHOO_POS = {"quarterback": "QB", "qb": "QB", "running back": "RB", "rb": "RB",
             "wide receiver": "WR", "wr": "WR", "tight end": "TE", "te": "TE"}
YAHOO_FLOORS = {"QB": 25, "RB": 50, "WR": 60, "TE": 25}
DOLLAR_RE = re.compile(r"^\$(\d+(?:\.\d+)?)\s+\**\s*(.+?)\s*\**$")  # unexplained "*" marks dropped

UNAVAILABLE = [
    {"source": "espn_ros_article", "reason": "ESPN's ROS article answers a runner with HTTP 202 and an empty body; not read any other way"},
    {"source": "hayden_winks_ros", "reason": "no Hayden Winks rest-of-season ranking page found; his Yahoo pages are preseason or weekly"},
    {"source": "usat_ros_overall", "reason": "USA Today's ROS table repeats its trade chart, already a DDF Value input (double count)"},
    {"source": "fantasylife_ros", "reason": "Fantasy Life's ROS table is empty in the page and fills only behind a sign-in wall"},
    {"source": "footballguys_ros", "reason": "Footballguys shows only its QB ROS list without an account; RB/WR/TE need a sign-up"},
    {"source": "rotoballer_ros", "reason": "RotoBaller's ROS page holds no list; its ranking widget serves draft-style data, not ROS"},
    {"source": "rsj_ros_article", "reason": "Roto Street Journal's site refuses a runner and posts its ROS lists as images; "
                                            "its list is read instead from the expert table (Wolf of Roto Street)"},
]


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def fetch(url: str, timeout: int = 60) -> tuple[int | None, str]:
    """curl with a browser UA (same transport as pull_razzball_ros.fetch)."""
    try:
        p = subprocess.run(
            ["curl", "-sS", "-L", "--compressed", "-o", "-", "-w", "\n%{http_code}", "-A", UA,
             "-H", "Accept-Language: en-US,en;q=0.9", "--max-time", str(timeout), url],
            capture_output=True, text=True, errors="replace", timeout=timeout + 15)
    except Exception as e:  # noqa: BLE001
        return None, f"curl exception: {e}"
    body, _, code = p.stdout.rpartition("\n")
    try:
        return int(code), body
    except ValueError:
        return None, p.stderr or "curl output unparseable"


def get_page(url: str, fetcher=fetch) -> str:
    code, body = fetcher(url)
    if code != 200 or len(body) < MIN_BODY:
        raise PullError(f"{url}: HTTP {code}, {len(body)} bytes", "SOURCE_BLOCKED")
    return body


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def same_site_links(page: str, base: str, path_re: re.Pattern) -> list[str]:
    host = urlparse(base).netloc
    out: list[str] = []
    for href in re.findall(r'href="([^"#]+)"', page):
        full = urljoin(base, htmllib.unescape(href))
        u = urlparse(full)
        if u.netloc == host and path_re.match(u.path):
            full = f"{u.scheme}://{u.netloc}{u.path}"
            if full not in out:
                out.append(full)
    return out


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# --- expert consensus ---------------------------------------------------------------------

def parse_ecr_page(page: str, url: str) -> dict:
    m = re.search(r"var\s+ecrData\s*=\s*", page)
    if not m:
        raise PullError(f"{url}: no ecrData on the page", "SOURCE_LAYOUT")
    try:
        data, _ = json.JSONDecoder().raw_decode(page[m.end():])
    except ValueError as e:
        raise PullError(f"{url}: ecrData does not parse ({e})", "SOURCE_LAYOUT")
    if str(data.get("ranking_type_name", "")).lower() != "ros":
        raise PullError(f"{url}: ecrData is {data.get('ranking_type_name')!r}, not ros", "SOURCE_LAYOUT")
    scoring = FP_SCORING.get(str(data.get("scoring", "")).upper())
    ts = data.get("last_updated_ts")
    if scoring is None or not ts:
        raise PullError(f"{url}: ecrData lacks a known scoring or last_updated_ts", "SOURCE_LAYOUT")
    vintage = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(CT).date().isoformat()
    experts = data.get("total_experts")
    rows, review = [], []
    for p in data.get("players") or []:
        pos = str(p.get("player_position_id") or "").upper()
        if pos not in POSITIONS:
            continue
        pm = re.match(r"^([A-Z]+)(\d+)$", str(p.get("pos_rank") or ""))
        name = str(p.get("player_name") or "").strip()
        if not pm or pm.group(1) != pos or not name:
            review.append({"source": "fantasypros_ros_ecr", "reason": "bad_pos_rank_or_name",
                           "player_name": name, "pos": pos, "pos_rank": p.get("pos_rank")})
            continue
        rows.append({
            "source": "fantasypros_ros_ecr", "analyst": "expert consensus",
            "scoring": scoring, "pos": pos, "player_name": name,
            "team": str(p.get("player_team_id") or "").strip() or None,
            "pos_rank": int(pm.group(2)), "overall_rank": _num(p.get("rank_ecr")),
            "source_value": None, "tier": int(p["tier"]) if str(p.get("tier") or "").isdigit() else None,
            "rank_min": _num(p.get("rank_min")), "rank_max": _num(p.get("rank_max")),
            "rank_avg": _num(p.get("rank_ave")), "rank_std": _num(p.get("rank_std")),
            "experts": int(experts) if str(experts or "").isdigit() else None,
            "source_vintage": vintage, "source_url": url,
        })
    for pos in POSITIONS:
        n = sum(1 for r in rows if r["pos"] == pos)
        if n < FP_FLOORS[pos]:
            raise PullError(f"{url}: {pos} has {n} rows, floor {FP_FLOORS[pos]}", "SOURCE_TRUNCATED")
    return {"url": url, "scoring": scoring, "vintage": vintage, "experts": experts,
            "type": data.get("type"), "rows": rows, "review_rows": review}


def pull_ecr(fetcher=fetch) -> dict:
    start = get_page(FP_START, fetcher)
    links = same_site_links(start, FP_START, FP_LINK_RE)
    if not links:
        raise PullError(f"{FP_START}: links no ROS rankings page", "SOURCE_LAYOUT")
    first = get_page(links[0], fetcher)
    # The linked overall page names the other scorings' overall pages; follow only those names.
    for name in sorted(set(FP_CUTS_RE.findall(first))):
        u = f"https://www.fantasypros.com/nfl/rankings/{name}"
        if u not in links:
            links.append(u)
    pages = [parse_ecr_page(first if u == links[0] else get_page(u, fetcher), u) for u in links]
    got = sorted(pg["scoring"] for pg in pages)
    if len(set(got)) != len(got):
        raise PullError(f"expert consensus: two pages share a scoring {got}", "SOURCE_LAYOUT")
    return {"pages": [{k: v for k, v in pg.items() if k not in ("rows", "review_rows")} for pg in pages],
            "rows": [r for pg in pages for r in pg["rows"]],
            "review_rows": [r for pg in pages for r in pg["review_rows"]]}


# --- each expert's own ROS list ------------------------------------------------------------

def expert_table(start: str) -> list[dict]:
    """The start page's expert table: name (site), their ROS list link, Updated date."""
    out = []
    for row in re.findall(r"<tr\b.*?</tr>", start, re.S | re.I):
        hrefs = [htmllib.unescape(h) for h in re.findall(r'href="([^"]+)"', row)]
        link = next((h for h in hrefs if "type=ros" in h and FP_EXPERT_RE.match(urlparse(h).path)), None)
        dm = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", _text(row))
        nm = re.match(r"^(.+?\(.+?\))", _text(row))
        if link and dm and nm:
            out.append({"analyst": nm.group(1).strip(),
                        "path": urlparse(link).path,
                        "vintage": date(int(dm.group(3)), int(dm.group(1)), int(dm.group(2))).isoformat()})
    return out


def parse_expert_page(page: str, url: str, analyst: str, vintage: str, code: str) -> dict:
    """One expert's ROS list in one scoring. rows is empty when the site says it is not available."""
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    t = _text(title.group(1)) if title else ""
    if "Rest of Season" not in t or not FP_EXPERT_TITLE[code].search(t):
        raise PullError(f"{url}: title {t[:90]!r} is not a {code} rest-of-season list", "SOURCE_LAYOUT")
    vint = date.fromisoformat(vintage)
    season = vint.year if vint.month >= 8 else vint.year - 1
    if not re.search(rf"\b{season}\b", t):
        raise PullError(f"{url}: title is not the {season} season", "SOURCE_LAYOUT")
    tables = re.findall(r"<table\b.*?</table>", page, re.S | re.I)
    rows, review = [], []
    for tr in re.findall(r"<tr\b.*?</tr>", tables[0], re.S | re.I) if tables else []:
        tds = re.findall(r"<td\b[^>]*>(.*?)</td", tr, re.S | re.I)
        if len(tds) < 4:
            continue
        nm = re.search(r'fp-player-name="([^"]+)"', tr)
        rank, pm = _text(tds[0]), re.match(r"^([A-Z]+)(\d+)$", _text(tds[2]))
        if not nm or not rank.isdigit() or not pm:
            review.append({"source": "fantasypros_expert_ros", "reason": "bad_row", "analyst": analyst,
                           "player_name": _text(tds[1])[:60]})
            continue
        if pm.group(1) not in POSITIONS:
            continue
        rows.append({
            "source": "fantasypros_expert_ros", "analyst": analyst, "scoring": FP_SCORING[code],
            "pos": pm.group(1), "player_name": htmllib.unescape(nm.group(1)).strip(),
            "team": _text(tds[3]) or None, "pos_rank": int(pm.group(2)), "overall_rank": float(rank),
            "source_value": None, "tier": None, "rank_min": None, "rank_max": None, "rank_avg": None,
            "rank_std": None, "experts": 1, "source_vintage": vintage, "source_url": url,
        })
    if not rows and "not available" not in _text(page).lower():
        raise PullError(f"{url}: no ranking rows", "SOURCE_LAYOUT")
    return {"url": url, "scoring": FP_SCORING[code], "analyst": analyst, "vintage": vintage,
            "rows": rows, "review_rows": review}


def pull_experts(fetcher=fetch, delay: float | None = None) -> dict:
    start = get_page(FP_START, fetcher)
    experts = expert_table(start)
    if not experts:
        raise PullError(f"{FP_START}: no expert ROS lists linked", "SOURCE_LAYOUT")
    delay = EXPERT_DELAY_S if delay is None and fetcher is fetch else (delay or 0)
    pages, rows, review = [], [], []
    for ex in experts:
        for code in FP_SCORING:
            url = f"https://www.fantasypros.com{ex['path']}?type=ros&scoring={code}"
            if delay:
                time.sleep(delay)
            try:
                pg = parse_expert_page(get_page(url, fetcher), url, ex["analyst"], ex["vintage"], code)
            except PullError as e:  # one expert's page does not sink the others
                review.append({"source": "fantasypros_expert_ros", "reason": e.code, "analyst": ex["analyst"],
                               "scoring": FP_SCORING[code], "error": str(e)[:160]})
                continue
            counts = {p: sum(1 for r in pg["rows"] if r["pos"] == p) for p in POSITIONS}
            short = [p for p in POSITIONS if counts[p] < EXPERT_FLOORS[p]]
            if not pg["rows"] or short:
                review.append({"source": "fantasypros_expert_ros", "reason": "list_short_or_unavailable",
                               "analyst": ex["analyst"], "scoring": FP_SCORING[code], "counts": counts})
                continue
            age = (datetime.now(CT).date() - date.fromisoformat(ex["vintage"])).days
            pages.append({k: v for k, v in pg.items() if k not in ("rows", "review_rows")}
                         | {"counts": counts, "age_days": age, "stale": age > EXPERT_STALE_DAYS})
            rows += pg["rows"]
            review += pg["review_rows"]
    if not rows:
        raise PullError("expert lists: none read in full", "SOURCE_TRUNCATED")
    return {"pages": pages, "rows": rows, "review_rows": review}


# --- Yahoo, Scott Pianowski ---------------------------------------------------------------

def value_ranks(values: list[float]) -> list[float]:
    """Rank by dollar value, highest first; equal salaries share the average rank.

    Pianowski treats equal salaries as even, and some tiers (an injury tier) sit at the end of
    the page out of value order, so page order is not his rank.
    """
    order = sorted(range(len(values)), key=lambda i: -values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in order[i:j + 1]:
            out[k] = (i + j + 2) / 2
        i = j + 1
    return out


def parse_pianowski_page(page: str, url: str) -> dict | None:
    """Rows of one tiers article, or None when the page is not a ROS tiers article."""
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    tm = YAHOO_TITLE_RE.search(_text(title.group(1)) if title else "")
    if not tm:
        return None
    pos = YAHOO_POS[tm.group(1).lower()]
    dm = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page)
    if not dm:
        raise PullError(f"{url}: no datePublished", "SOURCE_LAYOUT")
    try:
        published = parse_iso_timestamp(dm.group(1))
    except ValueError:
        raise PullError(f"{url}: unreadable datePublished {dm.group(1)!r}", "SOURCE_LAYOUT")
    vintage = published.astimezone(CT).date().isoformat()
    rows, tier, in_tier = [], 0, False
    for m in re.finditer(r"<(h[2-4])\b[^>]*>(.*?)</\1>|<li\b[^>]*>(.*?)</li>", page, re.S | re.I):
        if m.group(1):
            in_tier = False
            continue
        dm2 = DOLLAR_RE.match(_text(m.group(3)))
        if not dm2:
            continue
        if not in_tier:
            tier, in_tier = tier + 1, True
        rows.append({
            "source": "yahoo_pianowski_ros", "analyst": "Scott Pianowski", "scoring": "unstated",
            "pos": pos, "player_name": dm2.group(2).strip(), "team": None,
            "pos_rank": None, "overall_rank": None, "source_value": float(dm2.group(1)),
            "tier": tier, "rank_min": None, "rank_max": None, "rank_avg": None, "rank_std": None,
            "experts": 1, "source_vintage": vintage, "source_url": url,
        })
    if len(rows) < YAHOO_FLOORS[pos]:
        raise PullError(f"{url}: {pos} has {len(rows)} rows, floor {YAHOO_FLOORS[pos]}", "SOURCE_TRUNCATED")
    for r, rank in zip(rows, value_ranks([r["source_value"] for r in rows])):
        r["pos_rank"] = rank
    return {"url": url, "pos": pos, "published": published.isoformat(), "vintage": vintage,
            "tiers": tier, "rows": rows}


def pull_pianowski(fetcher=fetch) -> dict:
    candidates = list(YAHOO_SEEDS)
    try:
        author = get_page(YAHOO_AUTHOR, fetcher)
        for u in same_site_links(author, YAHOO_AUTHOR, YAHOO_LINK_RE):
            if u not in candidates:
                candidates.append(u)
    except PullError as e:
        print(f"yahoo author page not read ({e}); using the seed articles only")
    newest: dict[str, dict] = {}
    for u in candidates:
        art = parse_pianowski_page(get_page(u, fetcher), u)
        if art and (art["pos"] not in newest or art["published"] > newest[art["pos"]]["published"]):
            newest[art["pos"]] = art
    missing = [p for p in POSITIONS if p not in newest]
    if missing:
        raise PullError(f"yahoo: no ROS tiers article for {missing}", "SOURCE_TRUNCATED")
    return {"pages": [{k: v for k, v in a.items() if k != "rows"} for a in newest.values()],
            "rows": [r for p in POSITIONS for r in newest[p]["rows"]], "review_rows": []}


PULLERS = {"fantasypros_ros_ecr": pull_ecr, "fantasypros_expert_ros": pull_experts,
           "yahoo_pianowski_ros": pull_pianowski}


def build_snapshot(sources, fetcher=fetch, allow_partial=False) -> dict:
    snap = {"schema": "ros-rankings-snapshot-v1", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "sources": {}, "rows": [], "review_rows": [], "failures": [], "unavailable": UNAVAILABLE}
    for src in sources:
        try:
            got = PULLERS[src](fetcher)
        except PullError as e:
            snap["failures"].append({"source": src, "code": e.code, "error": str(e)})
            print(f"ROS RANKINGS PULL FAILED [{e.code}] {src}: {e}")
            continue
        snap["sources"][src] = {"pages": got["pages"], "row_count": len(got["rows"])}
        snap["rows"].extend(got["rows"])
        snap["review_rows"].extend(got["review_rows"])
    if snap["failures"] and (not allow_partial or not snap["rows"]):
        raise PullError("; ".join(f"{f['source']}: {f['error']}" for f in snap["failures"]),
                        snap["failures"][0]["code"])
    snap["row_count"] = len(snap["rows"])
    return snap


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--sources", default=",".join(PULLERS), help="comma-separated, default all")
    ap.add_argument("--allow-partial", action="store_true", help="save the sources that read when one fails")
    ap.add_argument("--print-lists", action="store_true", help="print each ranking as one compact line")
    args = ap.parse_args(argv)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in sources if s not in PULLERS]
    if unknown:
        print(f"ROS RANKINGS PULL FAILED [SOURCE_LAYOUT] unknown sources {unknown}")
        return 2
    try:
        snap = build_snapshot(sources, allow_partial=args.allow_partial)
    except PullError as e:
        print(f"ROS RANKINGS PULL FAILED [{e.code}] {e}")
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "snapshot.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
    for src, meta in snap["sources"].items():
        for pg in meta["pages"]:
            print(f"ros {src} {pg.get('analyst') or ''} {pg.get('pos') or pg.get('scoring')} vintage {pg['vintage']} "
                  f"tiers={pg.get('tiers')} experts={pg.get('experts')} {pg['url']}")
    for src in snap["sources"]:
        for r in [x for x in snap["rows"] if x["source"] == src][:3]:
            print(f"  sample {src}: {r['pos']}{r['pos_rank']} {r['player_name']} value={r['source_value']} tier={r['tier']}")
        print(f"ros {src}: {snap['sources'][src]['row_count']} rows")
    if args.print_lists:  # one compact line per source/scoring/position, for review in the run log
        groups: dict[tuple, list[str]] = {}
        for r in snap["rows"]:
            groups.setdefault((r["source"], r["analyst"], r["scoring"], r["pos"], r["source_vintage"]), []).append(
                f"{r['pos_rank']}:{r['player_name']}:{'' if r['source_value'] is None else r['source_value']:}"
                f":{'' if r['tier'] is None else r['tier']}")
        for k, items in groups.items():
            print("ROSLIST|" + "|".join(k) + "|" + ";".join(items))
    for r in snap["review_rows"][:40]:
        print(f"  review: {json.dumps(r)[:220]}")
    print(f"ros rankings: {snap['row_count']} rows, {len(snap['review_rows'])} review, "
          f"{len(snap['unavailable'])} sources unavailable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
