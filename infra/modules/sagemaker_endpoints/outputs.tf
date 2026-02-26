output "endpoint_names" {
  description = "Map of team key to SageMaker endpoint name"
  value       = { for k, v in aws_sagemaker_endpoint.team : k => v.name }
}

output "endpoint_arns" {
  description = "Map of team key to SageMaker endpoint ARN"
  value       = { for k, v in aws_sagemaker_endpoint.team : k => v.arn }
}

output "model_names" {
  description = "Map of team key to SageMaker model name"
  value       = { for k, v in aws_sagemaker_model.team : k => v.name }
}

output "endpoint_config_names" {
  description = "Map of team key to SageMaker endpoint configuration name"
  value       = { for k, v in aws_sagemaker_endpoint_configuration.team : k => v.name }
}
