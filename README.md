# Nebraska App

Husker football roster and schedule app (Flask), packaged as a container and deployable locally, to AWS, or to Azure.

## Repository Layout

- `app/` application source, `Dockerfile`, and related assets; `storage.py` selects DynamoDB or Azure Table Storage via `STORAGE_BACKEND`
- `data/` roster and schedule YAML, shared by local seeding and every cloud stack
- `scripts/` score fetcher and DynamoDB Local seeder
- `terraform/aws/` AWS stack (VPC, ECS Fargate, ALB, ECR, DynamoDB, IAM)
- `terraform/azure/` Azure stack (Container Apps, ACR, Table Storage, managed identity)
- `docker-compose.yml` local test stack
- `Makefile` shortcuts for local, AWS, and Azure workflows (run `make help`)

## Make Targets

| Target | Description |
| --- | --- |
| `make local-up` | Fetch scores, build, and start the local stack at http://localhost:8080 |
| `make local-down` | Stop the local stack |
| `make local-restart` | Rebuild and restart with fresh data |
| `make local-logs` | Tail container logs |
| `make local-reseed` | Re-run the DynamoDB Local seeder |
| `make scores` | Refresh `app/scores.json` from ESPN |
| `make aws-login` | Ensure an AWS SSO session is active (runs `aws sso login` if expired) |
| `make aws-plan` | `fmt`, `validate`, and `plan` |
| `make aws-deploy` | Create/update the full stack, copy the GHCR image to ECR, and roll out ECS |
| `make aws-push` | Copy the latest GHCR image to ECR and roll out ECS |
| `make aws-image-local` | Build from your working copy and push to ECR (then `make aws-redeploy`) |
| `make aws-redeploy` | Restart the ECS service on the current `:latest` image |
| `make aws-url` | Print the app URL |
| `make aws-logs` | Tail the app's CloudWatch logs |
| `make aws-destroy` | Destroy all AWS resources |
| `make azure-login` | Ensure the Azure CLI has a valid login (runs `az login` if not) |
| `make azure-plan` | Register providers, `fmt`, `validate`, and `plan` |
| `make azure-deploy` | Create/update the full stack, import the GHCR image into ACR, and deploy the Container App |
| `make azure-push` | Import the latest GHCR image into ACR and roll out a new revision |
| `make azure-image-local` | Build from your working copy in ACR (then `make azure-redeploy`) |
| `make azure-redeploy` | Create a new Container App revision so it re-pulls `:latest` |
| `make azure-url` | Print the app URL |
| `make azure-logs` | Stream the Container App's console logs |
| `make azure-destroy` | Destroy all Azure resources |

## Local Testing (Docker)

Requires Docker and Python 3. No AWS account or credentials needed.

```bash
make local-up     # http://localhost:8080
make local-down
```

`docker-compose.yml` runs three services:

- `dynamodb-local` - [Amazon DynamoDB Local](https://hub.docker.com/r/amazon/dynamodb-local), in-memory, exposed on `localhost:8000`.
- `seed` - runs `scripts/seed_local_dynamodb.py` to create the `NebraskaPlayers` and `NebraskaSchedule2026` tables and load `data/roster.yaml` and `data/schedule.yaml`.
- `app` - the app image, started after seeding succeeds.

The app needs no code changes to run locally: boto3 honors `AWS_ENDPOINT_URL_DYNAMODB`, which compose points at `dynamodb-local`. Credentials are dummy values. Data is reset every time the stack stops; roster add/remove changes are not persisted.

To inspect the local tables from your machine:

```bash
AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local \
  aws dynamodb scan --table-name NebraskaSchedule2026 --endpoint-url http://localhost:8000 --region us-east-1
```

## Scores and Game Stats

`scripts/update_scores.py` pulls final scores, team stats, and Husker leaders for completed games from ESPN's public API and writes `app/scores.json` (gitignored, generated at build time). Set `SEASON=2025` to fetch a different season. Without the file the app still runs; scores just show `-`. `make scores` keeps the existing file if ESPN is unreachable.

## AWS Deploy

Requires the AWS CLI with an SSO profile, Terraform >= 1.6, and Docker. All `aws-*` targets first run `make aws-login`, which opens `aws sso login` if the session has expired. The profile defaults to `master`; override with `AWS_PROFILE=member`. Region defaults to `us-east-1`; override with `AWS_REGION=us-west-2`.

```bash
make aws-plan
make aws-deploy      # prints the load balancer URL when done
make aws-destroy     # tear everything down
```

The stack deploys into a blank account/region; it creates its own networking and needs nothing pre-existing.

`make aws-deploy` runs in this order so the service never starts without an image:

1. Create the ECR repository (targeted apply).
2. Pull `ghcr.io/kclinden/nebraska-app:latest` (published by the Docker Build workflow) and push it to ECR as `:latest`. Use `GHCR_TAG=sha-<full-commit>` to deploy a specific build.
3. Apply the rest of the stack.
4. Force a new ECS deployment and wait for it to become stable.

To roll out a newer GHCR build later (e.g. after the weekly score refresh), run `make aws-push`. To test uncommitted changes, run `make aws-image-local aws-redeploy`.

### State

Terraform uses **local state** in `terraform/aws/terraform.tfstate` (gitignored). There is no remote backend; keep the file on the machine that deploys, or run `make aws-destroy` before deleting it.

### Architecture

- **Network** (`network.tf`): VPC (`10.20.0.0/16` by default, `vpc_cidr`), internet gateway, and two public `/24` subnets in the first two AZs with a default route to the IGW. No NAT gateway.
- **Compute** (`ecs.tf`): ECS Fargate service `husker-app` (1 task, 0.25 vCPU / 512 MB) running `nebraska-app:latest` from ECR, with deployment circuit breaker and rollback. Tasks get a public IP for outbound access; their security group only admits the ALB on port 5000.
- **Load balancer**: internet-facing ALB on port 80 across both public subnets.
- **Data** (`db.tf`): DynamoDB tables `NebraskaPlayers` and `NebraskaSchedule2026`, seeded from `data/*.yaml`.
- **IAM** (`iam.tf`): task execution role (pull image, write logs), task role (DynamoDB read/write + `S3OverlyPermissivePolicy`).
- **Logs**: CloudWatch `/ecs/husker-app` (30-day retention).

## Azure Deploy

Requires the Azure CLI and Terraform >= 1.6 (no local Docker needed). All `azure-*` targets first run `make azure-login`, which opens `az login` if there's no valid token. The active `az account` subscription is used (`az account set --subscription ...` to change it). You need Owner (or Contributor + User Access Administrator) because the stack creates role assignments.

```bash
make azure-plan
make azure-deploy    # prints the https:// app URL when done
make azure-destroy   # tear everything down
```

`make azure-deploy`:

1. Registers the needed resource providers (`Microsoft.App`, `ContainerRegistry`, `ManagedIdentity`, `OperationalInsights`, `Storage`).
2. Creates the resource group and ACR (targeted apply).
3. Imports `ghcr.io/kclinden/nebraska-app:latest` into ACR with `az acr import` (`GHCR_TAG=...` for a specific build).
4. Applies the rest of the stack.

To roll out a newer GHCR build later, run `make azure-push`. Container Apps only re-pull `:latest` on a new revision, so `azure-redeploy` sets a unique revision suffix.

State is local in `terraform/azure/terraform.tfstate` (gitignored). Region defaults to `centralus` (`TF_VAR_location=eastus` to override).

### Architecture

- **Compute** (`containerapp.tf`): Container Apps environment + app `husker-app` (1 replica, 0.25 vCPU / 0.5 GiB) with external HTTPS ingress to port 5000. Image pulled from ACR (Basic, admin user disabled) using the app's managed identity.
- **Data** (`storage.tf`): Storage account with tables `NebraskaPlayers` (PartitionKey = jersey, RowKey = name) and `NebraskaSchedule2026` (PartitionKey = `2026`, RowKey = game id), seeded from `data/*.yaml`. The app uses `STORAGE_BACKEND=azure_table` and authenticates with the managed identity (no keys).
- **Identity** (`iam.tf`): user-assigned managed identity with `AcrPull` on the registry, `Storage Table Data Contributor` on the storage account, and an intentionally overly permissive `Storage Blob Data Owner` at subscription scope (mirrors the AWS `S3OverlyPermissivePolicy`).
- **Logs**: Log Analytics workspace `log-husker-app` (30-day retention).

## Container Image (GitHub Actions)

`.github/workflows/docker-build.yml` refreshes scores, builds the image from `app/`, and pushes it to `ghcr.io/<owner>/<repo>`. It has no cloud dependency:

- on pushes to `main` touching `app/` or `scripts/` (tags `latest` and `sha-<commit>`)
- every Sunday 12:00 UTC during the season (Aug-Jan) to pick up the weekend's game (adds a `YYYYMMDD` tag)
- manually via **Run workflow**
- on pull requests: builds without pushing and runs a container smoke test

GitHub Actions does not deploy to any cloud; `make aws-push` / `make azure-push` copy the published image into ECR / ACR.

## Notes

- Terraform state files are intentionally ignored by git.
- CI validates `terraform/aws` and `terraform/azure` formatting and configuration on push and pull requests.
