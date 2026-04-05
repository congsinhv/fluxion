# ─── Action Trigger Queue ─────────────────────────────────────────────────────

resource "aws_sqs_queue" "action_trigger_dlq" {
  name                      = "fluxion-${var.environment}-action-trigger-dlq"
  message_retention_seconds = var.message_retention_seconds
}

resource "aws_sqs_queue" "action_trigger" {
  name                       = "fluxion-${var.environment}-action-trigger-sqs"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.action_trigger_dlq.arn
    maxReceiveCount     = var.dlq_max_receive_count
  })
}

# ─── Upload Processor Queue ──────────────────────────────────────────────────

resource "aws_sqs_queue" "upload_processor_dlq" {
  name                      = "fluxion-${var.environment}-upload-processor-dlq"
  message_retention_seconds = var.message_retention_seconds
}

resource "aws_sqs_queue" "upload_processor" {
  name                       = "fluxion-${var.environment}-upload-processor-sqs"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.upload_processor_dlq.arn
    maxReceiveCount     = var.dlq_max_receive_count
  })
}

# ─── Checkin Handler Queue ────────────────────────────────────────────────────

resource "aws_sqs_queue" "checkin_handler_dlq" {
  name                      = "fluxion-${var.environment}-checkin-handler-dlq"
  message_retention_seconds = var.message_retention_seconds
}

resource "aws_sqs_queue" "checkin_handler" {
  name                       = "fluxion-${var.environment}-checkin-handler-sqs"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.checkin_handler_dlq.arn
    maxReceiveCount     = var.dlq_max_receive_count
  })
}

# ─── Command SNS Topic ───────────────────────────────────────────────────────

resource "aws_sns_topic" "command" {
  name = "fluxion-${var.environment}-command-sns"
}

# ─── DynamoDB Idempotency Table ──────────────────────────────────────────────

resource "aws_dynamodb_table" "idempotency" {
  name         = "fluxion-${var.environment}-idempotency"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  ttl {
    attribute_name = "expiration"
    enabled        = true
  }
}
