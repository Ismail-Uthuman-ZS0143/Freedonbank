#!/usr/bin/env bash
# Creates the "fbv" Postgres database used by Credit File Server 2.0.
#
# Matches backend/config/settings.py's defaults: database "fbv", owner
# "ismail", local Postgres over the Unix socket (no host/port needed for
# peer auth). Idempotent -- safe to re-run.
#
# Usage: ./setup_fbv_database.sh

set -euo pipefail

DB_NAME="${PGDATABASE:-fbv}"
DB_OWNER="${PGUSER:-ismail}"

echo "Ensuring role \"$DB_OWNER\" can create databases..."
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER ROLE \"$DB_OWNER\" CREATEDB;"

if psql -lqt | cut -d '|' -f 1 | grep -qw "$DB_NAME"; then
  echo "Database \"$DB_NAME\" already exists -- nothing to do."
else
  echo "Creating database \"$DB_NAME\" (owner: $DB_OWNER)..."
  createdb -O "$DB_OWNER" "$DB_NAME"
  echo "Created."
fi

echo
echo "Next: apply Django migrations --"
echo "  cd backend && python3 manage.py migrate"
