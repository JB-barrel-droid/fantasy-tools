"""Repository identity for org cutover prep (JEG-1468).

Set DDF_GITHUB_REPOSITORY at build/runtime after the org name is confirmed.
The old slug remains the default until cutover. Planned org: datadrivenfootball.
"""
import os
import re

OLD_REPOSITORY = "JB-barrel-droid/fantasy-tools"
PLANNED_REPOSITORY = "datadrivenfootball/fantasy-tools"
WRITER_REPOSITORIES = frozenset((OLD_REPOSITORY.lower(), PLANNED_REPOSITORY.lower()))
REPOSITORY = os.environ.get("DDF_GITHUB_REPOSITORY") or OLD_REPOSITORY
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/fantasy-tools", REPOSITORY):
    raise ValueError("Invalid DDF_GITHUB_REPOSITORY")
SITE_URL = f"https://{REPOSITORY.split('/')[0].lower()}.github.io/fantasy-tools/"

if __name__ == "__main__":
    print(SITE_URL)
