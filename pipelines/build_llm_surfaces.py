"""JEG-1028: publish what an AI assistant needs to find and use the Data Driven Football tools.

Writes, under dist/ (called from sync_dashboard_artifacts.main, the single publish path):
  llms.txt                    what the site is, how to connect, how to answer
  ddf-skill/SKILL.md          the Claude skill, readable by a crawler
  ddf-skill.zip               the same skill as an uploadable zip (SKILL.md in a ddf folder)
  mcp-server-card.json        connection card (also at .well-known/mcp/server-card.json)
  get-values.openapi.yaml     Custom GPT Actions schema (copy of docs/get-values.openapi.yaml)
  connect/index.html          the connect guide (docs/use-ddf-in-claude-chatgpt.md as a page), linked from the site footer (JEG-1026)
Sources live in app/llm/; {{SITE_URL}} and {{MCP_URL}} are filled in here so the URLs have one home.
"""
from __future__ import annotations

import html as html_lib
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from lib.repository import SITE_URL
SRC = ROOT / "app" / "llm"
OPENAPI = ROOT / "docs" / "get-values.openapi.yaml"
GUIDE = ROOT / "docs" / "use-ddf-in-claude-chatgpt.md"

# The public remote MCP function (JEG-1012). DDF_MCP_URL overrides it for a new project or domain.
DEFAULT_MCP_URL = "https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp"


def fill(text: str, site_url: str, mcp_url: str) -> str:
    out = text.replace("{{SITE_URL}}", site_url).replace("{{MCP_URL}}", mcp_url)
    if "{{" in out:
        raise SystemExit(f"build_llm_surfaces: unfilled placeholder in template: {out[out.index('{{'):][:40]!r}")
    return out


def _inline(text: str) -> str:
    """Inline Markdown for the guide: `code`, **bold**, [text](url). Everything else is escaped text."""
    out = html_lib.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)


def guide_html(markdown: str) -> str:
    """The connect guide as a small standalone page (JEG-1026). The guide uses headings, paragraphs and bullet lists only."""
    body: list[str] = []
    in_list = False
    title = "Use Data Driven Football in Claude and ChatGPT"
    for line in markdown.splitlines():
        item = re.match(r"^\s*[-*]\s+(.*)$", line)
        if in_list and not item:
            body.append("</ul>")
            in_list = False
        if item:
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline(item.group(1))}</li>")
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            if level == 1:
                title = heading.group(2).strip()
            body.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
        elif line.strip():
            body.append(f"<p>{_inline(line.strip())}</p>")
    if in_list:
        body.append("</ul>")
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<meta name=\"color-scheme\" content=\"light dark\">\n"
            f"<title>{html_lib.escape(title)}</title>\n"
            "<style>body{font:16px/1.55 system-ui,sans-serif;max-width:46rem;margin:0 auto;padding:24px 16px 48px;"
            "background:#F3F7F7;color:#142B25}a{color:#066B4C}code{background:rgba(128,144,139,.18);padding:1px 4px;border-radius:4px;"
            "overflow-wrap:anywhere}li{margin:.35em 0}@media(prefers-color-scheme:dark){body{background:#101A17;color:#E6EFEC}a{color:#7FD4B0}}</style>\n"
            "</head>\n<body>\n<nav><a href=\"../v2/\">Data Driven Football</a></nav>\n" + "\n".join(body) + "\n</body>\n</html>\n")


def build(dist: Path, site_url: str = SITE_URL, mcp_url: str | None = None) -> list[Path]:
    mcp_url = mcp_url or os.environ.get("DDF_MCP_URL") or DEFAULT_MCP_URL
    written: list[Path] = []

    def write(rel: str, text: str) -> None:
        path = dist / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)

    write("llms.txt", fill((SRC / "llms.txt").read_text(encoding="utf-8"), site_url, mcp_url))
    skill = fill((SRC / "skill" / "SKILL.md").read_text(encoding="utf-8"), site_url, mcp_url)
    write("ddf-skill/SKILL.md", skill)
    card = fill((SRC / "server-card.json").read_text(encoding="utf-8"), site_url, mcp_url)
    write("mcp-server-card.json", card)
    write(".well-known/mcp/server-card.json", card)
    shutil.copy2(OPENAPI, dist / "get-values.openapi.yaml")
    written.append(dist / "get-values.openapi.yaml")
    write("connect/index.html", guide_html(GUIDE.read_text(encoding="utf-8")))

    # A skill zip holds one folder with SKILL.md. Fixed timestamp so the file only changes when the text does.
    zip_path = dist / "ddf-skill.zip"
    info = zipfile.ZipInfo("data-driven-football/SKILL.md", date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(info, skill)
    written.append(zip_path)
    return written


if __name__ == "__main__":
    for path in build(ROOT / "dist"):
        print(f"Wrote {path}")
    sys.exit(0)
