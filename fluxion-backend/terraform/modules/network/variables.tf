variable "resource_name_prefix" {
  type        = string
  description = "Prefix for all resource names, e.g. 'fluxion-dev'."
}

variable "env" {
  type        = string
  description = "Deployment environment: dev, staging, or prod."
}

variable "vpc_cidr" {
  type        = string
  default     = "10.0.0.0/16"
  description = "CIDR block for the VPC."
}

variable "azs" {
  type        = list(string)
  default     = ["ap-southeast-1a", "ap-southeast-1b"]
  description = "Availability zones to deploy subnets into (exactly 2 required)."
}

variable "public_subnet_cidrs" {
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
  description = "CIDR blocks for public subnets (one per AZ, index-aligned with azs)."
}

variable "private_subnet_cidrs" {
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
  description = "CIDR blocks for private subnets (one per AZ, index-aligned with azs)."
}

variable "fck_nat_instance_type" {
  type        = string
  default     = "t4g.nano"
  description = "EC2 instance type for the fck-nat NAT instance (ARM Graviton recommended)."
}
