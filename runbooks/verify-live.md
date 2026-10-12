# Verify the live site

After a PR that changes published output merges, wait for the `Deploy dashboard` run, then prove the live site serves that build. Site: https://jb-barrel-droid.github.io/fantasy-tools/

## 1. The deploy ran

```
gh run list --workflow=pages.yml --limit 3
```

Expected: the newest run is `completed success`.

## 2. The build tag

```
curl -s https://jb-barrel-droid.github.io/fantasy-tools/ | grep -o "tv-2026[0-9-]*[a-f0-9]*" | head -1
```

Expected: a tag like `tv-20261012-1634-a7bb2bf` (2026-10-12 value). The sha is the merge commit or a newer generated-output commit from the chain, which is normal. `make sync` prints the tag of a local build.

## 3. verify_live.py (known false failure)

```
python3 verify_live.py [expected_build_tag]
```

Prints the HTTP status, the live build tag and PASS or FAIL per marker. **As of 2026-10-12 it exits 1 on a healthy site**: two markers ("news timing badges", "news max-3 cap" in `assets/comparison-dashboard.js`) belong to features that no longer exist (JEG-629). Until that is fixed, read only `HTTP 200`, `Live build tag: ...` and, when you pass the tag, `PASS: build tag matches expected <tag>`. Ignore the two stale FAILs.

## 4. The scheduled live check

`live-page-synthetic.yml` runs a synthetic check of the live page on a schedule (the `live_page_checks` heartbeat, JEG-339). A red there means the page is up but broken; open that run's log.
