SHELL      := /bin/bash
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
# Homebrew's az on Python 3.14 prints SyntaxWarnings on every call.
export PYTHONWARNINGS := ignore::SyntaxWarning

# Project resolved per command from the active gcloud config (`gcloud config set project ...`).
GCP_REGION ?= us-central1
GCP_TF := TF_VAR_project_id=$$(gcloud config get-value project 2>/dev/null) TF_VAR_region=$(GCP_REGION) terraform -chdir=terraform/gcp
GCP_OUT = $(shell terraform -chdir=terraform/gcp output -raw $(1) 2>/dev/null)

# VERBOSE=1 adds Terraform INFO logs and az/gcloud verbose output.
ifeq ($(VERBOSE),1)
export TF_LOG := INFO
AZ_FLAGS := --verbose
GCP_FLAGS := --verbosity=info
endif

# Usage: $(call step,Message) - avoid commas in the message.
step = @printf '\n\033[1;36m==> %s\033[0m\n' "$(1)"

.DEFAULT_GOAL := help
.PHONY: help setup-check scores local-up local-down local-restart local-logs local-reseed \
        aws-login aws-init aws-plan aws-deploy aws-ecr-login aws-image aws-image-local aws-push \
        aws-redeploy aws-url aws-logs aws-destroy \
        azure-login azure-init azure-plan azure-deploy azure-outputs azure-image azure-image-local \
        azure-push azure-redeploy azure-wait azure-status azure-url azure-logs azure-destroy \
        gcp-login gcp-init gcp-plan gcp-deploy gcp-outputs gcp-image gcp-image-local gcp-push \
        gcp-redeploy gcp-wait gcp-status gcp-url gcp-logs gcp-destroy

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup-check: ## Check dev tools and logins (SECTIONS="local aws azure gcp" to limit)
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
	$(call step,Checking AWS SSO session for profile $(AWS_PROFILE))
	@aws sts get-caller-identity >/dev/null 2>&1 || aws sso login
	@echo "Identity: $$(aws sts get-caller-identity --query Arn --output text)"
	@echo "Region:   $(AWS_REGION)"

aws-init: aws-login ## Initialize Terraform (local state in terraform/aws)
	$(call step,Initializing Terraform in $(TF_DIR))
	$(TF) init -upgrade=false

aws-plan: aws-init ## Show the Terraform plan
	$(call step,Formatting and validating Terraform)
	$(TF) fmt -recursive
	$(TF) validate
	$(call step,Planning AWS changes)
	$(TF) plan

# ECR is created first so the image exists before the ECS service starts.
aws-deploy: aws-init ## Create/update everything: network, ECR, copy image from GHCR, ECS
	$(call step,[1/4] Creating ECR repository)
	$(TF) apply -auto-approve -target=aws_ecr_repository.app -target=aws_ecr_lifecycle_policy.app
	$(call step,[2/4] Copying $(GHCR_IMAGE):$(GHCR_TAG) into ECR)
	@$(MAKE) --no-print-directory aws-image
	$(call step,[3/4] Applying full AWS stack)
	$(TF) apply
	$(call step,[4/4] Rolling out ECS service)
	@$(MAKE) --no-print-directory aws-redeploy
	$(call step,AWS deploy complete)
	@$(MAKE) --no-print-directory aws-url

aws-ecr-login: aws-login
	$(eval ECR_URL := $(shell $(TF) output -raw ecr_repository_url 2>/dev/null))
	@test -n "$(ECR_URL)" || { echo "No ECR repository in Terraform state; run make aws-deploy first." >&2; exit 1; }
	$(call step,Logging Docker in to $(firstword $(subst /, ,$(ECR_URL))))
	aws ecr get-login-password | docker login --username AWS --password-stdin $(firstword $(subst /, ,$(ECR_URL)))

aws-image: aws-ecr-login ## Copy the GHCR image (GHCR_TAG, default latest) into ECR as :latest
	$(call step,Pulling $(GHCR_IMAGE):$(GHCR_TAG))
	docker pull --platform linux/amd64 $(GHCR_IMAGE):$(GHCR_TAG)
	$(call step,Pushing to $(ECR_URL):latest)
	docker tag $(GHCR_IMAGE):$(GHCR_TAG) $(ECR_URL):latest
	docker push $(ECR_URL):latest
	@echo "ECR digest: $$(aws ecr describe-images --repository-name $(lastword $(subst /, ,$(ECR_URL))) --image-ids imageTag=latest --query 'imageDetails[0].imageDigest' --output text)"

aws-image-local: aws-ecr-login scores ## Build the image from your working copy and push it to ECR as :latest
	$(call step,Building ./app for linux/amd64)
	docker build --platform linux/amd64 -t $(ECR_URL):latest -t $(ECR_URL):sha-$(IMAGE_TAG) ./app
	$(call step,Pushing to $(ECR_URL))
	docker push $(ECR_URL):sha-$(IMAGE_TAG)
	docker push $(ECR_URL):latest

aws-push: aws-image aws-redeploy ## Copy the latest GHCR image to ECR and roll out ECS

aws-redeploy: aws-login ## Restart the ECS service on the current :latest image and wait until stable
	$(eval CLUSTER := $(shell $(TF) output -raw ecs_cluster_name 2>/dev/null))
	$(eval SERVICE := $(shell $(TF) output -raw ecs_service_name 2>/dev/null))
	@test -n "$(SERVICE)" || { echo "No ECS service in Terraform state; run make aws-deploy first." >&2; exit 1; }
	$(call step,Forcing new deployment of $(CLUSTER)/$(SERVICE))
	aws ecs update-service --cluster $(CLUSTER) --service $(SERVICE) --force-new-deployment --no-cli-pager >/dev/null
	@echo "Waiting for rollout (checks every 15s; up to 15 min)..."
	@for i in $$(seq 1 60); do \
		read -r state running desired <<< "$$(aws ecs describe-services --cluster $(CLUSTER) --services $(SERVICE) \
			--query 'services[0].[deployments[?status==`PRIMARY`]|[0].rolloutState, runningCount, desiredCount]' --output text)"; \
		printf '  %s  rollout=%s running=%s/%s\n' "$$(date +%H:%M:%S)" "$$state" "$$running" "$$desired"; \
		case "$$state" in COMPLETED) exit 0;; FAILED) echo "Rollout failed; see make aws-logs" >&2; exit 1;; esac; \
		sleep 15; \
	done; echo "Timed out waiting for rollout" >&2; exit 1
	@echo "Service $(SERVICE) is stable"

aws-url: aws-login ## Print the app URL
	@url=$$($(TF) output -raw app_url 2>/dev/null); echo "App URL: $${url:-(not deployed; run make aws-deploy)}"

aws-logs: aws-login ## Tail the app's CloudWatch logs
	$(call step,Tailing /ecs/husker-app (Ctrl-C to stop))
	aws logs tail /ecs/husker-app --follow

aws-destroy: aws-init ## Destroy all AWS resources
	$(call step,Destroying AWS stack)
	$(TF) destroy

# ---------- Azure (Terraform + App Service, local state) ----------

azure-login: ## Ensure the Azure CLI has a valid login and show the active subscription
	$(call step,Checking Azure CLI login)
	@az account get-access-token -o none 2>/dev/null || az login
	@echo "Subscription: $$(az account show --query '[name, id]' -o tsv | paste -sd ' ' -)"
	@echo "Signed in as: $$(az account show --query user.name -o tsv)"

azure-init: azure-login ## Register resource providers and initialize Terraform (local state in terraform/azure)
	$(call step,Registering Azure resource providers)
	@for ns in Microsoft.Web Microsoft.ContainerRegistry Microsoft.ManagedIdentity Microsoft.Storage; do \
		printf '  %-32s ' "$$ns"; \
		az provider register --namespace $$ns --wait -o none $(AZ_FLAGS) && az provider show --namespace $$ns --query registrationState -o tsv; \
	done
	$(call step,Initializing Terraform in terraform/azure)
	$(AZ_TF) init -upgrade=false

azure-plan: azure-init ## Show the Azure Terraform plan
	$(call step,Formatting and validating Terraform)
	$(AZ_TF) fmt -recursive
	$(AZ_TF) validate
	$(call step,Planning Azure changes)
	$(AZ_TF) plan

# ACR is created first so the image exists before the web app starts.
azure-deploy: azure-init ## Create/update everything: storage, ACR, import image from GHCR, App Service
	$(call step,[1/3] Creating resource group and ACR)
	$(AZ_TF) apply -auto-approve -target=azurerm_container_registry.app
	$(call step,[2/3] Importing $(GHCR_IMAGE):$(GHCR_TAG) into ACR)
	@$(MAKE) --no-print-directory azure-image
	$(call step,[3/3] Applying full Azure stack)
	$(AZ_TF) apply
	@$(MAKE) --no-print-directory azure-wait
	@$(MAKE) --no-print-directory azure-status
	$(call step,Azure deploy complete)
	@$(MAKE) --no-print-directory azure-url

azure-outputs: azure-login
	$(eval AZ_RG := $(shell terraform -chdir=terraform/azure output -raw resource_group_name 2>/dev/null))
	$(eval AZ_ACR := $(shell terraform -chdir=terraform/azure output -raw acr_name 2>/dev/null))
	$(eval AZ_APP := $(shell terraform -chdir=terraform/azure output -raw web_app_name 2>/dev/null))
	$(eval AZ_URL := $(shell terraform -chdir=terraform/azure output -raw app_url 2>/dev/null))
	@test -n "$(AZ_ACR)" || { echo "No ACR in Terraform state; run make azure-deploy first." >&2; exit 1; }

azure-image: azure-outputs ## Import the GHCR image (GHCR_TAG, default latest) into ACR as :latest
	$(call step,Importing $(GHCR_IMAGE):$(GHCR_TAG) into $(AZ_ACR) as nebraska-app:latest)
	az acr import --name $(AZ_ACR) --source $(GHCR_IMAGE):$(GHCR_TAG) --image nebraska-app:latest --force $(AZ_FLAGS)
	@echo "ACR digest: $$(az acr repository show --name $(AZ_ACR) --image nebraska-app:latest --query digest -o tsv)"

azure-image-local: azure-outputs scores ## Build the image from your working copy in ACR as :latest
	$(call step,Building ./app in $(AZ_ACR) (ACR Tasks))
	az acr build --registry $(AZ_ACR) --platform linux/amd64 --image nebraska-app:latest --image nebraska-app:sha-$(IMAGE_TAG) $(AZ_FLAGS) ./app

azure-push: azure-image azure-redeploy ## Import the latest GHCR image into ACR and restart the web app

azure-redeploy: azure-outputs ## Restart the web app so it re-pulls :latest, then wait until it serves
	@test -n "$(AZ_APP)" || { echo "No web app in Terraform state; run make azure-deploy first." >&2; exit 1; }
	$(call step,Restarting $(AZ_APP) in $(AZ_RG))
	az webapp restart --name $(AZ_APP) --resource-group $(AZ_RG) $(AZ_FLAGS)
	@$(MAKE) --no-print-directory azure-wait
	@$(MAKE) --no-print-directory azure-status

# The first request after a (re)start pulls the image and boots the container.
azure-wait: azure-outputs
	$(call step,Waiting for $(AZ_URL) to return 200 (checks every 10s; up to 10 min))
	@for i in $$(seq 1 60); do \
		code=$$(curl -s -o /dev/null -m 30 -w '%{http_code}' "$(AZ_URL)/"); \
		printf '  %s  HTTP %s\n' "$$(date +%H:%M:%S)" "$$code"; \
		[ "$$code" = 200 ] && exit 0; \
		sleep 10; \
	done; echo "App did not become healthy; see make azure-logs" >&2; exit 1

azure-status: azure-outputs ## Show the web app's state, image, and plan
	$(call step,Web app $(AZ_APP))
	@az webapp show --name $(AZ_APP) --resource-group $(AZ_RG) \
		--query "{state:state, host:defaultHostName, image:siteConfig.linuxFxVersion, httpsOnly:httpsOnly, lastModified:lastModifiedTimeUtc}" -o table

azure-url: azure-login ## Print the Azure app URL
	@url=$$(terraform -chdir=terraform/azure output -raw app_url 2>/dev/null); echo "App URL: $${url:-(not deployed; run make azure-deploy)}"

azure-logs: azure-outputs ## Stream the web app's container logs
	$(call step,Streaming $(AZ_APP) logs (Ctrl-C to stop))
	az webapp log tail --name $(AZ_APP) --resource-group $(AZ_RG)

azure-destroy: azure-init ## Destroy all Azure resources
	$(call step,Destroying Azure stack)
	$(AZ_TF) destroy

# ---------- GCP (Terraform + Cloud Run, local state) ----------

gcp-login: ## Ensure gcloud and Application Default Credentials are logged in; show the project
	$(call step,Checking gcloud login)
	@gcloud auth print-access-token >/dev/null 2>&1 || gcloud auth login
	@gcloud auth application-default print-access-token >/dev/null 2>&1 || gcloud auth application-default login
	@project=$$(gcloud config get-value project 2>/dev/null); \
		test -n "$$project" || { echo "No gcloud project set; run: gcloud config set project <project-id>" >&2; exit 1; }; \
		echo "Project: $$project"; echo "Account: $$(gcloud config get-value account 2>/dev/null)"; echo "Region:  $(GCP_REGION)"

gcp-init: gcp-login ## Enable required APIs and initialize Terraform (local state in terraform/gcp)
	$(call step,Enabling GCP APIs)
	gcloud services enable run.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com iam.googleapis.com $(GCP_FLAGS)
	$(call step,Initializing Terraform in terraform/gcp)
	$(GCP_TF) init -upgrade=false

gcp-plan: gcp-init ## Show the GCP Terraform plan
	$(call step,Formatting and validating Terraform)
	$(GCP_TF) fmt -recursive
	$(GCP_TF) validate
	$(call step,Planning GCP changes)
	$(GCP_TF) plan

# Artifact Registry is created first so the image exists before Cloud Run starts.
gcp-deploy: gcp-init ## Create/update everything: Firestore, Artifact Registry, copy image from GHCR, Cloud Run
	$(call step,[1/3] Creating Artifact Registry repository)
	$(GCP_TF) apply -auto-approve -target=google_artifact_registry_repository.app
	$(call step,[2/3] Copying $(GHCR_IMAGE):$(GHCR_TAG) into Artifact Registry)
	@$(MAKE) --no-print-directory gcp-image
	$(call step,[3/3] Applying full GCP stack)
	$(GCP_TF) apply
	@$(MAKE) --no-print-directory gcp-wait
	@$(MAKE) --no-print-directory gcp-status
	$(call step,GCP deploy complete)
	@$(MAKE) --no-print-directory gcp-url

gcp-outputs: gcp-login
	$(eval GCP_IMAGE := $(call GCP_OUT,image))
	$(eval GCP_SERVICE := $(call GCP_OUT,service_name))
	$(eval GCP_URL := $(call GCP_OUT,app_url))
	@test -n "$(GCP_IMAGE)" || { echo "No Artifact Registry repository in Terraform state; run make gcp-deploy first." >&2; exit 1; }
	@gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet >/dev/null 2>&1

gcp-image: gcp-outputs ## Copy the GHCR image (GHCR_TAG, default latest) into Artifact Registry as :latest
	$(call step,Pulling $(GHCR_IMAGE):$(GHCR_TAG))
	docker pull --platform linux/amd64 $(GHCR_IMAGE):$(GHCR_TAG)
	$(call step,Pushing to $(GCP_IMAGE))
	docker tag $(GHCR_IMAGE):$(GHCR_TAG) $(GCP_IMAGE)
	docker push $(GCP_IMAGE)

gcp-image-local: gcp-outputs scores ## Build the image from your working copy and push it to Artifact Registry as :latest
	$(call step,Building ./app for linux/amd64)
	docker build --platform linux/amd64 -t $(GCP_IMAGE) ./app
	docker push $(GCP_IMAGE)

gcp-push: gcp-image gcp-redeploy ## Copy the latest GHCR image to Artifact Registry and roll out Cloud Run

gcp-redeploy: gcp-outputs ## Deploy a new Cloud Run revision from :latest, then wait until it serves
	@test -n "$(GCP_SERVICE)" || { echo "No Cloud Run service in Terraform state; run make gcp-deploy first." >&2; exit 1; }
	$(call step,Deploying new revision of $(GCP_SERVICE))
	gcloud run deploy $(GCP_SERVICE) --image $(GCP_IMAGE) --region $(GCP_REGION) --quiet $(GCP_FLAGS)
	@$(MAKE) --no-print-directory gcp-wait
	@$(MAKE) --no-print-directory gcp-status

# Cloud Run scales to zero, so the first request may include a cold start.
gcp-wait: gcp-outputs
	$(call step,Waiting for $(GCP_URL) to return 200 (checks every 10s; up to 5 min))
	@for i in $$(seq 1 30); do \
		code=$$(curl -s -o /dev/null -m 30 -w '%{http_code}' "$(GCP_URL)/"); \
		printf '  %s  HTTP %s\n' "$$(date +%H:%M:%S)" "$$code"; \
		[ "$$code" = 200 ] && exit 0; \
		sleep 10; \
	done; echo "Service did not become healthy; see make gcp-logs" >&2; exit 1

gcp-status: gcp-outputs ## Show the Cloud Run service's ready revision, image, and URL
	$(call step,Cloud Run service $(GCP_SERVICE))
	@gcloud run services describe $(GCP_SERVICE) --region $(GCP_REGION) \
		--format='table(status.latestReadyRevisionName:label=REVISION, status.conditions[0].status:label=READY, spec.template.spec.containers[0].image:label=IMAGE, status.url:label=URL)'

gcp-url: gcp-login ## Print the GCP app URL
	@url=$$(terraform -chdir=terraform/gcp output -raw app_url 2>/dev/null); echo "App URL: $${url:-(not deployed; run make gcp-deploy)}"

gcp-logs: gcp-outputs ## Show recent Cloud Run logs
	$(call step,Recent logs for $(GCP_SERVICE))
	gcloud run services logs read $(GCP_SERVICE) --region $(GCP_REGION) --limit 100

gcp-destroy: gcp-init ## Destroy all GCP resources
	$(call step,Destroying GCP stack)
	$(GCP_TF) destroy

