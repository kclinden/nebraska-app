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

## Application Source and Deploy Model

- The Flask application source now lives in `app/app.py`.
- EC2 user data now clones application code from GitHub during instance boot.
- EC2 installs dependencies from `app/requirements.txt`.

### Private Repo Access for EC2

For private repositories, store a GitHub token in SSM Parameter Store as a SecureString.

```bash
aws ssm put-parameter \
	--region us-east-1 \
	--name /husker/github/token \
	--type SecureString \
	--overwrite \
	--value "YOUR_GITHUB_TOKEN"
```

The EC2 instance reads this parameter at runtime and uses it for git clone/pull.

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
