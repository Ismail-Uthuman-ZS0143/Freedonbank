-- Creates the "fbv" Postgres database used by Credit File Server 2.0.
-- Matches backend/config/settings.py's defaults: database "fbv", owner
-- "ismail", local Postgres over the Unix socket (peer auth).
--
-- CREATE DATABASE can't run inside a transaction block and has no
-- IF NOT EXISTS clause in Postgres, so run this as the postgres superuser
-- and expect an error (harmless) if "fbv" already exists:
--
--   sudo -u postgres psql -f fbv_database.sql

ALTER ROLE ismail CREATEDB;

CREATE DATABASE fbv OWNER ismail;

-- Next: apply Django migrations --
--   cd backend && python3 manage.py migrate
