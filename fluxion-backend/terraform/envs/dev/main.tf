# Dev env entry — wires sub-modules from ../../modules/.
# Populated by tickets #30 (network + database), #31 (migrations),
# #32 (Cognito + CI/CD), #33 (AppSync), #37+ (per sub-repo specifics).
#
# Intentionally empty in #29 (scaffold only).

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

module "network" {
  source               = "../../modules/network"
  resource_name_prefix = var.resource_name_prefix
  env                  = var.env
}

module "database" {
  source               = "../../modules/database"
  resource_name_prefix = var.resource_name_prefix
  env                  = var.env
  private_subnet_ids   = module.network.private_subnet_ids
  rds_sg_id            = module.network.rds_sg_id
  rds_proxy_sg_id      = module.network.rds_proxy_sg_id
  enable_rds_proxy     = var.enable_rds_proxy
}

module "auth" {
  source               = "../../modules/auth"
  resource_name_prefix = var.resource_name_prefix
  env                  = var.env
}

locals {
  ssm_prefix = "/fluxion/${var.env}"

  ssm_tags = {
    Project   = "fluxion"
    Env       = var.env
    ManagedBy = "terraform"
  }
}

resource "aws_ssm_parameter" "vpc_id" {
  name  = "${local.ssm_prefix}/network/vpc-id"
  type  = "String"
  value = module.network.vpc_id
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "private_subnet_ids" {
  name  = "${local.ssm_prefix}/network/private-subnet-ids"
  type  = "StringList"
  value = join(",", module.network.private_subnet_ids)
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "public_subnet_ids" {
  name  = "${local.ssm_prefix}/network/public-subnet-ids"
  type  = "StringList"
  value = join(",", module.network.public_subnet_ids)
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "lambda_sg_id" {
  name  = "${local.ssm_prefix}/network/lambda-sg-id"
  type  = "String"
  value = module.network.lambda_sg_id
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "rds_endpoint" {
  name  = "${local.ssm_prefix}/rds/endpoint"
  type  = "String"
  value = module.database.effective_endpoint
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "rds_port" {
  name  = "${local.ssm_prefix}/rds/port"
  type  = "String"
  value = tostring(module.database.db_port)
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "rds_secret_arn" {
  name  = "${local.ssm_prefix}/rds/secret-arn"
  type  = "String"
  value = nonsensitive(module.database.secret_arn)
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "cognito_user_pool_id" {
  name  = "${local.ssm_prefix}/auth/user-pool-id"
  type  = "String"
  value = module.auth.user_pool_id
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "cognito_user_pool_arn" {
  name  = "${local.ssm_prefix}/auth/user-pool-arn"
  type  = "String"
  value = module.auth.user_pool_arn
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "cognito_client_id" {
  name  = "${local.ssm_prefix}/auth/client-id"
  type  = "String"
  value = module.auth.client_id
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "cognito_issuer_url" {
  name  = "${local.ssm_prefix}/auth/issuer-url"
  type  = "String"
  value = module.auth.issuer_url
  tags  = local.ssm_tags
}
