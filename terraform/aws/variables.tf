variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC; two /24 public subnets are carved from it"
  type        = string
  default     = "10.20.0.0/16"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider; set false if the account already has one"
  type        = bool
  default     = true
}

variable "github_repository" {
  description = "GitHub owner/repo allowed to push images and deploy via OIDC"
  type        = string
  default     = "kclinden/nebraska-app"
}

variable "github_branch" {
  description = "Branch whose workflows may assume the deploy role"
  type        = string
  default     = "main"
}

variable "image_tag" {
  description = "Image tag the ECS task definition runs"
  type        = string
  default     = "latest"
}
