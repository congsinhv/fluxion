# fluxion-oem-processor

Python 3.12 Lambda workers that consume SQS events and talk to vendor-specific device APIs.

## How this repo differs from fluxion-backend

| | fluxion-backend | fluxion-oem-processor |
|---|---|---|
| Lambda trigger | AppSync (GraphQL) | SQS batch |
| DB migrations | Alembic (`migrations/`) | None — workers read-only or use backend migrations |
| Schema contract | `schema.graphql` | SQS event payload (Pydantic model inline in handler) |
| Base Dockerfile | `Dockerfile.resolver` + `Dockerfile.worker` | `Dockerfile.worker` only |
| Vendor SDKs | None | `httpx` (APNS HTTP/2), `cryptography` (APNS JWT signing) |

Workers **never own DB schema migrations**. Schema changes are applied by `fluxion-backend`.

## Layout

```
fluxion-oem-processor/
├── modules/
│   ├── _template/          # Copy + rename to add a new OEM worker
│   └── apple_process_action/   # (Phase 08+) Apple APNS worker
├── terraform/              # IaC — Phase 06 fills
├── pyproject.toml          # uv workspace root (dev tools only)
├── Dockerfile.worker       # Base image; per-module Dockerfiles inherit from this
├── .python-version         # 3.12
└── README.md
```

## Adding a new OEM worker Lambda

```bash
cp -r modules/_template modules/<new_worker_name>
cd modules/<new_worker_name>
# 1. Edit pyproject.toml: rename `name = "_template"` → `name = "<new_worker_name>"`
# 2. Edit src/config.py: update POWERTOOLS_SERVICE_NAME default
# 3. Replace src/handler.py stub with real SQS record processing
# 4. Update Dockerfile: change FROM tag if needed
```

Naming rules (from docs/code-standards.md §2.1): module dir must be `snake_case` to satisfy AWS Lambda handler import resolution.

## Running tests

```bash
# All modules
uv run pytest

# Single module
cd modules/<name> && uv run pytest tests/
```

## Lint + type-check

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict modules/_template/src/
```

## References

- [docs/module-structure.md §3](../docs/module-structure.md) — OEM processor layout rules
- [docs/code-standards.md](../docs/code-standards.md) — file naming, import rules, error handling
