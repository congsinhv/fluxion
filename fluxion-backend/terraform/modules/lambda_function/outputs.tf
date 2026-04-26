output "function_arn" {
  value       = aws_lambda_function.this.arn
  description = "Plain Lambda ARN. Use this for AppSync Lambda data sources."
}

output "invoke_arn" {
  value       = aws_lambda_function.this.invoke_arn
  description = "API Gateway-formatted invoke URL (apigateway:.../path/...). Use ONLY for API Gateway integrations, NOT for AppSync."
}

output "role_arn" {
  value       = aws_iam_role.this.arn
  description = "ARN of the Lambda execution IAM role."
}

output "function_name" {
  value       = aws_lambda_function.this.function_name
  description = "Canonical name of the Lambda function as registered in AWS."
}
