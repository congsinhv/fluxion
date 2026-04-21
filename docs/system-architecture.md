# System Architecture

> **Version:** v1.0
> **Audience:** Fluxion contributors, operators, and architects.
> **Authority:** High-level design decisions and data flow. Pairs with [design-patterns.md](design-patterns.md) (patterns) and [code-standards.md](code-standards.md) (rules).

---

## 1. Overview

Fluxion is a multi-tenant device management platform built on AWS Lambda, PostgreSQL, and AppSync GraphQL. It supports installment payment workflows, OEM integrations (starting with Apple MDM), and real-time device state management via a Finite State Machine (FSM).

**Key principles:**
- **Tenant isolation via schema.** Each tenant gets one PostgreSQL schema holding 16 business tables. Cross-tenant data (users, permissions) lives in `accesscontrol` schema.
- **Serverless choreography.** Multi-step device workflows orchestrated via SNS fan-out + SQS per consumer, not centralized state machines.
- **DB-driven FSM.** Device state transitions are policy-driven: policies stored in tables, guards evaluated in SQL, events emitted post-commit via outbox pattern.

---

## 2. Database Architecture

### 2.1 Schema Layout

PostgreSQL single-database, multi-schema isolation:

```
PostgreSQL (fluxion database)
├── accesscontrol               # Cross-tenant identity & authorization (Alembic rev 7124824094ea)
│   ├── tenants                 # Tenant registry: id, schema_name, enabled, created_at
│   ├── users                   # Cross-tenant users: id, email, cognito_sub, name, enabled
│   ├── permissions             # Permission codes: id, code, description
│   └── users_permissions       # User → permission grants, optionally scoped by tenant_id
│
├── public                      # Provisioning & utility procs (Alembic rev 4768d32c8037)
│   ├── create_tenant_schema(schema_name: TEXT)      # DDL proc: creates schema + 16 business tables
│   └── create_default_tenant_data(schema_name: TEXT) # Seed proc: FSM config, brands, tacs, templates
│
├── {tenant_schema_N}           # Per-tenant business data (one per provisioned tenant, e.g., dev1, acme)
│   │
│   ├── FSM tables (Service Design)
│   │   ├── services            # id (SMALLINT), name, is_enabled, created_at
│   │   ├── states              # id (SMALLINT), name, created_at
│   │   ├── policies            # id (SMALLINT), name, state_id, service_type_id, color, created_at
│   │   └── actions             # id (UUID), name, action_type_id, from_state_id, service_type_id, apply_policy_id, configuration, ext_fields, created_at
│   │
│   ├── Device tables
│   │   ├── devices             # id (UUID), state_id (FK states), current_policy_id (FK), assigned_action_id (FK), created_at, updated_at
│   │   ├── device_informations # id (UUID), device_id (FK devices), serial_number, udid, name, model, os_version, battery_level, wifi_mac, is_supervised, last_checkin_at, created_at, updated_at, ext_fields
│   │   ├── device_tokens       # id (UUID), device_id (FK devices), push_token (BYTEA), push_magic, unlock_token, topic, created_at, updated_at
│   │   └── action_executions   # id (UUID), device_id (FK devices), action_id (FK actions), command_uuid (UUID), status (VARCHAR), created_at, updated_at, ext_fields
│   │
│   ├── Milestone & Policy Audit
│   │   └── milestones          # id (UUID), device_id (FK devices), assigned_action_id (FK), policy_id (FK), created_at, ext_fields
│   │
│   ├── Chat & Templates
│   │   ├── chat_sessions       # id (UUID), user_id (BIGINT, no FK — validates app-layer to accesscontrol.users), created_at, updated_at
│   │   ├── chat_messages       # id (UUID), session_id (FK chat_sessions), role (VARCHAR), content (TEXT), tool_calls (JSONB), tool_result (JSONB), created_at
│   │   └── message_templates   # id (UUID), name, content, notification_type (POPUP|FULLSCREEN), is_active, notification_icon_path, header_icon_path, additional_icon_path, created_at, updated_at
│   │
│   ├── Brand & Device Model Registry
│   │   ├── brands              # id (SERIAL), name (VARCHAR), created_at, updated_at
│   │   └── tacs                # id (UUID), tac_code, provisioning_type, brand_id (FK), model, marketing_name, created_at, updated_at
│   │
│   └── Batch Operations
│       ├── batch_actions       # id (UUID), batch_id (UUID, unique), action_id (FK actions), created_by, total_devices, status, created_at, updated_at
│       └── batch_device_actions # id (UUID), batch_id (FK batch_actions.batch_id), device_id (FK devices), status, error_code, error_message, started_at, finished_at, created_at
│
└── [additional tenant schemas as provisioned]
```

**Table count per tenant:** 16 business tables.
**Indexes per tenant:** 20 (per migration verify-migrations.sh §3.6.3).

### 2.2 Alembic Migration Chain

Three revisions deployed sequentially (Alembic auto-generated hex IDs):

| Revision | Date | Scope | Tables | Description |
|----------|------|-------|--------|-------------|
| `7124824094ea` | 2026-04-20 | `accesscontrol` schema | 4 | Cross-tenant identity: tenants, users, permissions, users_permissions |
| `4768d32c8037` | 2026-04-20 | `public` procs | 2 procs | `create_tenant_schema()` + `create_default_tenant_data()` provisioning |
| `6bbab220d60c` | 2026-04-20 | dev1 seed | - | Calls procs to provision `dev1` demo tenant (16 tables, FSM policies, brands, tacs, message templates) |

**Idempotency:** Alembic tracks applied revisions in `alembic_version` table; each revision runs once. Downgrade is supported for non-prod envs (see verify-migrations.sh for example).

### 2.3 Tenant Provisioning

Two PostgreSQL procedures in `public` schema own tenant creation:

1. **`create_tenant_schema(schema_name TEXT)`**
   - Validates `schema_name` format: `^[a-z][a-z0-9_]{0,39}$` (e.g., `dev1`, `acme`, `fpt`)
   - Rejects reserved names: `public`, `information_schema`, `pg_catalog`, `pg_toast`, `accesscontrol`
   - Creates schema via `CREATE SCHEMA {schema_name}`
   - Creates 16 per-tenant business tables with CHECK constraints + indexes
   - Idempotent: called per-tenant once at provision time

2. **`create_default_tenant_data(schema_name TEXT)`**
   - Inserts seed data into the newly-created tenant schema:
     - 3 services (Inventory, Supply Chain, Postpaid)
     - 6 states (Idle, Registered, Enrolled, Active, Locked, Released)
     - 6 policies (one per state, mapping state ↔ service)
     - 15 actions (Register, Activate, Lock, Unlock, Release, etc.)
     - 1 brand (iPhone)
     - 1 TAC code (iPhone 14 Pro, Apple provisioning type)
     - 3 message templates (lock_popup, lock_fullscreen, reminder_popup in Vietnamese)

**Tenant provisioning flow (app-layer):**
```
Admin UI → API → Lambda → RDS psycopg2 connection
  → CALL public.create_tenant_schema('new_tenant')
  → CALL public.create_default_tenant_data('new_tenant')
  → INSERT INTO accesscontrol.tenants (schema_name, ...) VALUES ('new_tenant', ...)
  → Tenant ready for use
```

### 2.4 Per-Tenant Data Access

All Lambdas follow the tenant-per-schema isolation model:

1. **Auth:** Cognito token carries `tenant_id` claim.
2. **Lookup:** Lambda auth decorator queries `accesscontrol.tenants` WHERE `id = tenant_id`, retrieves `schema_name`.
3. **Repositories:** `DeviceRepository(conn, schema_name)` f-string-interpolates schema into all queries.
4. **Queries:** All tables prefixed with explicit schema, e.g., `SELECT * FROM dev1.devices WHERE id = %s`.

**Cross-tenant leaks:** Prevented by schema boundaries (isolation) + Cognito claim validation (auth). One misconfigured repo → wrong tenant schema passed = wrong data accessed, but still within that tenant's schema boundary.

**Chat sessions & users:** `{tenant_schema}.chat_sessions.user_id` is BIGINT with no cross-schema FK. App layer validates that `user_id` exists in `accesscontrol.users` before accepting the reference.

---

## 3. Application Layers

### 3.1 GraphQL Resolver Layer (AppSync + Lambda)

AppSync routes GraphQL fields to Lambda resolvers via the `Resolver` pattern (see [design-patterns.md §4](design-patterns.md)):

```
Client GraphQL mutation
  ↓
AppSync GraphQL engine
  ↓
Lambda resolver (e.g., device_resolver, action_resolver)
  ├─ Parse event, extract Cognito claims
  ├─ Validate tenant_id claim, resolve schema_name from accesscontrol.tenants
  ├─ Validate input (Pydantic models)
  ├─ Call business logic with tenant context
  ├─ Map errors to AppSync error responses
  └─ Serialize output, return to AppSync
  ↓
AppSync serializes JSON response
  ↓
Client receives response
```

### 3.2 Choreography Saga (SNS/SQS Multi-Lambda Workflows)

Device actions flow across multiple Lambdas using choreography sagas (see [design-patterns.md §2](design-patterns.md)):

```
action_resolver Lambda (AppSync field resolver)
  ├─ Validates & records action intent in action_logs
  └─ Publishes SNS event: action.assigned
       ↓
       ├→ action_trigger Lambda (SQS consumer)
       │  ├─ Reads action details
       │  ├─ Applies FSM policy checks
       │  └─ Publishes SNS: device.push.triggered
       │       ↓
       │       └→ apple_process_action Lambda (OEM worker)
       │          ├─ Sends APNS push to device
       │          └─ Publishes SNS: device.push.sent
       │
       └→ audit_logger Lambda
          └─ Logs action intent for compliance
```

---

## 4. Finite State Machine (FSM)

Device lifecycle driven by DB-driven FSM (see [design-patterns.md §3](design-patterns.md)).

### 4.1 States & Transitions

Seed data (per tenant):

```
Idle → Registered → Enrolled → Active ⇄ Locked → Released
```

6 states, 6 policies (one per state), 15 actions covering:
- Registration & enrollment
- Activate, lock, unlock
- Release (reset to Idle)
- Deregister
- Send message, message in locked state

Guards: Evaluated in SQL (e.g., "can only release if no outstanding installment charges").

### 4.2 Policy Enforcement

```sql
-- Pseudocode from device state update Lambda
WITH policy_check AS (
  SELECT to_state FROM {schema}.state_policies
  WHERE from_state = (SELECT state_id FROM {schema}.devices WHERE id = %s)
    AND action_id = %s
    AND guard_sql IS NULL OR evaluate_guard(guard_sql, %s)
)
UPDATE {schema}.devices SET state_id = (SELECT to_state FROM policy_check)
WHERE id = %s AND (SELECT to_state FROM policy_check) IS NOT NULL
RETURNING *;
```

---

## 5. External Integrations

### 5.1 Apple MDM (OEM Integration)

Factory pattern (see [design-patterns.md §6](design-patterns.md)) abstracts OEM providers:

```python
class OEMProvider(ABC):
    @abstractmethod
    def push_action(self, device: Device, action: Action) -> PushResult: ...

class AppleProvider(OEMProvider):
    # APNS HTTP/2 calls, MDM command queuing, etc.
    ...

PROVIDERS = {Platform.APPLE: AppleProvider}
```

apple_process_action Lambda:
1. Receives SQS event (device.push.triggered)
2. Looks up device serial, push token, topic
3. Calls AppleProvider.push_action()
4. Handles transient failures (circuit breaker)
5. Publishes device.push.sent (success/failure)

---

## 6. Authorization

`accesscontrol.users_permissions` table:
- User → permission grants
- Optionally scoped by `tenant_id` (NULL = global admin)

Lambda auth decorator:
1. Reads Cognito sub from token
2. Looks up user in `accesscontrol.users`
3. Queries `accesscontrol.users_permissions` WHERE `user_id = ? AND (tenant_id IS NULL OR tenant_id = ?)`
4. Checks permission code against field-level decorator (e.g., `@require_role("admin")`)

---

## 7. Idempotency & Deduplication

SQS and AppSync both retry. Lambdas tolerate at-least-once delivery via idempotency keys:

```sql
INSERT INTO {schema}.action_logs (id, idempotency_key, ...)
VALUES (%s, %s, ...)
ON CONFLICT (idempotency_key) DO UPDATE
  SET id = {schema}.action_logs.id
RETURNING *;
```

Idempotency key sourced from:
- AppSync mutations: client-supplied or derived from request_id + tenant + operation
- SQS consumers: SNS message ID (included in SQS message attributes)

---

## 8. CI/CD Pipeline & Deployment

### 8.1 GitHub Actions Workflow (`deploy.yml`)

Two-phase deployment strategy: plan-only on PR; auto-apply on merge to `master` (prod).

**Git flow:**
```
feature/<N>-<slug> ──(PR)──▶ develop ──(manual dev deploy)──┐
                                                            ▼
                               (PR at phase close) develop ──▶ master  ──(CI/CD auto-apply, prod)
```

- `develop` — integration branch, **no CI/CD**; operator runs `terraform apply` locally for dev-env verification.
- `master` — prod branch; push triggers `deploy.yml` which applies Terraform + pushes ECR images.

**On `push: master`** (auto-apply, no manual approval):
```
lint (flake8) ─→ test (pytest) ─→ terraform apply ─→ docker push matrix
```

**On `pull_request` (to master)** (plan-only, gates merge):
```
lint (flake8) ─→ test (pytest) ─→ terraform plan (artifact) ─→ [blocked: no apply/push]
```

### 8.2 Jobs & Composite Actions

| Job | Inputs | Outputs | Description |
|-----|--------|---------|-------------|
| `lint` | source: `fluxion-backend/modules/*/` | pass/fail | Runs `flake8 --ignore=E501` on all Lambda modules |
| `test` | pytest tests | coverage ≥70% | Validates all unit + integration tests pass |
| `terraform` | `.tfvars`, Cognito/ECR modules | plan artifact (PR) / resources live (push:main) | `plan` on PR; `apply -auto-approve` on push:main |
| `docker` (matrix) | ECR repo list, Lambda module source | image tags pushed to ECR | Builds & pushes per-Lambda image; scans repo list from terraform outputs |

**Composite Actions:**
1. **`aws-oidc-login`** — Assumes `fluxion-backend-gha-deploy` role via GitHub OIDC, exports AWS credentials
2. **`terraform-apply`** — Runs `tf init`, `tf plan`, `tf apply` with var files; supports dry-run mode (PR only)
3. **`docker-build-push-ecr`** — Builds single Lambda image, tags with module name + commit SHA, pushes to ECR repo

### 8.3 OIDC & IAM Role

**GitHub OIDC Provider** (AWS):
- Issuer: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`
- Trust policy scoped to:
  - `repo:congsinhv/fluxion:ref:refs/heads/master` — auto-apply on push:master (prod CI/CD)
  - `repo:congsinhv/fluxion:pull_request` — plan-only for PR validation
  - `develop` branch is dev-env integration only — no CI/CD trust needed (manual deploy)

**IAM Role: `fluxion-backend-gha-deploy`**
- Permissions: Terraform state (S3, DynamoDB lock), RDS, ECR, Cognito, Secrets Manager, SSM Parameter Store
- No static AWS keys in GitHub secrets — OIDC-only

### 8.4 ECR Module & Auto-Discovery

**ECR Module** (`terraform/modules/ecr/`) scans `fluxion-backend/modules/` for directories containing `handler.py` (Lambda marker) and creates:

```
ECR Repository per Lambda module:
  fluxion-backend-device-resolver
  fluxion-backend-action-resolver
  fluxion-backend-apple-process-action
  ...
```

**Lifecycle Policy:** Keep last 10 images per repo; delete older. This prevents ECR cost explosion and maintains deployment rollback window.

### 8.5 Deployment Flow (Manual Invocation)

After merge to main, GitHub Actions triggers automatically:

```
1. Pull code & mount AWS credentials (OIDC role assumption)
2. Lint: flake8 on all modules
3. Test: pytest all modules
4. Terraform: 
   - cd terraform/envs/dev
   - terraform plan (verify no surprises)
   - terraform apply -auto-approve (create/update resources)
5. Docker Build & Push (matrix job):
   - For each ECR repo created in step 4
   - Build image: fluxion-backend-{module}:latest
   - Tag: {ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/{repo}:latest
   - Push to ECR (ready for Lambda deployment via CI/CD tool or manual invoke)
```

### 8.6 Secrets & Environment

**GitHub Secrets:**
- `AWS_DEPLOY_ROLE_ARN` — IAM role ARN for OIDC assumption

**Environment Variables (in workflow file):**
- `AWS_REGION = "us-east-1"`
- `TF_VAR_environment = "dev"`
- `REGISTRY_PREFIX = "{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com"`

**SSM Parameter Exports** (Cognito module):
- `/{env}/cognito/user_pool_id` — Lambda config.py reads at startup
- `/{env}/cognito/app_client_id` — Injected into app initialization

---

## 9. Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.1 | 2026-04-20 | Added CI/CD section (§8): GitHub OIDC, deploy.yml workflow, ECR auto-discovery, docker matrix push (#32, pending merge). |
| v1.0 | 2026-04-20 | Initial release. Documents 3-revision Alembic chain, accesscontrol + 16 per-tenant tables, provisioning procs, FSM design (#31). |
