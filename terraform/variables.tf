variable "app_repo_url" {
  description = "GitHub repository URL used by EC2 to clone/pull the app source"
  type        = string
  default     = "https://github.com/kclinden/nebraska-app.git"
}

variable "app_repo_branch" {
  description = "Git branch deployed on the EC2 instance"
  type        = string
  default     = "main"
}

variable "github_token_parameter_name" {
  description = "SSM SecureString parameter name containing a GitHub token with repo read access"
  type        = string
  default     = "/husker/github/token"
}
