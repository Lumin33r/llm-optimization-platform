# Design Document 5: GitHub Actions CI/CD

## Overview

This document defines the CI/CD pipeline architecture for the LLM Optimization Platform using GitHub Actions.

**Key Principles**:

- **GitHub OIDC to AWS** - No stored AWS credentials, federated identity
- **Build → Push → Deploy** workflow with verification gates
- **Kustomize-based deployment** with environment overlays
- **Explicit rollback strategy** with revision tracking

---

## Quick Start (Implementation Order)

```bash
# 1. Prerequisites (after design-01 Terraform apply)
# GitHub OIDC provider and IAM role created by Terraform

# 2. Create GitHub repository secrets (in GitHub UI)
# - AWS_REGION: us-west-2
# - AWS_ACCOUNT_ID: <your-account-id>
# - AWS_ROLE_ARN: arn:aws:iam::<account>:role/llmplatform-github-actions
# - HF_TOKEN: <huggingface-token> (for baseline model)

# 3. Copy workflow files to .github/workflows/
cp -r cicd-templates/.github/workflows/* .github/workflows/

# 4. Push to trigger CI
git push origin develop

# 5. Merge to main to trigger CD
git checkout main && git merge develop && git push
```

**Depends On**: [design-01-infrastructure.md](design-01-infrastructure.md) (OIDC setup)
**Feeds Into**: [design-02-kubernetes.md](design-02-kubernetes.md) (deployment targets)

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              GitHub Actions Workflows                                            │
│                                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                  CI Pipeline (on: push)                                   │  │
│  │                                                                                           │  │
│  │   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐    ┌────────────────┐    │  │
│  │   │  Lint   │───▶│  Test   │───▶│  Build  │───▶│ Push to ECR │───▶│ Verify Image  │    │  │
│  │   │         │    │         │    │  Image  │    │             │    │    Scan       │    │  │
│  │   └─────────┘    └─────────┘    └─────────┘    └─────────────┘    └────────────────┘    │  │
│  │                                                                                           │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                              │                                                   │
│                                              ▼ (on success + main branch)                       │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                 CD Pipeline (Deploy)                                      │  │
│  │                                                                                           │  │
│  │   ┌────────────────┐    ┌────────────────┐    ┌────────────────┐    ┌───────────────┐   │  │
│  │   │ Update Kubeconfig│──▶│ Kustomize Build│──▶│ kubectl apply  │──▶│ Verify Rollout │   │  │
│  │   │                │    │                │    │                │    │               │   │  │
│  │   └────────────────┘    └────────────────┘    └────────────────┘    └───────────────┘   │  │
│  │                                                                                           │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                           Infrastructure Pipeline (on: path infra/**)                     │  │
│  │                                                                                           │  │
│  │   ┌───────────────┐    ┌───────────────┐    ┌────────────────┐    ┌────────────────┐    │  │
│  │   │ terraform fmt │───▶│terraform plan │───▶│ Manual Approve │───▶│terraform apply │    │  │
│  │   │               │    │               │    │   (prod only)  │    │                │    │  │
│  │   └───────────────┘    └───────────────┘    └────────────────┘    └────────────────┘    │  │
│  │                                                                                           │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## GitHub OIDC Configuration

### AWS IAM Role for GitHub Actions

```hcl
# infra/modules/github_oidc/main.tf

# OIDC Provider (create once per AWS account)
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  tags            = var.tags
}

# Role for GitHub Actions
resource "aws_iam_role" "github_actions" {
  name = "${var.project}-github-actions"
  tags = var.tags

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
          # Restrict to specific repo and branches
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main",
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/develop",
            "repo:${var.github_org}/${var.github_repo}:pull_request"
          ]
        }
      }
    }]
  })
}

# ECR Push permissions
resource "aws_iam_role_policy" "ecr_push" {
  name = "ecr-push"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/${var.project}-*"
      }
    ]
  })
}

# EKS deployment permissions
resource "aws_iam_role_policy" "eks_deploy" {
  name = "eks-deploy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters"
        ]
        Resource = "*"
      }
    ]
  })
}

# Terraform state access (for infra workflows)
resource "aws_iam_role_policy" "terraform_state" {
  name = "terraform-state"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::tfstate-${var.project}-*",
          "arn:aws:s3:::tfstate-${var.project}-*/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem"
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/tf-locks-*"
      }
    ]
  })
}

output "role_arn" {
  description = "ARN of GitHub Actions IAM role"
  value       = aws_iam_role.github_actions.arn
}
```

---

## Workflow: Build, Push, Deploy

### Main CI/CD Workflow

```yaml
# .github/workflows/ci-cd.yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
    paths:
      - "services/**"
      - "k8s/**"
      - ".github/workflows/ci-cd.yaml"
  pull_request:
    branches: [main]
    paths:
      - "services/**"
      - "k8s/**"

env:
  AWS_REGION: us-west-2
  ECR_REGISTRY: ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-west-2.amazonaws.com
  PROJECT: llmplatform

permissions:
  id-token: write # Required for OIDC
  contents: read

jobs:
  # ===========================================
  # Lint and Test
  # ===========================================
  lint-and-test:
    name: Lint & Test
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -r services/requirements-dev.txt
          pip install ruff pytest pytest-asyncio

      - name: Lint with Ruff
        run: |
          ruff check services/

      - name: Run tests
        run: |
          pytest services/tests/ -v --tb=short

  # ===========================================
  # Build and Push Images
  # ===========================================
  build-push:
    name: Build & Push
    needs: lint-and-test
    runs-on: ubuntu-latest

    strategy:
      matrix:
        service: [gateway, quant-api, finetune-api, eval-api]

    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ env.PROJECT }}-github-actions
          role-session-name: github-actions-${{ github.run_id }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Docker meta
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-${{ github.ref_name == 'main' && 'prod' || 'dev' }}/${{ matrix.service }}
          tags: |
            type=sha,prefix=sha-
            type=ref,event=branch
            type=raw,value=latest,enable=${{ github.ref_name == 'main' }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: services/${{ matrix.service }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            SERVICE_NAME=${{ matrix.service }}
            GIT_SHA=${{ github.sha }}

      - name: Verify image scan
        run: |
          # Wait for ECR scan to complete
          IMAGE_TAG=$(echo "${{ steps.meta.outputs.tags }}" | head -n1)
          aws ecr wait image-scan-complete \
            --repository-name ${{ env.PROJECT }}-${{ github.ref_name == 'main' && 'prod' || 'dev' }}/${{ matrix.service }} \
            --image-id imageTag=sha-${{ github.sha }}

          # Check for critical vulnerabilities
          SCAN_RESULT=$(aws ecr describe-image-scan-findings \
            --repository-name ${{ env.PROJECT }}-${{ github.ref_name == 'main' && 'prod' || 'dev' }}/${{ matrix.service }} \
            --image-id imageTag=sha-${{ github.sha }} \
            --query 'imageScanFindings.findingSeverityCounts.CRITICAL' \
            --output text)

          if [ "$SCAN_RESULT" != "None" ] && [ "$SCAN_RESULT" -gt "0" ]; then
            echo "::error::Critical vulnerabilities found in image"
            exit 1
          fi

  # ===========================================
  # Deploy to Dev
  # ===========================================
  deploy-dev:
    name: Deploy to Dev
    needs: build-push
    if: github.ref == 'refs/heads/develop'
    runs-on: ubuntu-latest
    environment: dev

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ env.PROJECT }}-github-actions
          role-session-name: github-actions-deploy-${{ github.run_id }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Update kubeconfig
        run: |
          aws eks update-kubeconfig --name ${{ env.PROJECT }}-dev --region ${{ env.AWS_REGION }}

      - name: Install Kustomize
        uses: imranismail/setup-kustomize@v2

      - name: Deploy with Kustomize
        run: |
          cd k8s/overlays/dev

          # Update image tags to current SHA
          kustomize edit set image \
            gateway=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-dev/gateway:sha-${{ github.sha }} \
            quant-api=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-dev/quant-api:sha-${{ github.sha }} \
            finetune-api=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-dev/finetune-api:sha-${{ github.sha }} \
            eval-api=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-dev/eval-api:sha-${{ github.sha }}

          # Apply changes
          kustomize build . | kubectl apply -f -

      - name: Verify deployment
        run: |
          # Wait for rollouts to complete
          kubectl rollout status deployment/gateway -n platform --timeout=300s
          kubectl rollout status deployment/quant-api -n quant --timeout=300s
          kubectl rollout status deployment/finetune-api -n finetune --timeout=300s
          kubectl rollout status deployment/eval-api -n eval --timeout=300s

          # Verify pods are ready
          echo "=== Pod Status ==="
          kubectl get pods -A -l app.kubernetes.io/part-of=llm-optimization-platform

          # Verify endpoints
          echo "=== Endpoints ==="
          kubectl get endpoints -A | grep -E 'gateway|quant|finetune|eval'

      - name: Health check
        run: |
          # Get gateway service URL
          GATEWAY_URL=$(kubectl get ingress platform-ingress -n platform -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

          # Wait for DNS propagation
          sleep 30

          # Health check
          curl -sf "http://${GATEWAY_URL}/health" || exit 1
          echo "Health check passed"

  # ===========================================
  # Deploy to Prod
  # ===========================================
  deploy-prod:
    name: Deploy to Prod
    needs: build-push
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production # Requires approval

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ env.PROJECT }}-github-actions
          role-session-name: github-actions-deploy-prod-${{ github.run_id }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Update kubeconfig
        run: |
          aws eks update-kubeconfig --name ${{ env.PROJECT }}-prod --region ${{ env.AWS_REGION }}

      - name: Install Kustomize
        uses: imranismail/setup-kustomize@v2

      - name: Deploy with Kustomize
        run: |
          cd k8s/overlays/prod

          # Update image tags
          kustomize edit set image \
            gateway=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-prod/gateway:sha-${{ github.sha }} \
            quant-api=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-prod/quant-api:sha-${{ github.sha }} \
            finetune-api=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-prod/finetune-api:sha-${{ github.sha }} \
            eval-api=${{ env.ECR_REGISTRY }}/${{ env.PROJECT }}-prod/eval-api:sha-${{ github.sha }}

          kustomize build . | kubectl apply -f -

      - name: Verify deployment
        run: |
          kubectl rollout status deployment/gateway -n platform --timeout=600s
          kubectl rollout status deployment/quant-api -n quant --timeout=600s
          kubectl rollout status deployment/finetune-api -n finetune --timeout=600s
          kubectl rollout status deployment/eval-api -n eval --timeout=600s

      - name: Smoke test
        run: |
          GATEWAY_URL=$(kubectl get ingress platform-ingress -n platform -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

          # Health check
          curl -sf "http://${GATEWAY_URL}/health"

          # Quick prediction test
          curl -sf -X POST "http://${GATEWAY_URL}/api/quant/predict" \
            -H "Content-Type: application/json" \
            -d '{"prompt": "test", "max_tokens": 5}' \
            || echo "Warning: Prediction test failed"
```

---

## Workflow: Terraform Infrastructure

```yaml
# .github/workflows/terraform.yaml
name: Terraform Infrastructure

on:
  push:
    branches: [main]
    paths:
      - "infra/**"
  pull_request:
    branches: [main]
    paths:
      - "infra/**"
  workflow_dispatch:
    inputs:
      environment:
        description: "Target environment"
        required: true
        default: "dev"
        type: choice
        options:
          - dev
          - staging
          - prod
      action:
        description: "Terraform action"
        required: true
        default: "plan"
        type: choice
        options:
          - plan
          - apply
          - destroy

env:
  AWS_REGION: us-west-2
  PROJECT: llmplatform
  TF_VERSION: 1.6.0

permissions:
  id-token: write
  contents: read
  pull-requests: write

jobs:
  # ===========================================
  # Terraform Format Check
  # ===========================================
  fmt:
    name: Format Check
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Terraform Format
        run: terraform fmt -check -recursive infra/

  # ===========================================
  # Terraform Plan
  # ===========================================
  plan:
    name: Plan (${{ matrix.environment }})
    needs: fmt
    runs-on: ubuntu-latest

    strategy:
      matrix:
        environment: [dev] # Add staging, prod as needed

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ env.PROJECT }}-github-actions
          aws-region: ${{ env.AWS_REGION }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Terraform Init
        working-directory: infra/envs/${{ matrix.environment }}
        run: terraform init

      - name: Terraform Plan
        id: plan
        working-directory: infra/envs/${{ matrix.environment }}
        run: |
          terraform plan -no-color -out=tfplan 2>&1 | tee plan_output.txt
          echo "plan_exitcode=$?" >> $GITHUB_OUTPUT

      - name: Upload Plan
        uses: actions/upload-artifact@v4
        with:
          name: tfplan-${{ matrix.environment }}
          path: infra/envs/${{ matrix.environment }}/tfplan

      - name: Comment Plan on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const plan = fs.readFileSync('infra/envs/${{ matrix.environment }}/plan_output.txt', 'utf8');
            const truncatedPlan = plan.length > 60000 ? plan.substring(0, 60000) + '\n...(truncated)' : plan;

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `### Terraform Plan - ${{ matrix.environment }}\n\n\`\`\`hcl\n${truncatedPlan}\n\`\`\``
            });

  # ===========================================
  # Terraform Apply (main branch only)
  # ===========================================
  apply:
    name: Apply (${{ matrix.environment }})
    needs: plan
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: ${{ matrix.environment }} # Requires approval for prod

    strategy:
      matrix:
        environment: [dev]

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ env.PROJECT }}-github-actions
          aws-region: ${{ env.AWS_REGION }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Download Plan
        uses: actions/download-artifact@v4
        with:
          name: tfplan-${{ matrix.environment }}
          path: infra/envs/${{ matrix.environment }}

      - name: Terraform Init
        working-directory: infra/envs/${{ matrix.environment }}
        run: terraform init

      - name: Terraform Apply
        working-directory: infra/envs/${{ matrix.environment }}
        run: terraform apply -auto-approve tfplan

      - name: Output Results
        working-directory: infra/envs/${{ matrix.environment }}
        run: |
          echo "=== Terraform Outputs ==="
          terraform output -json | jq .

  # ===========================================
  # Terraform Destroy (manual only)
  # ===========================================
  destroy:
    name: Destroy (${{ inputs.environment }})
    if: github.event_name == 'workflow_dispatch' && inputs.action == 'destroy'
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}-destroy # Extra approval

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ env.PROJECT }}-github-actions
          aws-region: ${{ env.AWS_REGION }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Terraform Init
        working-directory: infra/envs/${{ inputs.environment }}
        run: terraform init

      - name: Terraform Destroy
        working-directory: infra/envs/${{ inputs.environment }}
        run: |
          echo "::warning::DESTROYING ${{ inputs.environment }} INFRASTRUCTURE"
          terraform destroy -auto-approve
```

---

## Rollback Strategy

### Deployment Rollback Commands

```bash
# Rollback specific deployment to previous revision
kubectl rollout undo deployment/gateway -n platform

# Rollback to specific revision
kubectl rollout undo deployment/gateway -n platform --to-revision=3

# Check rollout history
kubectl rollout history deployment/gateway -n platform

# Check specific revision details
kubectl rollout history deployment/gateway -n platform --revision=3
```

### Automated Rollback Workflow

```yaml
# .github/workflows/rollback.yaml
name: Rollback Deployment

on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Environment to rollback"
        required: true
        type: choice
        options:
          - dev
          - staging
          - prod
      service:
        description: "Service to rollback"
        required: true
        type: choice
        options:
          - gateway
          - quant-api
          - finetune-api
          - eval-api
          - all
      revision:
        description: "Revision number (blank for previous)"
        required: false
        type: string

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: us-west-2
  PROJECT: llmplatform

jobs:
  rollback:
    name: Rollback ${{ inputs.service }} in ${{ inputs.environment }}
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}

    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ env.PROJECT }}-github-actions
          aws-region: ${{ env.AWS_REGION }}

      - name: Update kubeconfig
        run: |
          aws eks update-kubeconfig --name ${{ env.PROJECT }}-${{ inputs.environment }} --region ${{ env.AWS_REGION }}

      - name: Rollback deployment
        run: |
          SERVICES="${{ inputs.service }}"
          REVISION="${{ inputs.revision }}"

          if [ "$SERVICES" = "all" ]; then
            SERVICES="gateway quant-api finetune-api eval-api"
          fi

          for SERVICE in $SERVICES; do
            case $SERVICE in
              gateway) NAMESPACE="platform" ;;
              quant-api) NAMESPACE="quant" ;;
              finetune-api) NAMESPACE="finetune" ;;
              eval-api) NAMESPACE="eval" ;;
            esac

            echo "Rolling back $SERVICE in namespace $NAMESPACE"

            if [ -n "$REVISION" ]; then
              kubectl rollout undo deployment/$SERVICE -n $NAMESPACE --to-revision=$REVISION
            else
              kubectl rollout undo deployment/$SERVICE -n $NAMESPACE
            fi

            kubectl rollout status deployment/$SERVICE -n $NAMESPACE --timeout=300s
          done

      - name: Verify rollback
        run: |
          echo "=== Current Pod Status ==="
          kubectl get pods -A -l app.kubernetes.io/part-of=llm-optimization-platform

          echo "=== Deployment Images ==="
          kubectl get deployments -A -l app.kubernetes.io/part-of=llm-optimization-platform -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.template.spec.containers[0].image}{"\n"}{end}'
```

---

## Branch Protection and Environments

### GitHub Environment Configuration

| Environment  | Protection Rules                          | Secrets          |
| ------------ | ----------------------------------------- | ---------------- |
| `dev`        | None                                      | `AWS_ACCOUNT_ID` |
| `staging`    | Required reviewers (1)                    | `AWS_ACCOUNT_ID` |
| `production` | Required reviewers (2), deployment branch | `AWS_ACCOUNT_ID` |
| `*-destroy`  | Required reviewers (2), admin only        | `AWS_ACCOUNT_ID` |

### Branch Rules

```yaml
# Required for main branch
- Require pull request reviews (1+)
- Require status checks (lint-and-test, plan)
- Require branches to be up to date
- Restrict who can push (maintainers only)
```

---

## Secrets Management

### Required Repository Secrets

| Secret           | Description                 | Where Used    |
| ---------------- | --------------------------- | ------------- |
| `AWS_ACCOUNT_ID` | AWS account ID for ECR/OIDC | All workflows |

### Environment-Specific Secrets (Optional)

| Secret              | Environment | Description                 |
| ------------------- | ----------- | --------------------------- |
| `SAGEMAKER_API_KEY` | production  | SageMaker auth (if needed)  |
| `GRAFANA_API_KEY`   | production  | Grafana API for annotations |

---

## Workflow Triggers Summary

| Workflow  | Trigger                               | Branches      | Paths               |
| --------- | ------------------------------------- | ------------- | ------------------- |
| CI/CD     | push, pull_request                    | main, develop | services/**, k8s/** |
| Terraform | push, pull_request, workflow_dispatch | main          | infra/\*\*          |
| Rollback  | workflow_dispatch                     | any           | -                   |

---

## Implementation Checklist

- [ ] Create GitHub OIDC IAM role in AWS
- [ ] Configure GitHub repository secrets (`AWS_ACCOUNT_ID`)
- [ ] Create GitHub environments (dev, staging, production, \*-destroy)
- [ ] Configure environment protection rules
- [ ] Add CI/CD workflow file (`.github/workflows/ci-cd.yaml`)
- [ ] Add Terraform workflow file (`.github/workflows/terraform.yaml`)
- [ ] Add Rollback workflow file (`.github/workflows/rollback.yaml`)
- [ ] Create Dockerfiles for all services
- [ ] Test build workflow on feature branch
- [ ] Test deploy workflow on develop branch
- [ ] Test production deploy with approval
- [ ] Document rollback procedure
