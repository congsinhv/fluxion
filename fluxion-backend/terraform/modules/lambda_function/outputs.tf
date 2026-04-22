output "function_arn" {
  value       = aws_lambda_function.this.arn
  description = "ARN of the Lambda function."
}

output "invoke_arn" {
  value       = aws_lambda_function.this.invoke_arn
  description = "Invoke ARN used by AppSync Lambda data source."
}

output "role_arn" {
  value       = aws_iam_role.this.arn
  description = "ARN of the Lambda execution IAM role."
}

output "function_name" {
  value       = aws_lambda_function.this.function_name
  description = "Canonical name of the Lambda function as registered in AWS."
}
