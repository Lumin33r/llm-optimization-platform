# infra/modules/github_oidc/outputs.tf

output "role_arn" {
  description = "ARN of GitHub Actions IAM role"
  value       = aws_iam_role.github_actions.arn
}

output "provider_arn" {
  description = "ARN of the GitHub OIDC provider"
  value       = aws_iam_openid_connect_provider.github.arn
}
