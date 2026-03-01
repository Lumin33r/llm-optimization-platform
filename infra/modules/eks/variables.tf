variable "project" {
  description = "Project name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where the EKS cluster will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for EKS node groups"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for EKS cluster"
  type        = list(string)
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.29"
}

variable "node_groups" {
  description = "Map of EKS managed node group configurations"
  type = map(object({
    instance_types = list(string)
    disk_size      = number
    desired_size   = number
    min_size       = number
    max_size       = number
    ami_type       = optional(string, "AL2_x86_64")
    capacity_type  = optional(string, "ON_DEMAND")
    labels         = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
