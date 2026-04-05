# All BE Lambda functions (6 resolvers + 3 workers), ECR repos, IAM roles, SQS event source mappings

locals {
  lambdas = {
    device_resolver = {
      memory  = 256
      timeout = 30
      env_vars = {
        DATABASE_URL = var.database_url
      }
      sqs_trigger = null
    }
    platform_resolver = {
      memory  = 256
      timeout = 30
      env_vars = {
        DATABASE_URL = var.database_url
      }
      sqs_trigger = null
    }
    user_resolver = {
      memory  = 256
      timeout = 30
      env_vars = {
        DATABASE_URL = var.database_url
      }
      sqs_trigger = null
    }
    action_resolver = {
      memory  = 256
      timeout = 30
      env_vars = {
        DATABASE_URL  = var.database_url
        SQS_QUEUE_URL = var.action_trigger_queue_url
      }
      sqs_trigger = null
    }
    upload_resolver = {
      memory  = 256
      timeout = 30
      env_vars = {
        DATABASE_URL  = var.database_url
        SQS_QUEUE_URL = var.upload_processor_queue_url
      }
      sqs_trigger = null
    }
    chat_resolver = {
      memory  = 256
      timeout = 30
      env_vars = {
        DATABASE_URL = var.database_url
      }
      sqs_trigger = null
    }
    action_trigger = {
      memory  = 512
      timeout = 60
      env_vars = {
        DATABASE_URL           = var.database_url
        SNS_TOPIC_ARN          = var.command_sns_topic_arn
        IDEMPOTENCY_TABLE_NAME = var.idempotency_table_name
      }
      sqs_trigger = var.action_trigger_queue_arn
    }
    upload_processor = {
      memory  = 256
      timeout = 30
      env_vars = {
        DATABASE_URL = var.database_url
      }
      sqs_trigger = var.upload_processor_queue_arn
    }
    checkin_handler = {
      memory  = 512
      timeout = 60
      env_vars = {
        DATABASE_URL           = var.database_url
        APPSYNC_ENDPOINT       = var.appsync_endpoint
        IDEMPOTENCY_TABLE_NAME = var.idempotency_table_name
      }
      sqs_trigger = var.checkin_handler_queue_arn
    }
  }

  # Workers only — have SQS event source mappings
  workers = { for k, v in local.lambdas : k => v if v.sqs_trigger != null }
}

# ─── ECR Repositories ─────────────────────────────────────────────────────────

resource "aws_ecr_repository" "lambda" {
  for_each             = local.lambdas
  name                 = "fluxion-${var.environment}-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# ─── IAM Roles ────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each           = local.lambdas
  name               = "fluxion-${var.environment}-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Base policy: CloudWatch Logs + VPC access
resource "aws_iam_role_policy_attachment" "vpc_access" {
  for_each   = local.lambdas
  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# SQS receive/delete for workers
resource "aws_iam_role_policy" "sqs_consume" {
  for_each = local.workers
  name     = "sqs-consume"
  role     = aws_iam_role.lambda[each.key].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
      ]
      Resource = each.value.sqs_trigger
    }]
  })
}

# SQS send for resolvers that enqueue (action_resolver, upload_resolver)
resource "aws_iam_role_policy" "sqs_send_action" {
  name = "sqs-send"
  role = aws_iam_role.lambda["action_resolver"].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = var.action_trigger_queue_arn
    }]
  })
}

resource "aws_iam_role_policy" "sqs_send_upload" {
  name = "sqs-send"
  role = aws_iam_role.lambda["upload_resolver"].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = var.upload_processor_queue_arn
    }]
  })
}

# SNS publish for action_trigger
resource "aws_iam_role_policy" "sns_publish" {
  name = "sns-publish"
  role = aws_iam_role.lambda["action_trigger"].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = var.command_sns_topic_arn
    }]
  })
}

# DynamoDB idempotency for action_trigger + checkin_handler
resource "aws_iam_role_policy" "dynamodb_idempotency" {
  for_each = toset(["action_trigger", "checkin_handler"])
  name     = "dynamodb-idempotency"
  role     = aws_iam_role.lambda[each.key].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
      ]
      Resource = var.idempotency_table_arn
    }]
  })
}

# AppSync invoke for checkin_handler
resource "aws_iam_role_policy" "appsync_invoke" {
  name = "appsync-invoke"
  role = aws_iam_role.lambda["checkin_handler"].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["appsync:GraphQL"]
      Resource = "${var.appsync_api_arn}/*"
    }]
  })
}

# ─── Lambda Functions ─────────────────────────────────────────────────────────

resource "aws_lambda_function" "main" {
  for_each      = local.lambdas
  function_name = "fluxion-${var.environment}-${each.key}"
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda[each.key].repository_url}:latest"
  role          = aws_iam_role.lambda[each.key].arn
  memory_size   = each.value.memory
  timeout       = each.value.timeout

  environment {
    variables = each.value.env_vars
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_sg_id]
  }

  # Ignore image_uri changes — CI/CD updates the image
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# ─── SQS Event Source Mappings (workers only) ─────────────────────────────────

resource "aws_lambda_event_source_mapping" "sqs" {
  for_each         = local.workers
  event_source_arn = each.value.sqs_trigger
  function_name    = aws_lambda_function.main[each.key].arn
  batch_size       = 10
  enabled          = true

  function_response_types = ["ReportBatchItemFailures"]
}
