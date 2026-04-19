terraform {
  backend "s3" {
    # bucket supplied via -backend-config at `terraform init` time
    key          = "envs/dev/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
