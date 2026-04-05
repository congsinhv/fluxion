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
