# Self-hosted runner for the data workflows (JEG-792, lane D)

Context: the data store moves to the Mac mini (`docs/selfhost-supabase.md`).
GitHub's cloud runners cannot reach it, so the workflows that use
`SUPABASE_URL` / `SUPABASE_SERVICE_KEY` must be able to run on a runner that
sits next to it. Nothing here is on by default: until the repository variable
`DATA_RUNNER` is set, every workflow runs on `ubuntu-latest` exactly as before.

## How it works

25 workflows have `runs-on: ${{ vars.DATA_RUNNER || 'ubuntu-latest' }}`.
`DATA_RUNNER` holds one runner label (for example `mac-mini`). Unset or empty
means `ubuntu-latest`.

Left on `ubuntu-latest` on purpose:

- `preview.yml`, `v2-render-test.yml`: triggered by `pull_request`. A
  self-hosted runner runs whatever code a workflow runs, so PR code must never
  reach the Mac.
- `pages.yml`: deploy to GitHub Pages, no data store.
- `divergence-issues.yml`, `espn-history-probe.yml`,
  `sleeper-projections-backfill.yml`: no Supabase secrets.
- `live-page-synthetic.yml` job `monitor-bridge`: no secrets, artifact copy only.

Note on `live-page-synthetic.yml` job `live-gate`: it probes the public site
and then records the result in the data store. On the Mac it probes from the
Mac's network, which is a weaker outside view. Leave `DATA_RUNNER` unset for a
while if you want the outside view, or accept it.

### Triggers (checked 2026-10-21)

None of the 25 has a `pull_request` or `pull_request_target` trigger. Their
triggers are `workflow_dispatch`, `schedule` via pg_cron dispatch, `workflow_run`
(`fidelity-pulse` after "Rebuild comparison chain"; `record-pages-deploy` after
"Deploy dashboard", branch `main`), and `push` to dedicated branches (`bake/**`,
`load/cbsros-*`, `pulse/**`, `health/**`, `loader/**`, `identity/**`, `drift/**`,
`fcsave/*`, `razzball/*`, `draftsharks/*`, `fantasysharks/*`). Branch pushes can
only come from people with write access to this repo; forks cannot trigger them.
Because no PR event reaches these jobs, no `if:` guard was needed. Check this
again if anyone adds `pull_request` to one of them:

    grep -l pull_request $(grep -l DATA_RUNNER .github/workflows/*.yml)   # must print nothing

## Install and register the runner on the Mac

1. On the Mac mini, create a dedicated non-admin macOS user (for example
   `ghrunner`). Do not run the runner as your own login. The user needs
   Python 3.12, `jq`, `git` and `gh` (Homebrew), and network access to the
   local data store.
2. Repo Settings, Actions, Runners, New self-hosted runner, macOS, ARM64. Follow
   the download and `./config.sh` steps GitHub shows (the token is shown once;
   never commit it). Use:
   - name: `mac-mini`
   - labels: `mac-mini` (plus the defaults `self-hosted`, `macOS`, `ARM64`)
   - work folder: default `_work`
3. Install as a launchd service so it survives reboots:
   `./svc.sh install ghrunner && ./svc.sh start && ./svc.sh status`
   (run from the runner folder as the `ghrunner` user; it installs a LaunchAgent,
   so that user must be logged in, or enable auto-login for it).
4. Update policy: leave GitHub's automatic runner self-update on (default). If
   the service stops after a major update, re-run `./svc.sh stop && ./svc.sh start`.
   Check the runner version monthly; a runner older than GitHub's minimum is
   refused jobs.

### macOS differences to expect

Reviewed from the workflow YAML, not run:

- `actions/setup-python@v5` with `3.12` works on macOS ARM64 self-hosted; it
  downloads into the runner tool cache. If it fails, install `python@3.12` with
  Homebrew and the step still passes when that version is on `PATH`.
- Playwright (`rebuild-chain`, `bake-players`, `live-page-synthetic`): the
  `playwright install --with-deps chromium` form is accepted on macOS (deps are a
  Linux concept, so it only downloads the browser). First run downloads
  Chromium into the runner user's cache.
- `/tmp` paths (the `/tmp/gh_shim` pattern, probe output) work: `/tmp` is a
  symlink to `/private/tmp`. They persist between jobs on a self-hosted runner,
  so a stale `/tmp/gh_shim/sbclient.py` can linger; each job overwrites it with
  `cp`.
- Workspace persists between jobs. `actions/checkout` cleans it, but untracked
  generated files under `output/` can survive on a self-hosted runner. Treat
  odd "file already exists" results as this first.
- `apt-get` and `sudo` are not used in any of the 25 workflows (checked by
  grep). `shell:` is not overridden, so steps use bash 3.2 on the Mac: no
  `mapfile`, `readarray`, `declare -A` or `${var,,}` were found in these
  workflows' inline scripts. Scripts in `pipelines/` run under Python, not bash.
- `jq` and `gh` must be installed (several steps call them). GNU-only flags
  (`sed -i` without a suffix, `date -d`, `grep -P`) were not found in the 25
  workflows.
- Only the workflow files were reviewed. Any shell script a step calls was not
  audited for GNU-isms.

## Set the variable

Repo Settings, Secrets and variables, Actions, Variables, New repository
variable: name `DATA_RUNNER`, value `mac-mini`. Do this after the runner shows
Idle and after the GitHub secrets `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` point
at the Mac store. A repository variable, not a secret: the label is not
sensitive.

To try one workflow first without changing everything, there is no per-workflow
override; set the variable, dispatch one workflow, and delete the variable if it
misbehaves (see rollback).

## Restrict who can use the runner

- This repo is owned by a personal account, so GitHub offers no runner groups
  (they are an organization feature). Register the runner at repository level
  (Settings, Actions, Runners) so it is attached to this repo only and no other
  repo can use it.
- If the repo moves to an organization: create a runner group, set Repository
  access to "Selected repositories: fantasy-tools", and leave "Allow public
  repositories" off unless you accept the risk below. Workflow selection in a
  group can pin to `refs/heads/main` workflows; that would block the
  dedicated-branch push triggers (`bake/**`, `load/*` and the like), which then
  would need to move to `workflow_dispatch` on main.
- Settings, Actions, General, "Fork pull request workflows": require approval for
  all outside collaborators (belt and braces; PR workflows are on GitHub-hosted
  runners anyway).
- Keep the workflow `permissions:` blocks as they are (read-only unless needed).

## Security trade-off

Repo visibility (checked 2026-10-21 via the GitHub API): **public**.

GitHub's guidance is not to use self-hosted runners with public repos, because
a pull request from a fork can run arbitrary code on your machine. Here that
is contained by three things, all of which must hold:

1. PR workflows (`preview.yml`, `v2-render-test.yml`) stay on `ubuntu-latest`.
2. None of the 25 data workflows can be triggered by a PR or a fork.
3. Only collaborators with write access can push branches or dispatch workflows.

The remaining exposure: anyone with write access (or a stolen token or PAT with
`workflow` scope) can push a branch such as `load/cbsros-write-x` carrying changed
workflow or pipeline code, and it runs on the Mac with the data store key and
whatever the `ghrunner` user can reach. Mitigations: dedicated unprivileged
user, no personal files or keys in its home, firewall the Mac so the runner user
reaches only the data store port, keep branch protection and 2FA on. If you would
rather not accept this, make the repo private (also hides the dashboard source;
GitHub Pages on a private repo needs a paid plan) or keep `DATA_RUNNER` unset and
reach the Mac through a tunnel instead.

## When the Mac is off

Jobs for the `mac-mini` label wait in the queue. GitHub fails a queued job after
24 hours without a runner (the exact limit is GitHub's, 24h at time of
writing; not verified here). Consequences: scheduled chain runs do not happen,
fidelity pulse and record-pages-deploy do not run, and the site keeps serving the
last deployed snapshot. The pg_cron schedule lives in the data store, which is
also on the Mac, so a Mac outage stops both the trigger and the runner. After a
restart, queued dispatches that have not yet expired start on their own; expired
ones need a manual dispatch.

## Roll back

Delete the repository variable `DATA_RUNNER` (Settings, Secrets and variables,
Actions, Variables). The next run of every workflow is back on `ubuntu-latest`.
Jobs already queued for `mac-mini` stay queued: cancel them in the Actions tab.
Point the secrets back at a reachable data store as well, because the cloud
runners cannot reach the Mac. The runner can then be removed in Settings,
Actions, Runners, or with `./svc.sh uninstall && ./config.sh remove`.
