"""Publish swapped redesign pages at the site root (JEG-1534 plan step 1+, JEG-1535 first).

The redesign lives in app/next/ (served as the private /next/ preview by build_next_preview.py). A page moves to the
live root in its swap step by being listed in ROOT_PAGES. Per listed page the build:

- writes dist/<page> from app/next/<page> (no noindex: it is a public page);
- for a page whose source carries <!-- ddf-engine --> (values.html and learn.html must), injects the live value engine exactly as the v2 front door carries it: the build-only engine page's
  body (hidden, inert) and its scripts and data islands (build_v2_page.ENGINE_SCRIPT_MARKER to </body>), at the page's
  <!-- ddf-engine --> marker, before the page's own deferred scripts. No second copy of the value math: the page reads
  the engine's rows through app/next/ddf-engine.js;
- rewrites links to redesign pages that are not live yet (not in ROOT_PAGES) to the live hash routes that do their job
  today (LIVE_ROUTES), in the page and in the shared scripts copied beside it, so no public page links into /next/
  or to a page that does not exist at the root;
- copies the shared files the pages load (ROOT_FILES) to dist/, stamped with ?v=<build tag> like the preview;
- replaces dist/next/<page> with a redirect to the root copy, so the preview has one source of truth for a swapped page.

Re-running with the same tag gives the same output. Adding a page later (Learn, Build a Trade, ...) is one entry in
ROOT_PAGES (and the <!-- ddf-engine --> marker when it needs numbers) plus the files it loads in ROOT_FILES.
"""
from __future__ import annotations

import html as html_lib
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "next"
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
from build_next_preview import DATA_VERSION, LOCAL_ASSET, data_version_script  # noqa: E402
from build_v2_page import ENGINE_PAGE, ENGINE_SCRIPT_MARKER, FETCH_SHARE_SHIM  # noqa: E402

ROOT_PAGES = ("values.html", "learn.html", "build.html",
              # JEG-1539 (step 5): the workspace pages and the new front door. index.html replaces the v2 shell at
              # the root; build_v2_page writes the v2 shell build-only (build/v2/index.html) for the render harnesses.
              "index.html", "team.html", "explore.html", "partners.html", "find.html", "waivers.html",
              "settings.html", "ai.html", "compare.html",
              # JEG-1538: the entry pages; connect.html reads pasted rosters against the engine's player rows.
              "connect.html", "setup.html")
# A page gets the engine when its source carries the <!-- ddf-engine --> marker; ENGINE_PAGES must carry it.
ENGINE_PAGES = frozenset({"values.html", "learn.html", "build.html", "connect.html"})
# Files the root pages load from beside them (copied from app/next/). v2/*.js are already published by build_v2_page.
ROOT_FILES = ("site.js", "styles.css", "players-table-1.json", "ddf-engine.js",
              "values-chart.js", "values-buysell.js", "values-overrides.js",
              # Learn (JEG-1536): the posts, the markdown renderer and the numbers tabs.
              "learn/render.js", "learn/posts.json", "learn/posts",
              "learn/numbers/learn-engine.js", "learn/numbers/numbers.js",
              # Workspace pages (JEG-1539).
              "actionbar.js", "actionbar.css", "legacy-routes.js",
              # Lane "team" (JEG-1539): the shared league adapter (DDF.league) for team/explore/partners/settings/find/waivers.
              "ddf-league.js",
              # Lane "find" (JEG-1539): the recommendation and waiver searches, and the two pages' scripts.
              "find-engine.js", "find-page.js", "waivers-page.js",
              # JEG-1561 (lane partners-ranking): the shared "Why" panel for a trade (DDFWhy).
              "ddf-why.js",
              # waivers.html how-to slides (the provider walkthrough).
              # Build a Trade (JEG-1537): the page script, the trade chart component.
              "build-trade.js", "tradechart.js", "tradechart.css",
              "assets/howto/slides",
              # Entry pages (JEG-1538): paste reader, page scripts, league ID screenshots (actionbar.* listed above).
              "rosterparse.js", "league-paste.js", "connect-entry.js", "setup-entry.js",
              "img/league-id")
# JEG-1539: the get-values edge function (supabase/functions/get-values/index.ts) and the MCP tools read the
# players-data island from the site root page (PAGE_URL = <origin>/). The front door has no engine, so it carries that
# island alone (inert JSON, nothing reads it on the page) until get-values reads the data from another address.
DATA_ISLAND_PAGES = frozenset({"index.html"})
PLAYERS_ISLAND = re.compile(r'<script id="players-data" type="application/json">.*?</script>', re.S)
# Shared scripts copied as they are: legacy-routes.js names the redesigned pages on purpose (it is the redirect map).
NO_REWRITE = frozenset({"legacy-routes.js"})
ENGINE_MARKER = "<!-- ddf-engine -->"
ICON_BLANK = '<link rel="icon" href="data:,">'
ICON_SITE = '<link rel="icon" href="icon.jpg">'
BUILD_META = '<meta name="trade-chart-build" content="{tag}">'

# Redesign pages that are not live yet -> the live route that does that job today (relative to the root).
# A page listed in ROOT_PAGES is never rewritten.
LIVE_ROUTES = {
    "build": "./#compare-trade",
    # JEG-1537: Check a trade and Trade detail are the Build a Trade screen.
    "check": "build.html",
    "trade": "build.html",
    "compare": "values.html#buy-sell",
    "find": "./#find-trade",
    "connect": "./#find-trade",
    "setup": "./#find-trade",
    "settings": "./#find-trade",
    "team": "./#find-trade",
    "explore": "./#find-trade",
    "partners": "./#find-trade",
    "waivers": "./#waivers",
    "learn": "./#writing/manifesto",
    "ai": "connect/",
}
# learn.html#numbers/... (how the numbers are made) has a closer live home than the manifesto.
LIVE_ROUTE_BY_HASH = {("learn", "numbers"): "./#writing/how-values"}
PAGE_REF = re.compile(r'(?P<q>["\'])(?P<page>[a-z]+)\.html(?P<rest>[^"\'\s]*)(?P=q)')


def live_href(page: str, rest: str, root_pages=ROOT_PAGES) -> str | None:
    """The root-relative href for a link to <page>.html<rest>, or None to leave it unchanged."""
    if f"{page}.html" in root_pages or page not in LIVE_ROUTES:
        return None
    frag = rest.split("#", 1)[1] if "#" in rest else ""
    by_hash = LIVE_ROUTE_BY_HASH.get((page, frag.split("/", 1)[0]))
    return by_hash or LIVE_ROUTES[page]


def rewrite_links(text: str, root_pages=ROOT_PAGES) -> str:
    def sub(m: re.Match) -> str:
        target = live_href(m.group("page"), m.group("rest"), root_pages)
        return m.group(0) if target is None else f"{m.group('q')}{target}{m.group('q')}"
    return PAGE_REF.sub(sub, text)


def engine_block(engine_html: str) -> str:
    """The engine as v2 carries it: its page body hidden, then its scripts and data islands."""
    body_at = engine_html.index("<body>") + len("<body>")
    scripts_at = engine_html.index(ENGINE_SCRIPT_MARKER)
    end_at = engine_html.rindex("</body>")
    return (FETCH_SHARE_SHIM
            + '<div id="legacyEngine" class="legacy-engine" hidden aria-hidden="true" inert style="display:none">'
            + engine_html[body_at:scripts_at] + "</div>\n  "
            # The tail (scripts, data islands, the engine page's own build footer) stays hidden too.
            + '<div class="legacy-engine-tail" hidden aria-hidden="true" style="display:none">'
            + engine_html[scripts_at:end_at] + "</div>\n")


def build_tag_of(engine_html: str) -> str | None:
    m = re.search(r'<meta name="trade-chart-build" content="([^"]*)">', engine_html)
    return m.group(1) if m else None


def root_page_html(html: str, name: str, engine_html: str | None, tag: str | None, root_pages=ROOT_PAGES) -> str:
    html = rewrite_links(html, root_pages)
    html = html.replace(ICON_BLANK, ICON_SITE)
    if tag:
        html = LOCAL_ASSET.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={tag}{m.group(3)}", html)
        html = DATA_VERSION.sub("", html)
        head = re.search(r"<meta charset=\"[^\"]*\">", html, re.I) or re.search(r"<head(?:\s[^>]*)?>", html, re.I)
        if not head:
            raise ValueError(f"{name}: no <head> to carry the build tag")
        html = html[:head.end()] + BUILD_META.format(tag=html_lib.escape(tag)) + data_version_script(tag) + html[head.end():]
    if name in DATA_ISLAND_PAGES and engine_html is not None:
        island = PLAYERS_ISLAND.search(engine_html)
        if not island:
            raise ValueError(f"{name}: the engine page has no players-data island to carry (get-values reads it here)")
        at = html.rindex("</body>")
        html = html[:at] + island.group(0) + "\n" + html[at:]
    if name in ENGINE_PAGES or ENGINE_MARKER in html:
        if engine_html is None:
            raise ValueError(f"{name}: needs the engine page, which is not built")
        if html.count(ENGINE_MARKER) != 1:
            raise ValueError(f"{name}: needs exactly one {ENGINE_MARKER} marker before its own scripts")
        html = html.replace(ENGINE_MARKER, engine_block(engine_html), 1)
    return html


def redirect_stub(page: str) -> str:
    target = f"../{page}"
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="robots" content="noindex, nofollow">'
            f"<title>Moved</title><link rel=\"canonical\" href=\"{target}\">"
            f"<script>location.replace('{target}'+location.search+location.hash)</script>"
            f"<meta http-equiv=\"refresh\" content=\"0; url={target}\"></head>"
            f"<body><p><a href=\"{target}\">This page has moved.</a></p></body></html>\n")


def build(dist: Path = DIST, tag: str | None = None, source: Path = SOURCE, engine_page: Path = ENGINE_PAGE,
          root_pages=ROOT_PAGES) -> list[Path]:
    engine_html = engine_page.read_text(encoding="utf-8") if engine_page.exists() else None
    tag = tag or (build_tag_of(engine_html) if engine_html else None)
    written = []
    for name in root_files_for(root_pages):
        src = source / name
        if not src.exists():
            raise SystemExit(f"build_root_pages: {name} is missing from {source}")
        out = dist / name
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():   # a folder of data files (Learn's posts): copied whole, so a new post needs no entry here
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(src, out, ignore=shutil.ignore_patterns("README.md", ".DS_Store"))
        elif name.endswith(".js") and name not in NO_REWRITE:
            out.write_text(rewrite_links(src.read_text(encoding="utf-8"), root_pages), encoding="utf-8")
        else:
            shutil.copy2(src, out)
        written.append(out)
    for name in root_pages:
        out = dist / name
        out.write_text(root_page_html((source / name).read_text(encoding="utf-8"), name, engine_html, tag, root_pages),
                       encoding="utf-8")
        written.append(out)
        preview = dist / "next" / name
        if preview.parent.is_dir():
            preview.write_text(redirect_stub(name), encoding="utf-8")
    return written


def root_files_for(root_pages) -> tuple[str, ...]:
    return ROOT_FILES if root_pages else ()


if __name__ == "__main__":
    for path in build():
        print(f"Wrote {path}")
    sys.exit(0)
