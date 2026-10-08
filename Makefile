TF_DIR     := terraform/aws
AWS_REGION ?= us-east-1
AWS_PROFILE ?= master
TF         := terraform -chdir=$(TF_DIR)
IMAGE_TAG  := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
# Image published by the Docker Build workflow; copied into ECR on deploy.
GHCR_IMAGE ?= ghcr.io/kclinden/nebraska-app
GHCR_TAG   ?= latest

export AWS_PROFILE AWS_REGION
export TF_VAR_aws_region := $(AWS_REGION)

# Resolved per command so it reflects the account selected by `make azure-login`.
AZ_TF := ARM_SUBSCRIPTION_ID=$$(az account show --query id -o tsv) terraform -chdir=terraform/azure
export AZURE_EXTENSION_USE_DYNAMIC_INSTALL := yes_without_prompt

.DEFAULT_GOAL := help
.PHONY: help setup-check scores local-up local-down local-restart local-logs local-reseed \
        aws-login aws-init aws-plan aws-deploy aws-ecr-login aws-image aws-image-local aws-push \
        aws-redeploy aws-url aws-logs aws-destroy \
        azure-login azure-init azure-plan azure-deploy azure-outputs azure-image azure-image-local \
        azure-push azure-redeploy azure-url azure-logs azure-destroy

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup-check: ## Check dev tools and logins (SECTIONS="local aws azure" to limit)
	@scripts/check_setup.sh $(SECTIONS)

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
aws-deploy: aws-init ## Create/update everything: network, ECR, copy image from GHCR, ECS
	$(TF) apply -auto-approve -target=aws_ecr_repository.app -target=aws_ecr_lifecycle_policy.app
	@$(MAKE) --no-print-directory aws-image
	$(TF) apply
	@$(MAKE) --no-print-directory aws-redeploy
	@$(MAKE) --no-print-directory aws-url

aws-ecr-login: aws-login
	$(eval ECR_URL := $(shell $(TF) output -raw ecr_repository_url 2>/dev/null))
	@test -n "$(ECR_URL)" || { echo "No ECR repository in Terraform state; run make aws-deploy first." >&2; exit 1; }
	aws ecr get-login-password | docker login --username AWS --password-stdin $(firstword $(subst /, ,$(ECR_URL)))

aws-image: aws-ecr-login ## Copy the GHCR image (GHCR_TAG, default latest) into ECR as :latest
	docker pull --platform linux/amd64 $(GHCR_IMAGE):$(GHCR_TAG)
	docker tag $(GHCR_IMAGE):$(GHCR_TAG) $(ECR_URL):latest
	docker push $(ECR_URL):latest

aws-image-local: aws-ecr-login scores ## Build the image from your working copy and push it to ECR as :latest
	docker build --platform linux/amd64 -t $(ECR_URL):latest -t $(ECR_URL):sha-$(IMAGE_TAG) ./app
	docker push $(ECR_URL):sha-$(IMAGE_TAG)
	docker push $(ECR_URL):latest

aws-push: aws-image aws-redeploy ## Copy the latest GHCR image to ECR and roll out ECS

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

aws-destroy: aws-init ## Destroy all AWS resources
	$(TF) destroy

# ---------- Azure (Terraform + Container Apps, local state) ----------

azure-login: ## Ensure the Azure CLI has a valid login and show the active subscription
	@az account get-access-token -o none 2>/dev/null || az login
	@echo "Azure subscription: $$(az account show --query '[name, id]' -o tsv | paste -sd ' ' -)"

azure-init: azure-login ## Register resource providers and initialize Terraform (local state in terraform/azure)
	@for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.ManagedIdentity Microsoft.OperationalInsights Microsoft.Storage; do \
		az provider register --namespace $$ns --wait -o none; \
	done
	$(AZ_TF) init -upgrade=false

azure-plan: azure-init ## Show the Azure Terraform plan
	$(AZ_TF) fmt -recursive
	$(AZ_TF) validate
	$(AZ_TF) plan

# ACR is created first so the image exists before the container app starts.
azure-deploy: azure-init ## Create/update everything: storage, ACR, import image from GHCR, Container App
	$(AZ_TF) apply -auto-approve -target=azurerm_container_registry.app
	@$(MAKE) --no-print-directory azure-image
	$(AZ_TF) apply
	@$(MAKE) --no-print-directory azure-url

azure-outputs: azure-login
	$(eval AZ_RG := $(shell terraform -chdir=terraform/azure output -raw resource_group_name 2>/dev/null))
	$(eval AZ_ACR := $(shell terraform -chdir=terraform/azure output -raw acr_name 2>/dev/null))
	$(eval AZ_APP := $(shell terraform -chdir=terraform/azure output -raw container_app_name 2>/dev/null))
	@test -n "$(AZ_ACR)" || { echo "No ACR in Terraform state; run make azure-deploy first." >&2; exit 1; }

azure-image: azure-outputs ## Import the GHCR image (GHCR_TAG, default latest) into ACR as :latest
	az acr import --name $(AZ_ACR) --source $(GHCR_IMAGE):$(GHCR_TAG) --image nebraska-app:latest --force

azure-image-local: azure-outputs scores ## Build the image from your working copy in ACR as :latest
	az acr build --registry $(AZ_ACR) --platform linux/amd64 --image nebraska-app:latest --image nebraska-app:sha-$(IMAGE_TAG) ./app

azure-push: azure-image azure-redeploy ## Import the latest GHCR image into ACR and roll out the Container App

azure-redeploy: azure-outputs ## Create a new Container App revision so it re-pulls :latest
	@test -n "$(AZ_APP)" || { echo "No Container App in Terraform state; run make azure-deploy first." >&2; exit 1; }
	az containerapp update --name $(AZ_APP) --resource-group $(AZ_RG) --revision-suffix r$$(date +%s) -o none
	@echo "Container App $(AZ_APP) updated"

azure-url: azure-login ## Print the Azure app URL
	@terraform -chdir=terraform/azure output -raw app_url; echo

azure-logs: azure-outputs ## Stream the Container App's console logs
	az containerapp logs show --name $(AZ_APP) --resource-group $(AZ_RG) --follow

azure-destroy: azure-init ## Destroy all Azure resources
	$(AZ_TF) destroy

