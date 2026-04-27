# ─── Unit resolvers for Lambda-backed fields ─────────────────────────────────
# Created only for fields whose resolver key is present in
# var.lambda_resolver_arns (see locals.unit_resolver_specs).
resource "aws_appsync_resolver" "unit" {
  for_each = { for s in local.unit_resolver_specs : s.key => s }

  api_id      = aws_appsync_graphql_api.this.id
  type        = each.value.type_name
  field       = each.value.field_name
  data_source = aws_appsync_datasource.lambda[each.value.resolver].name

  # Classic AppSync Lambda invocation template — uses the AWS standard
  # event shape so Lambda dispatchers can read event["info"]["fieldName"].
  # The original (field/typeName) shape was non-standard and the Lambda
  # dispatchers in fluxion-backend/modules/*/src/handler.py don't read it,
  # so every resolver silently raised UnknownFieldError. Replaced with
  # info{} to match `aws_lambda_powertools` / standard direct-resolver shape.
  # $util.* and $ctx.* are VTL — Terraform leaves them alone because they
  # don't use the ${...} interpolation syntax.
  request_template = <<-EOT
    {
      "version": "2018-05-29",
      "operation": "Invoke",
      "payload": {
        "info": {
          "fieldName": "${each.value.field_name}",
          "parentTypeName": "${each.value.type_name}"
        },
        "arguments": $util.toJson($ctx.args),
        "identity": $util.toJson($ctx.identity),
        "source": $util.toJson($ctx.source),
        "request": $util.toJson($ctx.request)
      }
    }
  EOT

  response_template = "$util.toJson($ctx.result)"
}

# ─── Notify mutations (NONE passthrough, always present) ─────────────────────
# Subscriptions fan out from these. Payload is echoed back via ctx.args so
# subscribers receive the mutation's input fields as the source object.
resource "aws_appsync_resolver" "notify" {
  for_each = toset(local.notify_mutations)

  api_id      = aws_appsync_graphql_api.this.id
  type        = "Mutation"
  field       = each.value
  data_source = aws_appsync_datasource.notify_passthrough.name

  request_template  = <<-EOT
    {
      "version": "2017-02-28",
      "payload": $util.toJson($ctx.args)
    }
  EOT
  response_template = "$util.toJson($ctx.result)"
}
