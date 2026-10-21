-- First-boot init for the self-hosted stack (JEG-792).
-- Mounted at /docker-entrypoint-initdb.d/init-scripts/99-ddf-roles.sql and run
-- by psql as supabase_admin, once, when the data volume is empty.
--
-- supabase/postgres 17.6.1.136 already creates these roles in
-- migrations/db/init-scripts/00000000000000-initial-schema.sql:
--   anon, authenticated   nologin noinherit
--   service_role          nologin noinherit BYPASSRLS
--   authenticator         login noinherit, member of the three above
-- This file makes that true even if a future image changes it, so the 168
-- cloud RLS policies behave the same after import: service_role bypasses
-- RLS (as in the cloud: pg_roles.rolbypassrls = true, checked 2026-10-21),
-- anon and authenticated are subject to it.

\set pgpass `echo "$POSTGRES_PASSWORD"`

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
    CREATE ROLE authenticator LOGIN NOINHERIT;
  END IF;
END
$$;

-- RLS: exactly as the cloud project.
ALTER ROLE service_role BYPASSRLS;
ALTER ROLE anon NOBYPASSRLS;
ALTER ROLE authenticated NOBYPASSRLS;
ALTER ROLE authenticator NOINHERIT LOGIN;

GRANT anon, authenticated, service_role TO authenticator;

-- PostgREST logs in as authenticator with the stack's POSTGRES_PASSWORD.
ALTER ROLE authenticator WITH PASSWORD :'pgpass';

-- Schema usage the cloud grants by default. Table grants come with the import.
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- The `api` schema is exposed through PostgREST (Accept-Profile: api).
CREATE SCHEMA IF NOT EXISTS api;
GRANT USAGE ON SCHEMA api TO anon, authenticated, service_role;

-- Extensions the cloud project uses (pg_extension, 2026-10-21):
-- pg_cron 1.6.4, pg_net 0.20.4, pg_stat_statements, pgcrypto,
-- supabase_vault 0.3.1, uuid-ossp. The image preloads pg_cron, pg_net and
-- supabase_vault (shared_preload_libraries) and sets cron.database_name to
-- 'postgres'. Its newest pg_net for PG17 is 0.20.3, one patch behind cloud.
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_cron;
-- supabase_vault is created by the image's own migrations.

-- Fail the first boot loudly if the RLS contract does not hold.
DO $$
BEGIN
  IF NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role') THEN
    RAISE EXCEPTION 'service_role must have BYPASSRLS';
  END IF;
  IF (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'anon')
     OR (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'authenticated') THEN
    RAISE EXCEPTION 'anon/authenticated must not bypass RLS';
  END IF;
END
$$;
