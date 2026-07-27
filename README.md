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

## Terraform Remote State (S3 + DynamoDB Locking)

This repo is configured for an S3 backend using partial backend config in `terraform/backend.tf`.

Backend resources are also managed by this same Terraform stack in `terraform/backend_resources.tf`.

1. Bootstrap backend resources with local state (one time):

```bash
cd terraform
terraform init -backend=false
terraform apply -target=aws_s3_bucket.tf_state -target=aws_dynamodb_table.tf_lock
```

2. Create local backend config from the example:

```bash
cd terraform
cp backend.hcl.example backend.hcl
```

Defaults are set to the requested names:

- bucket: `klinden-tfstate`
- dynamodb_table: `klinden-tfstate`

Update values only if you want different names.

3. Migrate existing local state into S3:

```bash
terraform init -backend-config=backend.hcl -migrate-state
terraform plan
```

Notes:

- `terraform/backend.hcl` is gitignored because it is environment-specific.
- DynamoDB table provides state locking to prevent concurrent Terraform writes.

## Application Source and Deploy Model

- The Flask application source now lives in `app/app.py`.
- EC2 user data now clones application code from GitHub during instance boot.
- EC2 installs dependencies from `app/requirements.txt`.

## Update App Code Without Terraform Redeploy

After pushing app changes to GitHub, run:

```bash
cd terraform
./update_app_on_ec2.sh
```

This uses AWS Systems Manager Run Command to execute `/usr/local/bin/update-husker-app` on the instance, which pulls the latest code and restarts services.

## Notes

- Terraform state files are intentionally ignored by git.
- CI validates Terraform formatting and configuration on push and pull requests.
