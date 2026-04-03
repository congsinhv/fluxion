# Lambda datasources — conditionally created when ARN is provided.
# When compute module (#34-36) wires Lambda ARNs, datasources auto-create.

locals {
  lambda_datasources = {
    for k, v in {
      device   = var.device_resolver_arn
      platform = var.platform_resolver_arn
      user     = var.user_resolver_arn
      action   = var.action_resolver_arn
      upload   = var.upload_resolver_arn
      chat     = var.chat_resolver_arn
    } : k => v if v != ""
  }
}

resource "aws_appsync_datasource" "lambda" {
  for_each         = local.lambda_datasources
  api_id           = aws_appsync_graphql_api.main.id
  name             = "fluxion_${each.key}_resolver"
  type             = "AWS_LAMBDA"
  service_role_arn = aws_iam_role.appsync_lambda.arn

  lambda_config {
    function_arn = each.value
  }
}

# NONE datasource for internal pass-through mutations (notify* → subscriptions)
resource "aws_appsync_datasource" "none" {
  api_id = aws_appsync_graphql_api.main.id
  name   = "NONE_DS"
  type   = "NONE"
}
