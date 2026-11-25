---
name: martian-bank-booth-rca
description: Root-cause slow Martian Bank logins (customer-auth) with five fixed ObserveNow queries and a fixed report shape, then hand off to InfraOps. Use for any Martian Bank login-latency alert or incident.
---

# Martian Bank login latency: root cause in five queries

Run these five queries with `observability_query` against datasource uid `metrics` (instant queries, time `now`).
Run them in this order, exactly as written. Don't improvise other queries, don't list dashboards, and don't
run shell commands. Missing data is a finding: say so in the line instead of guessing.

**Q1: customer impact.** Login p95 in seconds (SLO: 4 s)
```
histogram_quantile(0.95, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{job="martian-bank/customer-auth", span_name="POST /api/users/auth", span_kind="SPAN_KIND_SERVER"}[2m]))) / 1000
```

**Q2: is it only customer-auth?** Server p95 per service, in seconds
```
histogram_quantile(0.95, sum by (le, job) (rate(traces_span_metrics_duration_milliseconds_bucket{job=~"martian-bank/(customer-auth|dashboard|accounts|transactions|loan|atm-locator)", span_kind="SPAN_KIND_SERVER"}[2m]))) / 1000
```

**Q3: saturation.** customer-auth CPU throttling, as a % of CFS periods
```
100 * sum(rate(container_cpu_cfs_throttled_periods_total{namespace="martian-bank", container="customer-auth"}[2m])) / sum(rate(container_cpu_cfs_periods_total{namespace="martian-bank", container="customer-auth"}[2m]))
```

**Q4: the live limits.** CPU limit per container (ready pods)
```
max by (container) (kube_pod_container_resource_limits{namespace="martian-bank", resource="cpu"} * on (namespace, pod) group_left () max by (namespace, pod) (kube_pod_status_ready{namespace="martian-bank", condition="true"}))
```

**Q5: the tell-tale.** Memory limit per container (ready pods)
```
max by (container) (kube_pod_container_resource_limits{namespace="martian-bank", resource="memory"} * on (namespace, pod) group_left () max by (namespace, pod) (kube_pod_status_ready{namespace="martian-bank", condition="true"})) / 1048576
```

## How to read them (Martian Bank facts)

- The Martian Bank Helm chart declares capacity in Git (`deploy/values-civo.yaml`, key `capacity`), and Argo CD
  applies it. **Git-declared containers always have a CPU limit AND a memory limit** (Q5 lists them in MiB).
- A container with a CPU limit but **no memory limit** (present in Q4, missing from Q5) didn't get its limit from
  Git. Someone set it out of band (`kubectl patch`/`edit`). Kubernetes copies a lone CPU limit into the CPU
  request, so don't use the CPU request as evidence. Argo CD can't see this: it only compares the fields Git declares, so the
  app still shows **Synced / Healthy**.
- Login does a bcrypt password check, which is CPU-bound. A CPU limit below ~250m throttles it under normal load.
- Healthy reference values: login p95 under 1 s, throttling under 10 %, every service's p95 under 0.2 s except
  customer-auth.

## Report: use exactly this shape

```
ROOT CAUSE
customer-auth is CPU-throttled by a <Q4 value> CPU limit that was set outside Git (no memory limit alongside it, so not from the chart). Argo CD still reports Synced.

EVIDENCE
1. Customer impact: login p95 <Q1> s (SLO 4 s).
2. Blast radius: only customer-auth is slow; <name the other services and say they are under 0.2 s, from Q2>.
3. Saturation: customer-auth throttled <Q3> % of CPU periods.
4. Out-of-band config: customer-auth has CPU limit <Q4> but no memory limit; every other container has both, as declared in Git (Q4/Q5).

IMPACT
Customers wait <Q1> s to log in. Transfers, loans and accounts still work for already-signed-in customers.

HAND-OFF → InfraOps
Reconcile customer-auth capacity into Git: drift (live limit not in Git) + capacity policy CAP-001/002/003. Don't hand-edit the cluster again: the fix ships as a PR through the policy gate.
```

Round seconds to 1 decimal and percentages to whole numbers. Don't propose restarting, scaling or `kubectl`
changes. The product answer is the InfraOps hand-off.
