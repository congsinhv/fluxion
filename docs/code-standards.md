# Code Standards

> **Version:** v1.0
> **Audience:** Fluxion contributors (human + LLM) and reviewers.
> **Authority:** Source of truth. Tooling configs (pre-commit, CI) enforce these rules in follow-up tickets.
> **Principles:** YAGNI — You Aren't Gonna Need It. KISS — Keep It Simple, Stupid. DRY — Don't Repeat Yourself.

---

## 1. Introduction

Fluxion is an AWS serverless MDM platform targeting the Vietnamese installment / rental phone market. Code must be shippable by a solo developer, reviewable by a thesis committee, and extensible once contributors onboard.

This document declares rules. Enforcement (pre-commit hooks, CI gates) is a follow-up ticket. Until then, rules are **self-enforced** via a PR review checklist that cites the section numbers below.

**When in doubt:** prefer the simpler option. If a rule blocks delivery, open an issue to adjust the doc — do not silently break it.

---

## 2. General Rules

### 2.1 File Naming

| Language | Convention | Example | Note |
|----------|------------|---------|------|
| Python (modules) | `snake_case.py` | `device_repository.py` | PEP 8 mandatory; importable modules must be snake_case. |
| Python (Lambda package dirs) | `snake_case/` | `device_resolver/`, `action_trigger/` | Must match handler import path. AWS Lambda resolves `action_trigger.handler` → imports `action_trigger/handler.py`. Hyphens break imports. |
| TypeScript (components) | `PascalCase.tsx` | `DeviceTable.tsx` | React / TypeScript official standard. |
| TypeScript (hooks) | `kebab-case.ts` with `use-` prefix | `use-device-list.ts` | 2026 consensus (TanStack, shadcn/ui). |
| TypeScript (utilities, services) | `kebab-case.ts` | `format-date.ts`, `api-client.ts` | 2026 consensus. |
| TypeScript (types, DTOs) | `kebab-case.ts` | `device-types.ts`, `api-responses.ts` | Consistency with utilities; types exported within are PascalCase. |
| TypeScript (CSS Modules) | `kebab-case.module.css` | `device-table.module.css` | Matches component (kebab variant). Tailwind utility-first preferred; CSS Modules only when scoped styles needed. |
| TypeScript (config, constants) | `kebab-case.ts` file; `UPPER_SNAKE_CASE` exports | `device-constants.ts` exports `DEVICE_STATES` | Ecosystem standard (Vite, Next.js config files). |
| TypeScript (tests) | `PascalCase.test.tsx` or `kebab-case.test.ts` | `DeviceTable.test.tsx`, `format-date.test.ts` | Matches the file under test. |
| Terraform modules | `kebab-case/` | `terraform/modules/compute/` | HashiCorp convention. |
| Shell scripts | `kebab-case.sh` | `deploy-stack.sh` | POSIX convention. |
| SQL / Alembic migrations | `NNNN_snake_case.py` | `0042_add_tacs_table.py` | Alembic auto-generates this pattern; keep as-is. |

**Descriptive > short.** `device_enrollment_handler.py` is better than `handler.py`.

**Path aliases (TypeScript):** configure `@/*` → `src/*` in both `tsconfig.json` and `vite.config.ts`. Prefer absolute imports via alias over relative paths beyond two levels (`../../../` is a smell).

**Feature-based organization (recommended):** group by business feature (`features/devices/`, `features/actions/`) rather than purely by technical layer (`components/`, `utils/` at root). Improves colocation and discoverability. See [module-structure.md](module-structure.md) for layout details.

**Evidence sources:** [PEP 8](https://peps.python.org/pep-0008/), [AWS Lambda Python handler docs](https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html), [TanStack Router naming](https://tanstack.com/router/latest/docs/framework/react/routing/file-naming-conventions), [shadcn/ui](https://ui.shadcn.com/docs/installation/manual), [Alembic naming](https://alembic.sqlalchemy.org/en/latest/naming.html). Research notes: [researcher-260419-1545-file-naming-conventions-2026.md](../plans/reports/researcher-260419-1545-file-naming-conventions-2026.md).

### 2.2 File Size

- **Hard limit:** 200 LOC per source file (excluding blank lines, docstrings, imports).
- **Lambda `handler.py` entry:** ≤ 50 LOC — wire only, delegate to business logic modules.
- **React component:** ≤ 150 LOC.
- **Terraform `main.tf`:** ≤ 300 LOC (split via sub-modules if over).

When over limit, split by concern (queries vs mutations, presentational vs container) — see [module-structure.md](module-structure.md).

### 2.3 Comments

- **Why, not what.** Code already says what; comment explains why.
- **No AI references** in comments or commit messages.
- **No `TODO` without issue link.** `# TODO(#123): handle APNS rate limit` ✅. `# TODO: fix later` ❌.
- **No commented-out code.** Delete it. Git history preserves it.
- **Docstrings for public functions** (see §3.2).

**Do:**

```python
# APNS returns 410 for tokens revoked by iOS. Treat as permanent, not transient.
if response.status == 410:
    repository.mark_push_token_invalid(device_id)
```

**Don't:**

```python
# Check if status is 410
if response.status == 410:  # mark invalid
    repository.mark_push_token_invalid(device_id)
```

### 2.4 Error Handling

- **Validate at boundaries only** (handler entry, external API responses). Trust internal code.
- **No bare `except`** (Python) or empty `catch` (TS). Always catch specific types.
- **Re-raise with context**, don't swallow.
- **Structured errors:** domain errors extend a base class (`FluxionError`), map to HTTP / GraphQL errors at boundary.

**Do:**

```python
try:
    device = repository.get_device(device_id)
except psycopg2.OperationalError as e:
    logger.exception("db.connection_lost", extra={"device_id": device_id})
    raise TransientError("Database unavailable") from e
```

**Don't:**

```python
try:
    device = repository.get_device(device_id)
except Exception:
    return None  # hides bugs, caller can't tell failure from missing
```

### 2.5 Logging

- **Structured JSON only.** Use `python-json-logger` / `pino`.
- **Event naming:** `<entity>.<action>.<outcome>` — `device.enrolled`, `action.dispatched`, `apns.push_failed`.
- **No PII in logs.** Device serial OK; customer name / phone number NOT OK.
- **Correlation ID propagation:** pass `correlation_id` through SNS/SQS message attributes, include in every log line.

**Do:**

```python
logger.info(
    "device.enrolled",
    extra={"device_id": d.id, "tenant_id": t.id, "correlation_id": ctx.correlation_id},
)
```

**Don't:**

```python
print(f"device {d.id} enrolled for customer {customer.full_name}")  # PII leak + unstructured
```

### 2.6 Security

- **No secrets in code or git history.** Use AWS Secrets Manager / Parameter Store. `.env` files in `.gitignore`.
- **Parameterized SQL only.** See §5.1.
- **Input validation at handler boundary** via Pydantic / Zod. Reject unknown fields strictly.
- **Least privilege IAM.** Lambda role grants only actions needed — no `*` wildcard on production.
- **No `eval` / `exec`** on user input. Ever.
- **OWASP Top 10 awareness** — each PR touching auth / input / output must cite threat model notes in description.

---

## 3. Python Rules

**Target runtime:** Python 3.12 on AWS Lambda (container image).
**Formatter/Linter:** [Ruff](https://docs.astral.sh/ruff/) — single tool replacing Black + isort + flake8 + pylint (≈20× faster, 2026 ecosystem standard). Commands: `ruff format` + `ruff check --select ALL` (justified `# noqa: <RULE>` with reason).
**Type checker:** `mypy --strict`.

### 3.1 Type Hints

- **100% coverage** — every parameter, return value, class attribute.
- Use `from __future__ import annotations` at top of every file (defers evaluation, allows forward refs).
- Prefer built-in generics (`list[str]`, `dict[str, int]`) over `typing.List` / `typing.Dict`.
- Use `Literal`, `TypedDict`, `NotRequired` where applicable.
- For SQLAlchemy, prefer 2.0 style types (`Engine`, `Connection` from `sqlalchemy.engine`; `Result` for return values) — not legacy `engine.Engine` module-path syntax.

**Do:**

```python
from __future__ import annotations

def enroll_device(tenant_id: str, serial: str) -> Device:
    ...
```

**Don't:**

```python
def enroll_device(tenant_id, serial):  # no hints
    ...
```

### 3.2 Docstrings

- **Mandatory on public functions / classes** (no leading underscore).
- **Google style.** Include `Args`, `Returns`, `Raises` sections.
- **First line:** imperative mood, ends with period, ≤ 80 chars.

**Do:**

```python
def enroll_device(tenant_id: str, serial: str) -> Device:
    """Register a new device in the `registered` state for a tenant.

    Args:
        tenant_id: UUID of the owning tenant.
        serial: Device serial number (IMEI for Apple).

    Returns:
        Device DTO with generated id and initial state.

    Raises:
        ConflictError: Serial already registered for this tenant.
    """
```

### 3.3 Error Handling Specifics

- Define domain errors in `errors.py` per module, extending `FluxionError`.
- At handler boundary, map to AppSync error response with stable error codes.
- Never raise `Exception` directly; always a specific subclass.

### 3.4 Pydantic at Boundaries

- **Every handler entry** parses `event["arguments"]` into a Pydantic model.
- **Every repository return** is a Pydantic DTO, not a raw cursor row.
- **Every external API response** parsed through Pydantic before use.
- Use `model_config = ConfigDict(extra="forbid")` — reject unknown fields.

**Do:**

```python
class EnrollDeviceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    serial: str
    platform: Platform

def handler(event, context):
    args = EnrollDeviceInput.model_validate(event["arguments"])
    ...
```

### 3.5 Imports

- **Absolute imports only, no `src.` prefix** — `from config import logger`, not `from src.config import logger` and not relative `from .config import ...`.
  - Rationale: Lambda runtime copies `src/` contents flat into `LAMBDA_TASK_ROOT`. Tests mirror this via `pyproject.toml` → `[tool.pytest.ini_options] pythonpath = ["src"]`. Handlers import the same way in both contexts.
- **Grouped** (PEP 8): stdlib → third-party → local, blank line between groups.
- **No wildcard imports** (`from x import *`).
- **No circular deps** — enforce via `import-linter` when tooling ticket lands.

### 3.6 Async

- Prefer `aioboto3` for I/O-bound Lambda (SNS publish, S3 get).
- Don't mix sync/async in one handler — pick one.
- Use `asyncio.gather` with `return_exceptions=True` for fan-out, inspect results.

### 3.7 Strict Target

| Tool | Command | Must Pass |
|------|---------|-----------|
| Formatter | `ruff format --check .` | Yes |
| Linter | `ruff check --select ALL .` | Yes (w/ justified `noqa`) |
| Type checker | `mypy --strict src/` | Yes |
| Security | `bandit -r src/` | No high-severity findings |

---

## 4. TypeScript Rules

**Target runtime:** Node 20+ (frontend build), React 19, Vite.
**Formatter:** Prettier (default config, 100-char line).
**Linter:** `eslint:recommended` + `@typescript-eslint/strict` + `eslint-plugin-react-hooks`.
**Type checker:** `tsc --strict` (strictest — see §4.1).

### 4.1 Strict Mode

`tsconfig.json` must include:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true
  }
}
```

### 4.2 No `any`, No `!`

- **No `any`** — use `unknown` and narrow.
- **No `!` non-null assertion** outside tests. Use type guards or explicit null checks.
- **No `@ts-ignore`**, `@ts-expect-error` only with inline comment explaining why.

**Do:**

```ts
const device = devices.find(d => d.id === id);
if (!device) throw new NotFoundError(`device ${id}`);
// TS knows device is Device here
```

**Don't:**

```ts
const device = devices.find(d => d.id === id)!;  // lies to compiler
```

### 4.3 Explicit Return Types

- **Exported functions / hooks** must have explicit return types.
- Internal one-liners can infer.

**Do:**

```ts
export function useDeviceList(tenantId: string): DeviceListResult {
    ...
}
```

### 4.4 Interface over Type

- Prefer `interface` for object shapes (extendability, better error messages).
- Use `type` for unions, tuples, mapped types.

### 4.5 Imports and Path Alias

- Configure `@/*` alias → `src/*` in `tsconfig.json` + Vite.
- Prefer absolute imports via alias over deep relative (`../../../`).
- Group: external → aliased → relative, blank line between.

### 4.6 Strict Target

| Tool | Command | Must Pass |
|------|---------|-----------|
| Formatter | `prettier --check .` | Yes |
| Linter | `eslint . --max-warnings 0` | Yes |
| Type checker | `tsc --noEmit` | Yes |

---

## 5. SQL Rules

**Target DB:** PostgreSQL 15+.
**Migration tool:** Alembic (via psycopg2-binary).

### 5.1 Parameterized Queries Only

- **Never** string-concat / f-string user input into SQL.
- Fluxion uses **SQLAlchemy 2.0** with `text()` + named params (`:name` style) everywhere.
- Tenant schema names are the single exception to the f-string rule: they can be interpolated into the SQL **only after** the regex validation in `Connection.get_schema_name` (see [design-patterns.md §11.2](design-patterns.md)).

**Do (SQLAlchemy, named params):**

```python
from sqlalchemy import text

query = text(f"SELECT * FROM {schema}.devices WHERE serial = :serial")
row = conn._execute(query, {"serial": serial}).fetchone()
```

**Don't:**

```python
conn._execute(text(f"SELECT * FROM {schema}.devices WHERE serial = '{serial}'"))  # SQL injection
conn._execute(text("SELECT * FROM devices WHERE serial = %s"), (serial,))        # wrong param style
```

### 5.2 Migration Style

- **Up and down both required.** Every migration is reversible.
- **Idempotent** — `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` where supported.
- **One logical change per migration.** No mixing schema + data seed in same file.
- **Data migrations separate** from DDL migrations, numbered sequentially.

### 5.3 Naming

| Object | Convention | Example |
|--------|------------|---------|
| Tables | plural snake_case | `devices`, `batch_device_actions` |
| Columns | snake_case | `created_at`, `push_token` |
| Foreign keys | `<entity>_id` | `tenant_id`, `device_id` |
| Timestamps | `<verb>_at` | `enrolled_at`, `locked_at` |
| Booleans | `is_<adjective>` / `has_<noun>` | `is_locked`, `has_active_chat` |
| Indexes | `ix_<table>_<cols>` | `ix_devices_tenant_id_serial` |
| Unique constraints | `uq_<table>_<cols>` | `uq_devices_tenant_id_serial` |

### 5.4 Indexes

- **Declare explicitly** in migrations — never rely on ORM auto-generation.
- **Composite index order matters:** most selective column first.
- **Never index high-churn bool columns** without partial index.

---

## 6. Git Rules

### 6.1 Commit Message Format

Format: `[<ticket>]: <subject>`

- **Ticket** is the GitHub issue number with `#`, e.g. `[#34]`. If there is truly no ticket (hotfix on a dead system, emergency rollback), use `[chore]` — but the default is a ticket.
- **Subject** is imperative mood, lowercase first word, ≤ 72 chars, no trailing period. Describe the change, not the process.
- **No scope, no type prefix, no conventional-commits syntax.** Ticket number already groups changes; the diff shows the type.
- **Body** (optional, blank line after subject) explains *why* when non-obvious. Hard-wrap at 72.
- **Footer** (optional) for `Closes #N`, `Related #M`.

**Do:**

```
[#34]: add device enrollment handler

Handler parses AppSync event, delegates to DeviceRepository.enroll,
maps SerialAlreadyRegistered to GraphQL error code CONFLICT.

Closes #34
```

```
[#50]: retry on APNS 503 with exponential backoff
```

```
[#61]: foundation docs for phase 3
```

**Don't:**

```
feat(#34): add device handler          # old conventional-commits syntax
[34]: add device handler                # missing # in ticket
Added device handler.                   # not imperative, ends with period
[#34] add device handler                # missing colon after ]
WIP                                     # not descriptive
```

### 6.2 No AI References

Commit messages, PR descriptions, code comments must not reference AI assistants (Claude, Copilot, ChatGPT). Describe the change, not the author.

### 6.3 Pull Request Conventions

- **Title matches first commit** subject.
- **Body must cite docs sections** when rules apply (e.g., "Follows docs/code-standards.md §3.4 for Pydantic boundary validation").
- **Link the ticket** (`Closes #34`).
- **Test plan** as checkbox list.
- **No `--no-verify` / hook skip** unless explicit reviewer approval.

### 6.4 Branch Naming

Format: `<type>/<ticket>-<slug>`

Examples: `feat/34-device-resolver`, `fix/50-apns-retry`, `refactor/60-extract-fsm`.

---

## 7. Tooling Targets (Declared, Enforcement Pending)

These commands **will be** CI gates. Until the pre-commit / CI ticket lands, run locally before every commit.

| Stack | Tool | Command | CI Gate |
|-------|------|---------|---------|
| Python | ruff (format) | `ruff format --check .` | Fail on diff |
| Python | ruff (lint) | `ruff check --select ALL .` | Fail on error |
| Python | mypy | `mypy --strict src/` | Fail on error |
| Python | bandit | `bandit -r src/ -ll` | Fail on high severity |
| Python | pytest | `pytest --cov --cov-fail-under=80` | Fail under 80% |
| TypeScript | prettier | `prettier --check .` | Fail on diff |
| TypeScript | eslint | `eslint . --max-warnings 0` | Fail on warning |
| TypeScript | tsc | `tsc --noEmit` | Fail on error |
| TypeScript | vitest | `vitest run --coverage` | Fail under 80% |
| Terraform | fmt | `terraform fmt -check -recursive` | Fail on diff |
| Terraform | validate | `terraform validate` | Fail on error |
| Terraform | tflint | `tflint --recursive` | Fail on error |
| SQL | sqlfluff | `sqlfluff lint migrations/` | Fail on error |
| Commits | commitlint | `commitlint --from origin/main` | Fail on non-conforming |

---

## 8. References

- **Wiki T2** — Theoretical foundations (architecture principles).
- **Wiki T3** — FSM and Harel Statechart theory (patterns referenced in §3).
- **Wiki T4** — System architecture design (module boundaries).
- **Wiki T5** — API Contract + ER Diagram (schema conventions in §5).
- [module-structure.md](module-structure.md) — stack-specific layouts
- [design-patterns.md](design-patterns.md) — patterns the rules presuppose
- [testing-guide.md](testing-guide.md) — test naming and coverage rules

---

## 9. Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.0 | 2026-04-19 | Initial release (#61). |
