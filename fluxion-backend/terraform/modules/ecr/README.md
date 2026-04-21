# Module: ecr

Creates one ECR repository per Lambda module, each with image scanning,
AES256 encryption, and a "keep last N images" lifecycle policy.

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `resource_name_prefix` | string | — | Prefix (e.g. `fluxion-backend`) — final name: `<prefix>-<repo>` |
| `repository_names` | list(string) | `[]` | Base names, usually auto-discovered from Lambda module dirs |
| `lifecycle_keep_last` | number | `10` | Number of most-recent images to retain |
| `tags` | map(string) | `{}` | Applied to every repo |

## Outputs

| Name | Description |
|------|-------------|
| `repository_urls` | Map `base_name → repo URL` (use in `docker push` + Lambda `image_uri`) |
| `repository_arns` | Map `base_name → ARN` |

## Auto-discovery pattern (caller)

```hcl
locals {
  lambda_module_paths = fileset("${path.module}/../../../modules", "*/pyproject.toml")
  lambda_module_names = [
    for p in local.lambda_module_paths :
    dirname(p) if !startswith(dirname(p), "_")
  ]
}

module "ecr" {
  source               = "../../modules/ecr"
  resource_name_prefix = var.resource_name_prefix
  repository_names     = local.lambda_module_names
  tags                 = local.ssm_tags
}
```

Adding a new Lambda module (`modules/foo/pyproject.toml`) + `terraform apply`
auto-creates `<prefix>-foo` without editing the ECR wiring. Underscore-prefixed
modules (e.g. `_template`) are skipped.

## Teardown

Deleting a name from `repository_names` removes the repo AND all images in
the next apply. Intentional — keeps dev clean. Do not list prod-critical
repos here without separate retention policy.
