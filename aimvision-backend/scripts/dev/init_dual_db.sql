-- One Postgres cluster, two databases.
--
-- docker-compose.dev.yml seeds the AIMVISION database via POSTGRES_DB +
-- POSTGRES_USER; this script adds the second database (`gotrue`) plus
-- a dedicated role for the gotrue service, the `auth` schema GoTrue's
-- own migrations target, and the extensions it depends on. Runs once
-- on first container start (the volume that hosts /var/lib/postgresql/
-- data persists across `docker compose up`/`down`; use
-- `docker compose down -v` to force a re-init).

CREATE USER gotrue WITH PASSWORD 'gotrue-dev-only';
CREATE DATABASE gotrue OWNER gotrue;
GRANT ALL PRIVILEGES ON DATABASE gotrue TO gotrue;

-- Supabase-platform roles that supabase/auth's RLS-grant migrations
-- assume already exist. We're not running PostgREST so these roles
-- have no real privileges; the migrations just need them resolvable
-- by `GRANT ... TO <role>` lookups.
CREATE ROLE postgres;
CREATE ROLE anon NOINHERIT;
CREATE ROLE authenticated NOINHERIT;
CREATE ROLE service_role NOINHERIT BYPASSRLS;

-- Inside the new gotrue database: create the schema GoTrue's
-- 00_init_auth_schema migration expects to already exist, plus the
-- two extensions it uses (uuid-ossp for `uuid_generate_v4()`,
-- pgcrypto for the `crypt`/`gen_salt` calls the auth flow uses).
\c gotrue
CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION gotrue;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
