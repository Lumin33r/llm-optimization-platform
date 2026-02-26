# Create IRSA role for a specific service account
resource "aws_iam_role" "irsa" {
  name = "${var.project}-${var.environment}-${var.service_name}-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:${var.namespace}:${var.service_account_name}"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

# SageMaker invoke policy
resource "aws_iam_role_policy" "sagemaker_invoke" {
  count = var.enable_sagemaker_invoke ? 1 : 0
  name  = "sagemaker-invoke"
  role  = aws_iam_role.irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sagemaker:InvokeEndpoint",
          "sagemaker:DescribeEndpoint",
          "sagemaker:DescribeEndpointConfig"
        ]
        Resource = var.sagemaker_endpoint_arns
      }
    ]
  })
}

# CloudWatch metrics/logs policy
resource "aws_iam_role_policy" "cloudwatch" {
  count = var.enable_cloudwatch ? 1 : 0
  name  = "cloudwatch-access"
  role  = aws_iam_role.irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })
}
