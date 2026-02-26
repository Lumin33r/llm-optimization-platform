variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "namespaces" {
  description = "Map of namespace configurations including quotas, limits, config, and IRSA"
  type = map(object({
    name        = string
    labels      = map(string)
    annotations = map(string)
    quota       = map(string)
    limit_range = object({
      default_cpu            = string
      default_memory         = string
      default_request_cpu    = string
      default_request_memory = string
      max_cpu                = string
      max_memory             = string
      min_cpu                = string
      min_memory             = string
    })
    config_data   = map(string)
    irsa_role_arn = string
  }))
}
