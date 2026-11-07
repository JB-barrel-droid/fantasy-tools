"""JEG-1567: keep the whole published site out of search engines.

While source-data permissions are being settled the site is shared by link
only. A robots.txt cannot do this: GitHub Pages serves a project site under
/fantasy-tools/, and crawlers read robots.txt only from the host root
(datadrivenfootball.github.io/robots.txt), outside this repository's path. So
`make sync` adds <meta name="robots" content="noindex, nofollow"> to every
HTML file in dist/ as its last step.

To reverse (let search engines in again): set SITE_NOINDEX = False and run
`make sync`. That is the only switch. Pages that carry their own noindex
(404, /next/, the math inspector, redirect stubs) keep it either way, because
they set it themselves.
"""
from __future__ import annotations

import re
from pathlib import Path

SITE_NOINDEX = True

ROBOTS = '<meta name="robots" content="noindex, nofollow">'
_ROBOTS_TAG = re.compile(r'<meta\b(?=[^>]*\bname=["\']robots["\'])[^>]*>', re.I)
_ANCHOR = re.compile(r'<head(?:\s[^>]*)?>|<meta\s+charset=[^>]*>', re.I)


def noindex_html(html: str, name: str = "page") -> str:
    """Return html with a noindex robots meta. A page already noindex is unchanged."""
    existing = _ROBOTS_TAG.search(html)
    if existing:
        if "noindex" in existing.group(0).lower():
            return html
        return html[:existing.start()] + ROBOTS + html[existing.end():]
    anchor = _ANCHOR.search(html)
    if anchor is None:
        raise ValueError(f"{name}: no <head> or <meta charset>, cannot add noindex")
    return html[:anchor.end()] + ROBOTS + html[anchor.end():]


def apply_site_noindex(dist: Path, enabled: bool | None = None) -> list[str]:
    """Add noindex to every *.html under dist. Returns the paths changed (dist-relative)."""
    if not (SITE_NOINDEX if enabled is None else enabled):
        return []
    changed = []
    for path in sorted(dist.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        out = noindex_html(text, str(path.relative_to(dist)))
        if out != text:
            path.write_text(out, encoding="utf-8")
            changed.append(str(path.relative_to(dist)))
    return changed
