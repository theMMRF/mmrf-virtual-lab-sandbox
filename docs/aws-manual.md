# Manual EKS deployment with a localhost port-forward

For the automated HTTPS deployment, start with [the AWS launcher](aws-deployment.md).
This lower-level alternative intentionally leaves `enable_https=false` and does
not create a browser-accessible CloudFront distribution.

## Full EKS deployment runbook

The operator runs every AWS command in this guide. Preparation used local Docker,
Helm rendering and Terraform mock tests; **no live AWS deployment has been tested**.
Do not interpret an offline pass as proof of account permissions, capacity or
network-policy enforcement. Existing automated preview-image builds are separate.

## Access model: no domain or certificate required for the first test

The chart exposes **ClusterIP services only**. There is no public web endpoint,
load balancer, Ingress, Route 53 record or application TLS certificate. Authenticate
with your own AWS CLI role and use `kubectl port-forward` bound to `127.0.0.1`.
Your browser visits `http://localhost:3081`, while the application runs in AWS.
Port 3081 avoids the local Compose sandbox already using 3080.

The laptop-to-EKS API connection uses TLS and AWS authentication; HTTP here is
limited to the laptop's loopback interface. Do not use `--address 0.0.0.0` or expose
the shared synthetic identity gateway publicly. See [Kubernetes port forwarding](https://kubernetes.io/docs/tasks/access-application-cluster/port-forward-access-application-cluster/)
and [EKS kubeconfig authentication](https://docs.aws.amazon.com/eks/latest/userguide/create-kubeconfig.html).

For a shared browser-only hackathon URL, add and test an authenticated HTTPS
entry point separately. A custom domain/certificate is not a prerequisite:
[CloudFront can serve HTTPS on its default AWS-owned hostname](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-https-alternate-domain-names.html).
Configuring that distribution, access control and correct application routing is
still additional work and is not included here. An approved private access
service is another follow-up option. Public HTTP exposes application traffic to tampering,
and some browser capabilities require a secure context. Loopback HTTP receives
special treatment that a public HTTP IP address does not; see [secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts).

## 1. Prepare the dedicated account and local tools

An existing **empty dedicated sandbox account** is suitable; a newly created
account is not required. Never use a development/production account. The operator
needs permission to create VPC, IAM, EKS, EC2 and ECR resources, plus an existing
IAM role in that account for Kubernetes administration. This guide assumes the
selected AWS profile already authenticates as that role. IAM Identity Center/SSO
is fine; use the full IAM role ARN, including any role path, not an STS
`assumed-role` session ARN. Terraform grants that role cluster administration;
application pods receive no AWS credentials or Kubernetes service-account token.
The operator also needs the IAM actions used by Terraform, including
`iam:CreateRole`, `iam:AttachRolePolicy` and `iam:PassRole`, and the corresponding
cleanup permissions for the resources it creates. EKS can also require
`iam:CreateServiceLinkedRole` when its service-linked role is absent. These are
examples of required permissions, not a complete IAM policy; account guardrails
can still prevent provisioning.

Requirements: Terraform >=1.9 and <2, AWS CLI v2, Docker with Buildx and Compose
>=2.17, Helm 3 or 4, Python >=3.9, Git, and kubectl compatible with EKS 1.35 (1.34–1.36).
Node/npm are needed only for the optional headless UI checks. Allow at least
12 GiB Docker memory and 30 GiB free local disk for image preparation. Check account
EKS/EC2 quotas, regional m6i.xlarge availability and your event budget yourself.

The defaults create one EKS 1.35 control plane, one m6i.xlarge worker (4 vCPU,
16 GiB RAM, 80 GB root disk), a fresh VPC/two public subnets, IAM roles and six ECR
repositories. There is no NAT gateway or load balancer. EKS, EC2, disk, public IPv4,
registry storage and data transfer can incur charges until removed. EKS 1.35
standard support ends March 27, 2027; check the [current EKS calendar](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html)
before a later event. To use a newer version that AWS lists in standard support,
add `"kubernetes_version": "YOUR_SUPPORTED_VERSION"` to the JSON object in step 3,
replacing the placeholder, before planning. Use a compatible kubectl version
(within one minor version of that selection). Terraform retains the `1.35`
default and `STANDARD` support policy; it does not automatically select a version
or opt into extended support.

Use a terminal dedicated to this test. Replace the four example values below:

```sh
export AWS_PROFILE='YOUR_SANDBOX_ONE_PROFILE'
export AWS_REGION='us-east-1'
export SANDBOX_ACCOUNT_ID='YOUR_12_DIGIT_SANDBOX_ONE_ACCOUNT_ID'
export SANDBOX_OPERATOR_ROLE_ARN='arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_EXISTING_ROLE'
export SANDBOX_OPERATOR_CIDR='YOUR_PUBLIC_IPV4/32'
aws sso login --profile "$AWS_PROFILE"  # Only if your profile uses SSO.
aws sts get-caller-identity
```

**Stop if the Account is not Sandbox One, or the principal is not the intended
operator role.** The public IPv4 must be your actual internet/VPN egress address,
not the laptop's private Wi-Fi address. Terraform restricts EKS API access to
these CIDRs (/24 or narrower) and rejects an account other than the specified ID.
Credentials stay in your own approved CLI configuration, never in this repository.

## 2. Prepare images before starting chargeable infrastructure

Use the implementation branch until PR #1 is merged; the default branch currently
contains only the initial repository scaffold. An existing checkout already on
`codex/synthetic-sandbox` can be reused instead of cloning another copy.

```sh
git clone --branch codex/synthetic-sandbox https://github.com/theMMRF/mmrf-virtual-lab-sandbox.git
cd mmrf-virtual-lab-sandbox
python3 scripts/fetch_sources.py
python3 synthetic/generate.py
```

The fetcher refuses to overwrite a different source commit or uncommitted source
work. If updating an existing `.sources` checkout after a pin change, preserve
any work, then explicitly fetch/check out the commit in `sources.json`, or use a
fresh sandbox clone. Do not reset another development checkout.

All six application images must be **linux/amd64**, matching the EKS worker and
public ProteinPaint image. Apple Silicon builds use emulation and may take time.
For builds on the same laptop as the local sandbox, stop only its Compose stack
to leave memory for compilation; do not delete its volume. Build services one at
a time. This replaces the local `:local` image tags with amd64 versions, which
Docker Desktop can also run through emulation.

```sh
docker compose stop
python3 - <<'PYBUILD'
import os, subprocess
for service in ['seed', 'guppy', 'analysis', 'proteinpaint', 'identity', 'frontend']:
    subprocess.run(['docker', 'compose', 'build', service], check=True,
                   env={**os.environ, 'DOCKER_DEFAULT_PLATFORM': 'linux/amd64'})
PYBUILD
```

Proceed only if **all six builds succeeded**. If you want the local sandbox back
while testing AWS, restart it with `docker compose up -d --wait`. No AWS resources
have been created yet by the commands in this section.

## 3. Review and apply Terraform yourself

From the sandbox repository root, create the ignored variable file. Keep the same
repository directory and its local state until teardown is complete. State,
plans, kubeconfig and generated overrides are ignored; never publish them.

```sh
python3 - <<'PY'
import json, os
from pathlib import Path
Path('terraform/sandbox.auto.tfvars.json').write_text(json.dumps({
    'sandbox_account_id': os.environ['SANDBOX_ACCOUNT_ID'],
    'region': os.environ['AWS_REGION'],
    'operator_role_arn': os.environ['SANDBOX_OPERATOR_ROLE_ARN'],
    'operator_cidrs': [os.environ['SANDBOX_OPERATOR_CIDR']],
}, indent=2) + '\n')
PY
cd terraform
terraform init -backend=false
terraform fmt -check
terraform validate
terraform test
terraform plan -out=sandbox.tfplan
```

The first four Terraform commands validate locally (provider download needs the
internet); the **real plan and apply contact AWS**. Review the account, region,
resource list and costs before applying. This creates fresh resources and does
not import private GitOps configuration or existing clusters/buckets/state.

```sh
terraform apply sandbox.tfplan
mkdir -p ../generated
terraform output -json image_repositories > ../generated/ecr-repositories.json
terraform output -raw cluster_name > ../generated/aws-cluster-name
cd ..
```

If apply partly fails, retain the state and inspect the failure before retrying
or following teardown. Do not create another state directory to bypass it.

## 4. Publish the six synthetic application images

The registry is dedicated to this Terraform deployment. Authenticate Docker using
your operator CLI profile. Use a new tag for every build: ECR tags are immutable.

```sh
export SANDBOX_IMAGE_TAG="synthetic-$(date -u +%Y%m%dT%H%M%SZ)"
export SANDBOX_REGISTRY="${SANDBOX_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$SANDBOX_REGISTRY"
```

The following Python snippet runs local Docker tag/push commands and creates Helm
overrides from Terraform's exact repository URLs. It checks all registry targets
and local architectures before pushing anything. It does not contain credentials.

```sh
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path
repos = json.loads(Path('generated/ecr-repositories.json').read_text())
services = {'frontend', 'guppy', 'analysis', 'proteinpaint', 'identity', 'seed'}
assert set(repos) == services, 'Unexpected repository set'
registry, tag = os.environ['SANDBOX_REGISTRY'], os.environ['SANDBOX_IMAGE_TAG']
for service, repo in repos.items():
    assert repo.startswith(registry + '/'), f'Wrong registry: {repo}'
    arch = subprocess.check_output(['docker', 'image', 'inspect',
        f'mmrf-sandbox/{service}:local', '--format', '{{.Architecture}}'], text=True).strip()
    assert arch == 'amd64', f'{service}: rebuild for linux/amd64 (found {arch})'
images = {service: f'{repo}:{tag}' for service, repo in repos.items()}
for service, target in images.items():
    subprocess.run(['docker', 'tag', f'mmrf-sandbox/{service}:local', target], check=True)
    subprocess.run(['docker', 'push', target], check=True)
Path('generated/aws-values.json').write_text(json.dumps({'images': images}, indent=2) + '\n')
PY
```

JSON is valid Helm values input. The public Elasticsearch digest and wait-helper
image retain their chart defaults. If account egress restricts those registries,
mirror those two images to an approved registry and override `images.elasticsearch`
and `waitImage` too. Keep the source pins and immutable image tags with test notes;
record resolved digests for a reusable hackathon release. Do not substitute private
production images or ppmmrf images.

## 5. Install and test through your local tunnel

These commands assume the selected AWS profile already uses the role granted
access in step 1. `--kubeconfig` keeps this test out of your normal kubeconfig.
If instead authenticating with a different principal authorized to assume that
role, add `--role-arn "$SANDBOX_OPERATOR_ROLE_ARN"` to `update-kubeconfig`.
Do not force an SSO role to assume itself.

```sh
aws eks update-kubeconfig --region "$AWS_REGION" \
  --name "$(cat generated/aws-cluster-name)" \
  --kubeconfig generated/aws-kubeconfig
kubectl --kubeconfig generated/aws-kubeconfig get nodes
helm lint helm
helm upgrade --install sandbox helm --namespace mmrf-synthetic --create-namespace \
  --kubeconfig generated/aws-kubeconfig -f generated/aws-values.json \
  --wait --timeout 15m
kubectl --kubeconfig generated/aws-kubeconfig -n mmrf-synthetic get pods
kubectl --kubeconfig generated/aws-kubeconfig -n mmrf-synthetic \
  port-forward service/identity 3081:8080 --address 127.0.0.1
```

Keep that terminal running. Open **http://localhost:3081**. In a second terminal
from the same repository root, run:

```sh
python3 scripts/smoke.py --origin http://127.0.0.1:3081
# Optional automated screenshots; requires Node/npm locally:
npm ci
npx playwright install chromium
SANDBOX_ORIGIN=http://127.0.0.1:3081 npm run test:ui
```

Confirm the synthetic banner, 1,000 cases, a female-only cohort of 500, survival
plots, OncoMatrix, MYC/c-Myc search, repository metadata, bulk UMAP, single-cell
Meta analysis and age-decade counts. See [verification.md](verification.md).
Tracking requests and the tracking-consent pop-up should be absent even with a
previously accepted consent preference. Authentication is a disposable shared
synthetic identity; this does not test production login or per-user authorization.

Also inspect services: `kubectl --kubeconfig generated/aws-kubeconfig -n
mmrf-synthetic get services` must show ClusterIP only. The operator must verify
network-policy enforcement in the live EKS cluster, including denied external
application-pod egress. Terraform enables VPC CNI network policy in **standard**
startup mode: pods can briefly have unrestricted access before policy attachment.
This is an acknowledged limit, not a claim of continuous network isolation.
Strict mode requires a tested CoreDNS policy/bootstrap sequence. See [AWS network
policy configuration](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html).

If startup fails, inspect `kubectl --kubeconfig generated/aws-kubeconfig -n
mmrf-synthetic get events --sort-by=.lastTimestamp` and the affected pod's
`describe`/`logs`, then retry after fixing the cause. A Helm timeout does not
tear down infrastructure. Wrong-account errors, access denied, unreachable API
(changed VPN/IP), image architecture/pull failures and node capacity must be
resolved by the operator before accepting the deployment.

## 6. Tear down completely

**Closing the browser, stopping port-forward or uninstalling Helm does not stop
EKS/EC2 billing.** Use the same AWS profile, region, Terraform directory and state
as creation. Confirm `aws sts get-caller-identity` is still Sandbox One.

1. Stop port-forward with Ctrl-C. Remove the application while the cluster is up:

   ```sh
   helm uninstall sandbox -n mmrf-synthetic --kubeconfig generated/aws-kubeconfig
   kubectl --kubeconfig generated/aws-kubeconfig delete namespace mmrf-synthetic
   ```

2. In the **Sandbox One ECR console, in the chosen region**, open only the six
   repositories recorded in `generated/ecr-repositories.json`. With the default
   name these are `mmrf-synthetic/frontend`, `guppy`, `analysis`, `proteinpaint`,
   `identity`, and `seed` (all six have the `mmrf-synthetic/` prefix). In each,
   select the test images, including untagged manifests/attestations, and choose
   **Delete**. Delete a parent image index before any child manifests it references
   if ECR reports dependencies, then refresh and remove the remaining images.
   Confirm each repository is empty. Do not delete other repositories or images.
   Terraform intentionally has `force_delete=false`, so it refuses to destroy a
   nonempty repository. See [ECR image deletion](https://docs.aws.amazon.com/AmazonECR/latest/userguide/delete_image.html).
   If apply failed before exporting repository URLs, identify any created ECR
   resources with `terraform state list` / `terraform state show` in the original
   Terraform directory. Skip Helm removal if the release was never installed.

3. Review the destroy plan, then apply exactly that plan:

   ```sh
   cd terraform
   terraform plan -destroy -out=destroy.tfplan
   terraform apply destroy.tfplan
   terraform state list
   cd ..
   ```

4. Require successful completion and an empty Terraform resource list. In the
   Sandbox One console verify the test EKS cluster, managed node/EC2 instance,
   associated root volume, fresh VPC/networking and six ECR repositories are gone.
   Check billing/Cost Explorer once usage has reported. Retain state until cleanup
   is confirmed; if destroy fails, fix the cause and rerun a fresh destroy plan.
   The chart creates no persistent volumes, load balancers, DNS records or certs.

Search storage uses disposable `emptyDir`; a seed watcher restores fixtures after
Elasticsearch storage loss. This is intentionally not a durable data commons.
For a new seed or case count, rebuild all fixture-bearing images and use a fresh
application namespace rather than mixing datasets. Local Compose data is separate
from AWS and is not affected by this teardown.
