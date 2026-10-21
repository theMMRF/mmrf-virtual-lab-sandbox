# EKS sandbox with an HTTPS URL

The operator runs every AWS command. This launcher has been tested offline and
against local containers; **it has not been deployed to AWS by this preparation
workflow**. Keep the dedicated checkout and its state until teardown succeeds.

## What it deploys

Browser **HTTPS → CloudFront → private ALB → password-protected entry → Virtual Lab**.
CloudFront supplies its AWS-owned `https://….cloudfront.net` hostname and certificate.
An ALB's default `*.elb.amazonaws.com` hostname cannot use a public certificate
for that AWS-owned name. No domain, Route 53 zone or ACM validation is needed.

CloudFront uses a [VPC origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html).
The ALB is internal, in two private subnets; origin traffic stays inside the VPC.
TLS terminates at CloudFront: ALB-to-pod and private-origin traffic use HTTP.
This is **not end-to-end TLS** and is for fabricated, disposable data only.
The browser must use HTTPS; public HTTP is rejected. API responses, credentials
and cohort-specific results are not cached. Only a minimal `/_status` health
response is public; the application requires the generated team login.

Terraform creates a new isolated VPC (default `10.86.0.0/16`), two public worker
subnets, two private ALB subnets, EKS 1.35, one amd64 m6i.xlarge worker (4 vCPU,
16 GiB, 80 GiB root disk), six ECR repositories, an ALB and CloudFront. There is
no NAT gateway, autoscaler, AWS Load Balancer Controller, shared account storage
or production identity. Terraform registers the node group's ASG with the ALB;
a fixed NodePort serves only the password-protected entry. Backing services stay
ClusterIP. Worker ingress for that port is limited to the ALB security group.

The existing LZA/Control Tower network is neither imported nor modified. The
launcher checks for CIDR overlap, but does not inspect or override organization
policies. The existing standard-mode CNI policy startup window is still a known
limitation; it is not a claim of continuous pod isolation during startup.

## Time and cost

Allow roughly **1–2 hours with working permissions and images ready**. First
image builds/downloads on Apple Silicon and AWS provisioning/CloudFront rollout
can extend this; allow extra time for the first account test. Build images before
creating chargeable resources. Teardown can also take tens of minutes because
CloudFront/VPC-origin deletion and ENI cleanup are asynchronous.

Illustrative us-east-1 low-traffic base cost: EKS standard support $0.10/hour,
m6i.xlarge about $0.192/hour, ALB about $0.0225/hour plus LCUs. Together that is
about **$0.32/hour before disk, IPv4, registry, transfer and CloudFront usage**.
Budgeting $5–$10 for a short manual test is reasonable, not a spending cap.
Bedrock/AgentCore charges are separate and those services are not provisioned.
Stopping the browser or local containers does not stop AWS billing.
Sources: [EKS](https://aws.amazon.com/eks/pricing/),
[EC2 example](https://docs.aws.amazon.com/prescriptive-guidance/latest/optimize-costs-microsoft-workloads/right-size-selection.html),
[ALB](https://aws.amazon.com/elasticloadbalancing/pricing/).

## 1. Prepare your computer and sandbox role

Use an empty **dedicated sandbox account** and an AWS CLI profile that assumes
an IAM role in it. Do not use a dev/prod profile. Required local tools:

- Python 3.9+, Git, AWS CLI v2, Terraform >=1.9 and <2, Docker/Compose >=2.17,
  Helm 3, kubectl 1.34–1.36 for the default EKS 1.35.
- Docker memory at least 12 GiB and at least 30 GiB free disk. All application
  images are built as linux/amd64; Apple Silicon uses emulation.
- For optional browser checks, Node/npm and Playwright Chromium.

Check local tools without contacting AWS:

```sh
python3 scripts/aws_sandbox.py doctor
```

If Terraform is missing on macOS with Homebrew, install it before proceeding:

```sh
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

Other installers: [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html),
[Terraform](https://developer.hashicorp.com/terraform/install),
[kubectl for EKS](https://docs.aws.amazon.com/eks/latest/userguide/install-kubectl.html),
[Helm](https://helm.sh/docs/intro/install/). Use a kubectl minor version compatible
with the selected EKS version, not an arbitrarily newer client.

The operator role needs provisioning, read, update and cleanup permissions for
VPC/EC2, IAM, EKS, Auto Scaling, ECR, ELBv2 and CloudFront, including PassRole and
conditional CreateServiceLinkedRole for EKS/CloudFront. CloudFront's managed
prefix list consumes 55 security-group rule slots; the default quota of 60 is
sufficient for this dedicated ALB group. Account SCPs, regional service quotas
and organization tagging requirements can still block deployment. Preflight
checks do not certify those permissions or capacity.

Open a terminal and authenticate yourself:

```sh
aws sso login --profile YOUR_SANDBOX_ONE_PROFILE
```

Skip that command if your profile does not use SSO. Do not paste credentials or
the later generated access file into chat. You can share a redacted error message.

## 2. Use a dedicated checkout and configure once

Until the AWS PR is merged, use its branch:

```sh
git clone --branch codex/aws-https-launcher https://github.com/theMMRF/mmrf-virtual-lab-sandbox.git mmrf-aws-test
cd mmrf-aws-test
python3 scripts/aws_sandbox.py init   --profile YOUR_SANDBOX_ONE_PROFILE   --account-id YOUR_12_DIGIT_SANDBOX_ACCOUNT_ID
python3 scripts/aws_sandbox.py check
```

`init` only reads AWS identity/IAM and saves local configuration. It discovers
the full IAM role ARN (including an SSO role path) and your IPv4 egress address
using AWS's public check-IP service. AWS credentials stay in your normal CLI
profile. The Kubernetes API is limited to that egress `/32`.

Overrides, if necessary, belong on the `init` command:

- `--role-arn arn:aws:iam::ACCOUNT:role/FULL_ROLE_PATH` if `iam:GetRole` is denied.
- `--operator-cidr YOUR_PUBLIC_IPV4/32` if automatic IP detection is unsuitable.
- `--vpc-cidr 10.87.0.0/16` if the default overlaps another VPC.
- `--region …` or `--kubernetes-version …` only after checking service support
  and [the EKS calendar](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html).

A successful `init` is not repeated. If `check` detects a CIDR overlap before
provisioning, edit the local `generated/aws/config.json` vpc_cidr value and retry.
If your VPN/IP changes, update operator_cidr there before deployment. Never
change account, region or deployment name after resources exist; tear down using
the original configuration first. Do not copy state into another event account.

## 3. Build locally, then deploy

```sh
python3 scripts/aws_sandbox.py build
python3 scripts/aws_sandbox.py deploy --skip-build
```

The build step fetches pinned public sources, generates default fixtures, builds
six amd64 images sequentially and records their immutable local image IDs. Its
separate build project and `:aws-build` image tags preserve the regular local
sandbox. For memory headroom, stop your existing sandbox from its own checkout
before this step (`docker compose stop`); the launcher does not stop or change
another checkout's containers. Restart that local sandbox afterward if desired.

The deploy step:

1. Verifies account/role, checks the new network, and writes ignored tfvars.
2. Shows a Terraform plan. Type the sandbox account ID once to apply it.
3. Publishes the six images only to this deployment's six ECR repositories.
4. Writes a dedicated kubeconfig, creates a random team password in a Kubernetes
   Secret and a mode-0600 local file, then installs the Helm chart using image digests.
5. Waits for the chart and HTTPS route, verifies anonymous requests receive 401,
   and checks the authenticated synthetic API returns 1,000 cases.

For one command including builds, use `python3 scripts/aws_sandbox.py deploy`.
For unattended operator execution, `deploy --yes` skips the typed confirmation;
it does not bypass account checks. Initial manual testing should keep the prompt.

At completion the script prints the HTTPS URL and the local credential-file path.
To view the team login **on your own computer**:

```sh
python3 scripts/aws_sandbox.py credentials
```

Open the printed CloudFront URL, enter that username/password in the browser's
HTTP authentication prompt, and use the synthetic platform. No Gen3 credentials
are needed. The team password protects this shared demo, not production data.
It is excluded from Git and Docker build contexts and is injected only at runtime.
Do not place it in a URL or commit it. Share it with authorized builders through
your normal secure channel. To rotate it, remove only generated/aws/access.json
and rerun deploy --skip-build; the launcher recreates the entry pod afterward.

## 4. Verify and resume

```sh
python3 scripts/aws_sandbox.py status
python3 scripts/smoke.py --origin https://YOUR_DISTRIBUTION.cloudfront.net   --access-file generated/aws/access.json
npm ci
npx playwright install chromium
SANDBOX_ORIGIN=https://YOUR_DISTRIBUTION.cloudfront.net   SANDBOX_ACCESS_FILE=generated/aws/access.json npm run test:ui
```

Replace the example origin with the exact printed URL. The smoke tools refuse
production hosts and refuse to send team credentials to another origin. Browser
checks use a separate headless Chromium profile; normal browser sessions are
untouched. Review Projects, demographic cohorts, OncoMatrix, mutation/survival,
RNA-seq views, repository facets, manifests and downloads as in the local build.

If interrupted, keep the checkout, generated/aws and terraform state. Rerun
`deploy --skip-build` to resume with the recorded images, or `destroy` to clean
up a partial deployment. Failed Helm installs remain inspectable. The launcher
uses its dedicated kubeconfig; it does not change your normal kubectl context.
For diagnostics use the generated kubeconfig and `kubectl -n mmrf-synthetic get
pods`, `describe pod`, or `logs`. If a crashed process left operator.lock, confirm
it is no longer running before removing only that lock file.

The agent and MCP implementation remain hackathon work. A hosted agent can call
the protected HTTPS API with a securely supplied team credential, or developers
can add a tool server inside the cluster and explicitly configure its network
and authorization. No AgentCore runtime, model grants, Gateway OAuth or agent
IAM roles are created by this platform launcher. EKS does not make this an
identical production deployment: synthetic identity, ephemeral storage and the
small fixture dataset remain intentional differences.

## 5. Tear down from the SAME checkout

```sh
python3 scripts/aws_sandbox.py destroy
```

Review the destroy plan and type the account ID. The launcher empties only the
six ECR repositories owned by this Terraform state, deleting parent manifests
before their referenced images, then applies the saved destroy plan. Terraform
owns the ALB/CloudFront/ASG links, so no Kubernetes load-balancer controller
finalizers are involved. The worker's ephemeral index and team Secret disappear
with the cluster.

Do not delete the checkout/state while teardown is running or if it fails.
Retry `destroy` using the same directory/profile. CloudFront and service-managed
ENIs can take time to detach. Completion requires empty Terraform state; also
check the sandbox console for the test EKS cluster, EC2/node group, ALB, CloudFront
distribution, ECR repositories and VPC being gone. Shared AWS service-linked
roles can remain and are not deleted by this launcher. Billing reports can lag.
Only after that verification should you discard the local credential file and
checkout. There is no automatic expiry or shutdown timer.

For manual port-forward deployment and lower-level debugging, see
[the manual EKS guide](aws-manual.md).
