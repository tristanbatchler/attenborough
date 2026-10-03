-- Creates Attenborough's production database and its two roles. Run once, as a PostgreSQL
-- superuser, from the repository's root on the server (deploy/README.md):
--
--     psql -U postgres -h /var/run/postgresql -f deploy/database.sql
--
-- It asks for both passwords (put the same ones in .env). The names default to those in
-- .env.example; to use others, pass them: -v database=... -v owner=... -v app=...
--
--   owner  owns the database and its schema: applies migrations (`docker compose run --rm migrate`).
--   app    the API's role: may read, insert and update rows in the owner's tables, and nothing else.
--          It can't create, alter or drop anything, or delete rows, so the honeypot's data survives
--          even a compromised API. The one exception: it may delete login states and sessions,
--          granted by migration 0008_admin.sql to PUBLIC, which only it can use (USAGE, below).
--
-- It creates objects but never drops any: run against an existing database or role, it stops at
-- the first error and changes nothing more.

\set ON_ERROR_STOP on

\if :{?database}
\else
    \set database attenborough
\endif
\if :{?owner}
\else
    \set owner attenborough_owner
\endif
\if :{?app}
\else
    \set app attenborough_app
\endif

\prompt 'Password for the owner role: ' owner_password
\prompt 'Password for the app role: ' app_password

CREATE ROLE :"owner" LOGIN PASSWORD :'owner_password';
CREATE ROLE :"app" LOGIN PASSWORD :'app_password';
CREATE DATABASE :"database" OWNER :"owner";

-- Only the two roles may connect, and no one else may create temporary tables.
REVOKE ALL ON DATABASE :"database" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database" TO :"app";

\connect :"database"

-- The schema `public` belongs to the database's owner. Nobody else may create in it; the app may
-- use what the owner creates there.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app";

-- Every table and sequence the owner creates from now on (that is, every migration) is readable
-- and writable by the app: SELECT, INSERT and UPDATE (UpsertDecoy updates; the triggers' running
-- totals update). Sequences need USAGE for BIGSERIAL columns. No DELETE or TRUNCATE.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT USAGE ON SEQUENCES TO :"app";
