variable "resource_name_prefix" {
  type        = string
  description = "Prefix for all repo names, e.g. 'fluxion-backend'."
}

variable "repository_names" {
  type        = list(string)
  description = "Base names (without prefix) of ECR repos to create. Typically auto-discovered from Lambda module dirs."
  default     = []
}

variable "lifecycle_keep_last" {
  type        = number
  default     = 10
  description = "Number of most-recent images to retain per repo."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags applied to every repo."
}
