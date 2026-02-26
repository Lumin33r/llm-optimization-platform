output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name for EKS"
  value       = aws_cloudwatch_log_group.eks.name
}

output "alb_controller_role_arn" {
  description = "IAM role ARN for ALB Ingress Controller"
  value       = aws_iam_role.alb_controller.arn
}

output "external_secrets_role_arn" {
  description = "IAM role ARN for External Secrets Operator"
  value       = aws_iam_role.external_secrets.arn
}
