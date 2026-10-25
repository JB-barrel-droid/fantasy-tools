"""JEG-1028: publish what an AI assistant needs to find and use the Data Driven Football tools.

Writes, under dist/ (called from sync_dashboard_artifacts.main, the single publish path):
  llms.txt                    what the site is, how to connect, how to answer
  ddf-skill/SKILL.md          the Claude skill, readable by a crawler
  ddf-skill.zip               the same skill as an uploadable zip (SKILL.md in a ddf folder)
  mcp-server-card.json        connection card (also at .well-known/mcp/server-card.json)
  get-values.openapi.yaml     Custom GPT Actions schema (copy of docs/get-values.openapi.yaml)
Sources live in app/llm/; {{SITE_URL}} and {{MCP_URL}} are filled in here so the URLs have one home.
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "llm"
OPENAPI = ROOT / "docs" / "get-values.openapi.yaml"

SITE_URL = "https://jb-barrel-droid.github.io/fantasy-tools/"
# The public remote MCP function (JEG-1012). DDF_MCP_URL overrides it for a new project or domain.
DEFAULT_MCP_URL = "https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp"


def fill(text: str, site_url: str, mcp_url: str) -> str:
    out = text.replace("{{SITE_URL}}", site_url).replace("{{MCP_URL}}", mcp_url)
    if "{{" in out:
        raise SystemExit(f"build_llm_surfaces: unfilled placeholder in template: {out[out.index('{{'):][:40]!r}")
    return out


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
