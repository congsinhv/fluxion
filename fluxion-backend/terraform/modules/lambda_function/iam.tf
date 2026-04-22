# ─── Lambda execution role ────────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# Grants CloudWatch Logs + ENI management (required for VPC-attached Lambdas).
resource "aws_iam_role_policy_attachment" "vpc_access" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# ─── Optional inline policy (extra_policy_statements) ─────────────────────────
# Only created when caller provides at least one statement (e.g. ssm:GetParameter,
# cognito-idp:AdminGetUser). Rendered via aws_iam_policy_document so callers
# cannot inject raw JSON.

data "aws_iam_policy_document" "extra" {
  count = length(var.extra_policy_statements) > 0 ? 1 : 0

  dynamic "statement" {
    for_each = var.extra_policy_statements
    content {
      effect    = statement.value.effect
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

resource "aws_iam_role_policy" "extra" {
  count  = length(var.extra_policy_statements) > 0 ? 1 : 0
  name   = "extra-permissions"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.extra[0].json
}
