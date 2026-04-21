variable "resource_name_prefix" {
  type        = string
  description = "Prefix for all resource names, e.g. 'fluxion-dev'."
}

variable "env" {
  type        = string
  description = "Deployment environment: dev, staging, or prod."
}

variable "aws_region" {
  type        = string
  description = "AWS region where the Cognito User Pool lives (used by AppSync auth config)."
}

variable "schema_path" {
  type        = string
  description = "Filesystem path to the GraphQL SDL (schema.graphql) used by AppSync."
}

variable "cognito_user_pool_id" {
  type        = string
  description = "Cognito User Pool ID that backs primary Cognito auth mode."
}

variable "lambda_resolver_arns" {
  type        = map(string)
  default     = {}
  description = <<-EOT
    Map of resolver key → Lambda function ARN. Keys:
    device | platform | user | action | upload | chat |
    tac | message_template | action_log.

    Empty map = deploy AppSync API + schema + internal NONE
    data source only; skip all Lambda-backed data sources and
    resolvers. Populate incrementally as resolver Lambdas ship.
  EOT
}

variable "log_retention_days" {
  type        = number
  default     = 14
  description = "CloudWatch log retention days for AppSync API logs."
}

variable "log_field_log_level" {
  type        = string
  default     = "ERROR"
  description = "AppSync field log level: NONE | ERROR | INFO | ALL."
  validation {
    condition     = contains(["NONE", "ERROR", "INFO", "ALL"], var.log_field_log_level)
    error_message = "log_field_log_level must be one of NONE, ERROR, INFO, ALL."
  }
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags applied to all resources."
}
