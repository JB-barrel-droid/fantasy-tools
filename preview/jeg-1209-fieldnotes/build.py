#!/usr/bin/env python3
"""Build the JEG-1209 Fieldnotes revision 3 private preview (index.html and revision2.html).

Private design review only: nothing here is published (pipelines/build_v2_page.py and make sync never read preview/).

The page is assembled from three inputs, none of which this script changes:
  * the preserved revision-2 baseline from PR #1089 (docs/design/jeg-1209-fieldnotes/prototype.html, pinned by sha256):
    its CSS tokens/components, its embedded Fraunces font and its historical Week 7 fixture rows;
  * unchanged copies of the sibling components (vendor/, pinned by commit and git blob in vendor/MANIFEST.json);
  * this continuation's own markup, CSS and script (src/).

No free text for how leaguemates trade (Jeremy, 2026-10-29: "I just didn't want text boxes for how my leaguemates trade,
and set everyone to default initially"). The Managers card's note box becomes checkboxes and every manager starts at the
default profile; ticking a box keeps any other text already in the note. The baseline and the vendor copies stay
byte-for-byte pinned; PREVIEW_STORAGE (preview-only storage keys) and NO_FREE_TEXT below list every change the build
makes to them, each an exact replacement that must match once. Every other input is as revision 3 had it.
revision2.html is the revision-2 page, so the preview's links work wherever it is opened.

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
VENDOR_JS = ["workspace.js", "opportunities.js", "league-status.js", "opponent-inclusion.js",
             "manager-profiles.js", "manager-recs.js", "manager-profiles-ui.js", "manager-recs-ui.js"]
VENDOR_CSS = ["league-status.css", "opponent-inclusion.css", "manager-profiles.css"]


# Preview-only storage (JEG-1250): the two stores save under their own keys, so opening the preview never reads, replaces
# or deletes a saved league or manager profiles on the same origin. The live keys are ddf.v2.workspaces and
# ddf.v2.managerProfiles; the probe each store writes and removes at start moves too.
PREVIEW_STORAGE = [
    ("workspace.js", "League store key", 'const STORAGE_KEY = "ddf.v2.workspaces";', 'const STORAGE_KEY = "ddf.preview.jeg1209.workspaces";'),
    ("workspace.js", "League store probe", 'const probe = "ddf.v2.probe";', 'const probe = "ddf.preview.jeg1209.probe";'),
    ("manager-profiles.js", "Manager profiles key", 'const STORAGE_KEY = "ddf.v2.managerProfiles";', 'const STORAGE_KEY = "ddf.preview.jeg1209.managerProfiles";'),
    ("manager-profiles.js", "Manager profiles probe", 'const probe = "ddf.v2.probe";', 'const probe = "ddf.preview.jeg1209.probe";'),
]

# (file, what it replaces it with, old, new). "baseline" is the revision-2 prototype; other names are vendor files.
NO_FREE_TEXT = [
    ("manager-profiles-ui.js", "Managers note box (JEG-1217): checkboxes for common leanings, saved in the same note field",
     'const note = el("textarea", {id: `v2MgNote-${key}`, class: "v2-mg-note", rows: "2", maxlength: String(M.MAX_NOTE), placeholder: "Anything else, like \\"loves rookies\\""});\n'
     '    note.value = p.note;\n'
     '    note.addEventListener("change", () => edit(row.teamId, (b, w, id) => M.ops.setNote(b, w, id, note.value)));',
     'const NOTE_TAGS = ["Likes rookies", "Wants draft picks", "Win-now", "Rebuilding", "Slow to reply", "Rarely trades"];\n'
     '    // Ticked boxes lead the note; any other text already in it stays after them word for word, never dropped (JEG-1250).\n'
     '    const parts = String(p.note || "").split("; ");\n'
     '    let lead = 0;\n'
     '    while (lead < parts.length && NOTE_TAGS.includes(parts[lead]) && parts.indexOf(parts[lead]) === lead) lead += 1;\n'
     '    const picked = new Set(parts.slice(0, lead));\n'
     '    const kept = parts.slice(lead).join("; ");\n'
     '    const compose = () => NOTE_TAGS.filter(x => picked.has(x)).concat(kept ? [kept] : []).join("; ");\n'
     '    const full = el("p", {id: `v2MgTagMsg-${key}`, class: "v2-mg-kept", role: "status", "aria-live": "polite"});\n'
     '    const note = el("fieldset", {id: `v2MgNote-${key}`, class: "v2-mg-tags"}, el("legend", {text: "Also true of them"}),\n'
     '      ...NOTE_TAGS.map((t, i) => {\n'
     '        const box = el("input", {type: "checkbox", id: `v2MgTag-${key}-${i}`});\n'
     '        box.checked = picked.has(t);\n'
     '        box.addEventListener("change", () => {\n'
     '          if (box.checked) picked.add(t); else picked.delete(t);\n'
     '          const next = compose();\n'
     '          if (next.length > M.MAX_NOTE) {   // saving would cut the earlier note short, so this box is not saved\n'
     '            picked.delete(t); box.checked = false;\n'
     '            full.textContent = "The earlier note is too long to add this. Nothing was changed.";\n'
     '            return;\n'
     '          }\n'
     '          full.textContent = "";\n'
     '          edit(row.teamId, (b, w, id) => M.ops.setNote(b, w, id, next));\n'
     '        });\n'
     '        return el("label", {class: "v2-mg-tag", for: box.id}, box, el("span", {text: t}));\n'
     '      }),\n'
     '      kept ? el("p", {class: "v2-mg-kept", "data-kept-note": "", text: `Kept from an earlier note: ${kept}`}) : null, full);'),
    ("manager-profiles-ui.js", "",
     'el("label", {class: "v2-mg-field v2-mg-note-field", for: `v2MgNote-${key}`}, el("span", {class: "v2-mg-field-name", text: "Note"}), note)', 'note'),
    ("manager-profiles-ui.js", "", "Other leanings (say which in the note)", "Other leanings (tick which below)"),
    # Not part of the rule: the revision-2 Find a trade route opens the revision-3 page, so there is one finder to review.
    ("baseline", "Revision-2 Find a trade route: opens the revision-3 page, so there is one finder to review",
     "function render(){", "function render(){if(location.hash.slice(1).split('?')[0]==='finder'){location.replace('index.html#finder');return}"),
]


def patched(name, text):
    for target, _, old, new in PREVIEW_STORAGE + NO_FREE_TEXT:
        if target != name:
            continue
        if text.count(old) != 1:
            raise SystemExit(f"preview patch for {name} matched {text.count(old)} times: {old[:70]!r}")
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
    vendor_js = "\n".join(f"</script><script>/* vendor/{n} */\n" + patched(n, (VENDOR / n).read_text(encoding="utf-8")) for n in VENDOR_JS)
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
    text = patched("baseline", BASELINE.read_text(encoding="utf-8"))
    note = ("<!-- Built by preview/jeg-1209-fieldnotes/build.py from the revision-2 prototype (#1089 "
            f"{BASELINE_COMMIT[:8]}); only change: its Find a trade route opens index.html. Private design review. Do not edit by hand. -->")
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
