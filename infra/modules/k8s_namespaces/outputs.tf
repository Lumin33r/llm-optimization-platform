output "namespace_names" {
  description = "Map of namespace key to namespace name"
  value       = { for k, v in kubernetes_namespace.team : k => v.metadata[0].name }
}

output "service_account_names" {
  description = "Map of namespace key to service account name"
  value       = { for k, v in kubernetes_service_account.team : k => v.metadata[0].name }
}
