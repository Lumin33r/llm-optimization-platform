terraform {
  backend "s3" {
    bucket         = "troys-bigbucket-west2"
    key            = "terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true
    dynamodb_table = "tf-locks-llmplatform-dev"

    # Optional: Use role assumption for CI
    # role_arn = "arn:aws:iam::ACCOUNT_ID:role/terraform-state-role"
  }
}
