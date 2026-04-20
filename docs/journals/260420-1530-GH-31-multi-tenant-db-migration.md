# T6 Multi-Tenant DB Migration Shipped

**Date**: 2026-04-20 15:30
**Severity**: High
**Component**: Database schema, migrations, access control
**Status**: Resolved

## What Happened

Shipped PR #67 / issue #31: Alembic raw-SQL migration chain deploying T6 multi-tenant DB schema to Postgres 16. Migration installs PL/pgSQL procs in `public` schema that own per-tenant DDL + seeding. Bare tenant names (`dev1`, not `tenant_dev1`). 16 per-tenant business tables per wiki ER. Cross-tenant identity (tenants/users/permissions) lives in `accesscontrol` schema. Verification script covers full chain, downgrade path, parity checks, and reserved-name rejection — all GREEN.

## The Brutal Truth

Implementation initially diverged from wiki spec. User caught misalignment on review. Embarrassing: we didn't validate against the authoritative source before shipping. Had to soft-reset 5 local commits into 4 clean ones. The rework itself was clean, but the sloppiness stung — this is foundational infrastructure. One query bug (adjacent string literals in SQL dollar-quoting) forced a second debugging cycle. Low confidence before final test run.

## Technical Details

**Schema structure:**
- `accesscontrol` (4 tables: tenants, users, permissions, users_permissions)
- Per-tenant schemas (`dev1`, `dev2`, etc.): 16 tables each (4 FSM core + 3 device services + messaging + analytics)
- DeviceFSM: 6 states, 6 policies, 15 actions (not 12), 1 brand, 1 TAC, 3 message templates
- `chat_sessions.user_id` is BIGINT — no cross-schema FK; app-layer validates

**Migration approach:**
- 3 Alembic revisions: accesscontrol schema → procs (DDL + seed) → dev1 tenant provisioning
- PL/pgSQL procs use dollar-quoting (`$proc$`, `$ddl$`, `$seed$`, `$q$`) to escape nested quotes
- Bug: `'CREATE INDEX...' "WHERE..."'` parsed as two SQL tokens; fixed with `$q$...$q$` wrapper

**Verification:**
- `scripts/verify-migrations.sh`: forward chain, downgrade, secondary tenant parity, invalid/reserved name rejection
- Postgres 16 validation passed

## What We Tried

1. Initial impl → user review → caught wiki divergence (user count, action count, brand count, schema placement)
2. Soft-reset 5 commits to consolidate → cleaned up local history
3. Alembic revision IDs: first attempt `0001/0002/0003` → user redirected to auto-hex (standard)
4. SQL string concatenation bug in proc def → tried adjacent literals → failed → switched to dollar-quoting wrapper

## Root Cause Analysis

**Wiki divergence:** No pre-implementation verification step. We read the spec, coded locally, and only validated on user review. Should have diff'd generated schema against wiki ER before commit.

**SQL parsing gotcha:** Python f-strings + raw SQL don't play well with quote mixing. Adjacent string literals in SQL context became multiple tokens. The fix (dollar-quoting) is solid, but we didn't test the edge case in isolation.

**Revision ID confusion:** We picked numeric IDs because it felt natural; Alembic's auto-hex is cleaner for reproducibility across branches.

## Lessons Learned

1. **Spec-first validation:** Before shipping foundational schema, generate the schema and diff it line-by-line against wiki ER. Don't trust memory.
2. **Test edge cases early:** SQL quoting nested in f-strings needs isolated validation before integration.
3. **Schema reviews are slow:** Accept it. Multi-tenant setup is high-stakes. User review caught real issues we missed.
4. **Git history matters:** Local commit count exploded because we reworked incrementally. Soft-reset before final push keeps history clean.

## Next Steps

1. **RDS dev parity:** Test full chain on actual RDS Postgres 16 (pending dev DB access)
2. **Issue #31 body:** Update table count from 17 to 20 (4 accesscontrol + 16 per-tenant)
3. **pgTAP suite:** Replace shell assertions in verification script with proper SQL unit tests (follow-up ticket)
4. **Cross-schema FK strategy:** Decide whether to add FK constraints at the application level or via triggers for deleted tenant cleanup
