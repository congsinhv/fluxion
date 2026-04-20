# Testing Guide

> **Version:** v1.0
> **Audience:** Fluxion contributors writing or reviewing tests.
> **Authority:** How Fluxion tests. Pairs with [code-standards.md](code-standards.md) (rules), [module-structure.md](module-structure.md) (test file placement), [design-patterns.md](design-patterns.md) (what to test per pattern).
> **Principles:** A failing test is a bug. A flaky test is a bigger bug. A missing test is a future bug.

---

## 1. Introduction

Fluxion handles real customer devices on real payment plans. A regression that locks the wrong phone, a migration that drops a tenant's data, or an auth decorator that leaks across tenants — any of these is unacceptable. Tests are the primary defense.

This guide defines the test pyramid, naming, fixtures, coverage, and CI gates. Every contributor follows it; every PR cites it when adding or changing tests.

---

## 2. Test Pyramid

| Layer | Share | Scope | Typical runtime |
|-------|-------|-------|-----------------|
| Unit | 70% | Single module or function, no I/O | < 100 ms each |
| Integration | 25% | Lambda + real dependencies (DB, LocalStack, moto) | < 5 s each |
| E2E | 5% | Full stack from frontend → AppSync → DB | < 60 s each |

**Keep the pyramid shape.** Inverted pyramids (most integration, few units) are slow, flaky, and expensive. If integration tests start duplicating unit-level logic, move the logic back to unit tests.

---

## 3. Python Tests (Pytest)

### 3.1 Placement and Naming

- Tests live **inside the Lambda package** at `modules/<name>/tests/`, matching the package layout (see [module-structure.md §2.2](module-structure.md)).
- File naming: `test_<module_under_test>.py` (e.g., `test_db.py`, `test_handler.py`).
- Function naming: `test_<scenario>_<expected>` — imperative, present tense, action-oriented.

```
modules/device_resolver/
├── handler.py
├── db.py
├── dto.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_handler.py
    ├── test_db.py
    └── test_dto.py
```

**Examples:**

```python
def test_enroll_device_returns_registered_state(...): ...
def test_enroll_device_raises_conflict_when_serial_duplicate(...): ...
def test_handler_rejects_unknown_field(...): ...
```

Do not prefix with the class name (`test_DeviceRepository_enroll`) — the file name already scopes it.

### 3.2 AAA Pattern

Arrange / Act / Assert, with blank-line separators. Comments optional, separators mandatory.

```python
def test_enroll_device_returns_registered_state(repo, tenant_schema):
    # Arrange
    serial = "F2LZK9H8LMNA"

    # Act
    device = repo.enroll(serial, Platform.APPLE)

    # Assert
    assert device.state == DeviceState.REGISTERED
    assert device.serial == serial
```

One behavior per test. If the "Assert" block checks three unrelated properties, split into three tests.

### 3.3 Fixtures

- `conftest.py` lives in every Lambda's `tests/` dir.
- Prefer **factories** (`factory-boy`, or plain factory functions) over JSON fixture files. Factories are typed, discoverable, composable.
- Shared fixtures **do not cross Lambda boundaries** — each Lambda's `conftest.py` is independent. Duplication is acceptable (see [design-patterns.md §1](design-patterns.md)).

```python
# modules/device_resolver/tests/conftest.py
import pytest
from device_resolver.dto import Device, Platform, DeviceState

@pytest.fixture
def registered_device_factory(tenant_schema):
    def _make(**overrides):
        defaults = dict(
            tenant_schema=tenant_schema,
            serial="F2LZK9H8LMNA",
            platform=Platform.APPLE,
            state=DeviceState.REGISTERED,
        )
        return Device(**{**defaults, **overrides})
    return _make
```

### 3.4 Mocking Policy

**Mock at the boundary. Never in the middle.**

| Layer | Mock? |
|-------|-------|
| AWS SDK calls (`boto3`) | Yes — via `moto` or local fakes. |
| HTTP to external APIs (APNS, OEM) | Yes — via `respx` / `httpx_mock`. |
| PostgreSQL driver | No. Use a real DB (testcontainers) — see §4. |
| Own repository / service classes | No. These are what you are testing. |
| Pydantic models | No. Real models; they are value objects. |

Violations of this policy cause most false-pass incidents: a test that mocks the repository passes while the real SQL is broken. Don't.

### 3.5 Parametrize Edge Cases

Use `@pytest.mark.parametrize` when the same behavior has many inputs — state transitions, policy matrices, boundary values.

```python
@pytest.mark.parametrize("from_state,action,expected_to_state", [
    (DeviceState.REGISTERED, "enroll", DeviceState.ENROLLED),
    (DeviceState.ENROLLED,   "lock",   DeviceState.LOCKED),
    (DeviceState.LOCKED,     "unlock", DeviceState.ACTIVE),
])
def test_fsm_transition_happy_path(from_state, action, expected_to_state, repo):
    ...
```

One matrix beats ten near-duplicate tests.

### 3.6 Testing `config.py`

Because `config.py` reads `os.environ` at import time, tests must set env vars **before** importing the module under test.

```python
# tests/conftest.py
import os
import pytest

@pytest.fixture(autouse=True, scope="session")
def _set_env():
    os.environ.setdefault("ACTION_TRIGGER_SQS", "arn:aws:sqs:...:test-queue")
    os.environ.setdefault("ACTION_ASSIGNED_TOPIC", "arn:aws:sns:...:test-topic")
    os.environ.setdefault("DB_SECRET_ARN", "arn:aws:secretsmanager:...:test")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    yield
```

For tests that exercise "env var is missing" behavior, use `monkeypatch.delenv` + `importlib.reload(config)` inside the test.

---

## 4. Integration Tests

Integration tests exercise a Lambda against real (or in-container) dependencies: PostgreSQL, SNS, SQS, S3.

### 4.1 PostgreSQL — Testcontainers

- Always a **real PostgreSQL 15+ container**, never SQLite. Production parity matters for schemas, JSONB, `ON CONFLICT`, `RETURNING`.
- Startup once per test **session**, torn down at the end.
- Each test creates its own tenant schema (via the schema-creation helper), runs, drops it.

```python
# tests/integration/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:15-alpine") as pg:
        # Apply base schema + meta + tenant_template
        apply_migrations(pg.get_connection_url())
        yield pg

@pytest.fixture
def tenant_schema(pg_container, request):
    name = f"tenant_test_{request.node.name[:30]}"
    create_tenant_schema(pg_container, name)  # clone from tenant_template
    yield name
    drop_tenant_schema(pg_container, name)
```

This gives every test a fresh schema, structurally isolated, torn down at test end.

### 4.2 AWS Services — Moto / LocalStack

- `moto` for SNS, SQS, S3, Secrets Manager, Parameter Store — fast, in-process, good enough for most flows.
- `LocalStack` only when a moto gap blocks you (e.g., AppSync flows, EventBridge rules). More heavyweight, slower.
- **Never mock Cognito.** Either use the real Cognito (staging pool) in an E2E test, or stub the auth decorator at the `TenantContext` boundary in a unit test.

### 4.3 Teardown

Transactional rollback > DB wipe. When possible, wrap each integration test in a savepoint and roll it back. When schema-level DDL is involved (e.g., tenant schema creation), drop the schema in teardown — still faster than recreating the whole database.

### 4.4 SQS / SNS Contract Tests

Per [module-structure.md §6](module-structure.md), SQS payloads are **duplicated** across consumers. Every producer and every consumer of an event type owns a contract test that asserts the payload it emits / consumes matches the schema.

```python
# In each consumer's tests/:
def test_consumes_action_assigned_v1(sample_sns_record):
    event = ActionAssigned.model_validate_json(sample_sns_record.body)
    assert event.version == "1"
    # ... further assertions
```

Shared JSON fixture files (`sample_action_assigned_v1.json`) live in each consuming Lambda, version-tagged. When a producer bumps the version, every consumer's contract test fails until updated — drift becomes visible.

---

## 5. TypeScript Tests (Vitest + React Testing Library)

### 5.1 Placement and Naming

- Component tests: next to the component, `DeviceTable.test.tsx`.
- Hook tests: next to the hook, `use-device-list.test.ts`.
- Feature-level tests: in `__tests__/` inside the feature dir.

### 5.2 React Testing Library Queries

Prefer queries that match how users find elements:

1. `getByRole` + `name` — best for buttons, headings, form fields.
2. `getByLabelText` — form inputs.
3. `getByText` — non-interactive content.
4. `getByTestId` — last resort; only when semantic queries fail.

```tsx
// Do
await user.click(screen.getByRole("button", { name: /enroll device/i }));

// Don't
await user.click(screen.getByTestId("enroll-button"));
```

### 5.3 API Mocking via MSW

Use Mock Service Worker (MSW) for GraphQL / HTTP. Intercepts at the network boundary — components under test exercise the real Amplify client.

```ts
// tests/msw/handlers.ts
export const handlers = [
  graphql.query("ListDevices", () => HttpResponse.json({ data: { listDevices: [...] }})),
];
```

No `any`, no `@ts-ignore` in tests — strict TypeScript applies to test files too.

---

## 6. Coverage Targets

| Scope | Target | Enforcement |
|-------|--------|-------------|
| Backend global (line + branch) | ≥ 80% | `pytest --cov --cov-fail-under=80` in CI |
| Frontend global | ≥ 80% | `vitest run --coverage` with threshold |
| Critical paths | **100%** | Manual review per PR (see §6.1) |
| Handler entry (`handler.py`) | Excluded | Tested via integration tests only |

### 6.1 Critical Paths Requiring 100% Coverage

These paths break production in ways that damage customer trust or data. No PR touching them merges with coverage < 100%:

- Auth decorators (`require_role`, `tenant_scoped`).
- FSM transitions (`apply_action` and all policy evaluations).
- Idempotency write paths (every `ON CONFLICT` insert).
- Schema-name validation regex + any f-string-interpolated SQL.
- Migrations (every up and down path runs in integration tests against a fresh DB).
- Frontend auth guard routes.

### 6.2 What NOT to Test

Testing these is noise:

- Third-party library behavior (trust pytest, moto, pydantic, React).
- Framework glue (AppSync routing, Vite HMR).
- Trivial getters/setters that only return a field.
- Generated code (GraphQL codegen output).

Write a test only if it would catch a realistic regression in **your** code.

---

## 7. Test Data

- **Factories over fixtures.** Typed, composable, discoverable. `factory-boy` for Python; hand-written factory functions for TypeScript.
- **No hardcoded JSON fixture files** except for contract-test samples (§4.4), which are versioned and owned.
- **Every test creates its own tenant schema.** No shared test DB state; no "setup data" that later tests depend on.
- **Use realistic but non-PII data.** Fake serials (`F2LZK9H8LMNA`), tenant slugs (`test_acme`), email domains (`@test.fluxion.local`).

---

## 8. CI Requirements

| Requirement | Enforcement |
|-------------|-------------|
| All tests pass | CI job blocks merge. |
| Coverage thresholds met | `pytest` / `vitest` fail below target. |
| No flaky tests | One retry only for known-flaky markers; persistent flakes are P0 bugs. |
| Parallel execution | `pytest-xdist -n auto` / Vitest thread pool. |
| Fail-fast on first failure (CI only) | `-x` flag. Locally, run full suite. |
| JUnit XML + coverage uploaded | For PR annotations + Codecov. |

No `--no-verify` / hook skip unless reviewer explicitly approves.

---

## 9. Test Review Checklist (PRs)

Reviewer and author tick the checklist. If an item cannot be ticked, explain in the PR body.

- [ ] AAA pattern with blank-line separators.
- [ ] No commented-out tests.
- [ ] No `time.sleep` — use deterministic synchronization (event loop fixtures, mocked clocks).
- [ ] Every critical path (§6.1) touched has 100% coverage.
- [ ] Integration tests use real PostgreSQL via testcontainers, not SQLite.
- [ ] Mocks only at boundaries (see §3.4).
- [ ] Factories, not JSON fixtures (except contract-test samples).
- [ ] Each test creates its own tenant schema; no shared state.
- [ ] Env vars set via `conftest.py`, not hardcoded inside tests.
- [ ] No `any` / `@ts-ignore` in TS tests.
- [ ] Test function names read as sentences (`test_<scenario>_<expected>`).

---

## 10. References

- [code-standards.md](code-standards.md) — rules tests must follow.
- [module-structure.md](module-structure.md) — where test files live.
- [design-patterns.md](design-patterns.md) — patterns tests validate (esp. §11 tenant-per-schema).
- Pytest docs — https://docs.pytest.org/
- Testcontainers Python — https://testcontainers-python.readthedocs.io/
- Moto — https://docs.getmoto.org/
- Vitest — https://vitest.dev/
- React Testing Library — https://testing-library.com/docs/react-testing-library/intro/
- MSW — https://mswjs.io/

---

## 11. Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.0 | 2026-04-19 | Initial release (#61). |
