# AppSync GraphQL API with dual authentication:
# 1. AMAZON_COGNITO_USER_POOLS (default) — UI queries/mutations via JWT
# 2. AWS_IAM (additional) — internal Lambda mutations (notify*)

resource "aws_appsync_graphql_api" "main" {
  name                = "fluxion-api-${var.environment}"
  authentication_type = "AMAZON_COGNITO_USER_POOLS"

  user_pool_config {
    user_pool_id  = var.cognito_user_pool_id
    aws_region    = var.region
    default_action = "ALLOW"
  }

  additional_authentication_provider {
    authentication_type = "AWS_IAM"
  }

  schema = file(var.schema_path)

  log_config {
    cloudwatch_logs_role_arn = aws_iam_role.appsync_logging.arn
    field_log_level          = "ERROR"
  }

  xray_enabled = true

  tags = { Name = "fluxion-api-${var.environment}" }
}
