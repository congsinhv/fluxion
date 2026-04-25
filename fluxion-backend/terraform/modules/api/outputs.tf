output "api_id" {
  value       = aws_appsync_graphql_api.this.id
  description = "AppSync GraphQL API ID."
}

output "api_arn" {
  value       = aws_appsync_graphql_api.this.arn
  description = "AppSync GraphQL API ARN (for IAM policies granting client access)."
}

output "graphql_endpoint" {
  value       = aws_appsync_graphql_api.this.uris["GRAPHQL"]
  description = "HTTPS endpoint for queries and mutations."
}

output "realtime_endpoint" {
  value       = aws_appsync_graphql_api.this.uris["REALTIME"]
  description = "WebSocket endpoint for subscriptions."
}

output "appsync_lambda_invoke_role_arn" {
  value       = aws_iam_role.appsync_lambda_invoke.arn
  description = "Role assumed by AppSync when invoking resolver Lambdas."
}

output "log_group_name" {
  value       = aws_cloudwatch_log_group.appsync.name
  description = "CloudWatch log group capturing AppSync field logs."
}
