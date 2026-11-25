---
name: martian-bank-booth-verify
description: Verify the Martian Bank login fix after the InfraOps PR shipped. Four fixed ObserveNow queries and a fixed VERIFIED / NOT VERIFIED verdict.
---

# Verify the customer-auth capacity fix

Run these four queries with `observability_query` (datasource uid `metrics`, instant, `now`), in order and
unchanged. No other tools.

**V1: login p95 (s)**
```
histogram_quantile(0.95, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{job="martian-bank/customer-auth", span_name="POST /api/users/auth", span_kind="SPAN_KIND_SERVER"}[2m]))) / 1000
```
**V2: throttling %**
```
100 * sum(rate(container_cpu_cfs_throttled_periods_total{namespace="martian-bank", container="customer-auth"}[2m])) / sum(rate(container_cpu_cfs_periods_total{namespace="martian-bank", container="customer-auth"}[2m]))
```
**V3: customer-auth CPU limit and memory limit in MiB (ready pod)**
```
max by (resource) (kube_pod_container_resource_limits{namespace="martian-bank", container="customer-auth", resource="cpu"} * on (namespace, pod) group_left () max by (namespace, pod) (kube_pod_status_ready{namespace="martian-bank", condition="true"}))
```
```
max by (resource) (kube_pod_container_resource_limits{namespace="martian-bank", container="customer-auth", resource="memory"} * on (namespace, pod) group_left () max by (namespace, pod) (kube_pod_status_ready{namespace="martian-bank", condition="true"})) / 1048576
```
**V4: is the alert still firing?** Use `list_firing_alerts` and look for "Martian Bank: customer logins slow".

## Verdict rules

VERIFIED only if all of these hold: V1 < 1.5 s, V2 < 25 %, the CPU limit is ≥ 0.25 core AND a memory limit exists
(capacity now comes from Git), and the alert isn't firing. Otherwise NOT VERIFIED, saying which check failed.
Spans arrive about 30–60 s after the sync, so if V1 has no data yet, say "wait 60 s and re-run".

## Report: exactly this shape

```
VERDICT: VERIFIED | NOT VERIFIED
- Login p95: <V1> s (was above 4 s during the incident)
- Throttling: <V2> %
- customer-auth capacity: CPU limit <V3 cpu> core, memory limit <V3 memory> MiB (declared in Git, owned by Argo CD)
- Alert: <resolved | still firing>
NEXT: <"Resolve the incident; postmortem: out-of-band CPU limit invisible to GitOps → now declared in Git and enforced by the capacity policy gate." | what to wait for>
```
