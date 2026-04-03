# Resolver mappings — Lambda-backed resolvers use for_each,
# internal mutations use NONE datasource with VTL pass-through.

locals {
  # Map: "Type.field" → datasource key
  lambda_resolvers = {
    # device resolver
    "Query.getDevice"            = "device"
    "Query.listDevices"          = "device"
    "Query.getDeviceHistory"     = "device"
    "Query.listAvailableActions" = "device"
    # platform resolver (config queries + mutations)
    "Query.listStates"        = "platform"
    "Query.listPolicies"      = "platform"
    "Query.listActions"       = "platform"
    "Query.listServices"      = "platform"
    "Mutation.updateState"    = "platform"
    "Mutation.updatePolicy"   = "platform"
    "Mutation.updateAction"   = "platform"
    "Mutation.updateService"  = "platform"
    # user resolver
    "Query.getUser"       = "user"
    "Query.listUsers"     = "user"
    "Query.me"            = "user"
    "Mutation.createUser" = "user"
    "Mutation.updateUser" = "user"
    # action resolver
    "Mutation.executeAction"     = "action"
    "Mutation.executeBulkAction" = "action"
    # upload resolver
    "Mutation.uploadDevices" = "upload"
    # chat resolver
    "Query.getChatSession"      = "chat"
    "Query.listChatSessions"    = "chat"
    "Mutation.sendChatMessage"  = "chat"
  }

  # Only create resolvers whose datasource exists (Lambda ARN provided)
  active_resolvers = {
    for k, ds in local.lambda_resolvers : k => ds
    if contains(keys(local.lambda_datasources), ds)
  }
}

resource "aws_appsync_resolver" "lambda" {
  for_each    = local.active_resolvers
  api_id      = aws_appsync_graphql_api.main.id
  type        = split(".", each.key)[0]
  field       = split(".", each.key)[1]
  data_source = aws_appsync_datasource.lambda[each.value].name
}

# ─── Internal mutations — NONE datasource (always active) ────────────────────────
# These pass arguments through to subscriptions via @aws_subscribe directive.

resource "aws_appsync_resolver" "notify_device_state" {
  api_id      = aws_appsync_graphql_api.main.id
  type        = "Mutation"
  field       = "notifyDeviceStateChanged"
  data_source = aws_appsync_datasource.none.name

  request_template  = <<-VTL
    {
      "version": "2017-02-28",
      "payload": $util.toJson($context.arguments)
    }
  VTL
  response_template = "$util.toJson($context.result)"
}

resource "aws_appsync_resolver" "notify_action_execution" {
  api_id      = aws_appsync_graphql_api.main.id
  type        = "Mutation"
  field       = "notifyActionExecutionUpdated"
  data_source = aws_appsync_datasource.none.name

  request_template  = <<-VTL
    {
      "version": "2017-02-28",
      "payload": $util.toJson($context.arguments)
    }
  VTL
  response_template = "$util.toJson($context.result)"
}
