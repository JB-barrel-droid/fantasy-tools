#!/usr/bin/env python3
"""Build the JEG-1209 Fieldnotes revision 3 private preview (index.html and revision2.html).

Private design review only: nothing here is published (pipelines/build_v2_page.py and make sync never read preview/).

The page is assembled from three inputs, none of which this script changes:
  * the preserved revision-2 baseline from PR #1089 (docs/design/jeg-1209-fieldnotes/prototype.html, pinned by sha256):
    its CSS tokens/components, its embedded Fraunces font and its historical Week 7 fixture rows;
  * unchanged copies of the sibling components (vendor/, pinned by commit and git blob in vendor/MANIFEST.json);
  * this continuation's own markup, CSS and script (src/).

No free text inputs (Jeremy, 2026-10-29, approving Fieldnotes with changes: "no free text inputs"). The baseline and the
vendor copies stay byte-for-byte pinned; NO_FREE_TEXT below lists every change the build makes to them for that rule, each
an exact replacement that must match once, so the list is the rollout spec for JEG-1137 to JEG-1140 and JEG-1217.
revision2.html is the revision-2 page with those changes, so every route the preview links to follows the rule.

  python3 preview/jeg-1209-fieldnotes/build.py           writes index.html
  python3 preview/jeg-1209-fieldnotes/build.py --check   exits 1 when index.html, the baseline or a vendor file drifted
  python3 preview/jeg-1209-fieldnotes/build.py --vendor  re-copies vendor/ from the commits in MANIFEST.json (needs them fetched)
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = ROOT / "docs/design/jeg-1209-fieldnotes/prototype.html"
BASELINE_SHA256 = "f66e00c6f0098c46fcac6552943dfdcfc8f7b1302325c37a99c4ad1764adcf07"   # #1089 head 2c893123
BASELINE_COMMIT = "2c8931231ccd2bbeb4946ac031aee5ac655182f4"
OUT = HERE / "index.html"
OUT_R2 = HERE / "revision2.html"
VENDOR = HERE / "vendor"
# Load order matters: the stores first, then the components, then the Managers and Trade ideas cards that mount on them.
VENDOR_JS = ["workspace.js", "opportunities.js", "league-status.js", "opponent-inclusion.js", "column-order.js",
             "manager-profiles.js", "manager-recs.js", "manager-profiles-ui.js", "manager-recs-ui.js"]
VENDOR_CSS = ["league-status.css", "opponent-inclusion.css", "column-order.css", "manager-profiles.css"]


# (file, what it replaces it with, old, new). "baseline" is the revision-2 prototype; other names are vendor files.
NO_FREE_TEXT = [
    ("baseline", "Team name box: dropped; a single roster is named My team and the league paste names its own teams",
     '<div class="field"><label for="teamName">Team name <span class="muted">(for a single roster)</span></label><input id="teamName" value="Sample roster" autocomplete="off"></div>', ''),
    ("baseline", "", "name:$('#teamName').value.trim()||'My team'", "name:'My team'"),
    ("baseline", "", "$('#teamName').value='Team '+(state.rosters.length+1);", ""),
    ("baseline", "League paste box: a Paste from clipboard button that reads what was copied, and says what it read",
     '<div class="field"><label for="pasteBox">Paste roster text</label><textarea id="pasteBox" placeholder="Paste a roster page or player names" aria-describedby="pasteHelp"></textarea><p class="meta" id="pasteHelp">Check the matches before saving. No platform connection is made.</p></div>',
     '<div class="field"><p class="fieldlabel">Roster text</p><button id="readClipboard" class="primary" aria-describedby="pasteHelp">Paste from clipboard</button><p class="meta" id="pasteRead" role="status" aria-live="polite">${pastedText?pastedLines():"Nothing pasted yet."}</p><p class="meta" id="pasteHelp">Copy the roster page on your platform, then press Paste. Nothing is typed here. Check the matches before saving. No platform connection is made.</p></div>'),
    ("baseline", "", "function checkPaste(){let text=$('#pasteBox').value.trim();",
     "let pastedText='';function pastedLines(){const n=pastedText.split(/\\n/).filter(l=>l.trim()).length;return 'Read '+n+' line'+(n===1?'':'s')+' from your clipboard.'}"
     "async function readClipboard(){try{const t=await navigator.clipboard.readText();if(!t||!t.trim()){$('#pasteRead').textContent='Your clipboard is empty. Copy the roster page first.';return}pastedText=t;$('#pasteRead').textContent=pastedLines();$('#pasteError').innerHTML=''}"
     "catch(e){$('#pasteRead').textContent='This browser did not allow reading the clipboard. Allow it when asked, or use the sample.'}}"
     "function checkPaste(){let text=pastedText.trim();"),
    ("baseline", "", "case'loadSample':$('#pasteBox').value='Puka Nacua\\nJahmyr Gibbs\\nGeorge Kittle\\nChris Olave';",
     "case'readClipboard':readClipboard();break;case'loadSample':pastedText='Puka Nacua\\nJahmyr Gibbs\\nGeorge Kittle\\nChris Olave';$('#pasteRead').textContent='Using the sample: 4 player names.';"),
    ("baseline", "", "$('#pasteBox').focus();", "$('#readClipboard').focus();"),
    ("baseline", "Buy & sell name search: position buttons (All, QB, RB, WR, TE), like Values",
     '<div class="search"><label for="targetSearch" class="meta">Find a player in this list</label><input id="targetSearch" type="search" placeholder="Search names" value="${esc(state.query)}"></div>',
     '<div class="segmented" aria-label="Position">${[\'ALL\',\'QB\',\'RB\',\'WR\',\'TE\'].map(pos=>`<button data-target-pos="${pos}" aria-pressed="${(state.targetPos||\'ALL\')===pos}">${pos===\'ALL\'?\'All\':pos}</button>`).join(\'\')}</div>'),
    ("baseline", "", "function targets(){let list=DATA.targets[state.targetTab].filter(p=>p.name.toLowerCase().includes(state.query.toLowerCase()));",
     "function targets(){let list=DATA.targets[state.targetTab].filter(p=>(state.targetPos||'ALL')==='ALL'||p.pos===state.targetPos);"),
    ("baseline", "", "if(b.dataset.valuePos){", "if(b.dataset.targetPos){state.targetPos=b.dataset.targetPos;persist();render();return}if(b.dataset.valuePos){"),
    ("baseline", "Values name search: dropped; the position buttons and Show more already narrow the list",
     '<div class="search"><label for="valueSearch" class="meta">Find a player</label><input id="valueSearch" type="search" value="${esc(state.valueSearch)}" placeholder="Search player names"></div>', ''),
    ("baseline", "", "&&r.name.toLowerCase().includes((state.valueSearch||'').toLowerCase())", ""),
    ("baseline", "Server URL box (read-only): shown as text beside its Copy button",
     '<label for="mcpEndpoint">DDF remote MCP server URL</label><input id="mcpEndpoint" readonly value="https://YOUR-DDF-MCP-ENDPOINT.example/mcp">',
     '<p class="fieldlabel">DDF remote MCP server URL</p><p><code id="mcpEndpoint">https://YOUR-DDF-MCP-ENDPOINT.example/mcp</code></p>'),
    ("baseline", "", "copy($('#mcpEndpoint').value)", "copy($('#mcpEndpoint').textContent)"),
    ("baseline", "Copy fallback box (read-only): the text shown selected, ready to copy",
     "<label for=\"copyFallback\">Select and copy</label><textarea id=\"copyFallback\" readonly>${esc(text)}</textarea>`);$('#copyFallback').select()",
     "<p class=\"meta\">Selected for you. Copy it with your device's copy command.</p><pre id=\"copyFallback\" tabindex=\"0\">${esc(text)}</pre>`);{const r=document.createRange();r.selectNodeContents($('#copyFallback'));const sel=getSelection();sel.removeAllRanges();sel.addRange(r);$('#copyFallback').focus()}"),
    ("baseline", "", "</head>", "<style>#copyFallback{white-space:pre-wrap;word-break:break-word;max-height:50vh;overflow:auto;padding:12px;border:1px solid var(--line);border-radius:9px}"
     "#mcpEndpoint{word-break:break-all}.fieldlabel{font-weight:650;margin-bottom:8px}</style></head>"),
    ("baseline", "Revision-2 Find a trade route: opens the revision-3 page, so there is one finder to review",
     "function render(){", "function render(){if(location.hash.slice(1).split('?')[0]==='finder'){location.replace('index.html#finder');return}"),
    ("manager-profiles-ui.js", "Managers note box (JEG-1217): checkboxes for common leanings, saved in the same note field",
     'const note = el("textarea", {id: `v2MgNote-${key}`, class: "v2-mg-note", rows: "2", maxlength: String(M.MAX_NOTE), placeholder: "Anything else, like \\"loves rookies\\""});\n'
     '    note.value = p.note;\n'
     '    note.addEventListener("change", () => edit(row.teamId, (b, w, id) => M.ops.setNote(b, w, id, note.value)));',
     'const NOTE_TAGS = ["Likes rookies", "Wants draft picks", "Win-now", "Rebuilding", "Slow to reply", "Rarely trades"];\n'
     '    const picked = new Set(String(p.note || "").split(";").map(t => t.trim()).filter(t => NOTE_TAGS.includes(t)));\n'
     '    const note = el("fieldset", {id: `v2MgNote-${key}`, class: "v2-mg-tags"}, el("legend", {text: "Also true of them"}),\n'
     '      ...NOTE_TAGS.map((t, i) => {\n'
     '        const box = el("input", {type: "checkbox", id: `v2MgTag-${key}-${i}`});\n'
     '        box.checked = picked.has(t);\n'
     '        box.addEventListener("change", () => {\n'
     '          if (box.checked) picked.add(t); else picked.delete(t);\n'
     '          edit(row.teamId, (b, w, id) => M.ops.setNote(b, w, id, NOTE_TAGS.filter(x => picked.has(x)).join("; ")));\n'
     '        });\n'
     '        return el("label", {class: "v2-mg-tag", for: box.id}, box, el("span", {text: t}));\n'
     '      }));'),
    ("manager-profiles-ui.js", "",
     'el("label", {class: "v2-mg-field v2-mg-note-field", for: `v2MgNote-${key}`}, el("span", {class: "v2-mg-field-name", text: "Note"}), note)', 'note'),
    ("manager-profiles-ui.js", "", "Other leanings (say which in the note)", "Other leanings (tick which below)"),
]


def no_free_text(name, text):
    for target, _, old, new in NO_FREE_TEXT:
        if target != name:
            continue
        if text.count(old) != 1:
            raise SystemExit(f"no-free-text patch for {name} matched {text.count(old)} times: {old[:70]!r}")
        text = text.replace(old, new)
    return text


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def manifest():
    return json.loads((VENDOR / "MANIFEST.json").read_text())


def check_inputs():
    problems = []
    if hashlib.sha256(BASELINE.read_bytes()).hexdigest() != BASELINE_SHA256:
        problems.append(f"baseline changed: {BASELINE.relative_to(ROOT)} no longer matches #1089 ({BASELINE_COMMIT[:8]})")
    for item in manifest()["files"]:
        if git_blob(VENDOR / item["file"]) != item["blob"]:
            problems.append(f"vendor/{item['file']} differs from {item['branch']} @ {item['commit'][:8]}")
    return problems


def baseline_parts():
    text = BASELINE.read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", text, re.S).group(1)

    def const(name):
        line = next(l for l in text.splitlines() if l.startswith(f"const {name}="))
        return json.loads(line[len(f"const {name}="):].rstrip().rstrip(";"))

    data = const("DATA")
    fixture = {
        "baseline": {"pr": 1089, "commit": BASELINE_COMMIT, "path": str(BASELINE.relative_to(ROOT))},
        "provenance": data["provenance"],
        # Only what the cards read: identity and the value series. Numbers are copied, never rounded or edited.
        "players": [{k: p[k] for k in ("player_key", "name", "pos", "team", "values")} for p in data["players"]],
        "finder": const("FINDER_DATA"),
        "rosters": const("ROSTERS_DATA")["teams"],
    }
    return css, fixture


def build():
    css, fixture = baseline_parts()
    vendor_css = "\n".join(f"/* vendor/{n} */\n" + (VENDOR / n).read_text(encoding="utf-8") for n in VENDOR_CSS)
    vendor_js = "\n".join(f"</script><script>/* vendor/{n} */\n" + no_free_text(n, (VENDOR / n).read_text(encoding="utf-8")) for n in VENDOR_JS)
    src = {n: (HERE / "src" / n).read_text(encoding="utf-8") for n in ("body.html", "continuation.css", "continuation.js")}
    pins = {m["file"]: f"{m['branch']}@{m['commit'][:8]}" for m in manifest()["files"]}
    head = ('<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
            '<title>Find a trade: Fieldnotes r3 (private)</title>'
            f'<!-- Built by preview/jeg-1209-fieldnotes/build.py. Private design review, not published. Baseline #1089 {BASELINE_COMMIT[:8]}. Do not edit by hand. -->')
    fixture_js = "const FIXTURE=" + json.dumps(fixture, separators=(",", ":")).replace("</", "<\\/") + ";const VENDOR_PINS=" + json.dumps(pins) + ";"
    return (head + "<style>" + css + "</style><style>" + vendor_css + "</style><style>" + src["continuation.css"] + "</style></head><body>"
            + src["body.html"] + "<script>" + fixture_js + vendor_js + "</script><script>" + src["continuation.js"] + "</script></body></html>\n")


def build_revision2():
    text = no_free_text("baseline", BASELINE.read_text(encoding="utf-8"))
    note = ("<!-- Built by preview/jeg-1209-fieldnotes/build.py from the revision-2 prototype (#1089 "
            f"{BASELINE_COMMIT[:8]}) with the no-free-text changes in NO_FREE_TEXT. Private design review. Do not edit by hand. -->")
    return text.replace("<head>", "<head>" + note, 1)


def refresh_vendor():
    for item in manifest()["files"]:
        data = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{item['commit']}:{item['path']}"])
        (VENDOR / item["file"]).write_bytes(data)


def main(argv):
    if "--vendor" in argv:
        refresh_vendor()
    problems = check_inputs()
    if "--check" in argv:
        for out, made in ((OUT, build), (OUT_R2, build_revision2)):
            if not out.exists() or out.read_text(encoding="utf-8") != made():
                problems.append(f"{out.name} is stale: run python3 preview/jeg-1209-fieldnotes/build.py")
        print("\n".join(problems) if problems else "preview inputs, index.html and revision2.html match")
        return 1 if problems else 0
    if problems:
        print("\n".join(problems))
        return 1
    OUT.write_text(build(), encoding="utf-8")
    OUT_R2.write_text(build_revision2(), encoding="utf-8")
    for out in (OUT, OUT_R2):
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
