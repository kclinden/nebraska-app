TF_DIR     := terraform/aws
AWS_REGION ?= us-east-1
AWS_PROFILE ?= master
TF         := terraform -chdir=$(TF_DIR)
IMAGE_TAG  := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

export AWS_PROFILE AWS_REGION
export TF_VAR_aws_region := $(AWS_REGION)

.DEFAULT_GOAL := help
.PHONY: help scores local-up local-down local-restart local-logs local-reseed \
        aws-login aws-init aws-plan aws-deploy aws-image aws-push aws-redeploy aws-url aws-logs \
        aws-destroy gh-setup

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------- Local (Docker + DynamoDB Local) ----------

scores: ## Fetch latest game scores/stats into app/scores.json (keeps the existing file if ESPN is unreachable)
	@python3 scripts/update_scores.py || { test -f app/scores.json && echo "WARNING: score fetch failed; using existing app/scores.json" >&2; }

local-up: scores ## Build and start the local stack at http://localhost:8080
	docker compose up --build -d
	@echo "App running at http://localhost:8080"

local-down: ## Stop the local stack (in-memory data is discarded)
	docker compose down

local-restart: local-down local-up ## Rebuild and restart everything with fresh data

local-logs: ## Tail logs from the local stack
	docker compose logs -f

local-reseed: ## Re-run the DynamoDB Local seeder from data/*.yaml
	docker compose run --rm seed

# ---------- AWS (Terraform + ECS Fargate, local state) ----------

aws-login: ## Ensure an AWS SSO session is active for AWS_PROFILE (default: master)
	@aws sts get-caller-identity >/dev/null 2>&1 || aws sso login
	@echo "AWS identity ($(AWS_PROFILE)): $$(aws sts get-caller-identity --query Arn --output text)"

aws-init: aws-login ## Initialize Terraform (local state in terraform/aws)
	$(TF) init -upgrade=false

aws-plan: aws-init ## Show the Terraform plan
	$(TF) fmt -recursive
	$(TF) validate
	$(TF) plan

# ECR is created first so the image exists before the ECS service starts.
aws-deploy: aws-init ## Create/update everything: network, ECR, image, ECS, then link GitHub Actions
	$(TF) apply -auto-approve -target=aws_ecr_repository.app -target=aws_ecr_lifecycle_policy.app
	@$(MAKE) --no-print-directory aws-image
	$(TF) apply
	@$(MAKE) --no-print-directory aws-redeploy
	@$(MAKE) --no-print-directory gh-setup
	@$(MAKE) --no-print-directory aws-url

aws-image: aws-login scores ## Build the image locally and push it to ECR
	$(eval ECR_URL := $(shell $(TF) output -raw ecr_repository_url 2>/dev/null))
	@test -n "$(ECR_URL)" || { echo "No ECR repository in Terraform state; run make aws-deploy first." >&2; exit 1; }
	aws ecr get-login-password | docker login --username AWS --password-stdin $(firstword $(subst /, ,$(ECR_URL)))
	docker build --platform linux/amd64 -t $(ECR_URL):latest -t $(ECR_URL):sha-$(IMAGE_TAG) ./app
	docker push $(ECR_URL):sha-$(IMAGE_TAG)
	docker push $(ECR_URL):latest

aws-push: aws-image aws-redeploy ## Build, push, and roll out the image from your machine

aws-redeploy: aws-login ## Restart the ECS service on the current :latest image and wait until stable
	$(eval CLUSTER := $(shell $(TF) output -raw ecs_cluster_name 2>/dev/null))
	$(eval SERVICE := $(shell $(TF) output -raw ecs_service_name 2>/dev/null))
	@test -n "$(SERVICE)" || { echo "No ECS service in Terraform state; run make aws-deploy first." >&2; exit 1; }
	aws ecs update-service --cluster $(CLUSTER) --service $(SERVICE) --force-new-deployment --no-cli-pager >/dev/null
	aws ecs wait services-stable --cluster $(CLUSTER) --services $(SERVICE)
	@echo "Service $(SERVICE) is stable"

aws-url: aws-login ## Print the app URL
	@$(TF) output -raw app_url; echo

aws-logs: aws-login ## Tail the app's CloudWatch logs
	aws logs tail /ecs/husker-app --follow

aws-destroy: aws-init ## Destroy all AWS resources and unlink GitHub Actions
	$(TF) destroy
	-gh variable delete AWS_ROLE_ARN

# ---------- GitHub Actions ----------

gh-setup: ## Set the AWS_ROLE_ARN repo variable so the workflow can push to ECR and deploy
	@command -v gh >/dev/null || { echo "Install the GitHub CLI or set AWS_ROLE_ARN manually: $$($(TF) output -raw github_actions_role_arn)"; exit 0; }
	gh variable set AWS_ROLE_ARN --body "$$($(TF) output -raw github_actions_role_arn)"
	gh variable set AWS_REGION --body "$(AWS_REGION)"
