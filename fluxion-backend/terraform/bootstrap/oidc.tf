# GitHub Actions OIDC identity provider + deploy IAM role.
# Lets workflows under `github_repo` assume `fluxion-gha-deploy` via
# short-lived STS credentials — no static access keys stored anywhere.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # Pin both known GitHub OIDC thumbprints to survive rotation.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_policy_document" "gha_deploy_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Allow: pushes to master (prod), tag pushes, and pull_request events.
    # `develop` is dev-env integration branch — no CI runs there, so no trust needed.
    # PR hardening (plan-only) deferred to follow-up ticket.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repo}:ref:refs/heads/master",
        "repo:${var.github_repo}:ref:refs/tags/*",
        "repo:${var.github_repo}:pull_request",
      ]
    }
  }
}

resource "aws_iam_role" "gha_deploy" {
  name                 = "${var.resource_name_prefix}-gha-deploy"
  assume_role_policy   = data.aws_iam_policy_document.gha_deploy_trust.json
  description          = "Assumed by GitHub Actions via OIDC to deploy Fluxion backend."
  max_session_duration = 3600
}

# Intentionally broad for dev/thesis scope. Tightening tracked in follow-up.
data "aws_iam_policy_document" "gha_deploy_inline" {
  statement {
    sid    = "TerraformState"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:GetBucketVersioning",
    ]
    resources = [
      "arn:aws:s3:::${var.resource_name_prefix}-tfstate",
      "arn:aws:s3:::${var.resource_name_prefix}-tfstate/*",
    ]
  }

  statement {
    sid    = "ECRPushPull"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:DescribeRepositories",
      "ecr:DescribeImages",
      "ecr:CreateRepository",
      "ecr:DeleteRepository",
      "ecr:PutLifecyclePolicy",
      "ecr:GetLifecyclePolicy",
      "ecr:DeleteLifecyclePolicy",
      "ecr:TagResource",
      "ecr:UntagResource",
      "ecr:ListTagsForResource",
      "ecr:SetRepositoryPolicy",
      "ecr:GetRepositoryPolicy",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "InfraManagement"
    effect = "Allow"
    actions = [
      "cognito-idp:*",
      "ec2:*",
      "autoscaling:*",
      "rds:*",
      "lambda:*",
      "appsync:*",
      "logs:*",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PassRole",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:CreatePolicy",
      "iam:DeletePolicy",
      "iam:GetPolicy",
      "iam:ListPolicyVersions",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:CreateInstanceProfile",
      "iam:DeleteInstanceProfile",
      "iam:GetInstanceProfile",
      "iam:AddRoleToInstanceProfile",
      "iam:RemoveRoleFromInstanceProfile",
      "iam:TagInstanceProfile",
      "iam:UntagInstanceProfile",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:CreateSecret",
      "secretsmanager:DeleteSecret",
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
      "secretsmanager:PutSecretValue",
      "secretsmanager:UpdateSecret",
      "secretsmanager:TagResource",
      "secretsmanager:UntagResource",
      "secretsmanager:ListSecrets",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:PutResourcePolicy",
      "secretsmanager:RotateSecret",
    ]
    resources = ["*"]
  }

  # ssm:DescribeParameters is a list-level action — only supports "*" resource.
  statement {
    sid       = "SSMDescribeParameters"
    effect    = "Allow"
    actions   = ["ssm:DescribeParameters"]
    resources = ["*"]
  }

  # SQS queue lifecycle for backend Lambda async paths (action_resolver / upload_resolver
  # → SQS, plus DLQs). Scoped to fluxion-* queues only.
  statement {
    sid    = "SQSQueueLifecycle"
    effect = "Allow"
    actions = [
      "sqs:CreateQueue",
      "sqs:DeleteQueue",
      "sqs:GetQueueAttributes",
      "sqs:SetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ListQueues",
      "sqs:ListQueueTags",
      "sqs:TagQueue",
      "sqs:UntagQueue",
    ]
    resources = [
      "arn:aws:sqs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${var.resource_name_prefix}-*",
    ]
  }

  # S3 application buckets (e.g. fluxion-dev-uploads for action-log error CSV reports).
  # Tfstate bucket has its own scoped statement above.
  statement {
    sid    = "S3AppBuckets"
    effect = "Allow"
    actions = [
      "s3:CreateBucket",
      "s3:DeleteBucket",
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:GetBucketTagging",
      "s3:PutBucketTagging",
      "s3:GetBucketVersioning",
      "s3:PutBucketVersioning",
      "s3:GetBucketLifecycleConfiguration",
      "s3:PutBucketLifecycleConfiguration",
      "s3:DeleteBucketLifecycle",
      "s3:GetBucketPublicAccessBlock",
      "s3:PutBucketPublicAccessBlock",
      "s3:GetBucketEncryption",
      "s3:PutBucketEncryption",
      "s3:GetBucketOwnershipControls",
      "s3:PutBucketOwnershipControls",
      "s3:GetBucketAcl",
      "s3:PutBucketAcl",
      "s3:GetBucketCORS",
      "s3:PutBucketCORS",
      "s3:GetBucketPolicy",
      "s3:PutBucketPolicy",
      "s3:DeleteBucketPolicy",
      "s3:GetBucketLogging",
      "s3:PutBucketLogging",
    ]
    resources = [
      "arn:aws:s3:::${var.resource_name_prefix}-uploads",
      "arn:aws:s3:::${var.resource_name_prefix}-uploads/*",
      "arn:aws:s3:::fluxion-dev-uploads",
      "arn:aws:s3:::fluxion-dev-uploads/*",
    ]
  }

  statement {
    sid    = "SSMParamsScoped"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
      "ssm:PutParameter",
      "ssm:DeleteParameter",
      "ssm:AddTagsToResource",
      "ssm:RemoveTagsFromResource",
      "ssm:ListTagsForResource",
    ]
    resources = [
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/fluxion/*",
    ]
  }
}

resource "aws_iam_policy" "gha_deploy" {
  name   = "${var.resource_name_prefix}-gha-deploy"
  policy = data.aws_iam_policy_document.gha_deploy_inline.json
}

resource "aws_iam_role_policy_attachment" "gha_deploy" {
  role       = aws_iam_role.gha_deploy.name
  policy_arn = aws_iam_policy.gha_deploy.arn
}
