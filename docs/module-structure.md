# Module Structure

> **Version:** v1.0
> **Audience:** Fluxion contributors scaffolding or reorganizing modules.
> **Authority:** Source of truth for directory layout. Pairs with [code-standards.md](code-standards.md) (file naming) and [design-patterns.md](design-patterns.md) (intra-module patterns).
> **Principles:** YAGNI — ship only dirs with real files. KISS — flat beats nested until it hurts.

---

## 1. Monorepo Top-Level

```
fluxion/
├── fluxion-frontend/       React 19 SPA (admin console) — own terraform/
├── fluxion-backend/        Python Lambda resolvers — own terraform/
├── fluxion-oem/            Python Lambda workers for OEM integrations (APNS, future Samsung/Xiaomi) — own terraform/
├── docs/                   Foundation docs (this document lives here)
├── plans/                  Implementation plans + reports
├── .github/                CI/CD workflows, PR templates, issue templates
└── README.md               Entry point + quick start
```

**Rules:**

- One language runtime per sub-repo. `fluxion-frontend/` is TypeScript only; `fluxion-backend/` and `fluxion-oem/` are Python only.
- Cross-repo sharing happens through **contracts**, not imports: GraphQL schema, SQS event schemas (JSON Schema / Pydantic models re-declared per consumer), SSM parameters.
- **Per-sub-repo IaC.** Each `fluxion-*` repo owns its own `terraform/` dir — deploys its own stack independently.
- **No shared code dirs.** Each Lambda is self-contained; cross-cutting concerns (logging, auth decorators, error base classes) are copied per Lambda. Avoids coupling + deployment-order issues.
- No root-level source files beyond `README.md`. Root is a workspace, not a module.

---

## 2. fluxion-backend (Python 3.12 Lambda + AppSync + Alembic)

Backend hosts AppSync GraphQL resolvers and command-pipeline Lambdas that write to PostgreSQL.

### 2.1 Top-Level Layout

```
fluxion-backend/
├── modules/
│   ├── device_resolver/          # Lambda package — AppSync resolver
│   ├── action_resolver/          # Lambda package
│   ├── upload_resolver/          # Lambda package
│   ├── action_trigger/           # Lambda package — SNS → SQS dispatcher
│   ├── checkin_handler/          # Lambda package — MDM check-in consumer
│   ├── message_template_resolver/
│   └── tac_resolver/
├── terraform/                    # IaC — modules + environments (see §5)
├── migrations/                   # Alembic environment
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       ├── 0001_create_tenant_tables.py
│       ├── 0042_add_tacs_table.py
│       └── ...
├── pyproject.toml                # Single root project; workspaces via tool.uv or tool.poetry groups
└── README.md
```

### 2.2 Lambda Package Layout

Each Lambda function is a Python package. Directory name **must be snake_case** to satisfy AWS Lambda handler import resolution (see [code-standards.md §2.1](code-standards.md#21-file-naming)).

```
fluxion-backend/modules/device_resolver/
├── __init__.py
├── handler.py                    # Lambda entry (≤ 50 LOC)
├── config.py                     # Env var parsing, constants
├── helpers.py                    # Module-local utilities
├── db.py                         # Data access (psycopg2 / SQLAlchemy)
├── errors.py                     # Domain errors (FluxionError subclasses)
├── pyproject.toml                # Per-Lambda dependencies
├── Dockerfile                    # Container image (inherits from Dockerfile.resolver)
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_*.py
```

**Rules:**

- `handler.py` ≤ 50 LOC. Parse event → Pydantic → delegate → serialize. No business logic.
- One logical concern per file. Split when a file crosses 200 LOC (see §2.3).
- Each Lambda is **self-contained** — no imports from sibling modules. Copy common utilities when needed; rely on AWS Lambda Layers or post-build bundling only if duplication becomes painful (document the exception).
- Tests live inside the Lambda package in `tests/` — colocated, not in a sibling tree. Self-contained packaging (exclude `tests/` via Dockerfile / zip).
- `__init__.py` stays empty unless re-exporting intentional public API.

### 2.3 When to Split a File

| Trigger | Action |
|---------|--------|
| File > 200 LOC | Split by concern (queries vs mutations, read vs write, public vs internal). |
| Two distinct responsibilities in one file | Split even under 200 LOC. |
| Circular import detected | Break the cycle by moving the shared type into the consumer that makes more semantic sense, or duplicate the definition (since each Lambda is self-contained). |

---

## 3. fluxion-oem (Python 3.12 — OEM worker Lambdas)

OEM workers consume SQS events and talk to vendor-specific APIs (Apple APNS today; Samsung Knox, Xiaomi in future).

### 3.1 Top-Level Layout

```
fluxion-oem/
├── modules/
│   └── apple_process_action/     # Lambda package — Apple MDM / APNS worker
├── terraform/                    # IaC — modules + environments (see §5)
├── pyproject.toml
└── README.md
```

Lambda package layout identical to backend (see §2.2). Additional OEM providers (Samsung Knox, Xiaomi) will be new sibling packages under `modules/`.

---

## 4. fluxion-frontend (React 19 + TypeScript 5.x + Vite + Tailwind 4)

Admin console for tenant operators. Feature-based organization, Amplify v6 for GraphQL calls.

### 4.1 Top-Level Layout

```
fluxion-frontend/
├── src/
│   ├── features/                     # Business features (primary organization)
│   │   ├── devices/
│   │   ├── actions/
│   │   ├── chat/
│   │   ├── message-templates/
│   │   └── tacs/
│   ├── components/
│   │   └── ui/                       # shadcn/ui primitives (Button, Dialog, Table)
│   ├── hooks/                        # Cross-feature hooks only
│   ├── lib/                          # Cross-feature utilities (format-date.ts, api-client.ts)
│   ├── services/                     # API gateway, Amplify client wrapper
│   ├── types/                        # Shared types (generated from GraphQL schema)
│   ├── routes/                       # TanStack Router route tree
│   ├── App.tsx
│   └── main.tsx
├── public/
├── terraform/
├── tests/
│   └── e2e/                          # Playwright E2E tests
├── tsconfig.json                     # "@/*" → "./src/*"
├── vite.config.ts                    # alias mirror of tsconfig paths
├── tailwind.config.ts
├── package.json
└── README.md
```

### 4.2 Feature Module Layout

```
fluxion-frontend/src/features/devices/
├── components/
│   ├── DeviceTable.tsx               # PascalCase — React component
│   ├── DeviceDetailPanel.tsx
│   └── EnrollmentForm.tsx
├── hooks/
│   ├── use-device-list.ts            # kebab-case — hook
│   └── use-enrollment-mutation.ts
├── services/
│   └── device-service.ts             # API calls wrapping Amplify client
├── types/
│   └── device-types.ts               # feature-local types (exports are PascalCase)
├── __tests__/
│   ├── DeviceTable.test.tsx
│   └── use-device-list.test.ts
└── index.ts                          # Public exports only (what other features may import)
```

### 4.3 Import Rules

- **Always via alias.** `import { DeviceTable } from "@/features/devices";` — never `"../../features/devices"`.
- **Cross-feature imports go through `index.ts`.** Deep imports (`@/features/devices/components/DeviceTable`) are forbidden — they bypass the public contract.
- **Shared code in `lib/` or `components/ui/`** is fair game from anywhere.
- **No circular feature deps.** If `features/actions` needs `features/devices`, extract the shared piece to `lib/` or `types/`.

---

## 5. terraform/ (Per-Sub-Repo IaC)

Each `fluxion-*` repo owns its own `terraform/` directory. No monorepo-root IaC. Cross-stack dependencies flow through **SSM parameters** (or remote state data sources), not shared code.

### 5.1 Per-Repo Scope

| Repo | Terraform owns |
|------|---------------|
| `fluxion-backend/terraform/` | AppSync API, RDS + Proxy, Cognito, Lambda resolvers (ECR repos), SNS/SQS for command pipeline |
| `fluxion-oem/terraform/` | OEM worker Lambdas (ECR repos), SQS consumer queues, APNS secret rotation |
| `fluxion-frontend/terraform/` | CloudFront, S3 static hosting, WAF, ACM cert, Route53 record |

Shared primitives (VPC, base networking, IAM roles) live in whichever repo boots them **first** (typically `fluxion-backend`); other repos consume via `data "aws_ssm_parameter"` or `data "terraform_remote_state"`.

### 5.2 Layout (applies to every sub-repo's `terraform/`)

```
<sub-repo>/terraform/
├── modules/
│   ├── <module-name>/                # Reusable module
│   │   ├── main.tf                   # Resource declarations
│   │   ├── variables.tf              # Typed inputs
│   │   ├── outputs.tf                # Exported values
│   │   ├── locals.tf                 # Computed values
│   │   ├── versions.tf               # Provider + terraform version pinning
│   │   ├── <component>.tf            # Split large main.tf by resource category
│   │   └── README.md                 # Inputs / Outputs / Example usage
│   └── ...
├── envs/
│   ├── dev/
│   │   ├── main.tf                   # Module wiring
│   │   ├── backend.tf                # S3 + DynamoDB lock config
│   │   └── terraform.tfvars          # Env-specific values
│   ├── staging/
│   └── prod/
└── README.md
```

### 5.3 Rules

- **Modules are reusable; environments wire them.** A module does not know which environment it runs in.
- **No hardcoded account IDs or region literals** inside modules — pass as variables.
- **State backends are per-environment**, locked via DynamoDB. Each sub-repo uses its own state bucket path (`s3://fluxion-tf-state/<repo>/<env>/`).
- **Cross-repo dependencies via SSM:** producing repo writes an `aws_ssm_parameter`; consuming repo reads via `data "aws_ssm_parameter"`. Never share Terraform state.
- **`main.tf` > 300 LOC** → split by resource category (`iam.tf`, `networking.tf`) or extract a sub-module.
- **README required** on every module. Use `terraform-docs` to auto-generate Inputs/Outputs tables.

### 5.4 Existing Modules

#### `fluxion-backend/terraform/modules/network` ([#30])

Provisions the core networking layer for Fluxion environments. Managed by a single environment (`envs/dev`); others inherit via SSM cross-stack reads.

**Resources:**
- VPC + DNS hostnames (default `10.0.0.0/16`)
- 2 public + 2 private subnets (one pair per AZ, 2 AZs fixed)
- Internet Gateway + public route table
- **fck-nat** ARM instance (t4g.nano, ~$3/mo) with static ENI + EIP as NAT replacement (vs. $32/mo AWS-managed NAT Gateway)
- Private route table routing outbound traffic through NAT ENI
- 3 security groups: Lambda → RDS Proxy → RDS ingress chain

**SSM exports:** `/fluxion/{env}/network/{vpc-id, vpc-cidr, public/private-subnet-ids, lambda-sg-id, rds-sg-id, rds-proxy-sg-id, nat-eip}`

**Sub-files:**
- `networking.tf` — VPC, subnets, route tables, IGW
- `nat.tf` — fck-nat instance, ENI, EIP, ASG
- `security-groups.tf` — Lambda, RDS Proxy, RDS SGs and ingress rules

**Example usage:** See module README (envs/dev wires it; see Phase 3 of [#30]).

---

## 6. Cross-Stack Contracts

When two sub-repos must agree on a shape, the contract lives outside both:

| Contract | Location | Consumer |
|----------|----------|----------|
| GraphQL schema | `fluxion-backend/schema.graphql` (root of backend repo) | Frontend codegen input |
| SQS event payloads | Re-declared as Pydantic models inside each consuming Lambda's `dto.py` | OEM workers, checkin_handler |
| SSM parameters | Written by producing repo's Terraform; read via `data "aws_ssm_parameter"` | Other sub-repos' Terraform (cross-stack wiring) |
| Lambda env vars | `<sub-repo>/terraform/modules/<lambda>/variables.tf` | Lambda runtime via `os.environ` |

**Rule:** when a contract changes, update it in one place first, then update consumers in a separate commit. Never co-mingle contract change with consumer change — makes review and rollback harder.

**No `shared/` module.** SQS event schemas are intentionally duplicated across consumers — each Lambda owns its own DTO definition. Schema drift is caught by contract tests (see [testing-guide.md](testing-guide.md)), not by a shared import.

---

## 7. File Size Enforcement

| File type | Max LOC | When over limit |
|-----------|---------|-----------------|
| Python module (non-handler) | 200 | Split by concern. |
| Python Lambda `handler.py` | 50 | Extract to sibling module. |
| React component | 150 | Extract sub-components or custom hook. |
| React hook | 100 | Extract helper utilities. |
| Terraform `main.tf` | 300 | Split by resource category or extract sub-module. |
| Tests | 300 | Split by behavior group. |
| Markdown docs | 800 | Split by topic (current file already under this limit). |

LOC counted excludes blank lines, imports, and top-level docstrings.

---

## 8. When to Deviate

Structure rules exist to reduce churn, not to gatekeep. Deviate when **documented** in a PR description:

- Prototyping a new Lambda? A single `handler.py` > 50 LOC is fine during spike — note intent to split before merge.
- One-off script that does not import anywhere else? Flat `scripts/` dir at sub-repo root is fine.
- Experimental OEM integration? Temporary `experimental/` dir within `fluxion-oem/modules/` is acceptable until graduated.

Deviations must not leak into tests or contracts — those follow the rules strictly.

---

## 9. References

- [code-standards.md](code-standards.md) — file naming, general rules.
- [design-patterns.md](design-patterns.md) — intra-module patterns (resolver, repository, factory).
- [testing-guide.md](testing-guide.md) — test file placement.
- `fluxion-backend/terraform/modules/network/README.md` — network module design (VPC, subnets, fck-nat).
- **Wiki T4** — System architecture design (module boundaries visualized).
- **Wiki T5** — API contract and ER diagram (informs schema and migration layout).
- Research: [researcher-260419-1545-file-naming-conventions-2026.md](../plans/reports/researcher-260419-1545-file-naming-conventions-2026.md).

---

## 10. Change Log

| Version | Date | Change |
|---------|------|--------|
| v1.1 | 2026-04-20 | Document Terraform modules section (§5.4); add network module reference (#30). |
| v1.0 | 2026-04-19 | Initial release (#61). |
