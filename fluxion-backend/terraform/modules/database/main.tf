# Database module entry point.
# Resources are split by category per module-structure.md §7 (>300 LOC → split):
#   secret.tf  — random_password, Secrets Manager secret + version
#   rds.tf     — DB subnet group, RDS instance
#   proxy.tf   — IAM role/policy, RDS Proxy + target group + target (conditional)

locals {
  common_tags = {
    Project   = "fluxion"
    Env       = var.env
    ManagedBy = "terraform"
  }
}
