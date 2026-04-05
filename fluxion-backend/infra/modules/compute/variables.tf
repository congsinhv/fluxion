variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-southeast-1"
}

# Network
variable "private_subnet_ids" {
  type = list(string)
}

variable "lambda_sg_id" {
  type = string
}

# Database
variable "db_secret_arn" {
  type = string
}

variable "database_url" {
  type      = string
  sensitive = true
}

# Messaging — queue URLs (for Lambda env vars)
variable "action_trigger_queue_url" {
  type = string
}

variable "upload_processor_queue_url" {
  type = string
}

# Messaging — queue ARNs (for IAM + event source mappings)
variable "action_trigger_queue_arn" {
  type = string
}

variable "upload_processor_queue_arn" {
  type = string
}

variable "checkin_handler_queue_arn" {
  type = string
}

# SNS
variable "command_sns_topic_arn" {
  type = string
}

# AppSync
variable "appsync_endpoint" {
  type = string
}

variable "appsync_api_arn" {
  type = string
}

# DynamoDB
variable "idempotency_table_name" {
  type = string
}

variable "idempotency_table_arn" {
  type = string
}
