# Fluxion Codebase Summary

> **Version:** v1.0
> **Last Updated:** 2026-04-22
> **Audience:** Fluxion contributors and maintainers
> **Authority:** Generated from `repomix-output.xml` (234 files, 154.8K tokens)

---

## Directory Structure

```
fluxion/
├── .github/
│   ├── actions/                              # Reusable CI/CD actions
│   │   ├── aws-oidc-login/                   # GitHub OIDC → AWS role assumption
│   │   ├── docker-build-push-ecr/            # Lambda image build & push
│   │   └── terraform-apply/                  # Terraform plan & apply
│   └── workflows/
│       ├── deploy.yml                        # Main CI/CD: lint → test → tf apply → docker push
│       ├── ci-backend.yml                    # Python linting + testing (flake8, pytest)
│       ├── ci-frontend.yml                   # TypeScript building (Vite)
│       └── ci-oem-processor.yml              # OEM processor (reserved for Phase 5)
│
├── docs/                                     # Documentation (8 files, ~10K LOC)
│   ├── system-architecture.md                # High-level design (v1.3, §3.2 resolver layer)
│   ├── code-standards.md                     # Coding rules: Python, TypeScript, SQL, Git
│   ├── design-patterns.md                    # 11 architectural patterns + cheat sheet
│   ├── development-roadmap.md                # Phase 1–8 planning + status (v1.3, Phase 4 complete)
│   ├── module-structure.md                   # Directory layout per tech stack
│   ├── testing-guide.md                      # Unit/integration testing strategy
│   ├── deployment-guide.md                   # Smoke tests, AWS manual ops (P5 #34)
│   ├── project-changelog.md                  # Semantic versioning + detailed changes
│   └── journals/                             # Planning docs per phase
│
├── fluxion-backend/                          # Python Lambda modules + Terraform
│   ├── migrations/                           # Alembic migration chain (5 revisions)
│   │   ├── versions/
│   │   │   ├── 7124824094ea_accesscontrol_schema.py           # P0: Cross-tenant identity
│   │   │   ├── 4768d32c8037_install_tenant_provisioning_procs.py  # P0: Provisioning procs
│   │   │   ├── 6bbab220d60c_provision_dev1_tenant.py          # P0: Dev1 seed
│   │   │   ├── a1b2c3d4e5f6_seed_permission_catalog.py        # P0: Permission codes
│   │   │   └── b9c3d1e2f4a5_seed_dev_admin_permissions.py     # P5: Dev admin user + grants
│   │   ├── alembic.ini                       # Alembic config
│   │   ├── env.py                            # Alembic engine setup
│   │   └── script.py.mako                    # Alembic migration template
│   │
│   ├── modules/                              # Lambda module directory (4 modules, ~2K LOC)
│   │   ├── _template/                        # Boilerplate for new resolvers
│   │   │   ├── src/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py                   # Permission decorator, Context dataclass
│   │   │   │   ├── base_types.py             # Pydantic v2: BaseInput, BaseResponse, pagination
│   │   │   │   ├── config.py                 # Env var loader (DATABASE_URI, POWERTOOLS_SERVICE_NAME)
│   │   │   │   ├── const.py                  # Constants (error codes, permission codes)
│   │   │   │   ├── db.py                     # psycopg3 Database class + repo pattern
│   │   │   │   ├── exceptions.py             # FluxionError hierarchy
│   │   │   │   ├── handler.py                # Lambda entry point (minimal)
│   │   │   │   └── helpers.py                # Utility functions
│   │   │   ├── tests/                        # Pytest unit/integration tests
│   │   │   │   ├── conftest.py               # Fixtures: DB, tenant schema, context
│   │   │   │   ├── test_auth.py              # Permission decorator tests
│   │   │   │   └── test_handler.py           # Handler dispatch tests
│   │   │   ├── Dockerfile                    # Multi-stage build (poetry, Python 3.12)
│   │   │   ├── pyproject.toml                # psycopg3, pydantic, aws-lambda-powertools
│   │   │   └── README.md                     # Module-specific docs
│   │   │
│   │   ├── device_resolver/                  # Device queries (P2 #34)
│   │   │   └── src/
│   │   │       ├── schema_types.py           # DeviceResponse, DeviceConnectionResponse
│   │   │       └── handler.py                # getDevice, listDevices, getDeviceHistory
│   │   │
│   │   ├── platform_resolver/                # FSM config queries (P3 #34)
│   │   │   └── src/
│   │   │       ├── schema_types.py           # State, Policy, Action, Service responses
│   │   │       └── handler.py                # listStates, listPolicies, etc.
│   │   │
│   │   ├── user_resolver/                    # User management (P4 #34)
│   │   │   └── src/
│   │   │       ├── cognito.py                # Cognito AdminCreateUser wrapper
│   │   │       ├── schema_types.py           # UserResponse, CreateUserInput
│   │   │       └── handler.py                # getCurrentUser, createUser, etc.
│   │   │
│   │   └── smoketest/                        # E2E validation Lambda (reserved)
│   │
│   ├── scripts/                              # Operational shell scripts
│   │   ├── verify-migrations.sh               # Migration validation (downgrade, seed counts)
│   │   ├── provision-dev-admin.sh             # Alembic upgrade + Cognito user seed (P5)
│   │   └── smoke-appsync.sh                   # E2E test: JWT auth → resolver invocation (P5)
│   │
│   └── terraform/                            # Infrastructure as Code (~3K LOC)
│       ├── bootstrap/                        # OIDC + deploy role (apply once, global)
│       │   ├── main.tf                       # OIDC provider, deploy role, trust policy
│       │   ├── oidc.tf                       # GitHub OIDC issuer config
│       │   ├── variables.tf                  # aws_region, github_repo
│       │   ├── versions.tf                   # Provider versions
│       │   └── outputs.tf                    # Role ARN export
│       │
│       ├── modules/                          # Reusable Terraform modules
│       │   ├── api/                          # AppSync GraphQL API module
│       │   │   ├── main.tf                   # AppSync API, schema, auth modes
│       │   │   ├── resolvers.tf              # Lambda data sources + mappings
│       │   │   ├── iam.tf                    # AppSync invoke role
│       │   │   ├── logging.tf                # CloudWatch config, PII redaction
│       │   │   ├── datasources.tf            # NONE + Lambda data sources
│       │   │   ├── variables.tf              # lambda_resolver_arns (map)
│       │   │   └── outputs.tf                # API ID, endpoints, role ARN
│       │   │
│       │   ├── auth/                         # Cognito User Pool module
│       │   │   ├── main.tf                   # User Pool, App Client, custom attributes
│       │   │   ├── variables.tf              # password_min_length, etc.
│       │   │   └── outputs.tf                # Pool ID, App Client ID, SSM exports
│       │   │
│       │   ├── database/                     # RDS + RDS Proxy module
│       │   │   ├── main.tf                   # RDS security group, parameter group
│       │   │   ├── rds.tf                    # RDS instance, backups
│       │   │   ├── proxy.tf                  # RDS Proxy (connection pooling)
│       │   │   └── outputs.tf                # Proxy endpoint, DB host
│       │   │
│       │   ├── network/                      # VPC, subnets, security groups
│       │   │   ├── main.tf                   # VPC, subnets (public + private)
│       │   │   └── outputs.tf                # Subnet IDs, SG IDs for Lambdas
│       │   │
│       │   ├── ecr/                          # ECR repos (auto-discovery)
│       │   │   ├── main.tf                   # Scans modules/ for handler.py, creates repos
│       │   │   └── outputs.tf                # Repo URLs
│       │   │
│       │   └── lambda_function/              # Reusable Lambda wrapper (P1 #34)
│       │       ├── main.tf                   # aws_lambda_function + role + VPC + logs
│       │       ├── variables.tf              # function_name, image_uri, env, extra_policy_statements
│       │       ├── outputs.tf                # function_arn, invoke_arn, role_arn
│       │       └── README.md                 # Usage guide + security notes
│       │
│       └── envs/                             # Environment-specific configs
│           ├── dev/                          # Development environment
│           │   ├── main.tf                   # Module calls: network, database, auth, api, ecr, resolvers
│           │   ├── variables.tf              # env, aws_region, resource_name_prefix
│           │   ├── backend.tf                # S3 state, DynamoDB lock
│           │   ├── terraform.tfvars.example  # Example values
│           │   └── outputs.tf                # API ID, database endpoint
│           ├── staging/                      # Staging environment (placeholder)
│           └── prod/                         # Production environment (placeholder)
│
├── fluxion-console/                          # React web UI (placeholder)
│   └── package.json                          # Node.js build config
│
├── fluxion-oem/                              # OEM processor stubs (Phase 5)
│
├── Makefile                                  # Convenience targets: make dev-up, make test
├── docker-compose.yml                        # Local dev: PostgreSQL, LocalStack
├── schema.graphql                            # 534-line SDL schema (root repo)
├── README.md                                 # Project onboarding
└── repomix-output.xml                        # Codebase compaction (this summary generated from it)
```

---

## Key Modules & Dependencies

### Backend Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12 | Lambda runtime |
| psycopg | 3.1+ | PostgreSQL driver (replaces psycopg2) |
| Pydantic | 2.6+ | Input/output validation |
| aws-lambda-powertools | 2.30+ | Structured logging, tracing |
| Alembic | (latest) | Database migrations |
| Pytest | (latest) | Unit/integration testing |
| Ruff | (latest) | Formatting + linting |
| mypy | (latest) | Type checking |

### Infrastructure Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Terraform | ~5.70 | IaC |
| AWS Lambda | (container image) | Compute runtime |
| AWS RDS PostgreSQL | 15+ | Database |
| AWS AppSync | (latest) | GraphQL API |
| AWS Cognito | (latest) | Authentication |
| AWS ECR | (latest) | Docker image registry |
| AWS SNS/SQS | (latest) | Event streaming (Phase 5+) |

---

## Core Patterns & Conventions

### 1. Lambda Module Structure

Every Lambda resolver lives in `fluxion-backend/modules/{resolver_name}/`:

```
{resolver_name}/
├── src/
│   ├── __init__.py
│   ├── handler.py               # Entry point: lambda_handler(event, context)
│   ├── auth.py                  # Permission decorator, Context class
│   ├── db.py                    # psycopg3 Database wrapper, repos
│   ├── exceptions.py            # Domain error hierarchy
│   ├── config.py                # Environment variable loader
│   ├── schema_types.py          # Pydantic v2 input/output models
│   └── helpers.py               # Utility functions (optional)
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── test_auth.py             # Permission tests
│   ├── test_db.py               # Repository tests
│   └── test_handler.py          # Integration tests
├── Dockerfile                   # Multi-stage: poetry → runtime
├── pyproject.toml               # Poetry dependencies + pytest config
└── README.md                    # Module-specific documentation
```

**Key principles:**
- **No shared code:** Patterns copied per module (auth.py, db.py pattern duplication allowed within code-standards budget).
- **Pydantic v2 boundaries:** Every handler parses input via Pydantic, returns DTO.
- **Permission decorator:** `@permission_required("code:action")` wraps handlers, injects Context.
- **Database context:** `with Database(dsn, tenant_schema) as db:` ensures proper connection lifecycle.
- **Error handling:** Domain errors mapped to AppSync error codes at handler boundary.

### 2. Permission Model

**Catalog table:** `accesscontrol.permissions` (code, description)
**User grants:** `accesscontrol.users_permissions` (user_id, permission_id, tenant_id)

**Examples:** `device:read`, `device:write`, `user:create`, `user:admin`, `platform:admin`

**Enforcement:** Handler decorator queries `accesscontrol.users_permissions` for (cognito_sub, code, tenant_id):

```sql
WHERE u.cognito_sub = %s
  AND p.code = %s
  AND (up.tenant_id = %s OR up.tenant_id IS NULL)  -- Tenant-scoped or global admin
```

### 3. Tenant Isolation

- **Per-schema model:** Each tenant gets one PostgreSQL schema (bare name: `dev1`, `acme`).
- **Schema validation:** Regex `^[a-z][a-z0-9_]{0,39}$` enforced before f-string interpolation.
- **Context-aware DB:** `Database(tenant_schema=ctx.tenant_schema)` scopes all queries.
- **Cross-tenant identity:** `accesscontrol` schema holds users, permissions (shared).

### 4. Handler Dispatch Pattern

```python
FIELD_HANDLERS: dict[str, FieldHandler] = {
    "getDevice": get_device,
    "listDevices": list_devices,
}

def lambda_handler(event, context):
    field = event["info"]["fieldName"]
    handler = FIELD_HANDLERS[field]
    return handler(event["arguments"], event, correlation_id)
```

**Decorator injection:**
```python
@permission_required("device:read")
def get_device(args, ctx, correlation_id):
    # ctx is injected by decorator
    ...
```

### 5. Error Mapping

Domain errors → AppSync error codes:

| Exception | AppSync Code | HTTP |
|-----------|--------------|------|
| AuthenticationError | UNAUTHENTICATED | 401 |
| ForbiddenError | FORBIDDEN | 403 |
| NotFoundError | NOT_FOUND | 404 |
| InvalidInputError | BAD_USER_INPUT | 400 |
| DatabaseError | INTERNAL_ERROR | 500 |

---

## Database Schema Overview

### accesscontrol (Cross-tenant)
- **tenants** — Tenant registry (id, schema_name, enabled)
- **users** — User directory (id, email, cognito_sub, name)
- **permissions** — Permission codes (id, code, description)
- **users_permissions** — Grants (user_id, permission_id, tenant_id)

### {tenant_schema} (Per-tenant, 16 tables)

**FSM Configuration**
- services, states, policies, actions

**Device Management**
- devices, device_informations, device_tokens, action_executions, milestones

**Chat & Messaging**
- chat_sessions, chat_messages, message_templates

**Brand & Model Registry**
- brands, tacs

**Batch Operations**
- batch_actions, batch_device_actions

---

## CI/CD Pipeline

**Workflow: `.github/workflows/deploy.yml`**

**Trigger:** Push to `master` (auto-apply, no approval)

**Jobs (sequential):**
1. **lint** — `flake8 --ignore=E501` on all modules
2. **test** — `pytest` all modules, coverage ≥70%
3. **terraform** — `terraform plan` (PR) / `terraform apply -auto-approve` (push:master)
4. **docker** (matrix) — Build & push per-Lambda image to ECR

**Auth:** GitHub OIDC → `fluxion-backend-gha-deploy` role (no static keys)

**PR Flow:** Lint + test + tf plan only (no apply)

---

## Recent Changes (GH #34, P0–P5)

**Phase 4: GraphQL Resolver Layer (2026-04-22)**

| Phase | Deliverable | Status |
|-------|-------------|--------|
| P0 | Template migration (psycopg3 + Pydantic v2) | ✅ |
| P1 | Reusable `lambda_function` Terraform module | ✅ |
| P2 | device_resolver (3 fields) | ✅ |
| P3 | platform_resolver (4 queries/mutations) | ✅ |
| P4 | user_resolver (Cognito integration) | ✅ |
| P5 | E2E smoke tests + permission catalog seed | ✅ |

**New files:**
- 3 resolver modules (device, platform, user)
- Terraform module: `terraform/modules/lambda_function/`
- Migrations: permission catalog + dev admin seed
- Scripts: `provision-dev-admin.sh`, `smoke-appsync.sh`

**Updated files:**
- `_template/` — psycopg3 + Pydantic v2 migration
- `system-architecture.md` — §3.2 resolver layer documented
- `code-standards.md` — §3.5 psycopg3 patterns, §3.7 handler dispatch
- `development-roadmap.md` — Phase 4 marked complete

---

## Next Steps (Phase 5+)

**Phase 5: OEM Integration (Apple MDM)**
- APNS push provider
- apple_process_action Lambda
- Device checkin handler
- Integration with SNS/SQS choreography

**Phase 6: Chat & Multi-Channel Messaging**
- WebSocket subscriptions
- Message templates
- Notification orchestration

**Phase 7: Payment Workflows**
- Installment contracts
- Lock/release FSM gates
- Payment provider integration

**Phase 8: QA & Performance**
- End-to-end test suite
- Load testing
- Security audit

---

## Unresolved Questions

- **Relay pagination opacity:** Is base64 cursor encoding needed for GraphQL clients (currently using raw ID)?
- **Cognito AdminCreateUser in prod:** ALLOW_ADMIN_USER_PASSWORD_AUTH currently dev-only; prod should use SRP or custom flow.
- **Lambda ARN wiring:** Phase 4 P5 deferred wiring of resolver ARNs into AppSync API module. Awaits P6+ phases.
- **Action resolver FSM:** Guards (SQL constraints) designed but not yet tested in action_resolver field handler.

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.0 | 2026-04-22 | Initial codebase summary (Post-Phase 4 #34 delivery). 234 files, 154.8K tokens. |
