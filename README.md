# Fluxion MDM

Cloud-Native Mobile Device Management (MDM) System.

**Graduation thesis** — Vo Cong Sinh, UTC2.

## Architecture

3-layer serverless on AWS (Event-Driven Architecture):

- **UI Layer** — React 19 + Tailwind CSS 4 + shadcn/ui
- **BE Layer** — AppSync + Lambda Resolvers/Workers + RDS PostgreSQL 16
- **OEM Layer** — API Gateway + Lambda (Apple MDM integration)

## Prerequisites

- Python 3.12+
- [Poetry](https://python-poetry.org/)
- [Bun](https://bun.sh/)
- [Terraform](https://www.terraform.io/) 1.0+
- [Docker](https://www.docker.com/)

## Quick Start

```bash
# Backend (includes local PostgreSQL + AppSync schema)
cd fluxion-backend
docker compose up -d
poetry install
poetry run ruff check .
poetry run pytest

# OEM Processor
cd fluxion-oem-processor
poetry install
poetry run ruff check .

# Frontend
cd fluxion-frontend
bun install
bun run lint
bun run build
```

## Project Structure

```
fluxion/
├── fluxion-backend/        # Python — Resolvers, Workers, DB, AppSync schema, Terraform
├── fluxion-oem-processor/  # Python — Apple MDM integration + Terraform
├── fluxion-frontend/       # React 19 + Vite + Tailwind + shadcn/ui + Terraform
├── .github/workflows/      # CI/CD
└── README.md
```

## Development

| Service | Lint | Test | Build |
|---------|------|------|-------|
| Backend | `poetry run ruff check .` | `poetry run pytest` | `docker build modules/<name>` |
| OEM | `poetry run ruff check .` | `poetry run pytest` | `docker build apple_process_action` |
| Frontend | `bun run lint` | `bun run test` | `bun run build` |

## Terraform

Each service manages its own infrastructure:

```bash
cd <service>/infra
terraform init
terraform plan
terraform apply
```

Deployment order: **backend** → **OEM** → **frontend**

## Wiki

Full design documentation: [Fluxion Wiki](https://github.com/congsinhv/fluxion/wiki)
