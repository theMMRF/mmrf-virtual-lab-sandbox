# EKS diagnostics

Run from the checkout used for [AWS deployment](aws-deployment.md).
The dedicated kubeconfig is `generated/aws/kubeconfig`.

```sh
python3 scripts/aws_sandbox.py status
kubectl --kubeconfig generated/aws/kubeconfig -n mmrf-synthetic get pods,services
kubectl --kubeconfig generated/aws/kubeconfig -n mmrf-synthetic logs deployment/guppy
kubectl --kubeconfig generated/aws/kubeconfig -n mmrf-synthetic logs deployment/synthetic-seed
```

For pod startup failures, use `describe pod POD_NAME` with the same kubeconfig
and namespace. For service-specific failures, replace the deployment name in
`logs` with `frontend`, `analysis`, `identity`, `access`, or `proteinpaint`.

## Local access through the Kubernetes API

```sh
kubectl --kubeconfig generated/aws/kubeconfig -n mmrf-synthetic \
  port-forward service/identity 3081:8080 --address 127.0.0.1
```

Open <http://localhost:3081>. Keep the command running during use; stop it with
Ctrl-C. This loopback route uses the synthetic session directly. The normal
CloudFront endpoint continues using its team login.
