#!/usr/bin/env bash
# Verify Alembic migration chain end-to-end against DATABASE_URI.
#
# Runs: downgrade base → upgrade head → assert seed counts (dev1) →
# provision secondary tenant (test2) → assert parity → invalid-name
# rejection → downgrade base → assert empty.
#
# Usage (from fluxion-backend/):
#   DATABASE_URI=postgresql://postgres:test@localhost:55432/fluxion \
#     ./scripts/verify-migrations.sh
#
# SAFETY: downgrade wipes tenant schemas. NEVER run against production.

set -euo pipefail

: "${DATABASE_URI:?DATABASE_URI env var required}"

# psql form of DATABASE_URI (strip SQLAlchemy driver suffix if present).
PSQL_URI="${DATABASE_URI//postgresql+psycopg2/postgresql}"
PSQL="psql $PSQL_URI -v ON_ERROR_STOP=1 -A -t"
ALEMBIC="alembic -c migrations/alembic.ini"

assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$expected" != "$actual" ]]; then
        echo "FAIL [$label]: expected=$expected actual=$actual" >&2
        exit 1
    fi
    echo "OK   [$label]: $actual"
}

echo "== Pre-check: CREATE privilege + server version =="
assert_eq "create_privilege" "t" \
    "$($PSQL -c "SELECT has_database_privilege(current_user, current_database(), 'CREATE')")"
echo "INFO server version: $($PSQL -c 'SHOW server_version')"

echo "== Clean slate (downgrade base) =="
$ALEMBIC downgrade base || true

echo "== Upgrade head =="
$ALEMBIC upgrade head

echo "== dev1 seed counts =="
assert_eq "services"          "3"  "$($PSQL -c 'SELECT count(*) FROM dev1.services')"
assert_eq "states"            "6"  "$($PSQL -c 'SELECT count(*) FROM dev1.states')"
assert_eq "policies"          "6"  "$($PSQL -c 'SELECT count(*) FROM dev1.policies')"
assert_eq "actions"           "15" "$($PSQL -c 'SELECT count(*) FROM dev1.actions')"
assert_eq "brands"            "1"  "$($PSQL -c 'SELECT count(*) FROM dev1.brands')"
assert_eq "tacs"              "1"  "$($PSQL -c 'SELECT count(*) FROM dev1.tacs')"
assert_eq "message_templates" "3"  "$($PSQL -c 'SELECT count(*) FROM dev1.message_templates')"
assert_eq "tenants_row"       "1"  \
    "$($PSQL -c "SELECT count(*) FROM accesscontrol.tenants WHERE schema_name='dev1'")"
assert_eq "dev1_table_count"  "16" \
    "$($PSQL -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='dev1'")"

echo "== Secondary tenant (test2) provisioning parity =="
$PSQL -c "CALL public.create_tenant_schema('test2')" >/dev/null
$PSQL -c "CALL public.create_default_tenant_data('test2')" >/dev/null
assert_eq "test2.services" "3"  "$($PSQL -c 'SELECT count(*) FROM test2.services')"
assert_eq "test2.actions"  "15" "$($PSQL -c 'SELECT count(*) FROM test2.actions')"

echo "== Table parity: dev1 vs test2 =="
DIFF=$($PSQL -c "
  SELECT table_name FROM information_schema.tables WHERE table_schema='dev1'
  EXCEPT
  SELECT table_name FROM information_schema.tables WHERE table_schema='test2'
")
assert_eq "table_parity_diff" "" "$DIFF"

echo "== Invalid schema_name rejection =="
set +e
$PSQL -c "CALL public.create_tenant_schema('Invalid Name')" 2>/dev/null
REJECTED=$?
set -e
assert_eq "invalid_name_rejected" "nonzero" \
    "$( [[ $REJECTED -ne 0 ]] && echo nonzero || echo zero )"

echo "== Reserved schema_name rejection =="
set +e
$PSQL -c "CALL public.create_tenant_schema('public')" 2>/dev/null
REJECTED=$?
set -e
assert_eq "reserved_name_rejected" "nonzero" \
    "$( [[ $REJECTED -ne 0 ]] && echo nonzero || echo zero )"

echo "== Cleanup test2 (drop schema; accesscontrol row not inserted) =="
$PSQL -c "DROP SCHEMA test2 CASCADE" >/dev/null

echo "== Downgrade to base =="
$ALEMBIC downgrade base

echo "== Assert empty =="
assert_eq "residual_schemas" "0" "$($PSQL -c "
    SELECT count(*) FROM information_schema.schemata
    WHERE schema_name IN ('accesscontrol','dev1','test2')
")"
assert_eq "residual_procs" "0" "$($PSQL -c "
    SELECT count(*) FROM pg_proc
    WHERE proname IN ('create_tenant_schema','create_default_tenant_data')
")"

echo "== ALL GREEN =="
