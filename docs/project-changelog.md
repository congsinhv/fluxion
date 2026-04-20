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
| v1.0 | 2026-04-20 | Initial changelog with Phases 1–3 entries; Phase 3 (T6 #31) marked complete. |
