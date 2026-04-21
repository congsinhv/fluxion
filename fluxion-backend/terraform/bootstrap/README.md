# fluxion-backend — Terraform State Bootstrap

## Purpose

One-time creation of the S3 bucket that stores all Terraform remote state for the
`fluxion-backend` sub-repo. The bootstrap itself runs with **local state** (no remote
backend); once the bucket exists you point every `envs/*/backend.tf` at it.

S3-native locking (`use_lockfile = true`) is used — no DynamoDB table required.
This feature requires **Terraform >= 1.10**.

## Prerequisites

- Terraform >= 1.10 installed (`terraform version`)
- AWS credentials configured and working:
  ```
  aws sts get-caller-identity
  ```

## Step-by-step

1. Change into the bootstrap directory:
   ```
   cd terraform/bootstrap
   ```

2. Initialise with local state:
   ```
   terraform init
   ```

3. Create the S3 bucket:
   ```
   terraform apply -var=resource_name_prefix=fluxion-backend
   ```

4. Copy the `state_bucket` output value — you will need it in step 6.

5. Change into the dev environment directory:
   ```
   cd ../envs/dev
   ```

6. Initialise the remote backend (substitute the bucket name from step 4):
   ```
   terraform init -backend-config="bucket=<state_bucket>"
   ```

7. From this point, `terraform plan` / `terraform apply` in any `envs/` directory
   stores state remotely in S3 with S3-native locking.

## GitHub Actions OIDC (deploy role)

The bootstrap also provisions a GitHub OIDC identity provider and the
`fluxion-backend-gha-deploy` IAM role. GitHub Actions workflows assume this
role via short-lived STS tokens — no static AWS access keys.

After `terraform apply`:

1. Capture the deploy role ARN:
   ```
   terraform output -raw deploy_role_arn
   ```

2. Set it as a GitHub repo secret (requires `gh auth login` with admin scope):
   ```
   gh secret set AWS_DEPLOY_ROLE_ARN --body "$(terraform output -raw deploy_role_arn)"
   ```

3. Verify:
   ```
   gh secret list | grep AWS_DEPLOY_ROLE_ARN
   aws iam get-role --role-name fluxion-backend-gha-deploy
   ```

Override the allowed repo with `-var=github_repo=owner/name` (default:
`congsinhv/fluxion`). The trust policy permits pushes to `main`, tag refs, and
`pull_request` events.

## Notes

- `terraform/bootstrap/terraform.tfstate` (local) must be kept outside version control —
  add it to `.gitignore`.
- Bucket names are globally unique in AWS. If `fluxion-backend-tfstate` is already
  taken, append a short suffix, e.g. `fluxion-backend-synh`.
- Default region is `ap-southeast-1` (Singapore). Override with
  `-var=aws_region=<region>` if needed.
- No DynamoDB table is created or required.
