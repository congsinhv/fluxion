# Lambda ARNs — needed by API module for AppSync resolver datasources
output "device_resolver_arn" {
  value = aws_lambda_function.main["device_resolver"].arn
}

output "platform_resolver_arn" {
  value = aws_lambda_function.main["platform_resolver"].arn
}

output "user_resolver_arn" {
  value = aws_lambda_function.main["user_resolver"].arn
}

output "action_resolver_arn" {
  value = aws_lambda_function.main["action_resolver"].arn
}

output "upload_resolver_arn" {
  value = aws_lambda_function.main["upload_resolver"].arn
}

output "chat_resolver_arn" {
  value = aws_lambda_function.main["chat_resolver"].arn
}

# Lambda invoke ARNs — needed for AppSync datasource invoke permissions
output "device_resolver_invoke_arn" {
  value = aws_lambda_function.main["device_resolver"].invoke_arn
}

output "platform_resolver_invoke_arn" {
  value = aws_lambda_function.main["platform_resolver"].invoke_arn
}

output "user_resolver_invoke_arn" {
  value = aws_lambda_function.main["user_resolver"].invoke_arn
}

output "action_resolver_invoke_arn" {
  value = aws_lambda_function.main["action_resolver"].invoke_arn
}

output "upload_resolver_invoke_arn" {
  value = aws_lambda_function.main["upload_resolver"].invoke_arn
}

output "chat_resolver_invoke_arn" {
  value = aws_lambda_function.main["chat_resolver"].invoke_arn
}
