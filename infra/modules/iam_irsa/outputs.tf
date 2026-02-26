output "role_arn" {
  description = "IRSA role ARN to annotate ServiceAccount"
  value       = aws_iam_role.irsa.arn
}

output "role_name" {
  description = "IRSA role name"
  value       = aws_iam_role.irsa.name
}
