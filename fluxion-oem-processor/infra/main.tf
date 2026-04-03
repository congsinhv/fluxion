terraform {
  required_version = ">= 1.0"

  backend "s3" {
    bucket         = "fluxion-terraform-state"
    key            = "oem/terraform.tfstate"
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
      Service = "oem"
    }
  }
}

data "terraform_remote_state" "backend" {
  backend = "s3"
  config = {
    bucket = "fluxion-terraform-state"
    key    = "backend/terraform.tfstate"
    region = "ap-southeast-1"
  }
}

module "compute" {
  source      = "./modules/compute"
  environment = var.environment
}

module "mdm-endpoint" {
  source      = "./modules/mdm-endpoint"
  environment = var.environment
}

module "cache" {
  source      = "./modules/cache"
  environment = var.environment
}
