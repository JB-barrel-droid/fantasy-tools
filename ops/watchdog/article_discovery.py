"""Shared helpers for finding a publisher's "Week N trade value chart" article.

Why this exists (2026-10-08): every source's discovery guessed one URL slug
per week, and the publishers keep changing their slugs. CBS's Week 5 chart
(dave-richards-2026-week-5-trade-chart) matched none of the guessed slugs, so
discovery settled on the Week 4 article and the ingest quietly skipped; USA
Today's "chart" -> "charts" change did the same a day earlier. The remedy:

* read the publisher's own listings (author page, section page, news
  sitemap) and take every link that looks like a trade chart;
* decide the week from the PAGE (headline), never from the slug alone;
* optionally ask a small LLM to point at the right link when the
  deterministic matching finds nothing. The LLM only nominates a URL from the
  listing; the caller still fetches it and runs the same week/table checks;
* make a miss loud once the week is old enough that the article should have
  been found (ingest_common.overdue), instead of a "not published yet" skip
  that can last forever.

Stdlib only (the LLM call imports the `anthropic` SDK lazily, and only when
ANTHROPIC_API_KEY is set).
"""
from __future__ import annotations

import html as _html
import json
import os
import re
from typing import Callable, Iterable
from urllib.parse import urljoin, urlsplit

LLM_MODEL_ENV = "DISCOVERY_LLM_MODEL"
LLM_DEFAULT_MODEL = "claude-haiku-5-5"
LLM_KEY_ENV = "ANTHROPIC_API_KEY"
LLM_MAX_CANDIDATES = 250

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(s: str | None) -> str:
    return _WS_RE.sub(" ", _html.unescape(_TAG_RE.sub(" ", s or ""))).strip()


def url_key(url: str) -> str:
    """Host-insensitive identity of an article (www vs a CDN mirror, trailing
    slash, query string) so one article reached two ways is tried once."""
    p = urlsplit(url)
    return p.path.rstrip("/").lower()


def links_from_html(page: str, base: str) -> list[tuple[str, str]]:
    """(absolute url, anchor text) for every <a href> in a listing page, in
    page order, deduplicated by url_key (the first non-empty text wins)."""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"<a\b[^>]*?href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>",
                         page or "", re.S | re.I):
        url = urljoin(base, _html.unescape(m.group(1)).strip())
        text = clean_text(m.group(2))
        k = url_key(url)
        if k not in out:
            out[k] = [url, text]
        elif not out[k][1] and text:
            out[k][1] = text
    return [(u, t) for u, t in out.values()]


def sitemap_entries(xml: str) -> list[tuple[str, str]]:
    """(loc, news:title or "") for each <url> of a (news) sitemap."""
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml or "", re.S):
        loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", block)
        if not loc:
            continue
        title = re.search(r"<news:title>(.*?)</news:title>", block, re.S)
        out.append((_html.unescape(loc.group(1)),
                    clean_text(title.group(1)) if title else ""))
    return out


_WEEK_SLUG_RE = re.compile(r"(?<![a-z0-9])week-(\d{1,2})(?![0-9])", re.I)
_WEEK_TEXT_RE = re.compile(r"\bweek\s+(\d{1,2})\b", re.I)


def week_in_slug(url: str) -> int | None:
    m = _WEEK_SLUG_RE.search(urlsplit(url).path)
    return int(m.group(1)) if m else None


def week_in_text(text: str | None) -> int | None:
    m = _WEEK_TEXT_RE.search(text or "")
    return int(m.group(1)) if m else None


def link_week(url: str, text: str) -> int | None:
    """Week a listing link advertises: the slug's, else its title's. A slug
    and title that disagree count as unknown (the page decides)."""
    a, b = week_in_slug(url), week_in_text(text)
    if a is not None and b is not None and a != b:
        return None
    return a if a is not None else b


def rank_candidates(links: Iterable[tuple[str, str]], week: int,
                    is_chart: Callable[[str, str], bool]) -> tuple[list[str], int | None]:
    """Chart-looking links ordered for verification: links advertising week
    N first, then links with no week evidence. Links that advertise another
    week are dropped; the newest older week seen is returned for the
    "not published yet" message."""
    exact, unknown, seen = [], [], set()
    newest_older = None
    for url, text in links:
        if not is_chart(url, text):
            continue
        k = url_key(url)
        if k in seen:
            continue
        seen.add(k)
        w = link_week(url, text)
        if w == week:
            exact.append(url)
        elif w is None:
            unknown.append(url)
        elif w < week:
            newest_older = w if newest_older is None else max(newest_older, w)
    return exact + unknown, newest_older


def is_overdue(week: int, week_fn: Callable, grace_days: int, today) -> bool:
    """True when `week` is the current content week (week_fn(today)) and
    already was `grace_days` ago: its chart should have been found by now.
    Backfills of older weeks and future weeks are never overdue."""
    from datetime import timedelta

    return week_fn(today) == week and week_fn(today - timedelta(days=grace_days)) == week


# ---------------------------------------------------------------------------
# LLM fallback: nominate one URL from the listing. Never trusted on its own.
# ---------------------------------------------------------------------------

def _prompt(publisher: str, week: int, season: int,
            links: list[tuple[str, str]]) -> str:
    lines = "\n".join("%d. %s | %s" % (i + 1, u, t or "(no link text)")
                      for i, (u, t) in enumerate(links))
    return (
        "Below are links from %s listing pages. Which ONE link is %s's "
        "fantasy football trade value chart article for Week %d of the %d NFL "
        "season (the weekly article with player trade values / rest-of-season "
        "trade chart tables)? Do not pick a different week's chart, trade "
        "advice columns (buy/sell lists, trade targets), rankings or waiver "
        "articles. Reply with JSON only: {\"index\": <link number>} or "
        "{\"index\": null} if none of the links is that article.\n\n%s"
        % (publisher, publisher, week, season, lines))


def llm_pick(publisher: str, week: int, links: list[tuple[str, str]],
             season: int = 2026, complete: Callable[[str], str] | None = None) -> str | None:
    """Ask a small model which listing link is the week-N chart.

    Returns a URL that is guaranteed to be one of `links` (an invented or
    malformed answer returns None), or None when no key is configured, the
    call fails, or the model says none. `complete` (prompt -> text) is
    injectable for tests; the default calls the Anthropic API.
    """
    links = list(links)[:LLM_MAX_CANDIDATES]
    if not links:
        return None
    if complete is None:
        if not os.environ.get(LLM_KEY_ENV):
            return None
        complete = _anthropic_complete
    try:
        reply = complete(_prompt(publisher, week, season, links))
    except Exception as e:  # the fallback must never break discovery
        print("[discovery] LLM fallback unavailable: %s" % e, flush=True)
        return None
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        idx = json.loads(m.group(0)).get("index") if m else None
    except (ValueError, AttributeError):
        return None
    if isinstance(idx, bool) or not isinstance(idx, int) or not 1 <= idx <= len(links):
        return None
    return links[idx - 1][0]


def _anthropic_complete(prompt: str) -> str:
    import anthropic  # lazy: only CI runs with the key need the SDK

    client = anthropic.Anthropic(timeout=60.0, max_retries=2)
    resp = client.messages.create(
        model=os.environ.get(LLM_MODEL_ENV) or LLM_DEFAULT_MODEL,
        max_tokens=2048,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        return ""
    return "".join(b.text for b in resp.content if b.type == "text")
