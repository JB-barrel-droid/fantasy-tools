#!/usr/bin/env python3
"""NEW FantasyPros trade-value-chart pull (repo replacement, stage 2).

Sits alongside ops/watchdog/pull_usatoday.py and pull_cbs.py — the only
existing repo puller that touches a FantasyPros article is the goal-workspace
lottery/bin/pull_fantasypros_chart.py (outside this repo). The CSVs in
weekly_vegas/data/fantasypros/ are its output.

JEG-86 / Jeremy 2026-10-02 directive: "We need to codify elements of the page
such as the headline to the dataset, so that we do not have these errors,
along with rules on how weeks get coded to datasets." The week on the dataset
must come from the page itself (URL slug + headline/H1), not from the request.

Usage:
  pull_fantasypros.py [--week N] [--write] [--url URL]

--write stores ops/watchdog/pulls/fantasypros-<date>.json (repo-local,
provisional — NOT wired into any live path). Default is a dry run that
prints the discovered URL, headline week, and table counts.
"""
from __future__ import annotations

import argparse
import csv
import html as htmllib
import json
import os
import re
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import content_week, fetch, REPO

# Auto-discovery: FantasyPros trade-value-chart article slug embeds the week.
# Candidate template (newest week first); discovery walks week N, N-1, N-2
# and returns the first whose page carries a parseable H1/title AND that
# headline's week matches the URL's week. Discovery never silently reuses
# a stale pinned URL.
SECTION_SLUG = ("https://www.fantasypros.com/2026/09/"
                "fantasy-football-trade-value-chart-week-%d-2026/")


class DiscoveryFailed(RuntimeError):
    pass


def candidate_urls(week=None):
    week = week or content_week()
    return [SECTION_SLUG % w for w in (week, week - 1, week - 2) if w >= 1]


def discover_url(week=None, fetch_fn=fetch):
    """First week-N slug (newest first) whose page is live AND whose page
    headline week matches the slug week. Raises DiscoveryFailed when none
    resolve — never silently reuses a stale pinned URL.

    We require URL week == title week here too (not just on the parsed
    payload) so a slug mismatch is caught at discovery, not after parsing.
    """
    week = week or content_week()
    tried = []
    for w in (week, week - 1, week - 2):
        if w < 1:
            continue
        url = SECTION_SLUG % w
        st, html = fetch_fn(url)
        tried.append((url, st))
        if st != 200 or not html:
            continue
        title = _extract_title_text(html)
        if title is None:
            continue
        title_week = extract_week_from_title(title)
        url_week = extract_week_from_url(url)
        if title_week is None or url_week is None:
            continue
        if title_week != url_week:
            # Slug said week-A, headline said week-B: treat as a stale page
            # (same class of miss as the 2026-10-02 USA Today incident).
            continue
        return url
    raise DiscoveryFailed(
        "no FantasyPros trade chart page found (tried: %s)"
        % [(u.rsplit("/", 2)[-2][:60], s) for u, s in tried])


def _extract_title_text(html):
    """Return the trimmed <title>...</title> text, or the <h1>...</h1> text
    if <title> is absent. Returns None if neither is found.

    Page-title is the more durable evidence: the article publishes with
    "Week N" in the <title> even when the H1 is more verbose. Falls back
    to H1 so a CMS rewrite that drops the <title> still leaves us
    fail-closed evidence instead of silently accepting a non-week page.
    """
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    return None


def extract_week_from_url(url: str) -> int | None:
    """Extract week number from the FantasyPros article URL slug.

    URL pattern: .../fantasy-football-trade-value-chart-week-N-2026/
    Returns None if no week found.
    """
    m = re.search(r"trade-value-chart-week-(\d+)-", url)
    return int(m.group(1)) if m else None


def extract_week_from_title(title: str) -> int | None:
    """Extract week number from the article headline / H1 / page title.

    Title pattern: "Week N fantasy football trade value chart" (or any text
    containing "Week N" as a standalone word). e.g. "Week 4 fantasy
    football trade value chart" -> 4. Returns None if no week found.
    """
    m = re.search(r"\bweek\s+(\d+)\b", title, re.I)
    return int(m.group(1)) if m else None


def validate_week_consistency(url: str, title: str,
                              requested_week: int | None) -> dict:
    """Validate that URL week, headline week, and requested week all agree.

    JEG-86 / Jeremy 2026-10-02: the dataset must carry evidence of what week
    it represents, derived from the page headline/title, not just the
    request. Fail-closed: raises RuntimeError on any mismatch. Returns a
    dict with the validated week and the evidence.
    """
    url_week = extract_week_from_url(url)
    title_week = extract_week_from_title(title) if title else None

    if url_week is None:
        raise RuntimeError(
            "FantasyPros URL has no week slug (url=%s). "
            "Refusing to label dataset without week evidence." % url)
    if title_week is None:
        raise RuntimeError(
            "FantasyPros page title contains no 'Week N' (url=%s, "
            "title=%r). Refusing to label dataset without week evidence."
            % (url, (title or "")[:80]))
    if url_week != title_week:
        raise RuntimeError(
            "FantasyPros URL week (%d) != page title week (%d) (url=%s, "
            "title=%r). Page content does not match slug; refusing to label "
            "dataset." % (url_week, title_week, url, (title or "")[:80]))
    if requested_week is not None and url_week != requested_week:
        raise RuntimeError(
            "FantasyPros requested week (%d) != page week (%d) (url=%s). "
            "Page content does not match request; refusing to label dataset."
            % (requested_week, url_week, url))

    return {
        "week": url_week,
        "week_url": url_week,
        "week_titles": [title_week],
        "week_requested": requested_week,
        "title": title,
    }


def pull(url, fetch_fn=fetch):
    """Fetch + extract the page headline (URL slug + <title>/<h1> evidence).

    The FantasyPros chart page embeds its player-by-player values as a
    structured <table>; this stub returns the page-level week evidence
    that JEG-86 demands. The downstream consumer (FantasyPros saver) reads
    the existing fantasypros_trade_chart.csv — JEG-86 is about the week
    label on that dataset, not about re-implementing the table parser
    that already lives in lottery/bin/pull_fantasypros_chart.py.
    """
    st, html = fetch_fn(url)
    if st != 200 or not html:
        raise RuntimeError("fetch failed: status=%r url=%s" % (st, url))
    title = _extract_title_text(html)
    if title is None:
        raise RuntimeError(
            "FantasyPros page has no <title> or <h1> at %s" % url)
    return title


POSITION_HEADINGS = (("quarterback", "QB"), ("running back", "RB"),
                     ("wide receiver", "WR"), ("tight end", "TE"))


def _cell_text(raw):
    return htmllib.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def published_date(html):
    """Article publication date (YYYY-MM-DD) from article:published_time."""
    m = re.search(r'article:published_time"\s+content="(\d{4}-\d{2}-\d{2})', html)
    return m.group(1) if m else None


def parse_tables(html):
    """-> [(position, name, team, value)] from the four position tables.

    Each table follows a "<Position> ... Trade Value Chart" heading; the
    position comes from that heading, never guessed from the player. Uses
    the 1QB "Value" column (the saver writes 1QB rows). Fails closed unless
    exactly QB, RB, WR and TE are each found once with rows.
    """
    rows, seen = [], []
    pos = None
    for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>|<table.*?</table>", html, re.S | re.I):
        if m.group(1) is not None:
            head = _cell_text(m.group(1)).lower()
            pos = next((p for k, p in POSITION_HEADINGS if k in head), None)
            continue
        if pos is None:
            continue
        trs = re.findall(r"<tr.*?</tr>", m.group(0), re.S | re.I)
        cells = [[_cell_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
                 for tr in trs]
        header = cells[0] if cells else []
        if "Name" not in header or "Value" not in header:
            raise RuntimeError("FantasyPros %s table has no Name/Value header: %r" % (pos, header))
        i_name, i_team, i_val = header.index("Name"), header.index("Team"), header.index("Value")
        n = 0
        for c in cells[1:]:
            if len(c) <= i_val or not c[i_name]:
                continue
            rows.append((pos, c[i_name], c[i_team], float(c[i_val])))
            n += 1
        if n == 0:
            raise RuntimeError("FantasyPros %s table is empty" % pos)
        seen.append(pos)
        pos = None
    if sorted(seen) != ["QB", "RB", "TE", "WR"]:
        raise RuntimeError("FantasyPros position tables found: %s (need QB, RB, WR, TE once each)" % seen)
    return rows


def write_saver_inputs(url, html, week, csv_path, log_path, players=None):
    """Resolve names to player_key and write the CSV + fetch-log entry that
    pipelines/save_fantasypros_references.py reads. Unresolved or ambiguous
    names are left out and reported, never guessed."""
    sys.path.insert(0, os.path.join(REPO, "pipelines"))
    from save_espn_cbs_references import build_name_index, fetch_players, resolve_name
    published = published_date(html)
    if not published:
        raise RuntimeError("FantasyPros page has no article:published_time at %s" % url)
    index = build_name_index(players if players is not None else fetch_players())
    clean, review = [], []
    for pos, name, team, value in parse_tables(html):
        # FantasyPros prints curly apostrophes (D’Andre); the players table uses straight ones.
        key, rec, _ = resolve_name(name.replace("’", "'").replace("‘", "'"), pos, index)
        if key is None:
            review.append((pos, name, team, value))
            continue
        clean.append({"player_key": key, "name": rec["full_name"], "team": team,
                      "value_1": value, "source_name": name, "position": pos})
    if not clean:
        raise RuntimeError("FantasyPros resolved zero players; not writing")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["player_key", "name", "team", "value_1",
                                           "source_name", "position"])
        w.writeheader()
        w.writerows(clean)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "ok": True, "published": published, "review_count": len(review),
                             "rows": len(clean), "url": url, "week": week}) + "\n")
    return clean, review


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--url", default=None,
                    help="explicit article URL (manual override; skips discovery)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--save", action="store_true",
                    help="--saver-inputs, then write the week to Supabase via "
                         "save_fantasypros_references (skips a week already saved)")
    ap.add_argument("--dry-run", action="store_true", help="with --save: no DB write")
    ap.add_argument("--force", action="store_true", help="with --save: save even if the week is in the DB")
    ap.add_argument("--saver-inputs", action="store_true",
                    help="parse the chart, resolve players, and write the CSV + "
                         "fetch log that save_fantasypros_references.py reads")
    args = ap.parse_args()

    want = args.week or content_week()
    url = args.url or discover_url(want)
    print("url:", url, flush=True)
    if args.save and not args.url and (extract_week_from_url(url) or 0) < want:
        print("week %d chart not published yet; newest is %s; skipping" % (
            want, extract_week_from_url(url)), flush=True)
        return 0
    title = pull(url)
    print("title:", title, flush=True)

    # JEG-86 / Jeremy 2026-10-02: codify the week from page elements.
    # The dataset must carry evidence of what week it represents,
    # derived from the page headline/title, not just the request.
    week_info = validate_week_consistency(url, title, args.week)
    print("week validated: %d (url=%d, titles=%s, requested=%s)" % (
        week_info["week"], week_info["week_url"],
        week_info["week_titles"], week_info["week_requested"]), flush=True)

    if args.write:
        outdir = os.path.join(REPO, "ops", "watchdog", "pulls")
        os.makedirs(outdir, exist_ok=True)
        outp = os.path.join(outdir, "fantasypros-%s.json" % date.today().isoformat())
        with open(outp, "w") as f:
            json.dump({"url": url, "fetched_at": date.today().isoformat(),
                       "week": week_info["week"],
                       "week_evidence": week_info,
                       "title": title}, f)
        print("wrote", outp)

    if args.save:
        sys.path.insert(0, os.path.join(REPO, "pipelines"))
        import save_fantasypros_references as saver
        wk = week_info["week"]
        have = saver.count_rows(
            "source_trade_values",
            "?select=player_key&source=eq.fantasypros&variant=eq.as_published"
            "&season=eq.2026&week=eq.%d" % wk)
        if have > 0 and not args.force:
            print("week %d already saved (%d rows); skipping" % (wk, have), flush=True)
            return 0
        args.saver_inputs = True

    if args.saver_inputs:
        sys.path.insert(0, os.path.join(REPO, "pipelines"))
        import save_fantasypros_references as saver
        st, html = fetch(url)
        if st != 200 or not html:
            raise RuntimeError("fetch failed: status=%r url=%s" % (st, url))
        clean, review = write_saver_inputs(url, html, week_info["week"],
                                           str(saver.FP_CSV), str(saver.FP_FETCH_LOG))
        print("saver inputs: %d players -> %s, %d unresolved: %s" % (
            len(clean), saver.FP_CSV, len(review),
            ["%s %s" % (r[0], r[1]) for r in review]))

    if args.save:
        res = saver.save_fantasypros(saver.FP_CSV, dry_run=args.dry_run, week=week_info["week"])
        print("INGEST OK fantasypros week=%d written=%d review=%d bake_id=%s" % (
            week_info["week"], res["written"], res["review_count"], res["bake_id"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())