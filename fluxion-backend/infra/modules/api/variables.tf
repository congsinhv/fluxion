variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-southeast-1"
}

variable "cognito_user_pool_id" {
  type        = string
  description = "Cognito User Pool ID for JWT authentication"
}

variable "schema_path" {
  type        = string
  description = "Absolute path to schema.graphql file"
}

# Lambda resolver ARNs — empty default means datasource not created.
# Uncomment in root main.tf when compute module (#34-36) is ready.

variable "device_resolver_arn" {
  type    = string
  default = ""
}

variable "platform_resolver_arn" {
  type    = string
  default = ""
}

variable "user_resolver_arn" {
  type    = string
  default = ""
}

variable "action_resolver_arn" {
  type    = string
  default = ""
}

variable "upload_resolver_arn" {
  type    = string
  default = ""
}

variable "chat_resolver_arn" {
  type    = string
  default = ""
}
