# Outputs consumed by OEM and Frontend via terraform_remote_state or SSM

output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "lambda_sg_id" {
  value = module.network.lambda_sg_id
}

output "rds_endpoint" {
  value = module.database.rds_endpoint
}

output "rds_proxy_endpoint" {
  value = module.database.rds_proxy_endpoint
}

output "cognito_user_pool_id" {
  value = module.auth.user_pool_id
}

output "cognito_client_id" {
  value = module.auth.client_id
}
