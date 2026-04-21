# `modules/api`

AWS AppSync GraphQL API fronting the Fluxion backend. Ticket [#33](https://github.com/congsinhv/fluxion/issues/33).

## What it creates

- `aws_appsync_graphql_api` named `${resource_name_prefix}-api`
  - Primary auth: `AMAZON_COGNITO_USER_POOLS` (UI clients, `default_action = DENY`)
  - Additional auth: `AWS_IAM` (internal `checkin-handler` Lambda invokes `notify*` mutations)
- CloudWatch log group with retention + role
- IAM role for AppSync → CloudWatch Logs
- IAM role for AppSync → Lambda invoke (scoped to `var.lambda_resolver_arns` values; policy only attached when map non-empty)
- One Lambda data source per populated key in `lambda_resolver_arns` + one NONE data source (`notify-passthrough`) for subscription-trigger mutations
- Unit resolvers per resolver key's field list, and two resolvers on `notify*` mutations backed by the NONE data source

## Gated resolver wiring

`lambda_resolver_arns` is a `map(string)` keyed by resolver name. Supported keys:

| Key | Wiki §3.8.3 resolver | Binds fields |
|---|---|---|
| `device` | device-resolver | `getDevice`, `listDevices`, `getDeviceHistory` |
| `platform` | platform-resolver | `listStates`/`listPolicies`/`listActions`/`listServices`; `updateState`/`updatePolicy`/`updateAction`/`updateService` |
| `message_template` | message-template-resolver | `getMessageTemplate`, `listMessageTemplates`; `generateIconUploadUrl`, `createMessageTemplate`, `updateMessageTemplate`, `deleteMessageTemplate` |
| `tac` | tac-resolver | `getTAC`, `listTACs`; `createTAC`, `updateTAC`, `deleteTAC` |
| `action_log` | action-log-resolver | `getActionLog`, `listActionLogs`; `generateActionLogErrorReport` |
| `user` | user-resolver | `getUser`, `listUsers`, `getCurrentUser`; `createUser`, `updateUser` |
| `action` | action-resolver | `assignAction`, `assignBulkAction` |
| `upload` | upload-resolver | `uploadDevices` |
| `chat` | chat-resolver | `getChatSession`, `listChatSessions`; `sendChatMessage` |

Keys absent from the input map → no data source, no resolver, no IAM policy entry. AppSync reaches the field and returns `FieldUndefined` at query time, which is fine during T7 when Lambdas don't yet exist.

The internal `notifyDeviceStateChanged` / `notifyActionExecutionUpdated` mutations are **always** wired to a NONE data source (passthrough template) — they're the trigger source for the two subscriptions and must resolve under IAM auth from day one.

## Usage

```hcl
module "api" {
  source               = "../../modules/api"
  resource_name_prefix = var.resource_name_prefix
  env                  = var.env
  aws_region           = var.aws_region
  schema_path          = "${path.module}/../../../schema.graphql"
  cognito_user_pool_id = module.auth.user_pool_id
  lambda_resolver_arns = {}  # populate as resolver Lambdas ship
  log_retention_days   = 14
  log_field_log_level  = "ERROR"
  tags                 = local.ssm_tags
}
```

## RBAC note

The GraphQL SDL marks only `notify*` with `@aws_iam`. ADMIN-vs-OPERATOR enforcement for the user-facing Cognito fields is deferred to resolver Lambdas, which read `custom:role` from the JWT — per wiki §3.8.5. This keeps the schema agnostic to Cognito group structure and lets Lambda RBAC evolve independently.

## Outputs

`api_id`, `api_arn`, `graphql_endpoint`, `realtime_endpoint`, `appsync_lambda_invoke_role_arn`, `log_group_name`.
