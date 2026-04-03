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
  source      = "./modules/database"
  environment = var.environment
}

module "auth" {
  source      = "./modules/auth"
  environment = var.environment
}

module "api" {
  source      = "./modules/api"
  environment = var.environment
}

module "compute" {
  source      = "./modules/compute"
  environment = var.environment
}

module "messaging" {
  source      = "./modules/messaging"
  environment = var.environment
}
