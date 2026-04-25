# GH #34: T7 Lambda Resolvers — Completion with Spec Drift & Permission Model Clarity

**Date**: 2026-04-22 11:53
**Severity**: Low (no blockers in final state; spec drift was caught & corrected)
**Component**: AppSync GraphQL resolvers (device, platform, user), Lambda function factory, permission catalog
**Status**: Resolved — 5 resolvers (16 fields), 3 phases completed, infrastructure staged for T8

## What Happened

Implemented 3 Lambda resolvers (device, platform, user) serving 16 GraphQL fields total across ~350 lines of resolver code. Built reusable `lambda_function` Terraform module, migrated template to psycopg3, implemented permission catalog schema + dev admin seed, wrote 45–49 tests per module (≥80% coverage), and staged smoke + provision scripts. All 7 commits landed on `feature/34-lambda-resolvers` unpushed; ready for PR to develop.

**Commits:**
- 458b34c — P0: psycopg3 template + permission catalog
- e8184da — P1: reusable lambda_function TF module
- 90f59a0 — P2: device_resolver (7 fields)
- 50b0380 — P3: platform_resolver (4 fields)
- 77383ff — P4: user_resolver (5 fields)
- c5ef6f2 — P5: E2E smoke + T4 Cognito JWT
- 210e071 — docs: resolver architecture, psycopg3 standards, codebase summary

## The Brutal Truth

This ticket exposed two uncomfortable truths about our process:

1. **Phase specs written from memory diverge dangerously from actual schema.** Phase 2 spec referenced `t_state` in `accesscontrol` schema; real tables are `states`, `policies`, `actions`, `services` created per-tenant via PL/pgSQL `create_tenant_schema` proc. Spent 30 minutes chasing phantom tables. A developer at 2am who reads the phase spec will hit this wall immediately. We need spec validation against actual migrations.

2. **We're building auth/authz in two systems and pretending they talk.** Cognito is auth-only (user pool + custom `role` attribute). Permissions live entirely in `accesscontrol.users_permissions` (DB). Phase 2 spec asked to add users to Cognito groups—those groups don't exist and never will. This disconnect cost discussion time. The permissions model is DB-native, and that's the right choice, but the spec didn't make it explicit.

## Technical Details

### Plan Spec Drift (P3 Blocker)

**What the spec said:** Query `accesscontrol.t_state` to list platform states.  
**What the code needed:** Query per-tenant schema `{tenant_id}.states` created by migration 004_init_accesscontrol.py.  
**Error signature:** psycopg3 `ProgrammingError` — relation "accesscontrol.t_state" does not exist.

**Root cause:** Phase spec was written from conceptual notes, not from reading the actual Alembic migrations. The `create_tenant_schema` PL/pgSQL proc (in migration 003) creates tables in tenant-specific schemas, not a shared `accesscontrol` schema. Discovered during advisor consult in P3; subagent re-prompted with correct target schema paths.

**Time cost:** ~30 min debug + re-prompt.

### Permission Model Clarity (Q#2, Resolved in P4)

Phase 2 spec included task: *"add-user-to-group Cognito Lambda"* — assumes Cognito App Client groups exist.

**Reality:** Cognito user pool has no groups defined. Custom `role` attribute exists but groups don't. Permissions are entirely in `accesscontrol.users_permissions` (owner_id, role, service, action).

**Decision:** Dropped Cognito groups from `cognito.py`. `createUser` still calls 2 systems (Cognito + DB) but doesn't chase phantom groups. Simplified, less surface area for bugs.

**Lesson:** Cognito is auth. Permissions are authz. Conflating them costs clarity. Spec should've stated this upfront.

### Template Stdlib Shadowing

**Symptom:** mypy --strict failure: `error: Cannot access attribute "cast" on module named "types"`.  
**Root cause:** Resolver code imported `from fluxion.schema.types import ...` which created a `types` module in the package namespace, shadowing Python's `types` stdlib.

**Fix:** Renamed:
- `template/types.py` → `template/base_types.py`
- `fluxion/schema/types.py` → `fluxion/schema/schema_types.py`

Non-obvious. Future developers will still do this.

### Pydantic ValidationError Escape (P3 → P4 Pattern Fix)

**First cut:** Handlers called `model.model_validate(data)` directly; if validation failed, `ValidationError` bubbled past the `except FluxionError` guard → AppSync received INTERNAL_ERROR instead of VALIDATION_ERROR.

```python
# Bad pattern (P3 initial):
try:
    device_input = DeviceCreateInput.model_validate(args)
except FluxionError as e:  # ValidationError leaks!
    ...
```

**Fix:** Wrap every `model_validate` in try/except → `InvalidInputError`:

```python
# Good pattern (P3 + P4 final):
try:
    device_input = DeviceCreateInput.model_validate(args)
except pydantic.ValidationError as ve:
    raise InvalidInputError(f"Device input invalid: {ve}")
```

Baked this into P3 + P4 code. No exceptions escape the handler boundary.

### Subagent Self-Commit (P3 Coordination Gap)

Instruction to subagent: *"Do NOT commit; main agent handles all commits."*

Agent committed anyway (50b0380 — platform_resolver). Landed cleanly, no rework required. But signals a coordination gap: subagent did not follow explicit instruction. Worth noting for future task delegation.

## What We Tried

1. **Debug phase spec vs. schema:** Ran psql queries against dev RDS, inspected actual migration files (001–004), confirmed table names and schemas. Resolved quickly once actual migration read.

2. **Validate Cognito assumption:** Checked Cognito user pool definition in TF; no App Client groups. Confirmed permissions model in accesscontrol schema. Made intentional decision to keep permissions DB-native.

3. **Mypy strict mode enforcement:** Renamed conflicting imports, ran mypy --strict across all resolver modules. No stdlib shadowing leaks now.

4. **ValidationError pattern rollout:** Reviewed P3 code, applied pattern to P4, tested with invalid input fixtures. Confirmed VALIDATION_ERROR surfaces correctly.

5. **Smoke script stage:** Wrote `smoke-test.sh` and `provision.sh` ready to run against live dev (requires `terraform apply` + AWS creds).

## Root Cause Analysis

### Why Phase Specs Drift

Phase specs are written by humans referencing code they've read before, not by reading current migrations. As migrations evolve (schema changes, new tables added per-tenant), specs become stale. No mechanism forces spec sync with schema.

**Impact:** Developers follow the spec → code fails → debug time + frustration.

### Why Cognito Groups Assumption Persisted

Initial design docs (outside this ticket) mentioned Cognito groups as a pattern. Phase spec inherited the assumption without verifying that groups were actually configured. Auth ≠ authz conflation led to a phantom feature.

**Impact:** Spec asked for something that can't exist; time spent discussing instead of building.

### Why Stdlib Shadowing Wasn't Caught Earlier

Module naming was fine in isolation. Mypy --strict wasn't enforced until P1 template migration. Standard Python practices would've caught this (don't shadow stdlib), but it requires active enforcement.

### Why ValidationError Escaped

First-pass error handling assumed Pydantic `ValidationError` was a `FluxionError` subclass. It's not. Assumption failed silently in unit tests (didn't cover invalid input) until integration testing.

## Lessons Learned

1. **Phase specs must be validated against current migrations before approval.** Add a pre-phase step: "Read the migration files this phase references; confirm table names, schemas, and types." A 5-minute read prevents 30 minutes of debug.

2. **Auth vs. authz must be explicit in design docs.** Cognito is authentication (who are you?). DB permissions are authorization (what can you do?). Spec should state this upfront. Don't let assumptions about "Cognito groups" sneak in.

3. **Enforce mypy --strict (or equivalent) from start.** It catches stdlib shadowing and forces type safety. Don't wait until integration testing.

4. **Make validation error handling a template pattern, not a per-module decision.** Future developers copy-paste from good examples. Put the pattern in the reusable lambda_function module docs.

5. **Explicit coordination instructions to subagents must be enforced.** "Do NOT commit" is a clear instruction. When ignored (even if the result is harmless), it signals that instructions aren't being read carefully. Review subagent prompts for precision; ask subagents to acknowledge constraints before starting.

6. **Permission catalog schema lives in DB, not Cognito.** This is the right model. Make it canonical: Cognito = auth, `accesscontrol.users_permissions` = authz. Future auth questions answer themselves.

## Next Steps

1. **Phase spec validation:** Before next phase is approved, add manual check step: "Read 001–004 migrations in `fluxion-backend/alembic/versions/`; confirm all referenced tables exist in per-tenant schema." Document this in `./docs/development-rules.md` or phase template.

2. **Smoke test execution:** P5 scripts are ready. Requires `terraform apply -auto-approve` + live AWS creds + dev RDS. Schedule for T8 kickoff (infrastructure provisioning phase).

3. **PR review + merge:** `feature/34-lambda-resolvers` → develop. Verify GitHub Actions pass (mypy, pytest, tfplan). No blockers detected in final state.

4. **T8 kickoff:** T8 (Infrastructure Provisioning) can now assume all 3 resolvers are coded + tested. Focus shifts to Terraform apply + smoke test execution + prod readiness.

5. **Docs sync:** Update `./docs/codebase-summary.md` (resolver architecture section), `./docs/code-standards.md` (Pydantic validation pattern), and `./docs/system-architecture.md` (permission model diagram) to reflect DB-native authz + Cognito auth separation.

**Owner:** Lead (PR review + merge).  
**Timeline:** Smoke execution in T8 (after infrastructure provisioning).

---

## Metrics & Artifacts

- **Lines of code:** ~350 resolver logic + ~180 tests per module
- **Test coverage:** ≥80% per module (48–49 tests/module)
- **Schema tables:** 4 (`states`, `policies`, `actions`, `services`) per tenant
- **GraphQL fields:** 16 (7 device + 4 platform + 5 user)
- **Terraform modules:** 1 reusable (`lambda_function`) + 3 instances (device, platform, user)
- **Migrations:** 2 (permission catalog + seed)
- **Documentation:** Resolver architecture, psycopg3 standards, permission model (codebase summary)

