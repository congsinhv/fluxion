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
| **Phase 4** | GraphQL Resolver Layer | 🔄 IN PROGRESS | 2026-05-10 | Device resolver, action resolver, FSM enforcement |
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

## Phase 4: GraphQL Resolver Layer (IN PROGRESS)

**Target:** 2026-05-10

### Scope

Implement core GraphQL resolvers for device management, action assignment, and FSM state transitions.

### Planned Deliverables

1. **Device Resolver Lambda**
   - `getDevice(id: UUID!): Device`
   - `listDevices(limit: Int, offset: Int): [Device!]!`
   - `enrollDevice(serial: String, platform: Platform): Device`

2. **Action Resolver Lambda**
   - `assignAction(deviceIds: [UUID!]!, action: Action!): ActionLog`
   - FSM policy validation (guard evaluation in SQL)
   - Publishes `action.assigned` SNS event

3. **Database Repositories**
   - `DeviceRepository`: CRUD ops with tenant schema binding
   - `ActionRepository`: State transition log, policy enforcement
   - Pydantic DTOs for input/output validation

4. **Tests**
   - Unit tests: repository layer, FSM guards
   - Integration tests: resolver → DB → FSM → event chain

### Success Criteria

- [ ] Resolvers parse & authorize Cognito claims
- [ ] Repositories pass tenant_schema to all queries
- [ ] FSM state transitions enforced via SQL policies
- [ ] Idempotency keys dedup retried actions
- [ ] All tests passing (unit + integration)
- [ ] Code review approved (design-patterns §4 compliance)

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
| v1.0 | 2026-04-20 | Initial roadmap: Phases 1–8, Phase 3 marked complete (#31). |
