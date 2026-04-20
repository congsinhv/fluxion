# database module

Provisions a **PostgreSQL 16 RDS instance** with Secrets Manager credentials and an optional **RDS Proxy** (feature-flagged, disabled by default).

## Architecture

```
                     (enable_rds_proxy = true)
Lambda ──▶ sg-rds-proxy ──▶ RDS Proxy ──▶ sg-rds ──▶ RDS instance
                                 │
                                 └──▶ Secrets Manager (proxy auth)

                     (enable_rds_proxy = false)
Lambda ──▶ sg-rds ──▶ RDS instance (direct)
                    Secrets Manager (app reads at startup)
```

## Feature flag: `enable_rds_proxy`

| Value | Resources created | Monthly cost delta |
|-------|------------------|--------------------|
| `false` (default) | RDS + Secret only | Free-tier eligible |
| `true` | + IAM role/policy + Proxy + target group + target | ~+$22/mo (t3.micro) |

Enable for production workloads where connection pooling and IAM auth are needed. Keep `false` for dev to stay within free tier.

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `resource_name_prefix` | `string` | — | Resource name prefix, e.g. `fluxion-dev` |
| `env` | `string` | — | Environment: `dev`, `staging`, `prod` |
| `private_subnet_ids` | `list(string)` | — | Private subnet IDs from network module |
| `rds_sg_id` | `string` | — | RDS security group ID from network module |
| `rds_proxy_sg_id` | `string` | — | RDS Proxy security group ID from network module |
| `db_name` | `string` | `fluxion` | Initial database name |
| `db_username` | `string` | `fluxion_admin` | Master username |
| `instance_class` | `string` | `db.t3.micro` | RDS instance class |
| `allocated_storage` | `number` | `20` | Storage in GB |
| `engine_version` | `string` | `16.3` | PostgreSQL version (pinned) |
| `enable_rds_proxy` | `bool` | `false` | Enable RDS Proxy in front of DB |
| `backup_retention_period` | `number` | `7` | Backup retention days (0 = disabled) |

## Outputs

| Name | Sensitive | Description |
|------|-----------|-------------|
| `db_instance_id` | no | RDS instance identifier |
| `db_endpoint` | no | Direct writer endpoint (`host:port`) |
| `db_port` | no | Port (5432) |
| `proxy_endpoint` | no | Proxy endpoint; `null` when disabled |
| `effective_endpoint` | no | Recommended endpoint for consumers |
| `secret_arn` | **yes** | Secrets Manager secret ARN |
| `secret_name` | no | Secrets Manager secret name |

Always wire `effective_endpoint` to application config — it automatically resolves to the proxy when enabled and falls back to the direct RDS address otherwise.

## Consumer pattern (Lambda reads secret)

Phase 3 stores `secret_arn` in SSM Parameter Store. A Lambda retrieves it at cold-start:

```python
import boto3, json, os

ssm = boto3.client("ssm")
sm  = boto3.client("secretsmanager")

def get_db_credentials():
    secret_arn = ssm.get_parameter(
        Name=os.environ["DB_SECRET_ARN_SSM_PATH"],
        WithDecryption=True,
    )["Parameter"]["Value"]
    secret = sm.get_secret_value(SecretId=secret_arn)
    return json.loads(secret["SecretString"])
    # returns {"username": "fluxion_admin", "password": "..."}
```

The Lambda execution role needs:
- `ssm:GetParameter` on the SSM path
- `secretsmanager:GetSecretValue` on the secret ARN

## Security notes

- RDS is **not publicly accessible** (`publicly_accessible = false`)
- Dev instance is **not encrypted at rest** (`storage_encrypted` not set); enable for staging/prod
- Password auto-generated (32 chars, URL-safe special chars) and stored only in Secrets Manager
- `secret_arn` output is marked `sensitive = true` — will not appear in plain `terraform output`
- IAM role for Proxy uses least-privilege: `secretsmanager:GetSecretValue` on the specific secret ARN only
- `deletion_protection = false` and `skip_final_snapshot = true` are intentional for dev; override for prod
- `recovery_window_in_days = 0` on the secret enables fast destroy in dev; use default (30) for prod
