# Local Kubernetes

Docker Compose is the primary local developer launcher, including on Apple
Silicon. The public ProteinPaint base is amd64-only. A Kubernetes node cannot
select a different CPU architecture for one pod: use an **amd64 kind host/VM**
for a complete local chart test. Docker Desktop's per-container emulation is
sufficient for Compose but does not make ProteinPaint schedulable on an ARM node.

After the normal source fetch, fixture generation and image build:

```sh
kind create cluster --name mmrf-sandbox --kubeconfig generated/kubeconfig
kind load docker-image --name mmrf-sandbox \
  mmrf-sandbox/frontend:local mmrf-sandbox/guppy:local \
  mmrf-sandbox/analysis:local mmrf-sandbox/proteinpaint:local \
  mmrf-sandbox/identity:local mmrf-sandbox/seed:local
helm upgrade --install sandbox helm -n mmrf-synthetic --create-namespace \
  --kubeconfig generated/kubeconfig --wait --timeout 10m
kubectl --kubeconfig generated/kubeconfig -n mmrf-synthetic \
  port-forward service/identity 3081:8080 --address 127.0.0.1
```

Test with `python3 scripts/smoke.py --origin http://127.0.0.1:3081` and
`SANDBOX_ORIGIN=http://127.0.0.1:3081 npm run test:ui`. Every command explicitly
uses the isolated kubeconfig. Delete only this test cluster with `kind delete
cluster --name mmrf-sandbox`. Default kind networking does not enforce the chart's
NetworkPolicy; enforcement is an AWS acceptance check.
