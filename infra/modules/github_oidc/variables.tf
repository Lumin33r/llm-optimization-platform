# infra/modules/github_oidc/variables.tf

variable "project" {
  description = "Project name prefix for resource naming"
  type        = string
}

variable "github_org" {
  description = "GitHub organization or user name"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "aws_region" {
  description = "AWS region for resource ARN construction"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID for resource ARN construction"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
