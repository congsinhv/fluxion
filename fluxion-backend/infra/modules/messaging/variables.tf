variable "environment" {
  type    = string
  default = "dev"
}

variable "visibility_timeout_seconds" {
  type    = number
  default = 30
}

variable "message_retention_seconds" {
  type    = number
  default = 345600 # 4 days
}

variable "dlq_max_receive_count" {
  type    = number
  default = 3
}
