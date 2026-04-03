output "rds_endpoint" {
  value = aws_db_instance.main.endpoint
}

output "rds_proxy_endpoint" {
  value = aws_db_proxy.main.endpoint
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "db_username" {
  value = aws_db_instance.main.username
}

output "db_secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}
