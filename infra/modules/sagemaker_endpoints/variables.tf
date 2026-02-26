variable "project" {
  description = "Project name prefix for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN for SageMaker execution"
  type        = string
}

variable "inference_image" {
  description = "ECR image URI for SageMaker inference container"
  type        = string
}

variable "endpoints" {
  description = "Map of team endpoint configurations"
  type = map(object({
    model_name     = string
    instance_type  = string
    instance_count = number
    model_data_url = string # S3 path to model artifacts
    variants = optional(list(object({
      name   = string
      weight = number
    })))
  }))
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
