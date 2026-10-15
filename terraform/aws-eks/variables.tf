variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "cluster_name" {
  type    = string
  default = "nebraska-eks"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{0,39}$", var.cluster_name))
    error_message = "Use a cluster name starting with a letter, followed by letters, digits or hyphens; at most 40 characters."
  }
}

variable "kubernetes_version" {
  type    = string
  default = "1.35"
}

variable "public_access_cidrs" {
  description = "IPv4 CIDRs allowed to reach the EKS API. Defaults to internet-wide access; IAM/Kubernetes authentication is still required."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition = length(var.public_access_cidrs) > 0 && alltrue([
      for cidr in var.public_access_cidrs : can(cidrnetmask(cidr))
    ])
    error_message = "Provide at least one valid IPv4 CIDR."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "namespace" {
  type    = string
  default = "nebraska-app"
}

variable "image_repository" {
  description = "Override the app image repository; empty uses this stack's ECR repository."
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Published image including configurable DynamoDB table names. Prefer an immutable tag."
  type        = string
  default     = "latest"
}

variable "public_alb_enabled" {
  description = "Expose this vulnerable lab through an internet-facing ALB. Disable for port-forward-only access."
  type        = bool
  default     = true
}

variable "alb_ingress_cidrs" {
  description = "IPv4 CIDRs allowed to reach the public application; independent of the EKS API allowlist."
  type        = set(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = length(var.alb_ingress_cidrs) > 0 && alltrue([for cidr in var.alb_ingress_cidrs : can(cidrnetmask(cidr))])
    error_message = "Provide at least one valid IPv4 CIDR."
  }
}

variable "alb_certificate_arn" {
  description = "Optional ACM certificate ARN in this region; enables HTTPS and redirects HTTP to HTTPS."
  type        = string
  default     = ""
}

variable "alb_hostname" {
  description = "Custom DNS name pointing to the ALB; required when using an ACM certificate. DNS is managed separately."
  type        = string
  default     = ""
}