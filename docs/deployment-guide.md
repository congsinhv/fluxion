# Deployment Guide

> Last updated: 2026-04-22
> Covers: local dev setup, Terraform apply, DB migrations, Cognito provisioning, smoke testing.

---

## Prerequisites

| Tool | Minimum version | Purpose |
|------|----------------|---------|
| `aws` CLI | v2.x | AWS resource management |
| `terraform` | 1.7+ | Infrastructure provisioning |
| `psql` | 14+ | DB admin operations |
| `jq` | 1.6+ | JSON parsing in shell scripts |
| `curl` | 7.68+ | HTTP requests in smoke tests |
| `uv` | 0.4+ | Python venv + Alembic runner |
| `shellcheck` | 0.8+ | Shell script linting |

AWS credentials must have the `fluxion-backend-gha-deploy` role (or equivalent dev-admin permissions) assumed before running any script.

---

## 1. Terraform Apply (dev)

```bash
cd fluxion-backend/terraform/envs/dev
terraform init
terraform plan
terraform apply
```

Key outputs consumed by scripts:

| Output | Description |
|--------|-------------|
| `cognito_user_pool_id` | Cognito User Pool ID |
| `cognito_client_id` | App client for admin console |
| `appsync_graphql_endpoint` | AppSync HTTPS endpoint |

---

## 2. Database Migrations

Run from the `fluxion-backend/` directory:

```bash
cd fluxion-backend
uv run alembic upgrade head
```

Migration chain (in order):

| Revision | Description |
|----------|-------------|
| `7124824094ea` | `accesscontrol` schema + 4 identity tables |
| `4768d32c8037` | Tenant provisioning stored procedures |
| `6bbab220d60c` | `dev1` demo tenant schema + seed data |
| `a1b2c3d4e5f6` | Permission catalog (6 codes) |
| `b9c3d1e2f4a5` | Dev admin user + `dev1` permission grants |

---

## 3. Provision Dev Admin User

The `provision-dev-admin.sh` script is **idempotent** — safe to re-run.

```bash
export DATABASE_URI="postgres://user:pass@host:5432/fluxion"
cd fluxion-backend
./scripts/provision-dev-admin.sh
```

What it does:

1. Reads `USER_POOL_ID` and `CLIENT_ID` from Terraform outputs.
2. Reads (or auto-generates) `DEV_ADMIN_PASSWORD` from SSM `/fluxion/dev/admin_password`.
3. Creates Cognito user `dev-admin@fluxion.local` with `SUPPRESS` message action and `email_verified=true`.
4. Sets a permanent password (no force-change-password challenge).
5. Extracts the Cognito `sub` and writes it to `accesscontrol.users.cognito_sub`.

> **Note:** The script never logs passwords or tokens. All credential operations are wrapped in `set +x`.

> **Note:** `DATABASE_URI` must resolve to an RDS instance reachable from the execution environment (bastion host, VPN tunnel, or within-VPC CI runner). The RDS instance is not publicly accessible.

---

## 4. Smoke Testing

The smoke script validates the full auth path: Cognito JWT → AppSync → Lambda resolvers → PostgreSQL.

### Run

```bash
cd fluxion-backend
./scripts/smoke-appsync.sh
```

### Prerequisites

- Terraform applied (outputs available).
- `provision-dev-admin.sh` has been run (dev admin has a `cognito_sub` in DB).
- DB migrations at `head` (all 5 revisions applied).
- Lambda resolvers deployed and wired into `lambda_resolver_arns` in `terraform/envs/dev/main.tf`.

### What the smoke script tests

| Suite | Operation | Assertion |
|-------|-----------|-----------|
| Device | `listDevices` | No errors, items shape |
| Device | `getDevice(id)` | No errors (skipped if no device rows) |
| Device | `getDeviceHistory(deviceId)` | No errors (skipped if no device rows) |
| Platform | `listServices` | No errors, id/name/isEnabled |
| Platform | `listStates` | No errors, id/name |
| Platform | `listPolicies` | No errors, id/name/stateId |
| Platform | `listActions` | No errors, id/name/applyPolicyId |
| Platform | `updateState` | Non-destructive round-trip, no errors |
| Platform | `updatePolicy` | Non-destructive round-trip, no errors |
| Platform | `updateAction` | Non-destructive round-trip, no errors |
| Platform | `updateService` | Non-destructive round-trip, no errors |
| User | `getCurrentUser` | No errors, email/name/role |
| User | `listUsers` | No errors, items shape |
| User | `getUser(id)` | No errors (uses first id from listUsers) |
| User | `createUser` (admin) | No errors, returns id |
| User | `updateUser` | No errors, name updated |
| **Negative** | `createUser` (non-admin) | Must return FORBIDDEN/Unauthorized |

Each curl call is timed; elapsed ms is printed alongside each PASS/FAIL line.

### Exit codes

- `0` — all assertions passed
- `1` — one or more assertions failed (failures listed in summary)

### Security notes

- Tokens are never printed; `set +x` guards all credential operations.
- Non-admin smoke user (`smoke-nonadmin@fluxion.local`) and its password are stored in SSM `/fluxion/dev/smoke_nonadmin_password`.
- `createUser` smoke mutations use timestamp-suffixed emails to avoid unique constraint collisions on reruns.

---

## 5. CI/CD Integration

The smoke script is designed for CI use. Add after `terraform apply` and Lambda deploy steps:

```yaml
- name: Run AppSync smoke tests
  env:
    DATABASE_URI: ${{ secrets.DEV_DATABASE_URI }}
  run: |
    cd fluxion-backend
    ./scripts/smoke-appsync.sh
```

Ensure the CI runner has network access to RDS (VPC runner or bastion tunnel) and AWS credentials with Cognito + SSM read permissions.

---

## 6. Rollback

Database rollback (dev/staging only — never production):

```bash
cd fluxion-backend
# Roll back last migration
uv run alembic downgrade -1

# Roll back to specific revision
uv run alembic downgrade 6bbab220d60c
```

Infrastructure rollback: revert `terraform/envs/dev/main.tf` and re-apply.
