terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "Terraform"
      Troy        = "troy"
    }
  }
}

# VPC
module "vpc" {
  source = "../../modules/vpc"

  project            = var.project
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  single_nat_gateway = true # Cost optimization for dev; use false in prod
  tags               = local.tags
}

# EKS
module "eks" {
  source = "../../modules/eks"

  project            = var.project
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids
  cluster_version    = var.cluster_version
  node_groups        = var.node_groups
  tags               = local.tags
}

# Configure Kubernetes provider
provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

# ECR Repositories
module "ecr" {
  source = "../../modules/ecr"

  project          = var.project
  environment      = var.environment
  repository_names = ["gateway", "quant-api", "finetune-api", "eval-api", "grafana-plugin", "data-engine"]
  tags             = local.tags
}

# IRSA Roles per team
module "irsa_quant" {
  source = "../../modules/iam_irsa"

  project                 = var.project
  environment             = var.environment
  service_name            = "quant-api"
  namespace               = "quant"
  service_account_name    = "quant-sa"
  oidc_provider_arn       = module.eks.oidc_provider_arn
  oidc_provider_url       = module.eks.oidc_provider_url
  enable_sagemaker_invoke = true
  sagemaker_endpoint_arns = ["arn:aws:sagemaker:${var.aws_region}:*:endpoint/quant-*"]
  enable_cloudwatch       = true
  tags                    = local.tags
}

module "irsa_finetune" {
  source = "../../modules/iam_irsa"

  project                 = var.project
  environment             = var.environment
  service_name            = "finetune-api"
  namespace               = "finetune"
  service_account_name    = "finetune-sa"
  oidc_provider_arn       = module.eks.oidc_provider_arn
  oidc_provider_url       = module.eks.oidc_provider_url
  enable_sagemaker_invoke = true
  sagemaker_endpoint_arns = ["arn:aws:sagemaker:${var.aws_region}:*:endpoint/finetune-*"]
  enable_cloudwatch       = true
  tags                    = local.tags
}

module "irsa_eval" {
  source = "../../modules/iam_irsa"

  project                 = var.project
  environment             = var.environment
  service_name            = "eval-api"
  namespace               = "eval"
  service_account_name    = "eval-sa"
  oidc_provider_arn       = module.eks.oidc_provider_arn
  oidc_provider_url       = module.eks.oidc_provider_url
  enable_sagemaker_invoke = true
  sagemaker_endpoint_arns = ["arn:aws:sagemaker:${var.aws_region}:*:endpoint/eval-*"]
  enable_cloudwatch       = true
  tags                    = local.tags
}

# Gateway IRSA (no SageMaker, CloudWatch only)
module "irsa_gateway" {
  source = "../../modules/iam_irsa"

  project                 = var.project
  environment             = var.environment
  service_name            = "gateway"
  namespace               = "platform"
  service_account_name    = "gateway-sa"
  oidc_provider_arn       = module.eks.oidc_provider_arn
  oidc_provider_url       = module.eks.oidc_provider_url
  enable_sagemaker_invoke = false
  sagemaker_endpoint_arns = []
  enable_cloudwatch       = true
  tags                    = local.tags
}

# Kubernetes Namespaces
module "k8s_namespaces" {
  source = "../../modules/k8s_namespaces"

  environment = var.environment
  namespaces  = local.namespace_configs

  depends_on = [module.eks]
}

locals {
  tags = {
    Project     = var.project
    Environment = var.environment
    Troy        = "troy"
  }

  namespace_configs = {
    platform = {
      name        = "platform"
      labels      = { "tier" = "platform" }
      annotations = { "description" = "Gateway, OTEL collector, ingress" }
      quota = {
        "requests.cpu"    = "4"
        "requests.memory" = "8Gi"
        "limits.cpu"      = "8"
        "limits.memory"   = "16Gi"
        "pods"            = "20"
      }
      limit_range = {
        default_cpu            = "500m"
        default_memory         = "512Mi"
        default_request_cpu    = "100m"
        default_request_memory = "128Mi"
        max_cpu                = "2"
        max_memory             = "4Gi"
        min_cpu                = "50m"
        min_memory             = "64Mi"
      }
      config_data = {
        AWS_REGION = var.aws_region
        LOG_LEVEL  = "INFO"
      }
      irsa_role_arn = module.irsa_gateway.role_arn
    }
    quant = {
      name        = "quant"
      labels      = { "tier" = "team", "team" = "quantization" }
      annotations = { "description" = "Quantization team - GPTQ/AWQ models" }
      quota = {
        "requests.cpu"    = "8"
        "requests.memory" = "16Gi"
        "limits.cpu"      = "16"
        "limits.memory"   = "32Gi"
        "pods"            = "15"
      }
      limit_range = {
        default_cpu            = "1"
        default_memory         = "2Gi"
        default_request_cpu    = "250m"
        default_request_memory = "512Mi"
        max_cpu                = "4"
        max_memory             = "8Gi"
        min_cpu                = "100m"
        min_memory             = "128Mi"
      }
      config_data = {
        AWS_REGION         = var.aws_region
        SAGEMAKER_ENDPOINT = "quant-endpoint"
        LOG_LEVEL          = "DEBUG"
        ENABLE_FALLBACK    = "false"
      }
      irsa_role_arn = module.irsa_quant.role_arn
    }
    finetune = {
      name        = "finetune"
      labels      = { "tier" = "team", "team" = "finetuning" }
      annotations = { "description" = "Fine-tuning team - LoRA models" }
      quota = {
        "requests.cpu"    = "4"
        "requests.memory" = "8Gi"
        "limits.cpu"      = "8"
        "limits.memory"   = "16Gi"
        "pods"            = "10"
      }
      limit_range = {
        default_cpu            = "500m"
        default_memory         = "1Gi"
        default_request_cpu    = "200m"
        default_request_memory = "256Mi"
        max_cpu                = "2"
        max_memory             = "4Gi"
        min_cpu                = "100m"
        min_memory             = "128Mi"
      }
      config_data = {
        AWS_REGION         = var.aws_region
        SAGEMAKER_ENDPOINT = "finetune-endpoint"
        LOG_LEVEL          = "DEBUG"
        AB_ROUTING_ENABLED = "true"
      }
      irsa_role_arn = module.irsa_finetune.role_arn
    }
    eval = {
      name        = "eval"
      labels      = { "tier" = "team", "team" = "evaluation" }
      annotations = { "description" = "Eval team - scoring models" }
      quota = {
        "requests.cpu"    = "4"
        "requests.memory" = "8Gi"
        "limits.cpu"      = "8"
        "limits.memory"   = "16Gi"
        "pods"            = "10"
      }
      limit_range = {
        default_cpu            = "500m"
        default_memory         = "1Gi"
        default_request_cpu    = "200m"
        default_request_memory = "256Mi"
        max_cpu                = "2"
        max_memory             = "4Gi"
        min_cpu                = "100m"
        min_memory             = "128Mi"
      }
      config_data = {
        AWS_REGION         = var.aws_region
        SAGEMAKER_ENDPOINT = "eval-endpoint"
        LOG_LEVEL          = "DEBUG"
      }
      irsa_role_arn = module.irsa_eval.role_arn
    }
    observability = {
      name        = "observability"
      labels      = { "tier" = "platform" }
      annotations = { "description" = "Prometheus, Grafana, Tempo, Loki, OTEL" }
      quota = {
        "requests.cpu"    = "8"
        "requests.memory" = "16Gi"
        "limits.cpu"      = "16"
        "limits.memory"   = "32Gi"
        "pods"            = "30"
      }
      limit_range = {
        default_cpu            = "500m"
        default_memory         = "512Mi"
        default_request_cpu    = "100m"
        default_request_memory = "128Mi"
        max_cpu                = "4"
        max_memory             = "8Gi"
        min_cpu                = "50m"
        min_memory             = "64Mi"
      }
      config_data   = {}
      irsa_role_arn = ""
    }
  }
}
