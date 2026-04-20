variable "aws_region" {
  type        = string
  default     = "ap-southeast-1"
  description = "AWS region."
}

variable "env" {
  type    = string
  default = "dev"
}

variable "resource_name_prefix" {
  type    = string
  default = "fluxion-dev"
}

variable "enable_rds_proxy" {
  type        = bool
  default     = false
  description = "Feature flag — dev=false to save cost (~$22/mo extra). Staging/prod=true."
}
