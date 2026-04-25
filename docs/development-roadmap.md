# Development Roadmap

> **Version:** v1.0
> **Last Updated:** 2026-04-20
> **Audience:** Fluxion contributors, project leads, stakeholders.

---

## Phase Overview

Fluxion development is organized into phases, each delivering concrete business capability and infrastructure milestones.

| Phase | Name | Status | Target | Key Deliverables |
|-------|------|--------|--------|------------------|
| **Phase 1** | Monorepo & Dev Env Setup | ✅ COMPLETE | 2026-04-19 | Terraform modules, Docker Compose, CI/CD pipeline (#29, #30) |
| **Phase 2** | Documentation Foundation | ✅ COMPLETE | 2026-04-19 | Design patterns, code standards, testing guide (#61) |
| **Phase 3** | Multi-Tenant DB Migration | ✅ COMPLETE | 2026-04-20 | Alembic 3-revision chain, accesscontrol + tenant-per-schema (#31) |
| **Phase 3b** | Auth + CI/CD Pipeline | ✅ COMPLETE | 2026-04-20 | Cognito User Pool, ECR module, deploy.yml pipeline (#32) |
| **Phase 3c** | AppSync GraphQL API | ✅ COMPLETE | 2026-04-21 | AppSync API infrastructure, schema, Cognito+IAM auth, SSM exports (#33) |
| **Phase 4** | GraphQL Resolver Layer | ✅ COMPLETE | 2026-04-22 | 3 Lambda resolvers (device/platform/user), psycopg3+Pydantic v2, permission catalog, E2E smoke (T8 #34) |
| **Phase 5** | OEM Integration (Apple MDM) | 📋 PLANNED | 2026-05-31 | APNS push, MDM command queue, device checkin workflow |
| **Phase 6** | Chat & Multi-Channel Messaging | 📋 PLANNED | 2026-06-30 | WebSocket chat, message templates, notification orchestration |
| **Phase 7** | Payment Workflows (Installments) | 📋 PLANNED | 2026-07-31 | Installment contracts, lock/release FSM gates, payment provider integration |
| **Phase 8** | Testing & Quality Assurance | 📋 PLANNED | 2026-08-31 | End-to-end tests, performance benchmarks, security audit |

---

## Phase 3: Multi-Tenant DB Migration (COMPLETE)

**GitHub Issue:** #31  
**Status:** ✅ COMPLETE (2026-04-20)

### Scope

Multi-tenant database architecture enabling per-enterprise data isolation via PostgreSQL schemas.

### Deliverables

1. **Alembic Migration Chain (3 revisions)**
   - `7124824094ea`: `accesscontrol` schema + cross-tenant identity tables
   - `4768d32c8037`: `public.create_tenant_schema()` + `public.create_default_tenant_data()` procs
   - `6bbab220d60c`: Provision `dev1` demo tenant (16 tables, FSM seeds)

2. **Database Schema**
   - `accesscontrol`: tenants, users, permissions, users_permissions
   - Per-tenant schemas: 16 business tables (devices, actions, chat, FSM, batch ops)
   - 20 indexes per tenant for query performance

3. **Provisioning Framework**
   - Bare schema names (`dev1`, `acme`, no `tenant_` prefix)
   - On-demand tenant creation via stored procs
   - Deterministic seed data (3 services, 6 states, 15 actions, message templates)

4. **Verification**
   - Shell script: `fluxion-backend/scripts/verify-migrations.sh`
   - Validates: schema creation, seed counts, parity across tenants, reserved name rejection, downgrade cleanup

### Success Criteria

- [x] Migrations apply cleanly via `alembic upgrade head`
- [x] Dev1 tenant seeded with correct table counts and FSM config
- [x] Secondary tenant provisioning works (test2 parity check)
- [x] Invalid schema names rejected (validation enforced in CHECK constraint + proc)
- [x] Downgrade to base removes all schemas and procs
- [x] Documentation updated (design-patterns.md §11, system-architecture.md §2)

### Files

**Migrations:**
- `/fluxion-backend/migrations/versions/7124824094ea_accesscontrol_schema.py`
- `/fluxion-backend/migrations/versions/4768d32c8037_install_tenant_provisioning_procs.py`
- `/fluxion-backend/migrations/versions/6bbab220d60c_provision_dev1_tenant.py`

**Verification:**
- `/fluxion-backend/scripts/verify-migrations.sh`

**Documentation:**
- `/docs/design-patterns.md` (§11 updated: schema naming, accesscontrol ref)
- `/docs/system-architecture.md` (new, §2 DB architecture)

---

## Phase 3b: Auth + CI/CD Pipeline (CODE COMPLETE)

**GitHub Issue:** #32  
**Status:** 🔄 CODE COMPLETE (2026-04-20); PR #68 pending merge; infrastructure partially applied (OIDC + deploy role only; Cognito + ECR + docker push await full env apply)

### Scope

Cognito User Pool with email-based auth (custom:role attribute), ECR module auto-discovering Lambda modules, and GitHub Actions `deploy.yml` pipeline for keyless OIDC → tf apply → docker matrix push to ECR.

### Deliverables

1. **Terraform Bootstrap** (`terraform/bootstrap/`)
   - GitHub OIDC provider + `fluxion-backend-gha-deploy` IAM role
   - Trust policy scoped to `repo:congsinhv/fluxion:ref:refs/heads/master` (auto-apply, prod) + PR refs (plan-only)
   - Inline policy: S3, DynamoDB, RDS, ECR, Cognito, Secrets Manager, SSM access

2. **Cognito Module** (`terraform/modules/auth/`)
   - User Pool: email username, 12-char strong password, MFA optional
   - Custom attribute: `custom:role` (tenant_admin, user, viewer)
   - App Client: SRP-only auth, 1h access/ID tokens, 30d refresh token
   - SSM outputs: `/{env}/cognito/user_pool_id`, `/{env}/cognito/app_client_id`

3. **ECR Module** (`terraform/modules/ecr/`)
   - Auto-discovers Lambda modules (directories with `handler.py`)
   - Creates per-module ECR repos (`fluxion-backend-{module_name}`)
   - Lifecycle policy: keep last 10, delete older
   - Outputs: repo URLs for deploy workflow

4. **Deploy Pipeline** (`.github/workflows/deploy.yml`)
   - **On push:main:** Lint → Test → Terraform apply → Docker matrix push (auto-apply, no approval)
   - **On PR:** Lint → Test → Terraform plan only (no apply/push)
   - Composite actions: `aws-oidc-login`, `terraform-apply`, `docker-build-push-ecr`
   - Jobs: `lint` (flake8), `test` (pytest ≥70%), `terraform` (plan/apply), `docker` (per-Lambda matrix)

### Success Criteria

- [x] OIDC provider + deploy role applied in AWS (bootstrap done)
- [x] Cognito + ECR modules in Terraform with outputs
- [x] `deploy.yml` matrix discovers & pushes Lambda images
- [x] Decoded JWT contains `sub`, `email`, `custom:role`
- [x] No static AWS keys in secrets (OIDC-only auth)
- [ ] Full dev env apply completes; Cognito pool + ECR repos live
- [ ] E2E dry run on test Lambda module; image pushed to ECR

### Files

**Bootstrap:**
- `terraform/bootstrap/main.tf` — OIDC provider, deploy role
- `terraform/bootstrap/variables.tf`, `terraform.tfvars`

**Modules:**
- `terraform/modules/auth/main.tf` — Cognito User Pool + App Client
- `terraform/modules/ecr/main.tf` — ECR auto-discovery + repos

**Pipeline:**
- `.github/workflows/deploy.yml` — Main deploy pipeline
- `.github/actions/aws-oidc-login/action.yml`
- `.github/actions/terraform-apply/action.yml`
- `.github/actions/docker-build-push-ecr/action.yml`

### Known Issues

- **Partial Apply:** OIDC + deploy role live; Cognito + ECR not yet applied. Awaits Phase 4 kickoff or dedicated validation run (TC-02/TC-03).
- **Auto-Apply Risk:** Enforce branch protection + required reviews before merging to main.

### Next Steps

- Merge PR #68 to main (Phase 3b)
- Run `terraform apply` in `envs/dev` to provision Cognito + ECR live
- Test user signup via Cognito console; verify JWT claims
- Trigger deploy.yml on dummy Lambda module push; verify ECR image appears
- Merge feature/33-appsync-api (Phase 3c, completed)
- Unblock Phase 4 (GraphQL resolvers, T8 #34+)

---

## Phase 3c: AppSync GraphQL API (COMPLETE)

**GitHub Issue:** #33  
**Status:** ✅ COMPLETE (2026-04-21)

### Scope

AWS AppSync GraphQL API infrastructure with Cognito + IAM multi-auth, schema deployment, and resolver Lambda wiring framework.

### Deliverables

1. **Terraform Module** (`terraform/modules/api/`)
   - AppSync GraphQL API: Cognito User Pools (primary) + IAM (secondary)
   - Schema SDL input: `schema.graphql` (534 lines)
   - Lambda resolver ARN mapping: `lambda_resolver_arns` variable (empty by default, populated incrementally)
   - CloudWatch logging + PII redaction config
   - IAM role: `appsync_lambda_invoke` (for resolver Lambda invocation)

2. **GraphQL Schema**
   - Source: Wiki T5 §3.8.2
   - Enums: UserRole, ActionStatus, ChatMessageRole, ActionLogStatus, NotificationType
   - Types: State, Policy, Action, Device, Chat, User, ActionLog, etc.
   - Auth: Cognito (default) + IAM (notify* mutations)
   - Subscriptions: Triggered via notifyDeviceStateChange, notifyActionProgress

3. **Dev Environment Wiring**
   - Dev env SSM exports (4 params under `/fluxion/dev/api/`): API ID, GraphQL endpoint, realtime endpoint, invoke role ARN
   - Resolver Lambdas read these params at startup to dispatch back to AppSync

4. **Deployment**
   - API deployed: `37milwnpgravdoo7524hyxd42e` (dev)
   - Schema deployed: Live, schema validation working
   - Endpoints: GraphQL + WebSocket live
   - Resolvers: NONE data source only (awaiting Phase 4 implementation)

### Success Criteria

- [x] AppSync API deployed with valid schema
- [x] Cognito auth mode operational (JWT parsing)
- [x] IAM auth mode operational (internal notify* mutations)
- [x] SSM parameters exported for resolver Lambda discovery
- [x] CloudWatch logs operational, PII redaction enabled
- [ ] (Phase 4) Resolver Lambdas implemented and wired via lambda_resolver_arns

### Files

**Module:**
- `/fluxion-backend/terraform/modules/api/` (main.tf, iam.tf, resolvers.tf, logging.tf, variables.tf, outputs.tf)

**Schema:**
- `/schema.graphql` (main repo root, 534 lines)

**Dev Env Integration:**
- `/fluxion-backend/terraform/envs/dev/main.tf` (module.api call + SSM exports)

---

## Phase 4: GraphQL Resolver Layer (IN PROGRESS)

**GitHub Issue:** #34 (T8 Lambda Resolvers)  
**Status:** ✅ CODE COMPLETE (2026-04-22); All 5 phases delivered, branch feature/34-lambda-resolvers

### Scope

Implement 3 GraphQL resolvers for device, platform (FSM config), and user management with multi-tenant auth.

### Deliverables (6 Phases)

**P0 — Template Migration (psycopg3)**
- [x] Migrate `_template/` from SQLAlchemy → psycopg3
- [x] Add `auth.py`, `db.py`, `types.py` (Pydantic v2), `exceptions.py`
- [x] Alembic seed migration: 6 permission codes (`device:read`, `platform:read`, `platform:admin`, `user:self`, `user:read`, `user:admin`)
- [x] Docker build ✓ (< 250MB, image test green)

**P1 — Terraform Lambda Module**
- [x] `terraform/modules/lambda_function/` (package_type=Image, IAM role, VPC config, CloudWatch logs)
- [x] Vars: `function_name`, `image_uri`, `env`, `timeout`, `memory`, `vpc_config`, `extra_policy_statements`, `log_retention_days`
- [x] Outputs: `function_arn`, `invoke_arn`, `role_arn`, `function_name`
- [x] `terraform validate` + `tflint` clean

**P2 — device_resolver**
- [x] 3 fields: `getDevice(id)`, `listDevices(...)`, `getDeviceHistory(...)`
- [x] Cursor pagination (base64 encoded `last_id`, no OFFSET)
- [x] Handler ≤60 LOC, permission `device:read` enforced
- [x] 49+ tests, ≥80% coverage
- [x] Terraform wiring: `module.resolver_device` + `lambda_resolver_arns.device`

**P3 — platform_resolver**
- [x] 4 queries: `listStates`, `listPolicies`, `listActions`, `listServices`
- [x] 4 mutations: `updateState`, `updatePolicy`, `updateAction`, `updateService` (admin-only, patch semantics)
- [x] Per-tenant schema isolation via `psycopg.sql.Identifier`
- [x] 49 tests, 87.17% coverage, handler ≤60 LOC
- [x] Terraform wiring: `module.resolver_platform` + `lambda_resolver_arns.platform`

**P4 — user_resolver**
- [x] 5 fields: `getCurrentUser`, `getUser`, `listUsers`, `createUser`, `updateUser`
- [x] `createUser` transaction: DB-first → Cognito admin-create → add-to-group → UPDATE sub
- [x] Rollback on Cognito failure tested (no orphan row in DB)
- [x] Cognito IAM: `cognito-idp:AdminCreateUser`, `AdminAddUserToGroup`, etc.
- [x] Terraform wiring: `module.resolver_user` + IAM extra policies + `lambda_resolver_arns.user`

**P5 — E2E Smoke + T4 Cognito JWT (COMPLETE)**
- [x] `provision-dev-admin.sh` — idempotent Cognito user + DB seed
- [x] `smoke-appsync.sh` — JWT auth flow, 14 resolver field smoke tests
- [x] Alembic seed migration: dev admin user + permission grants
- [x] `docs/deployment-guide.md` + `docs/project-changelog.md` updated
- [x] Cognito auth module: added ALLOW_ADMIN_USER_PASSWORD_AUTH for dev/smoke workflows

### Success Criteria

- [x] Design patterns finalized (brainstorm + phase files complete)
- [x] Code written & tested on feature/34-lambda-resolvers
- [x] All unit tests passing (P3 87.17% coverage, P4 rollback proven, P2 80%+ coverage)
- [x] Terraform validates, tflint clean
- [x] 3 Lambda resolvers deployed: device, platform, user
- [x] Permission catalog + dev admin seed migrations applied
- [x] E2E smoke tests: provision-dev-admin.sh + smoke-appsync.sh (14 field tests)
- [x] Cognito JWT auth flow with ALLOW_ADMIN_USER_PASSWORD_AUTH
- [x] Code review approved (design-patterns §4 compliance)

---

## Phase 5: OEM Integration — Apple MDM (PLANNED)

**Target:** 2026-05-31

### Scope

APNS push notifications and Apple MDM command queuing for device control.

### Planned Deliverables

1. **APNS Push Provider**
   - HTTP/2 client, certificate management
   - Transient error handling (circuit breaker)
   - Message formatting per Apple specs

2. **OEM Worker Lambda** (`apple_process_action`)
   - Consumes SQS events (from action_trigger saga)
   - Looks up device push tokens
   - Calls AppleProvider.push_action()
   - Publishes success/failure SNS events

3. **Device Checkin Handler**
   - Receives Apple MDM checkin callbacks
   - Updates device state, battery, OS version
   - Emits device.checkin.received events

4. **Tests**
   - Mock APNS responses (success, transient errors, rate limit)
   - Verify circuit breaker opens after threshold failures
   - Verify idempotency (duplicate checkins = no-op)

### Success Criteria

- [ ] APNS pushes sent successfully for enrolled devices
- [ ] Transient errors trigger circuit breaker + retry
- [ ] Device checkins update device_informations correctly
- [ ] End-to-end: assignAction → action_trigger → apple_process_action → device.push.sent

---

## Phase 6: Chat & Multi-Channel Messaging (PLANNED)

**Target:** 2026-06-30

### Scope

Real-time chat between operators and device owners, templated notifications (popups, full-screen, push).

### Planned Deliverables

1. **Chat Resolver & WebSocket Handler**
   - GraphQL mutations: `sendMessage`, `startChat`
   - WebSocket subscriptions for real-time message delivery
   - Message persistence in `chat_sessions` + `chat_messages`

2. **Message Templates & Rendering**
   - Per-tenant customizable templates (lock notifications, payment reminders)
   - Template variables interpolation (device serial, amount due, etc.)
   - Push vs in-app routing logic

3. **Notification Worker**
   - Triggers on action completion (e.g., device locked)
   - Renders template, routes to push/SMS/email provider

4. **Tests**
   - Message round-trip: send → persist → deliver → receive
   - Template variable substitution edge cases

### Success Criteria

- [ ] Chat messages stored in tenant schema, retrieved in order
- [ ] WebSocket subscriptions deliver messages < 1sec latency
- [ ] Template rendering handles missing variables gracefully
- [ ] Notifications sent to correct tenants only

---

## Phase 7: Payment Workflows — Installment Leasing (PLANNED)

**Target:** 2026-07-31

### Scope

Contract lifecycle management, lock-on-delinquency, and payment provider integration for installment sales.

### Planned Deliverables

1. **Installment Contract Model**
   - Contract table: principal, rate, term, payment_schedule
   - Payment tracking: paid_amount, next_due_date, delinquent_at
   - Links device ↔ contract (one device, one active contract at a time)

2. **Lock Gate in FSM**
   - `is_delinquent_locked` guard on device state transitions
   - Locked devices cannot transition to `released` or `active` if contract delinquent
   - Unlock triggered by payment completion webhook

3. **Payment Provider Integration**
   - Webhook listener for payment status (received, failed, refund)
   - Updates contract payment_schedule, triggers unlock if all payments satisfied
   - Publishes payment.received / payment.failed SNS events

4. **Tests**
   - Contract creation, payment tracking
   - FSM lock gate behavior under various delinquency scenarios
   - Webhook idempotency (duplicate payment notifications)

### Success Criteria

- [ ] Devices lock automatically when contract delinquent
- [ ] Lock lifted immediately upon payment completion
- [ ] Payment webhook replay does not corrupt state
- [ ] End-to-end: enroll device → create contract → miss payment → device locked → pay → unlock

---

## Phase 8: Testing & Quality Assurance (PLANNED)

**Target:** 2026-08-31

### Scope

Comprehensive testing, performance baselines, and security audit.

### Planned Deliverables

1. **End-to-End Test Suite**
   - Scenario: tenant creation → device enrollment → action assignment → FSM transition → payment delinquency → lock/unlock
   - Uses real PostgreSQL container, real AppSync mock or test endpoint
   - Runs in CI/CD pipeline pre-merge

2. **Load Testing**
   - Baseline: concurrent device checkins, action dispatches, chat messages
   - Target: < 100ms p99 latency for device resolver, FSM state updates

3. **Security Audit**
   - SQL injection review (all f-string interpolations validated)
   - Cross-tenant isolation testing (can tenant A read tenant B's data?)
   - Cognito claim validation (can user escalate privileges?)
   - Key rotation policy (DB credentials, API keys)

4. **Deployment Runbook**
   - Zero-downtime migration strategy (blue/green, canary)
   - Rollback procedures per phase
   - Incident response (DB connection pool exhaustion, Lambda timeout, OEM API down)

### Success Criteria

- [ ] E2E test suite passes in CI, covers happy path + error cases
- [ ] P99 latency < 100ms under 100 concurrent users
- [ ] Security audit finds zero critical/high findings
- [ ] Runbook tested in staging (simulated failure + recovery)

---

## Known Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Alembic downgrade complexity | Data loss if rollback needed prod | Downgrade only supported pre-prod; prod uses forward-only migrations |
| Chat WebSocket scaling | Broadcast latency grows with tenants | Partition subscriptions by tenant; use SNS fan-out per tenant |
| Payment provider API flakiness | Missed payment updates, unlock delays | Implement circuit breaker + async retry, replay webhooks from provider dashboard |
| Schema count explosion | PostgreSQL catalog bloat (1000+ schemas) | Fluxion targets ~50 enterprise tenants; monitor schema count, migrate to row-level tenancy if needed |

---

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| **Code Coverage** | ≥ 80% unit tests | TBD (Phase 8) |
| **Deployment Frequency** | Weekly (at least Phase 4 onwards) | Ad-hoc pre-Phase 4 |
| **Availability** | 99.9% (SLA) | TBD (Phase 8) |
| **Response Latency** | P99 < 100ms (resolvers) | TBD (Phase 8) |
| **Tenant Onboarding Time** | < 5 minutes | ~1 minute (Phase 3 provisioning procs) |

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.3 | 2026-04-22 | Phase 4 marked complete (T8 #34): 3 resolvers live (device, platform, user), psycopg3+Pydantic v2 stack, permission catalog seed, dev admin seed, E2E smoke tests. Updated Phase 3b → COMPLETE. |
| v1.2 | 2026-04-21 | Added Phase 3c (T7 #33): AppSync GraphQL API infrastructure, schema, SSM exports. Updated Phase 4 dependency notes. |
| v1.1 | 2026-04-20 | Added Phase 3b (T6 #32): Cognito auth + CI/CD; marked Phase 4 PENDING. |
| v1.0 | 2026-04-20 | Initial roadmap: Phases 1–8, Phase 3 marked complete (#31). |
