# Project Changelog

> **Version:** v1.0
> **Last Updated:** 2026-04-20
> **Format:** [Semantic Versioning](https://semver.org/) for releases; Git commits follow conventional format.

---

## [Unreleased]

### Added
- Documentation: system-architecture.md (DB schema, FSM design, choreography sagas, OEM integration outline)
- Documentation: development-roadmap.md (Phase 1–8 timeline, Phase 3 marked complete)
- Documentation: project-changelog.md (this file)

---

## [1.1.0] - 2026-04-20

### Feature: Cognito Auth + CI/CD Deploy Pipeline (#32)

**Summary:** GitHub OIDC provider for keyless AWS auth; Cognito User Pool (email username, 12-char strong pw, custom:role); ECR module with Lambda image auto-discovery; `deploy.yml` pipeline: lint → test → tf apply → docker matrix push.

**Added**

#### Terraform Modules

**`terraform/bootstrap/` — OIDC & Deploy Role (applied once, bootstrap-only)**
- GitHub OIDC provider (OIDC issuer, audience, thumbprint)
- `fluxion-backend-gha-deploy` IAM role (trust policy scoped to `repo:congsinhv/fluxion:ref:refs/heads/main` + PR refs)
- Inline policy: Terraform state (S3 + DynamoDB), RDS, ECR, Cognito, Secrets Manager, SSM Parameter Store
- Environment: `dev` only (stage/prod in future ticket #33)

**`terraform/modules/auth/` — Cognito User Pool + App Client**
- **User Pool:** Email-based username, 12-character minimum with uppercase + number requirement, MFA optional
- **Custom Attributes:** `custom:role` (tenant_admin, user, viewer) — initialized at signup
- **App Client:** SRP-only auth (no plain-password flow), 1-hour access token, 1-hour ID token, 30-day refresh token, ALLOW_USER_PASSWORD_AUTH disabled
- **SSM Parameter Exports:** `/{env}/cognito/user_pool_id`, `/cognito/app_client_id` for app code injection

**`terraform/modules/ecr/` — ECR Auto-Discovery + Lifecycle**
- **Auto-Discovery:** Scans `fluxion-backend/modules/` for directories containing `handler.py` (Lambda markers)
- **Repository per Module:** Creates ECR repo named `fluxion-backend-{module_name}` (e.g., `fluxion-backend-device-resolver`)
- **Lifecycle Policy:** Keep last 10 images per repo, delete older
- **Output:** Repository URLs for `deploy.yml` docker push matrix

#### CI/CD Pipeline (GitHub Actions)

**`.github/workflows/deploy.yml` — Push:main → Lint/Test → Tf Apply → Docker Matrix Push**

Workflow structure:
- **Trigger:** `push:` on `main` (auto-apply, no manual approval)
- **Jobs:**
  - `lint`: `flake8 --ignore=E501` on `fluxion-backend/modules/*/` (line length 200+ OK)
  - `test`: `pytest` on all modules, coverage ≥ 70% (configurable via `.pytest.ini`)
  - `terraform`: 
    - `cd terraform/envs/dev && terraform plan`
    - `cd terraform/envs/dev && terraform apply -auto-approve` (on push main only)
  - `docker` (matrix job, depends on terraform):
    - Discovers all ECR repos created in terraform
    - Builds & pushes per-Lambda image to `{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/{repo}:latest`
    - AWS auth via OIDC (no static keys in secrets)

**PR Flow:** Lint + test + tf plan only (no apply, no docker push).

**Composite Actions** (`.github/actions/`):
1. `aws-oidc-login/` — Assumes `fluxion-backend-gha-deploy` role via OIDC, sets AWS env vars
2. `terraform-apply/` — Runs tf init, plan, apply with var files
3. `docker-build-push-ecr/` — Builds single Lambda image, tags, pushes to ECR

#### Environment & Wiring

- **Terraform Variables:**
  - `environment = "dev"`
  - `aws_region = "us-east-1"` (configurable, defaults to ENV var or tfvars)
  - `cognito_password_min_length = 12`
  - `ecr_keep_last_images = 10`

- **GitHub Secrets:**
  - `AWS_DEPLOY_ROLE_ARN` = `arn:aws:iam::{ACCOUNT}:role/fluxion-backend-gha-deploy`
  - No static AWS keys (keyless OIDC only)

- **App-Layer Injection:**
  - Lambda `config.py` reads `boto3.client("ssm").get_parameter("/dev/cognito/user_pool_id")` at startup
  - App Client ID injected similarly from `/dev/cognito/app_client_id`

**Status:** Code merged (PR #68); infrastructure partially applied — OIDC + deploy role live in AWS, Cognito + ECR + docker push awaiting full dev env apply in follow-up validation (TC-02/TC-03).

### Changed
- (n/a)

### Changed
- **Design Patterns (§11):** Updated tenant-per-schema section to reflect actual implementation:
  - Schema naming: corrected from `tenant_{slug}` prefix to bare names (`dev1`, `acme`, `fpt`)
  - Shared schema: renamed `meta` → `accesscontrol` (cross-tenant identity)
  - Clarified 16 per-tenant business tables + provisioning proc structure

---

## [1.0.0] - 2026-04-20

### Feature: Multi-Tenant Database Migration (#31)

**Summary:** First production-ready database schema supporting per-enterprise data isolation via PostgreSQL tenant-per-schema model.

**Added**

#### Database Migrations (Alembic)

- **Rev 7124824094ea** — `accesscontrol` schema + 4 cross-tenant identity tables:
  - `accesscontrol.tenants` (id, schema_name, enabled, created_at) — registry of provisioned tenants
  - `accesscontrol.users` (id, email, cognito_sub, name, enabled, created_at) — cross-tenant user directory
  - `accesscontrol.permissions` (id, code, description) — permission catalog
  - `accesscontrol.users_permissions` (id, user_id, permission_id, tenant_id, granted_at) — user→permission grants, optionally tenant-scoped

- **Rev 4768d32c8037** — Tenant provisioning procedures in `public` schema:
  - `create_tenant_schema(schema_name TEXT)` — Creates per-tenant schema + 16 business tables with indexes
  - `create_default_tenant_data(schema_name TEXT)` — Seeds FSM config (services, states, policies, actions), brands, tacs, message templates
  - Schema name validation: `^[a-z][a-z0-9_]{0,39}$` (no prefix required)
  - Reserved name rejection: `public`, `information_schema`, `pg_catalog`, `pg_toast`, `accesscontrol`

- **Rev 6bbab220d60c** — Dev1 demo tenant:
  - Calls both provisioning procs to create `dev1` schema
  - Seeds 16 per-tenant tables with demo FSM config:
    - **FSM:** 3 services, 6 states, 6 policies, 15 actions
    - **Devices:** devices, device_informations, device_tokens, action_executions, milestones
    - **Chat:** chat_sessions, chat_messages, message_templates
    - **Brand Registry:** brands, tacs
    - **Batch Operations:** batch_actions, batch_device_actions

#### Per-Tenant Business Tables (16 total)

| Category | Tables |
|----------|--------|
| FSM Configuration | services, states, policies, actions |
| Device Management | devices, device_informations, device_tokens, action_executions, milestones |
| Chat & Messaging | chat_sessions, chat_messages, message_templates |
| Brand & Model Registry | brands, tacs |
| Batch Operations | batch_actions, batch_device_actions |

**Total:** 4 (accesscontrol) + 2 (procs) + 16 per-tenant = 22 tables across `accesscontrol` + per-tenant schemas.

#### Features

- **Tenant Isolation:** Each tenant schema is a hard boundary; cross-tenant data leaks require bugs in auth/construction, not query logic.
- **On-Demand Provisioning:** New tenants created by calling stored procs; schema + seed data created atomically.
- **Schema Name Safety:** Bare schema names (`dev1`, `acme`) validated via CHECK constraint in `accesscontrol.tenants` + regex in proc.
- **FSM Seeds:** Every tenant gets consistent FSM state machine (states, transitions, policies) enabling device lifecycle management.
- **Backward Compatibility:** No breaking changes (first migration in `7124824094ea` has `down_revision = None`).

#### Testing

- **Verification Script:** `fluxion-backend/scripts/verify-migrations.sh`
  - Downgrade to base → upgrade head → verify seed counts → secondary tenant parity → invalid name rejection → cleanup
  - Asserts: 16 per-tenant tables, correct seed counts (3 services, 6 states, 15 actions, etc.)

### Fixed
- (n/a — initial release)

### Security

- **SQL Injection Prevention:** Schema names validated before f-string interpolation in migration code. Lambda code paths (to be implemented Phase 4) must follow same pattern.
- **Cross-Tenant Isolation:** Schema-level isolation enforced; Cognito claims validated at auth boundary.
- **Password/Secrets:** No credentials stored in migration files; all DB auth via RDS IAM or Secrets Manager (external to migrations).

### Documentation

- **design-patterns.md §11** — Updated tenant-per-schema pattern docs with correct schema naming, `accesscontrol` reference, 16-table architecture.
- **system-architecture.md §2** — New comprehensive database architecture section covering schema layout, migration chain, provisioning flow, per-tenant access patterns.
- **development-roadmap.md** — Phase 3 marked complete; Phases 4–8 planning (GraphQL resolvers, OEM integration, chat, payments, QA).

### Known Issues

- None identified. All verification tests pass.

### Breaking Changes

- (n/a — initial schema)

### Deprecations

- (n/a)

---

## [0.2.0] - 2026-04-19

### Feature: Documentation Foundation (#61)

**Added**

- **design-patterns.md** (v1.0)
  - 11 core patterns: Choreography Saga, FSM, Resolver, Repository, Factory, DTO/Pydantic, Circuit Breaker, Idempotency, Anti-patterns, Tenant-per-Schema
  - Cheat sheet for pattern selection
  - References to Wiki + Architecture docs

- **code-standards.md**
  - File organization (Lambda module structure, 200-LOC budget, no shared code)
  - Error handling conventions (FluxionError hierarchy, re-raising)
  - Naming conventions (camelCase functions, SCREAMING_SNAKE constants)
  - Database practices (parameterized queries, schema-qualified SQL)
  - Testing standards (unit, integration, fixture patterns)

- **module-structure.md**
  - Monorepo layout: `fluxion-backend/`, `fluxion-oem/`, `fluxion-console/`
  - Per-Lambda module structure: `handler.py`, `config.py`, `db.py`, `service.py`, `dto.py`, `tests/`
  - No shared top-level `shared/` directory; code duplication allowed within budget

- **testing-guide.md**
  - Unit tests: mock driver seam, test business logic in isolation
  - Integration tests: real PostgreSQL container, RDS Proxy, full request-to-response flow
  - Fixtures: conftest.py per module, tenant schema setup helpers
  - Coverage targets: ≥ 80% on critical paths

---

## [0.1.0] - 2026-04-19

### Feature: Monorepo & Development Environment (#29, #30)

**Added**

- **Monorepo Structure**
  - `fluxion-backend/` — Python Lambda modules + Alembic migrations
  - `fluxion-oem/` — OEM-specific workers (Apple MDM, future Samsung Knox)
  - `fluxion-console/` — React web UI (placeholder)
  - Shared: `Makefile`, `.github/workflows/`, `docker-compose.yml`

- **Infrastructure as Code (Terraform)**
  - Network module: VPC, subnets, security groups
  - Database module: RDS PostgreSQL, parameter groups, backups
  - Lambda IAM roles, VPC endpoints
  - Dev environment: `docker-compose.yml` with PostgreSQL, LocalStack (S3, SQS, SNS)

- **CI/CD Pipeline**
  - GitHub Actions: `lint`, `test`, `build`, `deploy-dev`
  - Pre-commit hooks: code format, linting, migration validation
  - Deployment gates: required test pass, code review approval

- **Development Setup**
  - `Makefile` targets: `make dev-up`, `make test`, `make db-migrate`
  - Docker images: Python 3.10+ runtime, PostgreSQL 15
  - Local development: RDS Proxy emulation via pgBouncer

### Changed
- (n/a — initial setup)

### Fixed
- (n/a)

---

## Notes

### Commit Message Format

Follows `[#N]: Subject` pattern (not conventional-commits):
- `[#31]: Multi-tenant DB migrations (accesscontrol + 16 tables per tenant)`
- `[#30]: Terraform modules for network and database`

See [CLAUDE.md](../CLAUDE.md) for details.

### Versioning Strategy

- **Project Version:** Semantic versioning (MAJOR.MINOR.PATCH) tracked in this changelog.
- **Database Schema Version:** Tracked via Alembic `alembic_version` table; migrations cumulative, not replaced.
- **Release Cadence:** As-needed (feature-driven), planned weekly post-Phase 4.

### Migration & Deployment

- **Forward-only in production:** Downgrade only supported in dev/staging.
- **Zero-downtime:** Schema changes in separate revisions; app code compatible with N and N+1 schema versions.
- **Rollback:** Create new forward migration to undo changes, never downgrade in prod.

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.1 | 2026-04-20 | Added Phase 3b (T6 #32) entry: Cognito auth module + CI/CD deploy pipeline (code merged, infrastructure partial apply). |
| v1.0 | 2026-04-20 | Initial changelog with Phases 1–3 entries; Phase 3 (T6 #31) marked complete. |
