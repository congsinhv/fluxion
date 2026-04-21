# AppSync creates its own log group on first write under this name pattern.
# Pre-creating it here lets us control retention + tags and avoids orphaned
# groups when the API is destroyed.
resource "aws_cloudwatch_log_group" "appsync" {
  name              = "/aws/appsync/apis/${aws_appsync_graphql_api.this.id}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}
