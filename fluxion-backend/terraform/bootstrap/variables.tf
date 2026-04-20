variable "aws_region" {
  type        = string
  default     = "ap-southeast-1"
  description = "AWS region for state bucket."
}

variable "resource_name_prefix" {
  type        = string
  description = "Unique prefix for AWS resources, e.g. fluxion-backend."
}
