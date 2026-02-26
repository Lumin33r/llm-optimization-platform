# Cluster Access
output "eks_cluster_name" {
  description = "EKS cluster name - use with: aws eks update-kubeconfig"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_oidc_provider_arn" {
  description = "OIDC provider ARN for IRSA"
  value       = module.eks.oidc_provider_arn
}

# Container Registries
output "ecr_repository_urls" {
  description = "ECR repository URLs per service"
  value       = module.ecr.repository_urls
}

# Gateway URL (populated after ALB Ingress deployment)
output "gateway_url" {
  description = "Gateway ALB URL (available after ingress deployment)"
  value       = "Pending - deploy ingress controller first"
}

# Grafana URL
output "grafana_url" {
  description = "Grafana dashboard URL"
  value       = "Pending - deploy observability stack first"
}

# SageMaker Endpoints
output "sagemaker_endpoint_names" {
  description = "SageMaker endpoint names per team"
  value = {
    quant    = "quant-endpoint"
    finetune = "finetune-endpoint"
    eval     = "eval-endpoint"
  }
}

# IRSA Role ARNs
output "irsa_role_arns" {
  description = "IRSA role ARNs per namespace/service"
  value = {
    gateway  = module.irsa_gateway.role_arn
    quant    = module.irsa_quant.role_arn
    finetune = module.irsa_finetune.role_arn
    eval     = module.irsa_eval.role_arn
  }
}
