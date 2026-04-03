output "api_id" {
  description = "AppSync GraphQL API ID"
  value       = aws_appsync_graphql_api.main.id
}

output "api_url" {
  description = "AppSync GraphQL endpoint URL"
  value       = aws_appsync_graphql_api.main.uris["GRAPHQL"]
}

output "api_arn" {
  description = "AppSync GraphQL API ARN"
  value       = aws_appsync_graphql_api.main.arn
}
