# fluxion-backend — Dev Environment

## Prerequisites

- Bootstrap must be applied first — see `../../bootstrap/README.md`.
- Terraform >= 1.10 installed.
- AWS credentials configured (`aws sts get-caller-identity`).

## Initialise with remote backend

Substitute `<state_bucket>` with the `state_bucket` output from bootstrap
(current value: `fluxion-backend-tfstate`):

```bash
terraform init -backend-config="bucket=<state_bucket>"
```

To force re-initialisation (e.g. after provider updates):

```bash
terraform init -reconfigure -backend-config="bucket=<state_bucket>"
```

## Plan and apply

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars as needed

terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

## Variable file

Copy the example and fill in real values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

**Important:** `terraform.tfvars` contains environment-specific values and must be kept
local — never commit it to version control. It is already listed in the root `.gitignore`.

## Cost estimate

| Component | Monthly cost |
|---|---|
| RDS db.t3.micro (free-tier eligible first 12 months) | ~$0 / ~$15 after |
| fck-nat t4g.nano NAT instance | ~$3-4 |
| Secrets Manager secret | ~$0.40 |
| SSM Parameters (Standard tier) | free |
| **Total (enable_rds_proxy=false)** | **~$4-5/mo** |

Setting `enable_rds_proxy=true` adds ~$22/mo — keep false for dev.

## SSM Parameter Contract

All parameters are published under the prefix `/fluxion/{env}/`.

| Parameter path | Type | Source |
|---|---|---|
| `/fluxion/dev/network/vpc-id` | String | `module.network.vpc_id` |
| `/fluxion/dev/network/private-subnet-ids` | StringList | `module.network.private_subnet_ids` |
| `/fluxion/dev/network/public-subnet-ids` | StringList | `module.network.public_subnet_ids` |
| `/fluxion/dev/network/lambda-sg-id` | String | `module.network.lambda_sg_id` |
| `/fluxion/dev/rds/endpoint` | String | `module.database.effective_endpoint` (hostname only) |
| `/fluxion/dev/rds/port` | String | `module.database.db_port` |
| `/fluxion/dev/rds/secret-arn` | String | `module.database.secret_arn` |

### Consumer pattern (OEM processor / Lambda)

Use `data "aws_ssm_parameter"` to read values without hard-coding:

```hcl
data "aws_ssm_parameter" "vpc_id" {
  name = "/fluxion/dev/network/vpc-id"
}

data "aws_ssm_parameter" "private_subnet_ids" {
  name = "/fluxion/dev/network/private-subnet-ids"
}

data "aws_ssm_parameter" "rds_secret_arn" {
  name            = "/fluxion/dev/rds/secret-arn"
  with_decryption = false  # ARN is not encrypted, just a string
}
```

## Destroy warning

**Always destroy the dev environment when not in use to avoid unnecessary AWS charges.**

```bash
terraform destroy
```

RDS has a final snapshot skipped (`skip_final_snapshot = true` in dev) so destroy completes
without manual snapshot cleanup. Run destroy at the end of each dev session.

## Notes

- Module wiring added in ticket #30 (network + database). Further modules (#31 migrations,
  #32 Cognito + CI/CD, #33 AppSync) will extend `main.tf`.
- State is stored remotely in S3 with S3-native locking (`use_lockfile = true`).
  No DynamoDB table is required.
- `effective_endpoint` resolves to the RDS proxy endpoint when `enable_rds_proxy=true`,
  otherwise the direct RDS instance address. Always use SSM to read this — never hard-code.
