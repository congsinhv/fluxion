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
}

module "messaging" {
  source      = "./modules/messaging"
  environment = var.environment
}
