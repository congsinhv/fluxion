# Design Patterns

> **Version:** v1.0
> **Audience:** Fluxion contributors building Lambda resolvers, workers, and the React console.
> **Authority:** Patterns the codebase presupposes. Pairs with [code-standards.md](code-standards.md) (rules) and [module-structure.md](module-structure.md) (layout).
> **Principle:** Patterns exist to solve recurring problems. If the problem has not appeared twice, do not adopt the pattern (YAGNI).

---

## 1. Introduction

Fluxion uses a small, deliberate set of patterns. This document lists each one, the problem it solves, the Fluxion-specific implementation, and the common mistakes to avoid.

**Ground rules:**

- **No shared code modules.** Each Lambda is self-contained (see [module-structure.md §2.2](module-structure.md)). When a pattern requires boilerplate, it is copied per Lambda — not imported. If the boilerplate becomes painful, the answer is an AWS Lambda Layer, not a new top-level `shared/` dir.
- **Patterns are not architecture.** Do not introduce a pattern because "it's good practice." Introduce it when a concrete Fluxion need appears (a second Lambda needs the same shape, an external call starts timing out, etc.).
- **Prefer dumb code over clever pattern.** A 10-line function is better than a 3-file abstraction that "encapsulates future change."

---

## 2. Choreography Saga

**Problem.** An assignment of an action to a device must cross multiple Lambdas and external systems:
1. Operator calls `assignAction` via AppSync.
2. `action_resolver` records intent in `action_logs`.
3. `action_trigger` Lambda consumes an SNS event, fans out per-device SQS messages.
4. `apple_process_action` (OEM worker) sends APNS push.
5. Device checks in; `checkin_handler` Lambda updates FSM state.

Wrapping all five steps in a single synchronous handler would couple them, extend Lambda timeout risk, and lose the at-least-once durability of SQS.

**Solution — Choreography Saga.** Each Lambda owns one step, publishes an event when done, and does not know who consumes it. No central orchestrator. SNS fan-out with SQS per consumer gives retry, DLQ, and observability for free.

**Event naming.** `<entity>.<action>.<outcome>`:
- `action.assigned` — resolver wrote the intent.
- `device.push.sent` — OEM worker succeeded.
- `device.checkin.received` — device responded.
- `action.completed` / `action.failed` — terminal events for the saga.

**Payload shape.** Every event payload carries a `correlation_id` (UUID from the originating AppSync call) and a `version` field (starts at `"1"`). Consumers must tolerate unknown fields, and reject payloads whose `version` major bump they have not been updated for.

**Fluxion example (pseudocode, per-Lambda duplication allowed):**

```python
# modules/action_resolver/handler.py
def lambda_handler(event, context):
    input_ = AssignActionInput.model_validate(event["arguments"])
    log = repo.create_action_log(input_, correlation_id=context.aws_request_id)
    sns.publish(
        TopicArn=os.environ["ACTION_ASSIGNED_TOPIC"],
        Message=ActionAssigned(
            version="1",
            correlation_id=context.aws_request_id,
            action_log_id=log.id,
            device_ids=input_.device_ids,
        ).model_dump_json(),
    )
    return ActionLogOutput.from_model(log).model_dump()
```

**When NOT to use.** Single-service transactional operations (device update + audit write, both in PostgreSQL) → one DB transaction, not a saga. Distributed transactions across AWS accounts → that is a different problem entirely (use Step Functions Express).

**Common mistakes:**
- Consumer Lambdas importing the producer's event class. Re-declare Pydantic models per consumer (see [module-structure.md §6](module-structure.md)).
- Assuming exactly-once delivery. SQS is at-least-once — every consumer must be idempotent (§9).
- Missing DLQ. Every SQS queue needs one; every DLQ needs a CloudWatch alarm.

---

## 3. Finite State Machine (DB-Driven)

**Problem.** A device moves through a lifecycle — `idle` → `registered` → `enrolled` → `active` ⇄ `locked` → `released`. Transitions are triggered by operator actions, OEM callbacks, or scheduled jobs. Encoding "when can X happen" as `if/else` ladders scattered across resolvers leads to inconsistent behavior and security gaps (e.g., a locked device accepting a lock command).

**Solution — DB-driven FSM.** Four tables define the machine, inside each tenant's schema (see §11 on multi-schema isolation):

| Table | Role |
|-------|------|
| `{tenant_schema}.device_states` | Enumerates valid states (`idle`, `enrolled`, `active`, `locked`, `released`). |
| `{tenant_schema}.state_policies` | Allowed transitions: `from_state`, `to_state`, `action`, guard predicate. |
| `{tenant_schema}.state_actions` | Actions operators or workers can invoke (`enroll`, `lock`, `release`). |
| `{tenant_schema}.state_milestones` | Side effects to emit when reaching a target state (SNS events, audit rows). |

**Invariant:** a transition happens **only** via `apply_action(tenant_schema, device_id, action)` which:
1. Loads the current state (row lock if transition mutates).
2. Looks up `state_policies` for `(current_state, action)` — `NOT FOUND` → `IllegalTransition`.
3. Evaluates the guard (e.g., "device must have no unpaid installments to enter `released`").
4. Updates `devices.state` in the same transaction.
5. Writes a row to `device_state_transitions` (history).
6. Emits milestone events post-commit via outbox pattern.

**Fluxion example (schema-qualified, guard in SQL):**

```python
# modules/action_trigger/handler.py — simplified
def apply_action(conn, tenant_schema: str, device_id: str, action: str) -> Device:
    # tenant_schema is validated by caller (Cognito claim) — never user-supplied here
    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH cur AS (
                SELECT state FROM {tenant_schema}.devices WHERE id = %s FOR UPDATE
            ),
            policy AS (
                SELECT p.to_state
                FROM {tenant_schema}.state_policies p, cur
                WHERE p.from_state = cur.state AND p.action = %s
                  AND (p.guard_sql IS NULL OR evaluate_guard(p.guard_sql, %s))
            )
            UPDATE {tenant_schema}.devices
            SET state = (SELECT to_state FROM policy)
            WHERE id = %s AND (SELECT to_state FROM policy) IS NOT NULL
            RETURNING *;
            """,
            (device_id, action, device_id, device_id),
        )
        row = cur.fetchone()
        if not row:
            raise IllegalTransition(device_id, action)
        return Device.model_validate(dict(row))
```

**Schema name safety.** `tenant_schema` is injected into SQL via f-string, which is normally a SQL-injection red flag. It is safe **only because** the value comes from a validated source (Cognito claim → `meta.tenants.schema_name` lookup at auth time) and is matched against a regex (`^tenant_[a-z0-9_]+$`) before any query. Never accept `tenant_schema` from request arguments directly.

**Why DB-driven.** Policies change without redeploy — operators (with the right role) add a new `action=release` policy row for a new state. Guards stay in SQL so they run in the same transaction as the mutation.

**When NOT to use.** Single-flag toggles (`is_active`) or workflows where transitions are trivial and non-branching — just write `UPDATE devices SET is_active = TRUE`.

**Common mistakes:**
- Caching FSM state in Lambda memory between invocations. Containers are reused but not guaranteed — always reload from DB.
- Putting guards in Python and policy rows in SQL. Keep guard logic in one place (SQL here).
- Emitting milestone events before the transaction commits. Use the outbox pattern: write an event row in the same TX, publish post-commit.

**Reference:** Wiki T5 — DeviceFSM design.

---

## 4. Resolver Pattern (AppSync Lambda)

**Problem.** AppSync routes a GraphQL field to a Lambda. The Lambda must: parse the event, authorize the caller, validate input, call business logic, map errors, serialize output. Mixing these concerns in one function yields 300-LOC handlers that are untestable.

**Solution — thin handler + delegation.** The `handler.py` is a wire: it does the 4 boundary concerns (parse, auth, validate, serialize) and delegates work to sibling modules.

```python
# modules/device_resolver/handler.py (~40 LOC, under §2.2 budget)
from __future__ import annotations
import os, logging
from shared_logging import configure  # copied per-Lambda, not imported from a shared/ dir

configure()
logger = logging.getLogger(__name__)

FIELD_HANDLERS = {
    "getDevice": handle_get_device,
    "listDevices": handle_list_devices,
    "enrollDevice": handle_enroll_device,
}

def lambda_handler(event, context):
    field = event["info"]["fieldName"]
    tenant_ctx = tenant_context_from(event)  # parses Cognito claims
    correlation_id = context.aws_request_id

    logger.info("resolver.invoked", extra={"field": field, "tenant": tenant_ctx.id, "correlation_id": correlation_id})
    try:
        return FIELD_HANDLERS[field](event["arguments"], tenant_ctx, correlation_id)
    except FluxionError as e:
        return e.to_appsync_error()
```

**Field-level authorization via decorators.** Decorators live in the Lambda (copied, not imported):

```python
@require_role("admin")
@tenant_scoped
def handle_enroll_device(args, ctx, correlation_id):
    input_ = EnrollDeviceInput.model_validate(args)
    device = db.enroll(ctx.tenant_id, input_.serial, input_.platform)
    return Device.from_row(device).model_dump()
```

**Config in `config.py` (mandatory).** Every Lambda reads its environment variables exactly once, at module import, in `config.py`. Failures are loud at cold start, not buried inside request handlers.

```python
# modules/action_trigger/config.py
import os

ACTION_TRIGGER_SQS = os.environ["ACTION_TRIGGER_SQS"]          # required — fail fast
ACTION_ASSIGNED_TOPIC = os.environ["ACTION_ASSIGNED_TOPIC"]    # required
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]                    # required
PUSH_TIMEOUT_SECONDS = int(os.environ.get("PUSH_TIMEOUT_SECONDS", "10"))  # optional default
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

Handlers and services import from `config.py`. They never call `os.environ` directly.

**When NOT to use the pattern.** One-off Lambdas that run a single CLI-style task (a migration helper, a one-shot report generator). A `main()` function is fine.

**Common mistakes:**
- Putting GraphQL error mapping outside the handler (in business logic). Business logic raises `FluxionError`; only the handler knows about AppSync response shape.
- Reading environment variables inside request handlers. All env var reads live in `config.py`, evaluated at import. A missing var throws on cold start, not mid-request.
- Forgetting to log the correlation ID. Every log line in the handler scope must include it.

---

## 5. Repository Pattern

**Problem.** Business logic sprinkled with SQL is un-reviewable: you cannot tell at a glance whether a query respects tenant isolation, uses an index, or handles the "row already locked" race. Embedded `execute(...)` calls also couple business code to `psycopg2` specifics.

**Solution — `db.py` per Lambda.** All data access lives in a single module per Lambda with a clear API. Business logic gets Pydantic DTOs, never raw `dict` rows.

```python
# modules/device_resolver/db.py
class DeviceRepository:
    def __init__(self, conn: psycopg2.extensions.connection, tenant_schema: str) -> None:
        # tenant_schema comes from validated Cognito context (see §3 schema-name safety note)
        self._conn = conn
        self._schema = tenant_schema

    def get_by_id(self, device_id: str) -> Device | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {self._schema}.devices WHERE id = %s",
                (device_id,),
            )
            row = cur.fetchone()
        return Device.model_validate(dict(row)) if row else None

    def enroll(self, serial: str, platform: Platform) -> Device:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self._schema}.devices (serial, platform, state)
                VALUES (%s, %s, 'registered')
                ON CONFLICT (serial) DO NOTHING
                RETURNING *;
                """,
                (serial, platform.value),
            )
            row = cur.fetchone()
        if not row:
            raise SerialAlreadyRegistered(serial)
        return Device.model_validate(dict(row))
```

**Tenant isolation is structural.** With tenant-per-schema, isolation lives in the schema boundary — the `DeviceRepository` is bound to one tenant schema for its entire lifetime. No query has a free `WHERE tenant_id = %s` clause; cross-tenant leaks require a bug in *construction* (wrong schema passed in), not in individual queries.

**Testability.** In unit tests, mock `psycopg2.connection.cursor` (the driver seam), never the `DeviceRepository` class. The class is the thing under test.

**When NOT to use.** A Lambda that executes one query, no branching, no reuse (a health-check endpoint). Inline the `execute` call in the handler.

**Common mistakes:**
- Repository method returns raw row dicts. Always return Pydantic DTOs — the repository is the shape-validation boundary.
- Repository calls another repository. Keep it a leaf; if you need composition, do it in business logic, not inside the repository.
- Testing by mocking the repository class in business-logic tests. That hides SQL correctness bugs. Use a real (in-container) PostgreSQL for business-logic tests (see [testing-guide.md](testing-guide.md)).

---

## 6. Factory Pattern (OEM Abstraction)

**Problem.** Today Fluxion supports Apple devices (APNS + MDM). Tomorrow it needs Samsung Knox, maybe Xiaomi. The `action_trigger` Lambda should not care which OEM a device belongs to — it just asks "push this action to this device."

**Solution — provider interface + registry.** A small abstract base class defines the contract; the registry maps `Platform` enum → provider implementation. OEM-specific code lives in `fluxion-oem/modules/<oem>_process_action/`.

```python
# fluxion-oem/modules/apple_process_action/provider.py
class OEMProvider(ABC):
    @abstractmethod
    def push_action(self, device: Device, action: Action) -> PushResult: ...

class AppleProvider(OEMProvider):
    def push_action(self, device, action):
        # APNS HTTP/2 call, retry + CB, return structured result
        ...

# Registry lookup:
PROVIDERS: dict[Platform, type[OEMProvider]] = {Platform.APPLE: AppleProvider}
```

**No shared `providers/` module.** The `OEMProvider` base class is copied to each OEM worker Lambda because we do not share code across Lambdas (see §1). Duplication here is small (5 lines of ABC) and prevents deploy coupling: updating APNS logic does not force a redeploy of a hypothetical Samsung worker.

**When NOT to use.** Single-OEM codebase with no concrete second OEM on the roadmap. Just write `apple_push(device, action)` directly — a one-OEM "factory" is pure overhead.

**Common mistakes:**
- Stuffing provider-specific config (APNS bundle IDs, Samsung Knox tenant keys) into a shared config class. Each provider owns its own env vars — the registry reads none.
- Returning provider-specific exceptions across the boundary. `AppleProvider.push_action` catches `APNSRateLimited` and raises a shared `PushTransientError`.

---

## 7. DTO / Pydantic Boundary Validation

**Problem.** Raw `dict` payloads survive deep into a codebase, causing `KeyError` at 2am and silently accepting malformed input. Type checkers (`mypy`) cannot help with `dict[str, Any]`.

**Solution — Pydantic at every boundary.**
1. **Input.** Every handler entry parses `event["arguments"]` into a Pydantic model with `extra="forbid"`.
2. **Repository return.** Queries return Pydantic DTOs, not cursor rows.
3. **External response.** APNS / OEM responses parsed into Pydantic before the code trusts them.
4. **Output.** Before returning from a handler, serialize via Pydantic (`.model_dump()`) — never hand-craft the response dict.

```python
# modules/device_resolver/dto.py
class EnrollDeviceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    serial: str = Field(min_length=10, max_length=20, pattern=r"^[A-Z0-9]+$")
    platform: Platform

class DeviceOutput(BaseModel):
    id: UUID
    serial: str
    state: DeviceState
    enrolled_at: datetime | None
```

**Why strict (`extra="forbid"`).** Unknown fields from a misconfigured client are a signal of version drift, not a feature to silently accept.

**When NOT to use.** Never "not use." Every boundary gets Pydantic. The only exception is pass-through proxies (a Lambda that does nothing but re-publish an SNS message verbatim) — and even those are rare.

**Common mistakes:**
- Skipping validation at the repository boundary. "The DB would not return a bad row" — yes it would, after a failed migration.
- Using `dict` inside business logic after parsing at the boundary. If Pydantic parsed it, keep it as a model through the whole call stack.

---

## 8. Circuit Breaker

**Problem.** APNS has a bad minute, every `action_trigger` invocation blocks on a 15-second HTTP timeout, the whole Lambda concurrency limit saturates, and AppSync resolvers downstream time out too. One flaky dependency takes out the whole command pipeline.

**Solution — per-container circuit breaker.** Each Lambda container instance tracks its own recent failure rate for each external endpoint. When failures exceed a threshold in a window, the breaker opens and subsequent calls fail fast with a `ServiceUnavailable`. The caller (SQS consumer) can then NACK the message back to the queue with a short visibility timeout — retries are cheap, blocked handlers are not.

```python
# modules/apple_process_action/push_service.py (sketch)
breaker = CircuitBreaker(failure_threshold=5, window_seconds=60, half_open_after=30)

def push(device, action):
    if breaker.is_open():
        raise PushTransientError("apns breaker open")
    try:
        response = apns.send(device.push_token, payload(action))
        breaker.on_success()
        return response
    except (RequestTimeout, ConnectionError) as e:
        breaker.on_failure()
        raise PushTransientError("apns transient") from e
```

**Lambda-specific caveat.** The breaker state lives in the container and is lost on cold start. This is OK — cold starts are rare compared to the burst window we care about. Do **not** back the breaker with a shared store (Redis, DynamoDB) to "improve" this; shared-state breakers add new failure modes (breaker store itself goes down) to prevent a problem the container-local breaker already handles well enough.

**When NOT to use.** Low-QPS endpoints (one call per hour) — the breaker never gathers enough samples to open meaningfully. Rely on timeouts and DLQ instead.

**Common mistakes:**
- Using the breaker on AWS SDK calls. AWS SDK already has retry with exponential backoff; adding a breaker layers two retry strategies and hides real failures.
- Opening the breaker on 4xx responses. 4xx means "my request is wrong," retrying does not help — but it is also not a sign the service is down. Track only 5xx + timeouts.

---

## 9. Idempotency

**Problem.** SQS delivers at-least-once. AppSync retries on transient failures. An event that enrolls a device can arrive twice, creating duplicate rows or sending two APNS pushes. Worse: partial retries mean some side effects already happened, others did not.

**Solution — idempotency keys persisted with unique constraint.** Every mutating operation accepts (or generates) an idempotency key. The first write wins; subsequent duplicates are no-ops.

```sql
-- Created inside each tenant's schema; no tenant_id column needed (schema itself isolates).
CREATE TABLE {tenant_schema}.action_logs (
    id UUID PRIMARY KEY,
    idempotency_key UUID NOT NULL UNIQUE,
    -- ... other columns
);
```

```python
# modules/action_resolver/db.py
def create_action_log(self, input_: AssignActionInput, correlation_id: str) -> ActionLog:
    key = input_.idempotency_key or correlation_id
    with self._conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {self._schema}.action_logs (id, idempotency_key, ...)
            VALUES (%s, %s, ...)
            ON CONFLICT (idempotency_key) DO UPDATE
                SET id = {self._schema}.action_logs.id  -- no-op trigger so we return existing row
            RETURNING *;
            """,
            (uuid4(), key, ...),
        )
        return ActionLog.model_validate(dict(cur.fetchone()))
```

**Per-tenant uniqueness is automatic.** Because the table lives inside a tenant schema, the `UNIQUE (idempotency_key)` constraint scopes per-tenant for free. No cross-tenant collisions possible.

**Who supplies the key.**
- AppSync mutations: client passes an optional `idempotencyKey`. If absent, the resolver derives one from request id + tenant + logical operation (covers within-session dedup, not cross-session).
- SQS consumers: use the SNS message id as the key (included in message attributes).
- Internal Lambda → Lambda calls: use the caller's correlation id.

**When NOT to use.** Pure reads (no side effects). Idempotency is a write-side concern.

**Common mistakes:**
- Using the client's retry id (AppSync request id) as the only idempotency key. Different clients can retry the "same logical action" with different ids — bad for user-facing dedup.
- Making the key unique globally instead of per-tenant. You will collide across tenants, reject legitimate operations.
- Implementing idempotency at the API layer (check-then-insert with a cache). It is racy — only the database `UNIQUE` constraint gives atomic guarantees.

---

## 10. Anti-Patterns to Avoid

These have caused real bugs in similar systems. Catch them in review.

| Anti-pattern | Why it hurts | What to do instead |
|--------------|--------------|--------------------|
| **God class / god file** (> 200 LOC, > 10 public methods) | Hides coupling, makes review and testing painful. | Split by concern per [code-standards.md §2.2](code-standards.md). |
| **Deep inheritance** (3+ levels) | Behavior becomes hard to trace; framework magic proliferates. | Composition (pass collaborators as params) over inheritance. |
| **Mocks in production code paths** (e.g., a `MockProvider` fallback imported in `handler.py`) | Test doubles ship to prod; production-vs-test drift. | Mocks live in `tests/`, period. Production code uses real providers or a feature flag. |
| **Hidden coupling via module-level state** (module-level singletons, globals mutated from handlers) | Cold-start behavior differs from warm; impossible to unit-test in parallel. | Pass dependencies explicitly; if you need a cache, own its lifecycle in `config.py`. |
| **Premature abstraction** (a `BaseService` class with one subclass) | Overhead with no payoff; locks in the wrong shape. | Wait for the second concrete use. Duplicate once, extract at N=2. |
| **"Just in case" error handling** (catching every `Exception` at every layer) | Hides bugs; debugging becomes guessing. | Catch only at boundaries. Let unexpected exceptions surface. |
| **Side effects in imports** (a `client = BotoClient()` at module top level) | Cold-start cost; testing any file instantiates clients. | Create in `config.py` or lazily inside a function. |
| **String concatenation into SQL or GraphQL** | Injection, obviously, but also schema-drift bugs. | Parameterized everything ([code-standards.md §5.1](code-standards.md)). |

---

## 11. Tenant-per-Schema Isolation

**Problem.** Row-level multi-tenancy (every table has `tenant_id`, every query has `WHERE tenant_id = %s`) puts the isolation invariant in developer discipline. One missing `WHERE` clause leaks data across tenants. Audits, backups, and per-tenant archiving are awkward.

**Solution — one PostgreSQL schema per tenant.** Each tenant gets a bare schema name (e.g., `dev1`, `acme`, `fpt`). All 16 business tables (devices, actions, chats, etc.) live inside the tenant schema. A separate `accesscontrol` schema holds cross-tenant identity + authorization; `public` owns provisioning procedures.

```
postgres (single database)
├── accesscontrol             # Shared: tenants registry, users, permissions
│   ├── tenants               # (id, schema_name, enabled, created_at, ...)
│   ├── users                 # (id, email, cognito_sub, name, enabled, ...)
│   ├── permissions           # (id, code, description)
│   └── users_permissions     # (id, user_id, permission_id, tenant_id, ...)
├── public                    # Provisioning procedures
│   ├── create_tenant_schema(text)      # Creates schema + 16 business tables
│   └── create_default_tenant_data(text) # Seeds FSM, brands, tacs, templates
├── dev1                      # Per-tenant business data (16 tables)
│   ├── devices
│   ├── device_informations
│   ├── device_tokens
│   ├── action_executions
│   ├── services, states, policies, actions
│   ├── milestones, brands, tacs
│   ├── chat_sessions, chat_messages
│   ├── message_templates
│   ├── batch_actions, batch_device_actions
│   └── [12 indexes per table]
├── acme
│   └── (same 16 tables as dev1)
└── fpt
    └── (same 16 tables as dev1)
```

### 11.1 Schema-Qualified SQL (Mandatory)

Every query uses `{tenant_schema}.<table>` — never an unqualified table name, never `SET search_path`.

```python
# Correct — explicit schema:
cur.execute(f"SELECT * FROM {schema}.devices WHERE id = %s", (id,))

# Wrong — implicit via search_path:
cur.execute("SET search_path TO tenant_acme, public")
cur.execute("SELECT * FROM devices WHERE id = %s", (id,))
```

Explicit beats implicit: the query read in isolation tells you which tenant it touches. `search_path` is connection-level state that pooled connections can leak across tenants.

### 11.2 Schema Name Resolution

The `tenant_schema` value flows:
1. Client authenticates with Cognito — token carries `tenant_id` claim.
2. Lambda auth decorator reads the claim, looks up `accesscontrol.tenants` to fetch `schema_name`.
3. Resolved `tenant_schema` is passed into repositories at construction.
4. Repositories f-string-interpolate it into SQL.

**Schema name must be validated** before any f-string use: `re.fullmatch(r"^[a-z][a-z0-9_]{0,39}$", schema_name)` (bare names like `dev1`, `acme`; no prefix). Never accept `tenant_schema` from request arguments; only from the validated auth claim path.

### 11.3 Migrations

Alembic runs migrations against every tenant schema in sequence (and against `meta` for shared changes).

- DDL migrations receive `tenant_schema` as a parameter, apply once per schema.
- Data migrations (seeding FSM policies, for example) do the same.
- A new tenant is created by cloning a **template schema** (`tenant_template`), which holds the current DDL baseline.

### 11.4 When NOT to Use Tenant-per-Schema

- Single-tenant deployments (internal tooling, POCs).
- Very-high-cardinality tenancy (tens of thousands of tenants) where schema count becomes a PostgreSQL catalog bottleneck. Fluxion targets dozens of enterprise tenants, well within limits.

### 11.5 Common Mistakes

- Building a query string in Python and injecting `tenant_schema` without validation. Always validate with the regex in §11.2.
- Sharing a pooled connection across tenants using `SET search_path`. Don't — pool connections with no per-tenant state, pass `tenant_schema` in SQL.
- Forgetting to add DDL to the provisioning procedure. New per-tenant tables must be added to `public.create_tenant_schema()` (line ~57 in migrations/versions/4768d32c8037*), and new seed data to `public.create_default_tenant_data()` (line ~326).
- Putting tenant-global data (message templates, TACs) inside a tenant schema. These are already per-tenant (seeded in each schema); truly cross-tenant data belongs in `accesscontrol`.

---

## 12. Choosing Between Patterns (Cheat Sheet)

| Problem | Pattern |
|---------|---------|
| Multi-Lambda command flow | Choreography Saga (§2) |
| Branching device lifecycle | FSM (§3) |
| GraphQL field → business logic | Resolver (§4) |
| SQL spread through business code | Repository (§5) |
| Multiple OEM integrations | Factory (§6) |
| Bad data entering business logic | DTO / Pydantic (§7) |
| External dependency flaking | Circuit Breaker (§8) |
| Duplicate events / retries | Idempotency (§9) |

If your problem is not in the table, solving it with a pattern is probably premature. Write the straight-line code first.

---

## 13. References

- [code-standards.md](code-standards.md) — rules the patterns assume.
- [module-structure.md](module-structure.md) — where patterns physically live in the repo.
- [testing-guide.md](testing-guide.md) — how to test each pattern.
- **Wiki T3** — FSM and Harel Statechart theory (deeper background for §3).
- **Wiki T4** — System architecture (saga and resolver patterns visualized).
- **Wiki T5** — DeviceFSM tables (schema the §3 pattern relies on).

---

## 14. Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.1 | 2026-04-20 | Updated §11 (tenant-per-schema): corrected schema naming from `tenant_{slug}` to bare names (`dev1`, `acme`); changed `meta` schema ref to `accesscontrol`; clarified 16 per-tenant business tables + provisioning proc structure (#31). |
| v1.0 | 2026-04-19 | Initial release (#61). |
