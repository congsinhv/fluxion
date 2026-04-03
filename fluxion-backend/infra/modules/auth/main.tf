# Cognito User Pool + App Client for Fluxion authentication

resource "aws_cognito_user_pool" "main" {
  name = "fluxion-user-pool"

  # Password policy
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # Email as sign-in
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Custom attributes
  schema {
    name                = "role"
    attribute_data_type = "String"
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 20
    }
  }

  # Account recovery via email
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = { Name = "fluxion-user-pool" }
}

# App Client
resource "aws_cognito_user_pool_client" "main" {
  name         = "fluxion-app-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # Token expiry (NFR3.1)
  access_token_validity  = 1   # 1 hour
  id_token_validity      = 1   # 1 hour
  refresh_token_validity = 30  # 30 days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Auth flows
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  # Include custom:role in tokens
  read_attributes  = ["email", "custom:role"]
  write_attributes = ["email", "custom:role"]

  # No client secret (SPA)
  generate_secret = false
}

# Admin group
resource "aws_cognito_user_group" "admin" {
  name         = "ADMIN"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Admin users with full access"
}

# Operator group
resource "aws_cognito_user_group" "operator" {
  name         = "OPERATOR"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Operator users with standard access"
}
