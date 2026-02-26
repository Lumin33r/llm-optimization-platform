variable "project" {
  description = "Project name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "service_name" {
  description = "Name of the service for the IRSA role"
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace for the service account"
  type        = string
}

variable "service_account_name" {
  description = "Kubernetes service account name"
  type        = string
}

variable "oidc_provider_arn" {
  description = "EKS OIDC provider ARN"
  type        = string
}

variable "oidc_provider_url" {
  description = "EKS OIDC provider URL (without https://)"
  type        = string
}

variable "enable_sagemaker_invoke" {
  description = "Whether to attach SageMaker invoke policy"
  type        = bool
  default     = false
}

variable "sagemaker_endpoint_arns" {
  description = "List of SageMaker endpoint ARNs to allow invocation"
  type        = list(string)
  default     = []
}

variable "enable_cloudwatch" {
  description = "Whether to attach CloudWatch metrics/logs policy"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
