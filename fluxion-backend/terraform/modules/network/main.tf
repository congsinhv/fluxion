# Network module entry point.
# Resources are split by category per module-structure.md §7 (>300 LOC → split):
#   networking.tf   — VPC, IGW, subnets, route tables
#   nat.tf          — fck-nat ENI, EIP, IAM, Launch Template, ASG
#   security-groups.tf — Lambda / RDS Proxy / RDS SG chain

locals {
  common_tags = {
    Project   = "fluxion"
    Env       = var.env
    ManagedBy = "terraform"
  }
}
