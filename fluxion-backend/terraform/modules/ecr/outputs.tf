output "repository_urls" {
  value       = { for k, v in aws_ecr_repository.this : k => v.repository_url }
  description = "Map of base module name → ECR repository URL (use in docker push and Lambda image_uri)."
}

output "repository_arns" {
  value       = { for k, v in aws_ecr_repository.this : k => v.arn }
  description = "Map of base module name → ECR repository ARN."
}
