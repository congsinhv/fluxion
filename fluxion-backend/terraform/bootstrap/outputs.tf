output "state_bucket" {
  value       = aws_s3_bucket.tfstate.bucket
  description = "S3 bucket name to use in envs/*/backend.tf."
}

output "deploy_role_arn" {
  value       = aws_iam_role.gha_deploy.arn
  description = "ARN of the IAM role GitHub Actions assumes via OIDC. Set as repo secret AWS_DEPLOY_ROLE_ARN."
}

output "oidc_provider_arn" {
  value       = aws_iam_openid_connect_provider.github.arn
  description = "ARN of the GitHub OIDC identity provider."
}
