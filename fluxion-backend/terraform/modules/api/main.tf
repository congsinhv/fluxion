locals {
  api_name = "${var.resource_name_prefix}-api"
}

# AppSync GraphQL API — primary auth = Cognito User Pools (UI clients).
# Additional auth = IAM (internal checkin-handler Lambda signs SigV4 to invoke
# notify* mutations which drive subscriptions).
resource "aws_appsync_graphql_api" "this" {
  name                = local.api_name
  authentication_type = "AMAZON_COGNITO_USER_POOLS"
  schema              = file(var.schema_path)

  user_pool_config {
    user_pool_id   = var.cognito_user_pool_id
    aws_region     = var.aws_region
    default_action = "DENY" # unauthenticated requests rejected by AppSync
  }

  additional_authentication_provider {
    authentication_type = "AWS_IAM"
  }

  log_config {
    cloudwatch_logs_role_arn = aws_iam_role.appsync_logs.arn
    field_log_level          = var.log_field_log_level
    exclude_verbose_content  = false
  }

  xray_enabled = false

  tags = var.tags
}
