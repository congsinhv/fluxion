# fck-nat NAT instance: standalone ENI (source_dest_check=false), static EIP,
# IAM role/profile, Launch Template, and ASG size=1 in public AZ-a.
#
# Design: ENI is static (module lifetime) so the private route table can point
# to a stable network_interface_id. On each boot, the ASG instance runs
# fck-nat.service which reads /etc/fck-nat.conf and attaches the ENI.
#
# SSM AMI path to verify if data source errors appear in Phase 3:
#   /aws/service/fck-nat/fck-nat-al2023-arm64-latest/amzn2023

# Resolve latest fck-nat AMI for Amazon Linux 2023 ARM64
data "aws_ssm_parameter" "fck_nat_ami" {
  name = "/aws/service/fck-nat/fck-nat-al2023-arm64-latest/amzn2023"
}

# ---------------------------------------------------------------------------
# Standalone ENI — survives ASG instance recycling
# ---------------------------------------------------------------------------

resource "aws_network_interface" "nat" {
  subnet_id         = aws_subnet.public[var.azs[0]].id
  source_dest_check = false

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-nat-eni"
  })
}

# EIP attached to ENI (not instance) — stable public IP across recycles
resource "aws_eip" "nat" {
  domain            = "vpc"
  network_interface = aws_network_interface.nat.id

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-nat-eip"
  })

  depends_on = [aws_internet_gateway.main]
}

# ---------------------------------------------------------------------------
# IAM — instance profile lets boot script call EC2 API to attach ENI
# ---------------------------------------------------------------------------

resource "aws_iam_role" "fck_nat" {
  name = "${var.resource_name_prefix}-fck-nat-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-fck-nat-role"
  })
}

resource "aws_iam_role_policy" "fck_nat_eni_attach" {
  name = "fck-nat-eni-attach"
  role = aws_iam_role.fck_nat.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ec2:AttachNetworkInterface",
        "ec2:ModifyNetworkInterfaceAttribute",
        "ec2:AssociateAddress",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeInstances",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_instance_profile" "fck_nat" {
  name = "${var.resource_name_prefix}-fck-nat-profile"
  role = aws_iam_role.fck_nat.name

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-fck-nat-profile"
  })
}

# ---------------------------------------------------------------------------
# Launch Template + ASG
# ---------------------------------------------------------------------------

resource "aws_launch_template" "fck_nat" {
  name_prefix   = "${var.resource_name_prefix}-fck-nat-"
  image_id      = data.aws_ssm_parameter.fck_nat_ami.value
  instance_type = var.fck_nat_instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.fck_nat.name
  }

  # fck-nat.service reads /etc/fck-nat.conf at boot and attaches the ENI
  user_data = base64encode(<<-EOT
    #!/bin/bash
    echo "eni_id=${aws_network_interface.nat.id}" > /etc/fck-nat.conf
    systemctl enable --now fck-nat.service
  EOT
  )

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.common_tags, {
      Name = "${var.resource_name_prefix}-fck-nat"
    })
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ASG size=1 in public AZ-a — auto-heals on instance failure (single-AZ SPOF
# is acceptable for dev; upgrade to multi-AZ for prod if needed)
resource "aws_autoscaling_group" "fck_nat" {
  name                = "${var.resource_name_prefix}-fck-nat-asg"
  min_size            = 1
  max_size            = 1
  desired_capacity    = 1
  vpc_zone_identifier = [aws_subnet.public[var.azs[0]].id]

  launch_template {
    id      = aws_launch_template.fck_nat.id
    version = "$Latest"
  }

  tag {
    key                 = "Project"
    value               = "fluxion"
    propagate_at_launch = true
  }

  tag {
    key                 = "Env"
    value               = var.env
    propagate_at_launch = true
  }

  tag {
    key                 = "ManagedBy"
    value               = "terraform"
    propagate_at_launch = true
  }
}
