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

variable "image_tag" {
  description = "Image tag the ECS task definition runs"
  type        = string
  default     = "latest"
}
