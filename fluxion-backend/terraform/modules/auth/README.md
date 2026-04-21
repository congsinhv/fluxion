# Module: auth

Cognito User Pool + App Client for the Fluxion admin console.

## Inputs

| Name | Type | Description |
|------|------|-------------|
| `resource_name_prefix` | string | Name prefix (e.g. `fluxion-dev`) |
| `env` | string | Environment tag (`dev`, `staging`, `prod`) |

## Outputs

| Name | Description |
|------|-------------|
| `user_pool_id` | Cognito User Pool ID |
| `user_pool_arn` | ARN (used by AppSync authorizer) |
| `client_id` | App client ID (no secret; browser SDK uses SRP) |
| `issuer_url` | OIDC issuer URL for JWT verification |

## Token config

- Access/ID token: **1 hour**
- Refresh token: **30 days**
- SRP auth flow + refresh token only; no USER_PASSWORD_AUTH
- `prevent_user_existence_errors = ENABLED`

## Custom attributes

- `custom:role` (string, 1–16 chars, mutable) — used by AppSync/Lambda authorizers.

## Creating a test user

```bash
aws cognito-idp admin-create-user \
  --user-pool-id "$(aws ssm get-parameter --name /fluxion/dev/auth/user-pool-id --query 'Parameter.Value' --output text)" \
  --username admin@fluxion.local \
  --user-attributes Name=email,Value=admin@fluxion.local Name=email_verified,Value=true Name=custom:role,Value=ADMIN \
  --temporary-password 'TempPass#12345'
```

## Verifying JWT claims (quick check)

Use AWS CLI initiate-auth with SRP or Amplify SDK. JWT payload should contain:
`sub`, `email`, `cognito:username`, `custom:role`.

## Teardown

`prevent_destroy = true` on the user pool. To remove the pool, first edit
`main.tf` and delete the `lifecycle { prevent_destroy = true }` block, then
`terraform apply`. Intentional friction — protects real admin accounts.
