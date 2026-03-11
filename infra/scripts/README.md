# infra/scripts/

Shell scripts for Terraform lifecycle management. Wraps common terraform commands with environment-aware paths and post-apply actions.

## Files

| Script            | Purpose                                                     |
| ----------------- | ----------------------------------------------------------- |
| `init-backend.sh` | Creates S3 bucket + DynamoDB table for remote state backend |
| `plan.sh`         | Runs `terraform plan` for a given environment               |
| `apply.sh`        | Applies a saved plan and updates kubeconfig                 |
| `destroy.sh`      | Destroys all resources for an environment                   |

## Usage

```bash
# First-time setup: create state backend
bash infra/scripts/init-backend.sh llmplatform dev us-west-2

# Plan, review, apply
bash infra/scripts/plan.sh dev
bash infra/scripts/apply.sh dev
```

## Key Behavior

`init-backend.sh` creates a secure state backend:

- S3 bucket with versioning, KMS encryption, public access blocked
- DynamoDB table with PAY_PER_REQUEST for state locking

`apply.sh` automatically updates kubeconfig after successful apply:

```bash
aws eks update-kubeconfig --name "$(terraform output -raw eks_cluster_name)"
```
