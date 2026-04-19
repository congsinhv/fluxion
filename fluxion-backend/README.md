# fluxion-backend

Python 3.12 Lambda resolvers and workers for the Fluxion MDM platform.
Hosts AppSync GraphQL resolvers, command-pipeline Lambdas, and Alembic migrations
for the multi-tenant PostgreSQL database.

See [`docs/module-structure.md §2`](../docs/module-structure.md) for full layout rules.

## Contents

```
fluxion-backend/
├── modules/              # One directory per Lambda function
│   └── _template/        # Copy this to scaffold a new Lambda
├── migrations/           # Alembic environment (versions/ populated in #31)
├── terraform/            # IaC — modules + per-env wiring (populated in #30–#32)
├── schema.graphql        # GraphQL contract (populated in #33)
├── Dockerfile.resolver   # Base image for AppSync resolver Lambdas
├── Dockerfile.worker     # Base image for SQS worker Lambdas
├── pyproject.toml        # uv workspace root + shared dev tooling
└── .python-version       # 3.12 (read by pyenv and uv)
```

## Adding a New Lambda

```bash
cp -r modules/_template modules/<new_name>
cd modules/<new_name>
# Follow the checklist in modules/_template/README.md
```

## Running Tests

Run all tests across the workspace:

```bash
cd fluxion-backend
uv sync
uv run pytest
```

Run tests for a single Lambda:

```bash
cd modules/<lambda_name>
uv run pytest tests/
```

## Linting and Type Checks

```bash
# From fluxion-backend/
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict modules/_template/src/
```

## Building Container Images

Build the resolver base image:

```bash
docker build -f Dockerfile.resolver -t fluxion-backend/resolver-base:latest .
```

Build a specific Lambda image (from the Lambda directory):

```bash
cd modules/<lambda_name>
docker build -t fluxion-backend/<lambda_name>:latest .
```

## Database Migrations

```bash
# Apply all pending migrations
DATABASE_URI=postgresql://user:pass@host/dbname \
  alembic -c migrations/alembic.ini upgrade head

# Generate a new migration
DATABASE_URI=postgresql://user:pass@host/dbname \
  alembic -c migrations/alembic.ini revision --autogenerate -m "describe_change"
```

## References

- [`docs/module-structure.md`](../docs/module-structure.md) — layout and ownership rules
- [`docs/design-patterns.md`](../docs/design-patterns.md) — resolver, repository, FSM patterns
- [`docs/code-standards.md`](../docs/code-standards.md) — Python rules, import style, SQL rules
