terraform {
  required_version = ">= 1.0"

  backend "s3" {
    bucket         = "fluxion-terraform-state"
    key            = "backend/terraform.tfstate"
    region         = "ap-southeast-1"
    dynamodb_table = "fluxion-terraform-lock"
    encrypt        = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project = "fluxion"
      Service = "backend"
    }
  }
}

module "network" {
  source      = "./modules/network"
  environment = var.environment
}

module "database" {
  source             = "./modules/database"
  environment        = var.environment
  private_subnet_ids = module.network.private_subnet_ids
  rds_sg_id          = module.network.rds_sg_id
  db_password        = var.db_password
}

module "auth" {
  source      = "./modules/auth"
  environment = var.environment
}

module "api" {
  source               = "./modules/api"
  environment          = var.environment
  region               = var.region
  cognito_user_pool_id = module.auth.user_pool_id
  schema_path          = "${path.root}/../schema.graphql"

  # Lambda ARNs — uncomment when compute module is ready (#34-36)
  # device_resolver_arn   = module.compute.device_resolver_arn
  # platform_resolver_arn = module.compute.platform_resolver_arn
  # user_resolver_arn     = module.compute.user_resolver_arn
  # action_resolver_arn   = module.compute.action_resolver_arn
  # upload_resolver_arn   = module.compute.upload_resolver_arn
  # chat_resolver_arn     = module.compute.chat_resolver_arn
}

module "compute" {
  source      = "./modules/compute"
  environment = var.environment
  region      = var.region

  # Network
  private_subnet_ids = module.network.private_subnet_ids
  lambda_sg_id       = module.network.lambda_sg_id

  # Database
  db_secret_arn = module.database.db_secret_arn
  database_url  = "postgresql://${module.database.db_username}:${var.db_password}@${module.database.rds_proxy_endpoint}/${module.database.db_name}"

  # Messaging — queue URLs (for Lambda env vars)
  action_trigger_queue_url  = module.messaging.action_trigger_queue_url
  upload_processor_queue_url = module.messaging.upload_processor_queue_url

  # Messaging — queue ARNs (for IAM + event source mappings)
  action_trigger_queue_arn  = module.messaging.action_trigger_queue_arn
  upload_processor_queue_arn = module.messaging.upload_processor_queue_arn
  checkin_handler_queue_arn  = module.messaging.checkin_handler_queue_arn

  # SNS
  command_sns_topic_arn = module.messaging.command_sns_topic_arn

  # AppSync
  appsync_endpoint = module.api.api_url
  appsync_api_arn  = module.api.api_arn

  # DynamoDB
  idempotency_table_name = module.messaging.idempotency_table_name
  idempotency_table_arn  = module.messaging.idempotency_table_arn
}

module "messaging" {
  source      = "./modules/messaging"
  environment = var.environment
}
