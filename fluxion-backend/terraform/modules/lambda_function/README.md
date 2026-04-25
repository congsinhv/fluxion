# Module: lambda_function

DRY wrapper around `aws_lambda_function` (package_type=Image) for AppSync
resolver Lambdas. Creates the function, IAM execution role, VPC attachment,
and CloudWatch log group in a single module call.

## Usage

```hcl
module "resolver_device" {
  source        = "../../modules/lambda_function"
  function_name = "${var.resource_name_prefix}-device-resolver"
  image_uri     = "${module.ecr.repository_urls["device_resolver"]}:latest"
  env = {
    DATABASE_URI            = local.database_uri
    POWERTOOLS_SERVICE_NAME = "device_resolver"
  }
  vpc_config = {
    subnet_ids = module.network.private_subnet_ids
    sg_id      = module.network.lambda_sg_id
  }
}

# Wire invoke ARN into AppSync API module
module "api" {
  source = "../../modules/api"
  # ...
  lambda_resolver_arns = {
    device   = module.resolver_device.invoke_arn
    platform = module.resolver_platform.invoke_arn
    user     = module.resolver_user.invoke_arn
  }
}
```

### With extra IAM statements (e.g. user_resolver needs Cognito + SSM)

```hcl
module "resolver_user" {
  source        = "../../modules/lambda_function"
  function_name = "${var.resource_name_prefix}-user-resolver"
  image_uri     = "${module.ecr.repository_urls["user_resolver"]}:latest"
  env = {
    DATABASE_URI            = local.database_uri
    POWERTOOLS_SERVICE_NAME = "user_resolver"
  }
  vpc_config = {
    subnet_ids = module.network.private_subnet_ids
    sg_id      = module.network.lambda_sg_id
  }
  extra_policy_statements = [
    {
      effect    = "Allow"
      actions   = ["ssm:GetParameter"]
      resources = ["arn:aws:ssm:*:*:parameter/fluxion/*"]
    },
    {
      effect    = "Allow"
      actions   = ["cognito-idp:AdminGetUser", "cognito-idp:AdminCreateUser"]
      resources = [module.auth.user_pool_arn]
    },
  ]
}
```

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `function_name` | string | — | Unique Lambda name, e.g. `fluxion-dev-device-resolver` |
| `image_uri` | string | — | ECR image URI with tag |
| `env` | map(string) | `{}` | Runtime environment variables |
| `timeout` | number | `10` | Max execution time (seconds) |
| `memory` | number | `512` | Memory allocation (MB) |
| `vpc_config` | object({subnet_ids=list(string), sg_id=string}) | — | Required — RDS Proxy is in private subnets |
| `extra_policy_statements` | list(object({effect, actions, resources})) | `[]` | Additional inline IAM statements on the execution role |
| `log_retention_days` | number | `14` | CloudWatch log retention (days) |

## Outputs

| Name | Description |
|------|-------------|
| `function_arn` | ARN of the Lambda function |
| `invoke_arn` | Invoke ARN for AppSync Lambda data source |
| `role_arn` | ARN of the Lambda execution IAM role |
| `function_name` | Canonical function name as registered in AWS |

## Security notes

- Execution role trust policy is scoped to `lambda.amazonaws.com` only.
- `extra_policy_statements` are rendered via `aws_iam_policy_document` — callers
  cannot inject raw JSON. Apply least-privilege: pass only the actions and
  resource ARNs each resolver strictly requires.
- Log group retention is bounded (default 14 days) for cost and compliance.
  Override via `log_retention_days` for longer audit trails in prod.
