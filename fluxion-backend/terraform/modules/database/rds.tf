# RDS: subnet group + PostgreSQL 16 instance (single-AZ, dev-optimised settings).

resource "aws_db_subnet_group" "main" {
  name        = "${var.resource_name_prefix}-db-subnet-group"
  subnet_ids  = var.private_subnet_ids
  description = "Subnet group for ${var.resource_name_prefix} RDS instance (private subnets)."

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-db-subnet-group"
  })
}

resource "aws_db_instance" "main" {
  identifier = "${var.resource_name_prefix}-db"

  # Engine
  engine                     = "postgres"
  engine_version             = var.engine_version
  auto_minor_version_upgrade = false # Pin minor version; upgrade explicitly per release process.

  # Sizing
  instance_class    = var.instance_class
  allocated_storage = var.allocated_storage
  storage_type      = "gp2"

  # Credentials — password pulled from random_password directly to avoid circular dep
  # with the secret. The secret stores the same value for app/proxy consumption.
  db_name  = var.db_name
  username = var.db_username
  password = random_password.main.result

  # Networking
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.rds_sg_id]
  publicly_accessible    = false
  multi_az               = false

  # Backup / maintenance
  backup_retention_period = var.backup_retention_period
  backup_window           = "17:00-18:00"         # UTC — off-peak for ap-southeast-1
  maintenance_window      = "Sun:18:00-Sun:19:00" # UTC — immediately after backup window

  # Dev-safe destroy settings
  skip_final_snapshot = true
  deletion_protection = false
  apply_immediately   = true # Apply parameter changes without waiting for next window (dev).

  # Allow out-of-band password rotation (e.g. Secrets Manager rotation Lambda)
  # without Terraform attempting to revert the password on the next plan.
  lifecycle {
    ignore_changes = [password]
  }

  tags = merge(local.common_tags, {
    Name          = "${var.resource_name_prefix}-db"
    auto-shutdown = "dev"
  })
}
