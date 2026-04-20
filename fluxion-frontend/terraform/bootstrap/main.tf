# Bootstrap: creates the S3 bucket that holds Terraform state for all envs
# of fluxion-frontend. Run once manually before touching any envs/ config.
# S3-native locking (use_lockfile in envs/*/backend.tf) replaces DynamoDB.
#
# Usage:
#   terraform init      # local state
#   terraform apply -var=resource_name_prefix=fluxion-frontend

resource "aws_s3_bucket" "tfstate" {
  bucket = "${var.resource_name_prefix}-tfstate"
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
