terraform {
  required_version = ">= 1.0"

  backend "s3" {
    bucket         = "fluxion-terraform-state"
    key            = "frontend/terraform.tfstate"
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
      Service = "frontend"
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

module "hosting" {
  source      = "./modules/hosting"
  environment = var.environment
}
