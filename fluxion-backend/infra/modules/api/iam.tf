# IAM role allowing AppSync to invoke Lambda resolver functions

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "appsync_lambda" {
  name = "fluxion-appsync-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "appsync.amazonaws.com" }
    }]
  })

  tags = { Name = "fluxion-appsync-lambda-${var.environment}" }
}

# Policy: invoke fluxion Lambda functions only (scoped to this account)
resource "aws_iam_role_policy" "appsync_lambda_invoke" {
  name = "lambda-invoke"
  role = aws_iam_role.appsync_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:fluxion-*"
    }]
  })
}

# IAM role for AppSync CloudWatch logging
resource "aws_iam_role" "appsync_logging" {
  name = "fluxion-appsync-logging-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "appsync.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "appsync_logging" {
  role       = aws_iam_role.appsync_logging.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppSyncPushToCloudWatchLogs"
}
