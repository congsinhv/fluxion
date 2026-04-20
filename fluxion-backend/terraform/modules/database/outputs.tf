output "db_instance_id" {
  description = "Identifier of the RDS DB instance."
  value       = aws_db_instance.main.id
}

output "db_endpoint" {
  description = "Direct writer endpoint of the RDS instance (host:port)."
  value       = aws_db_instance.main.endpoint
}

output "db_port" {
  description = "Port the RDS instance listens on (5432 for PostgreSQL)."
  value       = aws_db_instance.main.port
}

output "proxy_endpoint" {
  description = "Endpoint of the RDS Proxy. null when enable_rds_proxy=false."
  value       = one(aws_db_proxy.main[*].endpoint)
}

output "effective_endpoint" {
  description = "Recommended endpoint for consumers: proxy endpoint when enabled, otherwise direct RDS address."
  value       = var.enable_rds_proxy ? aws_db_proxy.main[0].endpoint : aws_db_instance.main.address
}

output "secret_arn" {
  description = "ARN of the Secrets Manager secret holding DB credentials (username + password JSON)."
  value       = aws_secretsmanager_secret.main.arn
  sensitive   = true
}

output "secret_name" {
  description = "Name of the Secrets Manager secret (use for IAM resource scope or SDK lookup)."
  value       = aws_secretsmanager_secret.main.name
}
