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

    # Allow: pushes to main, tag pushes, and pull_request events.
    # PR hardening (plan-only) deferred to follow-up ticket.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repo}:ref:refs/heads/main",
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
    ]
    resources = ["*"]
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
      "ssm:DescribeParameters",
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
