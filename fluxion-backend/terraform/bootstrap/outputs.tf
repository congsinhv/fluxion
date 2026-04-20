output "state_bucket" {
  value       = aws_s3_bucket.tfstate.bucket
  description = "S3 bucket name to use in envs/*/backend.tf."
}
