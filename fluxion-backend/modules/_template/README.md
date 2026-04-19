# _template — Lambda Module Template

Copy this directory to create a new Lambda resolver or worker.

## Copy and Rename

```bash
cp -r modules/_template modules/<new_name>
cd modules/<new_name>
```

Then apply these changes:

1. **`pyproject.toml`** — rename `name = "_template"` → `name = "<new_name>"`
2. **`src/config.py`** — update `POWERTOOLS_SERVICE_NAME` default to `"<new_name>"`;
   uncomment and rename required env var constants (`DATABASE_URI`, topic ARNs, etc.)
3. **`src/handler.py`** — replace the `NotImplementedError` stub with real field
   dispatch (AppSync) or SQS record loop (worker). Keep it ≤ 50 LOC.
4. **`Dockerfile`** — update the base image tag if using a worker base:
   `FROM fluxion-backend/worker-base:latest`
5. **`src/db.py`** — add repository classes for this Lambda's data access needs.
   See `design-patterns.md §5` for the Repository pattern.
6. **`src/exceptions.py`** — add Lambda-specific error subclasses.
7. **`tests/`** — replace the smoke test with real unit/integration tests.

## Structure

```
<new_name>/
├── src/
│   ├── __init__.py       # empty
│   ├── handler.py        # Lambda entry point (≤ 50 LOC)
│   ├── config.py         # env vars + logger (single source of truth)
│   ├── helpers.py        # module-local utilities
│   ├── db.py             # SQLAlchemy Connection + repositories
│   ├── exceptions.py     # FluxionError subclasses
│   └── const.py          # event key constants
├── tests/
│   ├── conftest.py       # env fixtures
│   └── test_*.py
├── pyproject.toml        # runtime deps + pytest config
└── Dockerfile            # inherits from resolver-base or worker-base
```

## Import Style

Imports within `src/` use **no `src.` prefix**:

```python
from config import logger       # correct
from src.config import logger   # wrong — breaks in Lambda runtime
```

This mirrors how the Lambda runtime sees the package: `src/` contents are
copied flat into `LAMBDA_TASK_ROOT` by the Dockerfile. The `pyproject.toml`
sets `pythonpath = ["src"]` so pytest resolves imports the same way.

## Running Tests

```bash
cd modules/<new_name>
uv run pytest tests/
```

## References

- `docs/module-structure.md §2.2` — Lambda package layout rules
- `docs/design-patterns.md §4` — Resolver pattern (handler structure)
- `docs/design-patterns.md §5` — Repository pattern (db.py structure)
- `docs/code-standards.md §3.5` — Import rules
