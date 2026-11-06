"""Build the private preview of the redesigned multi-page site (JEG-1534).

app/next/ is a verbatim copy of the redesign wireframes (ddf-handoff
03-built-site). This step publishes it at dist/next/, i.e.
<SITE_URL>next/<page>.html, beside the live hash-routed site, which it never
touches. The pages use relative links only, so they work under any base path.

Per HTML page the build adds, without editing app/next/:
- <meta name="robots" content="noindex, nofollow"> (unlinked preview; a project
  Pages site cannot serve its own robots.txt);
- the site icon in place of the blank data: icon;
- ?v=<build tag> on the page's own .js/.css references, so a deploy never
  serves a new page with an old site.js from the browser cache.
Nothing links to /next/ from a public page.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "next"
DIST = ROOT / "dist"
OUTPUT = "next"

ROBOTS = '<meta name="robots" content="noindex, nofollow">'
ICON_BLANK = '<link rel="icon" href="data:,">'
ICON_SITE = '<link rel="icon" href="../icon.jpg">'
LOCAL_ASSET = re.compile(r'((?:src|href)=")([^"#?:]+\.(?:js|css))(")')


def preview_html(html: str, tag: str | None) -> str:
    if ROBOTS not in html:
        charset = re.search(r'<meta charset="[^"]*">', html, re.I)
        if charset:
            html = html[:charset.end()] + ROBOTS + html[charset.end():]
        else:
            html = re.sub(r"<head>", "<head>" + ROBOTS, html, count=1, flags=re.I)
    html = html.replace(ICON_BLANK, ICON_SITE)
    if tag:
        html = LOCAL_ASSET.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={tag}{m.group(3)}", html)
    return html


def build(dist: Path = DIST, tag: str | None = None, source: Path = SOURCE) -> Path:
    out = dist / OUTPUT
    if out.exists():
        shutil.rmtree(out)
    if not source.is_dir():
        return out
    shutil.copytree(source, out)
    for page in out.rglob("*.html"):
        page.write_text(preview_html(page.read_text(encoding="utf-8"), tag), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(f"Wrote {build()}")
    sys.exit(0)
