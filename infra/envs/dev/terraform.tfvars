aws_region      = "us-west-2"
project         = "llmplatform"
environment     = "dev"
vpc_cidr        = "10.0.0.0/16"
cluster_version = "1.29"

node_groups = {
  general = {
    instance_types = ["t3.medium"]
    disk_size      = 50
    desired_size   = 2
    min_size       = 1
    max_size       = 4
    labels = {
      "role" = "general"
    }
    taints = []
  }
  gpu = {
    instance_types = ["g4dn.xlarge"]
    disk_size      = 100
    desired_size   = 0
    min_size       = 0
    max_size       = 2
    ami_type       = "AL2_x86_64_GPU"
    labels = {
      "role"                   = "gpu"
      "nvidia.com/gpu.present" = "true"
    }
    taints = [
      {
        key    = "nvidia.com/gpu"
        value  = "true"
        effect = "NO_SCHEDULE"
      }
    ]
  }
}
