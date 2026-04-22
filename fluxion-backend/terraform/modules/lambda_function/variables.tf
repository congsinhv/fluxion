variable "function_name" {
  type        = string
  description = "Unique name for the Lambda function, e.g. 'fluxion-dev-device-resolver'."
}

variable "image_uri" {
  type        = string
  description = "ECR image URI (with tag) to deploy, e.g. '123456789.dkr.ecr.ap-southeast-1.amazonaws.com/fluxion-dev-device-resolver:latest'."
}

variable "env" {
  type        = map(string)
  default     = {}
  description = "Environment variables injected into the Lambda function at runtime."
}

variable "timeout" {
  type        = number
  default     = 10
  description = "Maximum execution time in seconds. Defaults to 10."
}

variable "memory" {
  type        = number
  default     = 512
  description = "Amount of memory (MB) allocated to the Lambda function. Defaults to 512."
}

variable "vpc_config" {
  type = object({
    subnet_ids = list(string)
    sg_id      = string
  })
  description = "VPC configuration for the Lambda function. Required — RDS Proxy lives in private subnets."
}

variable "extra_policy_statements" {
  type = list(object({
    effect    = string
    actions   = list(string)
    resources = list(string)
  }))
  default     = []
  description = "Additional IAM policy statements attached as an inline policy on the Lambda execution role (e.g. ssm:GetParameter, cognito-idp:AdminGetUser)."
}

variable "log_retention_days" {
  type        = number
  default     = 14
  description = "CloudWatch log retention period in days. Defaults to 14."
}
