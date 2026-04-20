# Fluxion

AWS serverless MDM platform for the Vietnamese installment / rental phone market.

## Repository Layout

```
fluxion/
├── fluxion-backend/          Python 3.12 Lambda resolvers (AppSync, DB migrations)
├── fluxion-oem-processor/    Python 3.12 Lambda workers (APNS, OEM integrations)
├── fluxion-frontend/         React 19 + Vite + TypeScript admin console
├── docs/                     Foundation docs (code standards, patterns, module layout, testing)
├── plans/                    Implementation plans (gitignored — local only)
├── .github/workflows/        CI — per-sub-repo lint + test
├── docker-compose.yml        Local dev (PostgreSQL 16 + LocalStack)
├── .pre-commit-config.yaml   Hooks: ruff, prettier, eslint, commitlint
├── commitlint.config.js      Enforces `[#<ticket>]: subject` commit format
└── .editorconfig             Editor defaults
```

Each sub-repo owns its own `terraform/` directory — no monorepo-root IaC.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12 | `uv python install 3.12` |
| [uv](https://docs.astral.sh/uv/) | 0.5.x | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Bun](https://bun.sh/) | 1.1.x | `curl -fsSL https://bun.sh/install \| bash` |
| [Terraform](https://www.terraform.io/) | ≥ 1.10 | `brew install terraform` (S3-native locking requires 1.10+) |
| Docker | recent | `brew install --cask docker` |
| [pre-commit](https://pre-commit.com/) | 4.x | `uv tool install pre-commit` |

## Quick Start

```bash
git clone <repo> && cd fluxion
cp .env.example .env                          # adjust if needed

# One-time hooks install
pre-commit install
pre-commit install --hook-type commit-msg

# Local dev services (Postgres + LocalStack)
docker compose up -d

# Backend
cd fluxion-backend && uv sync && cd ..

# OEM processor
cd fluxion-oem-processor && uv sync && cd ..

# Frontend
cd fluxion-frontend && bun install && cd ..
```

## Development Commands

### fluxion-backend (and fluxion-oem-processor)

```bash
uv sync                  # install deps
uv run ruff format .     # format
uv run ruff check .      # lint
uv run mypy --strict modules/
uv run pytest            # tests + coverage
```

### fluxion-frontend

```bash
bun install
bun run dev              # vite dev server (http://localhost:5173)
bun run format:check     # prettier
bun run lint             # eslint
bun run typecheck        # tsc --noEmit
bun run test             # vitest
bun run build            # production build
```

### Terraform (per sub-repo)

Each sub-repo owns its IaC. Modules are reusable; environments wire them via SSM cross-stack reads.

```bash
cd fluxion-backend/terraform/bootstrap
terraform init && terraform apply -var=resource_name_prefix=fluxion-backend

cd ../envs/dev
terraform init -backend-config="bucket=<from_bootstrap>"
terraform apply
```

**Core modules** (detailed in [docs/module-structure.md §5](docs/module-structure.md#54-existing-modules)):
- `modules/network` — VPC, subnets, fck-nat (t4g.nano), security groups; outputs to SSM for cross-repo use ([#30])

## Commit Convention

Commits use the format `[#<ticket>]: <subject>` (NOT conventional commits).

```
[#29]: scaffold monorepo + dev environment
[#34]: add device enrollment handler
[chore]: bump dependencies            # allowed when no ticket exists
```

Details: [docs/code-standards.md §6.1](docs/code-standards.md#61-commit-message-format).

## Architecture

Tenant-per-schema PostgreSQL multi-tenancy. Each tenant has a dedicated `tenant_{slug}` schema; the `public` schema holds shared registry and global lookup data. Cross-sub-repo contracts flow through SSM Parameter Store (no shared code modules, no Terraform remote state sharing).

Deeper reading:

- [docs/code-standards.md](docs/code-standards.md) — naming, error handling, tooling targets.
- [docs/module-structure.md](docs/module-structure.md) — per-sub-repo layout, Lambda package `src/` pattern.
- [docs/design-patterns.md](docs/design-patterns.md) — 8 architectural patterns (Saga, FSM, Repository, etc.).
- [docs/testing-guide.md](docs/testing-guide.md) — test pyramid, coverage targets, PR checklist.

## License

TBD — currently a graduation thesis project (ĐATN).
