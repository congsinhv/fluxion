#!/usr/bin/env bash
# provision-dev-admin.sh — Idempotent Cognito + DB seed for the dev admin user.
#
# Usage:
#   DATABASE_URI=postgres://... ./scripts/provision-dev-admin.sh
#
# What it does:
#   1. Reads USER_POOL_ID and CLIENT_ID from Terraform outputs.
#   2. Reads (or creates) DEV_ADMIN_PASSWORD in SSM /fluxion/dev/admin_password.
#   3. Creates the Cognito user (admin-create-user, SUPPRESS, email-verified).
#   4. Sets the user to permanent password so no force-change-password is needed.
#   5. Extracts the Cognito sub and writes it back to accesscontrol.users.
#
# Prerequisites:
#   - aws CLI v2 with credentials for the dev account
#   - jq, psql (or psql reachable via $DATABASE_URI)
#   - Terraform applied in fluxion-backend/terraform/envs/dev
#   - DATABASE_URI env var pointing at the RDS instance (via bastion/VPN/tunnel)
#
# Idempotency:
#   - Each step checks for existing state before acting.
#   - Safe to re-run without creating duplicates.

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────────

DEV_ADMIN_EMAIL="dev-admin@fluxion.local"
SSM_PASSWORD_PATH="/fluxion/dev/admin_password"
TF_DIR="$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)"

# ── Helpers ────────────────────────────────────────────────────────────────────

log()  { echo "[provision-dev-admin] $*"; }
die()  { echo "[provision-dev-admin] ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

require_cmd aws
require_cmd jq
require_cmd psql
require_cmd terraform

# ── DATABASE_URI guard ─────────────────────────────────────────────────────────

[[ -z "${DATABASE_URI:-}" ]] && die "DATABASE_URI env var is required (postgres://user:pass@host/db)"

# ── Step 1: Terraform outputs ──────────────────────────────────────────────────

log "Reading Terraform outputs from $TF_DIR ..."
USER_POOL_ID=$(terraform -chdir="$TF_DIR" output -raw cognito_user_pool_id)
CLIENT_ID=$(terraform -chdir="$TF_DIR" output -raw cognito_client_id)

[[ -z "$USER_POOL_ID" ]] && die "cognito_user_pool_id output is empty"
[[ -z "$CLIENT_ID"    ]] && die "cognito_client_id output is empty"
log "USER_POOL_ID=$USER_POOL_ID  CLIENT_ID=$CLIENT_ID"

# ── Step 2: SSM password — create if missing ───────────────────────────────────

log "Checking SSM parameter $SSM_PASSWORD_PATH ..."

set +x  # No credential logging from here
if aws ssm get-parameter --name "$SSM_PASSWORD_PATH" --with-decryption \
       --query "Parameter.Value" --output text >/dev/null 2>&1; then
  log "SSM password parameter already exists."
  DEV_ADMIN_PASSWORD=$(
    aws ssm get-parameter \
      --name "$SSM_PASSWORD_PATH" \
      --with-decryption \
      --query "Parameter.Value" \
      --output text
  )
else
  log "SSM password parameter missing — generating and storing ..."
  # 20-char random password satisfying Cognito policy (upper, lower, number, symbol).
  DEV_ADMIN_PASSWORD=$(
    LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' </dev/urandom | head -c 20
  )
  aws ssm put-parameter \
    --name "$SSM_PASSWORD_PATH" \
    --type "SecureString" \
    --value "$DEV_ADMIN_PASSWORD" \
    --description "Dev admin password for dev-admin@fluxion.local (auto-generated)" \
    --overwrite >/dev/null
  log "Stored new password in SSM."
fi
set -x

# ── Step 3: Create Cognito user (idempotent) ───────────────────────────────────

log "Checking if Cognito user $DEV_ADMIN_EMAIL already exists ..."
USER_EXISTS=$(
  aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$DEV_ADMIN_EMAIL" \
    --query "Username" \
    --output text 2>/dev/null || echo "NOT_FOUND"
)

if [[ "$USER_EXISTS" == "NOT_FOUND" ]]; then
  log "Creating Cognito user $DEV_ADMIN_EMAIL ..."
  aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$DEV_ADMIN_EMAIL" \
    --message-action SUPPRESS \
    --user-attributes \
      Name=email,Value="$DEV_ADMIN_EMAIL" \
      Name=email_verified,Value=true \
      Name=custom:tenant_id,Value="1" \
    >/dev/null
  log "Cognito user created."
else
  log "Cognito user already exists — ensuring custom:tenant_id attribute is set."
  aws cognito-idp admin-update-user-attributes \
    --user-pool-id "$USER_POOL_ID" \
    --username "$DEV_ADMIN_EMAIL" \
    --user-attributes Name=custom:tenant_id,Value="1" \
    >/dev/null
fi

# ── Step 4: Set permanent password ────────────────────────────────────────────

log "Setting permanent password ..."
set +x
aws cognito-idp admin-set-user-password \
  --user-pool-id "$USER_POOL_ID" \
  --username "$DEV_ADMIN_EMAIL" \
  --password "$DEV_ADMIN_PASSWORD" \
  --permanent \
  >/dev/null
set -x
log "Permanent password set."

# ── Step 5: Extract Cognito sub ───────────────────────────────────────────────

log "Extracting Cognito sub for $DEV_ADMIN_EMAIL ..."
COGNITO_SUB=$(
  aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$DEV_ADMIN_EMAIL" \
    --query "UserAttributes[?Name=='sub'].Value" \
    --output text
)

[[ -z "$COGNITO_SUB" ]] && die "Could not extract Cognito sub for $DEV_ADMIN_EMAIL"
log "Cognito sub: $COGNITO_SUB"

# ── Step 6: Update accesscontrol.users with cognito_sub ───────────────────────

log "Writing cognito_sub to accesscontrol.users ..."
psql "$DATABASE_URI" -v ON_ERROR_STOP=1 -c \
  "UPDATE accesscontrol.users
   SET    cognito_sub = '$COGNITO_SUB'
   WHERE  email       = '$DEV_ADMIN_EMAIL';"

UPDATED=$(
  psql "$DATABASE_URI" -t -A -c \
    "SELECT COUNT(*) FROM accesscontrol.users
     WHERE email = '$DEV_ADMIN_EMAIL'
       AND cognito_sub IS NOT NULL;"
)

[[ "$UPDATED" -eq 1 ]] || die "DB update did not affect expected row (got $UPDATED)"
log "accesscontrol.users updated with cognito_sub."

log "Done. Dev admin provisioned successfully."
log "  Email:       $DEV_ADMIN_EMAIL"
log "  Pool:        $USER_POOL_ID"
log "  Cognito sub: $COGNITO_SUB"
