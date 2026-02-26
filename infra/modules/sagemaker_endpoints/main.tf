resource "aws_sagemaker_model" "team" {
  for_each = var.endpoints

  name               = "${var.project}-${var.environment}-${each.key}-model"
  execution_role_arn = var.sagemaker_role_arn

  primary_container {
    image          = var.inference_image
    model_data_url = each.value.model_data_url
    environment = {
      MODEL_NAME = each.value.model_name
    }
  }
}

resource "aws_sagemaker_endpoint_configuration" "team" {
  for_each = var.endpoints

  name = "${var.project}-${var.environment}-${each.key}-config"

  dynamic "production_variants" {
    for_each = each.value.variants != null ? each.value.variants : [
      { name = "default", weight = 100 }
    ]
    content {
      variant_name           = production_variants.value.name
      model_name             = aws_sagemaker_model.team[each.key].name
      initial_instance_count = each.value.instance_count
      instance_type          = each.value.instance_type
      initial_variant_weight = production_variants.value.weight
    }
  }
}

resource "aws_sagemaker_endpoint" "team" {
  for_each = var.endpoints

  name                 = "${var.project}-${var.environment}-${each.key}-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.team[each.key].name

  tags = var.tags
}
