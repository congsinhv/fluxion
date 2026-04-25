#!/usr/bin/env bash
# smoke-appsync.sh — E2E smoke test: Cognito JWT → AppSync GraphQL.
#
# Usage:
#   ./scripts/smoke-appsync.sh
#
# Requires:
#   - aws CLI v2, jq, curl, terraform
#   - Terraform applied in fluxion-backend/terraform/envs/dev
#   - DEV_ADMIN_PASSWORD available in SSM /fluxion/dev/admin_password
#   - provision-dev-admin.sh already run (cognito_sub populated in DB)
#
# Exit codes:
#   0 — all assertions passed
#   1 — one or more assertions failed
#
# Security:
#   - Tokens are never echoed; set +x guards all credential operations.
#   - Response bodies are inspected via jq; only field names / lengths are logged.

set -euo pipefail

TF_DIR="$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)"
SSM_PASSWORD_PATH="/fluxion/dev/admin_password"
DEV_ADMIN_EMAIL="dev-admin@fluxion.local"
SMOKE_USER_EMAIL="smoke-nonadmin@fluxion.local"

PASS=0
FAIL=0
declare -a FAILURES=()

# ── Helpers ────────────────────────────────────────────────────────────────────

log()    { echo "[smoke] $*"; }
log_ok() { echo "[smoke] PASS  $*"; }
log_fail() {
  echo "[smoke] FAIL  $*" >&2
  FAILURES+=("$*")
}

ms_now() { date +%s%3N; }

# assert_no_errors LABEL RESPONSE_FILE
# Checks that the jq path .errors is absent or null.
assert_no_errors() {
  local label="$1" resp_file="$2"
  local t_start t_end elapsed
  t_end=$(cat "${resp_file}.timing" 2>/dev/null || echo 0)
  t_start=$(cat "${resp_file}.timing_start" 2>/dev/null || echo 0)
  elapsed=$(( t_end - t_start ))

  if jq -e '.errors' "$resp_file" >/dev/null 2>&1; then
    local err_msg
    err_msg=$(jq -r '.errors[0].message // "unknown"' "$resp_file")
    log_fail "$label — errors present: $err_msg  (${elapsed}ms)"
    FAIL=$(( FAIL + 1 ))
  else
    log_ok "$label  (${elapsed}ms)"
    PASS=$(( PASS + 1 ))
  fi
}

# assert_forbidden LABEL RESPONSE_FILE
# Checks that .errors[0].errorType == "Unauthorized" or message contains FORBIDDEN.
assert_forbidden() {
  local label="$1" resp_file="$2"
  if jq -e '.errors' "$resp_file" >/dev/null 2>&1; then
    local err_type
    err_type=$(jq -r '(.errors[0].errorType // "") + " " + (.errors[0].message // "")' "$resp_file")
    if echo "$err_type" | grep -qiE "unauthorized|forbidden|permission"; then
      log_ok "$label (correctly FORBIDDEN)"
      PASS=$(( PASS + 1 ))
    else
      log_fail "$label — expected FORBIDDEN, got: $err_type"
      FAIL=$(( FAIL + 1 ))
    fi
  else
    log_fail "$label — expected FORBIDDEN but got success"
    FAIL=$(( FAIL + 1 ))
  fi
}

# gql TOKEN LABEL QUERY_JSON OUTPUT_FILE
# Executes a GraphQL request and saves response + timing.
gql() {
  local token="$1" label="$2" query_json="$3" output_file="$4"
  local t_start t_end

  t_start=$(ms_now)
  echo "$t_start" > "${output_file}.timing_start"

  # Suppress xtrace during curl to avoid leaking the Authorization token.
  # Use -s (silent) without -f so HTTP 4xx responses are still captured as
  # GraphQL error envelopes (AppSync always returns 200 for GraphQL errors,
  # but this keeps the script robust if that ever changes).
  set +x
  curl -s \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: $token" \
    --data "$query_json" \
    "$APPSYNC_URL" \
    -o "$output_file" \
    --max-time 30
  local curl_exit=$?
  set +x  # keep suppressed — restore is handled at function return

  t_end=$(ms_now)
  echo "$t_end" > "${output_file}.timing"

  if [[ $curl_exit -ne 0 ]]; then
    log_fail "$label — curl failed (exit $curl_exit)"
    echo '{"errors":[{"message":"curl failed"}]}' > "$output_file"
    FAIL=$(( FAIL + 1 ))
    return 1
  fi
  return 0
}

# ── Step 1: Terraform outputs ──────────────────────────────────────────────────

log "Reading Terraform outputs ..."
APPSYNC_URL=$(terraform -chdir="$TF_DIR" output -raw appsync_graphql_endpoint)
USER_POOL_ID=$(terraform -chdir="$TF_DIR" output -raw cognito_user_pool_id)
CLIENT_ID=$(terraform -chdir="$TF_DIR" output -raw cognito_client_id)

[[ -z "$APPSYNC_URL"   ]] && { echo "ERROR: appsync_graphql_endpoint empty" >&2; exit 1; }
[[ -z "$USER_POOL_ID"  ]] && { echo "ERROR: cognito_user_pool_id empty" >&2; exit 1; }
[[ -z "$CLIENT_ID"     ]] && { echo "ERROR: cognito_client_id empty" >&2; exit 1; }
log "AppSync URL: $APPSYNC_URL"

# ── Step 2: Read passwords from SSM ───────────────────────────────────────────

set +x
DEV_ADMIN_PASSWORD=$(
  aws ssm get-parameter \
    --name "$SSM_PASSWORD_PATH" \
    --with-decryption \
    --query "Parameter.Value" \
    --output text
)
[[ -z "$DEV_ADMIN_PASSWORD" ]] && { echo "ERROR: could not read SSM $SSM_PASSWORD_PATH" >&2; exit 1; }

# ── Step 3: Obtain admin IdToken ──────────────────────────────────────────────

log "Authenticating admin user ..."
set +x
ADMIN_AUTH_RESP=$(
  aws cognito-idp admin-initiate-auth \
    --user-pool-id "$USER_POOL_ID" \
    --client-id "$CLIENT_ID" \
    --auth-flow ADMIN_USER_PASSWORD_AUTH \
    --auth-parameters "USERNAME=$DEV_ADMIN_EMAIL,PASSWORD=$DEV_ADMIN_PASSWORD" \
    --output json
)
ADMIN_TOKEN=$(echo "$ADMIN_AUTH_RESP" | jq -r '.AuthenticationResult.IdToken')

[[ -z "$ADMIN_TOKEN" || "$ADMIN_TOKEN" == "null" ]] && {
  echo "ERROR: failed to obtain admin IdToken" >&2; exit 1;
}
log "Admin token obtained (length=$(echo -n "$ADMIN_TOKEN" | wc -c | tr -d ' '))"

# ── Step 4: Provision/verify smoke-nonadmin user ───────────────────────────────
# Provision a non-admin Cognito user if not present; we only need a token,
# not a DB row (negative test just checks AppSync/Lambda FORBIDDEN response).

log "Checking smoke non-admin user ..."
set +x
SSM_NONADMIN_PATH="/fluxion/dev/smoke_nonadmin_password"
NONADMIN_EXISTS=$(
  aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$SMOKE_USER_EMAIL" \
    --query "Username" --output text 2>/dev/null || echo "NOT_FOUND"
)

if [[ "$NONADMIN_EXISTS" == "NOT_FOUND" ]]; then
  log "Creating smoke non-admin Cognito user ..."
  NONADMIN_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' </dev/urandom | head -c 20)
  aws ssm put-parameter \
    --name "$SSM_NONADMIN_PATH" \
    --type "SecureString" \
    --value "$NONADMIN_PASSWORD" \
    --description "Smoke non-admin password (auto-generated)" \
    --overwrite >/dev/null
  aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$SMOKE_USER_EMAIL" \
    --message-action SUPPRESS \
    --user-attributes \
      Name=email,Value="$SMOKE_USER_EMAIL" \
      Name=email_verified,Value=true \
    >/dev/null
  aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username "$SMOKE_USER_EMAIL" \
    --password "$NONADMIN_PASSWORD" \
    --permanent >/dev/null
  log "Smoke non-admin user created."
else
  NONADMIN_PASSWORD=$(
    aws ssm get-parameter \
      --name "$SSM_NONADMIN_PATH" \
      --with-decryption \
      --query "Parameter.Value" \
      --output text
  )
fi

NONADMIN_AUTH_RESP=$(
  aws cognito-idp admin-initiate-auth \
    --user-pool-id "$USER_POOL_ID" \
    --client-id "$CLIENT_ID" \
    --auth-flow ADMIN_USER_PASSWORD_AUTH \
    --auth-parameters "USERNAME=$SMOKE_USER_EMAIL,PASSWORD=$NONADMIN_PASSWORD" \
    --output json
)
NONADMIN_TOKEN=$(echo "$NONADMIN_AUTH_RESP" | jq -r '.AuthenticationResult.IdToken')

[[ -z "$NONADMIN_TOKEN" || "$NONADMIN_TOKEN" == "null" ]] && {
  echo "ERROR: failed to obtain non-admin IdToken" >&2; exit 1;
}
log "Non-admin token obtained (length=$(echo -n "$NONADMIN_TOKEN" | wc -c | tr -d ' '))"

# ── Step 5: Smoke workdir ──────────────────────────────────────────────────────

TMPDIR_SMOKE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_SMOKE"' EXIT
log "Response staging dir: $TMPDIR_SMOKE"

# ── Step 6: Device queries (3) ────────────────────────────────────────────────

log "--- Device queries ---"

# 6a. listDevices — find a device ID to use in subsequent calls
gql "$ADMIN_TOKEN" "listDevices" \
  '{"query":"query { listDevices(limit:1) { items { id createdAt updatedAt } } }"}' \
  "$TMPDIR_SMOKE/list-devices.json"
assert_no_errors "listDevices" "$TMPDIR_SMOKE/list-devices.json"

DEVICE_ID=$(jq -r '.data.listDevices.items[0].id // empty' "$TMPDIR_SMOKE/list-devices.json")
if [[ -z "$DEVICE_ID" ]]; then
  log "WARN: No devices in dev1 — getDevice and getDeviceHistory will be skipped (no data)"
  DEVICE_ID="__NONE__"
fi

# 6b. getDevice
if [[ "$DEVICE_ID" != "__NONE__" ]]; then
  gql "$ADMIN_TOKEN" "getDevice($DEVICE_ID)" \
    "{\"query\":\"query { getDevice(id: \\\"$DEVICE_ID\\\") { id currentPolicy { id name } createdAt updatedAt } }\"}" \
    "$TMPDIR_SMOKE/get-device.json"
  assert_no_errors "getDevice" "$TMPDIR_SMOKE/get-device.json"
else
  log "SKIP  getDevice (no device rows in tenant)"
fi

# 6c. getDeviceHistory
if [[ "$DEVICE_ID" != "__NONE__" ]]; then
  gql "$ADMIN_TOKEN" "getDeviceHistory($DEVICE_ID)" \
    "{\"query\":\"query { getDeviceHistory(deviceId: \\\"$DEVICE_ID\\\", limit: 5) { items { id } } }\"}" \
    "$TMPDIR_SMOKE/get-device-history.json"
  assert_no_errors "getDeviceHistory" "$TMPDIR_SMOKE/get-device-history.json"
else
  log "SKIP  getDeviceHistory (no device rows in tenant)"
fi

# ── Step 7: Platform queries (4) ──────────────────────────────────────────────

log "--- Platform queries ---"

gql "$ADMIN_TOKEN" "listServices" \
  '{"query":"query { listServices { id name isEnabled } }"}' \
  "$TMPDIR_SMOKE/list-services.json"
assert_no_errors "listServices" "$TMPDIR_SMOKE/list-services.json"

gql "$ADMIN_TOKEN" "listStates" \
  '{"query":"query { listStates { id name } }"}' \
  "$TMPDIR_SMOKE/list-states.json"
assert_no_errors "listStates" "$TMPDIR_SMOKE/list-states.json"

gql "$ADMIN_TOKEN" "listPolicies" \
  '{"query":"query { listPolicies { id name stateId serviceTypeId } }"}' \
  "$TMPDIR_SMOKE/list-policies.json"
assert_no_errors "listPolicies" "$TMPDIR_SMOKE/list-policies.json"

gql "$ADMIN_TOKEN" "listActions" \
  '{"query":"query { listActions { id name actionTypeId applyPolicyId } }"}' \
  "$TMPDIR_SMOKE/list-actions.json"
assert_no_errors "listActions" "$TMPDIR_SMOKE/list-actions.json"

# ── Step 8: Platform mutations (4) — read IDs first, then update in-place ─────

log "--- Platform mutations (non-destructive round-trip) ---"

STATE_ID=$(jq -r '.data.listStates[0].id // empty' "$TMPDIR_SMOKE/list-states.json")
STATE_NAME=$(jq -r '.data.listStates[0].name // "unchanged"' "$TMPDIR_SMOKE/list-states.json")
if [[ -n "$STATE_ID" ]]; then
  gql "$ADMIN_TOKEN" "updateState($STATE_ID)" \
    "{\"query\":\"mutation { updateState(id: $STATE_ID, input: { name: \\\"$STATE_NAME\\\" }) { id name } }\"}" \
    "$TMPDIR_SMOKE/update-state.json"
  assert_no_errors "updateState" "$TMPDIR_SMOKE/update-state.json"
else
  log "SKIP  updateState (no state rows)"
fi

POLICY_ID=$(jq -r '.data.listPolicies[0].id // empty' "$TMPDIR_SMOKE/list-policies.json")
POLICY_NAME=$(jq -r '.data.listPolicies[0].name // "unchanged"' "$TMPDIR_SMOKE/list-policies.json")
if [[ -n "$POLICY_ID" ]]; then
  gql "$ADMIN_TOKEN" "updatePolicy($POLICY_ID)" \
    "{\"query\":\"mutation { updatePolicy(id: $POLICY_ID, input: { name: \\\"$POLICY_NAME\\\" }) { id name } }\"}" \
    "$TMPDIR_SMOKE/update-policy.json"
  assert_no_errors "updatePolicy" "$TMPDIR_SMOKE/update-policy.json"
else
  log "SKIP  updatePolicy (no policy rows)"
fi

ACTION_ID=$(jq -r '.data.listActions[0].id // empty' "$TMPDIR_SMOKE/list-actions.json")
ACTION_NAME=$(jq -r '.data.listActions[0].name // "unchanged"' "$TMPDIR_SMOKE/list-actions.json")
if [[ -n "$ACTION_ID" ]]; then
  gql "$ADMIN_TOKEN" "updateAction($ACTION_ID)" \
    "{\"query\":\"mutation { updateAction(id: \\\"$ACTION_ID\\\", input: { name: \\\"$ACTION_NAME\\\" }) { id name } }\"}" \
    "$TMPDIR_SMOKE/update-action.json"
  assert_no_errors "updateAction" "$TMPDIR_SMOKE/update-action.json"
else
  log "SKIP  updateAction (no action rows)"
fi

SERVICE_ID=$(jq -r '.data.listServices[0].id // empty' "$TMPDIR_SMOKE/list-services.json")
SERVICE_ENABLED=$(jq -r '.data.listServices[0].isEnabled // true' "$TMPDIR_SMOKE/list-services.json")
if [[ -n "$SERVICE_ID" ]]; then
  gql "$ADMIN_TOKEN" "updateService($SERVICE_ID)" \
    "{\"query\":\"mutation { updateService(id: $SERVICE_ID, input: { isEnabled: $SERVICE_ENABLED }) { id name isEnabled } }\"}" \
    "$TMPDIR_SMOKE/update-service.json"
  assert_no_errors "updateService" "$TMPDIR_SMOKE/update-service.json"
else
  log "SKIP  updateService (no service rows)"
fi

# ── Step 9: User queries (3) ──────────────────────────────────────────────────

log "--- User queries ---"

gql "$ADMIN_TOKEN" "getCurrentUser" \
  '{"query":"query { getCurrentUser { id email name role isActive } }"}' \
  "$TMPDIR_SMOKE/get-current-user.json"
assert_no_errors "getCurrentUser" "$TMPDIR_SMOKE/get-current-user.json"

gql "$ADMIN_TOKEN" "listUsers" \
  '{"query":"query { listUsers(limit:5) { items { id email name role } } }"}' \
  "$TMPDIR_SMOKE/list-users.json"
assert_no_errors "listUsers" "$TMPDIR_SMOKE/list-users.json"

USER_ID=$(jq -r '.data.listUsers.items[0].id // empty' "$TMPDIR_SMOKE/list-users.json")
if [[ -n "$USER_ID" ]]; then
  gql "$ADMIN_TOKEN" "getUser($USER_ID)" \
    "{\"query\":\"query { getUser(id: \\\"$USER_ID\\\") { id email name role isActive } }\"}" \
    "$TMPDIR_SMOKE/get-user.json"
  assert_no_errors "getUser" "$TMPDIR_SMOKE/get-user.json"
else
  log "SKIP  getUser (no users returned by listUsers)"
fi

# ── Step 10: User mutations (2) ───────────────────────────────────────────────

log "--- User mutations ---"

# createUser — random suffix to avoid unique email constraint on reruns.
SMOKE_TS=$(date +%s)
SMOKE_NEW_EMAIL="smoke-created-${SMOKE_TS}@fluxion.local"
gql "$ADMIN_TOKEN" "createUser" \
  "{\"query\":\"mutation { createUser(input: { email: \\\"$SMOKE_NEW_EMAIL\\\", name: \\\"Smoke User $SMOKE_TS\\\", role: OPERATOR }) { id email role } }\"}" \
  "$TMPDIR_SMOKE/create-user.json"
assert_no_errors "createUser (admin)" "$TMPDIR_SMOKE/create-user.json"

NEW_USER_ID=$(jq -r '.data.createUser.id // empty' "$TMPDIR_SMOKE/create-user.json")
if [[ -n "$NEW_USER_ID" ]]; then
  gql "$ADMIN_TOKEN" "updateUser($NEW_USER_ID)" \
    "{\"query\":\"mutation { updateUser(id: \\\"$NEW_USER_ID\\\", input: { name: \\\"Smoke Updated\\\" }) { id name } }\"}" \
    "$TMPDIR_SMOKE/update-user.json"
  assert_no_errors "updateUser" "$TMPDIR_SMOKE/update-user.json"
else
  log "SKIP  updateUser (createUser did not return an id)"
fi

# ── Step 11: Negative test — non-admin cannot createUser ──────────────────────

log "--- Negative test: non-admin createUser must be FORBIDDEN ---"

SMOKE_NEG_EMAIL="smoke-neg-${SMOKE_TS}@fluxion.local"
gql "$NONADMIN_TOKEN" "createUser(non-admin — expect FORBIDDEN)" \
  "{\"query\":\"mutation { createUser(input: { email: \\\"$SMOKE_NEG_EMAIL\\\", name: \\\"Should Fail\\\", role: OPERATOR }) { id } }\"}" \
  "$TMPDIR_SMOKE/neg-create-user.json" || true  # curl exit ignored; response inspected
assert_forbidden "createUser FORBIDDEN (non-admin)" "$TMPDIR_SMOKE/neg-create-user.json"

# ── Step 12: Summary ──────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════"
echo " Smoke Test Summary"
echo "══════════════════════════════════════════════════"
echo " PASS: $PASS"
echo " FAIL: $FAIL"
if [[ ${#FAILURES[@]} -gt 0 ]]; then
  echo ""
  echo " Failed assertions:"
  for f in "${FAILURES[@]}"; do
    echo "   - $f"
  done
fi
echo "══════════════════════════════════════════════════"
echo ""

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi

log "All smoke assertions passed."
exit 0
