-- One Postgres cluster, two databases.
--
-- docker-compose.dev.yml seeds the AIMVISION database via POSTGRES_DB +
-- POSTGRES_USER; this script adds the second database (`gotrue`) plus
-- a dedicated role for the gotrue service. Runs once on first
-- container start (the volume that hosts /var/lib/postgresql/data
-- persists across `docker compose up`/`down`; use
-- `docker compose down -v` to force a re-init).

CREATE USER gotrue WITH PASSWORD 'gotrue-dev-only';
CREATE DATABASE gotrue OWNER gotrue;
GRANT ALL PRIVILEGES ON DATABASE gotrue TO gotrue;
