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
