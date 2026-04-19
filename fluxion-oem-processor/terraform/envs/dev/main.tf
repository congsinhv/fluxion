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
  }
}

provider "aws" {
  region = var.aws_region
}
