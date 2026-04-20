variable "resource_name_prefix" {
  type        = string
  description = "Prefix for all resource names, e.g. 'fluxion-dev'."
}

variable "env" {
  type        = string
  description = "Deployment environment: dev, staging, or prod."
}
