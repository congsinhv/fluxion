# modules/network

Provisions the core network layer for a Fluxion environment:

- **VPC** (`10.0.0.0/16` default) with DNS hostnames enabled
- **2 public subnets** + **2 private subnets** across 2 AZs
- **Internet Gateway** + public route table
- **fck-nat** ([fck-nat.dev](https://fck-nat.dev)) — ARM t4g.nano ASG (size=1) with a static ENI + EIP; ~$3/mo vs $32/mo for Managed NAT Gateway
- **Private route table** pointing to the NAT ENI
- **3 Security Groups** forming the Lambda → RDS Proxy → RDS ingress chain

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `resource_name_prefix` | `string` | — | Prefix for all resource names (e.g. `fluxion-dev`) |
| `env` | `string` | — | Deployment environment: `dev`, `staging`, `prod` |
| `vpc_cidr` | `string` | `10.0.0.0/16` | VPC CIDR block |
| `azs` | `list(string)` | `["ap-southeast-1a","ap-southeast-1b"]` | AZs (exactly 2, index-aligned with subnet CIDRs) |
| `public_subnet_cidrs` | `list(string)` | `["10.0.0.0/24","10.0.1.0/24"]` | Public subnet CIDRs |
| `private_subnet_cidrs` | `list(string)` | `["10.0.10.0/24","10.0.11.0/24"]` | Private subnet CIDRs |
| `fck_nat_instance_type` | `string` | `t4g.nano` | EC2 instance type for NAT (ARM Graviton) |

## Outputs

| Name | Description |
|---|---|
| `vpc_id` | VPC ID |
| `vpc_cidr_block` | VPC CIDR block |
| `public_subnet_ids` | List of public subnet IDs |
| `private_subnet_ids` | List of private subnet IDs |
| `lambda_sg_id` | Security group ID for Lambda functions |
| `rds_sg_id` | Security group ID for RDS instances |
| `rds_proxy_sg_id` | Security group ID for RDS Proxy |
| `nat_eip` | Public IP of the NAT EIP (for debugging / allowlisting) |

## SSM Naming Convention

The `envs/dev` environment exports network outputs to SSM Parameter Store under:

```
/fluxion/{env}/network/vpc-id
/fluxion/{env}/network/vpc-cidr
/fluxion/{env}/network/public-subnet-ids     # comma-separated list
/fluxion/{env}/network/private-subnet-ids    # comma-separated list
/fluxion/{env}/network/lambda-sg-id
/fluxion/{env}/network/rds-sg-id
/fluxion/{env}/network/rds-proxy-sg-id
/fluxion/{env}/network/nat-eip
```

Other sub-repos consume these via `data "aws_ssm_parameter"` — never via shared Terraform state.

## Security Group Chain

```
Lambda (sg-lambda)
  │ egress: 0.0.0.0/0 all
  │
  ├──► RDS Proxy (sg-rds-proxy)
  │      ingress: tcp 5432 from sg-lambda
  │
  └──► RDS (sg-rds)
         ingress: tcp 5432 from sg-lambda       ← proxy-off path
         ingress: tcp 5432 from sg-rds-proxy    ← proxy-on path
```

## Example Usage

```hcl
module "network" {
  source = "../../modules/network"

  resource_name_prefix = "fluxion-dev"
  env                  = "dev"

  # All other vars use defaults (ap-southeast-1, 10.0.0.0/16, t4g.nano)
}

# Wire outputs to SSM for cross-stack consumption
resource "aws_ssm_parameter" "vpc_id" {
  name  = "/fluxion/dev/network/vpc-id"
  type  = "String"
  value = module.network.vpc_id
}
```

## Notes

- fck-nat runs in **public AZ-a only** (single-AZ by design for dev cost savings). Private subnets in AZ-b route through the same NAT ENI — acceptable SPOF for dev.
- The NAT ENI (`aws_network_interface.nat`) is **static** — it survives ASG instance recycling. The fck-nat boot script attaches it via `/etc/fck-nat.conf` → `fck-nat.service`.
- SSM AMI path: `/aws/service/fck-nat/fck-nat-al2023-arm64-latest/amzn2023` — verify with `aws ssm get-parameter --name <path>` if `terraform plan` reports a data source error.
- `terraform validate` requires a root module context — run it from `envs/dev/` in Phase 3, not here.
