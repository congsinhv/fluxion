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

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID."
  value       = module.auth.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito admin-console app client ID."
  value       = module.auth.client_id
}

output "cognito_issuer_url" {
  description = "OIDC issuer URL for the Cognito pool (JWT verification)."
  value       = module.auth.issuer_url
}
