variable "environment" {
  type    = string
  default = "dev"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for RDS and RDS Proxy"
}

variable "rds_sg_id" {
  type        = string
  description = "Security group ID for RDS instance"
}

variable "db_password" {
  type      = string
  sensitive = true
}
