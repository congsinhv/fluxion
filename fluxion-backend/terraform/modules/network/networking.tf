# VPC, Internet Gateway, public/private subnets (2 AZ), and route tables.
# fck-nat ENI is defined in nat.tf; private route table points to it.

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-igw"
  })
}

# ---------------------------------------------------------------------------
# Subnets — for_each over AZ index keeps CIDR/AZ pairs aligned
# ---------------------------------------------------------------------------

resource "aws_subnet" "public" {
  for_each = {
    for i, az in var.azs : az => {
      cidr = var.public_subnet_cidrs[i]
      az   = az
    }
  }

  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-public-${each.key}"
    Tier = "public"
  })
}

resource "aws_subnet" "private" {
  for_each = {
    for i, az in var.azs : az => {
      cidr = var.private_subnet_cidrs[i]
      az   = az
    }
  }

  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-private-${each.key}"
    Tier = "private"
  })
}

# ---------------------------------------------------------------------------
# Public route table → IGW
# ---------------------------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-rt-public"
  })
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# ---------------------------------------------------------------------------
# Private route table → NAT ENI (defined in nat.tf)
# ---------------------------------------------------------------------------

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block           = "0.0.0.0/0"
    network_interface_id = aws_network_interface.nat.id
  }

  tags = merge(local.common_tags, {
    Name = "${var.resource_name_prefix}-rt-private"
  })
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}
