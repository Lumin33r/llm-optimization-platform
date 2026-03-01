# Design Document 1: Terraform Infrastructure as Code

## Overview

This document defines the Terraform infrastructure for the LLM Optimization Platform. The IaC provisions all AWS resources with:

- **No hardcoded credentials** - Use AWS profile/role locally; GitHub OIDC in CI
- **Clear lifecycle** - Documented `init/plan/apply/destroy` workflow
- **Remote state** - S3 bucket + DynamoDB lock table
- **Kubernetes provider** - Optionally manage namespaces, RBAC, quotas, ConfigMaps

---

## Quick Start (Implementation Order)

```bash
# 1. Bootstrap remote state (one-time)
cd infra && ./scripts/init-backend.sh llmplatform dev us-west-2

# 2. Initialize Terraform
cd envs/dev && terraform init

# 3. Plan and apply
terraform plan -out=tfplan
terraform apply tfplan

# 4. Configure kubectl
aws eks update-kubeconfig --name $(terraform output -raw eks_cluster_name)

# 5. Verify cluster access
kubectl get nodes
```

**Depends On**: AWS account credentials, HuggingFace token (for baseline model)
**Feeds Into**: [design-02-kubernetes.md](design-02-kubernetes.md)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AWS Account                                         │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                              VPC (10.0.0.0/16)                              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │ │
│  │  │ Public Sub A │  │ Public Sub B │  │ Public Sub C │   ALB Ingress        │ │
│  │  │ 10.0.1.0/24  │  │ 10.0.2.0/24  │  │ 10.0.3.0/24  │                      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                      │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │ │
│  │  │ Private Sub A│  │ Private Sub B│  │ Private Sub C│   EKS + SageMaker    │ │
│  │  │ 10.0.10.0/24 │  │ 10.0.20.0/24 │  │ 10.0.30.0/24 │                      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                      │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                         EKS Cluster (6 namespaces)                          │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐ │ │
│  │  │platform │ │  quant  │ │finetune │ │  eval   │ │observ-  │ │llm-base-  │ │ │
│  │  │namespace│ │namespace│ │namespace│ │namespace│ │ability  │ │  line     │ │ │
│  │  │         │ │         │ │         │ │         │ │         │ │(vLLM+GPU) │ │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └───────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                      SageMaker Endpoints                                    │ │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐               │ │
│  │  │  quant-endpoint │ │ finetune-endpoint│ │  eval-endpoint  │               │ │
│  │  │   (GPTQ/AWQ)    │ │  (LoRA adapters) │ │   (Evaluator)   │               │ │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────┘               │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ S3 (TF State)│  │  DynamoDB    │  │     ECR      │  │  CloudWatch  │        │
│  │ + Versioning │  │ (State Lock) │  │  Registries  │  │    Logs      │        │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

> **Note**: The `llm-baseline` namespace runs vLLM with GPU nodes for the Mistral-7B baseline model. See [design-10-models.md](design-10-models.md) for deployment details.

---

## Directory Structure (Recommended Layout)

```
infra/
├── envs/
│   ├── dev/
│   │   ├── main.tf              # Root module composition
│   │   ├── backend.tf           # S3 + DynamoDB backend config
│   │   ├── variables.tf         # Environment-specific variable declarations
│   │   ├── outputs.tf           # Team-facing outputs
│   │   └── terraform.tfvars     # Variable values for dev
│   ├── staging/
│   │   └── ... (same structure)
│   └── prod/
│       └── ... (same structure)
├── modules/
│   ├── vpc/                     # VPC, subnets, NAT, route tables
│   ├── eks/                     # EKS cluster, node groups, OIDC
│   ├── ecr/                     # Container registries per service
│   ├── iam_irsa/                # IAM roles for service accounts
│   ├── observability/           # CloudWatch, ALB controller IAM
│   ├── sagemaker_endpoints/     # SageMaker models, configs, endpoints
│   └── k8s_namespaces/          # Namespaces, quotas, limitranges, RBAC, configmaps
└── scripts/
    ├── init-backend.sh          # Bootstrap S3 + DynamoDB
    ├── plan.sh                  # terraform plan wrapper
    ├── apply.sh                 # terraform apply wrapper
    └── destroy.sh               # terraform destroy with confirmation
```

---

## Remote State Configuration

### Backend Configuration (`envs/dev/backend.tf`)

```hcl
terraform {
  backend "s3" {
    bucket         = "tfstate-llmplatform-dev"
    key            = "terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true
    dynamodb_table = "tf-locks-llmplatform-dev"

    # Optional: Use role assumption for CI
    # role_arn = "arn:aws:iam::ACCOUNT_ID:role/terraform-state-role"
  }
}
```

### State Bucket Bootstrap Script (`scripts/init-backend.sh`)

```bash
#!/bin/bash
set -euo pipefail

ORG="${1:-llmplatform}"
ENV="${2:-dev}"
REGION="${3:-us-west-2}"

BUCKET_NAME="tfstate-${ORG}-${ENV}"
TABLE_NAME="tf-locks-${ORG}-${ENV}"

echo "==> Creating S3 bucket: ${BUCKET_NAME}"
aws s3api create-bucket \
    --bucket "${BUCKET_NAME}" \
    --region "${REGION}" \
    --create-bucket-configuration LocationConstraint="${REGION}"

# Enable versioning
aws s3api put-bucket-versioning \
    --bucket "${BUCKET_NAME}" \
    --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
    --bucket "${BUCKET_NAME}" \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "aws:kms"
            },
            "BucketKeyEnabled": true
        }]
    }'

# Block public access
aws s3api put-public-access-block \
    --bucket "${BUCKET_NAME}" \
    --public-access-block-configuration '{
        "BlockPublicAcls": true,
        "IgnorePublicAcls": true,
        "BlockPublicPolicy": true,
        "RestrictPublicBuckets": true
    }'

# Tag bucket
aws s3api put-bucket-tagging \
    --bucket "${BUCKET_NAME}" \
    --tagging 'TagSet=[{Key=Environment,Value='"${ENV}"'},{Key=ManagedBy,Value=Terraform},{Key=Troy,Value=troy}]'

echo "==> Creating DynamoDB table: ${TABLE_NAME}"
aws dynamodb create-table \
    --table-name "${TABLE_NAME}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${REGION}" \
    --tags Key=Environment,Value="${ENV}" Key=ManagedBy,Value=Terraform Key=Troy,Value=troy

echo "==> Backend initialization complete!"
echo "Bucket: ${BUCKET_NAME}"
echo "Table: ${TABLE_NAME}"
```

---

## Core Modules

### 1. VPC Module (`modules/vpc/`)

#### `modules/vpc/main.tf`

```hcl
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, {
    Name = "${var.project}-${var.environment}-vpc"
  })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = merge(var.tags, { Name = "${var.project}-${var.environment}-igw" })
}

resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name                                        = "${var.project}-${var.environment}-public-${count.index + 1}"
    "kubernetes.io/role/elb"                    = "1"
    "kubernetes.io/cluster/${var.project}-${var.environment}" = "shared"
  })
}

resource "aws_subnet" "private" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.tags, {
    Name                                        = "${var.project}-${var.environment}-private-${count.index + 1}"
    "kubernetes.io/role/internal-elb"           = "1"
    "kubernetes.io/cluster/${var.project}-${var.environment}" = "shared"
  })
}

resource "aws_eip" "nat" {
  count  = var.single_nat_gateway ? 1 : length(var.availability_zones)
  domain = "vpc"
  tags   = merge(var.tags, { Name = "${var.project}-${var.environment}-nat-eip-${count.index + 1}" })
}

resource "aws_nat_gateway" "main" {
  count         = var.single_nat_gateway ? 1 : length(var.availability_zones)
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = merge(var.tags, { Name = "${var.project}-${var.environment}-nat-${count.index + 1}" })
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-public-rt" })
}

resource "aws_route_table" "private" {
  count  = length(var.availability_zones)
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[var.single_nat_gateway ? 0 : count.index].id
  }
  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-private-rt-${count.index + 1}" })
}

resource "aws_route_table_association" "public" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
```

#### `modules/vpc/outputs.tf`

```hcl
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "vpc_cidr_block" {
  description = "VPC CIDR block"
  value       = aws_vpc.main.cidr_block
}
```

---

### 2. EKS Module (`modules/eks/`)

#### `modules/eks/main.tf`

```hcl
data "aws_caller_identity" "current" {}

# EKS Cluster IAM Role
resource "aws_iam_role" "cluster" {
  name = "${var.project}-${var.environment}-eks-cluster"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.cluster.name
}

resource "aws_iam_role_policy_attachment" "vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.cluster.name
}

# EKS Cluster
resource "aws_eks_cluster" "main" {
  name     = "${var.project}-${var.environment}"
  role_arn = aws_iam_role.cluster.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids              = concat(var.private_subnet_ids, var.public_subnet_ids)
    endpoint_private_access = true
    endpoint_public_access  = true
    security_group_ids      = [aws_security_group.cluster.id]
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-eks" })

  depends_on = [
    aws_iam_role_policy_attachment.cluster_policy,
    aws_iam_role_policy_attachment.vpc_resource_controller
  ]
}

# Cluster Security Group
resource "aws_security_group" "cluster" {
  name        = "${var.project}-${var.environment}-eks-cluster-sg"
  description = "EKS cluster security group"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-eks-cluster-sg" })
}

# Node Group IAM Role
resource "aws_iam_role" "nodes" {
  name = "${var.project}-${var.environment}-eks-nodes"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "worker_node" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.nodes.name
}

resource "aws_iam_role_policy_attachment" "cni" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.nodes.name
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.nodes.name
}

# Managed Node Group
resource "aws_eks_node_group" "main" {
  for_each = var.node_groups

  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project}-${var.environment}-${each.key}"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = each.value.instance_types
  ami_type        = each.value.ami_type
  capacity_type   = each.value.capacity_type  # ON_DEMAND or SPOT
  disk_size       = each.value.disk_size

  scaling_config {
    desired_size = each.value.desired_size
    min_size     = each.value.min_size
    max_size     = each.value.max_size
  }

  labels = each.value.labels

  dynamic "taint" {
    for_each = each.value.taints
    content {
      key    = taint.value.key
      value  = taint.value.value
      effect = taint.value.effect
    }
  }

  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-${each.key}-nodes" })

  depends_on = [
    aws_iam_role_policy_attachment.worker_node,
    aws_iam_role_policy_attachment.cni,
    aws_iam_role_policy_attachment.ecr_readonly
  ]
}

# OIDC Provider for IRSA
data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
  tags            = var.tags
}
```

#### `modules/eks/outputs.tf`

```hcl
output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_ca_certificate" {
  description = "Cluster CA certificate (base64)"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "oidc_provider_arn" {
  description = "OIDC provider ARN for IRSA"
  value       = aws_iam_openid_connect_provider.eks.arn
}

output "oidc_provider_url" {
  description = "OIDC provider URL"
  value       = replace(aws_iam_openid_connect_provider.eks.url, "https://", "")
}

output "node_role_arn" {
  description = "Node group IAM role ARN"
  value       = aws_iam_role.nodes.arn
}

output "cluster_security_group_id" {
  description = "Cluster security group ID"
  value       = aws_security_group.cluster.id
}
```

---

### 3. IAM IRSA Module (`modules/iam_irsa/`)

#### `modules/iam_irsa/main.tf`

```hcl
# Create IRSA role for a specific service account
resource "aws_iam_role" "irsa" {
  name = "${var.project}-${var.environment}-${var.service_name}-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:${var.namespace}:${var.service_account_name}"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

# SageMaker invoke policy
resource "aws_iam_role_policy" "sagemaker_invoke" {
  count = var.enable_sagemaker_invoke ? 1 : 0
  name  = "sagemaker-invoke"
  role  = aws_iam_role.irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sagemaker:InvokeEndpoint",
          "sagemaker:DescribeEndpoint",
          "sagemaker:DescribeEndpointConfig"
        ]
        Resource = var.sagemaker_endpoint_arns
      }
    ]
  })
}

# CloudWatch metrics/logs policy
resource "aws_iam_role_policy" "cloudwatch" {
  count = var.enable_cloudwatch ? 1 : 0
  name  = "cloudwatch-access"
  role  = aws_iam_role.irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })
}
```

#### `modules/iam_irsa/outputs.tf`

```hcl
output "role_arn" {
  description = "IRSA role ARN to annotate ServiceAccount"
  value       = aws_iam_role.irsa.arn
}

output "role_name" {
  description = "IRSA role name"
  value       = aws_iam_role.irsa.name
}
```

---

### 4. ECR Module (`modules/ecr/`)

#### `modules/ecr/main.tf`

```hcl
resource "aws_ecr_repository" "services" {
  for_each             = toset(var.repository_names)
  name                 = "${var.project}-${var.environment}/${each.key}"
  image_tag_mutability = var.image_tag_mutability

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }

  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-${each.key}" })
}

resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each   = toset(var.repository_names)
  repository = aws_ecr_repository.services[each.key].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 15 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "sha-", "main", "develop", "dev-"]
          countType     = "imageCountMoreThan"
          countNumber   = 15
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Remove untagged after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}
```

#### `modules/ecr/outputs.tf`

```hcl
output "repository_urls" {
  description = "Map of service name to ECR repository URL"
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}

output "repository_arns" {
  description = "Map of service name to ECR repository ARN"
  value       = { for k, v in aws_ecr_repository.services : k => v.arn }
}
```

---

### 5. Kubernetes Namespaces Module (`modules/k8s_namespaces/`)

#### `modules/k8s_namespaces/main.tf`

```hcl
# Namespaces
resource "kubernetes_namespace" "team" {
  for_each = var.namespaces

  metadata {
    name = each.value.name
    labels = merge({
      "app.kubernetes.io/managed-by" = "terraform"
      "team"                          = each.key
      "environment"                   = var.environment
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
```

---

## Environment Configuration

### `envs/dev/main.tf`

```hcl
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
  single_nat_gateway = true  # Cost optimization for dev; use false in prod
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
  repository_names = ["gateway", "quant-api", "finetune-api", "eval-api", "grafana-plugin"]
  tags             = local.tags
}

# IRSA Roles per team
module "irsa_quant" {
  source = "../../modules/iam_irsa"

  project              = var.project
  environment          = var.environment
  service_name         = "quant-api"
  namespace            = "quant"
  service_account_name = "quant-sa"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  oidc_provider_url    = module.eks.oidc_provider_url
  enable_sagemaker_invoke = true
  sagemaker_endpoint_arns = ["arn:aws:sagemaker:${var.aws_region}:*:endpoint/quant-*"]
  enable_cloudwatch    = true
  tags                 = local.tags
}

module "irsa_finetune" {
  source = "../../modules/iam_irsa"

  project              = var.project
  environment          = var.environment
  service_name         = "finetune-api"
  namespace            = "finetune"
  service_account_name = "finetune-sa"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  oidc_provider_url    = module.eks.oidc_provider_url
  enable_sagemaker_invoke = true
  sagemaker_endpoint_arns = ["arn:aws:sagemaker:${var.aws_region}:*:endpoint/finetune-*"]
  enable_cloudwatch    = true
  tags                 = local.tags
}

module "irsa_eval" {
  source = "../../modules/iam_irsa"

  project              = var.project
  environment          = var.environment
  service_name         = "eval-api"
  namespace            = "eval"
  service_account_name = "eval-sa"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  oidc_provider_url    = module.eks.oidc_provider_url
  enable_sagemaker_invoke = true
  sagemaker_endpoint_arns = ["arn:aws:sagemaker:${var.aws_region}:*:endpoint/eval-*"]
  enable_cloudwatch    = true
  tags                 = local.tags
}

# Gateway IRSA (no SageMaker, CloudWatch only)
module "irsa_gateway" {
  source = "../../modules/iam_irsa"

  project              = var.project
  environment          = var.environment
  service_name         = "gateway"
  namespace            = "platform"
  service_account_name = "gateway-sa"
  oidc_provider_arn    = module.eks.oidc_provider_arn
  oidc_provider_url    = module.eks.oidc_provider_url
  enable_sagemaker_invoke = false
  sagemaker_endpoint_arns = []
  enable_cloudwatch    = true
  tags                 = local.tags
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
        AWS_REGION           = var.aws_region
        SAGEMAKER_ENDPOINT   = "finetune-endpoint"
        LOG_LEVEL            = "DEBUG"
        AB_ROUTING_ENABLED   = "true"
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
      config_data = {}
      irsa_role_arn = ""
    }
  }
}
```

### `envs/dev/outputs.tf` (Team-Facing Outputs)

```hcl
# Cluster Access
output "eks_cluster_name" {
  description = "EKS cluster name - use with: aws eks update-kubeconfig"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_oidc_provider_arn" {
  description = "OIDC provider ARN for IRSA"
  value       = module.eks.oidc_provider_arn
}

# Container Registries
output "ecr_repository_urls" {
  description = "ECR repository URLs per service"
  value       = module.ecr.repository_urls
}

# Gateway URL (populated after ALB Ingress deployment)
output "gateway_url" {
  description = "Gateway ALB URL (available after ingress deployment)"
  value       = "Pending - deploy ingress controller first"
}

# Grafana URL
output "grafana_url" {
  description = "Grafana dashboard URL"
  value       = "Pending - deploy observability stack first"
}

# SageMaker Endpoints
output "sagemaker_endpoint_names" {
  description = "SageMaker endpoint names per team"
  value = {
    quant    = "quant-endpoint"
    finetune = "finetune-endpoint"
    eval     = "eval-endpoint"
  }
}

# IRSA Role ARNs
output "irsa_role_arns" {
  description = "IRSA role ARNs per namespace/service"
  value = {
    gateway  = module.irsa_gateway.role_arn
    quant    = module.irsa_quant.role_arn
    finetune = module.irsa_finetune.role_arn
    eval     = module.irsa_eval.role_arn
  }
}
```

---

## Lifecycle Commands

### Initialize

```bash
cd infra/envs/dev
terraform init -backend-config="bucket=tfstate-llmplatform-dev"
```

### Plan

```bash
terraform plan -out=tfplan -var-file=terraform.tfvars
```

### Apply

```bash
terraform apply tfplan

# Update kubeconfig
aws eks update-kubeconfig --name $(terraform output -raw eks_cluster_name) --region us-west-2
```

### Destroy

```bash
# WARNING: Destroys all infrastructure
terraform destroy -var-file=terraform.tfvars
```

---

## CI/CD Identity (GitHub OIDC)

### GitHub OIDC Provider (run once per AWS account)

```hcl
# In a separate bootstrap terraform or manually
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_actions" {
  name = "github-actions-terraform"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:YOUR_ORG/YOUR_REPO:*"
        }
      }
    }]
  })
}

# Attach policies for Terraform operations
resource "aws_iam_role_policy_attachment" "terraform_admin" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"  # Scope down in production
}
```

---

## Implementation Checklist

- [ ] Run `init-backend.sh` to create S3 bucket and DynamoDB table
- [ ] Configure AWS credentials (profile or OIDC)
- [ ] Review and customize `terraform.tfvars`
- [ ] Run `terraform init`
- [ ] Run `terraform plan` and review output
- [ ] Run `terraform apply`
- [ ] Verify outputs: cluster endpoint, ECR URLs, IRSA roles
- [ ] Update kubeconfig and verify `kubectl get nodes`
- [ ] Deploy observability stack to observability namespace
- [ ] Deploy ALB ingress controller to platform namespace
- [ ] Verify Grafana URL is accessible
