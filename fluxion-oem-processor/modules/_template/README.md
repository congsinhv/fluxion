# _template — OEM Worker Lambda

Scaffold for a new OEM worker Lambda. Copy and rename; do not deploy _template directly.

## Copy + rename steps

```bash
# 1. Copy the template
cp -r modules/_template modules/<new_worker_name>
cd modules/<new_worker_name>

# 2. Update pyproject.toml — change the project name
#    NOTE: dir name uses _template (underscore prefix OK for dirs) but pyproject.toml
#    uses "oem-worker-template" because PEP 625 forbids underscore-prefix package names.
#    New workers should use a descriptive name without leading underscores.
sed -i '' 's/name = "oem-worker-template"/name = "<new_worker_name>"/' pyproject.toml

# 3. Update the service name default in src/config.py
#    Change: POWERTOOLS_SERVICE_NAME = os.environ.get("POWERTOOLS_SERVICE_NAME", "_template")
#    To:     POWERTOOLS_SERVICE_NAME = os.environ.get("POWERTOOLS_SERVICE_NAME", "<new_worker_name>")

# 4. Replace the NotImplementedError stub in src/handler.py with real logic

# 5. Update the Dockerfile CMD if the handler function name changes
```

Module dir name **must be snake_case** (AWS Lambda handler import requirement — see docs/code-standards.md §2.1).

## Running tests locally

```bash
cd modules/_template
uv run pytest tests/ -v
```

## Lint + type-check

```bash
# From repo root
uv run ruff format --check modules/_template/
uv run ruff check modules/_template/
uv run mypy --strict modules/_template/src/
```
