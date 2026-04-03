output "state_bucket" {
  value = aws_s3_bucket.tfstate.id
}

output "lock_table" {
  value = aws_dynamodb_table.tflock.name
}
