# Log group created before the Lambda so AWS does not auto-create it without
# the retention policy. Explicit depends_on on the Lambda enforces ordering.
resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  package_type  = "Image"
  image_uri     = var.image_uri
  role          = aws_iam_role.this.arn

  timeout     = var.timeout
  memory_size = var.memory

  vpc_config {
    subnet_ids         = var.vpc_config.subnet_ids
    security_group_ids = [var.vpc_config.sg_id]
  }

  environment {
    variables = var.env
  }

  # Ensures the log group (with retention) exists before Lambda creates log streams.
  depends_on = [aws_cloudwatch_log_group.this]
}
