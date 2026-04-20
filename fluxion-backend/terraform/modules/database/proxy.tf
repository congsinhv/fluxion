# RDS Proxy: IAM role + policy, proxy, target group, target.
# All resources gated by var.enable_rds_proxy (count = 0 when disabled).
# Proxy adds ~$22/mo for t3.micro (2 vCPU × $0.015/vCPU-hr × 730hr); disabled by default.

resource "aws_iam_role" "proxy" {
  count = var.enable_rds_proxy ? 1 : 0

  name        = "${var.resource_name_prefix}-rds-proxy-role"
  description = "Allows RDS Proxy to retrieve DB credentials from Secrets Manager."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "rds.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "proxy" {
  count = var.enable_rds_proxy ? 1 : 0

  name = "${var.resource_name_prefix}-rds-proxy-policy"
  role = aws_iam_role.proxy[0].id

  # Least-privilege: only GetSecretValue on the specific DB credentials secret.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.main.arn
      }
    ]
  })
}

resource "aws_db_proxy" "main" {
  count = var.enable_rds_proxy ? 1 : 0

  name                   = "${var.resource_name_prefix}-db-proxy"
  debug_logging          = false
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = true
  role_arn               = aws_iam_role.proxy[0].arn
  vpc_subnet_ids         = var.private_subnet_ids
  vpc_security_group_ids = [var.rds_proxy_sg_id]

  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.main.arn
  }

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-db-proxy"
  })
}

resource "aws_db_proxy_default_target_group" "main" {
  count = var.enable_rds_proxy ? 1 : 0

  db_proxy_name = aws_db_proxy.main[0].name

  connection_pool_config {
    max_connections_percent = 100
  }
}

resource "aws_db_proxy_target" "main" {
  count = var.enable_rds_proxy ? 1 : 0

  db_proxy_name          = aws_db_proxy.main[0].name
  target_group_name      = aws_db_proxy_default_target_group.main[0].name
  db_instance_identifier = aws_db_instance.main.identifier
}
