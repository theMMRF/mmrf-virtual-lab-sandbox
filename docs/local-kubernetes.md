# Local Kubernetes

Use an amd64 kind host or VM for the complete chart. The ProteinPaint image is
amd64-only; Compose supports per-container emulation on Apple Silicon.

After local source fetch, fixture generation, and image builds:

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

Open <http://localhost:3081> or run
`python3 scripts/smoke.py --origin http://127.0.0.1:3081`.
NetworkPolicy enforcement depends on the cluster's CNI.

```sh
kind delete cluster --name mmrf-sandbox --kubeconfig generated/kubeconfig
```
