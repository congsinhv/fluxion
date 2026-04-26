# Canonical resolver → (Query|Mutation) field map.
# Keys MUST match the allowed keys documented in README.md.
# Fields MUST match exactly the field names in ../../schema.graphql.
#
# Only entries whose key is present in var.lambda_resolver_arns produce
# AppSync data sources and resolvers — everything here is intentional spec,
# not live infra, until wiring turns on.
locals {
  resolver_fields = {
    device = {
      Query    = ["getDevice", "listDevices", "getDeviceHistory"]
      Mutation = []
    }
    platform = {
      Query    = ["listStates", "listPolicies", "listActions", "listServices"]
      Mutation = ["updateState", "updatePolicy", "updateAction", "updateService"]
    }
    message_template = {
      Query    = ["getMessageTemplate", "listMessageTemplates"]
      Mutation = ["generateIconUploadUrl", "createMessageTemplate", "updateMessageTemplate", "deleteMessageTemplate"]
    }
    tac = {
      Query    = ["getTAC", "listTACs"]
      Mutation = ["createTAC", "updateTAC", "deleteTAC"]
    }
    user = {
      Query    = ["getUser", "listUsers", "getCurrentUser"]
      Mutation = ["createUser", "updateUser"]
    }
    action = {
      Query    = ["getActionLog", "listActionLogs"]
      Mutation = ["assignAction", "assignBulkAction", "generateActionLogErrorReport"]
    }
    upload = {
      Query    = []
      Mutation = ["uploadDevices"]
    }
    chat = {
      Query    = ["getChatSession", "listChatSessions"]
      Mutation = ["sendChatMessage"]
    }
  }

  # Flatten resolver_fields → list of unit-resolver specs for the active keys.
  unit_resolver_specs = flatten([
    for rkey, groups in local.resolver_fields : [
      for type_name, fields in groups : [
        for field in fields : {
          key        = "${type_name}.${field}"
          resolver   = rkey
          type_name  = type_name
          field_name = field
        }
      ]
    ] if contains(keys(var.lambda_resolver_arns), rkey)
  ])

  # Internal @aws_iam mutations that drive subscriptions.
  # Always wired via the NONE data source.
  notify_mutations = ["notifyDeviceStateChanged", "notifyActionExecutionUpdated"]
}
