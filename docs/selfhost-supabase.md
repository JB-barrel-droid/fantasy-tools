# Self-hosted data store on the Mac mini (JEG-792)

Jeremy decided on 2026-10-21 to run the data store on his Mac mini, because
the cloud Supabase project `iskiybsimubiujwuchsl` is over its egress quota
(HTTP 402) and he will not pay for it. This runbook sets up a minimal
replacement and moves the pipelines onto it.

Files: `selfhost/supabase/` (compose stack, key generator, init SQL, gateway
config, function router, backup/restore/health scripts, launchd plist).

> **Not tested on a Mac.** Everything here was written and checked on Linux
> without a Docker daemon. No container has been started. See
> [What was and was not tested](#what-was-and-was-not-tested) before relying on it.

## What runs

The pipelines reach the data store only through PostgREST
(`pipelines/gh_sbclient.py`: `GET/POST/PATCH/DELETE /rest/v1/<table>`,
`POST /rest/v1/rpc/<fn>`, headers `apikey` and `Authorization: Bearer
<SUPABASE_SERVICE_KEY>`) and one edge function, `usatoday-fetch`
(`ops/watchdog/pull_usatoday.py`, `POST /functions/v1/usatoday-fetch`). So
the stack is:

| Service | Image | Role |
|---|---|---|
| `db` | `supabase/postgres:17.6.1.136` | Postgres 17.6 with pg_cron, pg_net, supabase_vault (cloud is 17.6) |
| `rest` | `postgrest/postgrest:v14.18` | PostgREST, not published to the host |
| `gateway` | `nginx:1.29.3-alpine` | Serves `/rest/v1/*` and `/functions/v1/*` on **127.0.0.1:8000** only; refuses calls without a known `apikey`; the OpenAPI root `/rest/v1/` needs the service key |
| `functions` (profile `relay`) | `supabase/edge-runtime:v1.77.4` | `usatoday-fetch` (JWT verified, service_role only) and `get-values` (public) |
| `tunnel` (profile `tunnel`) | `cloudflare/cloudflared:2026.9.0` | Off by default; see [Option B](#option-b-cloudflare-tunnel-or-tailscale-funnel) |

No Auth, Realtime, Storage, Studio, analytics or pooler. The gateway exists
because PostgREST cannot serve under a `/rest/v1` prefix and the pipelines'
`SUPABASE_URL` must answer both `/rest/v1` and `/functions/v1`.

Image tags are the ones pinned in `supabase/supabase` `docker/docker-compose.yml`
on 2026-10-21 (commit `fdf03de3`). All five images publish `linux/arm64`
(checked with `docker manifest inspect`).

## Prerequisites

- The Mac mini on macOS (Apple silicon), set to not sleep: System Settings >
  Energy > "Prevent automatic sleeping when the display is off" on, and
  "Start up automatically after a power failure" on.
- Docker: [OrbStack](https://orbstack.dev) (lighter) or Docker Desktop, set to
  start at login. Check: `docker compose version` prints v2 or later.
- `git`, `python3` (ships with the Xcode command line tools), `curl`.
- About 5 GB free disk (the cloud database is 804 MB; dumps are smaller).
- Optional: `gh` CLI logged in as JB-barrel-droid, to set secrets.

## 1. Get a dedicated clone

Use a clone that nothing else checks out branches in, because the stack
mounts the function sources from it. Do not use `~/Projects/"fantasy tools"`.

```bash
mkdir -p ~/ddf-selfhost && cd ~/ddf-selfhost
git clone https://github.com/JB-barrel-droid/fantasy-tools.git
cd fantasy-tools/selfhost/supabase
```

Until the JEG-792 PR merges, add `git checkout be/jeg-792-selfhost-stack`.

## 2. Generate secrets

```bash
python3 gen-keys.py --write .env
python3 gen-keys.py --verify .env
```

`--verify` prints `ANON_KEY: ok (role=anon ...)` and
`SERVICE_ROLE_KEY: ok (role=service_role ...)`. `.env` is mode 600 and
gitignored. Keep a copy in your password manager: losing `JWT_SECRET` means
new keys and new GitHub secrets.

## 3. Start the stack

```bash
docker compose --env-file .env pull
docker compose --env-file .env up -d
docker compose --env-file .env ps
```

All three services should show `healthy` (or `running` for `rest`) within a
minute. The first boot runs `init/99-ddf-roles.sql`, which checks the roles
PostgREST uses and creates the extensions the cloud has. If it fails, the
`db` log says why: `docker compose --env-file .env logs db | tail -50`.

To also run the USA Today relay:

```bash
docker compose --env-file .env --profile relay up -d
```

## 4. Import the cloud data

This copies the app schemas (`public`, `api`, `ops`, `monitoring`, `archive`,
`ross`) and then the 20 pg_cron jobs. Supabase-managed schemas (auth,
storage, realtime, vault internals) come from the image instead.

**Unknown:** whether the cloud project still accepts direct Postgres
connections while it is over the egress quota. The dump itself is egress. If
the connection is refused, the fallback is a backup download from the
dashboard (Database > Backups), if your plan offers one.

1. In the Supabase dashboard, click **Connect** and copy the **Session pooler**
   connection string. It looks like
   `postgresql://postgres.iskiybsimubiujwuchsl:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`.
2. Dump with the Postgres 17 client inside the `db` container (so versions
   match), typing the database password when asked:

```bash
read -r -p "Session pooler URL (without password): " CLOUD_URL
read -rs -p "Cloud database password: " PGPASSWORD; echo
mkdir -p ~/ddf-supabase-backups
docker compose --env-file .env exec -T -e "PGPASSWORD=$PGPASSWORD" db \
  pg_dump "$CLOUD_URL" -Fc -n public -n api -n ops -n monitoring -n archive -n ross \
  > ~/ddf-supabase-backups/ddf-cloud-import.dump
unset PGPASSWORD
ls -lh ~/ddf-supabase-backups/ddf-cloud-import.dump
```

3. Export the cron jobs: in the cloud dashboard SQL editor, run the query
   below, copy the single result column, and save it as
   `~/ddf-supabase-backups/ddf-cloud-import.cron.sql`:

```sql
select format('select cron.schedule(%L, %L, %L);', coalesce(jobname, 'job_' || jobid), schedule, command)
       || case when active then '' else format(
            E'\nselect cron.alter_job((select jobid from cron.job where jobname = %L), active := false);',
            coalesce(jobname, 'job_' || jobid)) end
from cron.job order by jobid;
```

4. Restore into the Mac (this also replays the cron file and reloads PostgREST):

```bash
./restore.sh ~/ddf-supabase-backups/ddf-cloud-import.dump
```

Expect a few "already exists" errors for `public` and `api`. Any error about
a missing role, extension or function is real: stop and look at it.

5. Re-enter the Vault secret the cron jobs use. `public.dispatch_gha_workflow`
   reads `github_dispatch_token` from Vault and calls the GitHub API with
   pg_net. Cloud Vault values are encrypted with the cloud's key and do not
   survive a dump, so type the token again (a GitHub PAT with
   `actions:write` on this repo; it is not echoed and stays out of shell
   history, though it is visible to `ps` on the Mac for the second the
   command runs):

```bash
read -rs -p "GitHub dispatch token: " GH_TOKEN; echo
docker compose --env-file .env exec -T -e "GH_TOKEN=$GH_TOKEN" db \
  psql -h localhost -U supabase_admin -d postgres -v ON_ERROR_STOP=1 <<'SQL'
\getenv tok GH_TOKEN
select vault.create_secret(:'tok', 'github_dispatch_token', 'GitHub PAT for pg_cron workflow dispatch');
SQL
unset GH_TOKEN
```

   The other cloud secret, `supabase_service_key`, is not read by any
   function or cron job (checked 2026-10-21); skip it.

6. **Avoid double dispatch.** Once the Mac's cron jobs exist, the cloud's 20
   jobs would fire the same workflows. At cutover, in the cloud SQL editor
   (Jeremy's call; nothing here does it): `select cron.unschedule(jobid) from cron.job;`

## 5. Verify

```bash
./healthcheck.sh
```

It checks: `/rest/v1/` with the service key returns 200; `players` returns
rows; `/rest/v1/` with no key returns 401; with the relay running,
`usatoday-fetch` refuses the anon key. A one-line manual check that returns rows:

```bash
KEY=$(awk -F= '$1=="SERVICE_ROLE_KEY"{print substr($0, index($0,"=")+1)}' .env)
curl -s "http://127.0.0.1:8000/rest/v1/players?select=player_key&limit=3" \
  -H "apikey: $KEY" -H "Authorization: Bearer $KEY"; echo
```

RLS: `service_role` has BYPASSRLS, exactly like the cloud (checked
2026-10-21: `service_role` bypass true, `anon`/`authenticated` false; the
168 policies reference `anon`, `authenticated`, `public`, `service_role`
and none call `auth.*()` functions). To confirm on the Mac after import:

```bash
docker compose --env-file .env exec -T db psql -h localhost -U supabase_admin -d postgres -c \
  "select rolname, rolbypassrls from pg_roles where rolname in ('anon','authenticated','service_role') order by 1;
   select count(*) as policies from pg_policies where schemaname not in ('storage','cron');"
```

The cloud count of 168 includes policies on `storage` and `cron`, which come
from the image, so compare the non-platform count with the same query run in
the cloud SQL editor.

## 6. Let GitHub Actions reach the Mac

The gateway listens on 127.0.0.1 only. GitHub-hosted runners cannot reach it.
Pick one way in. Either way, do this only after step 5 passes.

### Option A: self-hosted runner on the Mac

The runner runs on the Mac and calls `http://127.0.0.1:8000`; nothing is
exposed to the internet.

- Set up: repo Settings > Actions > Runners > New self-hosted runner (macOS,
  ARM64), follow the commands, then `./svc.sh install && ./svc.sh start`.
- Restrict it: put it in a runner group limited to this repository and to
  the workflows that need the database, and run those jobs only on `main`
  (`if: github.ref == 'refs/heads/main'`). Workflows also need
  `runs-on: [self-hosted, macOS]` instead of `ubuntu-latest` on the jobs that
  touch the database. That is a workflow change; it is not in this PR.
- **Security trade-off.** This repository is **public**. GitHub warns against
  self-hosted runners on public repos: a pull request from a fork can run
  code on the Mac if a workflow lets it. Repo Settings > Actions >
  "Require approval for all outside collaborators" must be on, and no
  `pull_request` workflow may target the self-hosted label. The jobs also run
  as your macOS user, with access to your files. The workflows were written
  for Ubuntu (apt, Linux paths) and some may not run on macOS as is.
- `SUPABASE_URL` secret: `http://127.0.0.1:8000`.
- USA Today: the Mac's home IP is not a GitHub runner IP, so the relay may not
  be needed on this path. Keep it running anyway; `pull_usatoday.py` tries it
  only after a direct fetch is walled.

### Option B: Cloudflare Tunnel or Tailscale Funnel

The workflows stay on GitHub-hosted runners and call a public HTTPS URL that
forwards to the gateway. No inbound port is opened on the router.

- Cloudflare Tunnel (needs a domain on Cloudflare): Zero Trust > Networks >
  Tunnels > Create, type Cloudflared, copy the token into
  `CLOUDFLARE_TUNNEL_TOKEN` in `.env`, add a public hostname (for example
  `db.<your-domain>`) with service `http://gateway:8000`, then:

```bash
docker compose --env-file .env --profile relay --profile tunnel up -d
SUPABASE_URL=https://db.<your-domain> ./healthcheck.sh
```

- Tailscale Funnel (no domain needed; runs on the Mac, not in compose):
  install Tailscale, enable Funnel for the tailnet in the admin console, then
  `tailscale funnel --bg 8000`. The URL is `https://<mac-name>.<tailnet>.ts.net`.
- `SUPABASE_URL` secret: the public `https://` URL, no trailing slash.
- **Security trade-off.** PostgREST is then reachable from the internet. The
  gateway refuses any call without the anon or service key, and the anon key
  is held to the RLS policies, but anyone holding the service key has full
  read and write, and a PostgREST or nginx bug would be exposed. The keys
  are only in `.env` and GitHub secrets; rotate them (step 2 into a new file,
  restart, update secrets) if one leaks. Extra hardening, not set up here:
  Cloudflare Access with a service token, which would need the two headers
  added in `gh_sbclient.py`.

Recommendation: Option B with Cloudflare Tunnel. It keeps the public repo's
code off the Mac and needs no workflow changes; the exposure is one URL
guarded by a key that only GitHub secrets hold.

## 7. Set the two GitHub secrets

Every workflow reads only `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (65 uses
each). Changing them moves all pipelines from the cloud to the Mac at once.
From `selfhost/supabase/`, with `gh` logged in:

```bash
gh secret set SUPABASE_URL --repo JB-barrel-droid/fantasy-tools        # paste the URL when asked
awk -F= '$1=="SERVICE_ROLE_KEY"{printf "%s", substr($0, index($0,"=")+1)}' .env \
  | gh secret set SUPABASE_SERVICE_KEY --repo JB-barrel-droid/fantasy-tools
```

Or in the browser: repo Settings > Secrets and variables > Actions > edit
each secret. Then run one cheap workflow by hand (Actions > a loader's
"Run workflow") and check its log for HTTP 200s. To go back to the cloud,
set the two secrets to the old values.

## 8. Nightly backups

```bash
STACK_DIR="$(pwd)"
sed -e "s#__STACK_DIR__#$STACK_DIR#g" -e "s#__HOME__#$HOME#g" \
  launchd/com.ddf.supabase-backup.plist > ~/Library/LaunchAgents/com.ddf.supabase-backup.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ddf.supabase-backup.plist
launchctl kickstart gui/$(id -u)/com.ddf.supabase-backup     # run once now
tail -20 ~/Library/Logs/ddf-supabase-backup.log
```

`backup.sh` writes `ddf-<UTC stamp>.dump` and `ddf-<UTC stamp>.cron.sql` to
`~/ddf-supabase-backups` (or `BACKUP_DIR`), keeps a dump only if
`pg_restore --list` reads it back, and deletes files older than 14 days
(`BACKUP_KEEP_DAYS`). It runs at 03:17; if the Mac is asleep then, it runs
at wake. Backups on the same disk do not survive a dead Mac: copy the folder
somewhere else now and then (iCloud Drive, an external disk).

To stop it: `launchctl bootout gui/$(id -u)/com.ddf.supabase-backup`.

## Restore from a backup

Into a fresh database (safest):

```bash
cd ~/ddf-selfhost/fantasy-tools/selfhost/supabase
docker compose --env-file .env down
docker volume rm ddf-supabase_db-data          # deletes the current database
docker compose --env-file .env up -d
./restore.sh ~/ddf-supabase-backups/ddf-<stamp>.dump
```

Then re-enter `github_dispatch_token` (step 4.5) and run `./healthcheck.sh`.
Keep the `ddf-supabase_db-config` volume: it holds the Vault key.
`./restore.sh --clean <file>` restores over an existing database instead,
dropping and recreating the objects in the dump.

## What breaks when the Mac is off

- Every pipeline step that reads or writes the data store fails with
  `SupabaseError` (connection refused or timeout). The loaders fail closed,
  so nothing wrong is written; the data just stops refreshing.
- The 20 pg_cron schedules live in the Mac's database, so no scheduled
  workflow is dispatched while it is off. Missed runs are not replayed when
  it comes back.
- The USA Today relay is down, so the trade-chart ingest falls back to its
  other paths or holds the source.
- `get-values` on the Mac is down. The cloud copy of `get-values` and the
  published site do not depend on the Mac: the site is static on GitHub Pages
  and keeps showing the last published numbers, with its staleness labels.
- Sleep counts as off. A power cut needs "start up after power failure" and
  Docker set to start at login.

## Day-to-day commands

```bash
cd ~/ddf-selfhost/fantasy-tools/selfhost/supabase
docker compose --env-file .env ps                         # status
docker compose --env-file .env logs -f rest gateway       # logs
git pull && docker compose --env-file .env --profile relay up -d   # update
docker compose --env-file .env exec db psql -h localhost -U supabase_admin -d postgres   # SQL shell
```

## What was and was not tested

Checked on Linux, 2026-10-21, without a Docker daemon:

- `docker compose config --quiet` passes for the default, `relay` and
  `tunnel` profiles; default services are `db`, `rest`, `gateway`; the
  gateway publishes only `127.0.0.1:8000`.
- `bash -n` passes for `backup.sh`, `restore.sh`, `healthcheck.sh`; the
  launchd plist parses with Python `plistlib`.
- `gen-keys.py --write` then `--verify`: both JWTs verify against
  `JWT_SECRET` and carry `role` `anon` and `service_role`; an independent
  HMAC check with Node's `crypto` agrees; `--write` refuses to overwrite.
- The function router (`functions-main/index.ts`), run under Node with fake
  `Deno`/`EdgeRuntime` globals: `usatoday-fetch` gives 200 for the service
  key and 403 for the anon key, 401 for no token, a token signed with
  another secret, an expired token and `alg: none`; `get-values` needs no
  token; unknown names give 404; workers get only their listed env vars
  (never `JWT_SECRET`).
- Read only, against the cloud: Postgres 17.6; extensions pg_cron 1.6.4,
  pg_net 0.20.4, supabase_vault 0.3.1, pgcrypto, uuid-ossp,
  pg_stat_statements; role BYPASSRLS flags; 168 policies, none using
  `auth.*()`; 20 cron jobs calling `dispatch_gha_workflow` /
  `dispatch_vintage_check`; the deployed `usatoday-fetch` (v3,
  `verify_jwt: true`) is byte-identical to
  `supabase/functions/usatoday-fetch/index.ts`.
- From the `supabase/postgres` source at tag `17.6.1.136`: it creates
  `anon`, `authenticated`, `service_role` (BYPASSRLS) and `authenticator`;
  preloads pg_cron, pg_net and supabase_vault; sets
  `cron.database_name = 'postgres'`; its newest pg_net for PG17 is 0.20.3,
  one patch behind the cloud's 0.20.4.

Not tested (no Mac, no Docker daemon, no access to the cloud database dump):

- That any container starts, that the init SQL runs cleanly on first boot,
  or that nginx accepts `gateway/default.conf.template`.
- The edge runtime's worker API with this router (the router follows the
  upstream `main` function's `EdgeRuntime.userWorkers.create` call).
- The cloud dump and restore (egress quota), and whether pg_net 0.20.3 runs
  the dispatch function unchanged.
- launchd, the tunnel and Funnel, the self-hosted runner, and the workflows
  against the Mac.
