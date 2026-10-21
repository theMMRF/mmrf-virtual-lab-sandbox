# Operator-controlled AWS deployment

No direct AWS access or deployment test was performed during preparation.
Existing automated preview-image builds may run separately. The Terraform validation below is
offline apart from downloading providers; mock tests make no AWS API requests.
The real account test is a separate operator acceptance gate.

## Before provisioning

Use a **new dedicated sandbox account**, not the existing development/production
accounts. The operator needs permission to create VPC, IAM, EKS, EC2 and ECR
resources and an existing IAM role in that account for Kubernetes administration.
Check EKS availability, EC2 m6i.xlarge capacity, vCPU/IP quotas and event budget.
This creates a chargeable EKS control plane and one continuously running node.

Requirements: Terraform 1.9+, AWS CLI, Docker Buildx, Helm 3+, kubectl, Git and
Python 3.9+. Docker Compose 2.17+ is used to build the local images. Configure AWS
credentials yourself using your organization's approved method; never put them in
this repository, containers, an image, or a shared challenge submission.

```sh
cd terraform
terraform init -backend=false
terraform fmt -check
terraform validate
terraform test
```

Create an ignored `sandbox.auto.tfvars` (add that filename to your local exclude
if storing it elsewhere) containing your dedicated account ID, region, existing
operator IAM role ARN and your public egress IPv4 CIDR, for example `/32`. No
secrets belong in this file. The provider rejects a different account; the role
must belong to the same account; API CIDRs must be /24 or narrower.

The configuration intentionally creates fresh resources without importing private
GitOps files or accessing existing clusters/buckets/state. Default Terraform state
is local; keep it private and use an approved encrypted remote backend if sharing
administration. Never commit plans or state.

```sh
terraform plan -out=sandbox.tfplan
# Operator reviews the account, region, complete plan and costs, then:
terraform apply sandbox.tfplan
terraform output -json image_repositories > ../generated/ecr-repositories.json
aws eks update-kubeconfig --region YOUR_REGION --name mmrf-synthetic \
  --kubeconfig ../generated/aws-kubeconfig --role-arn YOUR_OPERATOR_ROLE_ARN
cd ..
```

## Build and publish synthetic images

Run `python3 scripts/fetch_sources.py` and `python3 synthetic/generate.py` first.
All six application images must target **linux/amd64**, matching the EKS worker
and public ProteinPaint base. On Apple Silicon use Buildx/Compose emulation; allow
extra build time. Do not publish the host's native arm64 images to this cluster.

```sh
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build
```

Authenticate Docker to the ECR registry yourself using AWS CLI. Read each service's
repository URL from `generated/ecr-repositories.json`. Tag and push each of
`frontend`, `guppy`, `analysis`, `proteinpaint`, `identity` and `seed`:

```sh
# Repeat with each service and its corresponding ECR URL.
docker tag mmrf-sandbox/frontend:local YOUR_ECR_FRONTEND_URL:UNIQUE_BUILD_TAG
docker push YOUR_ECR_FRONTEND_URL:UNIQUE_BUILD_TAG
```

Use a new immutable tag per build. Create an ignored
`generated/aws-values.yaml` with all six `images` overrides pointing to those
published URLs/tags. Leave the public Elasticsearch image pinned as supplied.
If registry access is restricted, override `waitImage` and the Elasticsearch
image with operator-approved mirrors; preload these images too for offline kind.
For reproducibility record the resolved image digests and preferably deploy them
with `URL@sha256:...`. Never use real deployment images or private ppmmrf images.

```sh
helm lint helm
helm upgrade --install sandbox helm --namespace mmrf-synthetic --create-namespace \
  --kubeconfig generated/aws-kubeconfig -f generated/aws-values.yaml \
  --wait --timeout 10m
kubectl --kubeconfig generated/aws-kubeconfig -n mmrf-synthetic get pods
kubectl --kubeconfig generated/aws-kubeconfig -n mmrf-synthetic \
  port-forward service/identity 3080:8080 --address 127.0.0.1
```

Open http://localhost:3080 in another terminal/browser. Run `python3
scripts/smoke.py` and `npm ci && npx playwright install chromium && npm run test:ui`.
Confirm the synthetic banner, 1,000 cases, a female cohort of 500, OncoMatrix,
repository files and the remaining tool acceptance checks. Save screenshots.
The default chart exposes **ClusterIP only**, with no public frontend or ingress.
Each participant can port-forward using their operator-approved cluster access.
The synthetic identity is deliberately shared; this is not production auth.

The chart installs a namespace-scoped NetworkPolicy. EKS VPC CNI network policy
support is enabled by Terraform; the operator must verify enforcement in the
actual cluster, including denied external egress from application pods. The local
kind test did not demonstrate enforcement. VPC CNI uses standard startup enforcement: new pods can briefly have unrestricted
network access while policies attach. This synthetic-only account contains no
patient data or real credentials. Strict startup enforcement requires a tested
CoreDNS policy/bootstrap sequence before enabling it; it is not claimed here.
See the [AWS network-policy documentation](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html).
The frontend should
still be unable to route sandbox requests to production services.

## Reset and teardown

Search data uses disposable `emptyDir` storage. A seed watcher restores generated
fixtures after Elasticsearch storage loss; this is intentionally not a durable
data commons. For a new seed or case count, rebuild all fixture-bearing images
and reinstall the release in a fresh namespace rather than mixing datasets.

```sh
helm uninstall sandbox -n mmrf-synthetic --kubeconfig generated/aws-kubeconfig
kubectl --kubeconfig generated/aws-kubeconfig delete namespace mmrf-synthetic
```

The operator then deletes the **sandbox ECR images** after confirming their
repository URLs. Terraform deliberately refuses to destroy nonempty ECR
repositories. Run and review `terraform plan -destroy` then `terraform destroy`
in `terraform/`. Confirm cluster, node, networking and registries are gone and
check account billing. Do not run teardown against another deployment's state.
