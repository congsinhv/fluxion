# ─── AppSync → CloudWatch Logs role ──────────────────────────────────────────

data "aws_iam_policy_document" "appsync_logs_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["appsync.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "appsync_logs" {
  name               = "${var.resource_name_prefix}-appsync-logs"
  assume_role_policy = data.aws_iam_policy_document.appsync_logs_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "appsync_logs_push" {
  role       = aws_iam_role.appsync_logs.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppSyncPushToCloudWatchLogs"
}

# ─── AppSync → Lambda invoke role ────────────────────────────────────────────
# Shared across all Lambda-backed data sources. Policy scoped to the exact
# ARNs provided via var.lambda_resolver_arns; skipped when map is empty.

data "aws_iam_policy_document" "appsync_lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["appsync.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "appsync_lambda_invoke" {
  name               = "${var.resource_name_prefix}-appsync-lambda-invoke"
  assume_role_policy = data.aws_iam_policy_document.appsync_lambda_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "appsync_lambda_invoke" {
  count = length(var.lambda_resolver_arns) > 0 ? 1 : 0

  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = values(var.lambda_resolver_arns)
  }
}

resource "aws_iam_role_policy" "appsync_lambda_invoke" {
  count  = length(var.lambda_resolver_arns) > 0 ? 1 : 0
  name   = "invoke-resolvers"
  role   = aws_iam_role.appsync_lambda_invoke.id
  policy = data.aws_iam_policy_document.appsync_lambda_invoke[0].json
}
