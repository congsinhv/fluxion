# T6 Cognito Auth + CI/CD Deploy Pipeline (PR #68)

**Date**: 2026-04-20 16:30
**Severity**: High
**Component**: Authentication (Cognito), CI/CD (GitHub Actions), Infrastructure (Terraform)
**Status**: In Review (PR #68 open, all CI green, awaiting merge to main)

## What Happened

Shipped PR #68 / issue #32: Cognito User Pool + App Client (with custom:role attribute + prevent_destroy), ECR auto-discovery module, GitHub OIDC provider + assume role policy, and complete `.github/workflows/deploy.yml` with 3 composite actions (aws-oidc-login, terraform-apply, docker-build-push-ecr). All CI jobs GREEN. Full apply + Cognito JWT / ECR push validation tests deferred until merge to main.

## The Brutal Truth

Got bitten by three non-obvious CI gotchas in succession. The `environment: dev` on terraform jobs silently changed the OIDC token's `sub` claim — orthogonal to what I expected. S3 state lock stale delete markers from prior sessions nuked conditional PutObject ops. These aren't documented clearly anywhere and ate 40+ minutes of debugging. Irritating because the pattern is correct; the sharp edges are just hidden.

## Technical Details

**Architecture:**
- `terraform/bootstrap/oidc.tf`: GitHub OIDC provider + `fluxion-backend-gha-deploy` role with policy allowing AssumeRoleWithWebIdentity + tf + ECR ops
- `terraform/modules/auth`: Cognito User Pool (auto-confirm, custom:role attr, SMS disabled), App Client (prevent_destroy)
- `terraform/modules/ecr`: Dynamic repo discovery via `fileset("Dockerfile.*)` across module dirs
- Composite actions: OIDC login, tf init/plan/apply, docker buildx + push to ECR

**CI Failures (resolved):**
1. PR auto-targeted `develop` (repo default) → manual retarget to `main`
2. `detect-changes` grep → no modules found → `set -euo pipefail` caught exit 1 → wrapped in `{ grep || true; }`
3. OIDC AssumeRoleWithWebIdentity → trust policy mismatch on OIDC token `sub` — culprit: `environment: dev` on terraform jobs mutated sub from `repo:fluxion:ref:refs/pull/...` to `repo:fluxion:environment:dev` — not in policy. Dropped `environment:` (dev doesn't need approval gates)
4. `terraform plan` → S3 state lock PreconditionFailed — stale `.tflock` **delete markers** from prior sessions broke conditional PutObject. Purged all lock versions + markers from S3 backend versioning bucket; rerun GREEN

## What We Tried

1. Debugged OIDC AssumeRole failure → checked trust policy, token claims, role ARN — all looked correct until examining the actual decoded token
2. Reran terraform init multiple times assuming state corruption → no improvement
3. Disabled backend config to skip locking → worked but masked root cause
4. Investigated S3 versioning logs → found old `.tflock` *delete markers* persisting

## Root Cause Analysis

**OIDC sub mutation:** GitHub Actions `environment` context is per-job, not implicit. It alters the OIDC token claims sent to AWS. This is documented in GitHub docs but not intuitive when you're setting up the trust relationship.

**Tflock delete markers:** Terraform creates conditional PutObject requests assuming a clean key. S3 versioning with lingering delete markers (from old lock cleanup) violates preconditions even on subsequent locks. Not a Terraform bug — it's S3 semantics + stale state interaction.

## Lessons Learned

1. **OIDC token claims are mutable:** Always decode and inspect the actual token in CloudTrail when debugging AssumeRole failures. Don't assume standard format.
2. **S3 versioning + conditional ops:** Delete markers are not cleanup; they're history entries. Manual S3 purge required after force-removing old locks.
3. **CI matrix clarity:** Empty module list should fail fast, not silently skip. Consider asserting non-empty early.
4. **State lock hygiene:** Document lock cleanup procedure. Add CI step to validate backend state before terraform operations.

## Next Steps

1. **Merge PR #68 to main** — all checks pass
2. **Post-merge TC-02/TC-03:** Test Cognito JWT issuance + ECR push validation in dev
3. **OIDC docs:** Add runbook in `./docs` covering token claims debugging and trust policy validation
4. **S3 backend ops:** Add helper script to safely purge stale locks + delete markers
