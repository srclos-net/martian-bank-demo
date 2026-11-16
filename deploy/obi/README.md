# OBI (OpenTelemetry eBPF Instrumentation) — devopsnow

`otel/ebpf-instrument:v1.0.0`, DaemonSet on every node, privileged +
hostPID, discovering all app namespaces (infra/monitoring namespaces are
excluded — especially `devopsnow` itself, so OBI doesn't trace its own OTEL
export traffic). Spans/metrics export to `http://otel-collector.devopsnow:4318`,
then spanmetrics → vmagent/zipkin → stephgen-medussa (ObserveNow) as
described in `docs/failure-playbook.md`.

Managed by Argo CD via the `obi` Application (`deploy/argocd-obi.yaml`).

## 2026-11-16: enabled trace context propagation

**Why:** distributed traces were "sparse" — every service hop became its own
orphan trace, because OBI only *reads* incoming trace context by default and
does not inject it into outgoing requests. Fix:
`OTEL_EBPF_BPF_CONTEXT_PROPAGATION=all` on the DaemonSet (kept as an env var
rather than config YAML because v1.0.0 predates the v2 config schema; the env
var is stable across version bumps).

Feasible on this cluster because:

- all node kernels are 6.12.85 — far above the 5.17+ needed for network-level
  HTTP/1 and plaintext HTTP/2/gRPC parsing;
- all in-cluster bank traffic is plaintext HTTP/1 or gRPC, so header
  injection reaches every hop (TLS only terminates at traefik, outside the
  app hops).

Not retroactive: hops only link for traffic after the DaemonSet rolled. OBI's
experimental "span linking" feature (Go channel handoffs) was deliberately
NOT enabled — irrelevant here, the services are Flask/Node.

## Adoption history

OBI was originally hand-`kubectl apply`'d (see the playbooks context: the
whole devopsnow monitoring stack predates GitOps). Adopting it into Argo
CD worked by bringing live state to match git first (hand-applying these
manifests, which rolled the DaemonSet once), then applying
`deploy/argocd-obi.yaml` — Argo diffed to zero and took ownership without
recreating anything. Never hand-edit these resources again; git is the
source of truth and Argo self-heal + prune are on.

## Known Argo-ignored runtime state

None — unlike the martian-bank app, OBI has no demo dials. Everything here is
git state.
