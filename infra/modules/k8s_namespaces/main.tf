# Namespaces
resource "kubernetes_namespace" "team" {
  for_each = var.namespaces

  metadata {
    name = each.value.name
    labels = merge({
      "app.kubernetes.io/managed-by" = "terraform"
      "team"                         = each.key
      "environment"                  = var.environment
    }, each.value.labels)
    annotations = each.value.annotations
  }
}

# ResourceQuotas
resource "kubernetes_resource_quota" "team" {
  for_each = var.namespaces

  metadata {
    name      = "${each.key}-quota"
    namespace = kubernetes_namespace.team[each.key].metadata[0].name
  }

  spec {
    hard = each.value.quota
  }
}

# LimitRanges
resource "kubernetes_limit_range" "team" {
  for_each = var.namespaces

  metadata {
    name      = "${each.key}-limits"
    namespace = kubernetes_namespace.team[each.key].metadata[0].name
  }

  spec {
    limit {
      type = "Container"
      default = {
        cpu    = each.value.limit_range.default_cpu
        memory = each.value.limit_range.default_memory
      }
      default_request = {
        cpu    = each.value.limit_range.default_request_cpu
        memory = each.value.limit_range.default_request_memory
      }
      max = {
        cpu    = each.value.limit_range.max_cpu
        memory = each.value.limit_range.max_memory
      }
      min = {
        cpu    = each.value.limit_range.min_cpu
        memory = each.value.limit_range.min_memory
      }
    }
  }
}

# ConfigMaps (non-sensitive config)
resource "kubernetes_config_map" "team" {
  for_each = var.namespaces

  metadata {
    name      = "${each.key}-config"
    namespace = kubernetes_namespace.team[each.key].metadata[0].name
  }

  data = each.value.config_data
}

# ServiceAccounts with IRSA annotation
resource "kubernetes_service_account" "team" {
  for_each = var.namespaces

  metadata {
    name      = "${each.key}-sa"
    namespace = kubernetes_namespace.team[each.key].metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = each.value.irsa_role_arn
    }
  }
}
