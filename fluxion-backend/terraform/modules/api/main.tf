locals {
  api_name = "${var.resource_name_prefix}-api"

  default_tags = {
    Project   = "fluxion"
    Env       = var.env
    ManagedBy = "terraform"
    Component = "appsync-api"
  }

  tags = merge(local.default_tags, var.tags)
}

# AppSync GraphQL API — primary auth = Cognito User Pools (UI clients).
# Additional auth = IAM (internal checkin-handler Lambda signs SigV4 to invoke
# notify* mutations which drive subscriptions).
resource "aws_appsync_graphql_api" "this" {
  name                = local.api_name
  authentication_type = "AMAZON_COGNITO_USER_POOLS"
  schema              = file(var.schema_path)

  user_pool_config {
    user_pool_id = var.cognito_user_pool_id
    aws_region   = var.aws_region
    # Must be ALLOW when additional auth providers are configured — AppSync
    # rejects DENY in that case. Security is preserved: requests still need
    # either a valid Cognito JWT OR SigV4 IAM signature; unauth requests
    # match neither and are rejected with UnauthorizedException.
    default_action = "ALLOW"
  }

  additional_authentication_provider {
    authentication_type = "AWS_IAM"
  }

  log_config {
    cloudwatch_logs_role_arn = aws_iam_role.appsync_logs.arn
    field_log_level          = var.log_field_log_level
    exclude_verbose_content  = var.log_exclude_verbose_content
  }

  xray_enabled = false

  tags = local.tags
}
