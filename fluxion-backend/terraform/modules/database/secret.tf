# Secrets Manager: random password generation + secret storage for RDS credentials.
# The secret is consumed by the app at runtime and by RDS Proxy for connection auth.

resource "random_password" "main" {
  length  = 32
  special = true
  # Exclude chars that break PostgreSQL URL encoding or JSON: / @ " space \ '
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "main" {
  name        = "${var.resource_name_prefix}/db/credentials"
  description = "RDS master credentials for ${var.resource_name_prefix} PostgreSQL instance."

  # recovery_window=0 allows immediate deletion during `terraform destroy` in dev.
  # staging/prod should use the default (30 days).
  recovery_window_in_days = 0

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "main" {
  secret_id = aws_secretsmanager_secret.main.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.main.result
  })
}
