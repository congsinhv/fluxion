# Cognito User Pool + App Client for Fluxion admin console.
# Exposes a custom `role` attribute used by AppSync/Lambda authorizers to gate
# per-tenant access. `prevent_destroy` protects real users from accidental
# pool recreation — tear-down requires manually removing the lifecycle block.

data "aws_region" "current" {}

resource "aws_cognito_user_pool" "main" {
  name = "${var.resource_name_prefix}-user-pool"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  # Custom `role` claim surfaced in ID tokens for authorization checks.
  schema {
    name                = "role"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 16
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project   = "fluxion"
    Env       = var.env
    ManagedBy = "terraform"
  }
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.resource_name_prefix}-admin-console"
  user_pool_id = aws_cognito_user_pool.main.id

  # SRP for browser SDK; refresh for long-lived sessions.
  # ALLOW_ADMIN_USER_PASSWORD_AUTH enables admin-initiate-auth used by
  # provision-dev-admin.sh and smoke-appsync.sh (server-side scripts only —
  # never exposed to browser clients).
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
  ]

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  generate_secret               = false
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
}
