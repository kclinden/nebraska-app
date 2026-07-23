# Nebraska App

Infrastructure and deployment configuration for the Nebraska app.

## Repository Layout

- `app/` application source and related assets
- `terraform/` infrastructure as code for cloud resources

## Terraform Quick Start

From the repository root:

```bash
cd terraform
terraform init
terraform fmt -recursive
terraform validate
```

## Notes

- Terraform state files are intentionally ignored by git.
- CI validates Terraform formatting and configuration on push and pull requests.
