# SSM parameters for cross-service import (OEM, Frontend)

resource "aws_ssm_parameter" "vpc_id" {
  name  = "/fluxion/network/vpc_id"
  type  = "String"
  value = module.network.vpc_id
}

resource "aws_ssm_parameter" "private_subnet_ids" {
  name  = "/fluxion/network/private_subnet_ids"
  type  = "StringList"
  value = join(",", module.network.private_subnet_ids)
}

resource "aws_ssm_parameter" "lambda_sg_id" {
  name  = "/fluxion/network/lambda_sg_id"
  type  = "String"
  value = module.network.lambda_sg_id
}

resource "aws_ssm_parameter" "rds_proxy_endpoint" {
  name  = "/fluxion/database/rds_proxy_endpoint"
  type  = "String"
  value = module.database.rds_proxy_endpoint
}

resource "aws_ssm_parameter" "db_secret_arn" {
  name  = "/fluxion/database/db_secret_arn"
  type  = "String"
  value = module.database.db_secret_arn
}
