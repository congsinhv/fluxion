# fluxion-oem-processor — Dev Environment

## Prerequisites

- Bootstrap must be applied first — see `../../bootstrap/README.md`.
- Terraform >= 1.10 installed.
- AWS credentials configured (`aws sts get-caller-identity`).

## Initialise with remote backend

Substitute `<state_bucket>` with the `state_bucket` output from bootstrap:

```
terraform init -backend-config="bucket=<state_bucket>"
```

## Plan and apply

```
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## Variable file

Copy the example and fill in real values:

```
cp terraform.tfvars.example terraform.tfvars
```

**Important:** `terraform.tfvars` contains environment-specific values and must be kept
local — never commit it to version control. It is already listed in the root `.gitignore`.

## Notes

- `main.tf` is intentionally empty in scaffold ticket #29. Module wiring is added in
  tickets #30 (network + database), #31 (migrations), #32 (Cognito + CI/CD).
- State is stored remotely in S3 with S3-native locking (`use_lockfile = true`).
  No DynamoDB table is required.
