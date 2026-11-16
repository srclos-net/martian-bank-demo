# Deploy: fe-stackgen-run (Civo k3s) via Argo CD

https://bank.stackgen.run

The `martian-bank` Argo CD Application (`argocd.yaml`) manages everything in
namespace `martian-bank` from `main`: the `martianbank` Helm chart (with
`values-civo.yaml`) plus the raw Ingress in `manifests/`. Argo CD auto-syncs
(self-heal + prune), so changes land after `git push` to `main`.

## Manual prerequisite (created out-of-band on purpose)

customer-auth signs its JWTs with a key from a Secret that is **not** in this
repo (it is public). If it's missing, the `customer-auth` pod will fail with
`CreateContainerConfigError`:

```sh
kubectl create secret generic martianbank-jwt-secret \
  --context fe-stackgen-run -n martian-bank \
  --from-literal=jwt_secret="<random-64-hex>"
```

Create the namespace first if needed (`kubectl create ns martian-bank`).
To rotate: re-create the secret with a new value and `kubectl rollout restart
deployment/customer-auth -n martian-bank`.

## Chart notes

- `mongodb.enabled=false` means in-cluster MongoDB (the flag actually means
  "use external/Atlas"). The chart's `mo-data-pv` static hostPath template was
  removed so the PVC provisions dynamically via Civo's `civo-volume` class.
- `nginx` and `dashboard` Services were changed to ClusterIP — the chart had
  them hardcoded as LoadBalancer, which is redundant behind the Ingress and
  would bill extra Civo LoadBalancers.
- The chart's built-in ingress template is unusable (its backend service name
  doesn't exist in this chart) — the real Ingress lives in `manifests/`.
- The chart templates ignore `.Values.resources`, so pods run without
  resource requests (fine for a demo; do not scale this onto a busy cluster).
