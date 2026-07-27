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

variable "tf_backend_bucket_name" {
  description = "S3 bucket name that stores Terraform remote state"
  type        = string
  default     = "klinden-tfstate"
}

variable "tf_backend_lock_table_name" {
  description = "DynamoDB table name used for Terraform state locking"
  type        = string
  default     = "klinden-tfstate"
}
