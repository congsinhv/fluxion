# Queue URLs — used as Lambda environment variables
output "action_trigger_queue_url" {
  value = aws_sqs_queue.action_trigger.url
}

output "upload_processor_queue_url" {
  value = aws_sqs_queue.upload_processor.url
}

# Queue ARNs — used for IAM policies and Lambda event source mappings
output "action_trigger_queue_arn" {
  value = aws_sqs_queue.action_trigger.arn
}

output "upload_processor_queue_arn" {
  value = aws_sqs_queue.upload_processor.arn
}

# DLQ ARNs — for monitoring/alerting
output "action_trigger_dlq_arn" {
  value = aws_sqs_queue.action_trigger_dlq.arn
}

output "upload_processor_dlq_arn" {
  value = aws_sqs_queue.upload_processor_dlq.arn
}
