output "vpc_id" {
  description = "ID of the VPC."
  value       = module.network.vpc_id
}

output "rds_endpoint" {
  description = "Effective RDS endpoint (proxy when enabled, direct address otherwise)."
  value       = module.database.effective_endpoint
}

output "rds_secret_arn" {
  description = "ARN of the Secrets Manager secret holding DB credentials."
  value       = module.database.secret_arn
  sensitive   = true
}

output "ssm_prefix" {
  description = "SSM Parameter Store path prefix for this environment."
  value       = local.ssm_prefix
}
