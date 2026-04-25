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

module "resolver_device" {
  source        = "../../modules/lambda_function"
  function_name = "${var.resource_name_prefix}-device-resolver"
  image_uri     = "${module.ecr.repository_urls["device_resolver"]}:latest"
  env = {
    DATABASE_URI            = local.database_uri
    POWERTOOLS_SERVICE_NAME = "device_resolver"
  }
  vpc_config = {
    subnet_ids = module.network.private_subnet_ids
    sg_id      = module.network.lambda_sg_id
  }
}

module "resolver_platform" {
  source        = "../../modules/lambda_function"
  function_name = "${var.resource_name_prefix}-platform-resolver"
  image_uri     = "${module.ecr.repository_urls["platform_resolver"]}:latest"
  env = {
    DATABASE_URI            = local.database_uri
    POWERTOOLS_SERVICE_NAME = "platform_resolver"
  }
  vpc_config = {
    subnet_ids = module.network.private_subnet_ids
    sg_id      = module.network.lambda_sg_id
  }
}

module "resolver_user" {
  source        = "../../modules/lambda_function"
  function_name = "${var.resource_name_prefix}-user-resolver"
  image_uri     = "${module.ecr.repository_urls["user_resolver"]}:latest"
  env = {
    DATABASE_URI            = local.database_uri
    POWERTOOLS_SERVICE_NAME = "user_resolver"
    COGNITO_USER_POOL_ID    = module.auth.user_pool_id
  }
  vpc_config = {
    subnet_ids = module.network.private_subnet_ids
    sg_id      = module.network.lambda_sg_id
  }
  extra_policy_statements = [
    {
      effect  = "Allow"
      actions = [
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminDeleteUser",
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminUpdateUserAttributes",
      ]
      resources = [module.auth.user_pool_arn]
    },
  ]
}

module "api" {
  source               = "../../modules/api"
  resource_name_prefix = var.resource_name_prefix
  env                  = var.env
  aws_region           = var.aws_region
  schema_path          = "${path.module}/../../../schema.graphql"
  cognito_user_pool_id = module.auth.user_pool_id
  lambda_resolver_arns = {
    device   = module.resolver_device.invoke_arn
    platform = module.resolver_platform.invoke_arn
    user     = module.resolver_user.invoke_arn
  }
  log_retention_days  = 14
  log_field_log_level = "ERROR"
  tags                = local.ssm_tags
}

data "aws_secretsmanager_secret_version" "db" {
  secret_id = module.database.secret_name
}

locals {
  ssm_prefix = "/fluxion/${var.env}"

  ssm_tags = {
    Project   = "fluxion"
    Env       = var.env
    ManagedBy = "terraform"
  }

  # Auto-discover Lambda modules (skip underscore-prefixed templates).
  lambda_module_paths = fileset("${path.module}/../../../modules", "*/pyproject.toml")
  lambda_module_names = [
    for p in local.lambda_module_paths :
    dirname(p) if !startswith(dirname(p), "_")
  ]

  # Construct psycopg3 DSN from RDS endpoint + Secrets Manager credentials.
  # Secret JSON shape: {"username": "...", "password": "..."} (set by database module).
  _db_secret   = jsondecode(data.aws_secretsmanager_secret_version.db.secret_string)
  database_uri = "postgresql://${local._db_secret.username}:${local._db_secret.password}@${module.database.effective_endpoint}/fluxion"
}

module "ecr" {
  source               = "../../modules/ecr"
  resource_name_prefix = var.resource_name_prefix
  repository_names     = local.lambda_module_names
  tags                 = local.ssm_tags
}

resource "aws_ssm_parameter" "ecr_repo_urls" {
  for_each = module.ecr.repository_urls

  name  = "${local.ssm_prefix}/ecr/${each.key}"
  type  = "String"
  value = each.value
  tags  = local.ssm_tags
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

resource "aws_ssm_parameter" "appsync_api_id" {
  name  = "${local.ssm_prefix}/api/api-id"
  type  = "String"
  value = module.api.api_id
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "appsync_graphql_endpoint" {
  name  = "${local.ssm_prefix}/api/graphql-endpoint"
  type  = "String"
  value = module.api.graphql_endpoint
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "appsync_realtime_endpoint" {
  name  = "${local.ssm_prefix}/api/realtime-endpoint"
  type  = "String"
  value = module.api.realtime_endpoint
  tags  = local.ssm_tags
}

resource "aws_ssm_parameter" "appsync_lambda_invoke_role_arn" {
  name  = "${local.ssm_prefix}/api/lambda-invoke-role-arn"
  type  = "String"
  value = module.api.appsync_lambda_invoke_role_arn
  tags  = local.ssm_tags
}
