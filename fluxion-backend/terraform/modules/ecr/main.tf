# Per-Lambda ECR repositories.
# Callers pass a list of base module names (e.g. ["billing", "fleet"]);
# each becomes "${resource_name_prefix}-${name}" with a lifecycle policy
# that keeps only the last N images to cap storage cost.

resource "aws_ecr_repository" "this" {
  for_each = toset(var.repository_names)

  name                 = "${var.resource_name_prefix}-${each.value}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last ${var.lifecycle_keep_last} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.lifecycle_keep_last
      }
      action = {
        type = "expire"
      }
    }]
  })
}
