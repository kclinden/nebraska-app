# AWS EKS Deployment

This is an additional deployment option, not a replacement for ECS. It uses
`terraform/aws-eks` with independent local state, a dedicated VPC, an EKS cluster,
two managed EC2 nodes, a public Application Load Balancer, and three managed
DynamoDB tables. Terraform seeds the
shared roster and schedule; the local DynamoDB pod and Helm seed job are disabled.
No AWS credentials are required to edit or run the mocked checks below.

## Before Deployment

- Install Terraform >= 1.7, AWS CLI v2, Docker, Helm, kubectl, Python 3, and make.
  Start Docker before deploying.
- The default deployment builds the current working copy and pushes it to a
  dedicated ECR repository; no GitHub merge or published image is required. If
  overriding `image_repository`, publish that image separately and ensure it
  supports the configurable DynamoDB table names. Prefer an immutable image tag.
- Use an isolated AWS account with permissions to manage EKS, EC2/VPC, IAM,
  DynamoDB, ECR, Elastic Load Balancing, Auto Scaling, and CloudWatch. The Terraform cluster creator gets cluster admin
  access; other IAM principals need separate EKS access entries.
- Set `AWS_PROFILE` and `AWS_REGION` consistently for every command. This stack
  defaults to `master` and `us-east-1`, like the existing ECS workflow.
- Choose a Kubernetes version currently supported in your AWS region. The
  default is 1.35; set `kubernetes_version` if needed.

Optionally create an ignored `terraform/aws-eks/terraform.tfvars` to override
the defaults:

```hcl
public_access_cidrs = ["0.0.0.0/0"]
image_tag           = "latest"
alb_ingress_cidrs    = ["0.0.0.0/0"]
```

The EKS API defaults to internet-wide IPv4 access (`0.0.0.0/0`). This makes the
endpoint reachable from anywhere but does not grant anonymous access: EKS IAM
authentication and Kubernetes authorization remain required. Restrict
`public_access_cidrs` to operator/VPN CIDRs to reduce exposure. Existing tfvars
or `TF_VAR_public_access_cidrs` settings override this default; update them if
they still contain an operator-only CIDR. The private API endpoint remains enabled
for nodes.
Do not reuse the Terraform state or table names from `terraform/aws`.

## Deploy and Access

With the tools installed, Docker running, and an AWS CLI profile configured,
deploy from scratch with one command:

```sh
make eks-deploy
```

`eks-deploy` checks tools, authenticates through AWS SSO if needed, initializes
Terraform, and prompts for approval before creating infrastructure. It then
authenticates Docker to the new ECR repository, refreshes scores, builds the
working copy for `linux/amd64`, and pushes the configured image tag. Finally it
updates/selects the `nebraska-eks` kubeconfig context, installs/upgrades the app
with Helm, restarts pods to pick up repeated tags, waits for rollout, and prints
the ALB URL. Image build/push failures stop before the Helm install. It streams generated Helm
values directly from Terraform output rather than writing a secret values file.
The API context can be renamed with `EKS_CONTEXT`; this does not rename the cluster.
The initial EKS deployment can take 15-25 minutes plus image build time. SSO and
Terraform approval may still require interaction. A pre-published custom
`image_repository` skips local build/push. Preview infrastructure separately with
`make eks-plan`; no manual ECR setup is needed for the default workflow.

Browse the URL printed by `make eks-url` or use it as the base URL for `/api/v1/`
requests. The default is a publicly reachable HTTP ALB hostname. This exposes an
intentionally vulnerable application, including its login and API routes, to
anyone on the internet. Use only synthetic data and disposable accounts; consider
restricting `alb_ingress_cidrs` to your tester/scanner IPs. This allowlist is
independent of `public_access_cidrs`, which controls the Kubernetes API only.

Terraform manages the ALB, listeners, instance target group, and attachment to
the managed node group's Auto Scaling group. Traffic flows from the ALB to the
app's NodePort (32080); the node security group allows that port only from the
ALB security group. Health checks use `/nebraska_football.png`. No Ingress or AWS
Load Balancer Controller is required. New nodes join the target group through
the Auto Scaling attachment. Allow time for target health checks after Helm
reports the pods ready.

For HTTPS, configure an issued ACM certificate in the cluster's region and a
matching DNS name:

```hcl
alb_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/REPLACE_ME"
alb_hostname        = "nebraska.example.com"
```

Create a DNS alias or CNAME for that hostname pointing to the Terraform
`alb_dns_name` output. DNS and certificate issuance are not created by this
stack. HTTPS enables Secure session cookies and redirects port 80 to 443.
Do not transmit non-disposable credentials over the default HTTP listener.
ALB-to-node traffic stays HTTP inside the VPC.

To keep the app private instead, set `public_alb_enabled = false` and redeploy.
This removes the ALB and uses ClusterIP with `make eks-open` at
http://localhost:8082. Port-forwarding also remains available in public mode,
but Secure cookies in HTTPS mode require HTTPS for browser login.

Retrieve the generated bootstrap passwords locally; do not share the output:

```sh
terraform -chdir=terraform/aws-eks output -json bootstrap_passwords
```

Usernames are `admin` and `viewer`. Passwords and signing keys are stored in
sensitive Terraform state, Kubernetes Secrets, and Helm release history. Protect
all three. Existing database account passwords are not reset by redeployment.

## Identity and Data

The EKS Pod Identity agent gives the `nebraska-app` service account a dedicated
IAM role. The role permits only GetItem, PutItem, DeleteItem, and Scan on this
stack's three DynamoDB tables. No static AWS keys or local DynamoDB endpoint are
injected. EC2 metadata requires IMDSv2 and a hop limit of one to prevent ordinary
app pods from using node credentials. Current boto3 images support Pod Identity.

Tables are named `<cluster_name>-players`, `<cluster_name>-schedule`, and
`<cluster_name>-users`, with encryption and point-in-time recovery enabled.
They survive pod/node restarts but are deleted by `eks-destroy`. Use a distinct
`cluster_name` and state for each independent EKS installation. The namespace is
set by Terraform's `namespace` variable and must match the Pod Identity association.

Nodes run in public subnets with public IPs for outbound image pulls and AWS
access, without SSH access or direct public NodePort access. The ALB is the public
app entry point. This lab layout avoids NAT
gateway cost; it is not a production networking design. GHCR and Docker Hub must
be reachable. Choose an x86-64-compatible node type (default `t3.medium`).

## Update and Teardown

```sh
make eks-status
make eks-url
make eks-logs
make eks-deploy     # rebuild the working copy, push to ECR, and deploy
make eks-push       # re-pull the configured published tag and wait for rollout
make eks-destroy    # uninstall app, then approve destroying EKS infrastructure/data
```

For a new immutable image tag, change `image_tag` in the ignored tfvars file and
run `make eks-deploy`. Use `make eks-image-local` to build/push to ECR without
deploying, followed by `make eks-push` to roll it out. `eks-image-local`, `eks-push`,
and `eks-app` use values from the last applied Terraform state. With a custom
image repository, publish the desired tag there before deploying. Teardown requires the same state and a principal
with cluster access. If the cluster exists but the app install failed, the Helm
uninstall tolerates a missing release. For a partial infrastructure failure with
no cluster access, run `terraform -chdir=terraform/aws-eks destroy` directly.

EKS control-plane fees, the ALB and capacity units, two EC2 instances, EBS,
public IPv4 addresses, CloudWatch,
ECR, and DynamoDB/PITR incur charges while deployed. There is no scale-to-zero or
automatic teardown. `make aws-destroy` only destroys ECS, not EKS.

## Credential-Free Checks

```sh
terraform -chdir=terraform/aws-eks init -backend=false
terraform -chdir=terraform/aws-eks fmt -check
terraform -chdir=terraform/aws-eks validate
terraform -chdir=terraform/aws-eks test
helm lint charts/nebraska-app --set seed.enabled=false
helm template nebraska-app charts/nebraska-app --set seed.enabled=false \
  --set dynamodb.enabled=false,dynamodb.useStaticCredentials=false,serviceAccount.create=true
```

Terraform tests use mocked providers and do not provision AWS resources. Actual
planning, regional availability, IAM access, image pulls, and end-to-end Pod
Identity require an authenticated deployment to verify.