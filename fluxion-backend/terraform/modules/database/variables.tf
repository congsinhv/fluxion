variable "resource_name_prefix" {
  type        = string
  description = "Prefix for all resource names, e.g. 'fluxion-dev'."
}

variable "env" {
  type        = string
  description = "Deployment environment: dev, staging, or prod."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "IDs of private subnets for the RDS subnet group (from network module)."
}

variable "rds_sg_id" {
  type        = string
  description = "Security group ID attached to the RDS instance (from network module)."
}

variable "rds_proxy_sg_id" {
  type        = string
  description = "Security group ID attached to the RDS Proxy (from network module)."
}

variable "db_name" {
  type        = string
  default     = "fluxion"
  description = "Name of the initial database to create inside the RDS instance."
}

variable "db_username" {
  type        = string
  default     = "fluxion_admin"
  description = "Master username for the RDS instance."
}

variable "instance_class" {
  type        = string
  default     = "db.t3.micro"
  description = "RDS instance class. db.t3.micro is free-tier eligible for the first 12 months."
}

variable "allocated_storage" {
  type        = number
  default     = 20
  description = "Allocated storage in GB. 20 GB is the free-tier maximum."
}

variable "engine_version" {
  type        = string
  default     = "16.3"
  description = "PostgreSQL engine version. Pinned to avoid unexpected upgrade surprises."
}

variable "enable_rds_proxy" {
  type        = bool
  default     = false
  description = "Feature flag: create an RDS Proxy in front of the DB instance. Adds ~$22/mo for t3.micro; disabled by default for dev cost savings."
}

variable "backup_retention_period" {
  type        = number
  default     = 7
  description = "Number of days to retain automated backups (1–35). Set 0 to disable."
}
