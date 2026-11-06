"""Build the private preview of the redesigned multi-page site (JEG-1534).

app/next/ is a verbatim copy of the redesign wireframes (ddf-handoff
03-built-site). This step publishes it at dist/next/, i.e.
<SITE_URL>next/<page>.html, beside the live hash-routed site, which it never
touches. The pages use relative links only, so they work under any base path.

Per HTML page the build adds, without editing app/next/:
- <meta name="robots" content="noindex, nofollow"> (unlinked preview; a project
  Pages site cannot serve its own robots.txt); a page without <head> fails the
  build rather than ship indexable;
- the site icon in place of the blank data: icon;
- ?v=<build tag> on the page's own .js/.css references, and a small script that
  adds the same ?v= to the page's relative .json/.md fetches, so a deploy never
  serves a new page with an old site.js or old data from the browser cache.
Re-running on its own output with the same tag changes nothing. Internal
README.md notes are not published. Nothing links to /next/ from a public page.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "next"
DIST = ROOT / "dist"
OUTPUT = "next"
UNPUBLISHED = ("README.md", ".DS_Store")

ROBOTS = '<meta name="robots" content="noindex, nofollow">'
ICON_BLANK = '<link rel="icon" href="data:,">'
ICON_SITE = '<link rel="icon" href="../icon.jpg">'
LOCAL_ASSET = re.compile(r'((?:src|href)=")([^"#?:]+\.(?:js|css))(")')
CHARSET = re.compile(r'<meta charset="[^"]*">', re.I)
HEAD = re.compile(r"<head(?:\s[^>]*)?>", re.I)
DATA_VERSION = re.compile(r'<script data-ddf-next-version="[^"]*">.*?</script>', re.S)
# Wraps fetch and XMLHttpRequest.open: a relative URL ending in .json or .md
# with no query yet gets ?v=<tag>. Absolute, root-relative and queried URLs pass unchanged.
DATA_VERSION_JS = (
    "(function(v){var re=/^(?![a-z][a-z0-9+.-]*:|\\/)[^?#]*\\.(?:json|md)(?=#|$)/i;"
    "function t(u){return typeof u==='string'&&re.test(u)?u.replace(/(#|$)/,'?v='+v+'$1'):u}"
    "var f=window.fetch;if(f)window.fetch=function(u,o){return f.call(window,t(u),o)};"
    "var x=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u){"
    "arguments[1]=t(u);return x.apply(this,arguments)}})(%s);"
)


def data_version_script(tag: str) -> str:
    return f'<script data-ddf-next-version="{tag}">{DATA_VERSION_JS % json.dumps(tag)}</script>'


def preview_html(html: str, tag: str | None, name: str = "page") -> str:
    if ROBOTS not in html:
        anchor = CHARSET.search(html) or HEAD.search(html)
        if not anchor:
            raise ValueError(f"{name}: no <head> or <meta charset>, cannot add noindex")
        html = html[:anchor.end()] + ROBOTS + html[anchor.end():]
    html = html.replace(ICON_BLANK, ICON_SITE)
    if tag:
        html = LOCAL_ASSET.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={tag}{m.group(3)}", html)
        html = DATA_VERSION.sub("", html)
        robots_end = html.index(ROBOTS) + len(ROBOTS)
        html = html[:robots_end] + data_version_script(tag) + html[robots_end:]
    return html


def build(dist: Path = DIST, tag: str | None = None, source: Path = SOURCE) -> Path:
    out = dist / OUTPUT
    if out.exists():
        shutil.rmtree(out)
    if not source.is_dir():
        return out
    shutil.copytree(source, out, ignore=shutil.ignore_patterns(*UNPUBLISHED))
    for page in out.rglob("*.html"):
        name = str(page.relative_to(out))
        page.write_text(preview_html(page.read_text(encoding="utf-8"), tag, name), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(f"Wrote {build()}")
    sys.exit(0)
