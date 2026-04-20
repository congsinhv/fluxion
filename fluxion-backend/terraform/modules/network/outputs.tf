output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.main.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC."
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (one per AZ)."
  value       = [for s in aws_subnet.public : s.id]
}

output "private_subnet_ids" {
  description = "IDs of the private subnets (one per AZ)."
  value       = [for s in aws_subnet.private : s.id]
}

output "lambda_sg_id" {
  description = "Security group ID for Lambda functions."
  value       = aws_security_group.lambda.id
}

output "rds_sg_id" {
  description = "Security group ID for RDS instances."
  value       = aws_security_group.rds.id
}

output "rds_proxy_sg_id" {
  description = "Security group ID for RDS Proxy."
  value       = aws_security_group.rds_proxy.id
}

output "nat_eip" {
  description = "Public IP of the fck-nat EIP (useful for debug / allowlisting)."
  value       = aws_eip.nat.public_ip
}
