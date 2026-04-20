output "user_pool_id" {
  value       = aws_cognito_user_pool.main.id
  description = "Cognito User Pool ID."
}

output "user_pool_arn" {
  value       = aws_cognito_user_pool.main.arn
  description = "Cognito User Pool ARN (for AppSync authorizer config)."
}

output "client_id" {
  value       = aws_cognito_user_pool_client.main.id
  description = "Admin console app client ID."
}

output "issuer_url" {
  value       = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  description = "OIDC issuer URL for JWT verification."
}
