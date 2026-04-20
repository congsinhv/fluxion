# Security Groups for the Lambda → RDS Proxy → RDS ingress chain.
#
# Chain:
#   sg-lambda    egress all → internet / VPC
#   sg-rds-proxy ingress tcp/5432 from sg-lambda only
#   sg-rds       ingress tcp/5432 from sg-lambda (proxy-off path)
#                             AND from sg-rds-proxy (proxy-on path)
#
# No circular dependency — chain is linear, so inline ingress blocks are fine.

resource "aws_security_group" "lambda" {
  name        = "${var.resource_name_prefix}-sg-lambda"
  description = "Lambda functions - unrestricted egress, no ingress needed."
  vpc_id      = aws_vpc.main.id

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-sg-lambda"
  })
}

resource "aws_security_group" "rds_proxy" {
  name        = "${var.resource_name_prefix}-sg-rds-proxy"
  description = "RDS Proxy - accept PostgreSQL from Lambda SG only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from Lambda"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-sg-rds-proxy"
  })
}

resource "aws_security_group" "rds" {
  name        = "${var.resource_name_prefix}-sg-rds"
  description = "RDS - accept PostgreSQL from Lambda SG and RDS Proxy SG."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from Lambda (proxy-off path)"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  ingress {
    description     = "PostgreSQL from RDS Proxy"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.rds_proxy.id]
  }

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-sg-rds"
  })
}
