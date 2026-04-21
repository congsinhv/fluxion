# One Lambda data source per populated key in var.lambda_resolver_arns.
# AppSync data source names allow [A-Za-z_0-9], so underscore keys work as-is.
resource "aws_appsync_datasource" "lambda" {
  for_each = var.lambda_resolver_arns

  api_id           = aws_appsync_graphql_api.this.id
  name             = "${each.key}_resolver"
  type             = "AWS_LAMBDA"
  service_role_arn = aws_iam_role.appsync_lambda_invoke.arn

  lambda_config {
    function_arn = each.value
  }
}

# Passthrough NONE data source backing the internal notify* mutations.
# Lets SigV4-signed callers (checkin-handler Lambda) publish events that
# AppSync fans out to subscribers via @aws_subscribe — without the trip
# through another resolver Lambda.
resource "aws_appsync_datasource" "notify_passthrough" {
  api_id = aws_appsync_graphql_api.this.id
  name   = "notify_passthrough"
  type   = "NONE"
}
